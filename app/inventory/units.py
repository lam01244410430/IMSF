"""P04-OPEN-01 proposal: explicit factors, exact six-decimal base quantities."""

from decimal import Decimal, localcontext
import re


def decimal_value(value, *, precision=20, scale=6):
    if isinstance(value, str):
        if len(value) > 128 or not re.fullmatch(
            r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", value
        ):
            raise ValueError("Finite decimal string required")
        value = Decimal(value)
    elif not isinstance(value, Decimal):
        raise ValueError("Decimal strings required; never float")
    if not value.is_finite() or value.copy_abs() >= Decimal(10) ** (precision - scale):
        raise ValueError("Decimal outside storage bounds")
    digits = value.as_tuple().digits
    trailing = 0
    for digit in reversed(digits):
        if digit:
            break
        trailing += 1
    if value and value.as_tuple().exponent + trailing < -scale:
        raise ValueError("Inexact decimal precision")
    return value


def quantity(value):
    result = decimal_value(value)
    if result <= 0:
        raise ValueError("Positive quantity required")
    return result


def cost(value):
    result = decimal_value(value, precision=30, scale=12)
    if result < 0:
        raise ValueError("Nonnegative cost required")
    return result


def convert(value, from_unit_id, to_unit_id, factor):
    value = quantity(value)
    if from_unit_id == to_unit_id:
        return value
    if factor is None:
        raise ValueError("Explicit same-dimension conversion required")
    factor = decimal_value(factor, precision=30, scale=12)
    if factor <= 0:
        raise ValueError("Positive factor required")
    with localcontext() as ctx:
        ctx.prec = 80
        return quantity(value * factor)
