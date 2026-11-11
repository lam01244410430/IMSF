"""P04-OPEN-01/08/13 proposals: Step 2 inventory request/response contracts."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import (
    BeforeValidator,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)
from app.finance.dto import (
    Identifier,
    Name,
    WriteDTO,
    ReadDTO,
    SerializedDecimal,
    CurrencyCode,
)
from app.inventory.units import quantity, cost


def string_quantity(value):
    if not isinstance(value, str):
        raise ValueError("Decimal string required")
    return quantity(value)


def string_cost(value):
    if not isinstance(value, str):
        raise ValueError("Decimal string required")
    return cost(value)


Quantity = Annotated[
    Decimal,
    BeforeValidator(string_quantity),
    PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json"),
]
Cost = Annotated[
    Decimal,
    BeforeValidator(string_cost),
    PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json"),
]
Reason = Annotated[str, Field(min_length=1, max_length=1000)]


class EmptyCommand(WriteDTO):
    pass


class ReasonCommand(WriteDTO):
    reason: Reason


class CategoryCreate(WriteDTO):
    name: Name


class CategoryPatch(CategoryCreate):
    pass


class ProductCreate(CategoryCreate):
    base_unit_id: Identifier
    category_id: Identifier | None = None


class ProductPatch(WriteDTO):
    name: Name | None = None
    base_unit_id: Identifier | None = None
    category_id: Identifier | None = None

    @field_validator("name", "base_unit_id", mode="before")
    @classmethod
    def nonnull(cls, value):
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class LotReceipt(WriteDTO):
    product_id: Identifier
    source_kind: Literal["PURCHASE", "GIFT", "MANUAL"]
    quantity: Quantity
    unit_id: Identifier
    received_at: datetime
    expires_on: date | None = None
    purchase_item_id: Identifier | None = None
    cost_currency: CurrencyCode | None = None
    unit_cost: Cost | None = None
    reason: Reason | None = None

    @field_validator("received_at")
    @classmethod
    def offset_required(cls, value):
        if value.utcoffset() is None:
            raise ValueError("Explicit offset required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def pairs(self):
        if (self.source_kind == "PURCHASE") != (self.purchase_item_id is not None):
            raise ValueError("Purchase requires item; other sources forbid it")
        if (self.unit_cost is None) != (self.cost_currency is None):
            raise ValueError("Cost/currency must be paired")
        return self


class LotMetadataPatch(ReasonCommand):
    expires_on: date | None = None


class UnitResponse(ReadDTO):
    id: int
    code: str
    dimension: str


class ConversionResponse(ReadDTO):
    from_unit_id: int
    to_unit_id: int
    dimension: str
    factor: SerializedDecimal


class ProductCategoryResponse(ReadDTO):
    id: int
    household_id: int
    name: str
    archived_at: datetime | None


class ProductResponse(ProductCategoryResponse):
    base_unit_id: int
    category_id: int | None


class LotResponse(ReadDTO):
    id: int
    household_id: int
    product_id: int
    source_kind: str
    received_at: datetime
    received_quantity: SerializedDecimal
    remaining_quantity: SerializedDecimal
    purchase_item_id: int | None
    expires_on: date | None
    cost_currency: str | None
    unit_cost: SerializedDecimal | None
    terminal_state: str | None
    archived_at: datetime | None
    receipt_movement_id: int


class MovementResponse(ReadDTO):
    id: int
    household_id: int
    lot_id: int
    kind: str
    quantity_delta: SerializedDecimal
    occurred_at: datetime
    recorded_at: datetime
    actor_member_id: int | None
    transaction_id: int | None
    reason: str | None
    correction_of_movement_id: int | None


class UnitPage(ReadDTO):
    items: list[UnitResponse]
    next_cursor: str | None


class ConversionPage(ReadDTO):
    items: list[ConversionResponse]
    next_cursor: str | None


class CategoryPage(ReadDTO):
    items: list[ProductCategoryResponse]
    next_cursor: str | None


class ProductPage(ReadDTO):
    items: list[ProductResponse]
    next_cursor: str | None


class LotPage(ReadDTO):
    items: list[LotResponse]
    next_cursor: str | None


class MovementPage(ReadDTO):
    items: list[MovementResponse]
    next_cursor: str | None
