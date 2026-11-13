"""Step 3 PROPOSALS: synchronized independent runtime connections, real writes."""
import asyncio
from decimal import Decimal
import httpx
import pytest
from sqlalchemy import text
from test_finance_transactions import query
from test_inventory_lots import product, receipt
from test_inventory_checkout import configure_timezone
from test_inventory_expiry import freeze_clock
from test_inventory_expiry_jobs import enqueue, jobs, finish, effects, expire


def business_snapshot(f):
    # All household-owned business tables, including finance, cooking, refunds,
    # settings and every inventory detail. Only approved operational rows differ.
    async def run():
        async with f.db() as db:
            names = (await db.execute(text("""SELECT table_name FROM information_schema.columns
                WHERE table_schema='public' AND column_name='household_id'
                AND table_name NOT IN ('scheduled_jobs','expiration_alerts','idempotency_requests')
                ORDER BY table_name"""))).scalars().all()
            return {name: (await db.execute(text(f'SELECT to_jsonb(t)::text FROM "{name}" t WHERE household_id=:hid ORDER BY to_jsonb(t)::text'), {"hid": f.hid})).scalars().all() for name in names}
    return asyncio.run(run())


def test_concurrent_expiry_workers_have_one_fenced_effect_set(f, monkeypatch):
    from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
    configure_timezone(f)
    receipt(f, product(f), expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    job = enqueue(f)
    original = SqlAlchemyExpiryJobRepository.claim_due
    async def run():
        locked, release = asyncio.Event(), asyncio.Event()
        backends = []
        async def hold(self, job_id):
            backends.append(await self.session.scalar(text("SELECT pg_backend_pid()")))
            row = await original(self, job_id)
            if row:
                locked.set()
                await release.wait()
            return row
        with monkeypatch.context() as patch:
            patch.setattr(SqlAlchemyExpiryJobRepository, "claim_due", hold)
            async with asyncio.timeout(15):
                first = asyncio.create_task(jobs(f).claim(job_id=job["id"]))
                try:
                    await locked.wait()
                    second = await jobs(f).claim(job_id=job["id"])
                    assert second is None
                finally:
                    release.set()
                claim = await first
        assert len(set(backends)) == 2
        async with f.db() as db:
            assert not await db.scalar(text("SELECT count(*) FROM expiration_alerts WHERE household_id=:hid"), {"hid": f.hid})
        # Even two deliveries of the same claim serialize and replay success.
        results = await asyncio.gather(jobs(f).batch(claim), jobs(f).batch(claim))
        assert results[0] == results[1] and results[0]["state"] == "SUCCEEDED"
    asyncio.run(run())
    assert len(effects(f)) == 1
    assert query(f, "SELECT attempt_count FROM scheduled_jobs WHERE household_id=:hid")[0]["attempt_count"] == 1


def test_expired_lease_reclaim_rejects_stale_worker_completion(f, monkeypatch):
    from app.lifecycle.jobs import LeaseLost
    from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
    configure_timezone(f)
    receipt(f, product(f), expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    job = enqueue(f)
    stale = asyncio.run(jobs(f).claim(job_id=job["id"]))
    expire(f, job["id"])
    current = asyncio.run(jobs(f).claim(job_id=job["id"]))
    assert current.token != stale.token and current.attempt_count == 2
    with pytest.raises(LeaseLost):
        asyncio.run(jobs(f).batch(stale))
    assert not effects(f)
    # Force lease expiry after a real alert INSERT, within that transaction.
    original = SqlAlchemyExpiryJobRepository.insert_alert
    async def expire_after_insert(self, values):
        inserted = await original(self, values)
        await self.session.execute(text("UPDATE scheduled_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:jid"), {"jid": job["id"]})
        return inserted
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyExpiryJobRepository, "insert_alert", expire_after_insert)
        with pytest.raises(LeaseLost):
            asyncio.run(jobs(f).batch(current))
    row = query(f, "SELECT checkpoint,result,state FROM scheduled_jobs WHERE household_id=:hid")[0]
    assert row["checkpoint"] == row["result"] == {"schema_version": 1}
    assert row["state"] == "RUNNING" and not effects(f)
    asyncio.run(finish(f, current))
    assert len(effects(f)) == 1


async def wait_for_block(f, task, blocker):
    async with asyncio.timeout(15):
        while True:
            assert not task.done(), task.result() if task.done() else None
            async with f.db() as db:
                if await db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)) AND wait_event_type='Lock'"), {"pid": blocker}):
                    return
            await asyncio.sleep(0)  # Cooperative polling of actual PG lock state; no fixed sleep.


def race_user(f, monkeypatch, action, user_first):
    from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
    from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
    configure_timezone(f)
    p = product(f)
    lot = receipt(f, p, expires_on="2026-11-12").json()
    freeze_clock(monkeypatch)
    job = enqueue(f)
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    before = business_snapshot(f)
    async def run():
        locked, release = asyncio.Event(), asyncio.Event()
        owner_pid = []
        original = (SqlAlchemyHouseholdAccess.resolve if user_first
                    else SqlAlchemyExpiryJobRepository.lock_household)
        async def hold(self, *args, **kwargs):
            row = await original(self, *args, **kwargs)
            owner_pid.append(await self.session.scalar(text("SELECT pg_backend_pid()")))
            locked.set()
            await release.wait()
            return row
        klass = SqlAlchemyHouseholdAccess if user_first else SqlAlchemyExpiryJobRepository
        method = "resolve" if user_first else "lock_household"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
            async def user():
                if action == "dispose":
                    return await client.post(f"/api/v1/households/{f.hid}/disposals",
                        headers=f.actors["INVENTORY_MANAGER"].headers | {"Idempotency-Key": "race-dispose"},
                        json={"allocations": [{"lot_id": lot["id"], "quantity": "1", "unit_id": p["base_unit_id"]}], "reason_code": "EXPIRED"})
                if action == "archive":
                    return await client.post(f"/api/v1/households/{f.hid}/inventory-lots/{lot['id']}/archive",
                        headers=f.actors["INVENTORY_MANAGER"].headers | {"Idempotency-Key": "race-archive"},
                        json={"reason": "Retain stock history"})
                return await client.patch(f"/api/v1/households/{f.hid}/inventory-lots/{lot['id']}",
                    headers=f.actors["INVENTORY_MANAGER"].headers | {"Idempotency-Key": "race-expiry"},
                    json={"expires_on": "2026-10-01", "reason": "Correct expiry"})
            with monkeypatch.context() as patch:
                patch.setattr(klass, method, hold)
                async with asyncio.timeout(20):
                    first = asyncio.create_task(user() if user_first else jobs(f).batch(claim))
                    second = None
                    try:
                        await locked.wait()
                        second = asyncio.create_task(jobs(f).batch(claim) if user_first else user())
                        await wait_for_block(f, second, owner_pid[0])
                    finally:
                        release.set()
                    results = await asyncio.gather(first, second)
            response = results[0 if user_first else 1]
            assert response.status_code == (201 if action == "dispose" else 200), response.text
    asyncio.run(run())
    if action == "archive":
        alerts = effects(f)
        assert len(alerts) == (0 if user_first else 1)
        if alerts:
            assert alerts[0]["lot_id"] == lot["id"] and alerts[0]["alert_kind"] == "WARNING"
        row = query(f, "SELECT archived_at,remaining_quantity FROM inventory_lots WHERE household_id=:hid")[0]
        assert row["archived_at"] is not None and row["remaining_quantity"] == 5
        after = business_snapshot(f)
        for name in before.keys() - {"inventory_lots", "audit_logs"}:
            assert after[name] == before[name], name
        return
    alert, = effects(f)
    assert alert["lot_id"] == lot["id"]
    if action == "expiry":
        assert str(alert["expires_on_snapshot"]) == ("2026-10-01" if user_first else "2026-11-12")
        assert alert["alert_kind"] == ("EXPIRED" if user_first else "WARNING")
        # Only the user's lot metadata, audit and key changed.
        after = business_snapshot(f)
        for name in before.keys() - {"inventory_lots", "audit_logs"}:
            assert after[name] == before[name], name
    else:
        rows = query(f, "SELECT remaining_quantity FROM inventory_lots WHERE household_id=:hid")
        assert rows[0]["remaining_quantity"] == Decimal(4)
        movements = query(f, "SELECT kind,quantity_delta FROM inventory_movements WHERE household_id=:hid ORDER BY id")
        assert [(r["kind"], r["quantity_delta"]) for r in movements] == [("RECEIPT", Decimal(5)), ("DISPOSE", Decimal(-1))]
        assert len(query(f, "SELECT id FROM disposal_records WHERE household_id=:hid")) == 1
        after = business_snapshot(f)
        for name in before.keys() - {"inventory_lots", "inventory_movements", "disposal_records", "audit_logs"}:
            assert after[name] == before[name], name


@pytest.mark.parametrize("user_first", [True, False])
def test_expiry_run_racing_partial_disposal_keeps_stock_history_unchanged_by_job(f, monkeypatch, user_first):
    race_user(f, monkeypatch, "dispose", user_first)


@pytest.mark.parametrize("user_first", [True, False])
def test_expiry_run_racing_expiry_patch_retains_consistent_observed_date(f, monkeypatch, user_first):
    race_user(f, monkeypatch, "expiry", user_first)


def test_expiry_job_success_retry_failure_and_duplicate_never_write_stock_or_finance(f, monkeypatch):
    from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
    configure_timezone(f)
    from test_inventory_lots import purchase
    p = product(f)
    tx = purchase(f, p)
    lot = receipt(f, p, source_kind="PURCHASE", purchase_item_id=tx["items"][0]["id"],
                  expires_on="2026-11-12", cost_currency="USD", unit_cost="2.46").json()
    assert f.request("POST", f"/inventory-lots/{lot['id']}/returns", json={"quantity": "1", "unit_id": p["base_unit_id"], "reason": "Retained unresolved refund"}).status_code == 201
    freeze_clock(monkeypatch)
    job = enqueue(f)
    before = business_snapshot(f)
    assert all(before[name] for name in ("transactions", "transaction_items", "transaction_payments", "account_ledger_entries", "refund_inventory_links"))
    original = SqlAlchemyExpiryJobRepository.insert_alert
    async def fault(self, values):
        await original(self, values)
        # Raise a real transient SQLSTATE after the real INSERT.
        await self.session.execute(text("DO $$ BEGIN RAISE EXCEPTION 'injected transient' USING ERRCODE='40001'; END $$"))
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyExpiryJobRepository, "insert_alert", fault)
        failed = asyncio.run(jobs(f).work(claim))
    assert failed["error_code"] == "INVENTORY_RETRY_EXHAUSTED" and failed["state"] == "RUNNING"
    assert not effects(f) and business_snapshot(f) == before
    expire(f, job["id"])
    current = asyncio.run(jobs(f).claim(job_id=job["id"]))
    completed = asyncio.run(jobs(f).work(current))
    assert completed["state"] == "SUCCEEDED" and len(effects(f)) == 1
    assert asyncio.run(jobs(f).batch(current)) == completed
    assert business_snapshot(f) == before


def test_concurrent_enqueue_and_dispatch_reuse_the_current_daily_job(f, monkeypatch):
    from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
    configure_timezone(f)
    freeze_clock(monkeypatch)
    original = SqlAlchemyExpiryJobRepository.enqueue
    async def run():
        inserted, release = asyncio.Event(), asyncio.Event()
        first_pid = []
        async def hold(self, *args, **kwargs):
            row = await original(self, *args, **kwargs)
            if not first_pid:
                first_pid.append(await self.session.scalar(text("SELECT pg_backend_pid()")))
                inserted.set()
                await release.wait()
            return row
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
            with monkeypatch.context() as patch:
                patch.setattr(SqlAlchemyExpiryJobRepository, "enqueue", hold)
                async with asyncio.timeout(20):
                    http = asyncio.create_task(client.post(f"/api/v1/households/{f.hid}/inventory/expiry-runs",
                        headers=f.actors["OWNER"].headers | {"Idempotency-Key": "concurrent-enqueue"}, json={}))
                    try:
                        await inserted.wait()
                        dispatch = asyncio.create_task(jobs(f).dispatch(after_id=f.hid - 1, limit=1))
                        await wait_for_block(f, dispatch, first_pid[0])
                    finally:
                        release.set()
                    response, result = await asyncio.gather(http, dispatch)
        assert response.status_code == 202, response.text
        assert result["job_ids"] == [response.json()["id"]]
    asyncio.run(run())
    assert len(query(f, "SELECT id FROM scheduled_jobs WHERE household_id=:hid")) == 1
    assert not effects(f)


@pytest.mark.parametrize("user_first", [True, False])
def test_expiry_run_racing_archive_retains_committed_observation_without_stock_writes(f, monkeypatch, user_first):
    race_user(f, monkeypatch, "archive", user_first)


def test_expiry_run_crossing_midnight_mid_batch_retains_first_date_then_skips_remaining(f, monkeypatch):
    from datetime import datetime
    from app.lifecycle import service
    from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
    configure_timezone(f)
    p = product(f)
    for _ in range(101):
        assert receipt(f, p, expires_on="2026-11-11", quantity="1").status_code == 201
    freeze_clock(monkeypatch, "2026-11-11T16:59:59+00:00")
    job = enqueue(f)
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    before = business_snapshot(f)
    original = SqlAlchemyExpiryJobRepository.source_page
    current = ["2026-11-11T16:59:59+00:00"]
    sampled = []
    def clock():
        sampled.append(current[0])
        return datetime.fromisoformat(current[0])
    monkeypatch.setattr(service, "utc_now", clock)
    async def run():
        observed, release = asyncio.Event(), asyncio.Event()
        worker_pid = []
        async def hold(self, *args):
            rows = await original(self, *args)
            worker_pid.append(await self.session.scalar(text("SELECT pg_backend_pid()")))
            observed.set()
            await release.wait()
            return rows
        with monkeypatch.context() as patch:
            patch.setattr(SqlAlchemyExpiryJobRepository, "source_page", hold)
            async with asyncio.timeout(30):
                task = asyncio.create_task(jobs(f).batch(claim))
                try:
                    await observed.wait()
                    # Independent observer sees no uncommitted alert/checkpoint.
                    async with f.db() as observer:
                        assert await observer.scalar(text("SELECT pg_backend_pid()")) != worker_pid[0]
                        assert not await observer.scalar(text("SELECT count(*) FROM expiration_alerts WHERE household_id=:hid"), {"hid": f.hid})
                    current[0] = "2026-11-11T17:00:00+00:00"
                finally:
                    release.set()
                first = await task
        assert first["state"] == "RUNNING" and first["scanned_count"] == first["warning_count"] == 100
        second = await jobs(f).batch(claim)
        assert second["state"] == "SUCCEEDED" and second["outcome_code"] == "SKIPPED_STALE"
        assert second["scanned_count"] == 100
    asyncio.run(run())
    assert sampled == ["2026-11-11T16:59:59+00:00", "2026-11-11T17:00:00+00:00"]
    alerts = effects(f)
    assert len(alerts) == 100 and {str(a["local_date"]) for a in alerts} == {"2026-11-11"}
    assert {a["alert_kind"] for a in alerts} == {"WARNING"}
    assert business_snapshot(f) == before
    rows = query(f, "SELECT payload,state FROM scheduled_jobs WHERE household_id=:hid ORDER BY id")
    assert [(r["payload"]["local_date"], r["state"]) for r in rows] == [("2026-11-11", "SUCCEEDED"), ("2026-11-12", "READY")]
