"""Step 2 product/FEFO locks and split receipt races on independent connections."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import httpx
import pytest
from sqlalchemy import text
from test_inventory_lots import product, purchase, receipt
from test_finance_transactions import query


@pytest.mark.parametrize("writer", ["receipt", "expiry", "archive", "adjustment-zero", "adjustment-partial"])
@pytest.mark.parametrize("schedule", ["http-writers", "product-wait"])
def test_receipt_expiry_archive_and_adjustment_races_recheck_fefo(f, writer, schedule):
    """Catch stale candidates, phantom receipts and stale quantities after waiting.

    Public commands serialize at the household prefix. Exercise that HTTP race
    AND an independent runtime SQL writer holding product/FEFO lot locks, so the
    shared allocator must wait on the product and then reload candidates.
    All rows commit under the frozen guards; no guard or allocator is replaced.
    """
    from test_inventory_checkout import configure_timezone, demand

    # Frozen household FKs on new receipt/movement/detail rows require KEY SHARE.
    # After an HTTP deduction holds household FOR UPDATE, inserting those rows
    # behind its product wait would introduce a lock inversion/deadlock. For
    # these three product-wait cases use the real shared application UoW API
    # (also used by checkout/cooking), without the outer identity/key locks.
    # HTTP writer races above that seam remain covered for every writer below.
    application_wait = schedule == "product-wait" and writer not in {"expiry", "archive"}

    configure_timezone(f, "UTC")
    p = product(f)
    today = datetime.now(timezone.utc).date()
    early_expiry = (today + timedelta(days=10)).isoformat()
    later_expiry = (today + timedelta(days=20)).isoformat()
    expired = (today - timedelta(days=30)).isoformat()
    new_expiry = (today + timedelta(days=5)).isoformat()
    lots = []
    for expiry in (early_expiry, later_expiry, None):
        r = receipt(f, p, quantity="3", expires_on=expiry)
        assert r.status_code == 201, r.text
        lots.append(r.json())
    first, fallback, undated = lots
    prefix = f"/api/v1/households/{f.hid}"
    writer_key, deduction_key = "fefo-race-writer", "fefo-race-deduction"

    async def run():
        tasks = []
        async with f.db() as locker:
            await locker.begin()
            backend = await locker.scalar(text("SELECT pg_backend_pid()"))
            await locker.execute(text(
                "SELECT id FROM products WHERE household_id=:hid AND id=:pid "
                "ORDER BY id FOR UPDATE"
            ), {"hid": f.hid, "pid": p["id"]})

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=f.app), base_url="https://testserver"
            ) as client:
                def command(method, path, body, key):
                    role = "INVENTORY_MANAGER" if key == writer_key else "OWNER"
                    task = asyncio.create_task(client.request(
                        method, prefix + path,
                        headers=f.actors[role].headers | {"Idempotency-Key": key},
                        json=body,
                    ))
                    tasks.append(task)
                    return task

                async def wait_for_lock(task, blocker, table):
                    async with asyncio.timeout(10):
                        while True:
                            if task.done():
                                pytest.fail(f"Command finished before {table} lock: {task.result()}")
                            async with f.db() as observer:
                                waiter = await observer.scalar(text(
                                    "SELECT pid FROM pg_stat_activity "
                                    "WHERE :blocker=ANY(pg_blocking_pids(pid)) "
                                    "AND wait_event_type='Lock' "
                                    "AND query LIKE :table AND query LIKE '%FOR UPDATE%'"
                                ), {"blocker": blocker, "table": f"%{table}%"})
                            if waiter is not None:
                                return waiter
                            await asyncio.sleep(0)

                try:
                    writer_response = None
                    if schedule == "http-writers":
                        if writer == "receipt":
                            writer_task = command("POST", "/inventory-lots", {
                                "product_id": p["id"], "source_kind": "GIFT",
                                "quantity": "2", "unit_id": p["base_unit_id"],
                                "received_at": "2026-11-11T10:00:00Z", "expires_on": new_expiry,
                            }, writer_key)
                        elif writer == "expiry":
                            writer_task = command("PATCH", f"/inventory-lots/{first['id']}", {
                                "expires_on": expired, "reason": "Correct expiry during FEFO race",
                            }, writer_key)
                        elif writer == "archive":
                            writer_task = command("POST", f"/inventory-lots/{first['id']}/archive", {
                                "reason": "Archive during FEFO race",
                            }, writer_key)
                        else:
                            writer_task = command("POST", "/inventory-adjustments", {
                                "lot_id": first["id"], "counted_quantity": "0" if writer == "adjustment-zero" else "1",
                                "unit_id": p["base_unit_id"], "reason": "Count during FEFO race",
                            }, writer_key)
                        writer_backend = await wait_for_lock(writer_task, backend, "products")
                        deduction = command("POST", "/checkout/deductions", demand(p), deduction_key)
                        # Prove overlap rather than relying on task scheduling or sleeps.
                        await wait_for_lock(deduction, writer_backend, "households")
                    else:
                        # SQL writer uses the same product -> FEFO lot order, with
                        # no household lock, to expose the allocator's own wait.
                        await locker.execute(text(
                            "SELECT id FROM inventory_lots WHERE household_id=:hid AND product_id=:pid "
                            "ORDER BY product_id,expires_on NULLS LAST,received_at,id FOR UPDATE"
                        ), {"hid": f.hid, "pid": p["id"]})
                        if application_wait:
                            from app.finance.domain import HouseholdContext
                            from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
                            from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
                            from app.inventory.service import InventoryService

                            async def allocate():
                                async with f.db() as db, db.begin():
                                    service = InventoryService(db, SqlAlchemyInventoryRepository(db), None,
                                                               SqlAlchemyFinanceRepository(db))
                                    return await service.deduct_in_uow(
                                        HouseholdContext(member_id=f.actors["OWNER"].member_id, role="OWNER"),
                                        f.hid, demand(p),
                                    )
                            deduction = asyncio.create_task(allocate())
                            tasks.append(deduction)
                        else:
                            deduction = command("POST", "/checkout/deductions", demand(p), deduction_key)
                        await wait_for_lock(deduction, backend, "products")
                        if writer == "receipt":
                            new_id = await locker.scalar(text(
                                "INSERT INTO inventory_lots(household_id,product_id,source_kind,"
                                "received_at,expires_on,received_quantity,remaining_quantity) "
                                "VALUES (:hid,:pid,'GIFT','2026-11-11T10:00:00Z',CAST(:expiry AS date),2,2) RETURNING id"
                            ), {"hid": f.hid, "pid": p["id"], "expiry": new_expiry})
                            await locker.execute(text(
                                "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at,actor_member_id) "
                                "VALUES (:hid,:lid,'RECEIPT',2,'2026-11-11T10:00:00Z',:actor)"
                            ), {"hid": f.hid, "lid": new_id, "actor": f.actors["OWNER"].member_id})
                        elif writer in {"expiry", "archive"}:
                            statement = (
                                "UPDATE inventory_lots SET expires_on=CAST(:expiry AS date) "
                                if writer == "expiry" else "UPDATE inventory_lots SET archived_at=now() "
                            ) + "WHERE household_id=:hid AND id=:lid"
                            await locker.execute(text(statement), {
                                "hid": f.hid, "lid": first["id"], "expiry": expired,
                            })
                        else:
                            count = 0 if writer == "adjustment-zero" else 1
                            mid = await locker.scalar(text(
                                "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at,actor_member_id,reason) "
                                "VALUES (:hid,:lid,'ADJUST_OUT',:delta,now(),:actor,'Count during FEFO race') RETURNING id"
                            ), {"hid": f.hid, "lid": first["id"], "delta": count - 3,
                                "actor": f.actors["OWNER"].member_id})
                            await locker.execute(text(
                                "INSERT INTO inventory_adjustments(household_id,movement_id,counted_quantity,reason) "
                                "VALUES (:hid,:mid,:count,'Count during FEFO race')"
                            ), {"hid": f.hid, "mid": mid, "count": count})
                            await locker.execute(text(
                                "UPDATE inventory_lots SET remaining_quantity=:count,terminal_state=:terminal "
                                "WHERE household_id=:hid AND id=:lid"
                            ), {"hid": f.hid, "lid": first["id"], "count": count,
                                "terminal": "ADJUSTED_OUT" if count == 0 else None})
                    await locker.commit()
                    async with asyncio.timeout(10):
                        if writer_response is None and schedule == "http-writers":
                            writer_response = await writer_task
                            assert writer_response.status_code == (200 if writer in {"expiry", "archive"} else 201), writer_response.text
                        response = await deduction
                    if application_wait:
                        return response
                    assert response.status_code == 201, response.text
                    return response.json()
                finally:
                    await locker.rollback()
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)

    result = asyncio.run(run())
    if writer == "receipt":
        new_lot, = query(f, "SELECT id FROM inventory_lots WHERE household_id=:hid AND received_quantity=2")
        expected = [(new_lot["id"], Decimal(2)), (first["id"], Decimal(2))]
        remaining = {new_lot["id"]: 0, first["id"]: 1, fallback["id"]: 3, undated["id"]: 3}
    elif writer == "adjustment-partial":
        # A reduced but still eligible lot can supply only its new count of one.
        expected = [(first["id"], Decimal(1)), (fallback["id"], Decimal(3))]
        remaining = {first["id"]: 0, fallback["id"]: 0, undated["id"]: 3}
    else:
        expected = [(fallback["id"], Decimal(3)), (undated["id"], Decimal(1))]
        remaining = {first["id"]: 0 if writer == "adjustment-zero" else 3,
                     fallback["id"]: 0, undated["id"]: 2}
    assert [(a["lot_id"], Decimal(a["base_quantity"])) for a in result["allocations"]] == expected
    movements = query(f, "SELECT id,lot_id,quantity_delta FROM inventory_movements WHERE household_id=:hid AND kind='CONSUME' ORDER BY id")
    assert [(m["lot_id"], -m["quantity_delta"]) for m in movements] == expected
    assert [m["id"] for m in movements] == result["movement_ids"]
    details = query(f, "SELECT movement_id,reason_code FROM consumption_records WHERE household_id=:hid ORDER BY movement_id")
    assert [d["movement_id"] for d in details] == result["movement_ids"]
    assert all(d["reason_code"] == "CHECKOUT" for d in details)
    persisted = query(f, """
        SELECT l.id,l.remaining_quantity,l.received_quantity,l.expires_on,l.archived_at,
               SUM(m.quantity_delta) AS movement_sum
        FROM inventory_lots l JOIN inventory_movements m
          ON (m.household_id,m.lot_id)=(l.household_id,l.id)
        WHERE l.household_id=:hid GROUP BY l.household_id,l.id
    """)
    assert {l["id"]: l["remaining_quantity"] for l in persisted} == remaining
    assert all(0 <= l["remaining_quantity"] <= l["received_quantity"]
               and l["movement_sum"] == l["remaining_quantity"] for l in persisted)
    changed = next(l for l in persisted if l["id"] == first["id"])
    if writer == "expiry":
        assert changed["expires_on"].isoformat() == expired
    elif writer == "archive":
        assert changed["archived_at"] is not None
    elif writer.startswith("adjustment"):
        adjustment, = query(f, "SELECT m.lot_id,m.quantity_delta,a.counted_quantity FROM inventory_movements m JOIN inventory_adjustments a ON (a.household_id,a.movement_id)=(m.household_id,m.id) WHERE m.household_id=:hid")
        count = 0 if writer == "adjustment-zero" else 1
        assert (adjustment["lot_id"], adjustment["quantity_delta"], adjustment["counted_quantity"]) == (first["id"], count - 3, count)
    keys = query(f, "SELECT request_key FROM idempotency_requests WHERE household_id=:hid AND request_key IN (:writer,:deduction)",
                 writer=writer_key, deduction=deduction_key)
    expected_keys = {writer_key, deduction_key} if schedule == "http-writers" else (
        set() if application_wait else {deduction_key}
    )
    assert {k["request_key"] for k in keys} == expected_keys


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
