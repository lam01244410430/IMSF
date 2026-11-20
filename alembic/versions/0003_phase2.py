"""0003_phase2 — create the 7 Phase 2 tables + pgvector (design §3).

Order follows FK dependency:
transactions → shopping_lists → shopping_list_items → notifications →
equipment_maintenance_logs → master_ingredient_aliases →
knowledge_documents (+ §3.8 ALTERs on equipments / master_ingredients).

§3.8 as corrected (verified in 0001): inventory_items.consumed_at +
status CHECK including 'consumed' and equipments.status already exist
in 0001, so this migration SKIPS those ALTERs. The only §3.8 ALTERs are
equipments.usage_per_week / maintenance_interval_days and
master_ingredients.embedding.

NOTE on the vector type: the pgvector Python package is NOT in
requirements.txt (and CI installs only requirements.txt), so this file
must not import it. _Vector below is a minimal UserDefinedType that
renders DDL as vector(N); this migration only needs the DDL, it never
binds vector values.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


class _Vector(sa.types.UserDefinedType):
    """Render as pgvector vector(N) without the pgvector package."""

    cache_ok = True

    def __init__(self, dim):
        self.dim = dim

    def get_col_spec(self, **kw):
        return "vector(%d)" % self.dim


def _pk():
    return sa.Column("id", PG_UUID(), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _timestamps(with_updated=True):
    cols = [sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      nullable=False, server_default=sa.text("now()"))]
    if with_updated:
        cols.append(sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                              nullable=False, server_default=sa.text("now()")))
    return cols


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 3.1 transactions
    op.create_table(
        "transactions",
        _pk(),
        sa.Column("household_id", PG_UUID(), sa.ForeignKey(
            "households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receipt_id", PG_UUID(), sa.ForeignKey(
            "receipts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", sa.VARCHAR(10), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("category", sa.VARCHAR(50), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True),
                  nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("type IN ('expense', 'income')",
                           name="ck_transactions_type"),
        sa.CheckConstraint("amount > 0",
                           name="ck_transactions_amount"),
        sa.CheckConstraint("currency IN ('CNY', 'VND')",
                           name="ck_transactions_currency"),
        sa.CheckConstraint(
            "category IN ('food', 'household', 'maintenance', 'other')",
            name="ck_transactions_category"),
    )
    # Anti-double-count rule (§1.3): exactly 1 transaction per receipt.
    op.create_index(
        "ux_transactions_receipt", "transactions", ["receipt_id"],
        unique=True, postgresql_where=sa.text("receipt_id IS NOT NULL"))
    op.create_index("ix_transactions_household_currency_occurred",
                    "transactions",
                    ["household_id", "currency", "occurred_at"])

    # 3.2 shopping_lists
    op.create_table(
        "shopping_lists",
        _pk(),
        sa.Column("household_id", PG_UUID(), sa.ForeignKey(
            "households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_recipe_id", PG_UUID(), sa.ForeignKey(
            "community_recipes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.VARCHAR(20), nullable=False,
                  server_default=sa.text("'open'")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True),
                  nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status IN ('open', 'done')",
                           name="ck_shopping_lists_status"),
    )
    # One open list per household.
    op.create_index(
        "ux_shopping_lists_open", "shopping_lists", ["household_id"],
        unique=True, postgresql_where=sa.text("status = 'open'"))

    # 3.3 shopping_list_items
    op.create_table(
        "shopping_list_items",
        _pk(),
        sa.Column("shopping_list_id", PG_UUID(), sa.ForeignKey(
            "shopping_lists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("master_ingredient_id", PG_UUID(), sa.ForeignKey(
            "master_ingredients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit", sa.VARCHAR(20), nullable=True),
        sa.Column("checked", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        *_timestamps(),
    )
    op.create_index("ix_shopping_list_items_list_checked",
                    "shopping_list_items", ["shopping_list_id", "checked"])

    # 3.4 notifications
    # user_id uses CASCADE, the same ON DELETE convention 0001 uses for
    # user references (household_members.user_id).
    op.create_table(
        "notifications",
        _pk(),
        sa.Column("user_id", PG_UUID(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("household_id", PG_UUID(), sa.ForeignKey(
            "households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.VARCHAR(30), nullable=False),
        sa.Column("ref_type", sa.VARCHAR(30), nullable=True),
        sa.Column("ref_id", PG_UUID(), nullable=True),
        sa.Column("channel", sa.VARCHAR(20), nullable=False,
                  server_default=sa.text("'in_app'")),
        sa.Column("payload_json", JSONB(), nullable=True),
        sa.Column("status", sa.VARCHAR(20), nullable=False,
                  server_default=sa.text("'sent'")),
        sa.Column("response", sa.VARCHAR(50), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("responded_at", sa.TIMESTAMP(timezone=True),
                  nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "type IN ('expiry_reminder', 'lazy_tracking',"
            " 'maintenance_reminder', 'system')",
            name="ck_notifications_type"),
        sa.CheckConstraint("channel IN ('in_app', 'wechat')",
                           name="ck_notifications_channel"),
        sa.CheckConstraint(
            "status IN ('sent', 'delivered', 'read', 'responded',"
            " 'failed')",
            name="ck_notifications_status"),
        sa.CheckConstraint("response IN ('used_up', 'extended')",
                           name="ck_notifications_response"),
    )
    # Anti-duplicate rules (§3.4): at most 1 open lazy_tracking /
    # maintenance_reminder notification per referenced item.
    op.create_index(
        "ux_notifications_open_lazy", "notifications",
        ["ref_type", "ref_id"],
        unique=True,
        postgresql_where=sa.text(
            "type = 'lazy_tracking' AND status IN ('sent', 'delivered',"
            " 'read')"))
    op.create_index(
        "ux_notifications_open_maint", "notifications",
        ["ref_type", "ref_id"],
        unique=True,
        postgresql_where=sa.text(
            "type = 'maintenance_reminder' AND status IN ('sent',"
            " 'delivered', 'read')"))
    op.create_index("ix_notifications_user_status_sent", "notifications",
                    ["user_id", "status", "sent_at"])

    # 3.5 equipment_maintenance_logs
    op.create_table(
        "equipment_maintenance_logs",
        _pk(),
        sa.Column("equipment_id", PG_UUID(), sa.ForeignKey(
            "equipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("performed_at", sa.TIMESTAMP(timezone=True),
                  nullable=False),
        sa.Column("maintenance_type", sa.VARCHAR(50), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.CHAR(3), nullable=True),
        sa.Column("transaction_id", PG_UUID(), sa.ForeignKey(
            "transactions.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "maintenance_type IN ('cleaning', 'filter_replace', 'repair',"
            " 'inspection')",
            name="ck_maintenance_logs_type"),
        sa.CheckConstraint("cost >= 0",
                           name="ck_maintenance_logs_cost"),
        sa.CheckConstraint("currency IN ('CNY', 'VND')",
                           name="ck_maintenance_logs_currency"),
    )
    op.create_index("ix_maintenance_logs_equipment_performed",
                    "equipment_maintenance_logs",
                    ["equipment_id", sa.text("performed_at DESC")])

    # 3.6 master_ingredient_aliases
    op.create_table(
        "master_ingredient_aliases",
        _pk(),
        sa.Column("master_ingredient_id", PG_UUID(), sa.ForeignKey(
            "master_ingredients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.VARCHAR(100), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("master_ingredient_id", "alias",
                            name="uq_aliases_ingredient_alias"),
    )
    op.create_index("ix_aliases_alias", "master_ingredient_aliases",
                    ["alias"])

    # 3.7 knowledge_documents
    op.create_table(
        "knowledge_documents",
        _pk(),
        sa.Column("topic", sa.VARCHAR(50), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", _Vector(1024), nullable=False),
        sa.Column("canonical_ingredient_id", PG_UUID(), sa.ForeignKey(
            "master_ingredients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("equipment_type", sa.VARCHAR(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("topic IN ('shelf_life', 'maintenance')",
                           name="ck_knowledge_documents_topic"),
    )
    # ivfflat is only useful once rows exist (§3.7); created here on the
    # empty table per the task, REINDEX after first ingest (§7.3).
    op.create_index("ix_knowledge_documents_embedding",
                    "knowledge_documents", ["embedding"],
                    postgresql_using="ivfflat",
                    postgresql_with={"lists": 100},
                    postgresql_ops={"embedding": "vector_cosine_ops"})

    # 3.8 ALTERs (corrected — only these three columns; the
    # inventory_items / equipments.status ALTERs from the first draft
    # are already in 0001 and are skipped).
    op.add_column("equipments",
                  sa.Column("usage_per_week", sa.Integer(),
                            nullable=True))
    op.create_check_constraint("ck_equipments_usage_per_week",
                               "equipments", "usage_per_week >= 0")
    op.add_column("equipments",
                  sa.Column("maintenance_interval_days", sa.Integer(),
                            nullable=True))
    op.create_check_constraint("ck_equipments_maintenance_interval_days",
                               "equipments",
                               "maintenance_interval_days > 0")
    op.add_column("master_ingredients",
                  sa.Column("embedding", _Vector(1024), nullable=True))


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_embedding",
                  table_name="knowledge_documents")
    for table in ("knowledge_documents", "master_ingredient_aliases",
                  "equipment_maintenance_logs", "notifications",
                  "shopping_list_items", "shopping_lists",
                  "transactions"):
        op.drop_table(table)
    op.drop_column("master_ingredients", "embedding")
    op.drop_column("equipments", "maintenance_interval_days")
    op.drop_column("equipments", "usage_per_week")
