"""Step 3 PROPOSAL contracts: real HTTP commands and retained runtime state.

Catches missing signed/detail writes, stale counts, archive/role bypasses,
partial commits, mutable corrections/cost, and financial return resolution.
"""

import asyncio
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from test_inventory_lots import product, receipt
from test_finance_inventory_reversal import setup_purchase, stock_snapshot
from test_finance_reversals import snapshot, reverse, reversal_counts
from test_finance_transactions import query

HISTORY = ("inventory_movements", "inventory_adjustments", "consumption_records",
           "disposal_records", "refund_inventory_links")


def allocation(p, lot, quantity="1", **changes):
    return {"lot_id": lot["id"], "quantity": quantity,
            "unit_id": p["base_unit_id"]} | changes


def deduction(f, p, lot, path="consumption", quantity="1", **kwargs):
    body = {"allocations": [allocation(p, lot, quantity)],
            "reason_code": "DAILY_USE" if path == "consumption" else "DAMAGED"}
    body.update(kwargs.pop("body", {}))
    return f.request("POST", "/" + path, json=body, **kwargs)


def adjust(f, p, lot, count, **kwargs):
    body = {"lot_id": lot["id"], "counted_quantity": count,
            "unit_id": p["base_unit_id"], "reason": "Physical recount"}
    body.update(kwargs.pop("body", {}))
    return f.request("POST", "/inventory-adjustments", json=body, **kwargs)


def invariant(f):
    rows = query(f, """SELECT l.id,l.remaining_quantity,l.received_quantity,
        l.terminal_state,l.unit_cost,l.cost_currency,sum(m.quantity_delta) AS total
        FROM inventory_lots l JOIN inventory_movements m
        ON (m.household_id,m.lot_id)=(l.household_id,l.id)
        WHERE l.household_id=:hid GROUP BY l.id ORDER BY l.id""")
    assert rows
    for row in rows:
        assert row["total"] == row["remaining_quantity"]
        assert 0 <= row["remaining_quantity"] <= row["received_quantity"]
        assert (row["remaining_quantity"] == 0) == (row["terminal_state"] is not None)
    return rows


def effects(f):
    return stock_snapshot(f) | {
        t: query(f, f"SELECT row_to_json(t)::text AS bytes FROM {t} t "
                 "WHERE household_id=:hid ORDER BY id")
        for t in ("audit_logs", "idempotency_requests")
    }


@pytest.mark.parametrize("path,kind,detail", [
    ("consumption", "CONSUME", "consumption_records"),
    ("disposals", "DISPOSE", "disposal_records"),
])
def test_signed_deltas_exact_details_duplicate_lot_normalization_and_fixed_cost(f, path, kind, detail):
    p = product(f)
    lot = receipt(f, p, unit_cost="0.123456789012", cost_currency="USD").json()
    r = deduction(f, p, lot, path, body={"allocations": [allocation(p, lot, "1"), allocation(p, lot, "2")]})
    assert r.status_code == 201, r.text
    result = r.json()
    assert len(result["movement_ids"]) == 1
    assert len(result["allocations"]) == 1
    allocated = result["allocations"][0]
    assert allocated["product_id"] == p["id"] and allocated["lot_id"] == lot["id"]
    assert isinstance(allocated["base_quantity"], str) and Decimal(allocated["base_quantity"]) == 3
    assert isinstance(allocated["remaining_quantity"], str) and Decimal(allocated["remaining_quantity"]) == 2
    mid = result["movement_ids"][0]
    movement = f.request("GET", f"/inventory-movements/{mid}")
    assert movement.status_code == 200
    assert movement.json()["kind"] == kind and Decimal(movement.json()["quantity_delta"]) == -3
    assert movement.json()["actor_member_id"] == f.actors["OWNER"].member_id
    for table in ("consumption_records", "disposal_records", "inventory_adjustments"):
        assert len(query(f, f"SELECT * FROM {table} WHERE household_id=:hid")) == (1 if table == detail else 0)
    persisted = invariant(f)[0]
    assert persisted["remaining_quantity"] == 2
    assert persisted["unit_cost"] == Decimal("0.123456789012") and persisted["cost_currency"] == "USD"
    assert len(query(f, "SELECT id FROM inventory_movements WHERE household_id=:hid AND kind='RECEIPT'")) == 1


def test_counted_vs_found_noop_cap_immutable_correction_and_manual_found_stock(f):
    p = product(f)
    lot = receipt(f, p).json()
    before = effects(f)
    for count in ("5", "6"):
        assert adjust(f, p, lot, count, key="reusable").status_code == 409
        assert effects(f) == before
    first = adjust(f, p, lot, "2", key="reusable")
    assert first.status_code == 201, first.text
    mid = first.json()["movement_id"]
    old = {t: query(f, f"SELECT row_to_json(t)::text AS bytes FROM {t} t WHERE household_id=:hid ORDER BY id")
           for t in HISTORY}
    correction = adjust(f, p, lot, "5", body={"correction_of_movement_id": mid})
    assert correction.status_code == 201, correction.text
    newmid = correction.json()["movement_id"]
    movement = f.request("GET", f"/inventory-movements/{newmid}").json()
    assert movement["kind"] == "ADJUST_IN" and movement["correction_of_movement_id"] == mid
    assert Decimal(movement["quantity_delta"]) == 3
    for t in old:
        now = query(f, f"SELECT row_to_json(t)::text AS bytes FROM {t} t WHERE household_id=:hid ORDER BY id")
        assert now[:len(old[t])] == old[t]
    assert invariant(f)[0]["remaining_quantity"] == 5
    assert adjust(f, p, lot, "6").status_code == 409
    found = receipt(f, p, source_kind="MANUAL", quantity="1", reason="Separately sourced excess found stock")
    assert found.status_code == 201
    assert [r["received_quantity"] for r in invariant(f)] == [5, 1]


@pytest.mark.parametrize("path,terminal", [("consumption", "CONSUMED"), ("disposals", "DISCARDED"), ("adjustment", "ADJUSTED_OUT")])
def test_terminal_replenishment_and_historical_mixed_classification(f, path, terminal):
    p = product(f)
    lot = receipt(f, p).json()
    r = adjust(f, p, lot, "0") if path == "adjustment" else deduction(f, p, lot, path, "5")
    assert r.status_code == 201, r.text
    assert invariant(f)[0]["terminal_state"] == terminal
    assert adjust(f, p, lot, "1").status_code == 201
    assert invariant(f)[0]["terminal_state"] is None
    # Choose a different negative kind; positive replenishment never erases old kinds.
    last = "consumption" if path != "consumption" else "disposals"
    assert deduction(f, p, lot, last).status_code == 201
    assert invariant(f)[0]["terminal_state"] == "MIXED"


def test_stock_only_purchase_return_appends_unresolved_link_and_never_resolves_finance(f):
    tx, lot = setup_purchase(f)
    unit = query(f, "SELECT base_unit_id FROM products WHERE household_id=:hid")[0]["base_unit_id"]
    before = snapshot(f, tx["id"])
    body = {"quantity": "5", "unit_id": unit, "reason": "Return purchase"}
    path = f"/inventory-lots/{lot['id']}/returns"
    r = f.request("POST", path, key="return", json=body)
    replay = f.request("POST", path, key="return", json=body | {"quantity": "5.000000"})
    assert r.status_code == replay.status_code == 201, r.text
    assert r.content == replay.content
    result = r.json()
    assert len(result["movement_ids"]) == len(result["refund_inventory_link_ids"]) == 1
    assert not result["consumption_record_ids"] and not result["disposal_record_ids"] and not result["adjustment_ids"]
    row = query(f, "SELECT * FROM refund_inventory_links WHERE household_id=:hid")[0]
    assert row["original_transaction_id"] == tx["id"] and row["purchase_item_id"] == tx["items"][0]["id"]
    assert row["return_movement_id"] == result["movement_ids"][0] and row["lot_id"] == lot["id"]
    assert invariant(f)[0]["terminal_state"] == "RETURNED"
    assert snapshot(f, tx["id"]) == before
    r = reverse(f, tx["id"], key="return-does-not-resolve")
    assert r.status_code == 409 and r.json()["error_code"] == "FINANCE_UNRESOLVED_REFUND"
    assert not any(reversal_counts(f).values())
    assert snapshot(f, tx["id"]) == before


@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "FINANCE_MANAGER", "INVENTORY_MANAGER", "MEMBER", "VIEWER"])
def test_step3_explicit_permission_matrix_and_reads(f, role):
    tx, lot = setup_purchase(f)
    p = {"base_unit_id": query(f, "SELECT base_unit_id FROM products WHERE household_id=:hid")[0]["base_unit_id"]}
    cases = [
        ("/consumption", {"allocations": [allocation(p, lot)], "reason_code": "DAILY_USE"}, {"OWNER", "INVENTORY_MANAGER", "MEMBER"}),
        ("/disposals", {"allocations": [allocation(p, lot)], "reason_code": "DAMAGED"}, {"OWNER", "INVENTORY_MANAGER", "MEMBER"}),
        ("/inventory-adjustments", {"lot_id": lot["id"], "counted_quantity": "4", "unit_id": p["base_unit_id"], "reason": "Count"}, {"OWNER", "INVENTORY_MANAGER"}),
        (f"/inventory-lots/{lot['id']}/returns", {"quantity": "1", "unit_id": p["base_unit_id"], "reason": "Return"}, {"OWNER", "INVENTORY_MANAGER"}),
    ]
    for path, body, allowed in cases:
        before = effects(f)
        r = f.request("POST", path, role=role, json=body)
        assert r.status_code == (201 if role in allowed else 403), (path, role, r.text)
        if role not in allowed:
            assert effects(f) == before
    for path in ("/consumption", "/disposals", "/inventory-adjustments", "/inventory-movements"):
        r = f.request("GET", path, role=role)
        assert r.status_code == 200, r.text
        assert "items" in r.json() and "next_cursor" in r.json()
    invariant(f)


@pytest.mark.parametrize("archive", ["product", "lot"])
def test_archive_proposal_blocks_consumption_allows_reasoned_disposal_adjustment_return(f, archive):
    tx, lot = setup_purchase(f)
    p = {"id": lot["product_id"], "base_unit_id": query(f, "SELECT base_unit_id FROM products WHERE household_id=:hid")[0]["base_unit_id"]}
    path, body = (f"/products/{p['id']}/archive", {}) if archive == "product" else (f"/inventory-lots/{lot['id']}/archive", {"reason": "Retain"})
    assert f.request("POST", path, json=body).status_code == 200
    before = effects(f)
    assert deduction(f, p, lot, role="MEMBER").status_code == 409
    assert deduction(f, p, lot, "disposals", role="MEMBER").status_code == 422
    assert effects(f) == before
    assert deduction(f, p, lot, "disposals", role="MEMBER", body={"reason": "Archived disposition"}).status_code == 201
    assert adjust(f, p, lot, "3").status_code == 201
    assert f.request("POST", f"/inventory-lots/{lot['id']}/returns", json={"quantity": "1", "unit_id": p["base_unit_id"], "reason": "Archived return"}).status_code == 201
    assert invariant(f)[0]["remaining_quantity"] == 2
    assert f.request("GET", f"/inventory-lots/{lot['id']}").status_code == 200


@pytest.mark.parametrize("path,changes", [
    ("consumption", {"reason_code": "COOKING"}),
    ("consumption", {"cooking_history_id": 1}),
    ("consumption", {"reason_code": "OTHER"}),
    ("disposals", {"reason_code": "OTHER"}),
    ("disposals", {"reason": " "}),
    ("disposals", {"reason_code": "COOKING"}),
    ("consumption", {"allocations": []}),
])
def test_reason_and_server_only_cooking_validation_has_zero_effects(f, path, changes):
    p = product(f)
    lot = receipt(f, p).json()
    before = effects(f)
    assert deduction(f, p, lot, path, body=changes).status_code == 422
    assert effects(f) == before


@pytest.mark.parametrize("path", ["consumption", "disposals"])
def test_multi_lot_command_shortage_and_duplicate_overdemand_are_atomic(f, path):
    p = product(f)
    a, b = receipt(f, p).json(), receipt(f, p).json()
    before = effects(f)
    for allocations in ([allocation(p, a, "4"), allocation(p, a, "2")],
                        [allocation(p, a), allocation(p, b, "6")]):
        r = deduction(f, p, a, path, body={"allocations": allocations})
        assert r.status_code == 409 and r.json()["error_code"] == "INVENTORY_STOCK_SHORTAGE", r.text
        assert effects(f) == before


@pytest.mark.parametrize("resource", ["inventory-movements", "consumption", "inventory-adjustments", "disposals"])
def test_history_http_never_deletes_and_runtime_history_is_immutable(f, resource):
    p = product(f)
    lot = receipt(f, p).json()
    assert deduction(f, p, lot).status_code == 201
    assert deduction(f, p, lot, "disposals").status_code == 201
    assert adjust(f, p, lot, "2").status_code == 201
    before = effects(f)
    assert f.request("DELETE", "/" + resource).status_code == 405

    async def run():
        for table in HISTORY:
            for operation in (f"UPDATE {table} SET id=id", f"DELETE FROM {table}", f"TRUNCATE {table} CASCADE"):
                with pytest.raises(DBAPIError) as error:
                    async with f.db() as db, db.begin():
                        await db.execute(text(operation))
                assert error.value.orig.sqlstate in {"42501", "55000"}
    asyncio.run(run())
    assert effects(f) == before
    invariant(f)


@pytest.mark.parametrize("path,fail_at", [("consumption", "movement"), ("consumption", "detail"), ("disposals", "detail"), ("inventory-adjustments", "detail"), ("return", "link"), ("consumption", "audit")])
def test_failure_after_real_movement_detail_or_link_flush_rolls_back_every_effect(f, monkeypatch, path, fail_at):
    from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
    tx, lot = setup_purchase(f)
    p = {"base_unit_id": query(f, "SELECT base_unit_id FROM products WHERE household_id=:hid")[0]["base_unit_id"]}
    before = effects(f)
    finance = snapshot(f, tx["id"])
    original_create = SqlAlchemyInventoryRepository.create
    original_link = SqlAlchemyInventoryRepository.create_refund_link
    original_audit = SqlAlchemyFinanceRepository.audit

    async def create(self, resource, values):
        result = await original_create(self, resource, values)
        if (fail_at == "movement" and resource == "inventory-movements") or (fail_at == "detail" and resource in {"consumption", "disposals", "inventory-adjustments"}):
            raise RuntimeError("Injected after real flush")
        return result

    async def link(self, values):
        result = await original_link(self, values)
        if fail_at == "link":
            raise RuntimeError("Injected after real flush")
        return result

    async def audit(self, values):
        await original_audit(self, values)
        if fail_at == "audit":
            raise RuntimeError("Injected after real flush")

    def command():
        if path == "inventory-adjustments":
            return adjust(f, p, lot, "2", key="rollback-key")
        if path == "return":
            return f.request("POST", f"/inventory-lots/{lot['id']}/returns", key="rollback-key", json={"quantity": "1", "unit_id": p["base_unit_id"], "reason": "Return"})
        return deduction(f, p, lot, path, key="rollback-key")

    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyInventoryRepository, "create", create)
        patch.setattr(SqlAlchemyInventoryRepository, "create_refund_link", link)
        patch.setattr(SqlAlchemyFinanceRepository, "audit", audit)
        with pytest.raises(RuntimeError, match="Injected after real flush"):
            command()
    assert effects(f) == before and snapshot(f, tx["id"]) == finance
    assert command().status_code == 201
    invariant(f)


def test_new_command_idempotency_scope_payload_and_current_permission_replay(f):
    p = product(f)
    lot = receipt(f, p).json()
    r = deduction(f, p, lot, key="same", role="MEMBER")
    replay = deduction(f, p, lot, quantity="1.000000", key="same", role="MEMBER")
    assert r.status_code == replay.status_code == 201 and r.content == replay.content
    assert deduction(f, p, lot, quantity="2", key="same", role="MEMBER").status_code == 409
    assert deduction(f, p, lot, "disposals", key="same", role="MEMBER").status_code == 201
    assert deduction(f, p, lot, key="same").status_code == 201  # Different actor.

    async def demote():
        async with f.db() as db, db.begin():
            await db.execute(text("UPDATE household_members SET role_id=(SELECT id FROM roles WHERE code='VIEWER') WHERE id=:mid"), {"mid": f.actors["MEMBER"].member_id})
    asyncio.run(demote())
    before = effects(f)
    assert deduction(f, p, lot, key="same", role="MEMBER").status_code == 403
    assert effects(f) == before
    assert invariant(f)[0]["remaining_quantity"] == 2


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_explicit_same_lot_deductions_have_one_effect(f, same_key):
    p = product(f)
    lot = receipt(f, p).json()

    async def run():
        barrier = asyncio.Barrier(2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
            async def call(i):
                await barrier.wait()
                return await client.post(f"/api/v1/households/{f.hid}/consumption", headers=f.actors["MEMBER"].headers | {"Idempotency-Key": "deduct" if same_key else f"deduct-{i}"}, json={"allocations": [allocation(p, lot, "4")], "reason_code": "DAILY_USE"})
            a, b = await asyncio.gather(call(0), call(1))
            assert sorted([a.status_code, b.status_code]) == ([201, 201] if same_key else [201, 409])
            if same_key:
                assert a.content == b.content
    asyncio.run(run())
    assert invariant(f)[0]["remaining_quantity"] == 1
    assert len(query(f, "SELECT id FROM consumption_records WHERE household_id=:hid")) == 1
    assert len(query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key LIKE 'deduct%'")) == 1


@pytest.mark.parametrize("changes", [{"counted_quantity": "-1"}, {"counted_quantity": "NaN"}, {"counted_quantity": 1.5}, {"counted_quantity": "0.0000001"}, {"reason": " "}, {"reason": "x" * 1001}, {"quantity_delta": "1"}, {"unit_id": 999999}])
def test_adjustment_rejects_invalid_count_reason_and_client_delta(f, changes):
    p = product(f)
    lot = receipt(f, p).json()
    before = effects(f)
    assert adjust(f, p, lot, "1", body=changes).status_code == 422
    assert effects(f) == before


def test_exact_unit_normalization_zero_count_and_invalid_conversion(f):
    p = product(f)
    lot = receipt(f, p).json()
    units = {u["code"]: u["id"] for u in f.request("GET", "/measurement-units").json()["items"]}
    assert deduction(f, p, lot, body={"allocations": [allocation(p, lot, "0.001", unit_id=units["kg"]), allocation(p, lot, "1")]}).status_code == 201
    assert invariant(f)[0]["remaining_quantity"] == 3
    before = effects(f)
    assert adjust(f, p, lot, "0", body={"unit_id": units["ml"]}).status_code == 422
    assert effects(f) == before
    assert adjust(f, p, lot, "0", body={"unit_id": units["kg"]}).status_code == 201
    assert invariant(f)[0]["terminal_state"] == "MIXED"


def test_correction_and_command_ids_cannot_cross_lots_or_households(f):
    p = product(f)
    a, b = receipt(f, p).json(), receipt(f, p).json()
    before = effects(f)
    assert adjust(f, p, a, "4", body={"correction_of_movement_id": b["receipt_movement_id"]}).status_code == 404
    for path, body in [
        ("/consumption", {"allocations": [allocation(p, a) | {"lot_id": 999999}], "reason_code": "DAILY_USE"}),
        ("/inventory-adjustments", {"lot_id": 999999, "counted_quantity": "0", "unit_id": p["base_unit_id"], "reason": "Count"}),
        ("/inventory-lots/999999/returns", {"quantity": "1", "unit_id": p["base_unit_id"], "reason": "Return"}),
    ]:
        assert f.request("POST", path, json=body).status_code == 404
    # Outsider has access only to other_hid, never the household owning these lots.
    for path in ("/consumption", "/disposals", "/inventory-adjustments"):
        assert f.request("GET", path, role="OUTSIDER").status_code == 404
    assert f.client.post(f"/api/v1/households/{f.other_hid}/consumption", headers=f.actors["OUTSIDER"].headers | {"Idempotency-Key": "foreign"}, json={"allocations": [allocation(p, a)], "reason_code": "DAILY_USE"}).status_code == 404
    assert effects(f) == before


def test_pages_are_filtered_scoped_and_bounded(f):
    p = product(f)
    a, b = receipt(f, p).json(), receipt(f, p).json()
    for lot in (a, b):
        assert deduction(f, p, lot).status_code == 201
        assert deduction(f, p, lot, "disposals").status_code == 201
        assert adjust(f, p, lot, "2").status_code == 201
    for resource in ("consumption", "disposals", "inventory-adjustments", "inventory-movements"):
        page = f.request("GET", "/" + resource, params={"lot_id": a["id"], "limit": 1})
        assert page.status_code == 200, page.text
        data = page.json()
        assert len(data["items"]) == 1
        if resource == "inventory-movements":
            assert data["items"][0]["lot_id"] == a["id"] and data["next_cursor"]
            assert f.request("GET", "/" + resource, params={"lot_id": b["id"], "cursor": data["next_cursor"]}).status_code == 422
        else:
            mid = data["items"][0]["movement_id"]
            assert f.request("GET", f"/inventory-movements/{mid}").json()["lot_id"] == a["id"]
        assert f.request("GET", "/" + resource, params={"limit": 201}).status_code == 422
        assert f.request("GET", "/" + resource, params={"lot_id": 999999}).status_code == 404


def test_stock_only_return_requires_purchase_lot(f):
    p = product(f)
    lot = receipt(f, p).json()
    before = effects(f)
    r = f.request("POST", f"/inventory-lots/{lot['id']}/returns", json={"quantity": "1", "unit_id": p["base_unit_id"], "reason": "Return gift"})
    assert r.status_code == 409
    assert effects(f) == before


def test_explicit_writer_waits_for_product_before_lots_and_rechecks_locked_quantity(f):
    p = product(f)
    lot = receipt(f, p).json()

    async def run():
        async with f.db() as locker:
            await locker.begin()
            pid = await locker.scalar(text("SELECT pg_backend_pid()"))
            await locker.execute(text("SELECT id FROM products WHERE household_id=:hid AND id=:pid FOR UPDATE"), {"hid": f.hid, "pid": p["id"]})
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
                task = asyncio.create_task(client.post(f"/api/v1/households/{f.hid}/consumption", headers=f.actors["MEMBER"].headers | {"Idempotency-Key": "wait-product"}, json={"allocations": [allocation(p, lot, "4")], "reason_code": "DAILY_USE"}))
                try:
                    async with asyncio.timeout(10):
                        while True:
                            if task.done():
                                assert task.result().status_code == 201, task.result().text
                            async with f.db() as observer:
                                blocked = await observer.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)) AND query LIKE '%products%' AND query LIKE '%FOR UPDATE%')"), {"pid": pid})
                            if blocked:
                                break
                            await asyncio.sleep(0)
                    async with f.db() as observer, observer.begin():
                        await observer.execute(text("SELECT id FROM inventory_lots WHERE household_id=:hid AND id=:lid FOR UPDATE NOWAIT"), {"hid": f.hid, "lid": lot["id"]})
                    # Another writer changes the count while the HTTP command waits.
                    mid = await locker.scalar(text("INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at,reason) VALUES (:hid,:lid,'ADJUST_OUT',-3,now(),'Locked recount') RETURNING id"), {"hid": f.hid, "lid": lot["id"]})
                    await locker.execute(text("INSERT INTO inventory_adjustments(household_id,movement_id,counted_quantity,reason) VALUES (:hid,:mid,2,'Locked recount')"), {"hid": f.hid, "mid": mid})
                    await locker.execute(text("UPDATE inventory_lots SET remaining_quantity=2 WHERE household_id=:hid AND id=:lid"), {"hid": f.hid, "lid": lot["id"]})
                    await locker.commit()
                    r = await task
                    assert r.status_code == 409 and r.json()["error_code"] == "INVENTORY_STOCK_SHORTAGE"
                finally:
                    await locker.rollback()
                    if not task.done():
                        task.cancel()
    asyncio.run(run())
    assert invariant(f)[0]["remaining_quantity"] == 2
    assert not query(f, "SELECT id FROM consumption_records WHERE household_id=:hid")
    assert not query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='wait-product'")


def test_adjustment_response_matches_plan_detail_contract_and_replays(f):
    """Catches P2 review finding: adjustment must return its typed detail DTO."""
    p = product(f)
    lot = receipt(f, p).json()
    kg = next(u["id"] for u in f.request("GET", "/measurement-units").json()["items"] if u["code"] == "kg")
    r = adjust(f, p, lot, "0.002", key="count-contract", body={"unit_id": kg})
    assert r.status_code == 201, r.text
    data = r.json()
    assert set(data) == {"id", "household_id", "movement_id", "counted_quantity", "reason"}
    assert data["household_id"] == f.hid and Decimal(data["counted_quantity"]) == 2
    assert data["reason"] == "Physical recount"
    persisted = query(f, "SELECT id,movement_id,counted_quantity FROM inventory_adjustments WHERE household_id=:hid")
    assert len(persisted) == 1 and persisted[0]["id"] == data["id"] and persisted[0]["movement_id"] == data["movement_id"] and persisted[0]["counted_quantity"] == 2
    replay = adjust(f, p, lot, "0.002000", key="count-contract", body={"unit_id": kg})
    assert replay.status_code == 201 and replay.content == r.content
    schema = f.app.openapi()["paths"]["/api/v1/households/{household_id}/inventory-adjustments"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/AdjustmentResponse"}


def test_multi_purchase_command_success_and_second_detail_failure_roll_back_every_lot(f, monkeypatch):
    from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
    a_tx, a = setup_purchase(f)
    b_tx, b = setup_purchase(f)
    p = {"base_unit_id": query(f, "SELECT base_unit_id FROM products WHERE household_id=:hid ORDER BY id")[0]["base_unit_id"]}
    body = {"allocations": [allocation(p, b, "2"), allocation(p, a, "3")], "reason_code": "CHECKOUT"}
    before = effects(f)
    finance = [snapshot(f, tx["id"]) for tx in (a_tx, b_tx)]
    original = SqlAlchemyInventoryRepository.create
    details = 0

    async def fail_second(self, resource, values):
        nonlocal details
        result = await original(self, resource, values)
        if resource == "consumption":
            details += 1
            if details == 2:
                # First lot projection/event/detail/audit really exist in this UoW.
                assert await self.session.scalar(text("SELECT remaining_quantity FROM inventory_lots WHERE household_id=:hid AND id=:lid"), {"hid": f.hid, "lid": a["id"]}) == 2
                raise RuntimeError("Injected second real detail flush")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyInventoryRepository, "create", fail_second)
        with pytest.raises(RuntimeError, match="second real detail"):
            f.request("POST", "/consumption", json=body, key="multi-purchase")
    assert details == 2 and effects(f) == before
    assert [snapshot(f, tx["id"]) for tx in (a_tx, b_tx)] == finance
    r = f.request("POST", "/consumption", json=body, key="multi-purchase")
    assert r.status_code == 201, r.text
    assert len(r.json()["movement_ids"]) == len(r.json()["consumption_record_ids"]) == 2
    assert [row["remaining_quantity"] for row in invariant(f)] == [2, 3]
    movements = query(f, "SELECT lot_id,transaction_id,quantity_delta FROM inventory_movements WHERE household_id=:hid AND kind='CONSUME' ORDER BY id")
    assert [(row["lot_id"], row["transaction_id"], row["quantity_delta"]) for row in movements] == [(a["id"], a_tx["id"], -3), (b["id"], b_tx["id"], -2)]
    assert [snapshot(f, tx["id"]) for tx in (a_tx, b_tx)] == finance


@pytest.mark.parametrize("lock_kind", ["original", "account"])
def test_batch_command_locks_originals_and_accounts_ascending_before_products(f, lock_kind):
    from test_finance_transactions import account, payment, create_draft, post
    a1, a2 = account(f), account(f)
    lots, txs = [], []
    p = product(f)
    for aid in (a2, a1):  # Original order deliberately differs from account order.
        tx = create_draft(f, items=[{"line_no": 1, "description": "Rice", "quantity": "1", "net_amount": "12.30", "product_id": p["id"], "base_quantity": "5"}])
        posted = post(f, tx, [payment(aid)])
        assert posted.status_code == 200, posted.text
        txs.append(tx)
        lots.append(receipt(f, p, source_kind="PURCHASE", purchase_item_id=posted.json()["items"][0]["id"]).json())
    table, low, high = ("transactions", txs[0]["id"], txs[1]["id"]) if lock_kind == "original" else ("accounts", a1, a2)

    async def run():
        async with f.db() as locker:
            await locker.begin()
            pid = await locker.scalar(text("SELECT pg_backend_pid()"))
            await locker.execute(text(f"SELECT id FROM {table} WHERE household_id=:hid AND id=:low FOR UPDATE"), {"hid": f.hid, "low": low})
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
                task = asyncio.create_task(client.post(f"/api/v1/households/{f.hid}/consumption", headers=f.actors["MEMBER"].headers | {"Idempotency-Key": "batch-lock-order"}, json={"allocations": [allocation(p, lot) for lot in reversed(lots)], "reason_code": "DAILY_USE"}))
                try:
                    async with asyncio.timeout(10):
                        while True:
                            async with f.db() as observer:
                                blocked = await observer.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)) AND query LIKE :pattern AND query LIKE '%FOR UPDATE%')"), {"pid": pid, "pattern": f"%{table}%"})
                            if blocked:
                                break
                            await asyncio.sleep(0)
                    async with f.db() as observer, observer.begin():
                        # Higher same-prefix row is still free while waiting on low.
                        await observer.execute(text(f"SELECT id FROM {table} WHERE household_id=:hid AND id=:high FOR UPDATE NOWAIT"), {"hid": f.hid, "high": high})
                        await observer.execute(text("SELECT id FROM products WHERE household_id=:hid AND id=:pid FOR UPDATE NOWAIT"), {"hid": f.hid, "pid": p["id"]})
                        await observer.execute(text("SELECT id FROM inventory_lots WHERE household_id=:hid FOR UPDATE NOWAIT"), {"hid": f.hid})
                    await locker.commit()
                    r = await task
                    assert r.status_code == 201, r.text
                finally:
                    await locker.rollback()
                    if not task.done():
                        task.cancel()
    asyncio.run(run())
    assert [row["remaining_quantity"] for row in invariant(f)] == [4, 4]
