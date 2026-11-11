"""Exact existing role grants; proposal routes never infer rank inheritance."""

import asyncio
import pytest
from sqlalchemy import text
from test_inventory_lots import product, receipt
from test_finance_transactions import query

ROLES = ["OWNER", "ADMIN", "FINANCE_MANAGER", "INVENTORY_MANAGER", "MEMBER", "VIEWER"]


@pytest.mark.parametrize("role", ROLES)
def test_every_route_uses_confirmed_explicit_role_matrix(f, role):
    p = product(f)
    lot = receipt(f, p).json()
    c = f.request("POST", "/product-categories", json={"name": "Dry food"}).json()
    read_paths = [
        "/measurement-units",
        "/unit-conversions",
        "/product-categories",
        f"/product-categories/{c['id']}",
        "/products",
        f"/products/{p['id']}",
        "/inventory-lots",
        f"/inventory-lots/{lot['id']}",
        "/inventory-movements",
        f"/inventory-movements/{lot['receipt_movement_id']}",
    ]
    for path in read_paths:
        assert f.request("GET", path, role=role).status_code == 200, path
    allowed = role in {"OWNER", "INVENTORY_MANAGER"}
    cases = [
        ("POST", "/product-categories", {"name": "Other"}),
        ("PATCH", f"/product-categories/{c['id']}", {"name": "Renamed"}),
        ("POST", f"/product-categories/{c['id']}/archive", {}),
        ("POST", "/products", {"name": "New", "base_unit_id": p["base_unit_id"]}),
        ("PATCH", f"/products/{p['id']}", {"name": "Rice renamed"}),
        (
            "POST",
            "/inventory-lots",
            {
                "product_id": p["id"],
                "source_kind": "MANUAL",
                "quantity": "1",
                "unit_id": p["base_unit_id"],
                "received_at": "2026-11-11T10:00:00Z",
            },
        ),
        (
            "PATCH",
            f"/inventory-lots/{lot['id']}",
            {"expires_on": None, "reason": "Label review"},
        ),
        ("POST", f"/inventory-lots/{lot['id']}/archive", {"reason": "Retain"}),
        ("POST", f"/products/{p['id']}/archive", {}),
    ]
    for method, path, body in cases:
        r = f.request(method, path, role=role, json=body)
        assert (
            r.status_code
            == (201 if method == "POST" and not path.endswith("archive") else 200)
            if allowed
            else r.status_code == 403
        ), (role, path, r.text)
    assert len(query(f, "SELECT id FROM inventory_lots WHERE household_id=:hid")) == (
        2 if allowed else 1
    )


def test_later_command_routes_are_absent(f):
    for path in [
        "/recipes",
        "/recipe-cooking-history",
    ]:
        assert f.request("POST", path, json={}).status_code == 404
    assert f.request("POST", "/inventory-movements", json={}).status_code == 405


def test_cross_household_path_body_and_filter_ids_return_404(f):
    p = product(f)

    async def seed():
        async with f.db() as db, db.begin():
            category = await db.scalar(
                text(
                    "INSERT INTO product_categories(household_id,name) VALUES (:hid,'Foreign') RETURNING id"
                ),
                {"hid": f.other_hid},
            )
            pid = await db.scalar(
                text(
                    "INSERT INTO products(household_id,name,base_unit_id) VALUES (:hid,'Foreign',:unit) RETURNING id"
                ),
                {"hid": f.other_hid, "unit": p["base_unit_id"]},
            )
            return category, pid

    cid, pid = asyncio.run(seed())
    for method, path, kwargs in [
        ("GET", f"/products/{pid}", {}),
        ("GET", "/products", {"params": {"category_id": cid}}),
        ("GET", "/inventory-lots", {"params": {"product_id": pid}}),
        (
            "POST",
            "/products",
            {
                "json": {
                    "name": "Invalid",
                    "base_unit_id": p["base_unit_id"],
                    "category_id": cid,
                }
            },
        ),
        ("PATCH", f"/products/{p['id']}", {"json": {"category_id": cid}}),
    ]:
        assert f.request(method, path, **kwargs).status_code == 404
    assert f.request("GET", "/products", role="OUTSIDER").status_code == 404


@pytest.mark.parametrize(
    "condition,status",
    [
        ("pending", 403),
        ("disabled", 401),
        ("removed", 404),
        ("revoked", 401),
        ("archived", 409),
        ("role", 403),
    ],
)
def test_pending_disabled_removed_revoked_and_archived_replays_denied(
    f, condition, status
):
    p = product(f)
    path, body = f"/products/{p['id']}", {"name": "Changed"}
    assert f.request("PATCH", path, key="saved", json=body).status_code == 200
    sql = {
        "pending": "UPDATE users SET state='PENDING' WHERE id=:uid",
        "disabled": "UPDATE users SET state='DISABLED' WHERE id=:uid",
        "removed": "UPDATE household_members SET removed_at=now() WHERE id=:mid",
        "revoked": "UPDATE auth_sessions SET revoked_at=now() WHERE id=:sid",
        "archived": "UPDATE households SET archived_at=now() WHERE id=:hid",
        "role": "UPDATE household_members SET role_id=(SELECT id FROM roles WHERE code='VIEWER') WHERE id=:mid",
    }[condition]

    async def change():
        async with f.db() as db, db.begin():
            await db.execute(
                text(sql),
                {
                    "uid": f.actors["OWNER"].id,
                    "mid": f.actors["OWNER"].member_id,
                    "sid": f.actors["OWNER"].session_id,
                    "hid": f.hid,
                },
            )

    asyncio.run(change())
    assert f.request("PATCH", path, key="saved", json=body).status_code == status


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("route", ["deductions", "purchases"])
def test_checkout_exact_role_intersection(f, role, route):
    from test_inventory_checkout import configure_timezone, demand, purchase_body, snapshot
    configure_timezone(f)
    p = product(f)
    receipt(f, p)
    body = demand(p) if route == "deductions" else purchase_body(f, p)[1]
    before = snapshot(f)
    r = f.request("POST", "/checkout/" + route, role=role, json=body)
    allowed = role in ({"OWNER", "INVENTORY_MANAGER"} if route == "deductions" else {"OWNER"})
    assert r.status_code == (201 if allowed else 403), r.text
    if not allowed:
        assert snapshot(f) == before


@pytest.mark.parametrize("route", ["deductions", "purchases"])
@pytest.mark.parametrize("condition,status", [("pending",403),("disabled",401),("removed",404),("revoked",401),("archived",409),("role",403)])
def test_checkout_replays_recheck_current_access(f, route, condition, status):
    from test_inventory_checkout import configure_timezone, demand, purchase_body, snapshot
    configure_timezone(f)
    p = product(f)
    receipt(f,p)
    body = demand(p) if route == "deductions" else purchase_body(f,p)[1]
    path = "/checkout/" + route
    assert f.request("POST", path, key="saved-checkout", json=body).status_code == 201
    sql = {
        "pending": "UPDATE users SET state='PENDING' WHERE id=:uid",
        "disabled": "UPDATE users SET state='DISABLED' WHERE id=:uid",
        "removed": "UPDATE household_members SET removed_at=now() WHERE id=:mid",
        "revoked": "UPDATE auth_sessions SET revoked_at=now() WHERE id=:sid",
        "archived": "UPDATE households SET archived_at=now() WHERE id=:hid",
        "role": "UPDATE household_members SET role_id=(SELECT id FROM roles WHERE code='FINANCE_MANAGER') WHERE id=:mid",
    }[condition]
    async def change():
        async with f.db() as db, db.begin():
            await db.execute(text(sql), {"uid": f.actors["OWNER"].id, "mid": f.actors["OWNER"].member_id,
                                         "sid": f.actors["OWNER"].session_id, "hid": f.hid})
    asyncio.run(change())
    before = snapshot(f)
    assert f.request("POST",path,key="saved-checkout",json=body).status_code == status
    assert snapshot(f) == before


@pytest.mark.parametrize("route", ["deductions", "purchases"])
def test_checkout_cross_household_path_and_body_return_404_without_effects(f, route):
    from test_inventory_checkout import configure_timezone, demand, purchase_body, snapshot
    configure_timezone(f)
    p = product(f)
    receipt(f,p)
    body = demand(p) if route == "deductions" else purchase_body(f,p)[1]
    before = snapshot(f)
    assert f.request("POST", "/checkout/"+route, role="OUTSIDER", json=body).status_code == 404
    # IDs in the other household must not authorize local writes.
    async def seed():
        async with f.db() as db, db.begin():
            return await db.scalar(text("INSERT INTO products(household_id,name,base_unit_id) VALUES (:hid,'Foreign',:unit) RETURNING id"), {"hid": f.other_hid,"unit":p["base_unit_id"]})
    foreign = asyncio.run(seed())
    if route == "deductions":
        body["items"][0]["product_id"] = foreign
    else:
        from test_finance_transactions import DRAFT
        r = f.client.post(f"/api/v1/households/{f.other_hid}/transactions",
                          headers=f.actors["OUTSIDER"].headers | {"Idempotency-Key":"foreign-transaction"}, json=DRAFT)
        assert r.status_code == 201
        body["transaction_id"] = r.json()["id"]
    assert f.request("POST", "/checkout/"+route, json=body).status_code == 404
    assert snapshot(f) == before


@pytest.mark.parametrize("reference", ["item", "account"])
def test_purchase_checkout_foreign_body_references_have_no_effects(f, reference):
    from test_inventory_checkout import purchase_body, snapshot
    from test_finance_transactions import DRAFT, payment
    p = product(f)
    tx, body = purchase_body(f,p)
    headers = f.actors["OUTSIDER"].headers | {"Idempotency-Key":"foreign-reference"}
    base = f"/api/v1/households/{f.other_hid}"
    if reference == "item":
        r = f.client.post(base+"/transactions",headers=headers,json=DRAFT)
        assert r.status_code == 201
        body["lots"][0]["item_id"] = r.json()["items"][0]["id"]
    else:
        r = f.client.post(base+"/accounts",headers=headers,json={"name":"Foreign", "currency_code":"USD"})
        assert r.status_code == 201
        body["payments"] = [payment(r.json()["id"])]
    before = snapshot(f)
    assert f.request("POST","/checkout/purchases",json=body).status_code == 404
    assert snapshot(f) == before
