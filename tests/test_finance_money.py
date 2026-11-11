"""PROPOSAL OPEN-01/02: exact decimal values, no user rounding boundary."""
from decimal import Decimal

import pytest


def money(value, currency="USD", scale=2):
    from app.finance.money import Money
    return Money.parse(value, currency, scale)


def test_money_uses_decimal_and_serializes_strings():
    result = money("12.30")
    assert result.amount == Decimal("12.30")
    assert isinstance(result.amount, Decimal)
    assert result.serialize() == "12.30"


@pytest.mark.parametrize("value", [1.2, float("nan"), float("inf"), "NaN", "Infinity", "-Infinity",
                                       "100000000000000", "99999999999999.9999999", True, 12, "1e10000"])
def test_reject_float_nan_infinity_overflow(value):
    with pytest.raises(ValueError):
        money(value, "XTS", 6)


@pytest.mark.parametrize("currency,scale,valid,invalid", [
    ("VND", 0, "123", "1.1"), ("USD", 2, "1.23", "1.001"),
    ("BHD", 3, "1.234", "1.0001"), ("XTS", 6, "0.000001", "0.0000001"),
])
def test_currency_zero_two_three_and_six_digit_scales(currency, scale, valid, invalid):
    assert money(valid, currency, scale).amount == Decimal(valid)
    with pytest.raises(ValueError):
        money(invalid, currency, scale)


def test_exact_decimal_addition_0_1_plus_0_2():
    assert money("0.1").amount + money("0.2").amount == Decimal("0.3")


@pytest.mark.parametrize("value", ["99999999999999.999999", "-99999999999999.999999", "0.000001"])
def test_amount_storage_boundary(value):
    assert money(value, "XTS", 6).amount == Decimal(value)


@pytest.mark.parametrize("scale", [-1, 7])
def test_currency_catalog_bounds(scale):
    with pytest.raises(ValueError):
        money("1", "XTS", scale)
