"""P06 Step 2 PROPOSALS: exact lot valuation, no stored report or writer."""

import base64
import json
from decimal import Decimal, localcontext

from sqlalchemy import text

from app.inventory.authorization import READ
from app.inventory.domain import InventoryRequestError
from app.inventory.dto import LotValuationPage, LotValuationResponse, WasteReport
from app.lifecycle.domain import household_zone

KINDS = ("received", "remaining", "consumed", "disposed", "returned", "adjusted_out")


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
                # P06 Step 4 PROPOSAL: full-scope SQL totals, bounded page only.
                report = await self.repository.valuation_aggregates(hid, filters)
                page = [lot_valuation(r) for r in await self.repository.valuation_page_rows(
                    hid, filters, position, 1 if single else limit + 1)]
                if single:
                    return LotValuationResponse.model_validate(page[0]).model_dump(mode="json")
                reconciliation = report["reconciliation"]
                reconciliation["issues"] = report["issues"]
                next_cursor = None
                if len(page) > limit:
                    page = page[:limit]
                    next_cursor = base64.urlsafe_b64encode(json.dumps({"scope": scope, "position": page[-1]["lot_id"]}, sort_keys=True, separators=(",", ":")).encode()).decode()
                return LotValuationPage.model_validate({
                    "items": page, "next_cursor": next_cursor,
                    "totals_by_currency": (
                        None if reconciliation["checked_lots"] and not report["totals_by_currency"]
                        else report["totals_by_currency"]
                    ),
                    "unknown_cost": report["unknown_cost"],
                    "reconciliation": reconciliation,
                }).model_dump(mode="json")

    async def waste(self, actor, hid, *, from_date=None, to_date=None, product_id=None,
                    reason=None, currency=None, limit=50, cursor=None):
        filters = dict(from_date=from_date.isoformat() if from_date else None,
                       to_date=to_date.isoformat() if to_date else None,
                       product_id=product_id, reason=reason, currency=currency)
        async with self.session.begin():
            await self.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            await self.access.resolve(actor, hid, READ, write=False)
            if product_id is not None and not await self.repository.contains(hid, "product_id", product_id):
                raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
            zone = household_zone(await self.repository.household_timezone(hid))
            if from_date is not None and to_date is not None and from_date > to_date:
                raise InventoryRequestError(422, "INVENTORY_INVALID_INPUT")
            # P06 Step 4 PROPOSAL: allow a 366-day span, reject 367 and above.
            if from_date is not None and to_date is not None and (to_date - from_date).days > 366:
                raise InventoryRequestError(422, "INVENTORY_INVALID_INPUT")
            scope = [hid, "inventory/waste-report", filters]
            position = ("", 0)
            if cursor is not None:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                    pos = decoded["position"]
                    if (decoded["scope"] != scope or not isinstance(pos, list) or len(pos) != 2
                            or pos[0] not in ("VND", "JPY", "USD", "EUR", "BHD")
                            or type(pos[1]) is not int or not 0 < pos[1] <= 9223372036854775807):
                        raise ValueError()
                    position = tuple(pos)
                except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
                    raise InventoryRequestError(422, "INVENTORY_INVALID_INPUT") from None
            # Reuse valuation's exact arithmetic and single read-snapshot model.
            with localcontext() as ctx:
                ctx.prec = 80
                # P06 Step 4 PROPOSAL: no root-event or full product scan in Python.
                query_filters = {**filters, "timezone": zone.key}
                report = await self.repository.waste_aggregates(hid, query_filters)
                for section in report["sections"]:
                    denominator = Decimal(section["denominator"]["value"])
                    section["waste_rate"] = Decimal(section["disposed"]["value"]) / denominator if denominator else None
                page = await self.repository.waste_product_rows(hid, query_filters, position, limit + 1)
                next_cursor = None
                if len(page) > limit:
                    page = page[:limit]
                    next_cursor = base64.urlsafe_b64encode(json.dumps({
                        "scope": scope, "position": [page[-1]["currency"], page[-1]["product_id"]],
                    }, sort_keys=True, separators=(",", ":")).encode()).decode()
                return WasteReport.model_validate({
                    **report, "by_product": page, "next_cursor": next_cursor,
                    "period": {"from_date": from_date, "to_date": to_date, "timezone": zone.key},
                }).model_dump(mode="json")
