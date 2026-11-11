"""P04-OPEN-05/07/13/15 PROPOSAL checkout contracts; decimal strings only."""
from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import Field, field_validator, model_validator
from app.finance.dto import WriteDTO, ReadDTO, Identifier, PaymentCreate, TransactionResponse, CurrencyCode
from app.inventory.dto import Quantity, Cost, Reason, LotReceipt


class StockDemand(WriteDTO):
    product_id: Identifier
    quantity: Quantity
    unit_id: Identifier


class StockCheckoutCreate(WriteDTO):
    # P04-OPEN-13 PROPOSAL: 100 input demand lines, before aggregation.
    items: Annotated[list[StockDemand], Field(min_length=1, max_length=100)]
    reason_code: Literal['CHECKOUT']
    reason: Reason | None = None


class PurchaseLotCreate(WriteDTO):
    item_id: Identifier
    quantity: Quantity
    unit_id: Identifier
    received_at: datetime
    expires_on: date | None = None
    cost_currency: CurrencyCode | None = None
    unit_cost: Cost | None = None

    @field_validator('received_at')
    @classmethod
    def offset_required(cls, value):
        return LotReceipt.offset_required(value)

    @model_validator(mode='after')
    def paired_cost(self):
        if (self.cost_currency is None) != (self.unit_cost is None):
            raise ValueError('Cost/currency must be paired')
        return self


class PurchaseCheckoutCreate(WriteDTO):
    transaction_id: Identifier
    payments: list[PaymentCreate]
    lots: list[PurchaseLotCreate]


class PurchaseCheckoutResponse(ReadDTO):
    transaction: TransactionResponse
    lot_ids: list[int]
    receipt_movement_ids: list[int]
