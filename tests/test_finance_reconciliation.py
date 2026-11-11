"""Manual observations never alter books; PROPOSAL OPEN-09/10/14 contracts."""
import asyncio
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool

from test_finance_transactions import account, create_draft, payment, post, query, assert_balances
from test_finance_reversals import reverse


def entry(f, aid, amount="1", *, currency="USD", kind="INCOME", **changes):
    draft = create_draft(f, kind=kind, currency_code=currency, total_amount=amount,
        items=[] if kind == "OPENING" else [{"line_no": 1, "description": "Observation fixture", "quantity": "1", "net_amount": amount}], **changes)
    assert post(f, draft, [payment(aid, amount, currency_code=currency, direction="IN")]).status_code == 200
    return query(f, "SELECT * FROM account_ledger_entries WHERE household_id=:hid AND transaction_id=:tid", tid=draft["id"])[0]


def session_body(aid, balance="0", currency="USD"):
    return {"account_id": aid, "currency_code": currency, "statement_date": "2026-11-11",
            "statement_balance": balance, "statement_source": "BANK_STATEMENT", "statement_reference": "Manual test observation"}


def open_session(f, aid, balance="0", currency="USD"):
    r = f.request("POST", "/reconciliations", json=session_body(aid, balance, currency))
    assert r.status_code == 201, r.text
    return r.json()


def path(s):
    return f"/reconciliations/{s['session_id']}"


def match(f, s, lid):
    return f.request("POST", path(s) + "/matches", json={"ledger_entry_id": lid})


def close(f, s, ids=(), **kw):
    return f.request("POST", path(s) + "/close", json={"acknowledged_outstanding_entry_ids": list(ids)}, **kw)


def codes(report):
    return {i["code"] for i in report["integrity_issues"]}


def books(f):
    return {t: query(f, f"SELECT row_to_json(t)::text AS bytes FROM {t} t WHERE household_id=:hid ORDER BY id")
            for t in ("account_ledger_entries", "transaction_payments", "transactions")}


def test_balance_is_ledger_sum_per_currency(f):
    aid, bid = account(f), account(f, "EUR")
    entry(f, aid, "0.10"); entry(f, aid, "0.20"); entry(f, bid, "7", currency="EUR")
    r = f.request("GET", "/finance/integrity")
    assert r.status_code == 200, r.text
    assert {(a["account_id"], a["currency_code"], Decimal(a["balance"]), a["entry_count"], a["payment_count"]) for a in r.json()["accounts"]} == {(aid, "USD", Decimal("0.30"), 2, 2), (bid, "EUR", Decimal("7"), 1, 1)}
    assert r.json()["integrity_issues"] == []
    assert_balances(f)


def test_partial_bill_integrity_uses_payments_not_header_total(f):
    aid, draft = account(f), create_draft(f)
    assert post(f, draft, [payment(aid, "2.30")]).status_code == 200
    r = f.request("GET", "/finance/integrity", params={"account_id": aid, "currency_code": "USD"})
    assert r.status_code == 200 and r.json()["integrity_issues"] == []
    assert Decimal(r.json()["accounts"][0]["balance"]) == Decimal("-2.30")


def corruption_check(f, urls, expected):
    """Migrator inserts inconsistent test rows inside rollback; guards stay enabled."""
    async def run():
        from app.finance.reconciliation_service import ReconciliationService
        from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
        from test_finance_migration import raw_seed
        engine = create_async_engine(urls[0], poolclass=NullPool)
        async with engine.connect() as c:
            outer = await c.begin()
            p = await raw_seed(c, f)  # two payments exceed total; second lacks entry
            # Existing append-only rows stay untouched. A wrong-sign new entry is permitted DDL.
            await c.execute(text("INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,payment_id) VALUES (:hid,:tid,:aid,'USD',1,now(),:pid2)"), p)
            await c.execute(text("INSERT INTO transaction_payments(household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id) VALUES (:hid,:tid,:aid,'USD',1,1,'OUT',now(),:mid)"), p)
            transfer = await c.scalar(text("INSERT INTO transactions(household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id,posted_at) VALUES (:hid,'TRANSFER','POSTED',now(),'USD',1,:mid,now()) RETURNING id"), p)
            await c.execute(text("INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at) VALUES (:hid,:transfer,:aid,'USD',1,now())"), p | {"transfer": transfer})
            rid = await c.scalar(text("INSERT INTO transactions(household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id,posted_at,original_transaction_id,reversal_reason) VALUES (:hid,'REVERSAL','POSTED',now(),'USD',1,:mid,now(),:tid,'Corruption fixture') RETURNING id"), p)
            await c.execute(text("INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at) VALUES (:hid,:rid,:aid,'USD',2,now())"), p | {"rid": rid})
            async with AsyncSession(bind=c) as db:
                svc = ReconciliationService(db, SqlAlchemyFinanceRepository(db), None)
                issues = await svc.integrity_issues(f.hid)
                assert expected <= {i["code"] for i in issues}
                missing = next(i for i in issues if i["code"] == "PAYMENT_LEDGER_MISSING")
                assert missing["payment_id"] is not None and Decimal(missing["actual_amount"]) == 0
                assert Decimal(missing["expected_amount"]) == -1
            await outer.rollback()
        await engine.dispose()
    before = books(f)
    asyncio.run(run())
    assert books(f) == before


def test_missing_or_mismatched_entry_is_reported_without_correction(f, finance_database_urls):
    corruption_check(f, finance_database_urls, {"PAYMENT_LEDGER_MISSING", "PAYMENT_LEDGER_MISMATCH"})


def test_first_session_includes_opening_entry(f):
    aid = account(f); e = entry(f, aid, "10", kind="OPENING")
    s = open_session(f, aid, "10")
    assert Decimal(s["previous_statement_balance"]) == 0 and s["previous_session_id"] is None
    assert s["unmatched_entry_ids"] == [e["id"]]
    assert match(f, s, e["id"]).status_code == 201
    r = close(f, s)
    assert r.status_code == 200 and r.json()["state"] == "CLOSED"
    assert Decimal(r.json()["expected_closing_balance"]) == 10
    assert query(f, "SELECT state,closed_by_member_id FROM reconciliation_sessions WHERE household_id=:hid")[0] == {"state": "CLOSED", "closed_by_member_id": f.actors["OWNER"].member_id}


def test_prior_closed_balance_plus_matches_equals_statement(f):
    aid = account(f); a = entry(f, aid, "10")
    s = open_session(f, aid, "10"); assert match(f, s, a["id"]).status_code == 201
    assert close(f, s).status_code == 200
    b = entry(f, aid, "2.30"); later = open_session(f, aid, "12.30")
    assert later["previous_session_id"] == s["session_id"]
    assert Decimal(later["previous_statement_balance"]) == 10
    assert match(f, later, b["id"]).status_code == 201
    assert close(f, later).status_code == 200
    assert len(query(f, "SELECT id FROM reconciliation_matches WHERE household_id=:hid AND unmatched_at IS NULL")) == 2


def test_nonzero_difference_blocks_close(f):
    s = open_session(f, account(f), "0.01")
    assert "STATEMENT_DIFFERENCE" in codes(s) and not s["close_eligible"]
    r = close(f, s); assert r.status_code == 409
    assert r.json()["error_code"] == "FINANCE_RECONCILIATION_NOT_CLOSABLE" and r.json()["details"] == {}
    assert query(f, "SELECT state FROM reconciliation_sessions WHERE household_id=:hid")[0]["state"] == "OPEN"


def test_unmatched_entries_are_reported_and_require_approved_acknowledgment(f):
    # OPEN-09 PROPOSAL; the historical plan name does not imply policy approval.
    aid = account(f); e = entry(f, aid); s = open_session(f, aid)
    assert s["unmatched_count"] == 1 and "UNMATCHED_LEDGER" in codes(s)
    assert close(f, s).status_code == 409
    assert close(f, s, [e["id"]]).status_code == 200


@pytest.mark.parametrize("currency", ["USD", "EUR"])
def test_wrong_account_or_currency_match_rejected(f, currency):
    aid = account(f); other = account(f, currency); e = entry(f, other, currency=currency)
    s = open_session(f, aid)
    r = match(f, s, e["id"])
    assert r.status_code == 422 and r.json()["error_code"] == "FINANCE_MATCH_ENTRY_INVALID"
    assert not query(f, "SELECT id FROM reconciliation_matches WHERE household_id=:hid")


def test_entry_cannot_be_actively_matched_twice(f):
    aid = account(f); e = entry(f, aid); s = open_session(f, aid, "1")
    assert match(f, s, e["id"]).status_code == 201
    r = match(f, s, e["id"]); assert r.status_code == 409 and r.json()["error_code"] == "FINANCE_MATCH_CONFLICT"
    assert close(f, s).status_code == 200
    later = open_session(f, aid, "1")
    assert match(f, later, e["id"]).status_code == 409
    assert len(query(f, "SELECT id FROM reconciliation_matches WHERE household_id=:hid")) == 1


def test_unmatch_retains_history(f):
    aid = account(f); e = entry(f, aid); s = open_session(f, aid, "1")
    m = match(f, s, e["id"]); assert m.status_code == 201
    mid = query(f, "SELECT id FROM reconciliation_matches WHERE household_id=:hid")[0]["id"]
    r = f.request("POST", path(s) + f"/matches/{mid}/unmatch", json={"reason": "  Incorrect selection  "})
    assert r.status_code == 200 and r.json()["unmatched_entry_ids"] == [e["id"]]
    retained = query(f, "SELECT * FROM reconciliation_matches WHERE household_id=:hid")[0]
    assert retained["unmatched_at"] is not None and retained["unmatched_by_member_id"] == f.actors["OWNER"].member_id
    assert match(f, s, e["id"]).status_code == 201
    assert len(query(f, "SELECT id FROM reconciliation_matches WHERE household_id=:hid")) == 2
    audit = query(f, "SELECT details FROM audit_logs WHERE household_id=:hid AND action='FINANCE_RECONCILIATION_UNMATCHED'")[0]
    assert audit["details"]["reason"] == "Incorrect selection"


def test_closed_session_is_immutable(f):
    aid = account(f); e = entry(f, aid); s = open_session(f, aid, "1")
    assert match(f, s, e["id"]).status_code == 201
    mid = query(f, "SELECT id FROM reconciliation_matches WHERE household_id=:hid")[0]["id"]
    assert close(f, s).status_code == 200
    before = query(f, "SELECT row_to_json(s)::text AS bytes FROM reconciliation_sessions s WHERE household_id=:hid")
    for suffix, body in [("/matches", {"ledger_entry_id": e["id"]}), (f"/matches/{mid}/unmatch", {"reason": "Wrong"}), ("/close", {"acknowledged_outstanding_entry_ids": []}), ("/refresh-cutoff", {})]:
        r = f.request("POST", path(s)+suffix, json=body)
        assert r.status_code == 409 and r.json()["error_code"] == "FINANCE_SESSION_CLOSED"
    assert query(f, "SELECT row_to_json(s)::text AS bytes FROM reconciliation_sessions s WHERE household_id=:hid") == before


@pytest.mark.parametrize("posting", [True, False])
@pytest.mark.parametrize("close_first", [True, False])
def test_post_racing_close_cannot_change_report_silently(f, monkeypatch, posting, close_first):
    from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
    aid = account(f); s = open_session(f, aid); draft = create_draft(f)
    if not posting:
        assert post(f, draft).status_code == 200
    original = SqlAlchemyHouseholdAccess.resolve
    async def run():
        barrier = asyncio.Barrier(2); pids = set()
        closed, posted = asyncio.Event(), asyncio.Event()
        async def gated(self, actor, *args, **kwargs):
            # Begin both real DB transactions before identity's household lock,
            # exactly like the established reversal race pattern. Control both
            # serialization outcomes without sleeps or bypassing authorization.
            pids.add(await self.session.scalar(text("SELECT pg_backend_pid()")))
            await asyncio.wait_for(barrier.wait(), 10)
            if close_first and actor.user_id == f.actors["FINANCE_MANAGER"].id:
                await asyncio.wait_for(closed.wait(), 10)
            if not close_first and actor.user_id == f.actors["OWNER"].id:
                await asyncio.wait_for(posted.wait(), 10)
            return await original(self, actor, *args, **kwargs)
        monkeypatch.setattr(SqlAlchemyHouseholdAccess, "resolve", gated)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as c:
            async def closing():
                r = await c.post(f"/api/v1/households/{f.hid}"+path(s)+"/close", headers=f.actors["OWNER"].headers | {"Idempotency-Key": "race-close"}, json={"acknowledged_outstanding_entry_ids": []})
                closed.set()
                return r
            async def writing():
                r = await c.post(f"/api/v1/households/{f.hid}/transactions/{draft['id']}/{'post' if posting else 'payments'}", headers=f.actors["FINANCE_MANAGER"].headers | {"Idempotency-Key": "race-post"}, json={"payments": [payment(aid)]})
                posted.set()
                return r
            a, b = await asyncio.gather(closing(), writing())
            assert b.status_code == (200 if posting else 201)
            assert a.status_code == (200 if close_first else 409)
            assert len(pids) == 2
            return a
    r = asyncio.run(run()); monkeypatch.setattr(SqlAlchemyHouseholdAccess, "resolve", original)
    report = f.request("GET", path(s)+"/discrepancies").json()
    if close_first:
        assert report == r.json() and report["cutoff_ledger_entry_id"] is None
    else:
        assert "CUTOFF_STALE" in codes(report) and report["state"] == "OPEN"
    assert_balances(f)


def test_backdated_occurred_at_does_not_change_closed_cutoff(f):
    aid = account(f); s = open_session(f, aid); closed = close(f, s)
    assert closed.status_code == 200
    e = entry(f, aid, occurred_at="2000-01-01T00:00:00Z")
    assert f.request("GET", path(s)).json() == closed.json()
    assert open_session(f, aid)["unmatched_entry_ids"] == [e["id"]]


def test_new_reversal_remains_outstanding_for_later_statement(f):
    aid = account(f); e = entry(f, aid); s = open_session(f, aid, "1")
    assert match(f, s, e["id"]).status_code == 201
    closed = close(f, s); assert closed.status_code == 200
    r = reverse(f, e["transaction_id"]); assert r.status_code == 201
    mirror = r.json()["ledger_entry_ids"][0]
    assert f.request("GET", path(s)+"/discrepancies").json() == closed.json()
    later = open_session(f, aid)
    assert later["unmatched_entry_ids"] == [mirror]
    assert match(f, later, mirror).status_code == 201 and close(f, later).status_code == 200


def test_multi_currency_totals_never_combined(f):
    aid, bid = account(f), account(f, "JPY")
    entry(f, aid, "0.30"); entry(f, bid, "300", currency="JPY")
    r = f.request("GET", "/finance/integrity", params={"currency_code": "JPY"})
    assert r.status_code == 200 and len(r.json()["accounts"]) == 1
    assert r.json()["accounts"][0]["currency_code"] == "JPY"
    assert Decimal(r.json()["accounts"][0]["balance"]) == 300
    assert f.request("POST", "/reconciliations", json=session_body(aid, currency="JPY")).status_code == 422


def test_second_open_session_rejected(f):
    aid = account(f); open_session(f, aid)
    r = f.request("POST", "/reconciliations", json=session_body(aid))
    assert r.status_code == 409 and r.json()["error_code"] == "FINANCE_SESSION_ALREADY_OPEN"
    assert len(query(f, "SELECT id FROM reconciliation_sessions WHERE household_id=:hid")) == 1


def test_refresh_cutoff_is_idempotent_and_admits_new_entries(f):
    aid = account(f); s = open_session(f, aid); e = entry(f, aid)
    assert close(f, s).status_code == 409
    assert "CUTOFF_STALE" in codes(f.request("GET", path(s)).json())
    r = f.request("POST", path(s)+"/refresh-cutoff", key="refresh", json={})
    assert r.status_code == 200 and r.json()["unmatched_entry_ids"] == [e["id"]]
    assert r.content == f.request("POST", path(s)+"/refresh-cutoff", key="refresh", json={}).content
    assert r.content == f.request("POST", path(s)+"/refresh-cutoff", key="another", json={}).content
    assert match(f, s, e["id"]).status_code == 201
    assert close(f, s).status_code == 409  # statement is zero, matched total one
    mid = query(f, "SELECT id FROM reconciliation_matches WHERE household_id=:hid")[0]["id"]
    assert f.request("POST", path(s)+f"/matches/{mid}/unmatch", json={"reason": "Not on statement"}).status_code == 200
    assert close(f, s, [e["id"]]).status_code == 200


def test_close_requires_exact_acknowledgment_set(f):
    aid = account(f); e = entry(f, aid); s = open_session(f, aid)
    assert close(f, s).status_code == 409
    assert close(f, s, [e["id"], 9223372036854775807]).status_code == 409
    assert close(f, s, [e["id"], e["id"]]).status_code == 200  # SET semantics


def test_integrity_report_lists_all_issue_codes(f, finance_database_urls):
    corruption_check(f, finance_database_urls, {"PAYMENT_LEDGER_MISSING", "PAYMENT_LEDGER_MISMATCH", "TRANSFER_UNBALANCED", "OVERSETTLED", "REVERSAL_INCOMPLETE"})
    aid = account(f); entry(f, aid); s = open_session(f, aid, "2"); entry(f, aid)
    assert {"UNMATCHED_LEDGER", "STATEMENT_DIFFERENCE", "CUTOFF_STALE"} <= codes(f.request("GET", path(s)).json())


def test_no_auto_correction_on_close_or_report(f):
    aid = account(f); e = entry(f, aid); s = open_session(f, aid)
    before = books(f)
    assert f.request("GET", "/finance/integrity").status_code == 200
    assert f.request("GET", path(s)+"/discrepancies").status_code == 200
    assert close(f, s).status_code == 409
    assert close(f, s, [e["id"]]).status_code == 200
    assert books(f) == before
    assert_balances(f)


def test_closed_session_report_is_stable(f):
    aid = account(f); e = entry(f, aid); s = open_session(f, aid)
    r = close(f, s, [e["id"]]); assert r.status_code == 200
    entry(f, aid); assert reverse(f, e["transaction_id"]).status_code == 201
    later = open_session(f, aid, "1"); assert match(f, later, e["id"]).status_code == 201
    assert f.request("GET", path(s)+"/discrepancies").json() == r.json()


@pytest.mark.parametrize("changes", [{"statement_balance": 1.2}, {"statement_balance": "0.001"}, {"statement_source": "FEED"}, {"statement_reference": "x"*201}, {"currency_code": "ZZZ"}, {"balance": "1"}])
def test_session_input_validation(f, changes):
    aid = account(f)
    r = f.request("POST", "/reconciliations", json=session_body(aid) | changes)
    assert r.status_code == 422
    assert not query(f, "SELECT id FROM reconciliation_sessions WHERE household_id=:hid")


def test_reconciliation_failure_rolls_back_session_key_and_audit(f, monkeypatch):
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
    aid = account(f)
    async def fail(*args):
        raise RuntimeError("Reconciliation audit failed")
    monkeypatch.setattr(SqlAlchemyFinanceRepository, "audit", fail)
    with pytest.raises(RuntimeError, match="Reconciliation audit failed"):
        open_session(f, aid)
    assert not query(f, "SELECT id FROM reconciliation_sessions WHERE household_id=:hid")
    assert not query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND operation LIKE '%reconciliations%'")


def test_finance_manager_can_unmatch_using_only_report_ids(f):
    aid = account(f); e = entry(f, aid); s = open_session(f, aid, "1")
    created = f.request("POST", path(s)+"/matches", role="FINANCE_MANAGER", json={"ledger_entry_id": e["id"]})
    assert created.status_code == 201
    read = f.request("GET", path(s), role="FINANCE_MANAGER")
    assert read.status_code == 200
    active = read.json()["active_matches"]
    assert active == created.json()["active_matches"] and len(active) == 1
    assert active[0]["ledger_entry_id"] == e["id"]
    withdrawn = f.request("POST", path(s)+f"/matches/{active[0]['match_id']}/unmatch", role="FINANCE_MANAGER", json={"reason": "Selected wrong entry"})
    assert withdrawn.status_code == 200 and withdrawn.json()["active_matches"] == []
    persisted = query(f, "SELECT id,unmatched_by_member_id FROM reconciliation_matches WHERE household_id=:hid")[0]
    assert persisted == {"id": active[0]["match_id"], "unmatched_by_member_id": f.actors["FINANCE_MANAGER"].member_id}


@pytest.mark.parametrize("corruption", ["entry_links", "payment_links"])
def test_reversal_detector_rejects_wrong_mirrors_even_when_totals_net_zero(f, finance_database_urls, corruption):
    """Migrator-seeded equal-total corruption, entirely rolled back; no guard bypass."""
    async def run():
        from app.finance.reconciliation_service import ReconciliationService
        from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
        engine = create_async_engine(finance_database_urls[0], poolclass=NullPool)
        async with engine.connect() as c:
            outer = await c.begin()
            p = {"hid": f.hid, "mid": f.actors["OWNER"].member_id}
            aid = await c.scalar(text("INSERT INTO accounts(household_id,name,currency_code) VALUES (:hid,'Mirror fixture','USD') RETURNING id"), p)
            p["aid"] = aid
            tid = await c.scalar(text("INSERT INTO transactions(household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id,posted_at) VALUES (:hid,'INCOME','POSTED',now(),'USD',10,:mid,now()) RETURNING id"), p)
            rid = await c.scalar(text("INSERT INTO transactions(household_id,kind,status,occurred_at,currency_code,total_amount,created_by_member_id,posted_at,original_transaction_id,reversal_reason) VALUES (:hid,'REVERSAL','POSTED',now(),'USD',10,:mid,now(),:tid,'Mirror fixture') RETURNING id"), p | {"tid": tid})
            old_pids, old_eids = [], []
            for amount in ("3", "7"):
                params = p | {"tid": tid, "amount": Decimal(amount)}
                pid = await c.scalar(text("INSERT INTO transaction_payments(household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id) VALUES (:hid,:tid,:aid,'USD',:amount,:amount,'IN',now(),:mid) RETURNING id"), params)
                lid = await c.scalar(text("INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,payment_id) VALUES (:hid,:tid,:aid,'USD',:amount,now(),:pid) RETURNING id"), params | {"pid": pid})
                old_pids.append(pid); old_eids.append(lid)
            for index, amount in enumerate(("7", "3")):
                # Each payment agrees with its own ledger; only original mirror
                # links are wrong, while all account/currency totals net to zero.
                params = p | {"tid": rid, "amount": Decimal(amount),
                    "oldpid": old_pids[1-index] if corruption == "entry_links" else old_pids[index],
                    "oldlid": old_eids[index] if corruption == "entry_links" else old_eids[1-index]}
                pid = await c.scalar(text("INSERT INTO transaction_payments(household_id,transaction_id,account_id,currency_code,amount,transaction_amount,direction,settled_at,created_by_member_id,reverses_payment_id) VALUES (:hid,:tid,:aid,'USD',:amount,:amount,'OUT',now(),:mid,:oldpid) RETURNING id"), params)
                await c.execute(text("INSERT INTO account_ledger_entries(household_id,transaction_id,account_id,currency_code,signed_amount,posted_at,payment_id,reverses_entry_id) VALUES (:hid,:tid,:aid,'USD',-:amount,now(),:pid,:oldlid)"), params | {"pid": pid})
            assert await c.scalar(text("SELECT sum(signed_amount) FROM account_ledger_entries WHERE household_id=:hid"), p) == 0
            async with AsyncSession(bind=c) as db:
                service = ReconciliationService(db, SqlAlchemyFinanceRepository(db), None)
                issues = await service.integrity_issues(f.hid)
                assert "REVERSAL_INCOMPLETE" in {i["code"] for i in issues}
                assert "PAYMENT_LEDGER_MISMATCH" not in {i["code"] for i in issues}
            await outer.rollback()
        await engine.dispose()
    before = books(f)
    asyncio.run(run())
    assert books(f) == before


def test_session_pages_are_bounded_and_household_filter_scoped(f):
    aids = [account(f) for _ in range(3)]
    sessions = [open_session(f, aid) for aid in aids]
    first = f.request("GET", "/reconciliations", params={"limit": 2})
    assert first.status_code == 200
    assert [s["session_id"] for s in first.json()["items"]] == [s["session_id"] for s in sessions[:2]]
    cursor = first.json()["next_cursor"]
    second = f.request("GET", "/reconciliations", params={"limit": 2, "cursor": cursor})
    assert [s["session_id"] for s in second.json()["items"]] == [sessions[2]["session_id"]]
    assert second.json()["next_cursor"] is None
    assert f.request("GET", "/reconciliations", params={"cursor": cursor, "account_id": aids[0]}).status_code == 422
    foreign = f.client.get(f"/api/v1/households/{f.other_hid}/reconciliations", headers=f.actors["OUTSIDER"].headers, params={"cursor": cursor})
    assert foreign.status_code == 422
    for params in ({"limit": 201}, {"limit": 0}, {"cursor": "garbage"}, {"cursor": "bnVsbA=="}):
        assert f.request("GET", "/reconciliations", params=params).status_code == 422
    filtered = f.request("GET", "/reconciliations", params={"account_id": aids[1]}).json()["items"]
    assert [s["session_id"] for s in filtered] == [sessions[1]["session_id"]]


def test_unmatch_reason_and_command_bodies_are_strict(f):
    aid = account(f); e = entry(f, aid); s = open_session(f, aid)
    created = match(f, s, e["id"]); assert created.status_code == 201
    mid = created.json()["active_matches"][0]["match_id"]
    for body in ({}, {"reason": " \t "}, {"reason": "a"*1001}, {"reason": "Valid", "amount": "1"}):
        assert f.request("POST", path(s)+f"/matches/{mid}/unmatch", json=body).status_code == 422
    for suffix, body in [("/close", {}), ("/close", {"acknowledged_outstanding_entry_ids": [], "total": "0"}), ("/refresh-cutoff", {"cutoff_ledger_entry_id": e["id"]})]:
        assert f.request("POST", path(s)+suffix, json=body).status_code == 422
    assert query(f, "SELECT unmatched_at FROM reconciliation_matches WHERE household_id=:hid")[0]["unmatched_at"] is None
