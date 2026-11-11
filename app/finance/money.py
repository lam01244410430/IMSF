"""PROPOSAL OPEN-01/02: Decimal ↔ NUMERIC(20,6); never round user input.

There are no approved conversion boundaries in Step 2, so no rounding path.
Currency denomination/version policy remains open; scale is supplied by catalog.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
LIMIT = Decimal("100000000000000")


def exact_decimal(value: str | Decimal, scale: int = 6) -> Decimal:
    if type(scale) is not int or not 0 <= scale <= 6:
        raise ValueError("Unsupported decimal scale")
    if isinstance(value, str):
        if len(value) > 128 or not _DECIMAL.fullmatch(value):
            raise ValueError("Expected a finite decimal string")
        try:
            amount = Decimal(value)
        except InvalidOperation:
            raise ValueError("Expected a finite decimal string") from None
    elif isinstance(value, Decimal):
        amount = value
    else:
        raise ValueError("Expected a decimal string or Decimal; never float")
    if not amount.is_finite() or abs(amount) >= LIMIT:
        raise ValueError("Amount outside NUMERIC(20,6)")
    # Ignore insignificant trailing zeros without quantize/normalize/context rounding.
    digits = amount.as_tuple().digits
    exponent = amount.as_tuple().exponent
    trailing = 0
    for digit in reversed(digits):
        if digit != 0:
            break
        trailing += 1
    if amount != 0 and exponent + trailing < -scale:
        raise ValueError("Excess currency precision")
    return amount


def canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency_code: str

    @classmethod
    def parse(cls, value: str | Decimal, currency_code: str, minor_units: int) -> "Money":
        if not re.fullmatch(r"[A-Z]{3}", currency_code):
            raise ValueError("Invalid currency code")
        return cls(exact_decimal(value, minor_units), currency_code)

    def serialize(self) -> str:
        return format(self.amount, "f")
