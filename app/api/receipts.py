"""Receipt endpoints (design §5.1, including POST .../confirm — Step 3).

- POST /api/v2/receipts: multipart image (jpg/png/webp, <= 10MB),
  household_id, optional store_name / purchased_at. Saves the image to
  /var/lib/imsf/receipts/{household_id}/{receipt_id}.{ext} (dirs
  0755), pushes a job to Redis, returns 202 {id, status: "pending"}.
  Supports Idempotency-Key (Redis, 24h TTL). total_amount is NOT taken
  from the client (§5.2) — the row is inserted with 0.00 and the worker
  fills the real total from OCR+Qwen.
- GET /api/v2/receipts: list, household-scoped, status filter, limit/offset.
- GET /api/v2/receipts/{id}: detail + lines + inventory_created.
- GET /api/v2/receipts/{id}/image: same-household only (else 403).
- POST /api/v2/receipts/{id}/confirm (§5.1, §5.4): only when status =
  needs_review, else 409. Body {lines: [{line_id, quantity, unit,
  price, is_stock_item}]}. Applies the corrections, re-runs the §6.4
  reconciliation on the corrected lines; if it passes, creates
  inventory_items for is_stock_item lines (same expiry logic as the
  worker) and marks completed; if it still fails, stays needs_review
  with the updated error_message and the corrected lines saved. The
  whole confirm (lines update + inventory creation + status change)
  runs in ONE database transaction.
"""

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth import Identity, require_auth, require_household_member, require_receipt_household
from app.db import (IDEMPOTENCY_PREFIX, IDEMPOTENCY_TTL_SECONDS, QUEUE_KEY,
                    get_engine, get_redis)
from app.ledger import insert_receipt_transaction
from app.rag import shelf_life_days_for
from app.reconcile import check_reconciliation, insert_inventory_item

router = APIRouter(prefix="/api/v2/receipts", tags=["receipts"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".png": "image/png", ".webp": "image/webp"}


def _storage_dir() -> Path:
    return Path(os.environ.get("RECEIPT_STORAGE_DIR", "/var/lib/imsf/receipts"))


def _receipt_row(row) -> dict:
    return {
        "id": str(row[0]), "household_id": str(row[1]),
        "uploaded_by_user_id": str(row[2]) if row[2] else None,
        "image_url": row[3], "store_name": row[4],
        "purchased_at": row[5].isoformat() if row[5] else None,
        "total_amount": float(row[6]), "currency": row[7],
        "status": row[8], "ocr_raw_text": row[9],
        "error_message": row[10],
        "processed_at": row[11].isoformat() if row[11] else None,
        "created_at": row[12].isoformat() if row[12] else None,
        "updated_at": row[13].isoformat() if row[13] else None,
    }


_RECEIPT_COLS = ("id, household_id, uploaded_by_user_id, image_url,"
                 " store_name, purchased_at, total_amount, currency,"
                 " status, ocr_raw_text, error_message, processed_at,"
                 " created_at, updated_at")


class ConfirmLine(BaseModel):
    line_id: uuid.UUID
    quantity: Decimal
    unit: str
    price: Decimal
    is_stock_item: bool


class ConfirmBody(BaseModel):
    lines: list[ConfirmLine] = Field(min_length=1)


@router.post("", status_code=202)
async def upload_receipt(
    request: Request,
    household_id: uuid.UUID = Form(...),
    image: UploadFile = File(...),
    store_name: str | None = Form(None),
    purchased_at: str | None = Form(None),
    ident: Identity = Depends(require_auth),
):
    require_household_member(household_id, ident)
    filename = (image.filename or "").lower()
    ext = Path(filename).suffix
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail="Image must be jpg, png or webp")
    content = await image.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400,
                            detail="Image exceeds 10MB")
    if not content:
        raise HTTPException(status_code=400, detail="Empty image")

    # Idempotency: same key + household within 24h -> same receipt.
    idem_key = request.headers.get("Idempotency-Key")
    redis_client = get_redis()
    idem_redis_key = None
    if idem_key:
        idem_redis_key = f"{IDEMPOTENCY_PREFIX}{household_id}:{idem_key}"
        existing = redis_client.get(idem_redis_key)
        if existing:
            engine = get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text(f"SELECT {_RECEIPT_COLS} FROM receipts WHERE id=:rid"),
                    {"rid": uuid.UUID(existing)},
                ).first()
            if row:
                return {"id": str(row[0]), "status": row[8]}

    engine = get_engine()
    with engine.connect() as conn:
        currency = conn.execute(
            text("SELECT default_currency FROM households WHERE id=:h"),
            {"h": household_id},
        ).scalar_one()
    purchased_dt = None
    if purchased_at:
        try:
            purchased_dt = datetime.fromisoformat(purchased_at)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail="purchased_at must be ISO 8601")

    receipt_id = uuid.uuid4()
    dest_dir = _storage_dir() / str(household_id)
    dest_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    dest = dest_dir / f"{receipt_id}{ext}"
    dest.write_bytes(content)
    os.chmod(dest, 0o644)

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO receipts (id, household_id,"
                 " uploaded_by_user_id, image_url, store_name, purchased_at,"
                 " total_amount, currency, status)"
                 " VALUES (:id, :h, :u, :url, :store, :purchased, 0, :cur,"
                 " 'pending')"),
            {"id": receipt_id, "h": household_id, "u": ident.user_id,
             "url": f"/api/v2/receipts/{receipt_id}/image",
             "store": store_name, "purchased": purchased_dt, "cur": currency},
        )
    if idem_redis_key:
        redis_client.set(idem_redis_key, str(receipt_id),
                         ex=IDEMPOTENCY_TTL_SECONDS)
    redis_client.rpush(QUEUE_KEY, json.dumps({
        "receipt_id": str(receipt_id), "household_id": str(household_id),
        "image_path": str(dest), "attempts": 0,
    }))
    return {"id": str(receipt_id), "status": "pending"}


@router.get("")
def list_receipts(household_id: uuid.UUID = Query(...),
                  status: str | None = Query(None),
                  limit: int = Query(20, ge=1, le=100),
                  offset: int = Query(0, ge=0),
                  ident: Identity = Depends(require_auth)):
    require_household_member(household_id, ident)
    if status and status not in ("pending", "processing", "completed",
                                 "failed", "needs_review"):
        raise HTTPException(status_code=400, detail="Invalid status filter")
    engine = get_engine()
    with engine.connect() as conn:
        if status:
            rows = conn.execute(
                text(f"SELECT {_RECEIPT_COLS} FROM receipts"
                     " WHERE household_id=:h AND status=:s"
                     " ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
                {"h": household_id, "s": status, "lim": limit, "off": offset},
            ).all()
        else:
            rows = conn.execute(
                text(f"SELECT {_RECEIPT_COLS} FROM receipts"
                     " WHERE household_id=:h"
                     " ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
                {"h": household_id, "lim": limit, "off": offset},
            ).all()
    return [_receipt_row(r) for r in rows]


@router.get("/{receipt_id}")
def get_receipt(receipt_id: uuid.UUID,
                ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_RECEIPT_COLS} FROM receipts WHERE id=:rid"),
            {"rid": receipt_id},
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Receipt not found")
        require_receipt_household(uuid.UUID(str(row[1])), ident)
        lines = conn.execute(
            text("SELECT l.id, l.line_no, l.raw_name, l.quantity, l.unit,"
                 " l.price, l.currency, l.canonical_ingredient_id,"
                 " m.canonical_name, l.is_stock_item"
                 " FROM receipt_lines l"
                 " LEFT JOIN master_ingredients m"
                 "   ON m.id = l.canonical_ingredient_id"
                 " WHERE l.receipt_id=:rid ORDER BY l.line_no"),
            {"rid": receipt_id},
        ).all()
        inventory_created = conn.execute(
            text("SELECT count(*) FROM inventory_items"
                 " WHERE receipt_id=:rid"),
            {"rid": receipt_id},
        ).scalar_one()
    out = _receipt_row(row)
    out["lines"] = [{
        "id": str(ln[0]), "line_no": ln[1], "raw_name": ln[2],
        "quantity": float(ln[3]), "unit": ln[4], "price": float(ln[5]),
        "currency": ln[6],
        "canonical_ingredient_id": str(ln[7]) if ln[7] else None,
        "canonical_name": ln[8], "is_stock_item": ln[9],
    } for ln in lines]
    out["inventory_created"] = inventory_created
    return out


@router.post("/{receipt_id}/confirm")
def confirm_receipt(receipt_id: uuid.UUID,
                    body: ConfirmBody,
                    ident: Identity = Depends(require_auth)):
    """§5.1 confirm: only when status = needs_review, else 409 (§5.4).

    Applies the corrected lines, re-runs the §6.4 reconciliation on
    ALL lines of the receipt (corrected + untouched), and either
    creates inventory + completes, or stays needs_review with the
    updated error_message. One transaction for the whole confirm.
    """
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(f"SELECT {_RECEIPT_COLS} FROM receipts WHERE id=:rid"
                 " FOR UPDATE"),
            {"rid": receipt_id},
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Receipt not found")
        require_receipt_household(uuid.UUID(str(row[1])), ident)
        if row[8] != "needs_review":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot confirm a receipt with status"
                       f" '{row[8]}' (must be 'needs_review')")
        existing = conn.execute(
            text("SELECT id, line_no, raw_name, quantity, unit, price,"
                 " currency, canonical_ingredient_id, is_stock_item"
                 " FROM receipt_lines WHERE receipt_id=:rid"
                 " ORDER BY line_no"),
            {"rid": receipt_id},
        ).all()
        by_id = {str(r[0]): r for r in existing}
        # §5.4 422: invalid corrected line (quantity <= 0; negative
        # price except on a non-stock discount/fee line; empty unit;
        # line_id that is not part of this receipt).
        for cl in body.lines:
            key = str(cl.line_id)
            if key not in by_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"line_id {key} is not part of this receipt")
            if cl.quantity <= 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"line {key}: quantity must be > 0")
            if not (cl.unit or "").strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"line {key}: unit must not be empty")
            if cl.price < 0 and cl.is_stock_item:
                raise HTTPException(
                    status_code=422,
                    detail=f"line {key}: negative price is only allowed"
                           " on a non-stock (discount/fee) line")
        for cl in body.lines:
            conn.execute(
                text("UPDATE receipt_lines SET quantity=:qty, unit=:unit,"
                     " price=:price, is_stock_item=:stock WHERE id=:lid"),
                {"qty": cl.quantity, "unit": cl.unit.strip(),
                 "price": cl.price, "stock": cl.is_stock_item,
                 "lid": cl.line_id},
            )
        # Re-run §6.4 on ALL lines (corrected + untouched).
        lines_total = conn.execute(
            text("SELECT COALESCE(SUM(price), 0) FROM receipt_lines"
                 " WHERE receipt_id=:rid"),
            {"rid": receipt_id},
        ).scalar_one()
        total_amount = row[6]  # NUMERIC from the receipt row
        ok, error_msg = check_reconciliation(lines_total, total_amount)
        if not ok:
            # Corrected lines are saved; stays needs_review with the
            # updated error_message; processed_at marks this run.
            conn.execute(
                text("UPDATE receipts SET error_message=:msg,"
                     " processed_at=now(), updated_at=now()"
                     " WHERE id=:rid"),
                {"msg": error_msg, "rid": receipt_id},
            )
        else:
            # Reconciliation passed: create inventory for stock lines
            # (same expiry logic as the worker), then complete.
            master_rows = conn.execute(
                text("SELECT id, canonical_name, default_storage_zone,"
                     " default_shelf_life_days FROM master_ingredients")
            ).all()
            master_by_id = {
                r[0]: {"id": r[0], "name": r[1], "zone": r[2],
                       "shelf_life": r[3]}
                for r in master_rows
            }
            # Defensive: a needs_review receipt should have no inventory,
            # but never create duplicates if one somehow exists.
            conn.execute(
                text("DELETE FROM inventory_items WHERE receipt_id=:rid"),
                {"rid": receipt_id},
            )
            lines_now = conn.execute(
                text("SELECT id, raw_name, quantity, unit, price, currency,"
                     " canonical_ingredient_id, is_stock_item"
                     " FROM receipt_lines WHERE receipt_id=:rid"
                     " ORDER BY line_no"),
                {"rid": receipt_id},
            ).all()
            added = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            # Phase 2 Step 5 (§7.3): same expiry logic as the worker —
            # seed > RAG > +3. RAG is consulted only when the seed shelf
            # life is NULL, once per canonical name; a RAG failure
            # degrades to +3 and never fails the confirm. (Twin of
            # worker.main._rag_shelf_life_days; kept separate so the API
            # module never imports the Redis worker.)
            rag_cache: dict = {}
            for ln in lines_now:
                if ln[7] and ln[2] > 0:
                    canon = master_by_id.get(ln[6])
                    rag_days = None
                    if canon is not None \
                            and canon.get("shelf_life") is None:
                        name = canon["name"]
                        if name not in rag_cache:
                            try:
                                found = shelf_life_days_for(name)
                                rag_cache[name] = (
                                    found["days"] if found else None)
                            except Exception:
                                rag_cache[name] = None
                        rag_days = rag_cache[name]
                    insert_inventory_item(
                        conn, uuid.UUID(str(row[1])), receipt_id, ln[0],
                        ln[1], canon, ln[2], ln[3], ln[4], ln[5], added,
                        rag_shelf_life_days=rag_days)
            # §3.1: the receipt's one ledger row, in the SAME DB
            # transaction as the inventory creation — a receipt
            # completed via confirm gets its ledger row too, and
            # ux_transactions_receipt blocks a second one.
            insert_receipt_transaction(
                conn, uuid.UUID(str(row[1])), receipt_id, row[6], row[7],
                row[5])
            conn.execute(
                text("UPDATE receipts SET status='completed',"
                     " error_message=NULL, processed_at=now(),"
                     " updated_at=now() WHERE id=:rid"),
                {"rid": receipt_id},
            )
    # Read the fresh detail only AFTER the transaction commits, so the
    # returned receipt reflects the confirmed lines and new status.
    return get_receipt(receipt_id, ident)


@router.get("/{receipt_id}/image")
def get_receipt_image(receipt_id: uuid.UUID,
                      ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT household_id, image_url FROM receipts WHERE id=:rid"),
            {"rid": receipt_id},
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Receipt not found")
        require_receipt_household(uuid.UUID(str(row[0])), ident)
    # image_url stores the API path (§5.5), not a file path; the file on
    # disk is {receipt_id}.{ext} under the household directory.
    candidates = sorted((_storage_dir() / str(row[0])).glob(f"{receipt_id}.*"))
    if not candidates:
        raise HTTPException(status_code=404, detail="Image file not found")
    path = candidates[0]
    ext = path.suffix.lower()
    return FileResponse(path, media_type=ALLOWED_EXT.get(ext, "image/jpeg"))
