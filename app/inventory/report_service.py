"""P06 Step 2 PROPOSALS: exact lot valuation, no stored report or writer."""

import base64
import json
from decimal import Decimal, localcontext

from sqlalchemy import text

from app.inventory.authorization import READ
from app.inventory.domain import InventoryRequestError
from app.inventory.dto import LotValuationPage, LotValuationResponse

KINDS = ("received", "remaining", "consumed", "disposed", "returned", "adjusted_out")
IDENTIFIER_LIMIT = 100


def lot_valuation(row):
    """Derive one lot from fixed cost and signed, correction-attributed deltas."""
    quantities = {
        "received": row["received_quantity"], "remaining": row["remaining_quantity"],
        "consumed": abs(row["consumed_delta"]), "disposed": abs(row["disposed_delta"]),
        "returned": abs(row["returned_delta"]), "adjusted_out": -row["adjusted_delta"],
    }
    unknown = row["unit_cost"] is None
    values = {k: None if unknown else q * row["unit_cost"] for k, q in quantities.items()}
    quantity_tied = quantities["received"] == sum((quantities[k] for k in KINDS[1:]), Decimal(0))
    value_tied = None if unknown else values["received"] == sum((values[k] for k in KINDS[1:]), Decimal(0))
    issues = []
    status = "UNKNOWN_COST" if unknown else "TIED_OUT"
    purchase = None
    if row["purchase_item_id"] is not None:
        matches = values["received"] == row["purchase_net_amount"] and row["cost_currency"] == row["purchase_currency"]
        purchase_status = "UNKNOWN_COST" if unknown else "AGREEMENT" if matches else "PURCHASE_MISMATCH"
        purchase = {"item_id": row["purchase_item_id"], "transaction_id": row["purchase_transaction_id"],
                    "currency": row["purchase_currency"], "net_amount": row["purchase_net_amount"],
                    "reversed_original": row["reversed_original"], "status": purchase_status}
        if purchase_status == "PURCHASE_MISMATCH":
            issues.append("PURCHASE_MISMATCH")
            status = "PURCHASE_MISMATCH"
        if row["reversed_original"]:
            issues.append("REVERSED_ORIGINAL")
    if not quantity_tied or value_tied is False:
        issues.insert(0, "TIE_OUT_MISMATCH")
        status = "TIE_OUT_MISMATCH"
    return {
        "lot_id": row["id"], **{k: row[k] for k in (
            "product_id", "base_unit_id", "source_kind", "received_at", "expires_on",
            "cost_currency", "unit_cost", "terminal_state", "archived_at", "product_archived_at")},
        **{k + "_quantity": q for k, q in quantities.items()},
        **{k + "_value": v for k, v in values.items()},
        "unknown_cost": unknown, "quantity_tied_out": quantity_tied, "value_tied_out": value_tied,
        "reconciliation_status": status, "purchase": purchase, "issues": issues,
    }


class InventoryReportService:
    def __init__(self, session, repository, access):
        self.session, self.repository, self.access = session, repository, access

    async def valuation(self, actor, hid, *, product_id=None, lot_id=None, currency=None,
                        archived=None, limit=50, cursor=None, single=False):
        filters = dict(product_id=product_id, lot_id=lot_id, currency=currency, archived=archived)
        async with self.session.begin():
            # One stable read snapshot, including permission and ownership reads.
            # READ COMMITTED alone would allow different statements to see later
            # stock commits. No SELECT FOR UPDATE or data writes are needed.
            await self.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            await self.access.resolve(actor, hid, READ, write=False)
            for resource in ("product_id", "lot_id"):
                if filters[resource] is not None and not await self.repository.contains(hid, resource, filters[resource]):
                    raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
            scope = [hid, "inventory/valuation", filters]
            position = 0
            if cursor is not None:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                    position = decoded["position"]
                    if decoded["scope"] != scope or type(position) is not int or not 0 < position <= 9223372036854775807:
                        raise ValueError()
                except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
                    raise InventoryRequestError(422, "INVENTORY_INVALID_INPUT") from None
            # NUMERIC(20,6) * NUMERIC(30,12) needs up to 50 digits;
            # 80 also covers totals over a BIGINT-sized set of lots. Never
            # quantize, normalize, use float, or inherit Decimal's default 28.
            with localcontext() as ctx:
                ctx.prec = 80
                rows = [lot_valuation(r) for r in await self.repository.valuation_rows(hid, filters)]
                if single:
                    return LotValuationResponse.model_validate(rows[0]).model_dump(mode="json")
                totals, unknown, issues = {}, [], []
                reconciliation = dict(checked_lots=len(rows), quantity_tied_out_count=0,
                    value_tied_out_count=0, unknown_cost_count=0, purchase_agreement_count=0,
                    purchase_mismatch_count=0, purchase_unknown_cost_count=0)
                for row in rows:
                    reconciliation["quantity_tied_out_count"] += row["quantity_tied_out"]
                    reconciliation["value_tied_out_count"] += row["value_tied_out"] is True
                    if row["unknown_cost"]:
                        unknown.append({k: row[k] for k in ("lot_id", "product_id", "base_unit_id", *(k + "_quantity" for k in KINDS))})
                    else:
                        total = totals.setdefault(row["cost_currency"], {k + "_value": Decimal(0) for k in KINDS})
                        for key in total:
                            total[key] += row[key]
                    if row["purchase"] is not None:
                        counter = {"AGREEMENT": "purchase_agreement_count", "PURCHASE_MISMATCH": "purchase_mismatch_count", "UNKNOWN_COST": "purchase_unknown_cost_count"}[row["purchase"]["status"]]
                        reconciliation[counter] += 1
                    issues.extend({"lot_id": row["lot_id"], "code": code} for code in row["issues"])
                reconciliation["unknown_cost_count"] = len(unknown)
                reconciliation["issues"] = {"count": len(issues), "items": issues[:IDENTIFIER_LIMIT]}
                page = [r for r in rows if r["lot_id"] > position][:limit + 1]
                next_cursor = None
                if len(page) > limit:
                    page = page[:limit]
                    next_cursor = base64.urlsafe_b64encode(json.dumps({"scope": scope, "position": page[-1]["lot_id"]}, sort_keys=True, separators=(",", ":")).encode()).decode()
                return LotValuationPage.model_validate({
                    "items": page, "next_cursor": next_cursor,
                    "totals_by_currency": (
                        None if rows and not totals else
                        [{"currency": c, **totals[c]} for c in sorted(totals)]
                    ),
                    "unknown_cost": {"count": len(unknown), "items": unknown[:IDENTIFIER_LIMIT]},
                    "reconciliation": reconciliation,
                }).model_dump(mode="json")
