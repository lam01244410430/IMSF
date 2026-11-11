"""Frozen future-command integrity, exercised as runtime SQL, no HTTP writer."""

import asyncio
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_inventory_lots import product, receipt
from test_finance_transactions import query


def test_zero_mixed_replenishment_and_movement_sum_projection(f):
    from app.inventory.domain import terminal_state

    lot = receipt(f, product(f)).json()

    async def run():
        async with f.db() as db, db.begin():
            params = {"hid": f.hid, "lid": lot["id"]}
            mid = await db.scalar(
                text(
                    "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at) VALUES (:hid,:lid,'CONSUME',-5,now()) RETURNING id"
                ),
                params,
            )
            await db.execute(
                text(
                    "INSERT INTO consumption_records(household_id,movement_id,reason_code) VALUES (:hid,:mid,'DAILY_USE')"
                ),
                params | {"mid": mid},
            )
            await db.execute(
                text(
                    "UPDATE inventory_lots SET remaining_quantity=0,terminal_state='CONSUMED' WHERE household_id=:hid AND id=:lid"
                ),
                params,
            )
        async with f.db() as db, db.begin():
            mid = await db.scalar(
                text(
                    "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at,reason) VALUES (:hid,:lid,'ADJUST_IN',1,now(),'Correction') RETURNING id"
                ),
                params,
            )
            await db.execute(
                text(
                    "INSERT INTO inventory_adjustments(household_id,movement_id,counted_quantity,reason) VALUES (:hid,:mid,1,'Correction')"
                ),
                params | {"mid": mid},
            )
            await db.execute(
                text(
                    "UPDATE inventory_lots SET remaining_quantity=1,terminal_state=NULL WHERE household_id=:hid AND id=:lid"
                ),
                params,
            )
        async with f.db() as db, db.begin():
            await db.execute(
                text(
                    "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at) VALUES (:hid,:lid,'RETURN',-1,now())"
                ),
                params,
            )
            await db.execute(
                text(
                    "UPDATE inventory_lots SET remaining_quantity=0,terminal_state='MIXED' WHERE household_id=:hid AND id=:lid"
                ),
                params,
            )

    asyncio.run(run())
    state = query(
        f,
        "SELECT remaining_quantity,terminal_state FROM inventory_lots WHERE household_id=:hid",
    )[0]
    assert state["remaining_quantity"] == 0 and state["terminal_state"] == "MIXED"
    assert (
        query(
            f,
            "SELECT sum(quantity_delta) AS q FROM inventory_movements WHERE household_id=:hid",
        )[0]["q"]
        == 0
    )
    assert terminal_state(0, ["CONSUME"]) == "CONSUMED"
    assert terminal_state(0, ["DISPOSE"]) == "DISCARDED"
    assert terminal_state(0, ["RETURN"]) == "RETURNED"
    assert terminal_state(0, ["ADJUST_OUT"]) == "ADJUSTED_OUT"
    assert terminal_state(0, ["CONSUME", "RETURN"]) == "MIXED"
    assert terminal_state(1, ["RETURN"]) is None


@pytest.mark.parametrize(
    "kind,detail",
    [
        ("CONSUME", None),
        ("CONSUME", "disposal"),
        ("RECEIPT", "consume"),
        ("ADJUST_OUT", "wrong_count"),
        ("DISPOSE", "other_without_reason"),
    ],
)
def test_detail_kind_and_exact_cardinality_enforced(f, kind, detail):
    lot = receipt(f, product(f)).json()

    async def run():
        with pytest.raises(DBAPIError) as error:
            async with f.db() as db, db.begin():
                params = {"hid": f.hid, "lid": lot["id"], "kind": kind}
                mid = await db.scalar(
                    text(
                        "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at) VALUES (:hid,:lid,:kind,-1,now()) RETURNING id"
                    ),
                    params,
                )
                params["mid"] = mid
                if detail == "disposal":
                    await db.execute(
                        text(
                            "INSERT INTO disposal_records(household_id,movement_id,reason_code) VALUES (:hid,:mid,'DAMAGED')"
                        ),
                        params,
                    )
                if detail == "consume":
                    await db.execute(
                        text(
                            "INSERT INTO consumption_records(household_id,movement_id,reason_code) VALUES (:hid,:mid,'DAILY_USE')"
                        ),
                        params,
                    )
                if detail == "wrong_count":
                    await db.execute(
                        text(
                            "INSERT INTO inventory_adjustments(household_id,movement_id,counted_quantity,reason) VALUES (:hid,:mid,3,'Count')"
                        ),
                        params,
                    )
                if detail == "other_without_reason":
                    await db.execute(
                        text(
                            "INSERT INTO disposal_records(household_id,movement_id,reason_code) VALUES (:hid,:mid,'OTHER')"
                        ),
                        params,
                    )
                await db.execute(
                    text(
                        "UPDATE inventory_lots SET remaining_quantity=4 WHERE household_id=:hid AND id=:lid"
                    ),
                    params,
                )
        assert error.value.orig.sqlstate in {"55000", "23514"}

    asyncio.run(run())
    assert (
        query(
            f, "SELECT remaining_quantity FROM inventory_lots WHERE household_id=:hid"
        )[0]["remaining_quantity"]
        == 5
    )
    assert (
        len(query(f, "SELECT id FROM inventory_movements WHERE household_id=:hid")) == 1
    )


def test_cooking_snapshot_cannot_duplicate_one_allocation_and_hide_another(f):
    """Frozen DDL must prove the full allocation bijection, not only equal counts."""
    import json

    lot = receipt(f, product(f)).json()

    async def run():
        with pytest.raises(DBAPIError) as error:
            async with f.db() as db, db.begin():
                params = {
                    "hid": f.hid,
                    "actor": f.actors["OWNER"].member_id,
                    "lid": lot["id"],
                }
                rid = await db.scalar(
                    text(
                        "INSERT INTO recipes(household_id,name,servings,created_by_member_id) VALUES (:hid,'Rice',1,:actor) RETURNING id"
                    ),
                    params,
                )
                mids = []
                for _ in range(2):
                    mids.append(
                        await db.scalar(
                            text(
                                "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at) VALUES (:hid,:lid,'CONSUME',-1,now()) RETURNING id"
                            ),
                            params,
                        )
                    )
                allocation = {
                    "movement_id": mids[0],
                    "lot_id": lot["id"],
                    "product_id": lot["product_id"],
                    "base_quantity": "1",
                }
                snapshot = {
                    "schema_version": 1,
                    "recipe": {
                        "id": rid,
                        "name": "Rice",
                        "servings": "1",
                        "instructions": None,
                    },
                    "ingredients": [],
                    "allocations": [allocation, allocation],
                    "local_date": "2026-11-11",
                    "timezone": "UTC",
                }
                cid = await db.scalar(
                    text(
                        "INSERT INTO recipe_cooking_history(household_id,recipe_id,cooked_at,servings,actor_member_id,recipe_snapshot) VALUES (:hid,:rid,now(),1,:actor,CAST(:snapshot AS jsonb)) RETURNING id"
                    ),
                    params | {"rid": rid, "snapshot": json.dumps(snapshot)},
                )
                for mid in mids:
                    await db.execute(
                        text(
                            "INSERT INTO consumption_records(household_id,movement_id,cooking_history_id,reason_code) VALUES (:hid,:mid,:cid,'COOKING')"
                        ),
                        params | {"mid": mid, "cid": cid},
                    )
                await db.execute(
                    text(
                        "UPDATE inventory_lots SET remaining_quantity=3 WHERE household_id=:hid AND id=:lid"
                    ),
                    params,
                )
        assert error.value.orig.sqlstate == "55000"

    asyncio.run(run())
    assert (
        len(query(f, "SELECT id FROM inventory_movements WHERE household_id=:hid")) == 1
    )
    assert not query(f, "SELECT id FROM recipe_cooking_history WHERE household_id=:hid")
