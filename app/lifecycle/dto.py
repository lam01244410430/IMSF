"""P05-OPEN-07 PROPOSAL: sanitized bounded read contracts, no worker secrets."""
from datetime import date, datetime
from typing import Literal
from pydantic import Field
from app.finance.dto import ReadDTO, SerializedDecimal

Freshness = Literal["FRESH", "WARNING", "EXPIRED", "UNKNOWN"]
AlertKind = Literal["WARNING", "EXPIRED"]


# OPEN-03/07 PROPOSAL: newest five by alert ID per lot; retained provenance.
STANDING_ALERT_LIMIT = 5


class StandingAlertSummary(ReadDTO):
    id: int
    alert_kind: AlertKind
    local_date: date
    job_id: int
    created_at: datetime


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
    standing_alerts: list[StandingAlertSummary] = Field(max_length=STANDING_ALERT_LIMIT)
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


class ExpiryRunResponse(ReadDTO):
    """PROPOSAL OPEN-07: explicit allow-list; no generic payload or lease data."""
    id: int
    kind: Literal["INVENTORY_EXPIRY"]
    local_date: date
    timezone: str
    state: Literal["READY", "RUNNING", "SUCCEEDED", "FAILED"]
    attempt_count: int = Field(ge=0, le=2147483647)
    run_after: datetime
    completed_at: datetime | None
    scanned_count: int = Field(ge=0, le=9223372036854775807)
    warning_count: int = Field(ge=0, le=9223372036854775807)
    expired_count: int = Field(ge=0, le=9223372036854775807)
    error_code: str | None = Field(max_length=64)
    outcome_code: str | None = Field(max_length=64)
