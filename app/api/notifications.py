"""Notification endpoints (Phase 2 design §5.1, §5.2, §6.2, §5.4).

- GET /api/v2/notifications: household-scoped list, newest first.
- POST /api/v2/notifications/{id}/respond: Lazy Tracking 1-tap
  (§6.2). Only when type='lazy_tracking' and status is open
  (sent/delivered/read); otherwise 409. In ONE DB transaction the
  notification goes to 'responded' and the linked inventory item is
  consumed (used_up) or extended (extended, days default 3, max 30).
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.api.fridge import _household_today
from app.auth import Identity, require_auth, require_household_member_403
from app.db import get_engine

router = APIRouter(prefix="/api/v2/notifications", tags=["notifications"])

STATUSES = ("sent", "delivered", "read", "responded", "failed")
TYPES = ("expiry_reminder", "lazy_tracking", "maintenance_reminder",
         "system")
OPEN_STATUSES = ("sent", "delivered", "read")
RESPONSES = ("used_up", "extended")

_NOTIFICATION_COLS = (
    "id, user_id, household_id, type, ref_type, ref_id, channel,"
    " payload_json, status, response, sent_at, responded_at, created_at"
)


def _notification_row(row) -> dict:
    return {
        "id": str(row[0]), "user_id": str(row[1]),
        "household_id": str(row[2]), "type": row[3],
        "ref_type": row[4],
        "ref_id": str(row[5]) if row[5] else None,
        "channel": row[6], "payload_json": row[7],
        "status": row[8], "response": row[9],
        "sent_at": row[10].isoformat() if row[10] else None,
        "responded_at": row[11].isoformat() if row[11] else None,
        "created_at": row[12].isoformat() if row[12] else None,
    }


class NotificationRespond(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: str
    days: int | None = None


@router.get("")
def list_notifications(household_id: uuid.UUID = Query(...),
                       user_id: uuid.UUID | None = Query(None),
                       status: str | None = Query(None),
                       type: str | None = Query(None),
                       limit: int = Query(20, ge=1, le=100),
                       offset: int = Query(0, ge=0),
                       ident: Identity = Depends(require_auth)):
    require_household_member_403(household_id, ident)
    if status is not None and status not in STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status must be one of sent, delivered, read,"
                   " responded, failed")
    if type is not None and type not in TYPES:
        raise HTTPException(
            status_code=400,
            detail="type must be one of expiry_reminder, lazy_tracking,"
                   " maintenance_reminder, system")
    engine = get_engine()
    with engine.connect() as conn:
        query = (f"SELECT {_NOTIFICATION_COLS} FROM notifications"
                 " WHERE household_id=:h")
        params: dict = {"h": household_id, "lim": limit, "off": offset}
        if user_id is not None:
            query += " AND user_id=:uid"
            params["uid"] = user_id
        if status is not None:
            query += " AND status=:status"
            params["status"] = status
        if type is not None:
            query += " AND type=:type"
            params["type"] = type
        query += (" ORDER BY sent_at DESC, created_at DESC"
                  " LIMIT :lim OFFSET :off")
        rows = conn.execute(text(query), params).all()
    return [_notification_row(r) for r in rows]


@router.post("/{notification_id}/respond")
def respond_notification(notification_id: uuid.UUID,
                         body: NotificationRespond,
                         ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(f"SELECT {_NOTIFICATION_COLS} FROM notifications"
                 " WHERE id=:nid"),
            {"nid": notification_id},
        ).first()
        if not row:
            raise HTTPException(status_code=404,
                                detail="Notification not found")
        require_household_member_403(uuid.UUID(str(row[2])), ident)
        if body.response not in RESPONSES:
            raise HTTPException(
                status_code=400,
                detail="response must be 'used_up' or 'extended'")
        days = body.days if body.days is not None else 3
        if body.response == "extended" and (days < 1 or days > 30):
            # §6.2: extended days max 30.
            raise HTTPException(
                status_code=400,
                detail="days must be between 1 and 30")
        if row[3] != "lazy_tracking" or row[8] not in OPEN_STATUSES:
            raise HTTPException(
                status_code=409,
                detail="Only an open lazy_tracking notification can be"
                       " responded to")
        item_row = None
        if row[4] == "inventory_item" and row[5] is not None:
            item_row = conn.execute(
                text("SELECT id, household_id, auto_expiry_date, status"
                     " FROM inventory_items WHERE id=:iid"),
                {"iid": row[5]},
            ).first()
            if item_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Linked inventory item not found")
            if item_row[3] == "consumed":
                raise HTTPException(
                    status_code=409,
                    detail="Linked inventory item is already consumed")
        # One DB transaction (§6.2): notification + item together.
        conn.execute(
            text("UPDATE notifications SET status='responded',"
                 " response=:resp, responded_at=now() WHERE id=:nid"),
            {"resp": body.response, "nid": notification_id},
        )
        if item_row is not None:
            if body.response == "used_up":
                conn.execute(
                    text("UPDATE inventory_items SET status='consumed',"
                         " consumed_at=now(), updated_at=now()"
                         " WHERE id=:iid"),
                    {"iid": item_row[0]},
                )
            else:
                today = _household_today(conn, uuid.UUID(str(row[2])))
                # A null expiry has nothing to add to: extend from today.
                base = item_row[2] if item_row[2] else today
                conn.execute(
                    text("UPDATE inventory_items"
                         " SET auto_expiry_date=:exp, updated_at=now()"
                         " WHERE id=:iid"),
                    {"exp": base + timedelta(days=days),
                     "iid": item_row[0]},
                )
        updated = conn.execute(
            text(f"SELECT {_NOTIFICATION_COLS} FROM notifications"
                 " WHERE id=:nid"),
            {"nid": notification_id},
        ).first()
    return _notification_row(updated)
