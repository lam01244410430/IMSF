"""Retained drafts, atomic posting, settlement and source-derived balances."""
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
    assert f.request('POST', f"/transactions/{draft['id']}/post", json={'payments': []}).status_code == 200
    for method, suffix, body in [("PATCH", "", {"total_amount": "1"}),
        ("POST", "/items", {"line_no": 2, "description": "New", "quantity": "1", "net_amount": "1"}),
        ("PATCH", f"/items/{draft['items'][0]['id']}", {"description": "Changed"})]:
        assert f.request(method, f"/transactions/{draft['id']}" + suffix, json=body, role="MEMBER").status_code == 409


def account(f, currency="USD"):
    response = f.request("POST", "/accounts", json={"name": "Settlement", "currency_code": currency})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def payment(aid, amount="12.30", direction="OUT", **extra):
    return {"account_id": aid, "amount": amount, "currency_code": "USD", "direction": direction} | extra


def post(f, draft, payments=None, **kwargs):
    return f.request("POST", f"/transactions/{draft['id']}/post", json={"payments": payments or []}, **kwargs)


def assert_balances(f):
    # Every affected account/currency is independently summed from persisted rows.
    for row in query(f, "SELECT a.id,a.currency_code,coalesce(sum(l.signed_amount),0) AS balance FROM accounts a LEFT JOIN account_ledger_entries l ON l.household_id=a.household_id AND l.account_id=a.id AND l.currency_code=a.currency_code WHERE a.household_id=:hid GROUP BY a.id,a.currency_code"):
        response = f.request("GET", f"/accounts/{row['id']}/balance")
        assert response.status_code == 200, response.text
        assert response.json()["currency_code"] == row["currency_code"]
        assert Decimal(response.json()["balance"]) == row["balance"]


def test_post_income_and_expense_have_correct_signs(f):
    aid = account(f)
    for kind, direction, sign in [("INCOME", "IN", 1), ("EXPENSE", "OUT", -1)]:
        draft = create_draft(f, role="MEMBER", kind=kind)
        r = post(f, draft, [payment(aid, direction=direction)])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "POSTED" and Decimal(r.json()["remaining_amount"]) == 0
        rows = query(f, "SELECT signed_amount FROM account_ledger_entries WHERE household_id=:hid AND transaction_id=:tid", tid=draft["id"])
        assert [v["signed_amount"] for v in rows] == [sign * Decimal("12.30")]
        assert_balances(f)
    assert f.request("GET", "/ledger").status_code == 200


def test_partial_payment_and_remaining_amount(f):
    aid = account(f)
    draft = create_draft(f)
    r = post(f, draft, [payment(aid, "2.30", method_code="CASH", external_reference="same reference")])
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["remaining_amount"]) == 10
    assert_balances(f)
    path = f"/transactions/{draft['id']}/payments"
    r = f.request("POST", path, json={"payments": [payment(aid, "5", external_reference="same reference")]})
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["remaining_amount"]) == 5
    assert len(r.json()["payments"]) == 1
    assert len(f.request("GET", path).json()["payments"]) == 2
    assert Decimal(f.request("GET", f"/transactions/{draft['id']}").json()["settled_amount"]) == Decimal("7.30")
    assert_balances(f)


def test_cumulative_overpayment_rejected(f):
    aid = account(f)
    draft = create_draft(f)
    assert post(f, draft, [payment(aid, "10")]).status_code == 200
    assert_balances(f)
    r = f.request("POST", f"/transactions/{draft['id']}/payments", key="overpay", json={"payments": [payment(aid, "2"), payment(aid, "1")]})
    assert r.status_code == 409
    assert len(query(f, "SELECT id FROM transaction_payments WHERE household_id=:hid")) == 1
    assert not query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='overpay'")
    assert_balances(f)


def test_two_account_transfer_is_atomic_and_zero_sum(f):
    aid, bid = account(f), account(f)
    draft = create_draft(f, kind="TRANSFER", items=[])
    r = post(f, draft, [payment(aid), payment(bid, direction="IN")])
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["settled_amount"]) == Decimal("12.30")
    assert Decimal(r.json()["remaining_amount"]) == 0
    entries = query(f, "SELECT signed_amount FROM account_ledger_entries WHERE household_id=:hid")
    assert len(entries) == 2 and sum(e["signed_amount"] for e in entries) == 0
    assert_balances(f)
    assert f.request("POST", f"/transactions/{draft['id']}/payments", json={"payments": [payment(aid, "1")]}).status_code == 409


@pytest.mark.parametrize("direction", ["IN", "OUT"])
def test_opening_is_ledger_event_not_mutable_balance(f, direction):
    aid = account(f)
    draft = create_draft(f, kind="OPENING", items=[])
    assert post(f, draft, [payment(aid, direction=direction)]).status_code == 200
    assert_balances(f)
    second = create_draft(f, kind="OPENING", items=[])
    assert post(f, second, [payment(aid, direction=direction)]).status_code == 409
    assert len(query(f, "SELECT id FROM account_ledger_entries WHERE household_id=:hid")) == 1
    columns = query(f, "SELECT column_name FROM information_schema.columns WHERE table_name='accounts' AND :hid>0")
    assert not any("balance" in c["column_name"] for c in columns)


def test_reversed_original_cannot_receive_new_payment(f):
    draft = create_draft(f)
    aid = account(f)
    assert post(f, draft).status_code == 200
    async def seed():
        async with f.db() as db, db.begin():
            await db.execute(text("INSERT INTO transactions(household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id,original_transaction_id,reversal_reason,posted_at) VALUES (:hid,'REVERSAL','POSTED',now(),'USD',12.30,:mid,:tid,'Controlled reversal fixture',now())"), {"hid": f.hid, "mid": f.actors["OWNER"].member_id, "tid": draft["id"]})
    asyncio.run(seed())
    assert f.request("POST", f"/transactions/{draft['id']}/payments", json={"payments": [payment(aid)]}).status_code == 409
    assert not query(f, "SELECT id FROM transaction_payments WHERE household_id=:hid")


@pytest.mark.parametrize("posting", [True, False])
def test_failed_audit_rolls_back_payment_ledger_and_idempotency(f, monkeypatch, posting):
    from app.finance.ledger_service import LedgerService
    aid, draft = account(f), create_draft(f)
    if not posting:
        assert post(f, draft).status_code == 200
    before = {t: len(query(f, f"SELECT id FROM {t} WHERE household_id=:hid")) for t in ("audit_logs", "idempotency_requests")}
    def fail(*args, **kwargs):
        raise RuntimeError("injected audit failure")
    monkeypatch.setattr(LedgerService, "_audit", fail)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        f.request("POST", f"/transactions/{draft['id']}/{'post' if posting else 'payments'}", json={"payments": [payment(aid)]})
    for table in ("transaction_payments", "account_ledger_entries"):
        assert not query(f, f"SELECT id FROM {table} WHERE household_id=:hid")
    for table, n in before.items():
        assert len(query(f, f"SELECT id FROM {table} WHERE household_id=:hid")) == n
    assert f.request("GET", f"/transactions/{draft['id']}").json()["status"] == ("DRAFT" if posting else "POSTED")


@pytest.mark.parametrize("case", ["zero", "items", "wrong_direction", "currency", "archived", "transfer_partial", "transfer_same", "transfer_items", "opening_partial", "opening_items", "transfer_category", "opening_category"])
def test_invalid_posting_is_atomic(f, case):
    aid, bid = account(f), account(f)
    changes = {}
    payments = [payment(aid)]
    if case == "zero": changes = {"total_amount": "0", "items": []}; payments = []
    if case == "items": changes = {"total_amount": "13"}
    if case == "wrong_direction": payments = [payment(aid, direction="IN")]
    if case == "currency": payments = [payment(account(f, "EUR"), currency_code="EUR")]
    if case == "archived": assert f.request("POST", f"/accounts/{aid}/archive").status_code == 204
    if case.startswith("transfer"):
        changes = {"kind": "TRANSFER", "items": []}
        payments = [payment(aid), payment(aid if case == "transfer_same" else bid, "1" if case == "transfer_partial" else "12.30", direction="IN")]
    if case.startswith("opening"): changes = {"kind": "OPENING", "items": []}
    if case == "opening_partial": payments = [payment(aid, "1")]
    if case.endswith("items"): changes["items"] = DRAFT["items"]
    if case.endswith("category"):
        changes["category_id"] = f.request("POST", "/categories", json={"name": "Income", "kind": "INCOME"}).json()["id"]
        # A category can be attached to a commercial draft, then kind changed in SQL
        # to exercise posting's independent invariants, beyond Step 2 validation.
        changes["kind"] = "INCOME"
    draft = create_draft(f, **changes)
    if case.endswith("category"):
        async def seed():
            async with f.db() as db, db.begin():
                await db.execute(text("UPDATE transactions SET kind=:kind WHERE household_id=:hid AND id=:tid"), {"hid": f.hid, "tid": draft["id"], "kind": "TRANSFER" if case.startswith("transfer") else "OPENING"})
        asyncio.run(seed())
    r = post(f, draft, payments)
    assert r.status_code in {409, 422}, r.text
    assert not query(f, "SELECT id FROM transaction_payments WHERE household_id=:hid")
    assert not query(f, "SELECT id FROM account_ledger_entries WHERE household_id=:hid")
    assert f.request("GET", f"/transactions/{draft['id']}").json()["status"] == "DRAFT"


@pytest.mark.parametrize("extra", [{"exchange_rate": "1"}, {"transaction_amount": "12"}, {"method_code": "WIRE"}, {"external_reference": "a" * 201}, {"amount": 12.3}, {"amount": "1.001"}, {"amount": "0"}, {"reverses_payment_id": 1}, {"pan": "secret"}])
def test_unsupported_payment_input_rejected(f, extra):
    draft, aid = create_draft(f), account(f)
    assert post(f, draft, [payment(aid) | extra]).status_code == 422
    assert not query(f, "SELECT id FROM transaction_payments WHERE household_id=:hid")


def test_unpaid_bill_and_payment_state_requirements(f):
    aid, draft = account(f), create_draft(f)
    path = f"/transactions/{draft['id']}/payments"
    assert f.request("POST", path, json={"payments": [payment(aid)]}).status_code == 409
    assert f.request("POST", path, json={"payments": []}).status_code == 422
    assert post(f, draft).status_code == 200
    assert_balances(f)
    assert post(f, draft).status_code == 409
    assert f.request("POST", path, json={"payments": [payment(aid)]}).status_code == 201
    assert_balances(f)


def test_ledger_and_balance_use_posting_time_and_stable_boundary(f):
    aid = account(f)
    first = create_draft(f, occurred_at="2020-01-01T00:00:00Z")
    assert post(f, first, [payment(aid, "1")]).status_code == 200
    assert_balances(f)
    snapshot = f.request("GET", f"/accounts/{aid}/balance").json()
    second = create_draft(f, occurred_at="2019-01-01T00:00:00Z")
    assert post(f, second, [payment(aid, "2")]).status_code == 200
    assert_balances(f)
    ledger = f.request("GET", "/ledger", params={"account_id": aid, "limit": 1}).json()
    assert ledger["items"][0]["transaction_id"] == second["id"]
    page = f.request("GET", "/ledger", params={"account_id": aid, "limit": 1, "cursor": ledger["next_cursor"]}).json()
    assert page["items"][0]["transaction_id"] == first["id"]
    old = f.request("GET", f"/accounts/{aid}/balance", params={"cursor": snapshot["cursor"]})
    assert old.status_code == 200 and Decimal(old.json()["balance"]) == -1
    before = f.request("GET", f"/accounts/{aid}/balance", params={"as_of": "2021-01-01T00:00:00Z"}).json()
    assert Decimal(before["balance"]) == 0
    assert not f.request("GET", "/ledger", params={"date_to": "2021-01-01T00:00:00Z"}).json()["items"]
    bid = account(f)
    assert f.request("GET", f"/accounts/{bid}/balance", params={"cursor": snapshot["cursor"]}).status_code == 422
    for path in ("/ledger", f"/accounts/{aid}/balance"):
        assert f.request("GET", path, params={"cursor": "bad"}).status_code == 422
    assert f.request("GET", f"/accounts/{aid}/balance", params={"as_of": "2026-01-01T00:00:00"}).status_code == 422


def test_unresolved_refund_blocks_future_full_reversal():
    from app.finance.domain import FinanceRequestError, require_full_reversal_eligible
    original = {"status": "POSTED", "kind": "EXPENSE", "is_reversed": False}
    require_full_reversal_eligible(original, [])
    with pytest.raises(FinanceRequestError) as error:
        require_full_reversal_eligible(original, [{"status": "POSTED", "is_reversed": False}])
    assert error.value.status_code == 409
    require_full_reversal_eligible(original, [{"status": "POSTED", "is_reversed": True}])


def test_transfer_second_leg_failure_rolls_back_every_effect(f, monkeypatch):
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
    aid, bid = account(f), account(f)
    draft = create_draft(f, kind="TRANSFER", items=[])
    original = SqlAlchemyFinanceRepository.create
    entries = []
    async def fail(self, resource, values):
        result = await original(self, resource, values)
        if resource == "ledger":
            entries.append(result["id"])
            if len(entries) == 2:
                raise RuntimeError("second leg failure")
        return result
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "create", fail)
    with pytest.raises(RuntimeError, match="second leg failure"):
        post(f, draft, [payment(aid), payment(bid, direction="IN")], key="second-leg")
    for table in ("transaction_payments", "account_ledger_entries"):
        assert not query(f, f"SELECT id FROM {table} WHERE household_id=:hid")
    assert not query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='second-leg'")
    assert f.request("GET", f"/transactions/{draft['id']}").json()["status"] == "DRAFT"
    assert_balances(f)


def test_opening_cannot_backdate_before_existing_commercial_entry(f):
    aid = account(f)
    assert post(f, create_draft(f), [payment(aid)]).status_code == 200
    opening = create_draft(f, kind="OPENING", items=[], occurred_at="2000-01-01T00:00:00Z")
    assert post(f, opening, [payment(aid, direction="IN")]).status_code == 409
    assert_balances(f)


def test_balance_and_ledger_equal_posting_times_use_id_boundary(f):
    # Controlled append-only SQL fixture: identical timestamps require ID ordering.
    aid, draft = account(f), create_draft(f)
    assert post(f, draft).status_code == 200
    async def seed(amount):
        async with f.db() as db, db.begin():
            pid = await db.scalar(text("INSERT INTO transaction_payments(household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id) VALUES (:hid,:tid,:aid,'USD',:amount,:amount,'OUT','2026-01-01T00:00:00Z',:mid) RETURNING id"), {"hid": f.hid, "tid": draft["id"], "aid": aid, "mid": f.actors["OWNER"].member_id, "amount": amount})
            await db.execute(text("INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,payment_id) VALUES (:hid,:tid,:aid,'USD',:amount,'2026-01-01T00:00:00Z',:pid)"), {"hid": f.hid, "tid": draft["id"], "aid": aid, "amount": -amount, "pid": pid})
    asyncio.run(seed(1))
    snapshot = f.request("GET", f"/accounts/{aid}/balance").json()
    asyncio.run(seed(2))
    assert_balances(f)
    assert Decimal(f.request("GET", f"/accounts/{aid}/balance", params={"as_of": "2026-01-01T00:00:00Z", "cursor": snapshot["cursor"]}).json()["balance"]) == -1
    first = f.request("GET", "/ledger", params={"account_id": aid, "limit": 1}).json()
    second = f.request("GET", "/ledger", params={"account_id": aid, "limit": 1, "cursor": first["next_cursor"]}).json()
    assert first["items"][0]["id"] > second["items"][0]["id"]
    assert second["next_cursor"] is None
    for params in ({"date_from": "2026-02-01T00:00:00Z", "date_to": "2026-01-01T00:00:00Z"}, {"date_from": "2026-01-01T00:00:00"}, {"limit": 201}):
        assert f.request("GET", "/ledger", params=params).status_code == 422


def test_payment_metadata_is_settled_history(f):
    aid, draft = account(f), create_draft(f)
    assert post(f, draft, [payment(aid, method_code="BANK_TRANSFER", external_reference="Receipt 42")]).status_code == 200
    row = f.request("GET", f"/transactions/{draft['id']}/payments").json()["payments"][0]
    assert row["method_code"] == "BANK_TRANSFER" and row["external_reference"] == "Receipt 42"
    assert row["created_by_member_id"] == f.actors["OWNER"].member_id
    assert row["settled_at"] and row["created_at"] and row["reverses_payment_id"] is None
    assert_balances(f)


@pytest.mark.parametrize("kind", ["INCOME", "EXPENSE"])
def test_posting_requires_nonempty_commercial_items(kind):
    from app.finance.domain import FinanceRequestError, validate_settlement
    header = DRAFT | {"kind": kind, "total_amount": Decimal("12.30"), "category_id": None}
    with pytest.raises(FinanceRequestError) as error:
        validate_settlement(header, [], [], Decimal(0), 2, posting=True)
    assert error.value.status_code == 422


def test_payment_dto_accepts_only_offset_aware_settlement_time():
    from app.finance.dto import PaymentCreate
    from pydantic import ValidationError
    dto = PaymentCreate.model_validate(payment(1, settled_at="2020-01-01T07:00:00+07:00"))
    assert dto.settled_at.isoformat() == "2020-01-01T00:00:00+00:00"
    for value in (None, "2020-01-01T00:00:00"):
        with pytest.raises(ValidationError):
            PaymentCreate.model_validate(payment(1, settled_at=value))


def test_backdated_settlement_keeps_actual_ledger_posting_time(f):
    aid, draft = account(f), create_draft(f)
    r = post(f, draft, [payment(aid, settled_at="2020-01-01T00:00:00Z")])
    assert r.status_code == 200, r.text
    p = f.request("GET", f"/transactions/{draft['id']}/payments").json()["payments"][0]
    assert p["settled_at"].startswith("2020-01-01")
    assert not f.request("GET", "/ledger", params={"date_to": "2021-01-01T00:00:00Z"}).json()["items"]
    assert_balances(f)


def test_archived_account_rejects_additional_payment(f):
    aid, draft = account(f), create_draft(f)
    assert post(f, draft, [payment(aid, "1")]).status_code == 200
    assert f.request("POST", f"/accounts/{aid}/archive").status_code == 204
    r = f.request("POST", f"/transactions/{draft['id']}/payments", json={"payments": [payment(aid, "1")]})
    assert r.status_code == 409
    assert len(query(f, "SELECT id FROM transaction_payments WHERE household_id=:hid")) == 1
    assert_balances(f)
