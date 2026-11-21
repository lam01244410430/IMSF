"""Spending-ledger endpoints (Phase 2 design §5.1, §5.3, §5.4).

- GET /api/v2/transactions: household-scoped list, newest first.
- POST /api/v2/transactions: manual expense/income. ``receipt_id`` is
  NEVER accepted from the client (only the worker/confirm path creates
  receipt transactions — see app/ledger.py); sending it is a 422.
- PATCH / DELETE /api/v2/transactions/{id}: only when ``receipt_id IS
  NULL``; a receipt transaction returns 409 (§3.1).
- GET /api/v2/spending/summary: per-currency expense summary. ``currency``
  is REQUIRED — missing it returns 400 (§5.4); the summary never sums
  across currencies (§5.3) and never includes income.

Household scoping returns 403 when the household does not belong to
the caller (Phase 2 design §5.4 — unlike the Phase 1 endpoints, which
return 400 for the same check).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.auth import (Identity, require_auth,
                      require_household_member_403)
from app.currencies import SUPPORTED_CURRENCIES
from app.db import get_engine

router = APIRouter(prefix="/api/v2/transactions", tags=["transactions"])
# The summary lives at /api/v2/spending/summary (design §5.1), not
# under /transactions, so it gets its own router.
summary_router = APIRouter(prefix="/api/v2/spending", tags=["spending"])

CURRENCIES = SUPPORTED_CURRENCIES
TYPES = ("expense", "income")
CATEGORIES = ("food", "household", "maintenance", "other")

_TRANSACTION_COLS = ("id, household_id, receipt_id, type, amount,"
                     " currency, category, occurred_at, note,"
                     " created_at, updated_at")


def _transaction_row(row) -> dict:
    return {
        "id": str(row[0]), "household_id": str(row[1]),
        "receipt_id": str(row[2]) if row[2] else None,
        "type": row[3], "amount": float(row[4]), "currency": row[5],
        "category": row[6],
        "occurred_at": row[7].isoformat() if row[7] else None,
        "note": row[8],
        "created_at": row[9].isoformat() if row[9] else None,
        "updated_at": row[10].isoformat() if row[10] else None,
    }


def _parse_dt(value: str | None, field: str) -> datetime | None:
    """Parse an ISO 8601 datetime query param; 400 when unparseable.

    A naive (timezone-less) value is read as UTC.
    """
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"{field} must be ISO 8601")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class TransactionCreate(BaseModel):
    # receipt_id is deliberately absent: extra="forbid" makes a client
    # that sends it fail loudly (422) instead of silently getting a
    # manual transaction (design §5.1).
    model_config = ConfigDict(extra="forbid")

    household_id: uuid.UUID
    type: str
    amount: Decimal = Field(gt=0)
    currency: str
    category: str
    occurred_at: datetime
    note: str | None = None


class TransactionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal | None = Field(default=None, gt=0)
    category: str | None = None
    note: str | None = None
    occurred_at: datetime | None = None


def _validate_enums(body_type: str | None, currency: str | None,
                    category: str | None) -> None:
    if body_type is not None and body_type not in TYPES:
        raise HTTPException(
            status_code=422, detail="type must be 'expense' or 'income'")
    if currency is not None and currency not in CURRENCIES:
        raise HTTPException(
            status_code=422, detail=f"currency must be one of {', '.join(CURRENCIES)}")
    if category is not None and category not in CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail="category must be one of food, household,"
                   " maintenance, other")


@router.get("")
def list_transactions(household_id: uuid.UUID = Query(...),
                      currency: str | None = Query(None),
                      category: str | None = Query(None),
                      from_: str | None = Query(None, alias="from"),
                      to: str | None = Query(None),
                      limit: int = Query(50, ge=1, le=100),
                      offset: int = Query(0, ge=0),
                      ident: Identity = Depends(require_auth)):
    require_household_member_403(household_id, ident)
    _validate_enums(None, currency, category)
    dt_from = _parse_dt(from_, "from")
    dt_to = _parse_dt(to, "to")
    engine = get_engine()
    with engine.connect() as conn:
        query = (f"SELECT {_TRANSACTION_COLS} FROM transactions"
                 " WHERE household_id=:h")
        params: dict = {"h": household_id, "lim": limit, "off": offset}
        if currency:
            query += " AND currency=:cur"
            params["cur"] = currency
        if category:
            query += " AND category=:cat"
            params["cat"] = category
        if dt_from is not None:
            query += " AND occurred_at >= :from"
            params["from"] = dt_from
        if dt_to is not None:
            query += " AND occurred_at < :to"
            params["to"] = dt_to
        query += (" ORDER BY occurred_at DESC, created_at DESC, id DESC"
                  " LIMIT :lim OFFSET :off")
        rows = conn.execute(text(query), params).all()
    return [_transaction_row(r) for r in rows]


@router.post("", status_code=201)
def create_transaction(body: TransactionCreate,
                       ident: Identity = Depends(require_auth)):
    require_household_member_403(body.household_id, ident)
    _validate_enums(body.type, body.currency, body.category)
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(f"INSERT INTO transactions (household_id, type, amount,"
                 " currency, category, occurred_at, note)"
                 " VALUES (:h, :t, :amount, :cur, :cat, :occurred, :note)"
                 f" RETURNING {_TRANSACTION_COLS}"),
            {"h": body.household_id, "t": body.type,
             "amount": body.amount, "cur": body.currency,
             "cat": body.category, "occurred": body.occurred_at,
             "note": body.note},
        ).first()
    return _transaction_row(row)


def _load_transaction_or_404(conn, transaction_id: uuid.UUID):
    row = conn.execute(
        text(f"SELECT {_TRANSACTION_COLS} FROM transactions"
             " WHERE id=:tid"),
        {"tid": transaction_id},
    ).first()
    if not row:
        raise HTTPException(status_code=404,
                            detail="Transaction not found")
    return row


@router.patch("/{transaction_id}")
def patch_transaction(transaction_id: uuid.UUID,
                      body: TransactionPatch,
                      ident: Identity = Depends(require_auth)):
    _validate_enums(None, None, body.category)
    engine = get_engine()
    with engine.begin() as conn:
        row = _load_transaction_or_404(conn, transaction_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        if row[2] is not None:
            # §3.1: a receipt transaction is never edited by hand.
            raise HTTPException(
                status_code=409,
                detail="Cannot edit a transaction created from a receipt;"
                       " correct the receipt instead")
        sets: list[str] = []
        params: dict = {"tid": transaction_id}
        if body.amount is not None:
            sets.append("amount=:amount")
            params["amount"] = body.amount
        if body.category is not None:
            sets.append("category=:category")
            params["category"] = body.category
        if body.note is not None:
            sets.append("note=:note")
            params["note"] = body.note
        if body.occurred_at is not None:
            sets.append("occurred_at=:occurred")
            params["occurred"] = body.occurred_at
        if not sets:
            raise HTTPException(status_code=400,
                                detail="Nothing to update")
        sets.append("updated_at=now()")
        updated = conn.execute(
            text(f"UPDATE transactions SET {', '.join(sets)}"
                 " WHERE id=:tid"
                 f" RETURNING {_TRANSACTION_COLS}"),
            params,
        ).first()
    return _transaction_row(updated)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: uuid.UUID,
                       ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        row = _load_transaction_or_404(conn, transaction_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        if row[2] is not None:
            # §3.1: a receipt transaction is never deleted by hand.
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a transaction created from a receipt;"
                       " correct the receipt instead")
        conn.execute(
            text("DELETE FROM transactions WHERE id=:tid"),
            {"tid": transaction_id},
        )
    return None


@summary_router.get("/summary")
def spending_summary(household_id: uuid.UUID = Query(...),
                     currency: str | None = Query(None),
                     from_: str | None = Query(None, alias="from"),
                     to: str | None = Query(None),
                     group_by: str | None = Query(None),
                     ident: Identity = Depends(require_auth)):
    """§5.3: expense-only summary for ONE currency.

    ``currency`` is required (§5.4: missing -> 400). ``from``/``to``
    bound ``occurred_at`` when given (unbounded otherwise). The
    response always carries both groupings (§5.1 shape); ``group_by``
    is accepted and validated but does not filter the response.
    """
    require_household_member_403(household_id, ident)
    if currency is None:
        raise HTTPException(
            status_code=400,
            detail="currency is required (spending is never summed"
                   " across currencies)")
    _validate_enums(None, currency, None)
    if group_by is not None and group_by not in ("category", "month"):
        raise HTTPException(
            status_code=400, detail="group_by must be category or month")
    dt_from = _parse_dt(from_, "from")
    dt_to = _parse_dt(to, "to")
    engine = get_engine()
    with engine.connect() as conn:
        where = ("WHERE household_id=:h AND currency=:cur"
                 " AND type='expense'")
        params: dict = {"h": household_id, "cur": currency}
        if dt_from is not None:
            where += " AND occurred_at >= :from"
            params["from"] = dt_from
        if dt_to is not None:
            where += " AND occurred_at < :to"
            params["to"] = dt_to
        total = conn.execute(
            text(f"SELECT COALESCE(SUM(amount), 0) FROM transactions {where}"),
            params,
        ).scalar_one()
        by_category = conn.execute(
            text(f"SELECT category, COALESCE(SUM(amount), 0)"
                 f" FROM transactions {where}"
                 " GROUP BY category ORDER BY category"),
            params,
        ).all()
        by_month = conn.execute(
            text("SELECT TO_CHAR(DATE_TRUNC('month', occurred_at),"
                 " 'YYYY-MM'), COALESCE(SUM(amount), 0)"
                 f" FROM transactions {where}"
                 " GROUP BY DATE_TRUNC('month', occurred_at)"
                 " ORDER BY DATE_TRUNC('month', occurred_at)"),
            params,
        ).all()
    return {
        "currency": currency,
        "total": float(total),
        "by_category": [{"category": c, "total": float(t)}
                        for c, t in by_category],
        "by_month": [{"month": m, "total": float(t)}
                     for m, t in by_month],
    }
