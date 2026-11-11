"""P04-OPEN-01/08/13 proposals: Step 2/3 inventory request/response contracts."""

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
from app.inventory.units import quantity, cost, decimal_value


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


# P04-OPEN-04/05/13 PROPOSAL: explicit commands, no arbitrary signed delta.
def string_count(value):
    if not isinstance(value, str):
        raise ValueError("Decimal string required")
    result = decimal_value(value)
    if result < 0:
        raise ValueError("Nonnegative count required")
    return result


CountedQuantity = Annotated[
    Decimal,
    BeforeValidator(string_count),
    PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json"),
]


class AdjustmentCreate(ReasonCommand):
    lot_id: Identifier
    counted_quantity: CountedQuantity
    unit_id: Identifier
    correction_of_movement_id: Identifier | None = None


class LotAllocation(WriteDTO):
    lot_id: Identifier
    quantity: Quantity
    unit_id: Identifier


class ConsumptionCreate(WriteDTO):
    allocations: Annotated[list[LotAllocation], Field(min_length=1, max_length=100)]
    # P04-OPEN-05 PROPOSAL: COOKING is server-only, never a route input.
    reason_code: Literal["DAILY_USE", "CHECKOUT"]
    reason: Reason | None = None


class DisposalCreate(WriteDTO):
    allocations: Annotated[list[LotAllocation], Field(min_length=1, max_length=100)]
    reason_code: Literal["EXPIRED", "SPOILED", "DAMAGED", "OTHER"]
    reason: Reason | None = None

    @model_validator(mode="after")
    def other_requires_text(self):
        if self.reason_code == "OTHER" and not self.reason:
            raise ValueError("OTHER requires reason text")
        return self


class ReturnCreate(ReasonCommand):
    quantity: Quantity
    unit_id: Identifier


class AdjustmentResponse(ReadDTO):
    id: int
    household_id: int
    movement_id: int
    counted_quantity: SerializedDecimal
    reason: str


class ConsumptionResponse(ReadDTO):
    id: int
    household_id: int
    movement_id: int
    reason_code: str
    cooking_history_id: int | None


class DisposalResponse(ReadDTO):
    id: int
    household_id: int
    movement_id: int
    reason_code: str


class AllocationResponse(ReadDTO):
    product_id: int
    lot_id: int
    base_quantity: SerializedDecimal
    remaining_quantity: SerializedDecimal


class StockCommandResponse(ReadDTO):
    movement_ids: list[int]
    consumption_record_ids: list[int]
    disposal_record_ids: list[int]
    adjustment_ids: list[int]
    allocations: list[AllocationResponse]
    refund_inventory_link_ids: list[int]


class AdjustmentPage(ReadDTO):
    items: list[AdjustmentResponse]
    next_cursor: str | None


class ConsumptionPage(ReadDTO):
    items: list[ConsumptionResponse]
    next_cursor: str | None


class DisposalPage(ReadDTO):
    items: list[DisposalResponse]
    next_cursor: str | None
