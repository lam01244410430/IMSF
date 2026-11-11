"""Inventory extends the decided P03 key protocol, including DATE values."""

import asyncio
import httpx
from test_inventory_lots import product
from test_finance_transactions import query


def test_same_key_same_body_replays_identical_bytes_and_changed_payload_conflicts(f):
    p = product(f)
    body = {
        "product_id": p["id"],
        "source_kind": "GIFT",
        "quantity": "2",
        "unit_id": p["base_unit_id"],
        "received_at": "2026-11-11T10:00:00Z",
        "expires_on": "2027-01-01",
    }
    r = f.request("POST", "/inventory-lots", key="same", json=body)
    replay = f.request(
        "POST", "/inventory-lots", key="same", json=body | {"quantity": "2.000000"}
    )
    assert r.status_code == replay.status_code == 201 and r.content == replay.content
    conflict = f.request(
        "POST", "/inventory-lots", key="same", json=body | {"expires_on": "2027-01-02"}
    )
    assert (
        conflict.status_code == 409
        and conflict.json()["error_code"] == "INVENTORY_IDEMPOTENCY_CONFLICT"
    )
    lid = r.json()["id"]
    for expiry in ["2027-02-01", None]:
        first = f.request(
            "PATCH",
            f"/inventory-lots/{lid}",
            key=str(expiry),
            json={"expires_on": expiry, "reason": "Label"},
        )
        second = f.request(
            "PATCH",
            f"/inventory-lots/{lid}",
            key=str(expiry),
            json={"expires_on": expiry, "reason": "Label"},
        )
        assert (
            first.status_code == second.status_code == 200
            and first.content == second.content
        )
    assert (
        len(query(f, "SELECT id FROM inventory_movements WHERE household_id=:hid")) == 1
    )


def test_concurrent_same_key_has_one_effect(f):
    p = product(f)

    async def run():
        barrier = asyncio.Barrier(2)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=f.app), base_url="https://testserver"
        ) as client:

            async def call():
                await barrier.wait()
                return await client.post(
                    f"/api/v1/households/{f.hid}/inventory-lots",
                    headers=f.actors["OWNER"].headers | {"Idempotency-Key": "race"},
                    json={
                        "product_id": p["id"],
                        "source_kind": "GIFT",
                        "quantity": "1",
                        "unit_id": p["base_unit_id"],
                        "received_at": "2026-11-11T10:00:00Z",
                    },
                )

            a, b = await asyncio.gather(call(), call())
            assert a.status_code == b.status_code == 201 and a.content == b.content

    asyncio.run(run())
    assert len(query(f, "SELECT id FROM inventory_lots WHERE household_id=:hid")) == 1
    assert (
        len(query(f, "SELECT id FROM inventory_movements WHERE household_id=:hid")) == 1
    )
