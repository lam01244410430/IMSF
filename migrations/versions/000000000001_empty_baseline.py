"""Empty baseline (P02-01): creates only alembic_version, no tables."""

revision = "000000000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass