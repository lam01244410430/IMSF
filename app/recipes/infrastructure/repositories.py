"""P04-OPEN-06/07 PROPOSAL: scoped recipe locks, retained lines and history."""
from sqlalchemy import select
from app.finance.infrastructure.repositories import record
from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
from app.inventory.infrastructure.models import ConsumptionRecord
from app.recipes.infrastructure.models import Recipe, RecipeIngredient, RecipeCookingHistory


class SqlAlchemyRecipeRepository(SqlAlchemyInventoryRepository):
    # Reuse scoped CRUD/pagination; this adapter only writes recipe-owned rows.
    models = {'recipes': Recipe, 'recipe-ingredients': RecipeIngredient,
              'recipe-cooking-history': RecipeCookingHistory}

    async def ingredients(self, hid, recipe_id, *, lock=False):
        statement = select(RecipeIngredient).where(
            RecipeIngredient.household_id == hid, RecipeIngredient.recipe_id == recipe_id
        ).order_by(RecipeIngredient.line_no, RecipeIngredient.id).execution_options(populate_existing=True)
        if lock:
            statement = statement.with_for_update()
        return [record(row) for row in (await self.session.scalars(statement)).all()]

    async def consumption_ids(self, hid, history_id):
        return list((await self.session.scalars(select(ConsumptionRecord.id).where(
            ConsumptionRecord.household_id == hid, ConsumptionRecord.cooking_history_id == history_id
        ).order_by(ConsumptionRecord.id))).all())
