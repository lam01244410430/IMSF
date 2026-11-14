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


class LotReadResponse(LotResponse):
    """OPEN-01/07 PROPOSAL: required evaluation only on GET, never writes."""
    freshness: Literal["FRESH", "WARNING", "EXPIRED", "UNKNOWN"]
    days_left: int | None
    local_date: date
    timezone: str


class LotReadPage(ReadDTO):
    items: list[LotReadResponse]
    next_cursor: str | None


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


class StockIntegrityFinding(ReadDTO):
    """P04-OPEN-13 PROPOSAL: identifiers and exact facts, never corrective commands."""

    code: str
    lot_id: Identifier | None = None
    product_id: Identifier | None = None
    movement_id: Identifier | None = None
    purchase_item_id: Identifier | None = None
    transaction_id: Identifier | None = None
    actual_transaction_id: Identifier | None = None
    link_id: Identifier | None = None
    return_movement_id: Identifier | None = None
    expected_quantity: SerializedDecimal | None = None
    actual_quantity: SerializedDecimal | None = None
    expected_count: int | None = None
    actual_count: int | None = None
    expected_state: str | None = None
    actual_state: str | None = None
    kind: str | None = None
    consumption_count: int | None = None
    disposal_count: int | None = None
    adjustment_count: int | None = None
    transaction_status: str | None = None
    transaction_kind: str | None = None


class StockIntegrityCategory(ReadDTO):
    count: int = Field(ge=0)
    items: list[StockIntegrityFinding] = Field(max_length=100)


class StockIntegrityReport(ReadDTO):
    """P04-OPEN-13 PROPOSAL: bounded read; unresolved links are separate facts."""

    limit_per_category: Literal[100] = 100
    projection_mismatches: StockIntegrityCategory
    receipt_anomalies: StockIntegrityCategory
    detail_misalignments: StockIntegrityCategory
    source_cap_violations: StockIntegrityCategory
    terminal_state_inconsistencies: StockIntegrityCategory
    purchase_link_inconsistencies: StockIntegrityCategory
    receipt_posting_mismatches: StockIntegrityCategory
    unresolved_refund_inventory_links: StockIntegrityCategory


# P06-OPEN-01/03/04/05/06/08 PROPOSALS: computed reads, not closure decisions.
class ValuationQuantities(ReadDTO):
    received_quantity: SerializedDecimal
    remaining_quantity: SerializedDecimal
    consumed_quantity: SerializedDecimal
    disposed_quantity: SerializedDecimal
    returned_quantity: SerializedDecimal
    adjusted_out_quantity: SerializedDecimal


class ValuationValues(ReadDTO):
    received_value: SerializedDecimal | None
    remaining_value: SerializedDecimal | None
    consumed_value: SerializedDecimal | None
    disposed_value: SerializedDecimal | None
    returned_value: SerializedDecimal | None
    adjusted_out_value: SerializedDecimal | None


class ValuationPurchase(ReadDTO):
    item_id: int
    transaction_id: int
    currency: str
    net_amount: SerializedDecimal
    reversed_original: bool
    status: Literal["AGREEMENT", "PURCHASE_MISMATCH", "UNKNOWN_COST"]


class LotValuationResponse(ValuationQuantities, ValuationValues):
    lot_id: int
    product_id: int
    base_unit_id: int
    source_kind: str
    received_at: datetime
    expires_on: date | None
    cost_currency: str | None
    unit_cost: SerializedDecimal | None
    terminal_state: str | None
    archived_at: datetime | None
    product_archived_at: datetime | None
    unknown_cost: bool
    quantity_tied_out: bool
    value_tied_out: bool | None
    reconciliation_status: Literal["TIED_OUT", "UNKNOWN_COST", "PURCHASE_MISMATCH", "TIE_OUT_MISMATCH"]
    purchase: ValuationPurchase | None
    issues: list[Literal["TIE_OUT_MISMATCH", "PURCHASE_MISMATCH", "REVERSED_ORIGINAL"]]


class ValuationCurrencyTotal(ValuationValues):
    currency: str


class UnknownCostLot(ValuationQuantities):
    lot_id: int
    product_id: int
    base_unit_id: int


class UnknownCostSection(ReadDTO):
    count: int
    items: list[UnknownCostLot]


class ValuationIssue(ReadDTO):
    lot_id: int
    code: Literal["TIE_OUT_MISMATCH", "PURCHASE_MISMATCH", "REVERSED_ORIGINAL"]


class ValuationIssues(ReadDTO):
    count: int
    items: list[ValuationIssue]


class ValuationReconciliation(ReadDTO):
    checked_lots: int
    quantity_tied_out_count: int
    value_tied_out_count: int
    unknown_cost_count: int
    purchase_agreement_count: int
    purchase_mismatch_count: int
    purchase_unknown_cost_count: int
    issues: ValuationIssues


class LotValuationPage(ReadDTO):
    items: list[LotValuationResponse]
    next_cursor: str | None
    totals_by_currency: list[ValuationCurrencyTotal] | None
    unknown_cost: UnknownCostSection
    reconciliation: ValuationReconciliation


# P06 Step 3 PROPOSALS: exact values; trim insignificant zeroes without rounding.
def waste_decimal_string(value):
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


WasteDecimal = Annotated[SerializedDecimal, PlainSerializer(waste_decimal_string, return_type=str, when_used="json")]
WasteReason = Literal["EXPIRED", "SPOILED", "DAMAGED", "OTHER"]


class WastePeriod(ReadDTO):
    from_date: date | None
    to_date: date | None
    timezone: str


class WasteAmount(ReadDTO):
    quantity: WasteDecimal
    value: WasteDecimal


class WasteReasonRow(WasteAmount):
    reason_code: WasteReason


class WastePeriodRow(WasteAmount):
    period: str


class WasteDenominator(ReadDTO):
    basis: Literal["total_received_value_known_cost"]
    value: WasteDecimal
    scope: Literal["same period and filters"]


class WasteCurrencySection(ReadDTO):
    currency: str
    disposed: WasteAmount
    by_reason: list[WasteReasonRow]
    by_period: list[WastePeriodRow]
    denominator: WasteDenominator
    waste_rate: WasteDecimal | None


class WasteProductRow(WasteAmount):
    currency: str
    product_id: int


class WasteUnknownReason(ReadDTO):
    reason_code: WasteReason
    quantity: WasteDecimal


class WasteUnknownCost(ReadDTO):
    disposed_quantity: WasteDecimal
    consumed_quantity: WasteDecimal
    by_reason: list[WasteUnknownReason]
    lot_ids: list[int]
    count: int


class WasteIssue(ReadDTO):
    lot_id: int
    code: Literal["TIE_OUT_MISMATCH"]


class WasteIssues(ReadDTO):
    count: int
    items: list[WasteIssue]


class WasteReconciliation(ReadDTO):
    status: Literal["TIED_OUT", "TIE_OUT_MISMATCH"]
    issues: WasteIssues


class WasteReport(ReadDTO):
    period: WastePeriod
    sections: list[WasteCurrencySection]
    by_product: list[WasteProductRow]
    next_cursor: str | None
    unknown_cost: WasteUnknownCost
    reconciliation: WasteReconciliation
