"""Step 2 only: exact, retained DRAFT commands and durable replay."""
import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import text

DRAFT = {"kind": "EXPENSE", "occurred_at": "2026-11-10T12:00:00Z", "currency_code": "USD",
         "total_amount": "12.30", "items": [{"line_no": 1, "description": "Test service", "quantity": "1", "net_amount": "12.30"}]}


def create_draft(f, *, role="OWNER", **changes):
    response = f.request("POST", "/transactions", role=role, json=DRAFT | changes)
    assert response.status_code == 201, response.text
    return response.json()


def query(f, sql, **params):
    async def run():
        async with f.db() as db:
            return (await db.execute(text(sql), params | {"hid": f.hid})).mappings().all()
    return asyncio.run(run())


def test_member_draft_does_not_change_balance(f):
    result = create_draft(f, role="MEMBER")
    assert result["status"] == "DRAFT" and result["created_by_member_id"] == f.actors["MEMBER"].member_id
    assert Decimal(result["total_amount"]) == Decimal("12.30")
    assert Decimal(result["settled_amount"]) == 0 and Decimal(result["remaining_amount"]) == Decimal("12.30")
    row = query(f, "SELECT count(*) AS n, coalesce(sum(signed_amount),0) AS balance FROM account_ledger_entries WHERE household_id=:hid")[0]
    assert row["n"] == 0 and row["balance"] == 0
    assert query(f, "SELECT count(*) AS n FROM transaction_payments WHERE household_id=:hid")[0]["n"] == 0
    assert query(f, "SELECT count(*) AS n FROM audit_logs WHERE household_id=:hid")[0]["n"] == 1
    assert query(f, "SELECT count(*) AS n FROM idempotency_requests WHERE household_id=:hid")[0]["n"] == 1


def test_draft_line_edits_are_retained(f):
    draft = create_draft(f)
    tid, iid = draft["id"], draft["items"][0]["id"]
    response = f.request("PATCH", f"/transactions/{tid}/items/{iid}", json={"description": "Corrected", "net_amount": "10.20"})
    assert response.status_code == 200
    assert response.json()["id"] == iid
    assert f.request("POST", f"/transactions/{tid}/items", json={"line_no": 2, "description": "Additional", "quantity": "2", "net_amount": "2.10"}).status_code == 201
    assert f.request("POST", f"/transactions/{tid}/items", json={"line_no": 2, "description": "Duplicate", "quantity": "1", "net_amount": "1"}).status_code == 409
    assert f.request("DELETE", f"/transactions/{tid}/items/{iid}").status_code == 405
    assert f.request("DELETE", f"/transactions/{tid}").status_code == 405
    detail = f.request("GET", f"/transactions/{tid}").json()
    assert len(detail["items"]) == 2 and detail["items"][0]["description"] == "Corrected"
    assert len(query(f, "SELECT id FROM audit_logs WHERE household_id=:hid")) == 3


def test_settings_empty_requires_explicit_currency(f):
    for path, body in [("/accounts", {"name": "Cash"}), ("/transactions", {k: v for k, v in DRAFT.items() if k != "currency_code"})]:
        assert f.request("POST", path, json=body).status_code == 422
        assert f.request("POST", path, json=body | {"currency_code": "ZZZ"}).status_code == 422
    assert query(f, 'SELECT "values" FROM household_settings WHERE household_id=:hid')[0]["values"] == {}
    assert f.request("POST", "/accounts", json={"name": "Cash", "currency_code": "USD"}).status_code == 201
    # OPEN-12 PROPOSAL: preserve existing identity validation, including unsupported catalog codes.
    r = f.client.patch(f"/api/v1/households/{f.hid}", headers=f.actors["OWNER"].headers,
                       json={"settings": {"currency": "ZZZ"}})
    assert r.status_code == 200 and r.json()["settings"] == {"currency": "ZZZ"}


@pytest.mark.parametrize("field,value", [("total_amount", 1.2), ("total_amount", "1.001"),
    ("total_amount", "NaN"), ("total_amount", "100000000000000"), ("total_amount", "-1"),
    ("occurred_at", "2026-11-10T12:00:00"), ("kind", "REVERSAL"), ("kind", "REFUND")])
def test_invalid_draft_is_rejected_without_effects(f, field, value):
    assert f.request("POST", "/transactions", json=DRAFT | {field: value}).status_code == 422
    assert query(f, "SELECT count(*) AS n FROM transactions WHERE household_id=:hid")[0]["n"] == 0
    assert query(f, "SELECT count(*) AS n FROM idempotency_requests WHERE household_id=:hid")[0]["n"] == 0


def test_header_currency_edit_revalidates_existing_lines(f):
    draft = create_draft(f)
    path = f"/transactions/{draft['id']}"
    assert f.request("PATCH", path, json={"currency_code": "JPY", "total_amount": "12"}).status_code == 422
    assert f.request("GET", path).json()["currency_code"] == "USD"
    assert f.request("PATCH", path, json={"total_amount": "13.20"}).status_code == 200


def test_same_key_same_payload_replays_identical_status_body(f):
    first = f.request("POST", "/transactions", key="repeat", json=DRAFT)
    second = f.request("POST", "/transactions", key="repeat", json=DRAFT | {"total_amount": "12.300"})
    assert first.status_code == second.status_code == 201, (first.text, second.text)
    assert first.json() == second.json()
    assert len(query(f, "SELECT id FROM transactions WHERE household_id=:hid")) == 1
    assert f.request("POST", "/transactions", key="repeat", json=DRAFT | {"total_amount": "12.31"}).status_code == 409


@pytest.mark.parametrize("key", [False, "", "a" * 129, "has space", "tab\there"])
def test_idempotency_key_required_and_bounded(f, key):
    assert f.request("POST", "/transactions", key=key, json=DRAFT).status_code == 422


def test_accounts_categories_archive_and_bounded_pages(f):
    account = f.request("POST", "/accounts", json={"name": "Cash", "currency_code": "VND"}).json()
    assert f.request("GET", f"/accounts/{account['id']}").json() == account
    category = f.request("POST", "/categories", json={"name": "Services", "kind": "EXPENSE"}).json()
    draft = create_draft(f, category_id=category["id"])
    assert draft["category_id"] == category["id"]
    assert f.request("POST", f"/accounts/{account['id']}/archive", key="archive").status_code == 204
    assert f.request("POST", f"/accounts/{account['id']}/archive", key="archive").status_code == 204
    assert f.request("POST", f"/categories/{category['id']}/archive").status_code == 204
    assert f.request("POST", "/transactions", json=DRAFT | {"category_id": category["id"]}).status_code == 409
    for resource in ("accounts", "categories", "transactions"):
        page = f.request("GET", f"/{resource}?limit=1").json()
        assert len(page["items"]) == 1 and "next_cursor" in page
        assert f.request("GET", f"/{resource}?limit=201").status_code == 422


def test_failed_audit_rolls_back_draft_and_idempotency(f, monkeypatch):
    from app.finance.ledger_service import LedgerService
    def fail(*args, **kwargs):
        raise RuntimeError("injected audit failure")
    monkeypatch.setattr(LedgerService, "_audit", fail)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        f.request("POST", "/transactions", json=DRAFT)
    for table in ("transactions", "transaction_items", "audit_logs", "idempotency_requests", "account_ledger_entries"):
        assert query(f, f"SELECT count(*) AS n FROM {table} WHERE household_id=:hid")[0]["n"] == 0


@pytest.mark.parametrize("changed", [False, True])
def test_concurrent_draft_keys_commit_one_effect(f, changed):
    import httpx
    async def run():
        barrier = asyncio.Barrier(2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
            async def create(index):
                await barrier.wait()
                return await client.post(f"/api/v1/households/{f.hid}/transactions",
                    headers=f.actors["MEMBER"].headers | {"Idempotency-Key": "simultaneous"},
                    json=DRAFT | ({"total_amount": "12.31"} if changed and index else {}))
            responses = await asyncio.gather(create(0), create(1))
            assert sorted(r.status_code for r in responses) == ([201, 409] if changed else [201, 201])
            if not changed:
                assert responses[0].json() == responses[1].json()
    asyncio.run(run())
    for table in ("transactions", "transaction_items", "idempotency_requests", "audit_logs"):
        assert query(f, f"SELECT count(*) AS n FROM {table} WHERE household_id=:hid")[0]["n"] == 1
    assert query(f, "SELECT count(*) AS n FROM account_ledger_entries WHERE household_id=:hid")[0]["n"] == 0


def test_key_scope_includes_actor_operation_and_target(f):
    first = f.request("POST", "/transactions", role="MEMBER", key="scope", json=DRAFT).json()
    second = f.request("POST", "/transactions", key="scope", json=DRAFT).json()
    assert first["id"] != second["id"]
    for row in (first, second):
        assert f.request("PATCH", f"/transactions/{row['id']}", key="scope", json={"total_amount": "14"}).status_code == 200
    assert query(f, "SELECT count(*) AS n FROM idempotency_requests WHERE household_id=:hid")[0]["n"] == 4


def test_cursor_pagination_is_stable_and_household_bound(f):
    ids = [create_draft(f)["id"] for _ in range(3)]
    page = f.request("GET", "/transactions?limit=2").json()
    assert [r["id"] for r in page["items"]] == list(reversed(ids))[0:2]
    cursor = page["next_cursor"]
    page2 = f.request("GET", "/transactions", params={"limit": 2, "cursor": cursor}).json()
    assert [r["id"] for r in page2["items"]] == [ids[0]] and page2["next_cursor"] is None
    response = f.client.get(f"/api/v1/households/{f.other_hid}/transactions", params={"cursor": cursor}, headers=f.actors["OUTSIDER"].headers)
    assert response.status_code == 422
    for malformed in ("garbage", "W10=", "bnVsbA==", "e30="):
        assert f.request("GET", "/transactions", params={"cursor": malformed}).status_code == 422


def test_test_only_scale6_currency_storage_boundary_and_no_sql_rounding(f, finance_database_urls):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    async def catalog():
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        async with engine.begin() as db:
            # Test-only currency; deliberately absent from the PROPOSAL seed set.
            await db.execute(text("INSERT INTO currencies(code,minor_units) VALUES ('XTS',6) ON CONFLICT DO NOTHING"))
        await engine.dispose()
    asyncio.run(catalog())
    draft = create_draft(f, currency_code="XTS", total_amount="99999999999999.999999", items=[
        {"line_no": 1, "description": "Boundary fixture", "quantity": "0.000001", "net_amount": "99999999999999.999999"}])
    stored = query(f, "SELECT total_amount FROM transactions WHERE household_id=:hid AND id=:tid", tid=draft["id"])[0]
    assert stored["total_amount"] == Decimal("99999999999999.999999")
    assert draft["total_amount"] == "99999999999999.999999"
    for value in ("0.0000001", "100000000000000", "NaN", "Infinity"):
        assert f.request("POST", "/transactions", json=DRAFT | {"currency_code": "XTS", "total_amount": value}).status_code == 422
    for currency, value in (("VND", "1.1"), ("USD", "1.001"), ("BHD", "1.0001")):
        assert f.request("POST", "/transactions", json=DRAFT | {"currency_code": currency, "total_amount": "1", "items": [
            {"line_no": 1, "description": "Invalid scale", "quantity": "1", "net_amount": value}]}).status_code == 422
    assert len(query(f, "SELECT id FROM transactions WHERE household_id=:hid")) == 1
    assert len(query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid")) == 1


def test_posted_header_and_items_reject_patch(f):
    draft = create_draft(f, role="MEMBER")
    async def post_fixture():
        # Controlled SQL fixture only: there is no Step 2 posting command/route.
        async with f.db() as db, db.begin():
            await db.execute(text("UPDATE transactions SET status='POSTED',posted_at=now() WHERE household_id=:hid AND id=:tid"),
                             {"hid": f.hid, "tid": draft["id"]})
    asyncio.run(post_fixture())
    for method, suffix, body in [("PATCH", "", {"total_amount": "1"}),
        ("POST", "/items", {"line_no": 2, "description": "New", "quantity": "1", "net_amount": "1"}),
        ("PATCH", f"/items/{draft['items'][0]['id']}", {"description": "Changed"})]:
        assert f.request(method, f"/transactions/{draft['id']}" + suffix, json=body, role="MEMBER").status_code == 409
