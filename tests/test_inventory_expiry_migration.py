"""Frozen revision 8: disposable PostgreSQL preservation, constraints and grants."""
import asyncio
import importlib.util
import json
import os
import re
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from conftest import migrate, table_names
from test_inventory_expiry import persist_alert
from test_inventory_expiry_jobs import INSERT_JOB, PAYLOAD
from test_inventory_lots import product, receipt
from test_finance_transactions import query


def revision():
    path = "migrations/versions/000000000008_inventory_expiry.py"
    assert os.path.isfile(path), "Step 2 additive revision 8 is required"
    spec = importlib.util.spec_from_file_location("expiry_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def expiry_rehearsal_url():
    raw = os.environ.get("EXPIRY_REHEARSAL_DATABASE_URL", "")
    url = make_url(raw)
    name = url.database or ""
    if (url.drivername != "postgresql+psycopg" or not re.fullmatch(r"p05_rehearsal_test_[a-z0-9_]+", name)
        or os.environ.get("P05_REHEARSAL_DATABASE") != name
        or name in {os.environ.get(k) for k in ["P02_DISPOSABLE_DATABASE", "P03_DISPOSABLE_DATABASE", "P03_REHEARSAL_DATABASE", "P04_REHEARSAL_DATABASE"]}):
        pytest.fail("Require separate explicitly configured fresh expiry rehearsal database")
    assert not asyncio.run(table_names(raw))
    return raw


def test_upgrade_empty_and_populated_revision_7_and_empty_downgrade_preserve_all_rows(expiry_rehearsal_url, monkeypatch):
    raw = expiry_rehearsal_url
    monkeypatch.setenv("DATABASE_URL", raw)
    revision()
    migrate("000000000007")
    async def source_grants():
        engine = create_async_engine(raw, poolclass=NullPool)
        try:
            async with engine.connect() as db:
                return list((await db.execute(text("SELECT relname,relacl::text FROM pg_class WHERE relnamespace='public'::regnamespace AND relname IN ('households','household_settings','products','inventory_lots') ORDER BY relname"))).all())
        finally:
            await engine.dispose()
    initial_grants = asyncio.run(source_grants())
    migrate("000000000008")
    assert {"scheduled_jobs", "expiration_alerts"} <= asyncio.run(table_names(raw))
    migrate("000000000007", downgrade=True)
    assert asyncio.run(source_grants()) == initial_grants

    async def seed():
        engine = create_async_engine(raw, poolclass=NullPool)
        try:
            async with engine.begin() as db:
                worker = db.dialect.identifier_preparer.quote(os.environ["INVENTORY_EXPIRY_WORKER_ROLE"])
                await db.execute(text(f"GRANT SELECT ON products TO {worker}"))
                for statement in [
                    "INSERT INTO users(id,email,email_key,password_hash,state) VALUES(1,'expiry@example.test','expiry@example.test','unused','ACTIVE')",
                    "INSERT INTO households(id,name) VALUES(1,'Retained revision 7')",
                    "INSERT INTO household_settings(household_id,values) VALUES(1,'{\"timezone\":\"Asia/Ho_Chi_Minh\"}')",
                    "INSERT INTO household_members(id,household_id,user_id,role_id) SELECT 1,1,1,id FROM roles WHERE code='OWNER'",
                    "INSERT INTO products(id,household_id,name,base_unit_id) SELECT 1,1,'Retained rice',id FROM measurement_units WHERE code='g'",
                    "INSERT INTO inventory_lots(id,household_id,product_id,source_kind,received_at,received_quantity,remaining_quantity,expires_on) VALUES(1,1,1,'GIFT',now(),5,5,'2026-11-12')",
                    "INSERT INTO inventory_movements(id,household_id,lot_id,kind,quantity_delta,occurred_at,actor_member_id) VALUES(1,1,1,'RECEIPT',5,now(),1)",
                    "INSERT INTO accounts(id,household_id,name,currency_code) VALUES(1,1,'Cash','USD')",
                    "INSERT INTO transactions(id,household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id) VALUES(1,1,'EXPENSE','DRAFT',now(),'USD',1,1)",
                    "INSERT INTO transaction_items(household_id,transaction_id,line_no,description,quantity,net_amount) VALUES(1,1,1,'Retained draft',1,1)",
                ]:
                    await db.execute(text(statement))
        finally:
            await engine.dispose()
    asyncio.run(seed())

    async def snapshot():
        engine = create_async_engine(raw, poolclass=NullPool)
        try:
            async with engine.connect() as db:
                tables = (await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version','scheduled_jobs','expiration_alerts') ORDER BY tablename"))).scalars().all()
                return {t: (await db.execute(text(f"SELECT to_jsonb(t)::text FROM {t} t ORDER BY to_jsonb(t)::text"))).scalars().all() for t in tables}
        finally:
            await engine.dispose()
    before = asyncio.run(snapshot())
    prior_grants = asyncio.run(source_grants())
    migrate("000000000008")
    assert asyncio.run(snapshot()) == before
    migrate("000000000007", downgrade=True)
    assert asyncio.run(snapshot()) == before
    assert "expiration_alerts" not in asyncio.run(table_names(raw))
    assert asyncio.run(source_grants()) == prior_grants
    migrate("000000000008")
    assert asyncio.run(snapshot()) == before


@pytest.mark.parametrize("with_alert,state", [(False, "READY"), (False, "FAILED"), (False, "SUCCEEDED"), (True, "READY")])
def test_expiry_downgrade_refuses_any_history_with_55000_and_preserves_schema_grants_rows(f, finance_database_urls, with_alert, state):
    async def run():
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        try:
            async with engine.connect() as db:
                outer = await db.begin()
                values = {"hid": f.hid, "key": "retained", "payload": json.dumps(PAYLOAD)}
                jid = (await db.execute(text(INSERT_JOB), values)).mappings().one()["id"]
                if state != "READY":
                    await db.execute(text("UPDATE scheduled_jobs SET state='RUNNING',attempt_count=1,lease_token='fixture',lease_until=now()+interval '1 minute' WHERE id=:jid"), {"jid": jid})
                    await db.execute(text("UPDATE scheduled_jobs SET state=:state,completed_at=now(),lease_until=NULL,lease_token=NULL WHERE id=:jid"), {"jid": jid, "state": state})
                if with_alert:
                    # This test already has a retained job; real scoped lot inserted via writer outside.
                    await db.execute(text("INSERT INTO expiration_alerts(household_id,lot_id,alert_kind,local_date,expires_on_snapshot,timezone,job_id) VALUES(:hid,:lid,'WARNING','2026-11-11','2026-11-12','Asia/Ho_Chi_Minh',:jid)"), {"hid": f.hid, "lid": lot["id"], "jid": jid})
                async def capture():
                    return tuple([list((await db.execute(text(s))).all()) for s in [
                        "SELECT to_jsonb(t)::text FROM scheduled_jobs t ORDER BY id",
                        "SELECT to_jsonb(t)::text FROM expiration_alerts t ORDER BY id",
                        "SELECT table_name,grantee,privilege_type FROM information_schema.role_table_grants WHERE table_name IN ('scheduled_jobs','expiration_alerts') ORDER BY 1,2,3",
                        "SELECT indexname,indexdef FROM pg_indexes WHERE tablename IN ('scheduled_jobs','expiration_alerts','inventory_lots') ORDER BY indexname",
                    ]])
                before = await capture()
                def invoke(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        revision().downgrade()
                with pytest.raises(DBAPIError) as error:
                    async with db.begin_nested():
                        await db.run_sync(invoke)
                assert error.value.orig.sqlstate == "55000"
                assert await capture() == before
                await outer.rollback()
        finally:
            await engine.dispose()
    lot = receipt(f, product(f), expires_on="2026-11-12").json() if with_alert else None
    asyncio.run(run())


def test_alert_and_job_composite_fks_unique_keys_and_timezone_enforce_scope(f):
    lot = receipt(f, product(f), expires_on="2026-11-12").json()
    a = persist_alert(f, lot)
    async def run():
        async with f.db() as db, db.begin():
            for values, state in [({}, "23505"), ({"hid": f.other_hid}, "23503"),
                ({"jid": 9223372036854775807, "kind": "EXPIRED"}, "23503"), ({"kind": "UNKNOWN"}, "23514"),
                ({"zone": "No/Zone"}, "23514"), ({"zone": ""}, "23514")]:
                params = {"hid": f.hid, "lid": lot["id"], "jid": a["job_id"], "kind": "WARNING", "zone": "Asia/Ho_Chi_Minh"} | values
                with pytest.raises(DBAPIError) as error:
                    async with db.begin_nested():
                        await db.execute(text("""INSERT INTO expiration_alerts(household_id,lot_id,alert_kind,local_date,expires_on_snapshot,timezone,job_id)
                            VALUES(:hid,:lid,:kind,'2026-11-11','2026-11-12',:zone,:jid)"""), params)
                assert error.value.orig.sqlstate == state
            # Foreign job with a real local lot exercises job FK independently of lot FK.
            foreign = (await db.execute(text(INSERT_JOB), {"hid": f.other_hid, "key": "foreign", "payload": json.dumps(PAYLOAD)})).mappings().one()
            with pytest.raises(DBAPIError) as error:
                async with db.begin_nested():
                    await db.execute(text("INSERT INTO expiration_alerts(household_id,lot_id,alert_kind,local_date,expires_on_snapshot,timezone,job_id) VALUES(:hid,:lid,'EXPIRED','2026-11-11','2026-11-10','Asia/Ho_Chi_Minh',:jid)"), {"hid": f.hid, "lid": lot["id"], "jid": foreign["id"]})
            assert error.value.orig.sqlstate == "23503"
            await db.rollback()
    asyncio.run(run())


def test_expiry_runtime_and_worker_grants_fail_closed(f, finance_database_urls, monkeypatch):
    async def run():
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        try:
            async with engine.connect() as db:
                role = os.environ["FINANCE_RUNTIME_ROLE"]
                worker = os.environ["INVENTORY_EXPIRY_WORKER_ROLE"]
                for target in [role, worker]:
                    for table in ["expiration_alerts", "scheduled_jobs"]:
                        assert await db.scalar(text("SELECT has_table_privilege(:r,:t,'SELECT') AND has_table_privilege(:r,:t,'INSERT') AND NOT has_table_privilege(:r,:t,'UPDATE') AND NOT has_table_privilege(:r,:t,'DELETE') AND NOT has_table_privilege(:r,:t,'TRUNCATE')"), {"r": target, "t": table})
                    assert await db.scalar(text("SELECT has_column_privilege(:r,'scheduled_jobs','state','UPDATE') AND NOT has_column_privilege(:r,'scheduled_jobs','payload','UPDATE')"), {"r": target})
                for table in ["inventory_lots", "products", "inventory_movements", "transactions", "transaction_items", "transaction_payments", "account_ledger_entries"]:
                    for privilege in ["INSERT", "UPDATE", "DELETE", "TRUNCATE"]:
                        assert not await db.scalar(text("SELECT has_table_privilege(:r,:t,:p)"), {"r": worker, "t": table, "p": privilege})
                for variable in ["FINANCE_RUNTIME_ROLE", "INVENTORY_EXPIRY_WORKER_ROLE"]:
                    original = os.environ[variable]
                    for invalid in [None, "p05_missing_role", make_url(finance_database_urls[0]).username]:
                        if invalid is None:
                            monkeypatch.delenv(variable)
                        else:
                            monkeypatch.setenv(variable, invalid)
                        def preflight(sync):
                            with Operations.context(MigrationContext.configure(sync)):
                                revision()._roles()
                        with pytest.raises(RuntimeError, match=variable):
                            await db.run_sync(preflight)
                    monkeypatch.setenv(variable, original)
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_expiry_history_rejects_update_delete_truncate_and_frozen_job_fields_even_with_broadened_grants(f, finance_database_urls):
    alert = persist_alert(f, receipt(f, product(f), expires_on="2026-11-12").json())
    async def run():
        # Ordinary grants deny history mutation; no DELETE cleanup.
        async with f.db() as db, db.begin():
            for statement in ["UPDATE expiration_alerts SET id=id", "DELETE FROM expiration_alerts", "TRUNCATE expiration_alerts", "DELETE FROM scheduled_jobs", "TRUNCATE scheduled_jobs CASCADE", "UPDATE scheduled_jobs SET payload=payload"]:
                with pytest.raises(DBAPIError) as error:
                    async with db.begin_nested():
                        await db.execute(text(statement))
                assert error.value.orig.sqlstate == "42501"
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        try:
            async with engine.connect() as db:
                outer = await db.begin()
                role = db.dialect.identifier_preparer.quote(os.environ["FINANCE_RUNTIME_ROLE"])
                await db.execute(text(f"GRANT UPDATE,DELETE,TRUNCATE ON expiration_alerts,scheduled_jobs TO {role}"))
                await db.execute(text(f"SET LOCAL ROLE {role}"))
                for statement in ["UPDATE expiration_alerts SET timezone='UTC' WHERE id=:aid", "DELETE FROM expiration_alerts WHERE id=:aid", "TRUNCATE expiration_alerts", "DELETE FROM scheduled_jobs WHERE id=:jid", "TRUNCATE scheduled_jobs CASCADE", "UPDATE scheduled_jobs SET payload='{}' WHERE id=:jid", "UPDATE scheduled_jobs SET job_key='changed' WHERE id=:jid", "UPDATE scheduled_jobs SET run_after=now()+interval '1 day' WHERE id=:jid", "UPDATE scheduled_jobs SET household_id=:other WHERE id=:jid"]:
                    with pytest.raises(DBAPIError) as error:
                        async with db.begin_nested():
                            await db.execute(text(statement), {"aid": alert["id"], "jid": alert["job_id"], "other": f.other_hid})
                    assert error.value.orig.sqlstate == "55000", statement
                await outer.rollback()
        finally:
            await engine.dispose()
    asyncio.run(run())
    assert len(query(f, "SELECT id FROM expiration_alerts WHERE household_id=:hid")) == 1


@pytest.mark.parametrize("grant_mode", ["noinherit_writer_membership", "direct_finance_column_write"])
def test_worker_preflight_rejects_set_role_paths_and_all_existing_business_writes(finance_database_urls, grant_mode):
    async def run():
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        try:
            async with engine.connect() as db:
                outer = await db.begin()
                quote = db.dialect.identifier_preparer.quote
                worker = quote(os.environ["INVENTORY_EXPIRY_WORKER_ROLE"])
                if grant_mode == "noinherit_writer_membership":
                    writer = quote("p05_probe_writer")
                    await db.execute(text(f"CREATE ROLE {writer} NOLOGIN"))
                    await db.execute(text(f"GRANT INSERT ON inventory_lots TO {writer}"))
                    await db.execute(text(f"ALTER ROLE {worker} NOINHERIT"))
                    await db.execute(text(f"GRANT {writer} TO {worker} WITH INHERIT FALSE, SET TRUE"))
                    assert not await db.scalar(text("SELECT has_table_privilege(:r,'inventory_lots','INSERT')"), {"r": os.environ["INVENTORY_EXPIRY_WORKER_ROLE"]})
                else:
                    await db.execute(text(f"GRANT UPDATE(state,closed_at,closed_by_member_id) ON reconciliation_sessions TO {worker}"))
                def invoke(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        revision()._roles()
                with pytest.raises(RuntimeError, match="INVENTORY_EXPIRY_WORKER_ROLE"):
                    await db.run_sync(invoke)
                await outer.rollback()
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_real_worker_credential_has_only_approved_reads_and_persistence(f, finance_database_urls):
    raw = os.environ.get("INVENTORY_EXPIRY_WORKER_DATABASE_URL", "")
    worker_url, runtime_url = make_url(raw), make_url(finance_database_urls[1])
    if (worker_url.drivername != "postgresql+psycopg"
        or (worker_url.host, worker_url.port, worker_url.database) != (runtime_url.host, runtime_url.port, runtime_url.database)
        or worker_url.username != os.environ.get("INVENTORY_EXPIRY_WORKER_ROLE")
        or not re.fullmatch(r"p03_finance_test_[a-z0-9_]+", worker_url.database or "")):
        pytest.fail("Require separately configured worker credential on the guarded disposable finance database")
    async def run():
        engine = create_async_engine(raw, poolclass=NullPool)
        try:
            async with engine.connect() as db:
                outer = await db.begin()
                assert await db.scalar(text("SELECT current_user")) == worker_url.username
                for table in ["households", "household_settings", "products", "inventory_lots", "expiration_alerts", "scheduled_jobs"]:
                    await db.execute(text(f"SELECT * FROM {table} LIMIT 1"))
                row = (await db.execute(text(INSERT_JOB), {"hid": f.hid, "key": "worker-storage-contract", "payload": json.dumps(PAYLOAD)})).mappings().one()
                assert row["state"] == "READY"
                runtime = db.dialect.identifier_preparer.quote(runtime_url.username)
                for statement in [f"SET ROLE {runtime}", "UPDATE inventory_lots SET expires_on=expires_on",
                    "INSERT INTO inventory_movements DEFAULT VALUES", "UPDATE reconciliation_sessions SET state=state",
                    "UPDATE transactions SET status=status", "DELETE FROM scheduled_jobs", "TRUNCATE expiration_alerts"]:
                    with pytest.raises(DBAPIError) as error:
                        async with db.begin_nested():
                            await db.execute(text(statement))
                    assert error.value.orig.sqlstate == "42501", statement
                await outer.rollback()
        finally:
            await engine.dispose()
    asyncio.run(run())
