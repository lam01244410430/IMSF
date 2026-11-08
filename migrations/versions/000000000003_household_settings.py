"""Minimal household settings; currency and defaults remain open plan items."""
from alembic import op

revision = "000000000003"
down_revision = "000000000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE household_settings (
        household_id BIGINT PRIMARY KEY REFERENCES households(id),
        "values" JSONB NOT NULL DEFAULT '{}'::jsonb
    )""")
    op.execute("INSERT INTO household_settings(household_id) SELECT id FROM households")


def downgrade() -> None:
    op.drop_table("household_settings")
