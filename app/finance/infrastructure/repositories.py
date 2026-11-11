"""Scoped persistence and locks; never commit a use case independently."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert

from app.finance.infrastructure.models import (
    Account, AccountLedgerEntry, Category, Currency, IdempotencyRequest, Transaction, TransactionItem, TransactionPayment,
    ReconciliationSession, ReconciliationMatch,
)
from app.identity.infrastructure.models import AuditLog

MODELS = {"accounts": Account, "categories": Category, "transactions": Transaction, "items": TransactionItem,
          "payments": TransactionPayment, "ledger": AccountLedgerEntry,
          "reconciliations": ReconciliationSession, "matches": ReconciliationMatch}


def record(row):
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


class SqlAlchemyFinanceRepository:
    def __init__(self, session):
        self.session = session

    async def product(self, household_id, identifier):
        from app.inventory.infrastructure.models import Product
        row = await self.session.scalar(select(Product).where(Product.household_id == household_id, Product.id == identifier))
        return record(row) if row else None

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
        # Transfer settlement counts one leg; two full legs represent one amount.
        settled = await self.session.scalar(select(func.coalesce(func.sum(TransactionPayment.transaction_amount), 0)).where(
            TransactionPayment.household_id == household_id, TransactionPayment.transaction_id == transaction_id,
            *([TransactionPayment.direction == "OUT"] if row["kind"] == "TRANSFER" else [])))
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

    async def payments(self, household_id, transaction_id):
        return [record(row) for row in (await self.session.scalars(select(TransactionPayment).where(
            TransactionPayment.household_id == household_id, TransactionPayment.transaction_id == transaction_id
        ).order_by(TransactionPayment.id))).all()]

    async def has_entries(self, household_id, account_id):
        return await self.session.scalar(select(AccountLedgerEntry.id).where(
            AccountLedgerEntry.household_id == household_id, AccountLedgerEntry.account_id == account_id).limit(1)) is not None

    async def ledger_entries(self, household_id, transaction_id):
        return [record(row) for row in (await self.session.scalars(select(AccountLedgerEntry).where(
            AccountLedgerEntry.household_id == household_id, AccountLedgerEntry.transaction_id == transaction_id
        ).order_by(AccountLedgerEntry.id).execution_options(populate_existing=True))).all()]

    def _ledger_query(self, household_id, account_id=None, date_from=None, date_to=None):
        model = AccountLedgerEntry
        statement = select(model).where(model.household_id == household_id)
        if account_id is not None:
            statement = statement.where(model.account_id == account_id)
        if date_from is not None:
            statement = statement.where(model.posted_at >= date_from)
        if date_to is not None:
            statement = statement.where(model.posted_at <= date_to)
        return statement

    async def ledger(self, household_id, account_id, date_from, date_to, position, limit):
        model = AccountLedgerEntry
        statement = self._ledger_query(household_id, account_id, date_from, date_to)
        if position:
            statement = statement.where(tuple_(model.posted_at, model.id) < tuple_(datetime.fromisoformat(position[0]), position[1]))
        return [record(row) for row in (await self.session.scalars(statement.order_by(
            model.posted_at.desc(), model.id.desc()).limit(limit))).all()]

    async def balance(self, household_id, account_id, as_of=None, position=None):
        model = AccountLedgerEntry
        statement = self._ledger_query(household_id, account_id, date_to=as_of)
        if position:
            statement = statement.where(tuple_(model.posted_at, model.id) <= tuple_(datetime.fromisoformat(position[0]), position[1]))
        entries = statement.cte("visible_entries")
        latest = select(entries).order_by(entries.c.posted_at.desc(), entries.c.id.desc()).limit(1).cte("latest_entry")
        # One statement/snapshot: the sum and its stable boundary agree even
        # while another connection posts or settles this account.
        row = (await self.session.execute(select(
            select(func.coalesce(func.sum(entries.c.signed_amount), 0)).scalar_subquery().label("balance"),
            select(latest.c.posted_at).scalar_subquery().label("posted_at"),
            select(latest.c.id).scalar_subquery().label("id"),
        ))).mappings().one()
        return dict(row)

    async def reconciliation_rows(self, household_id, resource):
        """Unpaginated source rows for integrity; no mutations or balance cache."""
        model = MODELS[resource]
        return [record(row) for row in (await self.session.scalars(select(model).where(
            model.household_id == household_id).order_by(model.id).execution_options(populate_existing=True))).all()]

    async def reconciliation_anchor(self, household_id, account_id, currency_code):
        model = ReconciliationSession
        row = await self.session.scalar(select(model).where(model.household_id == household_id,
            model.account_id == account_id, model.currency_code == currency_code, model.state == "CLOSED").order_by(model.id.desc()).limit(1))
        return record(row) if row else None

    async def reconciliation_open(self, household_id, account_id):
        return await self.session.scalar(select(ReconciliationSession.id).where(
            ReconciliationSession.household_id == household_id, ReconciliationSession.account_id == account_id,
            ReconciliationSession.state == "OPEN"))

    async def reconciliation_cutoff(self, household_id, account_id):
        return await self.session.scalar(select(func.max(AccountLedgerEntry.id)).where(
            AccountLedgerEntry.household_id == household_id, AccountLedgerEntry.account_id == account_id))
