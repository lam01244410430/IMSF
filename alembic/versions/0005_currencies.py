"""0005_currencies — expand the currency CHECKs to the 14 supported
currencies (D-F7, Lam 2026-11-21).

CNY, VND + USD, EUR, HKD + all ASEAN currencies (THB, MYR, SGD, IDR,
PHP, KHR, LAK, MMK, BND). Updates the CHECK on every table that had a
CNY/VND-only currency CHECK: households (default_currency), receipts,
receipt_lines, inventory_items, transactions, equipment_maintenance_logs.
Downgrade restores the CNY/VND-only CHECKs.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-21
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_NEW = ("CNY", "VND", "USD", "EUR", "HKD", "THB", "MYR", "SGD",
        "IDR", "PHP", "KHR", "LAK", "MMK", "BND")
_OLD = ("CNY", "VND")

# (table, constraint name, column)
_CHECKS = [
    ("households", "ck_households_currency", "default_currency"),
    ("receipts", "ck_receipts_currency", "currency"),
    ("receipt_lines", "ck_receipt_lines_currency", "currency"),
    ("inventory_items", "ck_inventory_items_currency", "currency"),
    ("transactions", "ck_transactions_currency", "currency"),
    ("equipment_maintenance_logs", "ck_maintenance_logs_currency",
     "currency"),
]


def _in_list(column, codes):
    return f"{column} IN ({', '.join(repr(c) for c in codes)})"


def upgrade() -> None:
    for table, name, column in _CHECKS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _in_list(column, _NEW))


def downgrade() -> None:
    for table, name, column in _CHECKS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _in_list(column, _OLD))
