"""Receipt endpoints (design §5.1, EXCEPT POST .../confirm — Step 3).

- POST /api/v2/receipts: multipart image (jpg/png/webp, <= 10MB),
  household_id, optional store_name / purchased_at. Saves the image to
  /var/lib/imsf-v2/receipts/{household_id}/{receipt_id}.{ext} (dirs
  0755), pushes a job to Redis, returns 202 {id, status: "pending"}.
  Supports Idempotency-Key (Redis, 24h TTL). total_amount is NOT taken
  from the client (§5.2) — the row is inserted with 0.00 and the worker
  fills the real total from OCR+Qwen.
- GET /api/v2/receipts: list, household-scoped, status filter, limit/offset.
- GET /api/v2/receipts/{id}: detail + lines + inventory_created.
- GET /api/v2/receipts/{id}/image: same-household only (else 403).
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.auth import Identity, require_auth, require_household_member, require_receipt_household
from app.db import (IDEMPOTENCY_PREFIX, IDEMPOTENCY_TTL_SECONDS, QUEUE_KEY,
                    get_engine, get_redis)

router = APIRouter(prefix="/api/v2/receipts", tags=["receipts"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".png": "image/png", ".webp": "image/webp"}


def _storage_dir() -> Path:
    return Path(os.environ.get("RECEIPT_STORAGE_DIR", "/var/lib/imsf-v2/receipts"))


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
