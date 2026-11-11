"""First persisted P03 OPEN-07 HTTP evidence; no guard/DB/auth doubles."""

import asyncio
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_inventory_lots import product, receipt, purchase
from test_finance_reversals import snapshot, reversal_counts, reverse, prepared
from test_finance_transactions import query

STOCK_TABLES = (
    "inventory_lots",
    "inventory_movements",
    "inventory_adjustments",
    "consumption_records",
    "disposal_records",
    "refund_inventory_links",
    "recipe_cooking_history",
)


def stock_snapshot(f):
    return {
        t: [
            r["bytes"].encode()
            for r in query(
                f,
                f"SELECT row_to_json(t)::text AS bytes FROM {t} t WHERE household_id=:hid ORDER BY id",
            )
        ]
        for t in STOCK_TABLES
    }


def setup_purchase(f):
    p = product(f)
    tx = purchase(f, p)
    r = receipt(f, p, source_kind="PURCHASE", purchase_item_id=tx["items"][0]["id"])
    assert r.status_code == 201, r.text
    return tx, r.json()


async def link(f, db, tx, lot, **changes):
    from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository

    return await SqlAlchemyInventoryRepository(db).create_refund_link(
        {
            "household_id": f.hid,
            "original_transaction_id": tx["id"],
            "purchase_item_id": tx["items"][0]["id"],
            "lot_id": lot["id"],
            "created_by_member_id": f.actors["OWNER"].member_id,
            "reason": "Unresolved purchase return association",
        }
        | changes
    )


@pytest.mark.parametrize("role", ["OWNER", "FINANCE_MANAGER"])
def test_http_reversal_rejects_real_unresolved_refund_inventory_link_without_effects(
    f, role
):
    tx, lot = setup_purchase(f)
    payments = query(
        f,
        "SELECT id FROM transaction_payments WHERE household_id=:hid AND transaction_id=:tid",
        tid=tx["id"],
    )
    ledger = query(
        f,
        "SELECT id FROM account_ledger_entries WHERE household_id=:hid AND transaction_id=:tid",
        tid=tx["id"],
    )

    async def seed():
        async with f.db() as db, db.begin():
            return await link(
                f,
                db,
                tx,
                lot,
                original_payment_id=payments[0]["id"],
                original_ledger_entry_id=ledger[0]["id"],
            )

    persisted = asyncio.run(
        seed()
    )  # Commits a real append-only row through runtime repository.
    assert (
        query(f, "SELECT id FROM refund_inventory_links WHERE household_id=:hid")[0][
            "id"
        ]
        == persisted["id"]
    )
    before, stock, counts = snapshot(f, tx["id"]), stock_snapshot(f), reversal_counts(f)
    key = "refused-" + uuid4().hex
    r = reverse(f, tx["id"], role=role, key=key)
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "FINANCE_UNRESOLVED_REFUND"
    assert snapshot(f, tx["id"]) == before
    assert stock_snapshot(f) == stock
    assert (
        reversal_counts(f)
        == counts
        == {"headers": 0, "payments": 0, "entries": 0, "audit": 0, "keys": 0}
    )
    assert not query(
        f,
        "SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key=:key",
        key=key,
    )


def test_stock_effect_refusal_does_not_mutate_purchase(f):
    tx, _ = setup_purchase(f)
    before, stock = snapshot(f, tx["id"]), stock_snapshot(f)
    r = reverse(f, tx["id"], key="stock-refusal")
    assert (
        r.status_code == 409
        and r.json()["error_code"] == "FINANCE_STOCK_EFFECT_UNRESOLVED"
    )
    assert snapshot(f, tx["id"]) == before and stock_snapshot(f) == stock
    assert not any(reversal_counts(f).values())


def test_foreign_household_and_same_household_wrong_aggregate_links_rejected(f):
    tx, lot = setup_purchase(f)
    other_tx, other_lot = setup_purchase(f)
    wrong_payment = query(
        f,
        "SELECT id FROM transaction_payments WHERE household_id=:hid AND transaction_id=:tid",
        tid=other_tx["id"],
    )[0]["id"]
    wrong_entry = query(
        f,
        "SELECT id FROM account_ledger_entries WHERE household_id=:hid AND transaction_id=:tid",
        tid=other_tx["id"],
    )[0]["id"]

    async def run():
        for changes in [
            {"household_id": f.other_hid},
            {"purchase_item_id": other_tx["items"][0]["id"]},
            {"original_transaction_id": other_tx["id"]},
            {"lot_id": other_lot["id"]},
            {"original_payment_id": wrong_payment},
            {"original_ledger_entry_id": wrong_entry},
            {"return_movement_id": lot["receipt_movement_id"]},
        ]:
            with pytest.raises(DBAPIError) as error:
                async with f.db() as db, db.begin():
                    await link(f, db, tx, lot, **changes)
            assert error.value.orig.sqlstate in {"23503", "23514"}

    asyncio.run(run())
    assert not query(f, "SELECT id FROM refund_inventory_links WHERE household_id=:hid")


@pytest.mark.parametrize("unpaid", [False, True])
def test_finance_only_reversal_remains_compatible(f, unpaid):
    from test_finance_transactions import create_draft, post

    if unpaid:
        tx = create_draft(f)
        assert post(f, tx, []).status_code == 200
    else:
        tx, aids = prepared(f)
        assert f.request("POST", f"/accounts/{aids[0]}/archive").status_code == 204
    before = snapshot(f, tx["id"])
    r = reverse(f, tx["id"])
    assert r.status_code == 201, r.text
    assert snapshot(f, tx["id"]) == before
    assert len(r.json()["ledger_entry_ids"]) == (0 if unpaid else 1)


def test_refund_link_creation_racing_reversal_serializes_on_original(f):
    """Independent connections, actual PostgreSQL blocking, link wins original lock."""
    tx, lot = setup_purchase(f)

    async def run():
        async with f.db() as writer:
            await writer.begin()
            await writer.execute(
                text(
                    "SELECT id FROM transactions WHERE household_id=:hid AND id=:tid FOR UPDATE"
                ),
                {"hid": f.hid, "tid": tx["id"]},
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=f.app), base_url="https://testserver"
            ) as client:
                task = asyncio.create_task(
                    client.post(
                        f"/api/v1/households/{f.hid}/transactions/{tx['id']}/reversals",
                        headers=f.actors["FINANCE_MANAGER"].headers
                        | {"Idempotency-Key": "race-real-link"},
                        json={"reason": "Race reversal"},
                    )
                )
                # Wait for the reversal's original-row lock, not an elapsed delay.
                async with asyncio.timeout(10):
                    while True:
                        async with f.db() as observer:
                            blocked = await observer.scalar(
                                text(
                                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%transactions%' AND cardinality(pg_blocking_pids(pid))>0)"
                                )
                            )
                        if blocked:
                            break
                        await asyncio.sleep(0)
                # Simulate a physical RETURN through real retained SQL history, no route enabled.
                movement = await writer.scalar(
                    text(
                        "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at) VALUES (:hid,:lid,'RETURN',-1,now()) RETURNING id"
                    ),
                    {"hid": f.hid, "lid": lot["id"]},
                )
                await writer.execute(
                    text(
                        "UPDATE inventory_lots SET remaining_quantity=4 WHERE household_id=:hid AND id=:lid"
                    ),
                    {"hid": f.hid, "lid": lot["id"]},
                )
                await link(f, writer, tx, lot, return_movement_id=movement)
                await writer.commit()
                r = await task
                assert (
                    r.status_code == 409
                    and r.json()["error_code"] == "FINANCE_UNRESOLVED_REFUND"
                )

    asyncio.run(run())
    assert not any(reversal_counts(f).values())
    assert (
        len(
            query(
                f,
                "SELECT id FROM refund_inventory_links WHERE household_id=:hid AND return_movement_id IS NOT NULL",
            )
        )
        == 1
    )
