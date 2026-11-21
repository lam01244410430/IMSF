"""Household endpoints (design §5.1). Creator becomes owner."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import Identity, require_auth
from app.currencies import SUPPORTED_CURRENCIES
from app.db import get_engine

router = APIRouter(prefix="/api/v2/households", tags=["households"])


class HouseholdIn(BaseModel):
    name: str
    default_currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    locale: str = "zh-CN"


@router.post("", status_code=201)
def create_household(body: HouseholdIn,
                     ident: Identity = Depends(require_auth)):
    if body.default_currency not in SUPPORTED_CURRENCIES:
        from fastapi import HTTPException
        raise HTTPException(status_code=400,
                            detail=f"default_currency must be one of {', '.join(SUPPORTED_CURRENCIES)}")
    engine = get_engine()
    with engine.begin() as conn:
        hid = conn.execute(
            text("INSERT INTO households (name, default_currency, timezone,"
                 " locale) VALUES (:n, :c, :tz, :loc) RETURNING id"),
            {"n": body.name, "c": body.default_currency,
             "tz": body.timezone, "loc": body.locale},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO household_members (user_id, household_id, role)"
                 " VALUES (:u, :h, 'owner')"),
            {"u": ident.user_id, "h": hid},
        )
        row = conn.execute(
            text("SELECT id, name, default_currency, timezone, locale,"
                 " created_at FROM households WHERE id = :h"),
            {"h": hid},
        ).first()
    return {"id": str(row[0]), "name": row[1], "default_currency": row[2],
            "timezone": row[3], "locale": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "role": "owner"}


@router.get("")
def list_households(ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT h.id, h.name, h.default_currency, h.timezone,"
                 " h.locale, h.created_at, m.role FROM households h"
                 " JOIN household_members m ON m.household_id = h.id"
                 " WHERE m.user_id = :u ORDER BY h.created_at"),
            {"u": ident.user_id},
        ).all()
    return [{"id": str(r[0]), "name": r[1], "default_currency": r[2],
             "timezone": r[3], "locale": r[4],
             "created_at": r[5].isoformat() if r[5] else None,
             "role": r[6]} for r in rows]
