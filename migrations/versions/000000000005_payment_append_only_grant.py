"""Frozen privilege correction for Step 2 P3-4; no schema or data changes."""
import os

from alembic import op

revision = "000000000005"
down_revision = "000000000004"
branch_labels = None
depends_on = None


def _runtime_role():
    role = os.environ.get("FINANCE_RUNTIME_ROLE")
    return op.get_bind().dialect.identifier_preparer.quote(role) if role else None


def upgrade() -> None:
    role = _runtime_role()
    if role:
        op.execute(f"REVOKE UPDATE ON TABLE transaction_payments FROM {role}")


def downgrade() -> None:
    # Restore revision 4's exact privilege contract for disposable rehearsals.
    role = _runtime_role()
    if role:
        op.execute(f"GRANT UPDATE ON TABLE transaction_payments TO {role}")
