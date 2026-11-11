"""P04-OPEN-01 proposals: exact directional conversion, never rounding."""

from decimal import Decimal
import pytest


def test_explicit_conversion_dimension_identity_and_precision(f):
    response = f.request("GET", "/measurement-units")
    assert response.status_code == 200
    units = {u["code"]: u for u in response.json()["items"]}
    assert {k: v["dimension"] for k, v in units.items()} == {
        "g": "MASS",
        "kg": "MASS",
        "ml": "VOLUME",
        "l": "VOLUME",
        "each": "COUNT",
    }
    factors = f.request("GET", "/unit-conversions").json()["items"]
    codes = {v["id"]: k for k, v in units.items()}
    assert {
        (codes[v["from_unit_id"]], codes[v["to_unit_id"]]): Decimal(v["factor"])
        for v in factors
    } == {
        ("kg", "g"): Decimal("1000"),
        ("g", "kg"): Decimal(".001"),
        ("l", "ml"): Decimal("1000"),
        ("ml", "l"): Decimal(".001"),
    }


@pytest.mark.parametrize(
    "value",
    [1.1, "NaN", "Infinity", "-Infinity", "100000000000000", "0.0000001", "1e-6"],
)
def test_float_nan_infinity_overflow_and_inexact_conversion_rejected(value):
    from app.inventory.units import quantity

    with pytest.raises(ValueError):
        quantity(value)


def test_exact_conversion_does_not_use_decimal_context_rounding():
    from app.inventory.units import convert

    assert convert("1.234567", 1, 1, None) == Decimal("1.234567")
    assert convert("1.234567", 1, 2, Decimal("1000")) == Decimal("1234.567")
    with pytest.raises(ValueError):
        convert("0.000001", 1, 2, Decimal(".001"))
    with pytest.raises(ValueError):
        convert("1", 1, 2, None)
    with pytest.raises(ValueError):
        convert("99999999999999", 1, 2, Decimal("1000"))
