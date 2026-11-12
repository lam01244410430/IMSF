"""P05-OPEN-07 PROPOSAL: sanitized bounded read contracts, no worker secrets."""
from datetime import date, datetime
from typing import Literal
from app.finance.dto import ReadDTO, SerializedDecimal

Freshness = Literal["FRESH", "WARNING", "EXPIRED", "UNKNOWN"]
AlertKind = Literal["WARNING", "EXPIRED"]


class LifecycleResponse(ReadDTO):
    lot_id: int
    household_id: int
    product_id: int
    received_at: datetime
    received_quantity: SerializedDecimal
    remaining_quantity: SerializedDecimal
    expires_on: date | None
    lot_archived_at: datetime | None
    product_archived_at: datetime | None
    household_archived_at: datetime | None
    activity_state: Literal["ACTIVE", "TERMINAL"]
    terminal_state: str | None
    freshness: Freshness
    days_left: int | None
    local_date: date
    timezone: str


class LifecyclePage(ReadDTO):
    items: list[LifecycleResponse]
    next_cursor: str | None
    local_date: date
    timezone: str


class ExpirationAlertResponse(ReadDTO):
    id: int
    household_id: int
    lot_id: int
    alert_kind: AlertKind
    local_date: date
    created_at: datetime
    expires_on_snapshot: date
    timezone: str
    job_id: int


class ExpirationAlertPage(ReadDTO):
    items: list[ExpirationAlertResponse]
    next_cursor: str | None
