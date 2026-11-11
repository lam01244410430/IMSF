"""Pure rules for finance drafts; posting and settlement arrive in later steps."""
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
