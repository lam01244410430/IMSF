"""Real PostgreSQL DDL, tuple ownership, runtime privileges and retention."""
import asyncio
import os
import re

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from conftest import migrate, table_names


@pytest.fixture(scope="module")
def rehearsal_url():
    raw = os.environ.get("FINANCE_REHEARSAL_DATABASE_URL", "")
    name = make_url(raw).database or ""
    if (not re.fullmatch(r"p03_rehearsal_test_[a-z0-9_]+", name)
        or os.environ.get("P03_REHEARSAL_DATABASE") != name
        or name in {os.environ.get("P02_DISPOSABLE_DATABASE"), os.environ.get("P03_DISPOSABLE_DATABASE")}):
        pytest.fail("Refusing rehearsal DB: explicitly configure a separate disposable database")
    assert not asyncio.run(table_names(raw))
    return raw


def test_core_upgrade_from_empty_and_preserves_populated_identity_and_empty_settings(rehearsal_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", rehearsal_url)
    migrate("head")
    assert {"currencies", "accounts", "transaction_items", "transaction_payments", "account_ledger_entries", "idempotency_requests"} <= asyncio.run(table_names(rehearsal_url))
    migrate("000000000003", downgrade=True)  # Empty finance rehearsal only.
    async def populate():
        engine = create_async_engine(rehearsal_url, poolclass=NullPool)
        async with engine.begin() as c:
            for sql in [
                "INSERT INTO users(id,email,email_key,password_hash,state) VALUES (1,'identity@example.test','identity@example.test','test-only','ACTIVE')",
                "INSERT INTO households(id,name) VALUES (1,'Retained identity')",
                "INSERT INTO household_settings(household_id) VALUES (1)",
                "INSERT INTO household_members(id,household_id,user_id,role_id) SELECT 1,1,1,id FROM roles WHERE code='OWNER'",
                "INSERT INTO auth_sessions(id,user_id,expires_at,csrf_digest) VALUES (1,1,now()+interval '1 day',repeat('a',64))",
            ]:
                await c.execute(text(sql))
        await engine.dispose()
    async def snapshot():
        engine = create_async_engine(rehearsal_url, poolclass=NullPool)
        async with engine.connect() as c:
            result = {t: (await c.execute(text(f"SELECT to_jsonb(t) FROM {t} t ORDER BY 1::text"))).scalars().all()
                      for t in ("users", "households", "household_members", "auth_sessions", "household_settings")}
        await engine.dispose()
        return result
    asyncio.run(populate())
    before = asyncio.run(snapshot())
    migrate("head")
    assert asyncio.run(snapshot()) == before
    assert before["household_settings"] == [{"household_id": 1, "values": {}}]


def test_metadata_matches_schema(finance_database_urls):
    from app.db.base import Base
    from app.finance.infrastructure import models  # noqa: F401
    async def run():
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        async with engine.connect() as c:
            assert await c.scalar(text("SELECT version_num FROM alembic_version")) == "000000000004"
            differences = await c.run_sync(lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata))
            assert differences == []
            assert (await c.execute(text("SELECT code,minor_units FROM currencies ORDER BY code"))).all() == [
                ("BHD", 3), ("EUR", 2), ("JPY", 0), ("USD", 2), ("VND", 0)]
        await engine.dispose()
    asyncio.run(run())


async def raw_seed(db, f):
    """Controlled test rows only; deliberately create POSTED data to probe guards."""
    params = {"hid": f.hid, "other": f.other_hid, "mid": f.actors["OWNER"].member_id}
    aid = await db.scalar(text("INSERT INTO accounts(household_id,name,currency_code) VALUES (:hid,'Cash','USD') RETURNING id"), params)
    bid = await db.scalar(text("INSERT INTO accounts(household_id,name,currency_code) VALUES (:hid,'Bank','USD') RETURNING id"), params)
    foreign = await db.scalar(text("INSERT INTO accounts(household_id,name,currency_code) VALUES (:other,'Other','USD') RETURNING id"), params)
    tids = []
    for _ in range(2):
        tid = await db.scalar(text("""INSERT INTO transactions(household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id)
            VALUES (:hid,'EXPENSE','DRAFT',now(),'USD',1,:mid) RETURNING id"""), params)
        tids.append(tid)
    params |= {"aid": aid, "bid": bid, "foreign": foreign, "tid": tids[0], "tid2": tids[1]}
    iid = await db.scalar(text("INSERT INTO transaction_items(household_id,transaction_id,line_no,description,quantity,net_amount) VALUES (:hid,:tid,1,'Test',1,1) RETURNING id"), params)
    await db.execute(text("UPDATE transactions SET status='POSTED',posted_at=now() WHERE household_id=:hid"), params)
    pid = await db.scalar(text("""INSERT INTO transaction_payments(household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id)
        VALUES (:hid,:tid,:aid,'USD',1,1,'OUT',now(),:mid) RETURNING id"""), params)
    params |= {"iid": iid, "pid": pid}
    lid = await db.scalar(text("""INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,payment_id)
        VALUES (:hid,:tid,:aid,'USD',-1,now(),:pid) RETURNING id"""), params)
    params["lid"] = lid
    params["pid2"] = await db.scalar(text("""INSERT INTO transaction_payments(household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id)
        VALUES (:hid,:tid,:aid,'USD',1,1,'OUT',now(),:mid) RETURNING id"""), params)
    await db.execute(text("INSERT INTO audit_logs(household_id,actor_member_id,request_id,action,target_type) VALUES (:hid,:mid,'guard-test','TEST','test')"), params)
    return params


@pytest.mark.parametrize("sql,state", [
    ("INSERT INTO transactions(household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id) VALUES (:other,'EXPENSE','DRAFT',now(),'USD',1,:mid)", "23503"),
    ("INSERT INTO transaction_payments(household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id) VALUES (:hid,:tid,:foreign,'USD',1,1,'OUT',now(),:mid)", "23503"),
    ("INSERT INTO transaction_payments(household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id) VALUES (:hid,:tid,:aid,'JPY',1,1,'OUT',now(),:mid)", "23503"),
    ("INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,payment_id) VALUES (:hid,:tid2,:aid,'USD',-1,now(),:pid2)", "23503"),
    ("INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,payment_id) VALUES (:hid,:tid,:bid,'USD',-1,now(),:pid2)", "23503"),
    ("UPDATE account_ledger_entries SET signed_amount=-2 WHERE id=:lid", "42501"),
    ("DELETE FROM account_ledger_entries WHERE id=:lid", "42501"),
    ("TRUNCATE account_ledger_entries", "42501"),
    ("UPDATE transactions SET total_amount=2 WHERE id=:tid", "55000"),
    ("UPDATE transaction_items SET net_amount=2 WHERE id=:iid", "55000"),
    ("INSERT INTO transaction_items(household_id,transaction_id,line_no,description,quantity,net_amount) VALUES (:hid,:tid,2,'Late',1,1)", "55000"),
    ("UPDATE transaction_payments SET amount=2 WHERE id=:pid", "55000"),
    ("DELETE FROM transactions WHERE id=:tid", "42501"),
    ("DELETE FROM transaction_items WHERE id=:iid", "42501"),
    ("DELETE FROM transaction_payments WHERE id=:pid", "42501"),
    ("UPDATE audit_logs SET action='CHANGED' WHERE household_id=:hid", "42501"),
    ("DELETE FROM audit_logs WHERE household_id=:hid", "42501"),
    ("TRUNCATE audit_logs", "42501"),
    ("ALTER TABLE account_ledger_entries DISABLE TRIGGER ALL", "42501"),
    ("UPDATE accounts SET currency_code='JPY' WHERE id=:aid", "55000"),
    ("UPDATE currencies SET minor_units=0 WHERE code='USD'", "42501"),
])
def test_composite_fks_runtime_immutability_and_retained_rows(f, sql, state):
    async def run():
        async with f.db() as db, db.begin():
            p = await raw_seed(db, f)
            with pytest.raises(DBAPIError) as failure:
                async with db.begin_nested():
                    await db.execute(text(sql), p)
            assert failure.value.orig.sqlstate == state
            assert await db.scalar(text("SELECT total_amount FROM transactions WHERE id=:tid"), p) == 1
            assert await db.scalar(text("SELECT signed_amount FROM account_ledger_entries WHERE id=:lid"), p) == -1
            # Fixture rollback, no teardown deletes, guards stay enabled.
            await db.rollback()
    asyncio.run(run())


def test_guards_still_reject_accidentally_broadened_runtime_grants(f, finance_database_urls):
    """Owner temporarily broadens DML inside rollback; triggers remain the backstop."""
    async def run():
        # Use the owner connection with SET ROLE only after validating configuration.
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        role = make_url(finance_database_urls[1]).username
        async with engine.connect() as c:
            outer = await c.begin()
            qrole = c.dialect.identifier_preparer.quote(role)
            await c.execute(text(f"GRANT UPDATE,DELETE,TRUNCATE ON account_ledger_entries,transactions,transaction_items,transaction_payments,audit_logs TO {qrole}"))
            await c.execute(text(f"SET LOCAL ROLE {qrole}"))
            params = await raw_seed(c, f)
            for statement in (
                "UPDATE account_ledger_entries SET signed_amount=-2 WHERE id=:lid",
                "DELETE FROM account_ledger_entries WHERE id=:lid",
                "DELETE FROM transactions WHERE id=:tid",
                "DELETE FROM transaction_items WHERE id=:iid",
                "DELETE FROM transaction_payments WHERE id=:pid",
                "UPDATE audit_logs SET action='CHANGED' WHERE household_id=:hid",
                "DELETE FROM audit_logs WHERE household_id=:hid",
            ):
                with pytest.raises(DBAPIError) as failure:
                    async with c.begin_nested():
                        await c.execute(text(statement), params)
                assert failure.value.orig.sqlstate == "55000"
            for table in ("account_ledger_entries", "transactions", "transaction_items", "transaction_payments", "audit_logs"):
                with pytest.raises(DBAPIError) as failure:
                    async with c.begin_nested():
                        await c.execute(text(f"TRUNCATE {table} CASCADE"))
                assert failure.value.orig.sqlstate in {"55000", "42501"}
            await outer.rollback()
        await engine.dispose()
    asyncio.run(run())


def test_downgrade_refuses_populated_finance(rehearsal_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", rehearsal_url)
    async def populate():
        engine = create_async_engine(rehearsal_url, poolclass=NullPool)
        async with engine.begin() as c:
            await c.execute(text("INSERT INTO accounts(household_id,name,currency_code) VALUES (1,'Retain','USD')"))
        await engine.dispose()
    asyncio.run(populate())
    with pytest.raises(DBAPIError) as failure:
        migrate("000000000003", downgrade=True)
    assert failure.value.orig.sqlstate == "55000"
    assert "accounts" in asyncio.run(table_names(rehearsal_url))


def test_incomplete_idempotency_reservation_cannot_commit(f):
    async def run():
        with pytest.raises(DBAPIError) as failure:
            async with f.db() as db, db.begin():
                await db.execute(text("""INSERT INTO idempotency_requests(household_id,actor_member_id,operation,request_key,request_hash,response_status,response_body)
                    VALUES (:hid,:mid,'test:incomplete','incomplete',repeat('a',64),200,jsonb_build_object('_pending',true))"""),
                    {"hid": f.hid, "mid": f.actors["OWNER"].member_id})
        assert failure.value.orig.sqlstate == "55000"
        async with f.db() as db:
            assert await db.scalar(text("SELECT count(*) FROM idempotency_requests WHERE household_id=:hid"), {"hid": f.hid}) == 0
    asyncio.run(run())
