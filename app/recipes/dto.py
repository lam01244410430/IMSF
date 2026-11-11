"""P04-OPEN-06/09/13 PROPOSAL: minimum retained recipes and cooking inputs."""
from datetime import datetime
from typing import Annotated
from pydantic import Field, StrictBool, field_validator, model_validator
from app.finance.dto import Identifier, Name, ReadDTO, SerializedDecimal, WriteDTO
from app.inventory.dto import Quantity, AllocationResponse


class IngredientCreate(WriteDTO):
    line_no: Annotated[int, Field(gt=0, le=2147483647)]
    product_id: Identifier
    quantity: Quantity
    unit_id: Identifier
    essential: StrictBool


class IngredientPatch(WriteDTO):
    product_id: Identifier | None = None
    quantity: Quantity | None = None
    unit_id: Identifier | None = None
    essential: StrictBool | None = None

    @field_validator('product_id', 'quantity', 'unit_id', 'essential', mode='before')
    @classmethod
    def nonnull(cls, value):
        if value is None:
            raise ValueError('Field cannot be null')
        return value


class RecipeCreate(WriteDTO):
    name: Name
    servings: Quantity
    instructions: Annotated[str, Field(max_length=10000)] | None = None
    # P04-OPEN-06/13 PROPOSAL: at least one ingredient, at most 100.
    ingredients: Annotated[list[IngredientCreate], Field(min_length=1, max_length=100)]

    @model_validator(mode='after')
    def unique_lines(self):
        if len({line.line_no for line in self.ingredients}) != len(self.ingredients):
            raise ValueError('Unique ingredient line numbers required')
        return self


class RecipePatch(WriteDTO):
    name: Name | None = None
    servings: Quantity | None = None
    instructions: Annotated[str, Field(max_length=10000)] | None = None

    @field_validator('name', 'servings', mode='before')
    @classmethod
    def nonnull(cls, value):
        if value is None:
            raise ValueError('Field cannot be null')
        return value


class CookingCreate(WriteDTO):
    servings: Quantity


class IngredientResponse(ReadDTO):
    id: int
    household_id: int
    recipe_id: int
    line_no: int
    product_id: int
    quantity: SerializedDecimal
    unit_id: int
    essential: bool


class RecipeResponse(ReadDTO):
    id: int
    household_id: int
    name: str
    servings: SerializedDecimal
    instructions: str | None
    archived_at: datetime | None
    created_by_member_id: int
    ingredients: list[IngredientResponse]


class RecipePage(ReadDTO):
    items: list[RecipeResponse]
    next_cursor: str | None


class CookingResponse(ReadDTO):
    history_id: int
    recipe_id: int
    servings: SerializedDecimal
    consumption_record_ids: list[int]
    allocations: list[AllocationResponse]


class CookingHistoryResponse(ReadDTO):
    id: int
    household_id: int
    recipe_id: int
    cooked_at: datetime
    servings: SerializedDecimal
    actor_member_id: int
    recipe_snapshot: dict
    consumption_record_ids: list[int]


class CookingHistoryPage(ReadDTO):
    items: list[CookingHistoryResponse]
    next_cursor: str | None
