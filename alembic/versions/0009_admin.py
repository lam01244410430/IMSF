"""0009_admin - admin dashboard auth + audit + job history (Phase C).

Adds the auth/audit/job-run schema the admin dashboard (plan §4,
contract §1.1) needs:

- ``users.disabled_at`` (NULL = enabled) and ``users.auth_version``
  (per-user token version; old tokens die when it is bumped).
- ``admin_audit_events``: one row per admin mutation and per sensitive
  read (household-records inspection), written in the same transaction
  as the mutation. Denied attempts go to the structured server log
  only, never here.
- ``job_runs``: durable history of the daily cron (``app/jobs/daily.py``
  writes one row per run).

Follows the 0007 conventions (docstring, ``revision`` /
``down_revision``, ``_pk()`` / ``_timestamps()`` helpers).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _pk():
    return sa.Column("id", PG_UUID(), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _timestamps():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      nullable=False, server_default=sa.text("now()"))]


def upgrade() -> None:
    op.add_column("users",
                  sa.Column("disabled_at", sa.TIMESTAMP(timezone=True),
                            nullable=True))
    op.add_column("users",
                  sa.Column("auth_version", sa.Integer(), nullable=False,
                            server_default=sa.text("1")))

    op.create_table(
        "admin_audit_events",
        _pk(),
        sa.Column("actor_user_id", PG_UUID(),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        *_timestamps(),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False,
                  server_default=sa.text("'success'")),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("environment", sa.String(20), nullable=True),
        sa.CheckConstraint("outcome IN ('success', 'failure')",
                           name="ck_admin_audit_events_outcome"),
    )
    op.create_index("ix_admin_audit_events_actor_created",
                    "admin_audit_events", ["actor_user_id", "created_at"])
    op.create_index("ix_admin_audit_events_action_created",
                    "admin_audit_events", ["action", "created_at"])

    op.create_table(
        "job_runs",
        _pk(),
        sa.Column("job_name", sa.String(50), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True),
                  nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'running'")),
        sa.Column("notifications_created", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('running', 'success', 'failed')",
                           name="ck_job_runs_status"),
    )
    op.create_index("ix_job_runs_job_started",
                    "job_runs", ["job_name", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_job_runs_job_started", table_name="job_runs")
    op.drop_table("job_runs")
    op.drop_index("ix_admin_audit_events_action_created",
                  table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_actor_created",
                  table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
    op.drop_column("users", "auth_version")
    op.drop_column("users", "disabled_at")
