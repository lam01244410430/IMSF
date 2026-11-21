"""Supported currencies (ISO 4217) — single source of truth.

Lam 2026-11-21 (D-F7): CNY, VND + USD, EUR, HKD + all ASEAN
currencies (14 total). Used by the transactions API, equipments
API, households API, and the receipt worker. Never sum across
currencies; amounts are stored and summed only within one currency.
No conversion / no exchange rates.
"""

SUPPORTED_CURRENCIES = (
    "CNY", "VND", "USD", "EUR", "HKD",
    "THB", "MYR", "SGD", "IDR", "PHP",
    "KHR", "LAK", "MMK", "BND",
)
