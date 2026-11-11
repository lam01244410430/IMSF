"""Immutable full reversals: persisted mirrors, locks, authorization and rollback."""
import asyncio
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.finance.domain import FinanceRequestError, require_full_reversal_eligible
from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
from test_finance_idempotency import race
from test_finance_transactions import DRAFT, account, assert_balances, create_draft, payment, post, query

REASON = {"reason": "Correct duplicate bill"}


def reverse(f, tid, **kwargs):
    return f.request("POST", f"/transactions/{tid}/reversals", **({"json": REASON} | kwargs))


def prepared(f, *, two=False, **changes):
    draft = create_draft(f, **changes)
    aids = [account(f), account(f)] if two else [account(f)]
    payments = ([payment(aids[0], "2.30", method_code="CASH", external_reference="Original receipt"),
                 payment(aids[1], "10.00", method_code="CARD")] if two else [payment(aids[0])])
    response = post(f, draft, payments)
    assert response.status_code == 200, response.text
    return response.json(), aids


def rows(f, table, tid):
    return query(f, f"SELECT * FROM {table} WHERE household_id=:hid AND "
                 + ("id=:tid" if table == "transactions" else "transaction_id=:tid") + " ORDER BY id", tid=tid)


def snapshot(f, tid, tables=("transactions", "transaction_items", "transaction_payments", "account_ledger_entries")):
    # PostgreSQL serializes ALL columns; compare bytes to detect any historical rewrite.
    return {table: [row["bytes"].encode() for row in query(f,
        f"SELECT row_to_json(t)::text AS bytes FROM {table} t WHERE household_id=:hid AND "
        + ("id=:tid" if table == "transactions" else "transaction_id=:tid") + " ORDER BY id", tid=tid)] for table in tables}


def assert_zero(f):
    assert_balances(f)
    for row in query(f, "SELECT account_id,currency_code,sum(signed_amount) AS balance FROM account_ledger_entries WHERE household_id=:hid GROUP BY account_id,currency_code"):
        assert row["balance"] == Decimal(0)
        assert Decimal(f.request("GET", f"/accounts/{row['account_id']}/balance").json()["balance"]) == 0


def reversal_counts(f):
    return {
        "headers": len(query(f, "SELECT id FROM transactions WHERE household_id=:hid AND kind='REVERSAL' AND status='POSTED'")),
        "payments": len(query(f, "SELECT id FROM transaction_payments WHERE household_id=:hid AND reverses_payment_id IS NOT NULL")),
        "entries": len(query(f, "SELECT id FROM account_ledger_entries WHERE household_id=:hid AND reverses_entry_id IS NOT NULL")),
        "audit": len(query(f, "SELECT id FROM audit_logs WHERE household_id=:hid AND action='FINANCE_REVERSED'")),
        "keys": len(query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND operation LIKE '%/reversals:v1'")),
    }


def test_single_full_reversal_keeps_original_unchanged(f):
    original, _ = prepared(f)
    tid = original["id"]
    before = snapshot(f, tid)
    response = reverse(f, tid, role="FINANCE_MANAGER")
    assert response.status_code == 201, response.text
    result = response.json()
    rev = result["reversal_transaction"]
    assert result["original_transaction_id"] == tid
    assert snapshot(f, tid) == before
    detail = f.request("GET", f"/transactions/{tid}").json()
    assert detail["is_reversed"] is True and detail["reversal_transaction_id"] == rev["id"]
    stored, = rows(f, "transactions", rev["id"])
    original_row, = rows(f, "transactions", tid)
    assert stored["kind"] == "REVERSAL" and stored["status"] == "POSTED"
    for field in ("household_id", "currency_code", "total_amount"):
        assert stored[field] == original_row[field]
    assert stored["original_transaction_id"] == tid
    assert stored["reversal_reason"] == REASON["reason"]
    assert stored["created_by_member_id"] == f.actors["FINANCE_MANAGER"].member_id
    assert stored["occurred_at"] == stored["posted_at"] >= original_row["posted_at"]
    assert stored["category_id"] is None and rev["items"] == []


def test_mirrors_exact_amount_currency_account_and_links(f):
    original, _ = prepared(f, two=True)
    tid = original["id"]
    before_payments = rows(f, "transaction_payments", tid)
    before_entries = rows(f, "account_ledger_entries", tid)
    response = reverse(f, tid, role="FINANCE_MANAGER")
    assert response.status_code == 201, response.text
    result = response.json()
    rid = result["reversal_transaction"]["id"]
    instant = rows(f, "transactions", rid)[0]["posted_at"]
    payments = rows(f, "transaction_payments", rid)
    entries = rows(f, "account_ledger_entries", rid)
    assert result["payment_ids"] == [p["id"] for p in payments]
    assert result["ledger_entry_ids"] == [e["id"] for e in entries]
    assert len(payments) == len(entries) == 2
    mapping = {}
    for original_payment, mirror in zip(before_payments, payments, strict=True):
        for field in ("household_id", "account_id", "currency_code", "amount", "transaction_amount", "method_code"):
            assert mirror[field] == original_payment[field]
        assert mirror["direction"] == "IN"
        assert mirror["reverses_payment_id"] == original_payment["id"]
        assert mirror["transaction_id"] == rid and mirror["settled_at"] == instant
        assert mirror["created_by_member_id"] == f.actors["FINANCE_MANAGER"].member_id
        assert mirror["external_reference"] is None and mirror["exchange_rate"] is None
        mapping[original_payment["id"]] = mirror["id"]
    for original_entry, mirror in zip(before_entries, entries, strict=True):
        for field in ("household_id", "account_id", "currency_code"):
            assert mirror[field] == original_entry[field]
        assert mirror["signed_amount"] == -original_entry["signed_amount"]
        assert mirror["reverses_entry_id"] == original_entry["id"]
        assert mirror["payment_id"] == mapping[original_entry["payment_id"]]
        assert mirror["posted_at"] == instant and mirror["transaction_id"] == rid
    assert_zero(f)


def test_unique_reversal_target_enforced_in_sql(f):
    original, _ = prepared(f)
    response = reverse(f, original["id"])
    assert response.status_code == 201, response.text
    rid = response.json()["reversal_transaction"]["id"]
    async def run():
        async with f.db() as db, db.begin():
            statements = [
                "INSERT INTO transactions(household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id,original_transaction_id,reversal_reason,posted_at) SELECT household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id,original_transaction_id,reversal_reason,posted_at FROM transactions WHERE id=:rid",
                "INSERT INTO transaction_payments(household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id,reverses_payment_id) SELECT household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id,reverses_payment_id FROM transaction_payments WHERE transaction_id=:rid",
                # Null payment avoids hitting uq_ledger_payment before uq_ledger_reversal.
                "INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,reverses_entry_id) SELECT household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,reverses_entry_id FROM account_ledger_entries WHERE transaction_id=:rid",
            ]
            for statement, constraint in zip(statements, ("uq_transactions_reversal", "uq_payments_reversal", "uq_ledger_reversal"), strict=True):
                with pytest.raises(DBAPIError) as error:
                    async with db.begin_nested():
                        await db.execute(text(statement), {"rid": rid})
                assert error.value.orig.sqlstate == "23505"
                assert error.value.orig.diag.constraint_name == constraint
    asyncio.run(run())
    assert reversal_counts(f) == {"headers": 1, "payments": 1, "entries": 1, "audit": 1, "keys": 1}


def test_concurrent_different_keys_reverse_once(f):
    original, _ = prepared(f)
    responses = asyncio.run(race(f, f"/transactions/{original['id']}/reversals", [REASON, REASON], ["one", "two"]))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert reversal_counts(f) == {"headers": 1, "payments": 1, "entries": 1, "audit": 1, "keys": 1}
    assert_zero(f)


def test_same_key_reversal_replays(f):
    original, _ = prepared(f)
    first = reverse(f, original["id"], key="replay")
    second = reverse(f, original["id"], key="replay")
    assert first.status_code == second.status_code == 201
    assert first.content == second.content
    conflict = reverse(f, original["id"], key="replay", json={"reason": "Changed reason"})
    assert conflict.status_code == 409 and conflict.json()["error_code"] == "FINANCE_IDEMPOTENCY_CONFLICT"
    assert reversal_counts(f) == {"headers": 1, "payments": 1, "entries": 1, "audit": 1, "keys": 1}


def test_reverse_failure_midway_rolls_back_all_mirrors_and_audit(f, monkeypatch):
    original, _ = prepared(f, two=True)
    before = snapshot(f, original["id"])
    create = SqlAlchemyFinanceRepository.create
    count = 0
    async def fail(self, resource, values):
        nonlocal count
        if resource == "ledger" and values.get("reverses_entry_id") is not None:
            count += 1
            if count == 2:
                raise RuntimeError("second reversal entry failure")
        return await create(self, resource, values)
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "create", fail)
    with pytest.raises(RuntimeError, match="second reversal entry failure"):
        reverse(f, original["id"], key="rollback")
    assert reversal_counts(f) == {"headers": 0, "payments": 0, "entries": 0, "audit": 0, "keys": 0}
    assert not query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='rollback'")
    assert snapshot(f, original["id"]) == before
    detail = f.request("GET", f"/transactions/{original['id']}").json()
    assert detail["status"] == "POSTED" and detail["is_reversed"] is False
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "create", create)
    assert reverse(f, original["id"], key="rollback").status_code == 201
    assert_zero(f)


def test_refund_or_inventory_link_blocks_unresolvable_reversal(f, monkeypatch):
    original, _ = prepared(f)
    for refund in ({"status": "DRAFT"}, {"status": "POSTED", "is_reversed": False}):
        with pytest.raises(FinanceRequestError) as error:
            require_full_reversal_eligible(original, [refund])
        assert error.value.status_code == 409 and error.value.code == "FINANCE_UNRESOLVED_REFUND"
    require_full_reversal_eligible(original, [{"is_reversed": True}])
    # No refund/inventory persistence exists in P03; HTTP links cannot be seeded.
    # Guard + command wiring prove refusal; future adapters must supply real links.
    def refuse(result, prior_refunds):
        assert result["id"] == original["id"] and prior_refunds == []
        raise FinanceRequestError(409, "FINANCE_UNRESOLVED_REFUND")
    monkeypatch.setattr("app.finance.ledger_service.require_full_reversal_eligible", refuse, raising=False)
    before = snapshot(f, original["id"])
    response = reverse(f, original["id"])
    assert response.status_code == 409 and response.json()["error_code"] == "FINANCE_UNRESOLVED_REFUND"
    assert reversal_counts(f) == {"headers": 0, "payments": 0, "entries": 0, "audit": 0, "keys": 0}
    assert snapshot(f, original["id"]) == before


def test_payment_racing_reversal_has_consistent_single_outcome(f):
    from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
    draft, aid = create_draft(f), account(f)
    assert post(f, draft, [payment(aid, "2.30")]).status_code == 200
    before = snapshot(f, draft["id"], ("transactions", "transaction_items"))
    async def run():
        barrier = asyncio.Barrier(2)
        connections = []
        resolve = SqlAlchemyHouseholdAccess.resolve
        async def synchronized(self, *args, **kwargs):
            connections.append(await self.session.scalar(text("SELECT pg_backend_pid()")))
            await asyncio.wait_for(barrier.wait(), timeout=10)
            return await resolve(self, *args, **kwargs)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(SqlAlchemyHouseholdAccess, "resolve", synchronized)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
                async def send(suffix, body, role):
                    return await client.post(f"/api/v1/households/{f.hid}/transactions/{draft['id']}/{suffix}",
                        headers=f.actors[role].headers | {"Idempotency-Key": suffix}, json=body)
                responses = await asyncio.gather(send("payments", {"payments": [payment(aid, "5.00")]}, "OWNER"),
                                                 send("reversals", REASON, "FINANCE_MANAGER"))
        assert len(connections) == len(set(connections)) == 2
        return responses
    paid, reversed_response = asyncio.run(run())
    assert reversed_response.status_code == 201, reversed_response.text
    assert paid.status_code in {201, 409}
    expected = 2 if paid.status_code == 201 else 1
    assert reversal_counts(f) == {"headers": 1, "payments": expected, "entries": expected, "audit": 1, "keys": 1}
    original_payments = rows(f, "transaction_payments", draft["id"])
    rid = reversed_response.json()["reversal_transaction"]["id"]
    mirrors = rows(f, "transaction_payments", rid)
    assert len(original_payments) == expected
    assert {p["reverses_payment_id"] for p in mirrors} == {p["id"] for p in original_payments}
    assert snapshot(f, draft["id"], ("transactions", "transaction_items")) == before
    assert_zero(f)


def test_cannot_reverse_draft_or_reversal(f):
    draft = create_draft(f)
    assert reverse(f, draft["id"]).status_code == 409
    assert post(f, draft).status_code == 200
    response = reverse(f, draft["id"])
    assert response.status_code == 201, response.text
    assert reverse(f, response.json()["reversal_transaction"]["id"]).status_code == 409
    assert reverse(f, draft["id"], key="different").status_code == 409
    foreign = f.client.post(f"/api/v1/households/{f.other_hid}/transactions",
        headers=f.actors["OUTSIDER"].headers | {"Idempotency-Key": "foreign"}, json=DRAFT).json()
    for tid in (foreign["id"], 9223372036854775807):
        assert reverse(f, tid).status_code == 404
    for body in ({}, {"reason": " \t "}, {"reason": "a" * 1001}, REASON | {"amount": "1"}):
        assert reverse(f, draft["id"], json=body).status_code == 422


def test_reversal_after_reconciliation_does_not_rewrite_closed_session(f):
    original, _ = prepared(f)
    before = snapshot(f, original["id"])
    response = reverse(f, original["id"])
    assert response.status_code == 201, response.text
    assert snapshot(f, original["id"]) == before
    originals = rows(f, "account_ledger_entries", original["id"])
    mirrors = rows(f, "account_ledger_entries", response.json()["reversal_transaction"]["id"])
    # Step 5 has no reconciliation tables/endpoints yet. Appending proves history
    # preservation; new entries are outstanding for a later session, never reopened.
    assert len(mirrors) == len(originals) == 1
    assert mirrors[0]["id"] != originals[0]["id"]
    assert mirrors[0]["posted_at"] > originals[0]["posted_at"]
    visible = f.request("GET", "/ledger", params={"date_from": mirrors[0]["posted_at"].isoformat()}).json()["items"]
    assert [e["id"] for e in visible] == [mirrors[0]["id"]]


def test_zero_payment_reversal_is_header_only(f):
    # OPEN-08 PROPOSAL: unpaid bill reversal appends a header, never a zero entry.
    aid, draft = account(f), create_draft(f)
    assert post(f, draft).status_code == 200
    response = reverse(f, draft["id"])
    assert response.status_code == 201, response.text
    assert response.json()["payment_ids"] == response.json()["ledger_entry_ids"] == []
    assert reversal_counts(f) == {"headers": 1, "payments": 0, "entries": 0, "audit": 1, "keys": 1}
    assert not query(f, "SELECT id FROM account_ledger_entries WHERE household_id=:hid")
    assert f.request("GET", f"/transactions/{draft['id']}").json()["is_reversed"] is True
    assert Decimal(f.request("GET", f"/accounts/{aid}/balance").json()["balance"]) == 0
    assert_zero(f)


def test_archived_account_reversal_is_allowed(f):
    # OPEN-11 PROPOSAL reversal exception; ordinary settlement remains blocked.
    original, aids = prepared(f)
    assert f.request("POST", f"/accounts/{aids[0]}/archive").status_code == 204
    response = reverse(f, original["id"])
    assert response.status_code == 201, response.text
    assert reversal_counts(f) == {"headers": 1, "payments": 1, "entries": 1, "audit": 1, "keys": 1}
    assert_zero(f)


def test_transfer_reversal_mirrors_both_legs(f):
    aids = [account(f), account(f)]
    draft = create_draft(f, kind="TRANSFER", items=[])
    assert post(f, draft, [payment(aids[0]), payment(aids[1], direction="IN")]).status_code == 200
    response = reverse(f, draft["id"])
    assert response.status_code == 201, response.text
    rid = response.json()["reversal_transaction"]["id"]
    mirrors = rows(f, "transaction_payments", rid)
    entries = rows(f, "account_ledger_entries", rid)
    assert [p["direction"] for p in mirrors] == ["IN", "OUT"]
    assert [p["account_id"] for p in mirrors] == aids
    assert [p["reverses_payment_id"] for p in mirrors] == [p["id"] for p in rows(f, "transaction_payments", draft["id"])]
    assert [e["signed_amount"] for e in entries] == [Decimal("12.30"), Decimal("-12.30")]
    assert [e["payment_id"] for e in entries] == [p["id"] for p in mirrors]
    assert_zero(f)


def test_reversal_reason_and_actor_are_audited(f):
    original, _ = prepared(f)
    response = reverse(f, original["id"], role="FINANCE_MANAGER", json={"reason": "  Audited correction  "})
    assert response.status_code == 201, response.text
    audit, = query(f, "SELECT * FROM audit_logs WHERE household_id=:hid AND action='FINANCE_REVERSED'")
    assert audit["actor_member_id"] == f.actors["FINANCE_MANAGER"].member_id
    assert audit["target_type"] == "transaction"
    assert audit["target_id"] == str(response.json()["reversal_transaction"]["id"])
    assert audit["details"]["original_transaction_id"] == original["id"]
    assert audit["details"]["reversal_reason"] == "Audited correction"


def test_persisted_incomplete_mirror_rolls_back(f, monkeypatch):
    original, _ = prepared(f)
    create = SqlAlchemyFinanceRepository.create
    async def corrupt(self, resource, values):
        if resource == "ledger" and values.get("reverses_entry_id") is not None:
            values = values | {"signed_amount": Decimal("1.00")}
        return await create(self, resource, values)
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "create", corrupt)
    response = reverse(f, original["id"], key="incomplete")
    assert response.status_code == 409 and response.json()["error_code"] == "FINANCE_REVERSAL_INCOMPLETE"
    assert reversal_counts(f) == {"headers": 0, "payments": 0, "entries": 0, "audit": 0, "keys": 0}
    assert not query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='incomplete'")
    assert f.request("GET", f"/transactions/{original['id']}").json()["is_reversed"] is False
