"""Step 6 PROPOSAL: household-scoped read-only stock/finance diagnostics."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from test_finance_transactions import create_draft, query
from test_inventory_lots import product, purchase
from test_inventory_checkout import configure_timezone, purchase_body, demand
from test_inventory_cooking import recipe, cook, ingredient, state

CATEGORIES = (
    "projection_mismatches",
    "receipt_anomalies",
    "detail_misalignments",
    "source_cap_violations",
    "terminal_state_inconsistencies",
    "purchase_link_inconsistencies",
    "receipt_posting_mismatches",
)


def report(f, **filters):
    r = f.request("GET", "/inventory/integrity", params=filters)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["limit_per_category"] == 100
    assert set(body) == {
        *CATEGORIES,
        "unresolved_refund_inventory_links",
        "limit_per_category",
    }
    return body


def assert_clean(body):
    for category in CATEGORIES:
        assert body[category] == {"count": 0, "items": []}, (category, body[category])


def checkout(f, p, *, paid=False):
    from test_finance_transactions import account, payment

    tx, body = purchase_body(f, p, payments=[payment(account(f))] if paid else [])
    r = f.request("POST", "/checkout/purchases", json=body)
    assert r.status_code == 201, r.text
    return tx, r.json()


@pytest.mark.parametrize("paid", [False, True])
def test_purchase_receipt_has_matching_finance_posting(f, paid):
    tx, result = checkout(f, product(f), paid=paid)
    rows = query(
        f,
        "SELECT transaction_id FROM inventory_movements WHERE household_id=:hid ORDER BY id",
    )
    assert [r["transaction_id"] for r in rows] == [tx["id"], tx["id"]]
    assert result["transaction"]["status"] == "POSTED"
    assert_clean(report(f))


def test_purchase_lot_traces_to_settled_expense(f):
    p = product(f)
    tx, result = checkout(f, p)
    rows = query(
        f,
        """SELECT t.status,t.kind,i.product_id,i.base_quantity,sum(l.received_quantity) AS received
        FROM inventory_lots l JOIN transaction_items i ON (i.household_id,i.id)=(l.household_id,l.purchase_item_id)
        JOIN transactions t ON (t.household_id,t.id)=(i.household_id,i.transaction_id)
        WHERE l.household_id=:hid GROUP BY t.status,t.kind,i.product_id,i.base_quantity""",
    )
    assert rows == [
        dict(
            status="POSTED",
            kind="EXPENSE",
            product_id=p["id"],
            base_quantity=Decimal(5),
            received=Decimal(5),
        )
    ]
    assert_clean(report(f, lot_id=result["lot_ids"][0]))


def test_integrity_read_reports_clean_on_healthy_household(f):
    configure_timezone(f)
    p = product(f)
    tx, result = checkout(f, p, paid=True)
    assert (
        f.request("POST", "/checkout/deductions", json=demand(p, "1")).status_code
        == 201
    )
    r = recipe(f, p, ingredients=[ingredient(p, "1")])
    assert cook(f, r).status_code == 201
    lid = result["lot_ids"][1]
    returned = f.request(
        "POST",
        f"/inventory-lots/{lid}/returns",
        json={
            "quantity": "1",
            "unit_id": p["base_unit_id"],
            "reason": "Return surplus",
        },
    )
    assert returned.status_code == 201, returned.text
    before = state(f) | {
        t: query(f, f"SELECT * FROM {t} WHERE household_id=:hid ORDER BY id")
        for t in ("inventory_adjustments", "disposal_records", "refund_inventory_links")
    }
    body = report(f)
    assert_clean(body)
    facts = body["unresolved_refund_inventory_links"]
    assert facts["count"] == len(facts["items"]) == 1
    (fact,) = facts["items"]
    assert fact["link_id"] == returned.json()["refund_inventory_link_ids"][0]
    assert fact["transaction_id"] == tx["id"] and fact["lot_id"] == lid
    assert fact["code"] == "UNRESOLVED_REFUND_INVENTORY_LINK"
    assert "resolved" not in fact
    assert report(f, product_id=p["id"], lot_id=lid) == body
    after = state(f) | {
        t: query(f, f"SELECT * FROM {t} WHERE household_id=:hid ORDER BY id")
        for t in ("inventory_adjustments", "disposal_records", "refund_inventory_links")
    }
    assert after == before


async def raw_lots(url, f, p, tx, count, *, transaction_id):
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as db:
            ids = []
            for _ in range(count):
                lid = await db.scalar(
                    text("""INSERT INTO inventory_lots
                    (household_id,product_id,source_kind,purchase_item_id,received_at,received_quantity,remaining_quantity)
                    VALUES (:hid,:pid,'PURCHASE',:iid,now(),1,1) RETURNING id"""),
                    dict(hid=f.hid, pid=p["id"], iid=tx["items"][0]["id"]),
                )
                await db.execute(
                    text("""INSERT INTO inventory_movements
                    (household_id,lot_id,kind,quantity_delta,occurred_at,transaction_id)
                    VALUES (:hid,:lid,'RECEIPT',1,now(),:tid)"""),
                    dict(hid=f.hid, lid=lid, tid=transaction_id),
                )
                ids.append(lid)
            return ids
    finally:
        await engine.dispose()


def test_integrity_read_flags_unsettled_purchase_link(f, finance_database_urls):
    p = product(f)
    tx = create_draft(
        f,
        items=[
            dict(
                line_no=1,
                description="Draft purchase",
                quantity="1",
                net_amount="12.30",
                product_id=p["id"],
                base_quantity="1",
            )
        ],
    )
    # Frozen revision 7 rejects even owner INSERTs referencing DRAFT. No bypass.
    with pytest.raises(DBAPIError) as error:
        asyncio.run(
            raw_lots(finance_database_urls[0], f, p, tx, 1, transaction_id=tx["id"])
        )
    assert error.value.orig.sqlstate == "55000"
    assert query(f, "SELECT id FROM inventory_lots WHERE household_id=:hid") == []
    assert_clean(report(f))


def test_receipt_posting_mismatches_are_bounded_counted_filtered_and_read_only(
    f, finance_database_urls
):
    p = product(f)
    tx = purchase(f, p, quantity="101", paid=False)
    # A null receipt transaction pointer is legal under revision 7; do not alter guards.
    ids = asyncio.run(
        raw_lots(finance_database_urls[0], f, p, tx, 101, transaction_id=None)
    )
    before = state(f)
    body = report(f)
    group = body["receipt_posting_mismatches"]
    assert group["count"] == 101 and len(group["items"]) == 100
    assert [x["lot_id"] for x in group["items"]] == ids[:100]
    assert all(x["transaction_id"] == tx["id"] for x in group["items"])
    assert all(
        body[k]["count"] == 0 for k in CATEGORIES if k != "receipt_posting_mismatches"
    )
    filtered = report(f, lot_id=ids[-1])
    assert filtered["receipt_posting_mismatches"]["count"] == 1
    assert filtered["receipt_posting_mismatches"]["items"][0]["lot_id"] == ids[-1]
    assert state(f) == before


def test_integrity_read_scope_and_permissions(f):
    p = product(f)
    _, result = checkout(f, p)
    foreign = f.client.post(
        f"/api/v1/households/{f.other_hid}/products",
        headers=f.actors["OUTSIDER"].headers | {"Idempotency-Key": "foreign-product"},
        json={"name": "Foreign rice", "base_unit_id": p["base_unit_id"]},
    ).json()
    foreign_lot = f.client.post(
        f"/api/v1/households/{f.other_hid}/inventory-lots",
        headers=f.actors["OUTSIDER"].headers | {"Idempotency-Key": "foreign-lot"},
        json={
            "product_id": foreign["id"],
            "quantity": "1",
            "unit_id": p["base_unit_id"],
            "source_kind": "GIFT",
            "received_at": "2026-11-11T10:00:00Z",
        },
    ).json()
    for role in (
        "OWNER",
        "ADMIN",
        "FINANCE_MANAGER",
        "INVENTORY_MANAGER",
        "MEMBER",
        "VIEWER",
    ):
        assert f.request("GET", "/inventory/integrity", role=role).status_code == 200
    for filters in ({"product_id": foreign["id"]}, {"lot_id": foreign_lot["id"]}):
        assert (
            f.request(
                "GET", "/inventory/integrity", params=filters, role="VIEWER"
            ).status_code
            == 404
        )
    assert f.request("GET", "/inventory/integrity", role="OUTSIDER").status_code == 404
    assert (
        f.client.get(f"/api/v1/households/{f.hid}/inventory/integrity").status_code
        == 401
    )
    for filters in ({"product_id": 0}, {"lot_id": -1}, {"product_id": "bad"}):
        assert (
            f.request("GET", "/inventory/integrity", params=filters).status_code == 422
        )
    assert_clean(report(f, product_id=p["id"], lot_id=result["lot_ids"][0]))


@pytest.mark.parametrize(
    "kind,terminal",
    [
        ("CONSUME", "CONSUMED"),
        ("DISPOSE", "DISCARDED"),
        ("ADJUST_OUT", "ADJUSTED_OUT"),
        ("RETURN", "RETURNED"),
        ("MIXED", "MIXED"),
    ],
)
def test_integrity_read_clean_for_terminal_details_and_replenishment(f, kind, terminal):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)  # Step 4 lot GET requires explicit household timezone.
    from test_inventory_lots import receipt

    p = product(f)
    if kind == "RETURN":
        tx = purchase(f, p, paid=False)
        lot = receipt(
            f, p, source_kind="PURCHASE", purchase_item_id=tx["items"][0]["id"]
        ).json()
    else:
        lot = receipt(f, p).json()
    lid, unit = lot["id"], p["base_unit_id"]
    if kind in {"CONSUME", "MIXED"}:
        assert (
            f.request(
                "POST",
                "/consumption",
                json={
                    "allocations": [
                        {
                            "lot_id": lid,
                            "quantity": "5" if kind == "CONSUME" else "2",
                            "unit_id": unit,
                        }
                    ],
                    "reason_code": "DAILY_USE",
                },
            ).status_code
            == 201
        )
    if kind in {"DISPOSE", "MIXED"}:
        assert (
            f.request(
                "POST",
                "/disposals",
                json={
                    "allocations": [
                        {
                            "lot_id": lid,
                            "quantity": "5" if kind == "DISPOSE" else "3",
                            "unit_id": unit,
                        }
                    ],
                    "reason_code": "DAMAGED",
                },
            ).status_code
            == 201
        )
    if kind == "ADJUST_OUT":
        assert (
            f.request(
                "POST",
                "/inventory-adjustments",
                json={
                    "lot_id": lid,
                    "counted_quantity": "0",
                    "unit_id": unit,
                    "reason": "Recount",
                },
            ).status_code
            == 201
        )
    if kind == "RETURN":
        assert (
            f.request(
                "POST",
                f"/inventory-lots/{lid}/returns",
                json={"quantity": "5", "unit_id": unit, "reason": "Surplus"},
            ).status_code
            == 201
        )
    assert (
        f.request("GET", f"/inventory-lots/{lid}").json()["terminal_state"] == terminal
    )
    assert_clean(report(f))
    assert (
        f.request(
            "POST",
            "/inventory-adjustments",
            json={
                "lot_id": lid,
                "counted_quantity": "1",
                "unit_id": unit,
                "reason": "Replenish within cap",
            },
        ).status_code
        == 201
    )
    assert f.request("GET", f"/inventory-lots/{lid}").json()["terminal_state"] is None
    assert (
        f.request(
            "POST", f"/inventory-lots/{lid}/archive", json={"reason": "Retain"}
        ).status_code
        == 200
    )
    assert_clean(report(f))
