"""PROPOSAL OPEN-01/04: explicit currencies and decimal string boundaries."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, field_validator
from app.finance.money import exact_decimal


def decimal_string(value):
    if not isinstance(value, str):
        raise ValueError("Decimal strings required")
    return exact_decimal(value)


Amount = Annotated[Decimal, BeforeValidator(decimal_string), PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json")]
Identifier = Annotated[int, Field(gt=0, le=9223372036854775807)]
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Name = Annotated[str, Field(min_length=1, max_length=200)]


class WriteDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AccountCreate(WriteDTO):
    name: Name
    currency_code: CurrencyCode


class CategoryCreate(WriteDTO):
    name: Name
    kind: Literal["INCOME", "EXPENSE"]


class ItemCreate(WriteDTO):
    line_no: Annotated[int, Field(gt=0, le=2147483647)]
    description: Annotated[str, Field(min_length=1, max_length=1000)]
    quantity: Amount
    net_amount: Amount


class ItemPatch(WriteDTO):
    description: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    quantity: Amount | None = None
    net_amount: Amount | None = None

    @field_validator("description", "quantity", "net_amount", mode="before")
    @classmethod
    def nonnull(cls, v):
        if v is None:
            raise ValueError("Editable fields cannot be null")
        return v


class TransactionDraftCreate(WriteDTO):
    kind: Literal["INCOME", "EXPENSE", "TRANSFER", "OPENING"]
    occurred_at: datetime
    currency_code: CurrencyCode
    total_amount: Amount
    category_id: Identifier | None = None
    items: list[ItemCreate] = Field(default_factory=list)

    @field_validator("occurred_at")
    @classmethod
    def offset_required(cls, v):
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("An explicit UTC offset is required")
        return v.astimezone(timezone.utc)


class TransactionDraftPatch(WriteDTO):
    kind: Literal["INCOME", "EXPENSE", "TRANSFER", "OPENING"] | None = None
    occurred_at: datetime | None = None
    currency_code: CurrencyCode | None = None
    total_amount: Amount | None = None
    category_id: Identifier | None = None

    @field_validator("kind", "occurred_at", "currency_code", "total_amount", mode="before")
    @classmethod
    def nonnull(cls, v):
        if v is None:
            raise ValueError("Editable fields cannot be null")
        return v

    @field_validator("occurred_at")
    @classmethod
    def offset_required(cls, v):
        return TransactionDraftCreate.offset_required(v)


class ReadDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CurrencyResponse(ReadDTO):
    code: str
    minor_units: int


class AccountResponse(ReadDTO):
    id: int
    household_id: int
    name: str
    currency_code: str
    created_at: datetime
    archived_at: datetime | None


class CategoryResponse(ReadDTO):
    id: int
    household_id: int
    name: str
    kind: str
    archived_at: datetime | None


SerializedDecimal = Annotated[Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json")]


class ItemResponse(ReadDTO):
    id: int
    household_id: int
    transaction_id: int
    line_no: int
    description: str
    quantity: SerializedDecimal
    net_amount: SerializedDecimal


class TransactionResponse(ReadDTO):
    id: int
    household_id: int
    kind: str
    status: str
    occurred_at: datetime
    currency_code: str
    total_amount: SerializedDecimal
    created_by_member_id: int
    created_at: datetime
    category_id: int | None
    posted_at: datetime | None
    original_transaction_id: int | None
    reversal_reason: str | None
    items: list[ItemResponse]
    settled_amount: SerializedDecimal
    remaining_amount: SerializedDecimal
    is_reversed: bool
    reversal_transaction_id: int | None


class ReversalCreate(WriteDTO):
    reason: Annotated[str, Field(min_length=1, max_length=1000)]


class ReversalResponse(ReadDTO):
    original_transaction_id: int
    reversal_transaction: TransactionResponse
    payment_ids: list[int]
    ledger_entry_ids: list[int]


class AccountPage(ReadDTO):
    items: list[AccountResponse]
    next_cursor: str | None


class CategoryPage(ReadDTO):
    items: list[CategoryResponse]
    next_cursor: str | None


class TransactionPage(ReadDTO):
    items: list[TransactionResponse]
    next_cursor: str | None


class PaymentCreate(WriteDTO):
    """OPEN-05 PROPOSAL: a settled bookkeeping record, never a gateway command."""
    account_id: Identifier
    currency_code: CurrencyCode
    amount: Amount
    transaction_amount: Amount | None = None
    direction: Literal["IN", "OUT"]
    settled_at: datetime | None = None
    method_code: Literal["CASH", "BANK_TRANSFER", "CARD", "OTHER"] | None = None
    external_reference: Annotated[str, Field(max_length=200)] | None = None

    @field_validator("settled_at")
    @classmethod
    def settlement_offset_required(cls, v):
        if v is None:
            raise ValueError("Omit settled_at to use server posting time")
        return TransactionDraftCreate.offset_required(v)

    @field_validator("transaction_amount", mode="before")
    @classmethod
    def nonnull(cls, v):
        if v is None:
            raise ValueError("Omit transaction_amount to use amount")
        return v


class TransactionPost(WriteDTO):
    payments: list[PaymentCreate]


class PaymentBatchCreate(WriteDTO):
    payments: list[PaymentCreate] = Field(min_length=1)


class PaymentResponse(ReadDTO):
    id: int
    household_id: int
    transaction_id: int
    account_id: int
    currency_code: str
    amount: SerializedDecimal
    transaction_amount: SerializedDecimal
    direction: str
    settled_at: datetime
    created_at: datetime
    created_by_member_id: int
    method_code: str | None
    external_reference: str | None
    reverses_payment_id: int | None


class PaymentBatchResponse(ReadDTO):
    transaction_id: int
    payments: list[PaymentResponse]
    settled_amount: SerializedDecimal
    remaining_amount: SerializedDecimal


class LedgerEntryResponse(ReadDTO):
    id: int
    household_id: int
    transaction_id: int
    account_id: int
    currency_code: str
    signed_amount: SerializedDecimal
    posted_at: datetime
    payment_id: int | None
    reverses_entry_id: int | None


class LedgerPage(ReadDTO):
    items: list[LedgerEntryResponse]
    next_cursor: str | None


class BalanceResponse(ReadDTO):
    account_id: int
    currency_code: str
    balance: SerializedDecimal
    cursor: str | None
