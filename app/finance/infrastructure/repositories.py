"""Scoped persistence and locks; never commit a use case independently."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert

from app.finance.infrastructure.models import (
    Account, Category, Currency, IdempotencyRequest, Transaction, TransactionItem, TransactionPayment,
)
from app.identity.infrastructure.models import AuditLog

MODELS = {"accounts": Account, "categories": Category, "transactions": Transaction, "items": TransactionItem}


def record(row):
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


class SqlAlchemyFinanceRepository:
    def __init__(self, session):
        self.session = session

    async def currencies(self):
        return [record(row) for row in (await self.session.scalars(select(Currency).order_by(Currency.code))).all()]

    async def currency(self, code):
        row = await self.session.get(Currency, code)
        return record(row) if row else None

    async def get(self, resource, household_id, identifier, *, lock=False):
        model = MODELS[resource]
        statement = select(model).where(model.household_id == household_id, model.id == identifier).execution_options(populate_existing=True)
        row = await self.session.scalar(statement.with_for_update() if lock else statement)
        return record(row) if row else None

    async def page(self, resource, household_id, limit, cursor, filters):
        model = MODELS[resource]
        statement = select(model).where(model.household_id == household_id)
        for key, value in filters.items():
            if value is not None:
                statement = statement.where(getattr(model, key) == value)
        if resource == "transactions":
            if cursor:
                statement = statement.where(tuple_(model.occurred_at, model.id) < tuple_(datetime.fromisoformat(cursor[0]), cursor[1]))
            statement = statement.order_by(model.occurred_at.desc(), model.id.desc())
        else:
            if cursor:
                statement = statement.where(model.id > cursor[0])
            statement = statement.order_by(model.id)
        return [record(row) for row in (await self.session.scalars(statement.limit(limit))).all()]

    async def items(self, household_id, transaction_id):
        return [record(row) for row in (await self.session.scalars(select(TransactionItem).where(
            TransactionItem.household_id == household_id, TransactionItem.transaction_id == transaction_id
        ).order_by(TransactionItem.line_no))).all()]

    async def create(self, resource, values):
        row = MODELS[resource](**values)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return record(row)

    async def update(self, resource, household_id, identifier, values):
        model = MODELS[resource]
        if values:
            await self.session.execute(update(model).where(model.household_id == household_id, model.id == identifier).values(**values))
        await self.session.flush()
        return await self.get(resource, household_id, identifier)

    async def transaction_result(self, household_id, transaction_id):
        row = await self.get("transactions", household_id, transaction_id)
        row["items"] = await self.items(household_id, transaction_id)
        # Source sums, never a mutable balance/settlement column. Step 2 writes no payments.
        settled = await self.session.scalar(select(func.coalesce(func.sum(TransactionPayment.transaction_amount), 0)).where(
            TransactionPayment.household_id == household_id, TransactionPayment.transaction_id == transaction_id))
        reversal = await self.session.scalar(select(Transaction.id).where(Transaction.household_id == household_id,
            Transaction.original_transaction_id == transaction_id, Transaction.kind == "REVERSAL", Transaction.status == "POSTED"))
        return row | {"settled_amount": Decimal(settled), "remaining_amount": row["total_amount"] - settled,
                      "is_reversed": reversal is not None, "reversal_transaction_id": reversal}

    async def reserve(self, values):
        identifier = await self.session.scalar(insert(IdempotencyRequest).values(**values,
            response_status=200, response_body={"_pending": True}).on_conflict_do_nothing(
                index_elements=["household_id", "actor_member_id", "operation", "request_key"]
            ).returning(IdempotencyRequest.id))
        if identifier is not None:
            return identifier, None
        # A fresh statement sees the committed winner after ON CONFLICT waits.
        saved = await self.session.scalar(select(IdempotencyRequest).where(*[
            getattr(IdempotencyRequest, key) == values[key]
            for key in ("household_id", "actor_member_id", "operation", "request_key")]))
        return saved.id, record(saved)

    async def complete(self, identifier, status, body):
        await self.session.execute(update(IdempotencyRequest).where(IdempotencyRequest.id == identifier).values(
            response_status=status, response_body=body))
        await self.session.flush()

    async def audit(self, values):
        self.session.add(AuditLog(**values))
        await self.session.flush()
