"""P04-OPEN-07/10/11 proposed real reversal-effects adapter; no finance writes."""

from sqlalchemy import select
from app.finance.ports import ReversalEffectsSnapshot
from app.finance.infrastructure.models import TransactionItem
from app.inventory.infrastructure.models import RefundInventoryLink
from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository


class SqlAlchemyReversalEffects:
    def __init__(self, session):
        self.session = session
        self.repository = SqlAlchemyInventoryRepository(session)

    async def load_locked(self, household_id, original_transaction_id):
        # Caller holds original/accounts. Lock items ascending before products;
        # all receipt/link writers also hold that original, including SQL guards.
        items = (
            await self.session.scalars(
                select(TransactionItem)
                .where(
                    TransactionItem.household_id == household_id,
                    TransactionItem.transaction_id == original_transaction_id,
                )
                .order_by(TransactionItem.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        product_ids = sorted(
            {item.product_id for item in items if item.product_id is not None}
        )
        await self.repository.lock_products(household_id, product_ids)
        lots = await self.repository.lock_lots(household_id, product_ids)
        item_ids = {item.id for item in items}
        stock_ids = tuple(
            lot["id"] for lot in lots if lot["purchase_item_id"] in item_ids
        )
        # Append-only rows need no UPDATE privilege/row lock: original lock
        # excludes competing inserts, and existing rows cannot change or vanish.
        links = (
            await self.session.scalars(
                select(RefundInventoryLink)
                .where(
                    RefundInventoryLink.household_id == household_id,
                    RefundInventoryLink.original_transaction_id
                    == original_transaction_id,
                )
                .order_by(RefundInventoryLink.id)
            )
        ).all()
        return ReversalEffectsSnapshot(
            tuple({"id": row.id, "is_reversed": False} for row in links), stock_ids
        )
