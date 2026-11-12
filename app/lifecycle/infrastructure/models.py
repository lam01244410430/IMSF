"""P05-OPEN-02/04/05/08 PROPOSAL persistence; frozen migration is independent."""
from datetime import date, datetime
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.finance.infrastructure.models import Scoped, scoped_unique
from app.inventory.infrastructure.models import InventoryLot


class ScheduledJob(Scoped, Base):
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        scoped_unique(), sa.UniqueConstraint("household_id", "job_key"),
        sa.CheckConstraint("length(btrim(job_key))>=1 AND length(job_key)<=200", name="ck_expiry_job_key"),
        sa.CheckConstraint("kind='INVENTORY_EXPIRY'", name="ck_expiry_job_kind"),
        sa.CheckConstraint("state IN ('READY','RUNNING','SUCCEEDED','FAILED')", name="ck_expiry_job_state"),
        sa.CheckConstraint("attempt_count>=0", name="ck_expiry_job_attempts"),
        sa.CheckConstraint("(state='RUNNING' AND lease_until IS NOT NULL AND lease_token IS NOT NULL AND length(lease_token) BETWEEN 1 AND 200) OR (state<>'RUNNING' AND lease_until IS NULL AND lease_token IS NULL)", name="ck_expiry_job_lease"),
        sa.CheckConstraint("(state IN ('SUCCEEDED','FAILED'))=(completed_at IS NOT NULL)", name="ck_expiry_job_completion"),
        sa.CheckConstraint("error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'", name="ck_expiry_job_error"),
        sa.CheckConstraint("public.inventory_expiry_payload_valid(payload)", name="ck_expiry_job_payload"),
        sa.CheckConstraint("public.inventory_expiry_progress_valid(checkpoint,false)", name="ck_expiry_job_checkpoint"),
        sa.CheckConstraint("public.inventory_expiry_progress_valid(result,true)", name="ck_expiry_job_result"),
        sa.Index("ix_expiry_jobs_due", "state", "run_after", "id", postgresql_where=sa.text("state='READY'")),
        sa.Index("ix_expiry_jobs_reclaim", "state", "lease_until", "id", postgresql_where=sa.text("state='RUNNING'")),
    )
    job_key: Mapped[str] = mapped_column(sa.Text)
    kind: Mapped[str] = mapped_column(sa.Text)
    state: Mapped[str] = mapped_column(sa.Text, server_default="READY")
    run_after: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(sa.Integer, server_default="0")
    lease_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(sa.Text)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp())
    payload: Mapped[dict] = mapped_column(JSONB)
    checkpoint: Mapped[dict] = mapped_column(JSONB, server_default=sa.text("'{\"schema_version\": 1}'::jsonb"))
    result: Mapped[dict] = mapped_column(JSONB, server_default=sa.text("'{\"schema_version\": 1}'::jsonb"))


class ExpirationAlert(Scoped, Base):
    __tablename__ = "expiration_alerts"
    __table_args__ = (
        scoped_unique(), sa.UniqueConstraint("household_id", "lot_id", "alert_kind", "local_date"),
        sa.ForeignKeyConstraint(["household_id", "lot_id"], ["inventory_lots.household_id", "inventory_lots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["household_id", "job_id"], ["scheduled_jobs.household_id", "scheduled_jobs.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("alert_kind IN ('WARNING','EXPIRED')", name="ck_expiry_alert_kind"),
        sa.CheckConstraint("public.inventory_expiry_timezone_valid(timezone)", name="ck_expiry_alert_timezone"),
        sa.Index("ix_expiry_alert_date", "household_id", "local_date", "id"),
        sa.Index("ix_expiry_alert_job", "household_id", "job_id"),
    )
    lot_id: Mapped[int] = mapped_column(sa.BigInteger)
    alert_kind: Mapped[str] = mapped_column(sa.Text)
    local_date: Mapped[date] = mapped_column(sa.Date)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp())
    expires_on_snapshot: Mapped[date] = mapped_column(sa.Date)
    timezone: Mapped[str] = mapped_column(sa.Text)
    job_id: Mapped[int] = mapped_column(sa.BigInteger)


# Revision 7's product-prefixed FEFO index does not cover household expiry scans.
# Register the additive index without changing the delivered inventory model.
sa.Index("ix_lot_expiry_scan", InventoryLot.household_id, InventoryLot.expires_on,
         InventoryLot.id, postgresql_where=sa.text("remaining_quantity>0 AND expires_on IS NOT NULL"))
