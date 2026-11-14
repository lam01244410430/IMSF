"""P06 Step 4 PROPOSAL: currency summary from exact, read-only aggregates."""

import base64
import json

from sqlalchemy import text

from app.finance.authorization import READ
from app.finance.domain import FinanceRequestError
from app.finance.dto import CurrencySummaryPage

CURRENCIES = ("VND", "JPY", "USD", "EUR", "BHD")
KINDS = ("received", "remaining", "consumed", "disposed", "returned", "adjusted_out")


class FinanceReportService:
    def __init__(self, session, repository, access, inventory_repository):
        self.session, self.repository, self.access = session, repository, access
        self.inventory_repository = inventory_repository

    async def currency_summary(self, actor, hid, *, currency=None, limit=50, cursor=None):
        filters = {"currency": currency}
        async with self.session.begin():
            await self.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            await self.access.resolve(actor, hid, READ, write=False)
            scope = [hid, "finance/currency-summary", filters]
            position = ""
            if cursor is not None:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                    position = decoded["position"]
                    if decoded["scope"] != scope or position not in CURRENCIES:
                        raise ValueError()
                except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
                    raise FinanceRequestError(422, "FINANCE_INVALID_CURSOR") from None
            finance = await self.repository.currency_aggregates(hid, filters)
            # Reuse inventory valuation SQL in this same read transaction; never
            # call InventoryReportService (which would start another transaction).
            inventory = await self.inventory_repository.valuation_aggregates(hid, dict(
                product_id=None, lot_id=None, archived=None, currency=None, summary_currency=currency))
            sections = {s["currency"]: s for s in finance}
            lot_totals = {s["currency"]: s for s in inventory["totals_by_currency"]}
            for code in inventory["currencies"]:
                sections.setdefault(code, {"currency": code, "purchase": {
                    "linked_total": "0", "linked_item_count": 0,
                    "unlinked_total": "0", "unlinked_item_count": 0}, "ledger_balances": []})
            for code, section in sections.items():
                section["lots"] = {k + "_value": lot_totals.get(code, {}).get(k + "_value") for k in KINDS}
                section["ledger_balances"] = section["ledger_balances"] or []
            unknown = inventory["unknown_cost"]
            lot_reconciliation = inventory["reconciliation"]
            reconciliation = {
                "currencies": len(sections),
                "purchase_linked_item_count": sum(s["purchase"]["linked_item_count"] for s in finance),
                "purchase_unlinked_item_count": sum(s["purchase"]["unlinked_item_count"] for s in finance),
                "purchase_mismatch_count": lot_reconciliation["purchase_mismatch_count"],
                "reversed_original_count": lot_reconciliation["reversed_original_count"],
                "unknown_cost_count": unknown["count"],
                "tie_out_mismatch_count": lot_reconciliation["tie_out_mismatch_count"],
                "issues": inventory["issues"],
            }
            # At most five observed currency sections, never a scan over input rows.
            page = [sections[c] for c in sorted(sections) if c > position][:limit + 1]
            next_cursor = None
            if len(page) > limit:
                page = page[:limit]
                next_cursor = base64.urlsafe_b64encode(json.dumps({"scope": scope, "position": page[-1]["currency"]},
                    sort_keys=True, separators=(",", ":")).encode()).decode()
            return CurrencySummaryPage.model_validate({
                "sections": page, "next_cursor": next_cursor,
                "unknown_cost": {"count": unknown["count"], "lot_ids": [r["lot_id"] for r in unknown["items"]]},
                "reconciliation": reconciliation,
            }).model_dump(mode="json")
