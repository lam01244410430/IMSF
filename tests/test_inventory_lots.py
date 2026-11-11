"""Step 2 proposed receipt contracts exercised through real runtime HTTP."""

import asyncio
from decimal import Decimal
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_finance_transactions import query, create_draft, post, account, payment


def product(f, **changes):
    units = f.request("GET", "/measurement-units")
    assert units.status_code == 200, units.text
    g = next(u["id"] for u in units.json()["items"] if u["code"] == "g")
    r = f.request(
        "POST", "/products", json={"name": "Rice", "base_unit_id": g} | changes
    )
    assert r.status_code == 201, r.text
    return r.json()


def receipt(f, p, **changes):
    return f.request(
        "POST",
        "/inventory-lots",
        json={
            "product_id": p["id"],
            "source_kind": "GIFT",
            "quantity": "5",
            "unit_id": p["base_unit_id"],
            "received_at": "2026-11-11T10:00:00Z",
        }
        | changes,
    )


def purchase(f, p, *, quantity="5", paid=True):
    draft = create_draft(
        f,
        items=[
            {
                "line_no": 1,
                "description": "Rice",
                "quantity": "1",
                "net_amount": "12.30",
                "product_id": p["id"],
                "base_quantity": quantity,
            }
        ],
    )
    r = post(f, draft, [payment(account(f))] if paid else [])
    assert r.status_code == 200, r.text
    return r.json()


def test_one_receipt_per_lot_and_atomic_creation(f):
    p = product(f)
    r = receipt(f, p)
    assert r.status_code == 201, r.text
    lot = r.json()
    assert Decimal(lot["received_quantity"]) == Decimal(lot["remaining_quantity"]) == 5
    assert lot["terminal_state"] is None and lot["unit_cost"] is None
    movements = f.request(
        "GET", "/inventory-movements", params={"lot_id": lot["id"]}
    ).json()["items"]
    assert len(movements) == 1 and movements[0]["kind"] == "RECEIPT"
    assert movements[0]["id"] == lot["receipt_movement_id"]

    async def run():
        async with f.db() as db, db.begin():
            with pytest.raises(DBAPIError) as error:
                async with db.begin_nested():
                    await db.execute(
                        text(
                            "INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at) VALUES (:hid,:lid,'RECEIPT',5,now())"
                        ),
                        {"hid": f.hid, "lid": lot["id"]},
                    )
            assert error.value.orig.sqlstate == "23505"
        with pytest.raises(DBAPIError) as error:
            async with f.db() as db, db.begin():
                await db.execute(
                    text(
                        "INSERT INTO inventory_lots(household_id,product_id,source_kind,received_at,received_quantity,remaining_quantity) VALUES (:hid,:pid,'MANUAL',now(),1,1)"
                    ),
                    {"hid": f.hid, "pid": p["id"]},
                )
        assert error.value.orig.sqlstate == "55000"

    asyncio.run(run())
    assert len(query(f, "SELECT id FROM inventory_lots WHERE household_id=:hid")) == 1


def test_split_purchase_receipts_cannot_exceed_item_base_quantity(f):
    p = product(f)
    tx = purchase(f, p)
    fields = {"source_kind": "PURCHASE", "purchase_item_id": tx["items"][0]["id"]}
    assert receipt(f, p, quantity="3", **fields).status_code == 201
    assert receipt(f, p, quantity="2", **fields).status_code == 201
    assert receipt(f, p, quantity="0.000001", **fields).status_code == 409
    assert (
        query(
            f,
            "SELECT sum(received_quantity) AS q FROM inventory_lots WHERE household_id=:hid",
        )[0]["q"]
        == 5
    )


def test_archived_product_and_lot_policy_and_expiry_correction(f):
    p = product(f)
    lot = receipt(f, p).json()
    r = f.request(
        "PATCH",
        f"/inventory-lots/{lot['id']}",
        json={"expires_on": "2026-12-31", "reason": "Correct label"},
    )
    assert r.status_code == 200 and r.json()["expires_on"] == "2026-12-31"
    assert (
        f.request(
            "PATCH",
            f"/inventory-lots/{lot['id']}",
            json={"unit_cost": "1", "reason": "Change"},
        ).status_code
        == 422
    )
    assert (
        f.request(
            "POST",
            f"/inventory-lots/{lot['id']}/archive",
            json={"reason": "Retain history"},
        ).status_code
        == 200
    )
    assert f.request("GET", f"/inventory-lots/{lot['id']}").status_code == 200
    assert f.request("POST", f"/products/{p['id']}/archive", json={}).status_code == 200
    assert receipt(f, p).status_code == 409
    for path in [
        f"/inventory-lots/{lot['id']}",
        f"/inventory-movements/{lot['receipt_movement_id']}",
    ]:
        assert f.request("DELETE", path).status_code == 405


def test_receipt_uses_exact_explicit_conversion(f):
    p = product(f)
    kg = next(
        u["id"]
        for u in f.request("GET", "/measurement-units").json()["items"]
        if u["code"] == "kg"
    )
    r = receipt(f, p, quantity="1.234567", unit_id=kg)
    assert r.status_code == 201 and Decimal(r.json()["remaining_quantity"]) == Decimal(
        "1234.567"
    )
    ml = next(
        u["id"]
        for u in f.request("GET", "/measurement-units").json()["items"]
        if u["code"] == "ml"
    )
    assert receipt(f, p, unit_id=ml).status_code == 422


def test_failure_after_receipt_flush_rolls_back_lot_receipt_audit_and_key(
    f, monkeypatch
):
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository

    p = product(f)
    before = {
        t: query(f, f"SELECT id FROM {t} WHERE household_id=:hid ORDER BY id")
        for t in [
            "inventory_lots",
            "inventory_movements",
            "audit_logs",
            "idempotency_requests",
        ]
    }
    original = SqlAlchemyFinanceRepository.audit

    async def fail(self, values):
        if values["action"] == "INVENTORY_RECEIVED":
            await original(self, values)
            raise RuntimeError("Injected after receipt and audit flush")
        return await original(self, values)

    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyFinanceRepository, "audit", fail)
        with pytest.raises(RuntimeError, match="Injected"):
            receipt(f, p)
    assert {
        t: query(f, f"SELECT id FROM {t} WHERE household_id=:hid ORDER BY id")
        for t in before
    } == before
    assert receipt(f, p).status_code == 201


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": "0"},
        {"quantity": "-1"},
        {"quantity": 1.5},
        {"quantity": "0.0000001"},
        {"unit_cost": "0.0000000000001", "cost_currency": "USD"},
        {"unit_cost": "NaN", "cost_currency": "USD"},
        {"unit_cost": "1"},
        {"received_at": "2026-11-11T10:00:00"},
        {"remaining_quantity": "4"},
    ],
)
def test_receipt_dto_rejects_inexact_cost_quantity_and_client_projections(f, changes):
    assert receipt(f, product(f), **changes).status_code == 422
    assert not query(f, "SELECT id FROM inventory_lots WHERE household_id=:hid")
