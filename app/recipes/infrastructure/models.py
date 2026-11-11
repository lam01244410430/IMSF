"""P04-OPEN-06/09/14 proposed frozen prerequisites; no recipe commands enabled."""

from datetime import datetime
from decimal import Decimal
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.finance.infrastructure.models import Scoped, scoped_fk, scoped_unique, finite


class Recipe(Scoped, Base):
    __tablename__ = "recipes"
    __table_args__ = (
        scoped_unique(),
        scoped_fk("created_by_member_id", "household_members"),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 200", name="ck_recipe_name"
        ),
        sa.CheckConstraint(finite("servings", "> 0"), name="ck_recipe_servings"),
        sa.CheckConstraint(
            "instructions IS NULL OR length(instructions)<=10000",
            name="ck_recipe_instructions",
        ),
        sa.Index("ix_recipe_creator", "household_id", "created_by_member_id"),
    )
    name: Mapped[str] = mapped_column(sa.Text)
    servings: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    created_by_member_id: Mapped[int] = mapped_column(sa.BigInteger)
    instructions: Mapped[str | None] = mapped_column(sa.Text)
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class RecipeIngredient(Scoped, Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        scoped_unique(),
        scoped_fk("recipe_id", "recipes"),
        scoped_fk("product_id", "products"),
        sa.UniqueConstraint("household_id", "recipe_id", "line_no"),
        sa.CheckConstraint("line_no>0", name="ck_ingredient_line"),
        sa.CheckConstraint(finite("quantity", "> 0"), name="ck_ingredient_quantity"),
        sa.Index("ix_ingredient_product", "household_id", "product_id"),
        sa.Index("ix_ingredient_unit", "unit_id"),
    )
    recipe_id: Mapped[int] = mapped_column(sa.BigInteger)
    line_no: Mapped[int] = mapped_column(sa.Integer)
    product_id: Mapped[int] = mapped_column(sa.BigInteger)
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    unit_id: Mapped[int] = mapped_column(sa.ForeignKey("measurement_units.id"))
    essential: Mapped[bool] = mapped_column(sa.Boolean)


class RecipeCookingHistory(Scoped, Base):
    __tablename__ = "recipe_cooking_history"
    __table_args__ = (
        scoped_unique(),
        scoped_fk("recipe_id", "recipes"),
        scoped_fk("actor_member_id", "household_members"),
        sa.CheckConstraint(finite("servings", "> 0"), name="ck_cooking_servings"),
        sa.CheckConstraint(
            "jsonb_typeof(recipe_snapshot)='object' AND recipe_snapshot ?& ARRAY['schema_version','recipe','ingredients','allocations','local_date','timezone'] AND recipe_snapshot->>'schema_version'='1' AND jsonb_typeof(recipe_snapshot->'recipe')='object' AND jsonb_typeof(recipe_snapshot->'ingredients')='array' AND jsonb_typeof(recipe_snapshot->'allocations')='array' AND jsonb_array_length(recipe_snapshot->'allocations')>0",
            name="ck_cooking_snapshot",
        ),
        sa.Index("ix_cooking_recipe", "household_id", "recipe_id"),
        sa.Index("ix_cooking_actor", "household_id", "actor_member_id"),
    )
    recipe_id: Mapped[int] = mapped_column(sa.BigInteger)
    cooked_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    servings: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    actor_member_id: Mapped[int] = mapped_column(sa.BigInteger)
    recipe_snapshot: Mapped[dict] = mapped_column(JSONB)
