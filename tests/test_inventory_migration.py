"""Frozen revision 7, runtime guards and real retained PostgreSQL evidence."""

import asyncio
import importlib.util
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
from test_inventory_lots import product, receipt, purchase
from test_finance_transactions import query


@pytest.fixture(scope="module")
def inventory_rehearsal_url():
    raw = os.environ.get("INVENTORY_REHEARSAL_DATABASE_URL", "")
    name = make_url(raw).database or ""
    if (
        not re.fullmatch(r"p04_rehearsal_test_[a-z0-9_]+", name)
        or os.environ.get("P04_REHEARSAL_DATABASE") != name
        or name
        in {
            os.environ.get("P02_DISPOSABLE_DATABASE"),
            os.environ.get("P03_DISPOSABLE_DATABASE"),
            os.environ.get("P03_REHEARSAL_DATABASE"),
        }
    ):
        pytest.fail(
            "Refusing inventory rehearsal DB: require separate explicitly configured fresh disposable DB"
        )
    assert not asyncio.run(table_names(raw))
    return raw


def test_upgrade_empty_and_populated_revision_6_preserves_finance(
    inventory_rehearsal_url, monkeypatch
):
    raw = inventory_rehearsal_url
    monkeypatch.setenv("DATABASE_URL", raw)
    migrate("head")
    assert "inventory_lots" in asyncio.run(table_names(raw))
    migrate("000000000006", downgrade=True)

    async def seed():
        engine = create_async_engine(raw, poolclass=NullPool)
        async with engine.begin() as db:
            for statement in [
                "INSERT INTO users(id,email,email_key,password_hash,state) VALUES (1,'p04@example.test','p04@example.test','unused','ACTIVE')",
                "INSERT INTO households(id,name) VALUES (1,'Retained revision 6')",
                "INSERT INTO household_settings(household_id) VALUES (1)",
                "INSERT INTO household_members(id,household_id,user_id,role_id) SELECT 1,1,1,id FROM roles WHERE code='OWNER'",
                "INSERT INTO accounts(id,household_id,name,currency_code) VALUES (1,1,'Cash','USD')",
                "INSERT INTO transactions(id,household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id,posted_at,original_transaction_id,reversal_reason) VALUES (1,1,'EXPENSE','DRAFT',now(),'USD',1,1,NULL,NULL,NULL),(2,1,'EXPENSE','DRAFT',now(),'USD',1,1,NULL,NULL,NULL)",
                "INSERT INTO transaction_items(household_id,transaction_id,line_no,description,quantity,net_amount) VALUES (1,1,1,'Draft',1,1),(1,2,1,'Posted purchase',1,1)",
                "UPDATE transactions SET status='POSTED',posted_at=now() WHERE id=2",
                "INSERT INTO transactions(id,household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id,posted_at,original_transaction_id,reversal_reason) VALUES (3,1,'REVERSAL','POSTED',now(),'USD',1,1,now(),2,'Correct')",
                "INSERT INTO transaction_payments(id,household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id) VALUES (1,1,2,1,'USD',1,1,'OUT',now(),1)",
                "INSERT INTO account_ledger_entries(id,household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,payment_id) VALUES (1,1,2,1,'USD',-1,now(),1)",
                "INSERT INTO transaction_payments(id,household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id,reverses_payment_id) VALUES (2,1,3,1,'USD',1,1,'IN',now(),1,1)",
                "INSERT INTO account_ledger_entries(id,household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,payment_id,reverses_entry_id) VALUES (2,1,3,1,'USD',1,now(),2,1)",
                "INSERT INTO reconciliation_sessions(id,household_id,account_id,currency_code,statement_date,statement_balance,opened_by_member_id,statement_source,cutoff_ledger_entry_id) VALUES (1,1,1,'USD',current_date,0,1,'CASH_COUNT',2)",
                "INSERT INTO reconciliation_matches(household_id,session_id,account_id,ledger_entry_id,matched_by_member_id) VALUES (1,1,1,1,1),(1,1,1,2,1)",
                "UPDATE reconciliation_sessions SET state='CLOSED',closed_at=now(),closed_by_member_id=1 WHERE id=1",
            ]:
                await db.execute(text(statement))
        await engine.dispose()

    asyncio.run(seed())

    async def snapshot():
        engine = create_async_engine(raw, poolclass=NullPool)
        async with engine.connect() as db:
            tables = [
                "users",
                "households",
                "household_members",
                "household_settings",
                "accounts",
                "transactions",
                "transaction_items",
                "transaction_payments",
                "account_ledger_entries",
                "reconciliation_sessions",
                "reconciliation_matches",
            ]
            results = {
                t: (
                    await db.execute(
                        text(
                            f"SELECT (to_jsonb(t) - 'product_id' - 'base_quantity')::text FROM {t} t ORDER BY id"
                            if t != "household_settings"
                            else f"SELECT to_jsonb(t)::text FROM {t} t"
                        )
                    )
                )
                .scalars()
                .all()
                for t in tables
            }
        await engine.dispose()
        return results

    before = asyncio.run(snapshot())
    migrate("head")
    assert asyncio.run(snapshot()) == before


def test_runtime_history_is_append_only_and_projection_guard(f):
    p = product(f)
    lot = receipt(f, p).json()

    async def run():
        async with f.db() as db, db.begin():
            for table in [
                "inventory_movements",
                "inventory_adjustments",
                "consumption_records",
                "disposal_records",
                "recipe_cooking_history",
                "refund_inventory_links",
            ]:
                for operation in [
                    f"UPDATE {table} SET id=id",
                    f"DELETE FROM {table}",
                    f"TRUNCATE {table} CASCADE",
                ]:
                    with pytest.raises(DBAPIError) as error:
                        async with db.begin_nested():
                            await db.execute(text(operation))
                    assert error.value.orig.sqlstate in {"42501", "55000"}
            for table in [
                "inventory_lots",
                "products",
                "product_categories",
                "recipe_ingredients",
                "recipes",
            ]:
                for operation in [f"DELETE FROM {table}", f"TRUNCATE {table} CASCADE"]:
                    with pytest.raises(DBAPIError) as error:
                        async with db.begin_nested():
                            await db.execute(text(operation))
                    assert error.value.orig.sqlstate in {"42501", "55000"}
        with pytest.raises(DBAPIError) as error:
            async with f.db() as db, db.begin():
                await db.execute(
                    text(
                        "UPDATE inventory_lots SET remaining_quantity=3 WHERE household_id=:hid AND id=:lid"
                    ),
                    {"hid": f.hid, "lid": lot["id"]},
                )
        assert error.value.orig.sqlstate == "55000"

    asyncio.run(run())
    assert (
        query(
            f, "SELECT remaining_quantity FROM inventory_lots WHERE household_id=:hid"
        )[0]["remaining_quantity"]
        == 5
    )


def test_base_unit_and_lot_cost_frozen_after_history(f):
    p = product(f)
    lot = receipt(f, p, cost_currency="USD", unit_cost="0.123456789012").json()
    kg = next(
        u["id"]
        for u in f.request("GET", "/measurement-units").json()["items"]
        if u["code"] == "kg"
    )
    assert (
        f.request(
            "PATCH", f"/products/{p['id']}", json={"base_unit_id": kg}
        ).status_code
        == 409
    )

    async def run():
        for statement, params in [
            (
                "UPDATE products SET base_unit_id=:unit WHERE household_id=:hid AND id=:pid",
                {"unit": kg, "pid": p["id"]},
            ),
            (
                "UPDATE inventory_lots SET unit_cost=1 WHERE household_id=:hid AND id=:lid",
                {"lid": lot["id"]},
            ),
            (
                "UPDATE inventory_lots SET received_quantity=6 WHERE household_id=:hid AND id=:lid",
                {"lid": lot["id"]},
            ),
            ("UPDATE measurement_units SET code='changed'", {}),
        ]:
            with pytest.raises(DBAPIError) as error:
                async with f.db() as db, db.begin():
                    await db.execute(text(statement), params | {"hid": f.hid})
            assert error.value.orig.sqlstate in {"42501", "55000"}

    asyncio.run(run())


def test_raw_sql_composite_ownership_and_source_product_fks(f):
    p = product(f)
    tx = purchase(f, p)
    other = product(f, name="Different")

    async def run():
        probes = [
            (
                "INSERT INTO products(household_id,name,base_unit_id,category_id) VALUES (:foreign,'Wrong',:unit,:cid)",
                "23503",
            ),
            (
                "INSERT INTO inventory_lots(household_id,product_id,source_kind,received_at,received_quantity,remaining_quantity,purchase_item_id) VALUES (:hid,:wrong,'PURCHASE',now(),1,1,:iid)",
                "23503",
            ),
            (
                "INSERT INTO inventory_lots(household_id,product_id,source_kind,received_at,received_quantity,remaining_quantity) VALUES (:foreign,:pid,'GIFT',now(),1,1)",
                "23503",
            ),
        ]
        async with f.db() as db, db.begin():
            cid = await db.scalar(
                text(
                    "INSERT INTO product_categories(household_id,name) VALUES (:hid,'Scoped') RETURNING id"
                ),
                {"hid": f.hid},
            )
            params = {
                "hid": f.hid,
                "foreign": f.other_hid,
                "pid": p["id"],
                "wrong": other["id"],
                "unit": p["base_unit_id"],
                "iid": tx["items"][0]["id"],
                "cid": cid,
            }
            for statement, state in probes:
                with pytest.raises(DBAPIError) as error:
                    async with db.begin_nested():
                        await db.execute(text(statement), params)
                assert error.value.orig.sqlstate == state
            await db.rollback()

    asyncio.run(run())


def test_inventory_downgrade_refuses_history_with_55000(f, finance_database_urls):
    receipt(f, product(f))

    async def run():
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        async with engine.connect() as db:
            outer = await db.begin()

            def invoke(sync):
                spec = importlib.util.spec_from_file_location(
                    "inventory_revision",
                    "migrations/versions/000000000007_inventory_core.py",
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                with Operations.context(MigrationContext.configure(sync)):
                    module.downgrade()

            with pytest.raises(DBAPIError) as error:
                await db.run_sync(invoke)
            assert error.value.orig.sqlstate == "55000"
            await outer.rollback()
        await engine.dispose()

    asyncio.run(run())
    assert len(query(f, "SELECT id FROM inventory_lots WHERE household_id=:hid")) == 1


def test_inventory_provisioning_fails_closed_for_absent_owner_and_unset_runtime_role(
    finance_database_urls, monkeypatch
):
    async def invoke(role):
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        try:
            async with engine.connect() as db:

                def preflight(sync):
                    spec = importlib.util.spec_from_file_location(
                        "inventory_role_probe",
                        "migrations/versions/000000000007_inventory_core.py",
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    with Operations.context(MigrationContext.configure(sync)):
                        module._runtime_role()

                with pytest.raises(RuntimeError, match="FINANCE_RUNTIME_ROLE"):
                    await db.run_sync(preflight)
        finally:
            await engine.dispose()

    for role in [
        None,
        "p04_nonexistent_runtime_role",
        make_url(finance_database_urls[0]).username,
    ]:
        if role is None:
            monkeypatch.delenv("FINANCE_RUNTIME_ROLE", raising=False)
        else:
            monkeypatch.setenv("FINANCE_RUNTIME_ROLE", role)
        asyncio.run(invoke(role))


def test_history_triggers_backstop_accidentally_broadened_runtime_grants(
    f, finance_database_urls
):
    receipt(f, product(f), cost_currency="USD", unit_cost="1")

    async def run():
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        async with engine.connect() as db:
            outer = await db.begin()
            role = db.dialect.identifier_preparer.quote(
                make_url(finance_database_urls[1]).username
            )
            for table in ["inventory_movements", "inventory_lots"]:
                await db.execute(
                    text(f"GRANT UPDATE,DELETE,TRUNCATE ON {table} TO {role}")
                )
            # PostgreSQL checks every CASCADE target's privilege before firing
            # any trigger. Broaden only within this rolled-back owner transaction
            # to prove trigger backstops rather than the ordinary grant denial.
            for table in [
                "inventory_adjustments",
                "consumption_records",
                "disposal_records",
                "refund_inventory_links",
            ]:
                await db.execute(text(f"GRANT TRUNCATE ON {table} TO {role}"))
            await db.execute(text(f"SET LOCAL ROLE {role}"))
            for statement in [
                "UPDATE inventory_movements SET quantity_delta=6 WHERE household_id=:hid",
                "DELETE FROM inventory_movements WHERE household_id=:hid",
                "TRUNCATE inventory_movements CASCADE",
                "UPDATE inventory_lots SET unit_cost=2 WHERE household_id=:hid",
                "DELETE FROM inventory_lots WHERE household_id=:hid",
                "TRUNCATE inventory_lots CASCADE",
            ]:
                with pytest.raises(DBAPIError) as error:
                    async with db.begin_nested():
                        await db.execute(text(statement), {"hid": f.hid})
                assert error.value.orig.sqlstate == "55000", statement
            await outer.rollback()
        await engine.dispose()

    asyncio.run(run())
    assert (
        query(f, "SELECT unit_cost FROM inventory_lots WHERE household_id=:hid")[0][
            "unit_cost"
        ]
        == 1
    )


def test_frozen_future_tables_enforce_composite_household_links(f):
    lot = receipt(f, product(f)).json()
    unit = query(f, "SELECT base_unit_id FROM products WHERE household_id=:hid")[0][
        "base_unit_id"
    ]

    async def run():
        async with f.db() as db, db.begin():
            params = {
                "hid": f.hid,
                "other": f.other_hid,
                "pid": lot["product_id"],
                "lid": lot["id"],
                "mid": lot["receipt_movement_id"],
                "actor": f.actors["OWNER"].member_id,
                "unit": unit,
            }
            params["rid"] = await db.scalar(
                text(
                    "INSERT INTO recipes(household_id,name,servings,created_by_member_id) VALUES (:hid,'Recipe',1,:actor) RETURNING id"
                ),
                params,
            )
            probes = [
                "INSERT INTO recipes(household_id,name,servings,created_by_member_id) VALUES (:other,'Invalid creator',1,:actor)",
                "INSERT INTO recipe_ingredients(household_id,recipe_id,line_no,product_id,quantity,unit_id,essential) VALUES (:other,:rid,1,:pid,1,:unit,true)",
                "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at) VALUES (:other,:lid,'RETURN',-1,now())",
                "INSERT INTO inventory_adjustments(household_id,movement_id,counted_quantity,reason) VALUES (:other,:mid,1,'Foreign')",
                "INSERT INTO consumption_records(household_id,movement_id,reason_code) VALUES (:other,:mid,'DAILY_USE')",
                "INSERT INTO disposal_records(household_id,movement_id,reason_code) VALUES (:other,:mid,'DAMAGED')",
            ]
            for statement in probes:
                with pytest.raises(DBAPIError) as error:
                    async with db.begin_nested():
                        await db.execute(text(statement), params)
                assert error.value.orig.sqlstate == "23503"
            await db.rollback()

    asyncio.run(run())
