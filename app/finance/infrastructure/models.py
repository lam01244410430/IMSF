"""Finance persistence. PROPOSAL OPEN-01: NUMERIC(20,6); no stored balances."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Scoped:
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    household_id: Mapped[int] = mapped_column(sa.ForeignKey("households.id"))


def scoped_unique():
    return sa.UniqueConstraint("household_id", "id")


def scoped_fk(column, target):
    return sa.ForeignKeyConstraint(["household_id", column], [f"{target}.household_id", f"{target}.id"])


def finite(column, sign):
    return f"{column} {sign} AND {column} NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)"


class Currency(Base):
    __tablename__ = "currencies"
    __table_args__ = (
        sa.CheckConstraint("code ~ '^[A-Z]{3}$'", name="ck_currencies_code"),
        sa.CheckConstraint("minor_units BETWEEN 0 AND 6", name="ck_currencies_scale"),
    )
    code: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    minor_units: Mapped[int] = mapped_column(sa.SmallInteger)


class Account(Scoped, Base):
    __tablename__ = "accounts"
    __table_args__ = (scoped_unique(), sa.UniqueConstraint("household_id", "id", "currency_code"),
                      sa.CheckConstraint("length(btrim(name)) BETWEEN 1 AND 200", name="ck_accounts_name"))
    name: Mapped[str] = mapped_column(sa.Text)
    currency_code: Mapped[str] = mapped_column(sa.ForeignKey("currencies.code"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Category(Scoped, Base):
    __tablename__ = "categories"
    __table_args__ = (scoped_unique(), sa.UniqueConstraint("household_id", "kind", "name"),
        sa.CheckConstraint("kind IN ('INCOME','EXPENSE')", name="ck_categories_kind"),
        sa.CheckConstraint("length(btrim(name)) BETWEEN 1 AND 200", name="ck_categories_name"))
    name: Mapped[str] = mapped_column(sa.Text)
    kind: Mapped[str] = mapped_column(sa.Text)
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Transaction(Scoped, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        scoped_unique(), sa.UniqueConstraint("household_id", "id", "currency_code"),
        scoped_fk("created_by_member_id", "household_members"), scoped_fk("category_id", "categories"),
        scoped_fk("original_transaction_id", "transactions"),
        sa.CheckConstraint("kind IN ('INCOME','EXPENSE','TRANSFER','OPENING','REVERSAL')", name="ck_transactions_kind"),
        sa.CheckConstraint("status IN ('DRAFT','POSTED')", name="ck_transactions_status"),
        sa.CheckConstraint("(status='POSTED') = (posted_at IS NOT NULL)", name="ck_transactions_posted"),
        sa.CheckConstraint(finite("total_amount", ">= 0"), name="ck_transactions_amount"),
        sa.CheckConstraint("(kind='REVERSAL' AND original_transaction_id IS NOT NULL AND reversal_reason IS NOT NULL AND length(btrim(reversal_reason)) BETWEEN 1 AND 1000 AND original_transaction_id <> id) OR (kind <> 'REVERSAL' AND original_transaction_id IS NULL AND reversal_reason IS NULL)", name="ck_transactions_reversal"),
        sa.Index("uq_transactions_reversal", "household_id", "original_transaction_id", unique=True,
                 postgresql_where=sa.text("kind='REVERSAL' AND status='POSTED'")),
        sa.Index("ix_transactions_timeline", "household_id", sa.text("occurred_at DESC"), sa.text("id DESC")),
        sa.Index("ix_transactions_creator", "household_id", "created_by_member_id"),
        sa.Index("ix_transactions_category", "household_id", "category_id"),
        sa.Index("ix_transactions_original", "household_id", "original_transaction_id"),
    )
    kind: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(sa.Text, server_default="DRAFT")
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    currency_code: Mapped[str] = mapped_column(sa.ForeignKey("currencies.code"))
    total_amount: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    created_by_member_id: Mapped[int] = mapped_column(sa.BigInteger)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    category_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    original_transaction_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    reversal_reason: Mapped[str | None] = mapped_column(sa.Text)


class TransactionItem(Scoped, Base):
    __tablename__ = "transaction_items"
    __table_args__ = (scoped_unique(), scoped_fk("transaction_id", "transactions"),
        sa.UniqueConstraint("household_id", "transaction_id", "line_no"),
        sa.UniqueConstraint("household_id", "id", "product_id"),
        sa.UniqueConstraint("household_id", "id", "transaction_id"),
        scoped_fk("product_id", "products"),
        sa.CheckConstraint("(product_id IS NULL) = (base_quantity IS NULL)", name="ck_items_product_pair"),
        sa.CheckConstraint(finite("base_quantity", "> 0"), name="ck_items_base_quantity"),
        sa.Index("ix_item_product", "household_id", "product_id"),
        sa.CheckConstraint("line_no > 0", name="ck_items_line"),
        sa.CheckConstraint("length(btrim(description)) BETWEEN 1 AND 1000", name="ck_items_description"),
        sa.CheckConstraint(finite("quantity", "> 0"), name="ck_items_quantity"),
        sa.CheckConstraint(finite("net_amount", ">= 0"), name="ck_items_amount"))
    transaction_id: Mapped[int] = mapped_column(sa.BigInteger)
    line_no: Mapped[int] = mapped_column(sa.Integer)
    description: Mapped[str] = mapped_column(sa.Text)
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    net_amount: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    # P04-OPEN-01/14 PROPOSAL: new/editable DRAFT only; no posted backfill.
    product_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    base_quantity: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 6))


class TransactionPayment(Scoped, Base):
    __tablename__ = "transaction_payments"
    __table_args__ = (
        scoped_unique(), sa.UniqueConstraint("household_id", "id", "transaction_id"), sa.UniqueConstraint("household_id", "id", "transaction_id", "account_id", "currency_code"),
        sa.ForeignKeyConstraint(["household_id", "transaction_id", "currency_code"], ["transactions.household_id", "transactions.id", "transactions.currency_code"]),
        sa.ForeignKeyConstraint(["household_id", "account_id", "currency_code"], ["accounts.household_id", "accounts.id", "accounts.currency_code"]),
        scoped_fk("created_by_member_id", "household_members"), scoped_fk("reverses_payment_id", "transaction_payments"),
        sa.CheckConstraint(finite("amount", "> 0"), name="ck_payments_amount"),
        sa.CheckConstraint(finite("transaction_amount", "> 0"), name="ck_payments_transaction_amount"),
        sa.CheckConstraint("amount = transaction_amount AND exchange_rate IS NULL", name="ck_payments_same_currency"),
        sa.CheckConstraint("direction IN ('IN','OUT')", name="ck_payments_direction"),
        sa.CheckConstraint("reverses_payment_id IS NULL OR reverses_payment_id <> id", name="ck_payments_not_self"),
        sa.CheckConstraint("external_reference IS NULL OR length(external_reference) <= 200", name="ck_payments_reference"),
        sa.Index("uq_payments_reversal", "household_id", "reverses_payment_id", unique=True, postgresql_where=sa.text("reverses_payment_id IS NOT NULL")),
        sa.Index("ix_payments_transaction", "household_id", "transaction_id", "id"),
        sa.Index("ix_payments_account", "household_id", "account_id", "currency_code"),
        sa.Index("ix_payments_creator", "household_id", "created_by_member_id"),
    )
    transaction_id: Mapped[int] = mapped_column(sa.BigInteger)
    account_id: Mapped[int] = mapped_column(sa.BigInteger)
    currency_code: Mapped[str] = mapped_column(sa.Text)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    transaction_amount: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    direction: Mapped[str] = mapped_column(sa.Text)
    settled_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    exchange_rate: Mapped[Decimal | None] = mapped_column(sa.Numeric(30, 12))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    created_by_member_id: Mapped[int] = mapped_column(sa.BigInteger)
    method_code: Mapped[str | None] = mapped_column(sa.Text)
    external_reference: Mapped[str | None] = mapped_column(sa.Text)
    reverses_payment_id: Mapped[int | None] = mapped_column(sa.BigInteger)


class AccountLedgerEntry(Scoped, Base):
    __tablename__ = "account_ledger_entries"
    __table_args__ = (
        scoped_unique(), sa.UniqueConstraint("household_id", "id", "transaction_id"), sa.UniqueConstraint("household_id", "id", "account_id"),
        sa.ForeignKeyConstraint(["household_id", "transaction_id", "currency_code"], ["transactions.household_id", "transactions.id", "transactions.currency_code"]),
        sa.ForeignKeyConstraint(["household_id", "account_id", "currency_code"], ["accounts.household_id", "accounts.id", "accounts.currency_code"]),
        sa.ForeignKeyConstraint(["household_id", "payment_id", "transaction_id", "account_id", "currency_code"],
            ["transaction_payments.household_id", "transaction_payments.id", "transaction_payments.transaction_id", "transaction_payments.account_id", "transaction_payments.currency_code"]),
        scoped_fk("reverses_entry_id", "account_ledger_entries"),
        sa.CheckConstraint(finite("signed_amount", "<> 0"), name="ck_ledger_amount"),
        sa.CheckConstraint("reverses_entry_id IS NULL OR reverses_entry_id <> id", name="ck_ledger_not_self"),
        sa.Index("uq_ledger_payment", "household_id", "payment_id", unique=True, postgresql_where=sa.text("payment_id IS NOT NULL")),
        sa.Index("uq_ledger_reversal", "household_id", "reverses_entry_id", unique=True, postgresql_where=sa.text("reverses_entry_id IS NOT NULL")),
        sa.Index("ix_ledger_account_timeline", "household_id", "account_id", "posted_at", "id"),
        sa.Index("ix_ledger_transaction", "household_id", "transaction_id"),
    )
    transaction_id: Mapped[int] = mapped_column(sa.BigInteger)
    account_id: Mapped[int] = mapped_column(sa.BigInteger)
    currency_code: Mapped[str] = mapped_column(sa.Text)
    signed_amount: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    posted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    payment_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    reverses_entry_id: Mapped[int | None] = mapped_column(sa.BigInteger)


class IdempotencyRequest(Scoped, Base):
    __tablename__ = "idempotency_requests"
    __table_args__ = (scoped_unique(), scoped_fk("actor_member_id", "household_members"),
        sa.UniqueConstraint("household_id", "actor_member_id", "operation", "request_key"),
        sa.CheckConstraint("length(request_key) BETWEEN 1 AND 128 AND request_key COLLATE \"C\" ~ '^[!-~]+$'", name="ck_idempotency_key"),
        sa.CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="ck_idempotency_hash"),
        sa.CheckConstraint("response_status IN (200,201,204)", name="ck_idempotency_status"),
        sa.CheckConstraint("(response_status=204 AND response_body='null'::jsonb) OR (response_status IN (200,201) AND jsonb_typeof(response_body)='object')", name="ck_idempotency_response"))
    actor_member_id: Mapped[int] = mapped_column(sa.BigInteger)
    operation: Mapped[str] = mapped_column(sa.Text)
    request_key: Mapped[str] = mapped_column(sa.Text)
    request_hash: Mapped[str] = mapped_column(sa.String(64))
    response_status: Mapped[int] = mapped_column(sa.SmallInteger)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


# OPEN-09 PROPOSAL: single open account observation; retained manual matching.
class ReconciliationSession(Scoped, Base):
    __tablename__ = "reconciliation_sessions"
    __table_args__ = (
        scoped_unique(), sa.UniqueConstraint("household_id", "id", "account_id"),
        sa.UniqueConstraint("household_id", "id", "account_id", "currency_code"),
        sa.ForeignKeyConstraint(["household_id", "account_id", "currency_code"], ["accounts.household_id", "accounts.id", "accounts.currency_code"]),
        sa.ForeignKeyConstraint(["household_id", "previous_session_id", "account_id", "currency_code"], ["reconciliation_sessions.household_id", "reconciliation_sessions.id", "reconciliation_sessions.account_id", "reconciliation_sessions.currency_code"]),
        sa.ForeignKeyConstraint(["household_id", "cutoff_ledger_entry_id", "account_id"], ["account_ledger_entries.household_id", "account_ledger_entries.id", "account_ledger_entries.account_id"]),
        scoped_fk("opened_by_member_id", "household_members"), scoped_fk("closed_by_member_id", "household_members"),
        sa.CheckConstraint("state IN ('OPEN','CLOSED')", name="ck_reconciliation_state"),
        sa.CheckConstraint("(state='OPEN' AND closed_at IS NULL AND closed_by_member_id IS NULL) OR (state='CLOSED' AND closed_at IS NOT NULL AND closed_by_member_id IS NOT NULL)", name="ck_reconciliation_closed"),
        sa.CheckConstraint("previous_session_id IS NULL OR previous_session_id <> id", name="ck_reconciliation_prior"),
        sa.CheckConstraint("statement_source IN ('BANK_STATEMENT','CASH_COUNT')", name="ck_reconciliation_source"),
        sa.CheckConstraint("statement_reference IS NULL OR length(statement_reference)<=200", name="ck_reconciliation_reference"),
        sa.CheckConstraint("statement_balance NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)", name="ck_reconciliation_amount"),
        sa.Index("uq_reconciliation_open", "household_id", "account_id", unique=True, postgresql_where=sa.text("state='OPEN'")),
        sa.Index("ix_reconciliation_account", "household_id", "account_id", "id"),
    )
    account_id: Mapped[int] = mapped_column(sa.BigInteger)
    currency_code: Mapped[str] = mapped_column(sa.ForeignKey("currencies.code"))
    statement_date: Mapped[date] = mapped_column(sa.Date)
    statement_balance: Mapped[Decimal] = mapped_column(sa.Numeric(20, 6))
    state: Mapped[str] = mapped_column(sa.Text, server_default="OPEN")
    opened_by_member_id: Mapped[int] = mapped_column(sa.BigInteger)
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    statement_source: Mapped[str] = mapped_column(sa.Text)
    statement_reference: Mapped[str | None] = mapped_column(sa.Text)
    previous_session_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    closed_by_member_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    cutoff_ledger_entry_id: Mapped[int | None] = mapped_column(sa.BigInteger)


class ReconciliationMatch(Scoped, Base):
    __tablename__ = "reconciliation_matches"
    __table_args__ = (
        scoped_unique(),
        sa.ForeignKeyConstraint(["household_id", "session_id", "account_id"], ["reconciliation_sessions.household_id", "reconciliation_sessions.id", "reconciliation_sessions.account_id"]),
        sa.ForeignKeyConstraint(["household_id", "ledger_entry_id", "account_id"], ["account_ledger_entries.household_id", "account_ledger_entries.id", "account_ledger_entries.account_id"]),
        scoped_fk("matched_by_member_id", "household_members"), scoped_fk("unmatched_by_member_id", "household_members"),
        sa.CheckConstraint("(unmatched_at IS NULL) = (unmatched_by_member_id IS NULL)", name="ck_match_withdrawal"),
        sa.CheckConstraint("unmatched_at IS NULL OR unmatched_at >= matched_at", name="ck_match_time"),
        sa.Index("uq_reconciliation_active_match", "household_id", "ledger_entry_id", unique=True, postgresql_where=sa.text("unmatched_at IS NULL")),
        sa.Index("ix_reconciliation_matches_session", "household_id", "session_id", "id"),
    )
    session_id: Mapped[int] = mapped_column(sa.BigInteger)
    account_id: Mapped[int] = mapped_column(sa.BigInteger)
    ledger_entry_id: Mapped[int] = mapped_column(sa.BigInteger)
    matched_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    matched_by_member_id: Mapped[int] = mapped_column(sa.BigInteger)
    unmatched_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    unmatched_by_member_id: Mapped[int | None] = mapped_column(sa.BigInteger)
