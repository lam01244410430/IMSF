"""P04-OPEN-01/03/04/07/08/10/13/14 proposals, not confirmed decisions."""

from datetime import date, datetime
from decimal import Decimal
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.finance.infrastructure.models import Scoped, scoped_fk, scoped_unique, finite


class MeasurementUnit(Base):
    __tablename__ = "measurement_units"
    __table_args__ = (
        sa.UniqueConstraint("id", "dimension"),
        sa.UniqueConstraint("code"),
        sa.CheckConstraint(
            "dimension IN ('MASS','VOLUME','COUNT')", name="ck_units_dimension"
        ),
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(sa.Text)
    dimension: Mapped[str] = mapped_column(sa.Text)


class UnitConversion(Base):
    __tablename__ = "unit_conversions"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["from_unit_id", "dimension"],
            ["measurement_units.id", "measurement_units.dimension"],
        ),
        sa.ForeignKeyConstraint(
            ["to_unit_id", "dimension"],
            ["measurement_units.id", "measurement_units.dimension"],
        ),
        sa.CheckConstraint("from_unit_id <> to_unit_id", name="ck_conversion_distinct"),
        sa.CheckConstraint(finite("factor", "> 0"), name="ck_conversion_factor"),
        sa.Index("ix_conversion_target", "to_unit_id", "dimension"),
    )
    from_unit_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    to_unit_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    dimension: Mapped[str] = mapped_column(sa.Text)
    factor: Mapped[Decimal] = mapped_column(sa.Numeric(30, 12))


class ProductCategory(Scoped, Base):
    __tablename__ = "product_categories"
    __table_args__ = (
        scoped_unique(),
        sa.UniqueConstraint("household_id", "name"),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 200", name="ck_product_category_name"
        ),
    )
    name: Mapped[str] = mapped_column(sa.Text)
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Product(Scoped, Base):
    __tablename__ = "products"
    __table_args__ = (
        scoped_unique(),
        scoped_fk("category_id", "product_categories"),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 200", name="ck_product_name"
        ),
        sa.Index("ix_product_category", "household_id", "category_id"),
        sa.Index("ix_product_unit", "base_unit_id"),
    )
    name: Mapped[str] = mapped_column(sa.Text)
    base_unit_id: Mapped[int] = mapped_column(sa.ForeignKey("measurement_units.id"))
    category_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class InventoryLot(Scoped, Base):
    __tablename__ = "inventory_lots"
    __table_args__ = (
        scoped_unique(),
        sa.UniqueConstraint("household_id", "id", "product_id"),
        sa.UniqueConstraint("household_id", "id", "purchase_item_id"),
        scoped_fk("product_id", "products"),
        sa.ForeignKeyConstraint(
            ["household_id", "purchase_item_id", "product_id"],
            [
                "transaction_items.household_id",
                "transaction_items.id",
                "transaction_items.product_id",
            ],
        ),
        sa.CheckConstraint(
            "source_kind IN ('PURCHASE','GIFT','MANUAL') AND ((source_kind='PURCHASE') = (purchase_item_id IS NOT NULL))",
            name="ck_lot_source",
        ),
        sa.CheckConstraint(finite("received_quantity", "> 0"), name="ck_lot_received"),
        sa.CheckConstraint(
            finite("remaining_quantity", ">= 0")
            + " AND remaining_quantity <= received_quantity",
            name="ck_lot_remaining",
        ),
        sa.CheckConstraint(
            "(cost_currency IS NULL) = (unit_cost IS NULL)", name="ck_lot_cost_pair"
        ),
        sa.CheckConstraint(finite("unit_cost", ">= 0"), name="ck_lot_cost"),
        sa.CheckConstraint(
            "(remaining_quantity=0) = (terminal_state IS NOT NULL) AND (terminal_state IS NULL OR terminal_state IN ('CONSUMED','DISCARDED','RETURNED','ADJUSTED_OUT','MIXED'))",
            name="ck_lot_terminal",
        ),
        sa.Index(
            "ix_lot_fefo",
            "household_id",
            "product_id",
            "expires_on",
            "received_at",
            "id",
            postgresql_where=sa.text("remaining_quantity>0"),
        ),
        sa.Index("ix_lot_purchase", "household_id", "purchase_item_id"),
        sa.Index("ix_lot_currency", "cost_currency"),
    )
    product_id: Mapped[int] = mapped_column(sa.BigInteger)
    source_kind: Mapped[str] = mapped_column(sa.Text)
    received_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    received_quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    remaining_quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    purchase_item_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    expires_on: Mapped[date | None] = mapped_column(sa.Date)
    cost_currency: Mapped[str | None] = mapped_column(sa.ForeignKey("currencies.code"))
    unit_cost: Mapped[Decimal | None] = mapped_column(sa.Numeric(30, 12))
    terminal_state: Mapped[str | None] = mapped_column(sa.Text)
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class InventoryMovement(Scoped, Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        scoped_unique(),
        sa.UniqueConstraint("household_id", "id", "lot_id", "kind"),
        scoped_fk("lot_id", "inventory_lots"),
        scoped_fk("actor_member_id", "household_members"),
        scoped_fk("transaction_id", "transactions"),
        sa.ForeignKeyConstraint(
            ["household_id", "correction_of_movement_id", "lot_id"],
            [
                "inventory_movements.household_id",
                "inventory_movements.id",
                "inventory_movements.lot_id",
            ],
        ),
        sa.UniqueConstraint("household_id", "id", "lot_id"),
        sa.CheckConstraint(
            "(kind IN ('RECEIPT','ADJUST_IN') AND quantity_delta>0) OR (kind IN ('CONSUME','DISPOSE','RETURN','ADJUST_OUT') AND quantity_delta<0)",
            name="ck_movement_sign",
        ),
        sa.CheckConstraint(
            finite("quantity_delta", "<> 0"), name="ck_movement_quantity"
        ),
        sa.CheckConstraint(
            "correction_of_movement_id IS NULL OR correction_of_movement_id<>id",
            name="ck_movement_correction",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR length(btrim(reason)) BETWEEN 1 AND 1000",
            name="ck_movement_reason",
        ),
        sa.Index(
            "uq_lot_receipt",
            "household_id",
            "lot_id",
            unique=True,
            postgresql_where=sa.text("kind='RECEIPT'"),
        ),
        sa.Index("ix_movement_lot", "household_id", "lot_id", "recorded_at", "id"),
        sa.Index("ix_movement_transaction", "household_id", "transaction_id"),
        sa.Index("ix_movement_actor", "household_id", "actor_member_id"),
        sa.Index(
            "ix_movement_correction",
            "household_id",
            "correction_of_movement_id",
            "lot_id",
        ),
    )
    lot_id: Mapped[int] = mapped_column(sa.BigInteger)
    kind: Mapped[str] = mapped_column(sa.Text)
    quantity_delta: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp()
    )
    actor_member_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    transaction_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    reason: Mapped[str | None] = mapped_column(sa.Text)
    correction_of_movement_id: Mapped[int | None] = mapped_column(sa.BigInteger)


class InventoryAdjustment(Scoped, Base):
    __tablename__ = "inventory_adjustments"
    __table_args__ = (
        scoped_unique(),
        scoped_fk("movement_id", "inventory_movements"),
        sa.UniqueConstraint("household_id", "movement_id"),
        sa.CheckConstraint(
            finite("counted_quantity", ">= 0"), name="ck_adjustment_count"
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) BETWEEN 1 AND 1000", name="ck_adjustment_reason"
        ),
    )
    movement_id: Mapped[int] = mapped_column(sa.BigInteger)
    counted_quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    reason: Mapped[str] = mapped_column(sa.Text)


class ConsumptionRecord(Scoped, Base):
    __tablename__ = "consumption_records"
    __table_args__ = (
        scoped_unique(),
        scoped_fk("movement_id", "inventory_movements"),
        sa.UniqueConstraint("household_id", "movement_id"),
        scoped_fk("cooking_history_id", "recipe_cooking_history"),
        sa.CheckConstraint(
            "reason_code IN ('DAILY_USE','CHECKOUT','COOKING') AND ((reason_code='COOKING') = (cooking_history_id IS NOT NULL))",
            name="ck_consumption_reason",
        ),
        sa.Index("ix_consumption_cooking", "household_id", "cooking_history_id"),
    )
    movement_id: Mapped[int] = mapped_column(sa.BigInteger)
    cooking_history_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    reason_code: Mapped[str] = mapped_column(sa.Text)


class DisposalRecord(Scoped, Base):
    __tablename__ = "disposal_records"
    __table_args__ = (
        scoped_unique(),
        scoped_fk("movement_id", "inventory_movements"),
        sa.UniqueConstraint("household_id", "movement_id"),
        sa.CheckConstraint(
            "reason_code IN ('EXPIRED','SPOILED','DAMAGED','OTHER')",
            name="ck_disposal_reason",
        ),
    )
    movement_id: Mapped[int] = mapped_column(sa.BigInteger)
    reason_code: Mapped[str] = mapped_column(sa.Text)


class RefundInventoryLink(Scoped, Base):
    __tablename__ = "refund_inventory_links"
    __table_args__ = (
        scoped_unique(),
        scoped_fk("original_transaction_id", "transactions"),
        scoped_fk("created_by_member_id", "household_members"),
        sa.ForeignKeyConstraint(
            ["household_id", "purchase_item_id", "original_transaction_id"],
            [
                "transaction_items.household_id",
                "transaction_items.id",
                "transaction_items.transaction_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "lot_id", "purchase_item_id"],
            [
                "inventory_lots.household_id",
                "inventory_lots.id",
                "inventory_lots.purchase_item_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "return_movement_id", "lot_id", "return_kind"],
            [
                "inventory_movements.household_id",
                "inventory_movements.id",
                "inventory_movements.lot_id",
                "inventory_movements.kind",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "original_payment_id", "original_transaction_id"],
            [
                "transaction_payments.household_id",
                "transaction_payments.id",
                "transaction_payments.transaction_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "original_ledger_entry_id", "original_transaction_id"],
            [
                "account_ledger_entries.household_id",
                "account_ledger_entries.id",
                "account_ledger_entries.transaction_id",
            ],
        ),
        sa.CheckConstraint("return_kind='RETURN'", name="ck_refund_return_kind"),
        sa.CheckConstraint(
            "length(btrim(reason)) BETWEEN 1 AND 1000", name="ck_refund_link_reason"
        ),
        sa.Index(
            "uq_refund_return",
            "household_id",
            "return_movement_id",
            unique=True,
            postgresql_where=sa.text("return_movement_id IS NOT NULL"),
        ),
        sa.Index("ix_refund_original", "household_id", "original_transaction_id"),
        sa.Index(
            "ix_refund_item",
            "household_id",
            "purchase_item_id",
            "original_transaction_id",
        ),
        sa.Index("ix_refund_lot", "household_id", "lot_id", "purchase_item_id"),
        sa.Index("ix_refund_actor", "household_id", "created_by_member_id"),
        sa.Index(
            "ix_refund_payment",
            "household_id",
            "original_payment_id",
            "original_transaction_id",
        ),
        sa.Index(
            "ix_refund_ledger",
            "household_id",
            "original_ledger_entry_id",
            "original_transaction_id",
        ),
    )
    original_transaction_id: Mapped[int] = mapped_column(sa.BigInteger)
    purchase_item_id: Mapped[int] = mapped_column(sa.BigInteger)
    lot_id: Mapped[int] = mapped_column(sa.BigInteger)
    created_by_member_id: Mapped[int] = mapped_column(sa.BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    reason: Mapped[str] = mapped_column(sa.Text)
    return_movement_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    return_kind: Mapped[str] = mapped_column(sa.Text, server_default="RETURN")
    original_payment_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    original_ledger_entry_id: Mapped[int | None] = mapped_column(sa.BigInteger)
