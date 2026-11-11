"""P04-OPEN-06 PROPOSAL: exact serving scaling without base-unit rounding."""
from decimal import Decimal, Inexact, DecimalException, localcontext
from app.inventory.domain import InventoryRequestError
from app.inventory.units import quantity


def scale(quantity_value, requested_servings, recipe_servings, factor):
    try:
        if factor is None or factor <= 0:
            raise ValueError('Explicit conversion required')
        with localcontext() as ctx:
            ctx.prec = 100
            ctx.traps[Inexact] = True
            numerator = quantity_value * requested_servings
            # Multiply before dividing: sub-six-decimal source-unit demand can
            # still have an exactly representable base quantity.
            base = quantity(numerator * factor / recipe_servings)
            requested = numerator / recipe_servings
            return requested, base
    except (ValueError, DecimalException):
        raise InventoryRequestError(422, 'INVENTORY_UNIT_CONVERSION_INVALID') from None
