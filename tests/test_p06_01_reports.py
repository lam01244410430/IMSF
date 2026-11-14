"""P06 Step 2 PROPOSAL contracts, exercised against disposable runtime PostgreSQL."""

import asyncio
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from test_finance_transactions import create_draft, post, query
from test_inventory_lots import product, receipt

ROOT = "/inventory/valuation"
KINDS = ("received", "remaining", "consumed", "disposed", "returned", "adjusted_out")


def kg_product(f):
    kg = next(u["id"] for u in f.request("GET", "/measurement-units").json()["items"] if u["code"] == "kg")
    return product(f, base_unit_id=kg)


def purchase_lot(f, p, *, unit_cost="20000", quantity="10"):
    draft = create_draft(f, currency_code="VND", total_amount="200000", items=[{
        "line_no": 1, "description": "Receipt valuation fixture", "quantity": "1",
        "net_amount": "200000", "product_id": p["id"], "base_quantity": quantity,
    }])
    tx = post(f, draft, []).json()
    r = receipt(f, p, quantity=quantity, source_kind="PURCHASE", purchase_item_id=tx["items"][0]["id"],
                unit_cost=unit_cost, cost_currency="VND" if unit_cost is not None else None)
    assert r.status_code == 201, r.text
    return r.json(), tx


def deduct(f, p, lot, kind, quantity, reason):
    r = f.request("POST", "/" + kind, json={"allocations": [{"lot_id": lot["id"],
        "quantity": quantity, "unit_id": p["base_unit_id"]}], "reason_code": reason,
        **({"reason": "Other disposal fixture"} if reason == "OTHER" else {})})
    assert r.status_code == 201, r.text
    return r.json()["movement_ids"][0]


def adjust(f, p, lot, counted, correction=None):
    r = f.request("POST", "/inventory-adjustments", json={"lot_id": lot["id"],
        "counted_quantity": counted, "unit_id": p["base_unit_id"], "reason": "Count correction",
        "correction_of_movement_id": correction})
    assert r.status_code == 201, r.text
    return r.json()["movement_id"]


def fixture_lots(f):
    p = kg_product(f)
    l1, tx = purchase_lot(f, p)
    l2 = receipt(f, p, quantity="5").json()
    l3 = receipt(f, p, source_kind="MANUAL", quantity="4", unit_cost="15000", cost_currency="VND").json()
    deduct(f, p, l1, "consumption", "4", "DAILY_USE")
    deduct(f, p, l1, "disposals", "1", "EXPIRED")
    deduct(f, p, l2, "consumption", "5", "DAILY_USE")
    deduct(f, p, l3, "disposals", "2", "SPOILED")
    return p, (l1, l2, l3), tx


def get_page(f, *, report_path=ROOT, **params):
    r = f.request("GET", report_path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def assert_amounts(row, quantities, values):
    for kind, q, v in zip(KINDS, quantities, values, strict=True):
        assert isinstance(row[kind + "_quantity"], str)
        assert Decimal(row[kind + "_quantity"]) == Decimal(q)
        amount = row[kind + "_value"]
        if v is None:
            assert amount is None
        else:
            assert isinstance(amount, str) and Decimal(amount) == Decimal(v)
    assert row["quantity_tied_out"] is True
    assert row["value_tied_out"] is (None if values[0] is None else True)


def test_valuation_section5_exact_fixture_and_purchase_agreement(f):
    p, lots, tx = fixture_lots(f)
    page = get_page(f)
    l1, l2, l3 = page["items"]
    assert [r["lot_id"] for r in page["items"]] == [r["id"] for r in lots]
    assert all(r["base_unit_id"] == p["base_unit_id"] for r in page["items"])
    assert_amounts(l1, ("10", "5", "4", "1", "0", "0"), ("200000", "100000", "80000", "20000", "0", "0"))
    assert_amounts(l2, ("5", "0", "5", "0", "0", "0"), (None,) * 6)
    assert_amounts(l3, ("4", "2", "0", "2", "0", "0"), ("60000", "30000", "0", "30000", "0", "0"))
    assert l2["unknown_cost"] is True and l2["reconciliation_status"] == "UNKNOWN_COST"
    assert l2["terminal_state"] == "CONSUMED"
    assert l1["purchase"]["item_id"] == tx["items"][0]["id"]
    assert Decimal(l1["purchase"]["net_amount"]) == 200000
    assert l1["purchase"]["status"] == "AGREEMENT"
    totals = page["totals_by_currency"]
    assert len(totals) == 1 and totals[0]["currency"] == "VND"
    assert [Decimal(totals[0][k + "_value"]) for k in KINDS] == [260000, 130000, 80000, 50000, 0, 0]
    unknown = page["unknown_cost"]
    assert unknown["count"] == 1 and unknown["items"][0]["lot_id"] == lots[1]["id"]
    assert Decimal(unknown["items"][0]["consumed_quantity"]) == 5
    assert not any("value" in key or "amount" in key for key in unknown["items"][0])
    summary = page["reconciliation"]
    assert summary["checked_lots"] == summary["quantity_tied_out_count"] == 3
    assert summary["value_tied_out_count"] == 2 and summary["purchase_agreement_count"] == 1
    assert summary["issues"] == {"count": 0, "items": []}
    for lot, expected in zip(lots, page["items"], strict=True):
        r = f.request("GET", ROOT + f"/{lot['id']}")
        assert r.status_code == 200 and r.json() == expected


@pytest.mark.parametrize("unit_cost,status", [("18000", "PURCHASE_MISMATCH"), (None, "UNKNOWN_COST")])
def test_valuation_purchase_mismatch_and_unknown_never_estimated(f, unit_cost, status):
    lot, _ = purchase_lot(f, kg_product(f), unit_cost=unit_cost)
    page = get_page(f)
    row = page["items"][0]
    assert row["reconciliation_status"] == row["purchase"]["status"] == status
    if unit_cost is None:
        assert all(row[k + "_value"] is None for k in KINDS)
        assert page["totals_by_currency"] is None
        assert page["unknown_cost"]["count"] == 1
        assert page["reconciliation"]["purchase_unknown_cost_count"] == 1
    else:
        assert Decimal(row["received_value"]) == 180000
        assert page["reconciliation"]["purchase_mismatch_count"] == 1
        assert page["reconciliation"]["issues"] == {"count": 1, "items": [{"lot_id": lot["id"], "code": "PURCHASE_MISMATCH"}]}


def test_valuation_adjust_in_corrections_net_by_original_kind_and_returns(f):
    p = kg_product(f)
    lot, _ = purchase_lot(f, p)
    consumed = deduct(f, p, lot, "consumption", "4", "DAILY_USE")
    corrected = adjust(f, p, lot, "8", consumed)  # CONSUME net 2.
    adjust(f, p, lot, "7", corrected)  # Correction of correction: CONSUME net 3.
    disposed = deduct(f, p, lot, "disposals", "1", "DAMAGED")
    adjust(f, p, lot, "7", disposed)  # DISPOSE net 0.
    r = f.request("POST", f"/inventory-lots/{lot['id']}/returns", json={"quantity": "1", "unit_id": p["base_unit_id"], "reason": "Stock return"})
    assert r.status_code == 201, r.text
    adjust(f, p, lot, "5")
    adjust(f, p, lot, "6")  # Ordinary adjustments net zero.
    row = get_page(f)["items"][0]
    assert_amounts(row, ("10", "6", "3", "0", "1", "0"), ("200000", "120000", "60000", "0", "20000", "0"))
    adjust(f, p, lot, "7")  # Ordinary inbound contributes negative adjusted-out.
    row = get_page(f)["items"][0]
    assert Decimal(row["adjusted_out_quantity"]) == -1
    assert row["quantity_tied_out"] and row["value_tied_out"]


@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "FINANCE_MANAGER", "INVENTORY_MANAGER", "MEMBER", "VIEWER"])
def test_valuation_view_all_six_roles(f, role):
    lot = receipt(f, kg_product(f)).json()
    for path in (ROOT, ROOT + f"/{lot['id']}"):
        assert f.request("GET", path, role=role).status_code == 200


def test_valuation_isolation_missing_auth_removed_member_and_invalid_filters(f):
    p = kg_product(f)
    lot = receipt(f, p).json()
    for path in (ROOT, ROOT + f"/{lot['id']}"):
        assert f.request("GET", path, role="OUTSIDER").status_code == 404
        assert f.client.get(f"/api/v1/households/{f.hid}" + path).status_code == 401
        r = f.client.get(f"/api/v1/households/{f.other_hid}" + path, headers=f.actors["OUTSIDER"].headers)
        assert r.status_code == (200 if path == ROOT else 404)
    for params in ({"product_id": 9223372036854775807}, {"lot_id": 9223372036854775807}):
        assert f.request("GET", ROOT, params=params).status_code == 404
    for params in ({"limit": 201}, {"lot_id": 0}, {"currency": "ZZZ"}, {"cursor": "garbage"}, {"cursor": "W10="}):
        assert f.request("GET", ROOT, params=params).status_code == 422
    async def remove():
        async with f.db() as db, db.begin():
            await db.execute(text("UPDATE household_members SET removed_at=now() WHERE household_id=:hid AND id=:mid"), {"hid": f.hid, "mid": f.actors["VIEWER"].member_id})
    asyncio.run(remove())
    assert f.request("GET", ROOT, role="VIEWER").status_code == 404


def test_valuation_currency_filters_pagination_full_scope_totals_and_archives(f):
    p, lots, _ = fixture_lots(f)
    usd = receipt(f, p, quantity="1", cost_currency="USD", unit_cost="0.123456789012").json()
    page = get_page(f, limit=1)
    assert len(page["items"]) == 1 and len(page["totals_by_currency"]) == 2
    assert set(page) == {"items", "next_cursor", "totals_by_currency", "unknown_cost", "reconciliation"}
    second = get_page(f, limit=1, cursor=page["next_cursor"])
    assert second["items"][0]["lot_id"] == lots[1]["id"]
    assert second["totals_by_currency"] == page["totals_by_currency"]
    assert second["unknown_cost"] == page["unknown_cost"]
    assert f.request("GET", ROOT, params={"cursor": page["next_cursor"], "currency": "VND"}).status_code == 422
    assert f.client.get(f"/api/v1/households/{f.other_hid}" + ROOT, headers=f.actors["OUTSIDER"].headers, params={"cursor": page["next_cursor"]}).status_code == 422
    assert len(get_page(f, currency="USD")["items"]) == 1
    assert get_page(f, currency="EUR")["totals_by_currency"] == []
    assert [r["lot_id"] for r in get_page(f, product_id=p["id"], lot_id=usd["id"])["items"]] == [usd["id"]]
    assert f.request("POST", f"/inventory-lots/{usd['id']}/archive", json={"reason": "Historical stock"}).status_code == 200
    assert f.request("POST", f"/products/{p['id']}/archive", json={}).status_code == 200
    assert f.client.post(f"/api/v1/households/{f.hid}/archive", headers=f.actors["OWNER"].headers).status_code == 204
    historical = get_page(f)
    assert len(historical["items"]) == 4
    assert historical["totals_by_currency"] == page["totals_by_currency"]
    assert historical["items"][-1]["archived_at"] is not None
    assert historical["items"][-1]["product_archived_at"] is not None
    assert len(get_page(f, archived=False)["items"]) == 3
    assert len(get_page(f, archived=True)["items"]) == 1


def test_valuation_exact_large_decimal_product_without_context_rounding(f):
    p = kg_product(f)
    r = receipt(f, p, quantity="99999999999999.999999", unit_cost="999999999999999999.999999999999", cost_currency="VND")
    assert r.status_code == 201, r.text
    row = get_page(f)["items"][0]
    assert row["received_value"] == "99999999999999999998999999999900.000000000000000001"


def household_snapshot(f):
    tables = query(f, "SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='household_id' ORDER BY table_name")
    return {t["table_name"]: query(f, f"SELECT row_to_json(t)::text AS bytes FROM {t['table_name']} t WHERE household_id=:hid ORDER BY row_to_json(t)::text") for t in tables}


def test_valuation_reports_change_no_stock_finance_history_or_operational_rows(f):
    _, lots, _ = fixture_lots(f)
    before = household_snapshot(f)
    page = get_page(f)
    get_page(f, limit=1)
    for lot in lots:
        assert f.request("GET", ROOT + f"/{lot['id']}").status_code == 200
    assert page["reconciliation"]["checked_lots"] == 3
    assert household_snapshot(f) == before


def test_valuation_one_read_only_snapshot_during_committed_stock_change(f, monkeypatch):
    from app.inventory.infrastructure.report_repository import SqlAlchemyInventoryReportRepository
    p = kg_product(f)
    lot, _ = purchase_lot(f, p)
    original = SqlAlchemyInventoryReportRepository.valuation_rows
    observed = []
    async def concurrent_read(self, hid, filters):
        settings = (await self.session.execute(text("SELECT current_setting('transaction_isolation'), current_setting('transaction_read_only')"))).one()
        observed.append(tuple(settings))
        # Access checks have established the report snapshot. Commit a real
        # movement in a different runtime transaction before the report SELECT.
        async with f.db() as writer, writer.begin():
            mid = await writer.scalar(text("INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at) VALUES (:hid,:lid,'CONSUME',-1,now()) RETURNING id"), {"hid": hid, "lid": lot["id"]})
            await writer.execute(text("INSERT INTO consumption_records(household_id,movement_id,reason_code) VALUES (:hid,:mid,'DAILY_USE')"), {"hid": hid, "mid": mid})
            await writer.execute(text("UPDATE inventory_lots SET remaining_quantity=9 WHERE household_id=:hid AND id=:lid"), {"hid": hid, "lid": lot["id"]})
        return await original(self, hid, filters)
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyInventoryReportRepository, "valuation_rows", concurrent_read)
        page = get_page(f)
    assert observed == [("repeatable read", "on")]
    assert Decimal(page["items"][0]["remaining_quantity"]) == 10
    assert Decimal(page["totals_by_currency"][0]["remaining_value"]) == 200000
    assert page["reconciliation"]["quantity_tied_out_count"] == 1
    assert Decimal(get_page(f)["items"][0]["remaining_quantity"]) == 9


def test_valuation_reversed_original_is_issue_without_suppressing_lot(f):
    p = kg_product(f)
    lot, tx = purchase_lot(f, p)
    # Defensive retained-data fixture: today's application correctly refuses a
    # stock-linked reversal. Seed a real unpaid reversal header through runtime
    # SQL to represent historical/imported records; no trigger/grant is bypassed.
    async def retained_reversal():
        async with f.db() as db, db.begin():
            rid = await db.scalar(text("""INSERT INTO transactions
                (household_id,kind,occurred_at,currency_code,total_amount,created_by_member_id,
                 original_transaction_id,reversal_reason)
                VALUES (:hid,'REVERSAL',now(),'VND',200000,:mid,:tid,'Retained fixture') RETURNING id"""),
                {"hid": f.hid, "mid": f.actors["OWNER"].member_id, "tid": tx["id"]})
            await db.execute(text("UPDATE transactions SET status='POSTED',posted_at=now() WHERE household_id=:hid AND id=:rid"), {"hid": f.hid, "rid": rid})
    asyncio.run(retained_reversal())
    before = household_snapshot(f)
    page = get_page(f)
    row = page["items"][0]
    assert Decimal(row["received_value"]) == Decimal(row["remaining_value"]) == 200000
    assert row["purchase"]["reversed_original"] is True
    assert page["reconciliation"]["issues"] == {"count": 1, "items": [{"lot_id": lot["id"], "code": "REVERSED_ORIGINAL"}]}
    assert household_snapshot(f) == before


def test_valuation_unknown_identifiers_bounded_with_complete_count(f):
    p = kg_product(f)
    ids = [receipt(f, p).json()["id"] for _ in range(101)]
    page = get_page(f, limit=1)
    assert page["unknown_cost"]["count"] == 101
    assert [r["lot_id"] for r in page["unknown_cost"]["items"]] == ids[:100]
    assert page["reconciliation"]["checked_lots"] == 101
    assert page["totals_by_currency"] is None
    assert get_page(f, cursor=page["next_cursor"], limit=200)["next_cursor"] is None


def test_valuation_issue_identifiers_bounded_and_tie_out_mismatch_exposed(f):
    p = kg_product(f)
    # Split receipt comparison remains per lot against the full item amount;
    # there is deliberately no pro-rata allocation in the proposed method.
    draft = create_draft(f, currency_code="VND", total_amount="200000", items=[{
        "line_no": 1, "description": "Split purchase", "quantity": "1",
        "net_amount": "200000", "product_id": p["id"], "base_quantity": "101"}])
    tx = post(f, draft, []).json()
    ids = []
    for _ in range(101):
        r = receipt(f, p, quantity="1", source_kind="PURCHASE", purchase_item_id=tx["items"][0]["id"], unit_cost="18000", cost_currency="VND")
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    page = get_page(f, limit=1)
    issues = page["reconciliation"]["issues"]
    assert issues["count"] == 101
    assert [r["lot_id"] for r in issues["items"]] == ids[:100]
    assert all(r["code"] == "PURCHASE_MISMATCH" for r in issues["items"])
    # Existing correction commands permit restoring more than the linked
    # deduction. Absolute per-kind netting then fails the proposed tie-out;
    # expose this valid retained shape as an issue, never silently repair it.
    lot = receipt(f, p, quantity="10", unit_cost="1", cost_currency="VND").json()
    consumed = deduct(f, p, lot, "consumption", "1", "DAILY_USE")
    deduct(f, p, lot, "disposals", "3", "DAMAGED")
    adjust(f, p, lot, "8", consumed)
    r = f.request("GET", ROOT + f"/{lot['id']}")
    assert r.status_code == 200
    row = r.json()
    assert row["quantity_tied_out"] is row["value_tied_out"] is False
    assert row["reconciliation_status"] == "TIE_OUT_MISMATCH"
    assert row["issues"] == ["TIE_OUT_MISMATCH"]


def test_valuation_empty_unknown_and_known_zero_have_distinct_money_totals(f):
    assert get_page(f)["totals_by_currency"] == []
    p = kg_product(f)
    unknown = receipt(f, p).json()
    page = get_page(f)
    assert page["totals_by_currency"] is None
    assert page["unknown_cost"]["count"] == 1
    assert all(page["items"][0][k + "_value"] is None for k in KINDS)
    known = receipt(f, p, cost_currency="VND", unit_cost="0").json()
    page = get_page(f)
    assert len(page["totals_by_currency"]) == 1
    assert page["totals_by_currency"][0]["currency"] == "VND"
    assert all(Decimal(page["totals_by_currency"][0][k + "_value"]) == 0 for k in KINDS)
    assert page["items"][1]["lot_id"] == known["id"]
    assert page["items"][1]["unknown_cost"] is False
    assert page["unknown_cost"]["items"][0]["lot_id"] == unknown["id"]


# P06 Step 3 PROPOSALS: root-event waste, household-local scope, no writers.
WASTE = "/inventory/waste-report"
NOVEMBER = {"from_date": "2026-11-01", "to_date": "2026-11-30"}


def waste_page(f, **params):
    # Reuse the report GET helper while preserving the valuation tests' default.
    return get_page(f, report_path=WASTE, **params)


def exact_rate(numerator, denominator):
    from decimal import localcontext
    with localcontext() as ctx:
        ctx.prec = 80
        return format(Decimal(numerator) / Decimal(denominator), "f")


def test_waste_report_section5_exact_fixture(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p, lots, _ = fixture_lots(f)
    assert waste_page(f, **NOVEMBER) == {
        "period": {**NOVEMBER, "timezone": "Asia/Ho_Chi_Minh"},
        "sections": [{
            "currency": "VND", "disposed": {"quantity": "3", "value": "50000"},
            "by_reason": [
                {"reason_code": "EXPIRED", "quantity": "1", "value": "20000"},
                {"reason_code": "SPOILED", "quantity": "2", "value": "30000"}],
            "by_period": [{"period": "2026-11", "quantity": "3", "value": "50000"}],
            "denominator": {"basis": "total_received_value_known_cost", "value": "260000", "scope": "same period and filters"},
            "waste_rate": exact_rate(50000, 260000)}],
        "by_product": [{"currency": "VND", "product_id": p["id"], "quantity": "3", "value": "50000"}],
        "next_cursor": None,
        "unknown_cost": {"disposed_quantity": "0", "consumed_quantity": "5", "by_reason": [], "lot_ids": [lots[1]["id"]], "count": 1},
        "reconciliation": {"status": "TIED_OUT", "issues": {"count": 0, "items": []}},
    }


def test_waste_report_consumption_is_not_waste(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p, lots, _ = fixture_lots(f)
    before = waste_page(f, **NOVEMBER)
    deduct(f, p, lots[2], "consumption", "2", "DAILY_USE")
    after = waste_page(f, **NOVEMBER)
    assert after == before
    assert after["unknown_cost"]["consumed_quantity"] == "5"
    assert after["unknown_cost"]["disposed_quantity"] == "0"


def test_waste_report_reason_filter_and_denominator_scope(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    fixture_lots(f)
    expired = waste_page(f, **NOVEMBER, reason="EXPIRED")["sections"][0]
    assert expired["disposed"] == {"quantity": "1", "value": "20000"}
    assert expired["denominator"]["value"] == "260000"
    assert expired["waste_rate"] == exact_rate(20000, 260000)
    damaged = waste_page(f, **NOVEMBER, reason="DAMAGED")["sections"][0]
    assert damaged["disposed"] == {"quantity": "0", "value": "0"}
    assert damaged["by_reason"] == damaged["by_period"] == []
    assert damaged["denominator"]["value"] == "260000"
    assert damaged["waste_rate"] == "0"


def test_waste_report_date_range_and_open_ended(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    fixture_lots(f)
    page = waste_page(f, from_date="2026-11-01", to_date="2026-11-12")
    assert page["sections"][0]["disposed"] == {"quantity": "0", "value": "0"}
    assert page["sections"][0]["denominator"]["value"] == "260000"
    assert page["sections"][0]["waste_rate"] == "0"
    expected = waste_page(f, **NOVEMBER)
    for filters in ({}, {"from_date": "2026-11-01"}, {"to_date": "2026-11-30"}):
        actual = waste_page(f, **filters)
        assert actual["period"] == {"from_date": filters.get("from_date"), "to_date": filters.get("to_date"), "timezone": "Asia/Ho_Chi_Minh"}
        assert {k: v for k, v in actual.items() if k != "period"} == {k: v for k, v in expected.items() if k != "period"}


def test_waste_report_disposal_outside_receipt_period_has_null_rate(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p = kg_product(f)
    lot = receipt(f, p, received_at="2026-10-15T10:00:00Z", unit_cost="20000", cost_currency="VND").json()
    deduct(f, p, lot, "disposals", "1", "EXPIRED")
    section = waste_page(f, **NOVEMBER)["sections"][0]
    assert section["disposed"] == {"quantity": "1", "value": "20000"}
    assert section["denominator"]["value"] == "0" and section["waste_rate"] is None


def test_waste_report_corrections_net_by_root_reason(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p = kg_product(f)
    lot = receipt(f, p, quantity="4", unit_cost="15000", cost_currency="VND").json()
    mid = deduct(f, p, lot, "disposals", "2", "SPOILED")
    correction = adjust(f, p, lot, "3", mid)
    section = waste_page(f, **NOVEMBER)["sections"][0]
    assert section["disposed"] == {"quantity": "1", "value": "15000"}
    assert section["by_reason"] == [{"reason_code": "SPOILED", "quantity": "1", "value": "15000"}]
    # A correction of a correction retains its root; fully corrected roots vanish.
    adjust(f, p, lot, "4", correction)
    page = waste_page(f, **NOVEMBER)
    assert page["by_product"] == []
    assert page["sections"][0]["by_reason"] == page["sections"][0]["by_period"] == []
    assert page["sections"][0]["disposed"] == {"quantity": "0", "value": "0"}


def test_waste_report_unknown_cost_disposed_never_estimated(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p = kg_product(f)
    lot = receipt(f, p).json()
    deduct(f, p, lot, "disposals", "1", "DAMAGED")
    page = waste_page(f, **NOVEMBER)
    assert page["sections"] == page["by_product"] == []
    assert page["unknown_cost"] == {"disposed_quantity": "1", "consumed_quantity": "0", "by_reason": [{"reason_code": "DAMAGED", "quantity": "1"}], "lot_ids": [lot["id"]], "count": 1}
    def quantity_keys(value):
        if isinstance(value, dict):
            assert not any("value" in key or "money" in key or "amount" in key or "cost" in key for key in value)
            for v in value.values():
                quantity_keys(v)
        elif isinstance(value, list):
            for v in value:
                quantity_keys(v)
    quantity_keys(page["unknown_cost"])
    # The precise Step 3 contract narrows unknown by_reason only.
    filtered = waste_page(f, **NOVEMBER, reason="EXPIRED")["unknown_cost"]
    assert filtered == page["unknown_cost"] | {"by_reason": []}
    assert waste_page(f, **NOVEMBER, currency="VND")["unknown_cost"]["count"] == 0


@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "FINANCE_MANAGER", "INVENTORY_MANAGER", "MEMBER", "VIEWER"])
def test_waste_report_all_six_roles_and_isolation(f, role):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p = kg_product(f)
    for _ in range(2):
        lot = receipt(f, p, unit_cost="1", cost_currency="VND").json()
        deduct(f, p, lot, "disposals", "1", "OTHER")
        p = kg_product(f)
    assert f.request("GET", WASTE, role=role, params=NOVEMBER).status_code == 200
    assert f.request("GET", WASTE, role="OUTSIDER", params=NOVEMBER).status_code == 404
    assert f.client.get(f"/api/v1/households/{f.hid}" + WASTE).status_code == 401
    page = waste_page(f, **NOVEMBER, limit=1)
    assert page["next_cursor"] is not None
    # Other household must have a valid timezone before checking its cursor.
    from types import SimpleNamespace
    configure_timezone(SimpleNamespace(db=f.db, hid=f.other_hid))
    r = f.client.get(f"/api/v1/households/{f.other_hid}" + WASTE, headers=f.actors["OUTSIDER"].headers, params=NOVEMBER | {"cursor": page["next_cursor"]})
    assert r.status_code == 422 and r.json()["error_code"] == "INVENTORY_INVALID_INPUT"


def test_waste_report_missing_and_invalid_timezone(f):
    from test_inventory_checkout import configure_timezone
    for name in (None, "Invalid/Timezone"):
        configure_timezone(f, name)
        r = f.request("GET", WASTE)
        assert r.status_code == 422 and r.json()["error_code"] == "INVENTORY_TIMEZONE_REQUIRED"
        r = f.request("GET", WASTE, params={"product_id": 9223372036854775807})
        assert r.status_code == 404 and r.json()["error_code"] == "INVENTORY_NOT_FOUND"
    # A real foreign product is also scoped before the timezone requirement.
    from types import SimpleNamespace
    other = SimpleNamespace(request=lambda method, path, **kw: f.client.request(method, f"/api/v1/households/{f.other_hid}" + path, headers=f.actors["OUTSIDER"].headers | {"Idempotency-Key": uuid4().hex}, **kw))
    foreign = kg_product(other)
    assert f.request("GET", WASTE, params={"product_id": foreign["id"]}).status_code == 404


def test_waste_report_invalid_filters_and_cursor_binding(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p, _, _ = fixture_lots(f)
    p2 = kg_product(f)
    lot = receipt(f, p2, unit_cost="1", cost_currency="VND").json()
    deduct(f, p2, lot, "disposals", "1", "OTHER")
    for params in ({"currency": "ZZZ"}, {"limit": 201}, {"limit": 0}, {"reason": "COOKING"}, {"product_id": 0}, {"from_date": "2026-12-01", "to_date": "2026-11-01"}, {"cursor": "garbage"}, {"cursor": "W10="}):
        r = f.request("GET", WASTE, params=params)
        assert r.status_code == 422 and r.json()["error_code"] == "INVENTORY_INVALID_INPUT"
    page = waste_page(f, **NOVEMBER, limit=1)
    for changed in ({"reason": "EXPIRED"}, {"currency": "VND"}, {"product_id": p["id"]}, {"from_date": "2026-11-02"}, {"to_date": "2026-11-29"}):
        assert f.request("GET", WASTE, params=NOVEMBER | {"cursor": page["next_cursor"]} | changed).status_code == 422


def test_waste_report_product_filter_and_by_product_pagination(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p, _, _ = fixture_lots(f)
    p2 = kg_product(f)
    lot = receipt(f, p2, unit_cost="2", cost_currency="VND").json()
    deduct(f, p2, lot, "disposals", "1", "OTHER")
    full = waste_page(f, **NOVEMBER)
    first = waste_page(f, **NOVEMBER, limit=1)
    second = waste_page(f, **NOVEMBER, limit=1, cursor=first["next_cursor"])
    assert first["by_product"] + second["by_product"] == full["by_product"]
    assert [r["product_id"] for r in full["by_product"]] == [p["id"], p2["id"]]
    assert second["next_cursor"] is None
    for key in ("sections", "unknown_cost", "reconciliation"):
        assert first[key] == second[key] == full[key]
    filtered = waste_page(f, **NOVEMBER, product_id=p2["id"])
    assert filtered["by_product"] == [{"currency": "VND", "product_id": p2["id"], "quantity": "1", "value": "2"}]
    assert filtered["sections"][0]["denominator"]["value"] == "10"
    assert filtered["unknown_cost"]["count"] == 0


def test_waste_report_currency_filter_and_no_combined_total(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p, _, _ = fixture_lots(f)
    empty = waste_page(f, **NOVEMBER, currency="EUR")
    assert empty["sections"] == empty["by_product"] == []
    usd = receipt(f, p, unit_cost="0.123456789012", cost_currency="USD").json()
    deduct(f, p, usd, "disposals", "1", "DAMAGED")
    page = waste_page(f, **NOVEMBER, currency="USD")
    assert [s["currency"] for s in page["sections"]] == ["USD"]
    assert page["sections"][0]["disposed"] == {"quantity": "1", "value": "0.123456789012"}
    assert set(page) == {"period", "sections", "by_product", "next_cursor", "unknown_cost", "reconciliation"}
    both = waste_page(f, **NOVEMBER)
    assert [s["currency"] for s in both["sections"]] == ["USD", "VND"]
    assert [(r["currency"], r["product_id"]) for r in both["by_product"]] == [("USD", p["id"]), ("VND", p["id"])]


def test_waste_report_read_only(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    fixture_lots(f)
    p = kg_product(f)
    lot = receipt(f, p, unit_cost="1", cost_currency="VND").json()
    deduct(f, p, lot, "disposals", "1", "OTHER")
    before = household_snapshot(f)
    waste_page(f, **NOVEMBER)
    first = waste_page(f, **NOVEMBER, limit=1)
    waste_page(f, **NOVEMBER, reason="SPOILED")
    waste_page(f, **NOVEMBER, limit=1, cursor=first["next_cursor"])
    assert household_snapshot(f) == before


def test_waste_report_snapshot_is_read_only(f, monkeypatch):
    from test_inventory_checkout import configure_timezone
    from app.inventory.infrastructure.report_repository import SqlAlchemyInventoryReportRepository
    configure_timezone(f)
    p = kg_product(f)
    lot, _ = purchase_lot(f, p)
    original = SqlAlchemyInventoryReportRepository.waste_rows
    observed = []
    async def concurrent_read(self, hid, filters):
        settings = (await self.session.execute(text("SELECT current_setting('transaction_isolation'), current_setting('transaction_read_only')"))).one()
        observed.append(tuple(settings))
        async with f.db() as writer, writer.begin():
            mid = await writer.scalar(text("INSERT INTO inventory_movements(household_id,lot_id,kind,quantity_delta,occurred_at) VALUES (:hid,:lid,'DISPOSE',-1,now()) RETURNING id"), {"hid": hid, "lid": lot["id"]})
            await writer.execute(text("INSERT INTO disposal_records(household_id,movement_id,reason_code) VALUES (:hid,:mid,'EXPIRED')"), {"hid": hid, "mid": mid})
            await writer.execute(text("UPDATE inventory_lots SET remaining_quantity=9 WHERE household_id=:hid AND id=:lid"), {"hid": hid, "lid": lot["id"]})
        return await original(self, hid, filters)
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyInventoryReportRepository, "waste_rows", concurrent_read)
        page = waste_page(f, **NOVEMBER)
    assert observed == [("repeatable read", "on")]
    assert page["sections"][0]["disposed"] == {"quantity": "0", "value": "0"}
    assert page["sections"][0]["denominator"]["value"] == "200000"
    assert page["reconciliation"] == {"status": "TIED_OUT", "issues": {"count": 0, "items": []}}
    assert waste_page(f, **NOVEMBER)["sections"][0]["disposed"] == {"quantity": "1", "value": "20000"}


def test_waste_report_root_month_local_midnight_and_later_correction(f, monkeypatch):
    from test_inventory_checkout import configure_timezone
    from test_inventory_fefo import freeze_inventory_clock
    configure_timezone(f)
    p = kg_product(f)
    lot = receipt(f, p, quantity="10", unit_cost="2", cost_currency="VND", received_at="2026-10-31T17:00:00Z").json()
    # Vietnam midnight is still October in UTC. The preceding instant is out.
    freeze_inventory_clock(monkeypatch, datetime.fromisoformat("2026-10-31T16:59:59+00:00"))
    deduct(f, p, lot, "disposals", "1", "DAMAGED")
    freeze_inventory_clock(monkeypatch, datetime.fromisoformat("2026-10-31T17:00:00+00:00"))
    root = deduct(f, p, lot, "disposals", "2", "SPOILED")
    freeze_inventory_clock(monkeypatch, datetime.fromisoformat("2026-11-30T16:59:59+00:00"))
    deduct(f, p, lot, "disposals", "1", "EXPIRED")
    freeze_inventory_clock(monkeypatch, datetime.fromisoformat("2026-11-30T17:00:00+00:00"))
    deduct(f, p, lot, "disposals", "1", "DAMAGED")
    # A December correction belongs to November's SPOILED root.
    adjust(f, p, lot, "6", root)
    nov = waste_page(f, **NOVEMBER)["sections"][0]
    assert nov["disposed"] == {"quantity": "2", "value": "4"}
    assert nov["by_period"] == [{"period": "2026-11", "quantity": "2", "value": "4"}]
    assert nov["by_reason"] == [{"reason_code": "EXPIRED", "quantity": "1", "value": "2"}, {"reason_code": "SPOILED", "quantity": "1", "value": "2"}]
    assert nov["denominator"]["value"] == "20"
    dec = waste_page(f, from_date="2026-12-01", to_date="2026-12-31")["sections"][0]
    assert dec["disposed"] == {"quantity": "1", "value": "2"}
    assert dec["waste_rate"] is None
    assert [r["period"] for r in waste_page(f)["sections"][0]["by_period"]] == ["2026-10", "2026-11", "2026-12"]


def test_waste_report_overcorrection_lists_lot_without_blocking_read(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p = kg_product(f)
    lot = receipt(f, p, quantity="10", unit_cost="2", cost_currency="VND").json()
    root = deduct(f, p, lot, "disposals", "1", "SPOILED")
    deduct(f, p, lot, "disposals", "3", "EXPIRED")
    adjust(f, p, lot, "8", root)  # SPOILED root net +1, EXPIRED root net -3.
    page = waste_page(f, **NOVEMBER)
    assert page["sections"][0]["disposed"] == {"quantity": "4", "value": "8"}
    assert page["reconciliation"] == {"status": "TIE_OUT_MISMATCH", "issues": {"count": 1, "items": [{"lot_id": lot["id"], "code": "TIE_OUT_MISMATCH"}]}}
    assert waste_page(f, **NOVEMBER, reason="EXPIRED")["reconciliation"]["status"] == "TIED_OUT"


def test_waste_report_archived_scope_and_known_zero_are_retained(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p = kg_product(f)
    lot = receipt(f, p, unit_cost="0", cost_currency="VND").json()
    deduct(f, p, lot, "disposals", "1", "DAMAGED")
    before = waste_page(f, **NOVEMBER)
    assert before["sections"][0]["disposed"] == {"quantity": "1", "value": "0"}
    assert before["sections"][0]["waste_rate"] is None
    assert f.request("POST", f"/inventory-lots/{lot['id']}/archive", json={"reason": "Historical report"}).status_code == 200
    assert f.request("POST", f"/products/{p['id']}/archive", json={}).status_code == 200
    assert f.client.post(f"/api/v1/households/{f.hid}/archive", headers=f.actors["OWNER"].headers).status_code == 204
    assert waste_page(f, **NOVEMBER) == before


def test_waste_report_unknown_identifiers_first_100_with_complete_count(f):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)
    p = kg_product(f)
    ids = []
    for _ in range(101):
        lot = receipt(f, p).json()
        ids.append(lot["id"])
        deduct(f, p, lot, "disposals", "1", "DAMAGED")
    unknown = waste_page(f, **NOVEMBER, limit=1)["unknown_cost"]
    assert unknown["lot_ids"] == ids[:100] and unknown["count"] == 101
    assert unknown["disposed_quantity"] == "101"
