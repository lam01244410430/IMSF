"""Step 2 product/FEFO locks and split receipt races on independent connections."""

import asyncio
from datetime import datetime, timezone
import httpx
from sqlalchemy import text
from test_inventory_lots import product, purchase, receipt
from test_finance_transactions import query


def test_concurrent_split_purchase_receipts_have_one_capacity_winner(f):
    p = product(f)
    tx = purchase(f, p)

    async def run():
        barrier = asyncio.Barrier(2)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=f.app), base_url="https://testserver"
        ) as client:

            async def call(key):
                await barrier.wait()
                return await client.post(
                    f"/api/v1/households/{f.hid}/inventory-lots",
                    headers=f.actors["OWNER"].headers | {"Idempotency-Key": key},
                    json={
                        "product_id": p["id"],
                        "source_kind": "PURCHASE",
                        "purchase_item_id": tx["items"][0]["id"],
                        "quantity": "4",
                        "unit_id": p["base_unit_id"],
                        "received_at": "2026-11-11T10:00:00Z",
                    },
                )

            responses = await asyncio.gather(call("split-a"), call("split-b"))
            assert sorted(r.status_code for r in responses) == [201, 409]

    asyncio.run(run())
    assert (
        query(
            f,
            "SELECT sum(received_quantity) AS q FROM inventory_lots WHERE household_id=:hid",
        )[0]["q"]
        == 4
    )
    assert (
        len(query(f, "SELECT id FROM inventory_movements WHERE household_id=:hid")) == 1
    )
    assert (
        len(
            query(
                f,
                "SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key IN ('split-a','split-b')",
            )
        )
        == 1
    )


def test_receipt_writer_locks_product_before_lots_and_rechecks_archive(f):
    """Product lock, rather than household serialization, excludes new receipts."""
    p = product(f)
    existing = receipt(f, p).json()

    async def run():
        async with f.db() as locker:
            await locker.begin()
            lock_pid = await locker.scalar(text("SELECT pg_backend_pid()"))
            await locker.execute(
                text(
                    "SELECT id FROM products WHERE household_id=:hid AND id=:pid FOR UPDATE"
                ),
                {"hid": f.hid, "pid": p["id"]},
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=f.app), base_url="https://testserver"
            ) as client:
                task = asyncio.create_task(
                    client.post(
                        f"/api/v1/households/{f.hid}/inventory-lots",
                        headers=f.actors["OWNER"].headers
                        | {"Idempotency-Key": "blocked-product"},
                        json={
                            "product_id": p["id"],
                            "source_kind": "GIFT",
                            "quantity": "1",
                            "unit_id": p["base_unit_id"],
                            "received_at": "2026-11-11T10:00:00Z",
                        },
                    )
                )
                async with asyncio.timeout(10):
                    while True:
                        async with f.db() as observer:
                            blocked = await observer.scalar(
                                text(
                                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)) AND query LIKE '%products%' AND query LIKE '%FOR UPDATE%')"
                                ),
                                {"pid": lock_pid},
                            )
                        if blocked:
                            break
                        await asyncio.sleep(0)
                async with f.db() as observer, observer.begin():
                    # The waiting writer has not acquired any lot lock first.
                    await observer.execute(
                        text(
                            "SELECT id FROM inventory_lots WHERE household_id=:hid AND id=:lid FOR UPDATE NOWAIT"
                        ),
                        {"hid": f.hid, "lid": existing["id"]},
                    )
                await locker.execute(
                    text(
                        "UPDATE products SET archived_at=now() WHERE household_id=:hid AND id=:pid"
                    ),
                    {"hid": f.hid, "pid": p["id"]},
                )
                await locker.commit()
                response = await task
                assert response.status_code == 409

    asyncio.run(run())
    assert len(query(f, "SELECT id FROM inventory_lots WHERE household_id=:hid")) == 1
    assert not query(
        f,
        "SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='blocked-product'",
    )


def test_repository_locks_products_ascending_and_lots_in_fefo_order(f):
    from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository

    p = product(f)
    second = product(f, name="Other")
    lots = [
        receipt(f, p, expires_on=expiry, received_at=instant).json()
        for expiry, instant in [
            (None, "2026-11-11T10:00:00Z"),
            ("2027-01-01", "2026-11-11T10:00:00Z"),
            ("2027-01-01", "2026-11-10T10:00:00Z"),
            ("2027-01-01", "2026-11-10T10:00:00Z"),
        ]
    ]

    async def run():
        async with f.db() as db, db.begin():
            repo = SqlAlchemyInventoryRepository(db)
            products = await repo.lock_products(f.hid, [second["id"], p["id"]])
            assert [r["id"] for r in products] == [p["id"], second["id"]]
            locked = await repo.lock_lots(f.hid, [second["id"], p["id"]])
            assert [r["id"] for r in locked] == [
                lots[2]["id"],
                lots[3]["id"],
                lots[1]["id"],
                lots[0]["id"],
            ]

    asyncio.run(run())


def test_concurrent_same_lot_deductions_have_one_winner(f):
    from test_inventory_checkout import configure_timezone, demand
    configure_timezone(f)
    p = product(f)
    receipt(f,p)
    async def run():
        barrier = asyncio.Barrier(2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app),base_url='https://testserver') as client:
            async def call(key):
                await barrier.wait()
                return await client.post(f'/api/v1/households/{f.hid}/checkout/deductions',
                    headers=f.actors['OWNER'].headers | {'Idempotency-Key':key},json=demand(p))
            a,b = await asyncio.gather(call('deduct-a'),call('deduct-b'))
            assert sorted([a.status_code,b.status_code]) == [201,409]
            assert next(r for r in [a,b] if r.status_code==409).json()['error_code'] == 'INVENTORY_STOCK_SHORTAGE'
    asyncio.run(run())
    assert query(f,'SELECT remaining_quantity AS q FROM inventory_lots WHERE household_id=:hid')[0]['q'] == 1
    assert len(query(f,"SELECT id FROM inventory_movements WHERE household_id=:hid AND kind='RECEIPT'")) == 1
    assert [m['quantity_delta'] for m in query(f,"SELECT quantity_delta FROM inventory_movements WHERE household_id=:hid AND kind='CONSUME'")] == [-4]
    for table,condition in [('consumption_records',''),('audit_logs'," AND action='INVENTORY_CONSUME'"),('idempotency_requests'," AND request_key IN ('deduct-a','deduct-b')")]:
        assert len(query(f,f'SELECT id FROM {table} WHERE household_id=:hid'+condition)) == 1


def test_allocator_locks_products_before_lots(f):
    from test_inventory_checkout import configure_timezone, demand
    configure_timezone(f)
    p = product(f)
    lot = receipt(f,p).json()
    async def run():
        async with f.db() as locker:
            await locker.begin()
            pid = await locker.scalar(text('SELECT pg_backend_pid()'))
            await locker.execute(text('SELECT id FROM products WHERE id=:id FOR UPDATE'),{'id':p['id']})
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app),base_url='https://testserver') as client:
                task = asyncio.create_task(client.post(f'/api/v1/households/{f.hid}/checkout/deductions',
                    headers=f.actors['OWNER'].headers | {'Idempotency-Key':'blocked-deduction'},json=demand(p)))
                async with asyncio.timeout(10):
                    while True:
                        async with f.db() as observer:
                            blocked = await observer.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)) AND query LIKE '%products%' AND query LIKE '%FOR UPDATE%')"),{'pid':pid})
                        if blocked:
                            break
                        await asyncio.sleep(0)
                async with f.db() as observer, observer.begin():
                    await observer.execute(text('SELECT id FROM inventory_lots WHERE id=:id FOR UPDATE NOWAIT'),{'id':lot['id']})
                # Eligibility changes while allocator waits must be re-read.
                await locker.execute(text('UPDATE inventory_lots SET archived_at=now() WHERE id=:id'),{'id':lot['id']})
                await locker.commit()
                r = await task
                assert r.status_code == 409
    asyncio.run(run())
    assert not query(f,"SELECT id FROM inventory_movements WHERE household_id=:hid AND kind='CONSUME'")
    assert not query(f,"SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='blocked-deduction'")


def test_purchased_fefo_locks_purchase_prefix_before_products_and_lots(f):
    from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
    from test_inventory_checkout import configure_timezone, demand
    configure_timezone(f)
    p = product(f)
    tx = purchase(f,p)
    lot = receipt(f,p,source_kind='PURCHASE',purchase_item_id=tx['items'][0]['id']).json()
    async def run():
        async with f.db() as locker:
            await locker.begin()
            repo = SqlAlchemyInventoryRepository(locker)
            await repo.lock_purchase(f.hid,tx['items'][0]['id'])
            backend = await locker.scalar(text('SELECT pg_backend_pid()'))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app),base_url='https://testserver') as client:
                task = asyncio.create_task(client.post(f'/api/v1/households/{f.hid}/checkout/deductions',headers=f.actors['OWNER'].headers | {'Idempotency-Key':'purchase-prefix'},json=demand(p)))
                async with asyncio.timeout(10):
                    while True:
                        async with f.db() as observer:
                            blocked = await observer.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)) AND query LIKE '%transactions%' AND query LIKE '%FOR UPDATE%')"),{'pid':backend})
                        if blocked:
                            break
                        await asyncio.sleep(0)
                async with f.db() as observer, observer.begin():
                    await observer.execute(text('SELECT id FROM products WHERE id=:id FOR UPDATE NOWAIT'),{'id':p['id']})
                    await observer.execute(text('SELECT id FROM inventory_lots WHERE id=:id FOR UPDATE NOWAIT'),{'id':lot['id']})
                await repo.lock_products(f.hid,[p['id']])
                await repo.lock_lots(f.hid,[p['id']])
                await repo.update('inventory-lots',f.hid,lot['id'],{'archived_at':datetime.now(timezone.utc)})
                await locker.commit()
                r = await task
                assert r.status_code == 409 and r.json()['error_code'] == 'INVENTORY_STOCK_SHORTAGE'
    asyncio.run(run())
    assert not query(f,"SELECT id FROM consumption_records WHERE household_id=:hid")
    assert not query(f,"SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='purchase-prefix'")


def test_new_purchase_source_after_discovery_refuses_without_reversed_lock_order(f):
    """Probe the internal seam independently of outer household serialization."""
    from app.finance.domain import HouseholdContext
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
    from app.inventory.domain import InventoryRequestError
    from app.inventory.dto import LotReceipt
    from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
    from app.inventory.service import InventoryService
    from test_inventory_checkout import configure_timezone, demand
    import pytest
    configure_timezone(f)
    p = product(f)
    tx = purchase(f,p)
    context = HouseholdContext(member_id=f.actors['OWNER'].member_id,role='OWNER')
    def service(db):
        return InventoryService(db,SqlAlchemyInventoryRepository(db),None,SqlAlchemyFinanceRepository(db))
    async def run():
        async with f.db() as locker:
            await locker.begin()
            writer = service(locker)
            await writer.repository.lock_purchase(f.hid,tx['items'][0]['id'])
            await writer.repository.lock_products(f.hid,[p['id']])
            backend = await locker.scalar(text('SELECT pg_backend_pid()'))
            async def allocate():
                with pytest.raises(InventoryRequestError) as error:
                    async with f.db() as db, db.begin():
                        await service(db).deduct_in_uow(context,f.hid,demand(p))
                assert error.value.status_code == 409 and error.value.code == 'INVENTORY_STATE_CONFLICT'
            task = asyncio.create_task(allocate())
            async with asyncio.timeout(10):
                while True:
                    async with f.db() as observer:
                        blocked = await observer.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)) AND query LIKE '%products%' AND query LIKE '%FOR UPDATE%')"),{'pid':backend})
                    if blocked:
                        break
                    await asyncio.sleep(0)
            await writer.receive_in_uow(context,f.hid,LotReceipt.model_validate({
                'product_id':p['id'],'source_kind':'PURCHASE','purchase_item_id':tx['items'][0]['id'],
                'quantity':'5','unit_id':p['base_unit_id'],'received_at':'2026-11-11T10:00:00Z'}).model_dump())
            await locker.commit()
            await task
    asyncio.run(run())
    assert not query(f,'SELECT id FROM consumption_records WHERE household_id=:hid')
    assert len(query(f,"SELECT id FROM inventory_movements WHERE household_id=:hid AND kind='RECEIPT'")) == 1
    assert query(f,'SELECT remaining_quantity AS q FROM inventory_lots WHERE household_id=:hid')[0]['q'] == 5
