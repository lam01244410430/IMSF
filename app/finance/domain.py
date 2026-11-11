"""Pure draft, posting and settlement rules; OPEN policies remain proposals."""
from dataclasses import dataclass
from enum import StrEnum
from app.finance.money import Money, exact_decimal


class TransactionKind(StrEnum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    TRANSFER = "TRANSFER"
    OPENING = "OPENING"


class CategoryKind(StrEnum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class FinanceRequestError(Exception):
    def __init__(self, status_code: int, code: str):
        self.status_code = status_code
        self.code = code
        super().__init__()


@dataclass(frozen=True)
class Actor:
    user_id: int
    session_id: int


@dataclass(frozen=True)
class HouseholdContext:
    member_id: int
    role: str


def validate_draft(header: dict, items: list[dict], minor_units: int) -> None:
    if Money.parse(header["total_amount"], header["currency_code"], minor_units).amount < 0:
        raise ValueError("Draft total must be nonnegative")
    lines = set()
    for item in items:
        if item["line_no"] in lines:
            raise FinanceRequestError(409, "FINANCE_DUPLICATE_LINE")
        lines.add(item["line_no"])
        if exact_decimal(item["quantity"]) <= 0:
            raise ValueError("Quantity must be positive")
        if Money.parse(item["net_amount"], header["currency_code"], minor_units).amount < 0:
            raise ValueError("Line amount must be nonnegative")
    # DRAFT aggregates may be incomplete; posting rules belong to Step 3.


def validate_settlement(header: dict, items: list[dict], payments: list[dict],
                        settled, minor_units: int, *, posting: bool) -> None:
    """OPEN-05/11 PROPOSALS: exact same-currency, positive, settled amounts."""
    total = header["total_amount"]
    kind = header["kind"]
    if total <= 0 or kind not in TransactionKind:
        raise FinanceRequestError(422, "FINANCE_INCOMPLETE_TRANSACTION")
    if posting:
        if kind in {"INCOME", "EXPENSE"} and (not items or sum(i["net_amount"] for i in items) != total):
            raise FinanceRequestError(422, "FINANCE_ITEM_TOTAL_MISMATCH")
        if kind in {"TRANSFER", "OPENING"} and (items or header["category_id"] is not None):
            raise FinanceRequestError(422, "FINANCE_SETTLEMENT_SHAPE")
    elif kind not in {"INCOME", "EXPENSE"}:
        raise FinanceRequestError(409, "FINANCE_ALREADY_SETTLED")
    for payment in payments:
        amount = Money.parse(payment["amount"], header["currency_code"], minor_units).amount
        if amount <= 0 or payment["currency_code"] != header["currency_code"]:
            raise FinanceRequestError(422, "FINANCE_PAYMENT_CURRENCY_OR_AMOUNT")
        if payment["transaction_amount"] != amount:
            raise FinanceRequestError(422, "FINANCE_FX_UNSUPPORTED")
        expected = {"INCOME": "IN", "EXPENSE": "OUT"}.get(kind)
        if expected and payment["direction"] != expected:
            raise FinanceRequestError(422, "FINANCE_PAYMENT_DIRECTION")
    if kind in {"INCOME", "EXPENSE"}:
        if settled + sum(p["amount"] for p in payments) > total:
            raise FinanceRequestError(409, "FINANCE_OVERPAYMENT")
    elif kind == "TRANSFER":
        if (len(payments) != 2 or {p["direction"] for p in payments} != {"IN", "OUT"}
            or len({p["account_id"] for p in payments}) != 2 or any(p["amount"] != total for p in payments)):
            raise FinanceRequestError(422, "FINANCE_TRANSFER_SETTLEMENT")
    elif len(payments) != 1 or payments[0]["amount"] != total:
        raise FinanceRequestError(422, "FINANCE_OPENING_SETTLEMENT")


def require_full_reversal_eligible(original: dict, prior_refunds: list[dict]) -> None:
    """OPEN-07 PROPOSAL groundwork only; Step 4 must load links under locks.

    Refund creation remains unsupported. A future refund adapter must pass every
    linked refund; unresolved (including draft) refunds block full reversal.
    """
    if (original["status"] != "POSTED" or original["kind"] not in {"INCOME", "EXPENSE", "TRANSFER", "OPENING"}
        or original["is_reversed"]):
        raise FinanceRequestError(409, "FINANCE_REVERSAL_INELIGIBLE")
    if any(not refund.get("is_reversed", False) for refund in prior_refunds):
        raise FinanceRequestError(409, "FINANCE_UNRESOLVED_REFUND")
