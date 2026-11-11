"""P04-OPEN-02/08 PROPOSAL: pure allocation over authoritative locked rows."""
from datetime import date
from decimal import Decimal, localcontext
from app.inventory.domain import InventoryRequestError
from app.inventory.units import quantity


def allocate(household_id, demands, products, candidates, *, local_date):
    """Return every (lot, base quantity) allocation before any stock write.

    The caller supplies one explicit household-local date and refreshes rows
    under purchase/product/lot locks. No implicit clock or expired override.
    """
    plans = []
    with localcontext() as ctx:
        ctx.prec = 80
        for pid in sorted(demands):
            product = products[pid]
            if product['household_id'] != household_id:
                raise InventoryRequestError(404, 'INVENTORY_NOT_FOUND')
            if product['archived_at'] is not None:
                raise InventoryRequestError(409, 'INVENTORY_STATE_CONFLICT')
            remaining = quantity(demands[pid])
            eligible = sorted((lot for lot in candidates
                if lot['household_id'] == household_id and lot['product_id'] == pid
                and lot['remaining_quantity'] > 0 and lot['archived_at'] is None
                and (lot['expires_on'] is None or lot['expires_on'] >= local_date)),
                key=lambda lot: (lot['expires_on'] or date.max, lot['expires_on'] is None,
                                 lot['received_at'], lot['id']))
            for lot in eligible:
                amount = min(remaining, lot['remaining_quantity'])
                plans.append((lot, amount))
                remaining -= amount
                if remaining == 0:
                    break
            if remaining:
                raise InventoryRequestError(409, 'INVENTORY_STOCK_SHORTAGE')
    return plans
