"""Spending-ledger helper (Phase 2 design §3.1, §1.3).

One expense in the family ledger comes from exactly one receipt:
a receipt that reaches ``completed`` creates exactly ONE transaction
with ``receipt_id`` = the receipt id, ``amount`` =
``receipts.total_amount``, ``currency`` = ``receipts.currency``,
``category`` = 'food', ``type`` = 'expense' and ``occurred_at`` =
``receipts.purchased_at``. The partial unique index
``ux_transactions_receipt`` enforces the "exactly one" part in the DB;
this helper is the single place that writes such a row, so the worker
and the confirm endpoint cannot drift apart.

Callers must call it inside the SAME database transaction that creates
the inventory items and marks the receipt completed, so a receipt can
never complete without its ledger row.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text


def insert_receipt_transaction(conn, household_id: UUID | str,
                               receipt_id: UUID | str,
                               total_amount: Decimal, currency: str,
                               purchased_at: datetime | None) -> UUID:
    """Insert the one ledger row for a completed receipt.

    ``purchased_at`` may be None (Qwen did not read a date); the row
    still needs a non-null ``occurred_at`` (NOT NULL in migration
    0003), so it falls back to now. Returns the new transaction id.
    """
    occurred = purchased_at if purchased_at is not None \
        else datetime.now(timezone.utc)
    return conn.execute(
        text("INSERT INTO transactions (household_id, receipt_id, type,"
             " amount, currency, category, occurred_at)"
             " VALUES (:h, :rid, 'expense', :amount, :cur, 'food',"
             " :occurred) RETURNING id"),
        {"h": household_id, "rid": receipt_id, "amount": total_amount,
         "cur": currency, "occurred": occurred},
    ).scalar_one()
