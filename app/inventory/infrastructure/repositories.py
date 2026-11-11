"""P04-OPEN-07/10 proposals: scoped persistence, original→account→item→product→lot."""

from sqlalchemy import select, update, func
from app.finance.infrastructure.models import (
    Transaction,
    TransactionItem,
    TransactionPayment,
    Account,
)
from app.finance.infrastructure.repositories import record
from app.inventory.infrastructure.models import (
    MeasurementUnit,
    UnitConversion,
    ProductCategory,
    Product,
    InventoryLot,
    InventoryMovement,
    InventoryAdjustment,
    ConsumptionRecord,
    DisposalRecord,
    RefundInventoryLink,
)

MODELS = {
    "product-categories": ProductCategory,
    "products": Product,
    "inventory-lots": InventoryLot,
    "inventory-movements": InventoryMovement,
    "inventory-adjustments": InventoryAdjustment,
    "consumption": ConsumptionRecord,
    "disposals": DisposalRecord,
    "measurement-units": MeasurementUnit,
    "unit-conversions": UnitConversion,
}


class SqlAlchemyInventoryRepository:
    def __init__(self, session):
        self.session = session

    async def get(self, resource, hid, identifier, *, lock=False):
        model = MODELS[resource]
        statement = (
            select(model)
            .where(model.household_id == hid, model.id == identifier)
            .execution_options(populate_existing=True)
        )
        row = await self.session.scalar(
            statement.with_for_update() if lock else statement
        )
        return record(row) if row else None

    async def create(self, resource, values):
        row = MODELS[resource](**values)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return record(row)

    async def update(self, resource, hid, identifier, values):
        model = MODELS[resource]
        if values:
            await self.session.execute(
                update(model)
                .where(model.household_id == hid, model.id == identifier)
                .values(**values)
            )
        await self.session.flush()
        return await self.get(resource, hid, identifier)

    async def page(self, resource, hid, limit, position, filters):
        model = MODELS[resource]
        statement = select(model)
        if resource not in {"measurement-units", "unit-conversions"}:
            statement = statement.where(model.household_id == hid)
        for key, value in filters.items():
            if value is None:
                continue
            if key == "archived":
                statement = statement.where(
                    model.archived_at.is_not(None)
                    if value
                    else model.archived_at.is_(None)
                )
            elif key == "lot_id" and resource in {
                "inventory-adjustments", "consumption", "disposals"
            }:
                statement = statement.where(model.movement_id.in_(
                    select(InventoryMovement.id).where(
                        InventoryMovement.household_id == hid,
                        InventoryMovement.lot_id == value,
                    )
                ))
            elif key == "expires_from":
                statement = statement.where(model.expires_on >= value)
            elif key == "expires_to":
                statement = statement.where(model.expires_on <= value)
            else:
                statement = statement.where(getattr(model, key) == value)
        if resource == "unit-conversions":
            from sqlalchemy import tuple_

            if position:
                statement = statement.where(
                    tuple_(model.from_unit_id, model.to_unit_id) > tuple_(*position)
                )
            statement = statement.order_by(model.from_unit_id, model.to_unit_id)
        else:
            if position:
                statement = statement.where(model.id > position[0])
            statement = statement.order_by(model.id)
        return [
            record(row)
            for row in (await self.session.scalars(statement.limit(limit))).all()
        ]

    async def unit(self, identifier):
        row = await self.session.get(MeasurementUnit, identifier)
        return record(row) if row else None

    async def factor(self, source, target):
        return await self.session.scalar(
            select(UnitConversion.factor).where(
                UnitConversion.from_unit_id == source,
                UnitConversion.to_unit_id == target,
            )
        )

    async def lock_products(self, hid, identifiers):
        statement = (
            select(Product)
            .where(
                Product.household_id == hid, Product.id.in_(sorted(set(identifiers)))
            )
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return [record(row) for row in (await self.session.scalars(statement)).all()]

    async def lock_lots(self, hid, product_ids):
        statement = (
            select(InventoryLot)
            .where(
                InventoryLot.household_id == hid,
                InventoryLot.product_id.in_(sorted(set(product_ids))),
            )
            .order_by(
                InventoryLot.product_id,
                InventoryLot.expires_on.asc().nulls_last(),
                InventoryLot.received_at,
                InventoryLot.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return [record(row) for row in (await self.session.scalars(statement)).all()]

    async def has_history(self, hid, product_id):
        return (
            await self.session.scalar(
                select(InventoryLot.id)
                .where(
                    InventoryLot.household_id == hid,
                    InventoryLot.product_id == product_id,
                )
                .limit(1)
            )
            is not None
        )

    async def receipt_id(self, hid, lot_id):
        return await self.session.scalar(
            select(InventoryMovement.id).where(
                InventoryMovement.household_id == hid,
                InventoryMovement.lot_id == lot_id,
                InventoryMovement.kind == "RECEIPT",
            )
        )

    async def split_received(self, hid, item_id):
        return await self.session.scalar(
            select(func.coalesce(func.sum(InventoryLot.received_quantity), 0)).where(
                InventoryLot.household_id == hid,
                InventoryLot.purchase_item_id == item_id,
            )
        )

    async def lock_purchase(self, hid, item_id):
        # Discovery is scoped and unlocked; authoritative state is read after locks.
        tid = await self.session.scalar(
            select(TransactionItem.transaction_id).where(
                TransactionItem.household_id == hid, TransactionItem.id == item_id
            )
        )
        if tid is None:
            return None
        parent = await self.session.scalar(
            select(Transaction)
            .where(Transaction.household_id == hid, Transaction.id == tid)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        accounts = select(TransactionPayment.account_id).where(
            TransactionPayment.household_id == hid,
            TransactionPayment.transaction_id == tid,
        )
        await self.session.scalars(
            select(Account)
            .where(Account.household_id == hid, Account.id.in_(accounts))
            .order_by(Account.id)
            .with_for_update()
        )
        item = await self.session.scalar(
            select(TransactionItem)
            .where(TransactionItem.household_id == hid, TransactionItem.id == item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        reversed_id = await self.session.scalar(
            select(Transaction.id).where(
                Transaction.household_id == hid,
                Transaction.original_transaction_id == tid,
                Transaction.kind == "REVERSAL",
                Transaction.status == "POSTED",
            )
        )
        return record(item) | {
            "original_transaction_id": tid,
            "status": parent.status,
            "kind": parent.kind,
            "currency_code": parent.currency_code,
            "is_reversed": reversed_id is not None,
        }

    async def create_refund_link(self, values):
        """Append-only unresolved association; no commit or financial resolution.

        SQL trigger also locks/revalidates the original, preventing raw runtime
        insertion after a reversal. Same-household wrong aggregates fail real FKs.
        """
        purchase = await self.lock_purchase(
            values["household_id"], values["purchase_item_id"]
        )
        if purchase and purchase["product_id"] is not None:
            await self.lock_products(values["household_id"], [purchase["product_id"]])
            await self.lock_lots(values["household_id"], [purchase["product_id"]])
        row = RefundInventoryLink(**values)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return record(row)


    async def negative_kinds(self, hid, lot_id):
        return list((await self.session.scalars(
            select(InventoryMovement.kind).where(
                InventoryMovement.household_id == hid,
                InventoryMovement.lot_id == lot_id,
                InventoryMovement.quantity_delta < 0,
            ).distinct()
        )).all())

    async def lock_purchases(self, hid, item_ids):
        """P04-OPEN-07 PROPOSAL: batch the Step 2 original/account/item prefix.

        Multiple explicit purchase lots must lock ALL originals ascending, then
        ALL accounts ascending, then ALL items ascending before any product/lot.
        Discovery is scoped; authoritative rows are refreshed under those locks.
        """
        item_ids = sorted(set(item_ids))
        if not item_ids:
            return {}
        tids = (await self.session.scalars(
            select(TransactionItem.transaction_id).where(
                TransactionItem.household_id == hid,
                TransactionItem.id.in_(item_ids),
            ).distinct()
        )).all()
        parents = (await self.session.scalars(
            select(Transaction).where(
                Transaction.household_id == hid, Transaction.id.in_(tids)
            ).order_by(Transaction.id).with_for_update()
            .execution_options(populate_existing=True)
        )).all()
        accounts = select(TransactionPayment.account_id).where(
            TransactionPayment.household_id == hid,
            TransactionPayment.transaction_id.in_(tids),
        )
        await self.session.scalars(
            select(Account).where(
                Account.household_id == hid, Account.id.in_(accounts)
            ).order_by(Account.id).with_for_update()
        )
        items = (await self.session.scalars(
            select(TransactionItem).where(
                TransactionItem.household_id == hid,
                TransactionItem.id.in_(item_ids),
            ).order_by(TransactionItem.id).with_for_update()
            .execution_options(populate_existing=True)
        )).all()
        reversed_ids = set((await self.session.scalars(
            select(Transaction.original_transaction_id).where(
                Transaction.household_id == hid,
                Transaction.original_transaction_id.in_(tids),
                Transaction.kind == "REVERSAL", Transaction.status == "POSTED",
            )
        )).all())
        parents = {row.id: row for row in parents}
        return {item.id: record(item) | {
            "original_transaction_id": item.transaction_id,
            "status": parents[item.transaction_id].status,
            "kind": parents[item.transaction_id].kind,
            "is_reversed": item.transaction_id in reversed_ids,
        } for item in items}
