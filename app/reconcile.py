"""Shared Step 3 logic (design §6.2 step 5, §6.4, §3.5-3.6).

Used by BOTH the worker (``worker/main.py``) and
``POST /api/v2/receipts/{id}/confirm`` (``app/api/receipts.py``) so the
two paths can never drift apart:

- ``resolve_canonical`` — canonical mapping order (Step 3 task 1):
  (a) exact normalised match of the printed ``raw_name`` against
  ``master_ingredients.canonical_name``; (b) Qwen's suggested
  ``canonical_name`` matched against master_ingredients (normalised,
  case-insensitive); (c) otherwise ``None`` = explicitly UNMATCHED.
- ``check_reconciliation`` — the §6.4 2% rule, implemented literally:
  ``lines_total`` is SUM(price) over ALL receipt_lines (including
  ``is_stock_item = false`` lines). ``total_amount`` null or <= 0 means
  needs_review ("không đọc được tổng tiền"). Otherwise
  ``diff / total_amount > 0.02`` (strictly greater) means needs_review
  with the actual percentage in the message; exactly 2.00% passes.
- ``insert_inventory_item`` — one inventory row per stock line, with
  the §6.2 step 6 expiry rule: ``added_date + default_shelf_life_days``
  of the matched canonical ingredient, or +3 days fallback when the
  line is unmatched (recorded fallback, not a guess at the food type).

``processed_at`` marks the END of processing, not success: it is set
on completed AND on needs_review AND on failed receipts.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import text

MISSING_TOTAL_MESSAGE = "không đọc được tổng tiền"
RECONCILE_THRESHOLD = Decimal("0.02")
FALLBACK_SHELF_LIFE_DAYS = 3  # §6.2 step 6: unmatched item -> +3 days


def normalize_name(name) -> str:
    """Normalise for matching: strip all whitespace, lowercase."""
    return "".join(str(name or "").split()).lower()


def resolve_canonical(raw_name, suggested_canonical_name, master_map):
    """Resolve one parsed line to a master_ingredients entry or None.

    ``master_map``: normalised canonical_name -> {"id", "name", "zone",
    "shelf_life"} (see ``worker.main.load_master_map``). Returns the
    entry, or ``None`` when explicitly unmatched.
    """
    entry = master_map.get(normalize_name(raw_name))
    if entry is not None:
        return entry
    if suggested_canonical_name:
        entry = master_map.get(normalize_name(suggested_canonical_name))
        if entry is not None:
            return entry
    return None


def check_reconciliation(lines_total, total_amount):
    """Literal §6.4. Returns ``(ok, error_message_or_None)``.

    ``lines_total`` / ``total_amount`` may be Decimal, int, float or
    None. Decimal arithmetic is used throughout so that exactly 2.00%
    (e.g. 98.00 vs 100.00) passes — the rule is strictly greater than.
    """
    if total_amount is None:
        return False, MISSING_TOTAL_MESSAGE
    total = Decimal(str(total_amount))
    if total <= 0:
        return False, MISSING_TOTAL_MESSAGE
    lines = Decimal(str(lines_total))
    diff = abs(lines - total)
    if diff / total > RECONCILE_THRESHOLD:
        pct = diff / total * Decimal(100)
        return False, f"tổng dòng lệch {pct:.2f}% so với tổng hóa đơn"
    return True, None


def expiry_for(canon, added_date):
    """§6.2 step 6 expiry: matched shelf life, else +3 day fallback."""
    if canon is not None and canon.get("shelf_life") is not None:
        return added_date + timedelta(days=canon["shelf_life"])
    return added_date + timedelta(days=FALLBACK_SHELF_LIFE_DAYS)


def insert_inventory_item(conn, household_id, receipt_id, line_id,
                          raw_name, canon, quantity, unit, price,
                          currency, added_date):
    """Insert one inventory_items row for a stock receipt line."""
    conn.execute(
        text("INSERT INTO inventory_items (household_id, receipt_id,"
             " receipt_line_id, raw_name, canonical_ingredient_id,"
             " quantity, unit, price, currency, storage_zone,"
             " added_date, auto_expiry_date, status)"
             " VALUES (:h, :rid, :lid, :raw, :canon, :qty, :unit,"
             " :price, :cur, :zone, :added, :exp, 'fresh')"),
        {"h": household_id, "rid": receipt_id, "lid": line_id,
         "raw": raw_name, "canon": canon["id"] if canon else None,
         "qty": quantity, "unit": unit, "price": price,
         "cur": currency, "zone": canon["zone"] if canon else None,
         "added": added_date, "exp": expiry_for(canon, added_date)},
    )
