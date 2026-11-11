"""Step 2 product/FEFO locks and split receipt races on independent connections."""

import asyncio
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
