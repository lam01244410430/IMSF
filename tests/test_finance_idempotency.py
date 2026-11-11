"""Real PostgreSQL commands, independent connections and barrier-controlled races."""
import asyncio

import httpx
import pytest
from sqlalchemy import text

from test_finance_transactions import account, assert_balances, create_draft, payment, post, query


def counts(f, tid):
    params = {"tid": tid}
    result = {table: query(f, f"SELECT count(*) AS n FROM {table} WHERE household_id=:hid AND transaction_id=:tid", **params)[0]["n"]
              for table in ("transaction_payments", "account_ledger_entries")}
    result["audit"] = query(f, "SELECT count(*) AS n FROM audit_logs WHERE household_id=:hid AND action IN ('FINANCE_POSTED','FINANCE_PAYMENTS_CREATED') AND target_id=:tid", tid=str(tid))[0]["n"]
    result["keys"] = query(f, "SELECT count(*) AS n FROM idempotency_requests WHERE household_id=:hid AND (operation LIKE :post OR operation LIKE :pay)", post=f"%/transactions/{tid}/post:v1", pay=f"%/transactions/{tid}/payments:v1")[0]["n"]
    assert not query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND response_body ? '_pending'")
    assert_balances(f)
    return result


def test_same_key_same_payload_replays_identical_status_body(f):
    draft, aid = create_draft(f), account(f)
    first = post(f, draft, [payment(aid, "2")], key="same")
    second = post(f, draft, [payment(aid, "2.00")], key="same")
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    path = f"/transactions/{draft['id']}/payments"
    first = f.request("POST", path, key="same", json={"payments": [payment(aid, "3")]})
    second = f.request("POST", path, key="same", json={"payments": [payment(aid, "3.00")]})
    assert first.status_code == second.status_code == 201
    assert first.content == second.content
    assert counts(f, draft["id"]) == {"transaction_payments": 2, "account_ledger_entries": 2, "audit": 2, "keys": 2}


def test_same_key_different_payload_conflicts(f):
    draft, aid = create_draft(f), account(f)
    assert post(f, draft, [payment(aid, "2")], key="same").status_code == 200
    assert post(f, draft, [payment(aid, "3")], key="same").status_code == 409
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 1, "keys": 1}


def test_key_scope_includes_household_actor_operation_and_target(f):
    aid = account(f)
    drafts = [create_draft(f), create_draft(f)]
    for draft in drafts:
        assert post(f, draft, [payment(aid, "1")], key="scope").status_code == 200
        for role in ("OWNER", "FINANCE_MANAGER"):
            r = f.request("POST", f"/transactions/{draft['id']}/payments", role=role, key="scope", json={"payments": [payment(aid, "1")]})
            assert r.status_code == 201, r.text
            assert_balances(f)
        assert counts(f, draft["id"]) == {"transaction_payments": 3, "account_ledger_entries": 3, "audit": 3, "keys": 3}
    async def join():
        async with f.db() as db, db.begin():
            await db.execute(text("INSERT INTO household_members(household_id,user_id,role_id) SELECT :other,:uid,id FROM roles WHERE code='OWNER'"), {"other": f.other_hid, "uid": f.actors["OWNER"].id})
    asyncio.run(join())
    # Same authenticated user, another membership/household and identical key.
    r = f.client.post(f"/api/v1/households/{f.other_hid}/transactions", headers=f.actors["OWNER"].headers | {"Idempotency-Key": "scope"}, json={"kind": "INCOME", "occurred_at": "2026-01-01T00:00:00Z", "currency_code": "USD", "total_amount": "1", "items": [{"line_no": 1, "description": "Other household bill", "quantity": "1", "net_amount": "1"}]})
    assert r.status_code == 201
    assert f.client.post(f"/api/v1/households/{f.other_hid}/transactions/{r.json()['id']}/post", headers=f.actors["OWNER"].headers | {"Idempotency-Key": "scope"}, json={"payments": []}).status_code == 200


async def race(f, path, bodies, keys):
    from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
    barrier = asyncio.Barrier(2)
    connections = []
    original = SqlAlchemyHouseholdAccess.resolve
    async def synchronized(self, *args, **kwargs):
        # Barrier inside actual application transactions, before any row locks.
        connections.append(await self.session.scalar(text("SELECT pg_backend_pid()")))
        await asyncio.wait_for(barrier.wait(), timeout=10)
        return await original(self, *args, **kwargs)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(SqlAlchemyHouseholdAccess, "resolve", synchronized)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
            async def send(index):
                return await client.post(f"/api/v1/households/{f.hid}" + path,
                    headers=f.actors[("OWNER", "FINANCE_MANAGER")[index] if keys[0] != keys[1] else "OWNER"].headers | {"Idempotency-Key": keys[index]}, json=bodies[index])
            responses = await asyncio.gather(send(0), send(1))
    assert len(connections) == len(set(connections)) == 2
    return responses


def test_concurrent_same_key_commits_one_effect(f):
    draft, aid = create_draft(f), account(f)
    body = {"payments": [payment(aid)]}
    responses = asyncio.run(race(f, f"/transactions/{draft['id']}/post", [body, body], ["race", "race"]))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].content == responses[1].content
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 1, "keys": 1}


def test_conflicting_concurrent_payload_has_one_winner(f):
    draft, aid = create_draft(f), account(f)
    responses = asyncio.run(race(f, f"/transactions/{draft['id']}/post", [{"payments": [payment(aid, "1")]}, {"payments": [payment(aid, "2")]}], ["race", "race"]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 1, "keys": 1}


def test_different_keys_cannot_post_same_draft_twice(f):
    draft, aid = create_draft(f), account(f)
    body = {"payments": [payment(aid)]}
    responses = asyncio.run(race(f, f"/transactions/{draft['id']}/post", [body, body], ["one", "two"]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 1, "keys": 1}


def test_competing_partial_payments_cannot_overpay(f):
    draft, aid = create_draft(f), account(f)
    assert post(f, draft).status_code == 200
    body = {"payments": [payment(aid, "10")]}
    responses = asyncio.run(race(f, f"/transactions/{draft['id']}/payments", [body, body], ["one", "two"]))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 2, "keys": 2}


def test_crash_before_commit_rolls_back_reservation_and_effects(f, monkeypatch):
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
    draft, aid = create_draft(f), account(f)
    original = SqlAlchemyFinanceRepository.complete
    async def crash(self, *args):
        await original(self, *args)
        raise RuntimeError("crash before commit")
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "complete", crash)
    with pytest.raises(RuntimeError, match="crash before commit"):
        post(f, draft, [payment(aid)], key="crash")
    assert counts(f, draft["id"]) == {"transaction_payments": 0, "account_ledger_entries": 0, "audit": 0, "keys": 0}
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "complete", original)
    assert post(f, draft, [payment(aid)], key="crash").status_code == 200
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 1, "keys": 1}


def test_response_lost_after_commit_replays(f, monkeypatch):
    import app.api.finance as api
    draft, aid = create_draft(f), account(f)
    original = api.saved_response
    def lost(result):
        raise RuntimeError("response lost after commit")
    monkeypatch.setattr(api, "saved_response", lost)
    with pytest.raises(RuntimeError, match="response lost after commit"):
        post(f, draft, [payment(aid)], key="lost")
    monkeypatch.setattr(api, "saved_response", original)
    r = post(f, draft, [payment(aid)], key="lost")
    assert r.status_code == 200
    saved = query(f, "SELECT response_body FROM idempotency_requests WHERE household_id=:hid AND request_key='lost'")[0]
    assert r.json() == saved["response_body"]
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 1, "keys": 1}


@pytest.mark.parametrize("change,expected", [("role", 403), ("session", 401), ("member", 404)])
def test_revoked_role_or_session_cannot_replay_saved_success(f, change, expected):
    draft, aid = create_draft(f), account(f)
    assert post(f, draft, [payment(aid)], key="revoke", role="FINANCE_MANAGER").status_code == 200
    async def revoke():
        actor = f.actors["FINANCE_MANAGER"]
        sql, identifier = {
            "role": ("UPDATE household_members SET role_id=(SELECT id FROM roles WHERE code='VIEWER') WHERE id=:id", actor.member_id),
            "member": ("UPDATE household_members SET removed_at=now() WHERE id=:id", actor.member_id),
            "session": ("UPDATE auth_sessions SET revoked_at=now() WHERE id=:id", actor.session_id),
        }[change]
        async with f.db() as db, db.begin():
            await db.execute(text(sql), {"id": identifier})
    asyncio.run(revoke())
    assert post(f, draft, [payment(aid)], key="revoke", role="FINANCE_MANAGER").status_code == expected
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 1, "keys": 1}


@pytest.mark.parametrize("sqlstate", ["40001", "40P01", "08006"])
def test_retry_restarts_whole_transaction(f, monkeypatch, sqlstate):
    from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
    draft, aid = create_draft(f), account(f)
    original, resolve = SqlAlchemyFinanceRepository.complete, SqlAlchemyHouseholdAccess.resolve
    transactions, authorizations = [], []
    async def tracked(self, *args, **kwargs):
        authorizations.append(1)
        return await resolve(self, *args, **kwargs)
    async def transient(self, *args):
        transactions.append(await self.session.scalar(text("SELECT txid_current()")))
        await original(self, *args)
        if len(transactions) < 3:
            # Real PostgreSQL transient failure after all effects, no fake repository.
            await self.session.execute(text(f"DO $$ BEGIN RAISE EXCEPTION 'retry fixture' USING ERRCODE='{sqlstate}'; END $$"))
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "complete", transient)
    monkeypatch.setattr(SqlAlchemyHouseholdAccess, "resolve", tracked)
    assert post(f, draft, [payment(aid)], key="retry").status_code == 200
    assert len(transactions) == len(set(transactions)) == len(authorizations) == 3
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 1, "keys": 1}



def test_concurrent_openings_allow_only_first_entry(f):
    aid = account(f)
    first, second = create_draft(f, kind="OPENING", items=[]), create_draft(f, kind="OPENING", items=[])
    # Distinct draft targets; account lock must enforce opening once.
    async def run():
        from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
        barrier = asyncio.Barrier(2)
        original = SqlAlchemyHouseholdAccess.resolve
        async def synchronized(self, *args, **kwargs):
            await self.session.scalar(text("SELECT pg_backend_pid()"))
            await asyncio.wait_for(barrier.wait(), timeout=10)
            return await original(self, *args, **kwargs)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(SqlAlchemyHouseholdAccess, "resolve", synchronized)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
                async def send(draft, role):
                    return await client.post(f"/api/v1/households/{f.hid}/transactions/{draft['id']}/post", headers=f.actors[role].headers | {"Idempotency-Key": "opening"}, json={"payments": [payment(aid)]})
                return await asyncio.gather(send(first, "OWNER"), send(second, "FINANCE_MANAGER"))
    responses = asyncio.run(run())
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert sum(counts(f, d["id"])["transaction_payments"] for d in (first, second)) == 1


def test_saved_draft_edit_rechecks_creator_before_replay(f):
    draft = create_draft(f, role="MEMBER")
    path = f"/transactions/{draft['id']}"
    first = f.request("PATCH", path, role="MEMBER", key="creator", json={"total_amount": "12.30"})
    assert first.status_code == 200
    # Another draft editor becomes MEMBER after creating/editing someone else's draft.
    first = f.request("PATCH", path, role="FINANCE_MANAGER", key="editor", json={"total_amount": "12.30"})
    assert first.status_code == 200
    assert post(f, draft).status_code == 200
    assert f.request("PATCH", path, role="MEMBER", key="creator", json={"total_amount": "12.30"}).status_code == 200
    async def demote():
        async with f.db() as db, db.begin():
            await db.execute(text("UPDATE household_members SET role_id=(SELECT id FROM roles WHERE code='MEMBER') WHERE id=:id"), {"id": f.actors["FINANCE_MANAGER"].member_id})
    asyncio.run(demote())
    assert f.request("PATCH", path, role="FINANCE_MANAGER", key="editor", json={"total_amount": "12.30"}).status_code == 403


def test_retry_budget_rolls_back_and_leaves_key_reusable(f, monkeypatch):
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
    draft, aid = create_draft(f), account(f)
    original = SqlAlchemyFinanceRepository.complete
    attempts = []
    async def always_transient(self, *args):
        attempts.append(await self.session.scalar(text("SELECT txid_current()")))
        await original(self, *args)
        await self.session.execute(text("DO $$ BEGIN RAISE EXCEPTION 'retry budget fixture' USING ERRCODE='40001'; END $$"))
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "complete", always_transient)
    r = post(f, draft, [payment(aid)], key="budget")
    assert r.status_code == 409 and r.json()["error_code"] == "FINANCE_RETRY_EXHAUSTED"
    assert len(attempts) == len(set(attempts)) == 3
    assert counts(f, draft["id"]) == {"transaction_payments": 0, "account_ledger_entries": 0, "audit": 0, "keys": 0}
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "complete", original)
    assert post(f, draft, [payment(aid)], key="budget").status_code == 200
    assert counts(f, draft["id"]) == {"transaction_payments": 1, "account_ledger_entries": 1, "audit": 1, "keys": 1}
