"""Equipment + maintenance-log endpoints (Phase 2 design §3.5, §5.1, §5.6,
§6.4, §9 Gate D).

FIELD MAPPING (design §5.6 says POST takes {name, type} but the Phase 1
table has brand_model/device_type — mapped, NO name column added):
- ``type`` (request/response) <-> ``device_type`` (DB, NOT NULL, required)
- ``name`` (request/response) <-> ``brand_model`` (DB, nullable, optional)
Responses serialize BOTH ``name`` and ``type`` plus all other columns.

- GET /api/v2/equipments: household-scoped list, newest first; each
  item carries ``next_maintenance_date`` and ``days_until_maintenance``
  (``next_maintenance_date - today``, today in the household's
  timezone; null when there is no next date).
- POST /api/v2/equipments: create; status defaults to 'active'.
  ``maintenance_interval_days`` is NOT defaulted to 90 in code (design
  §6.4's "default 90" is a product suggestion; the field stays nullable
  per the coordinator's decision).
- GET / PATCH /api/v2/equipments/{id}: PATCH accepts name, type,
  usage_per_week, maintenance_interval_days, status, usage_intensity,
  household_size. When ``maintenance_interval_days`` changes AND
  ``last_maintained_at`` is set, ``next_maintenance_date`` is recomputed
  as ``last_maintained_at.date() + new interval`` (§6.4). Empty PATCH
  returns 400 ("Nothing to update").
- DELETE /api/v2/equipments/{id}: 204 only when the equipment has NO
  maintenance logs; logs exist -> 409. (The design does not specify
  this rule; the parent brief prescribes it.)
- POST /api/v2/equipments/{id}/maintenance: log a maintenance event.
  All three steps run in ONE DB transaction (§3.5): (1) INSERT the log;
  (2) UPDATE equipments — ``last_maintained_at = performed_at``,
  ``next_maintenance_date = performed_at.date() +
  maintenance_interval_days`` (NULL interval -> NULL, per the
  coordinator's decision); (3) if ``cost`` is present, INSERT a
  transaction (type expense, category maintenance, amount = cost,
  currency = currency, occurred_at = performed_at, household_id = the
  equipment's household, receipt_id NULL) and set the log's
  ``transaction_id`` to it. Returns ``{log, equipment, transaction}``
  (``transaction`` is null when no cost was logged).
- GET /api/v2/equipments/{id}/maintenance: history, newest first.

FIXED interval only (Lam DECIDED D5, §10) — NO wear-based formula:
``usage_per_week`` is stored and returned but never used in any
computation here.

Household scoping returns 403 when the household does not belong to
the caller (design §5.4). Single-equipment endpoints load the
equipment first (404 if missing), then check its household membership
(403) — the same 404/403 ordering as app/api/transactions.py and
app/api/shopping_lists.py.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.auth import (Identity, require_auth,
                      require_household_member_403)
from app.db import get_engine

router = APIRouter(prefix="/api/v2/equipments", tags=["equipments"])

EQUIPMENT_STATUSES = ("active", "retired")
USAGE_INTENSITIES = ("low", "medium", "high")
MAINTENANCE_TYPES = ("cleaning", "filter_replace", "repair", "inspection")
CURRENCIES = ("CNY", "VND")

_EQUIPMENT_COLS = (
    "id, household_id, device_type, brand_model, usage_intensity,"
    " last_maintained_at, next_maintenance_date, rag_maintenance_notes,"
    " status, household_size, usage_per_week, maintenance_interval_days,"
    " created_at, updated_at"
)
_LOG_COLS = (
    "id, equipment_id, performed_at, maintenance_type, note, cost,"
    " currency, transaction_id, created_at, updated_at"
)
_TRANSACTION_COLS = (
    "id, household_id, receipt_id, type, amount, currency, category,"
    " occurred_at, note, created_at, updated_at"
)


def _household_today(conn, household_id: uuid.UUID) -> date:
    """Today's date in the household's timezone (same helper as fridge)."""
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


def _equipment_row(row, today: date) -> dict:
    next_date = row[6]
    return {
        "id": str(row[0]), "household_id": str(row[1]),
        # Mapping (see module docstring): type <-> device_type,
        # name <-> brand_model.
        "type": row[2], "name": row[3],
        "device_type": row[2], "brand_model": row[3],
        "usage_intensity": row[4],
        "last_maintained_at": row[5].isoformat() if row[5] else None,
        "next_maintenance_date": (
            next_date.isoformat() if next_date else None),
        "rag_maintenance_notes": row[7],
        "status": row[8],
        "household_size": row[9],
        "usage_per_week": row[10],
        "maintenance_interval_days": row[11],
        "created_at": row[12].isoformat() if row[12] else None,
        "updated_at": row[13].isoformat() if row[13] else None,
        "days_until_maintenance": (
            (next_date - today).days if next_date else None),
    }


def _log_row(row) -> dict:
    return {
        "id": str(row[0]), "equipment_id": str(row[1]),
        "performed_at": row[2].isoformat() if row[2] else None,
        "maintenance_type": row[3], "note": row[4],
        "cost": float(row[5]) if row[5] is not None else None,
        "currency": row[6],
        "transaction_id": str(row[7]) if row[7] else None,
        "created_at": row[8].isoformat() if row[8] else None,
        "updated_at": row[9].isoformat() if row[9] else None,
    }


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


def _load_equipment_or_404(conn, equipment_id: uuid.UUID):
    row = conn.execute(
        text(f"SELECT {_EQUIPMENT_COLS} FROM equipments WHERE id=:eid"),
        {"eid": equipment_id},
    ).first()
    if not row:
        raise HTTPException(status_code=404,
                            detail="Equipment not found")
    return row


class EquipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    household_id: uuid.UUID
    name: str | None = None
    # Optional in the model so a missing value can be answered with
    # 400 (not Pydantic's 422) — device_type is NOT NULL in the DB.
    type: str | None = None
    usage_per_week: int | None = Field(default=None, ge=0)
    maintenance_interval_days: int | None = Field(default=None, gt=0)


class EquipmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    type: str | None = None
    usage_per_week: int | None = Field(default=None, ge=0)
    maintenance_interval_days: int | None = Field(default=None, gt=0)
    status: str | None = None
    usage_intensity: str | None = None
    household_size: int | None = Field(default=None, gt=0)


class MaintenanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    performed_at: datetime
    maintenance_type: Literal["cleaning", "filter_replace", "repair",
                              "inspection"]
    note: str | None = None
    cost: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None


def _validate_status(status: str | None) -> None:
    if status is not None and status not in EQUIPMENT_STATUSES:
        raise HTTPException(
            status_code=422, detail="status must be 'active' or 'retired'")


def _validate_usage_intensity(value: str | None) -> None:
    if value is not None and value not in USAGE_INTENSITIES:
        raise HTTPException(
            status_code=422,
            detail="usage_intensity must be one of low, medium, high")


def _validate_currency(currency: str | None) -> None:
    if currency is not None and currency not in CURRENCIES:
        raise HTTPException(
            status_code=422, detail="currency must be CNY or VND")


@router.get("")
def list_equipments(household_id: uuid.UUID = Query(...),
                    ident: Identity = Depends(require_auth)):
    require_household_member_403(household_id, ident)
    engine = get_engine()
    with engine.connect() as conn:
        today = _household_today(conn, household_id)
        rows = conn.execute(
            text(f"SELECT {_EQUIPMENT_COLS} FROM equipments"
                 " WHERE household_id=:h"
                 " ORDER BY created_at DESC, id DESC"),
            {"h": household_id},
        ).all()
    return [_equipment_row(r, today) for r in rows]


@router.post("", status_code=201)
def create_equipment(body: EquipmentCreate,
                     ident: Identity = Depends(require_auth)):
    require_household_member_403(body.household_id, ident)
    if body.type is None or not body.type.strip():
        raise HTTPException(status_code=400, detail="type is required")
    engine = get_engine()
    with engine.begin() as conn:
        today = _household_today(conn, body.household_id)
        row = conn.execute(
            text(f"INSERT INTO equipments (household_id, device_type,"
                 " brand_model, usage_per_week,"
                 " maintenance_interval_days)"
                 " VALUES (:h, :dtype, :brand, :upw, :interval)"
                 f" RETURNING {_EQUIPMENT_COLS}"),
            {"h": body.household_id, "dtype": body.type,
             "brand": body.name, "upw": body.usage_per_week,
             "interval": body.maintenance_interval_days},
        ).first()
    return _equipment_row(row, today)


@router.get("/{equipment_id}")
def get_equipment(equipment_id: uuid.UUID,
                  ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.connect() as conn:
        row = _load_equipment_or_404(conn, equipment_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        today = _household_today(conn, uuid.UUID(str(row[1])))
    return _equipment_row(row, today)


@router.patch("/{equipment_id}")
def patch_equipment(equipment_id: uuid.UUID,
                    body: EquipmentPatch,
                    ident: Identity = Depends(require_auth)):
    _validate_status(body.status)
    _validate_usage_intensity(body.usage_intensity)
    if body.type is not None and not body.type.strip():
        raise HTTPException(status_code=400, detail="type is required")
    engine = get_engine()
    with engine.begin() as conn:
        row = _load_equipment_or_404(conn, equipment_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        today = _household_today(conn, uuid.UUID(str(row[1])))
        sets: list[str] = []
        params: dict = {"eid": equipment_id}
        if body.name is not None:
            sets.append("brand_model=:brand")
            params["brand"] = body.name
        if body.type is not None:
            sets.append("device_type=:dtype")
            params["dtype"] = body.type
        if body.usage_per_week is not None:
            sets.append("usage_per_week=:upw")
            params["upw"] = body.usage_per_week
        if body.maintenance_interval_days is not None:
            sets.append("maintenance_interval_days=:interval")
            params["interval"] = body.maintenance_interval_days
        if body.status is not None:
            sets.append("status=:status")
            params["status"] = body.status
        if body.usage_intensity is not None:
            sets.append("usage_intensity=:intensity")
            params["intensity"] = body.usage_intensity
        if body.household_size is not None:
            sets.append("household_size=:hsize")
            params["hsize"] = body.household_size
        if not sets:
            raise HTTPException(status_code=400,
                                detail="Nothing to update")
        if (body.maintenance_interval_days is not None
                and row[5] is not None):
            # §6.4: recompute the next date from the last maintenance
            # when the interval changes.
            next_date = (row[5].date()
                         + timedelta(days=body.maintenance_interval_days))
            sets.append("next_maintenance_date=:next_date")
            params["next_date"] = next_date
        sets.append("updated_at=now()")
        updated = conn.execute(
            text(f"UPDATE equipments SET {', '.join(sets)}"
                 " WHERE id=:eid"
                 f" RETURNING {_EQUIPMENT_COLS}"),
            params,
        ).first()
    return _equipment_row(updated, today)


@router.delete("/{equipment_id}", status_code=204)
def delete_equipment(equipment_id: uuid.UUID,
                     ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        row = _load_equipment_or_404(conn, equipment_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        log_count = conn.execute(
            text("SELECT COUNT(*) FROM equipment_maintenance_logs"
                 " WHERE equipment_id=:eid"),
            {"eid": equipment_id},
        ).scalar_one()
        if log_count > 0:
            # Parent-brief rule (not in the design): equipment with a
            # maintenance history cannot be deleted — the logs are the
            # audit trail for the ledger transactions they created.
            raise HTTPException(
                status_code=409,
                detail="Cannot delete equipment with maintenance logs")
        conn.execute(
            text("DELETE FROM equipments WHERE id=:eid"),
            {"eid": equipment_id},
        )
    return None


@router.post("/{equipment_id}/maintenance", status_code=201)
def log_maintenance(equipment_id: uuid.UUID,
                    body: MaintenanceCreate,
                    ident: Identity = Depends(require_auth)):
    _validate_currency(body.currency)
    if body.cost is not None and body.currency is None:
        # §5.4: cost without currency -> 400.
        raise HTTPException(
            status_code=400,
            detail="currency is required when cost is present")
    performed_at = body.performed_at
    if performed_at.tzinfo is None:
        performed_at = performed_at.replace(tzinfo=timezone.utc)
    engine = get_engine()
    with engine.begin() as conn:
        row = _load_equipment_or_404(conn, equipment_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        today = _household_today(conn, uuid.UUID(str(row[1])))
        interval = row[11]  # maintenance_interval_days
        next_date = (performed_at.date() + timedelta(days=interval)
                     if interval is not None else None)
        log_row = conn.execute(
            text(f"INSERT INTO equipment_maintenance_logs (equipment_id,"
                 " performed_at, maintenance_type, note, cost, currency)"
                 " VALUES (:eid, :performed, :mtype, :note, :cost, :cur)"
                 f" RETURNING {_LOG_COLS}"),
            {"eid": equipment_id, "performed": performed_at,
             "mtype": body.maintenance_type, "note": body.note,
             "cost": body.cost, "cur": body.currency},
        ).first()
        transaction_row = None
        # transactions.amount has CHECK > 0, so a zero cost has no ledger
        # row (the log still records cost 0); only cost > 0 creates one.
        if body.cost is not None and body.cost > 0:
            transaction_row = conn.execute(
                text(f"INSERT INTO transactions (household_id, type,"
                     " amount, currency, category, occurred_at)"
                     " VALUES (:h, 'expense', :amount, :cur,"
                     " 'maintenance', :occurred)"
                     f" RETURNING {_TRANSACTION_COLS}"),
                {"h": row[1], "amount": body.cost,
                 "cur": body.currency, "occurred": performed_at},
            ).first()
            log_row = conn.execute(
                text("UPDATE equipment_maintenance_logs"
                     " SET transaction_id=:tid, updated_at=now()"
                     " WHERE id=:lid"
                     f" RETURNING {_LOG_COLS}"),
                {"tid": transaction_row[0], "lid": log_row[0]},
            ).first()
        updated = conn.execute(
            text("UPDATE equipments"
                 " SET last_maintained_at=:performed,"
                 " next_maintenance_date=:next_date, updated_at=now()"
                 " WHERE id=:eid"
                 f" RETURNING {_EQUIPMENT_COLS}"),
            {"performed": performed_at, "next_date": next_date,
             "eid": equipment_id},
        ).first()
    return {
        "log": _log_row(log_row),
        "equipment": _equipment_row(updated, today),
        "transaction": (_transaction_row(transaction_row)
                        if transaction_row is not None else None),
    }


@router.get("/{equipment_id}/maintenance")
def list_maintenance(equipment_id: uuid.UUID,
                     limit: int = Query(20, ge=1, le=100),
                     offset: int = Query(0, ge=0),
                     ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.connect() as conn:
        row = _load_equipment_or_404(conn, equipment_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        rows = conn.execute(
            text(f"SELECT {_LOG_COLS} FROM equipment_maintenance_logs"
                 " WHERE equipment_id=:eid"
                 " ORDER BY performed_at DESC, created_at DESC, id DESC"
                 " LIMIT :lim OFFSET :off"),
            {"eid": equipment_id, "lim": limit, "off": offset},
        ).all()
    return [_log_row(r) for r in rows]
