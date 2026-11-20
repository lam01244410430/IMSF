"""Fridge (inventory) endpoints (Phase 2 design §5.1, §5.2, §5.4).

- GET /api/v2/fridge: household-scoped list. Each item carries
  ``canonical_name`` (join on master_ingredients) and ``days_left``
  (``auto_expiry_date - today``, today in the household's timezone;
  null when ``auto_expiry_date`` is null). ``status`` defaults to
  'active', which means anything not consumed — the inventory status
  enum is fresh/expiring/expired/consumed, there is no 'active' value
  (design §5.1's "status='active'" is read as "not consumed").
- POST /api/v2/fridge/{item_id}/consume: status -> 'consumed'.
- POST /api/v2/fridge/{item_id}/extend: auto_expiry_date += days.
"""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.auth import Identity, require_auth, require_household_member_403
from app.db import get_engine

router = APIRouter(prefix="/api/v2/fridge", tags=["fridge"])

STATUSES = ("fresh", "expiring", "expired", "consumed")

_INVENTORY_COLS = (
    "i.id, i.household_id, i.receipt_id, i.receipt_line_id, i.raw_name,"
    " i.canonical_ingredient_id, i.quantity, i.unit, i.price,"
    " i.currency, i.storage_zone, i.added_date, i.auto_expiry_date,"
    " i.status, i.consumed_at, i.created_at, i.updated_at"
)


def _household_today(conn, household_id: uuid.UUID) -> date:
    """Today's date in the household's timezone (design §5.1)."""
    row = conn.execute(
        text("SELECT timezone FROM households WHERE id=:h"),
        {"h": household_id},
    ).first()
    tzname = row[0] if row and row[0] else "Asia/Shanghai"
    try:
        tz = ZoneInfo(tzname)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz).date()


def _inventory_row(row, today: date) -> dict:
    expiry = row[12]
    return {
        "id": str(row[0]), "household_id": str(row[1]),
        "receipt_id": str(row[2]) if row[2] else None,
        "receipt_line_id": str(row[3]) if row[3] else None,
        "raw_name": row[4],
        "canonical_ingredient_id": str(row[5]) if row[5] else None,
        "quantity": float(row[6]), "unit": row[7],
        "price": float(row[8]) if row[8] is not None else None,
        "currency": row[9], "storage_zone": row[10],
        "added_date": row[11].isoformat() if row[11] else None,
        "auto_expiry_date": expiry.isoformat() if expiry else None,
        "status": row[13],
        "consumed_at": row[14].isoformat() if row[14] else None,
        "created_at": row[15].isoformat() if row[15] else None,
        "updated_at": row[16].isoformat() if row[16] else None,
        "canonical_name": row[17],
        "days_left": (expiry - today).days if expiry else None,
    }


def _load_item_or_404(conn, item_id: uuid.UUID, today: date) -> dict:
    row = conn.execute(
        text(f"SELECT {_INVENTORY_COLS}, m.canonical_name"
             " FROM inventory_items i"
             " LEFT JOIN master_ingredients m"
             " ON m.id = i.canonical_ingredient_id"
             " WHERE i.id=:iid"),
        {"iid": item_id},
    ).first()
    if not row:
        raise HTTPException(status_code=404,
                            detail="Inventory item not found")
    return _inventory_row(row, today)


class FridgeExtend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int | None = None


@router.get("")
def list_fridge(household_id: uuid.UUID = Query(...),
                status: str = Query("active"),
                expiring_within_days: int | None = Query(None, ge=0),
                limit: int = Query(50, ge=1, le=100),
                offset: int = Query(0, ge=0),
                ident: Identity = Depends(require_auth)):
    require_household_member_403(household_id, ident)
    if status != "active" and status not in STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status must be one of active, fresh, expiring,"
                   " expired, consumed")
    engine = get_engine()
    with engine.connect() as conn:
        today = _household_today(conn, household_id)
        query = (f"SELECT {_INVENTORY_COLS}, m.canonical_name"
                 " FROM inventory_items i"
                 " LEFT JOIN master_ingredients m"
                 " ON m.id = i.canonical_ingredient_id"
                 " WHERE i.household_id=:h")
        params: dict = {"h": household_id, "lim": limit, "off": offset}
        if status == "active":
            query += " AND i.status != 'consumed'"
        else:
            query += " AND i.status=:status"
            params["status"] = status
        if expiring_within_days is not None:
            query += (" AND i.auto_expiry_date >= :today"
                      " AND i.auto_expiry_date <= :today_plus")
            params["today"] = today
            params["today_plus"] = today + timedelta(
                days=expiring_within_days)
        query += (" ORDER BY i.auto_expiry_date ASC NULLS LAST,"
                  " i.created_at ASC LIMIT :lim OFFSET :off")
        rows = conn.execute(text(query), params).all()
    return [_inventory_row(r, today) for r in rows]


@router.post("/{item_id}/consume")
def consume_item(item_id: uuid.UUID,
                 ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(f"SELECT {_INVENTORY_COLS}, m.canonical_name"
                 " FROM inventory_items i"
                 " LEFT JOIN master_ingredients m"
                 " ON m.id = i.canonical_ingredient_id"
                 " WHERE i.id=:iid"),
            {"iid": item_id},
        ).first()
        if not row:
            raise HTTPException(status_code=404,
                                detail="Inventory item not found")
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        if row[13] == "consumed":
            raise HTTPException(
                status_code=409, detail="Item is already consumed")
        conn.execute(
            text("UPDATE inventory_items"
                 " SET status='consumed', consumed_at=now(),"
                 " updated_at=now() WHERE id=:iid"),
            {"iid": item_id},
        )
        today = _household_today(conn, uuid.UUID(str(row[1])))
        return _load_item_or_404(conn, item_id, today)


@router.post("/{item_id}/extend")
def extend_item(item_id: uuid.UUID,
                body: FridgeExtend,
                ident: Identity = Depends(require_auth)):
    days = body.days if body.days is not None else 3
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(f"SELECT {_INVENTORY_COLS}, m.canonical_name"
                 " FROM inventory_items i"
                 " LEFT JOIN master_ingredients m"
                 " ON m.id = i.canonical_ingredient_id"
                 " WHERE i.id=:iid"),
            {"iid": item_id},
        ).first()
        if not row:
            raise HTTPException(status_code=404,
                                detail="Inventory item not found")
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        if days < 1:
            raise HTTPException(
                status_code=400, detail="days must be >= 1")
        if row[13] == "consumed":
            raise HTTPException(
                status_code=409,
                detail="Cannot extend a consumed item")
        today = _household_today(conn, uuid.UUID(str(row[1])))
        # A null expiry has nothing to add to: extend from today.
        base = row[12] if row[12] else today
        conn.execute(
            text("UPDATE inventory_items"
                 " SET auto_expiry_date=:exp, updated_at=now()"
                 " WHERE id=:iid"),
            {"exp": base + timedelta(days=days), "iid": item_id},
        )
        return _load_item_or_404(conn, item_id, today)
