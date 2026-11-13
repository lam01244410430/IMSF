"""Step 2 persistence retained; Step 3 real-DB execution and recovery."""
import asyncio
import json
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_finance_transactions import query

PAYLOAD = {"schema_version": 1, "local_date": "2026-11-11", "timezone": "Asia/Ho_Chi_Minh"}
INSERT_JOB = """INSERT INTO scheduled_jobs(household_id,job_key,kind,run_after,payload)
    VALUES (:hid,:key,'INVENTORY_EXPIRY',now(),CAST(:payload AS jsonb)) RETURNING *"""


def test_job_persistence_defaults_lease_and_versioned_documents(f):
    async def run():
        async with f.db() as db, db.begin():
            row = (await db.execute(text(INSERT_JOB), {"hid": f.hid, "key": "persistence-only", "payload": json.dumps(PAYLOAD)})).mappings().one()
            assert row["state"] == "READY" and row["attempt_count"] == 0
            assert row["lease_until"] is None and row["lease_token"] is None
            assert row["completed_at"] is None and row["error_code"] is None
            assert row["created_at"].utcoffset() is not None
            assert row["checkpoint"] == row["result"] == {"schema_version": 1}
            assert row["payload"] == PAYLOAD
            with pytest.raises(DBAPIError) as error:
                async with db.begin_nested():
                    await db.execute(text(INSERT_JOB), {"hid": f.hid, "key": "persistence-only", "payload": json.dumps(PAYLOAD)})
            assert error.value.orig.sqlstate == "23505"
            # Same key in another household is legitimate persistence, no producer.
            await db.execute(text(INSERT_JOB), {"hid": f.other_hid, "key": "persistence-only", "payload": json.dumps(PAYLOAD)})
    asyncio.run(run())
    assert len(query(f, "SELECT id FROM scheduled_jobs WHERE household_id=:hid")) == 1


@pytest.mark.parametrize("payload", [None, [], {}, {"schema_version": "1"},
    PAYLOAD | {"schema_version": 2}, PAYLOAD | {"timezone": "No/Zone"},
    PAYLOAD | {"timezone": 42}, PAYLOAD | {"local_date": "2026-02-30"},
    PAYLOAD | {"local_date": "2026-1-1"}, PAYLOAD | {"client_override": True},
    PAYLOAD | {"timezone": "x" * 5000}])
def test_job_payload_is_bounded_validated_and_server_owned(f, payload):
    async def run():
        async with f.db() as db, db.begin():
            with pytest.raises(DBAPIError) as error:
                async with db.begin_nested():
                    await db.execute(text(INSERT_JOB), {"hid": f.hid, "key": "invalid", "payload": json.dumps(payload)})
            assert error.value.orig.sqlstate == "23514"
    asyncio.run(run())


@pytest.mark.parametrize("assignment", ["attempt_count=-1", "state='UNKNOWN'",
    "checkpoint='{}'::jsonb", "result='[]'::jsonb",
    "checkpoint='{\"schema_version\": 2}'::jsonb",
    "result='{\"schema_version\": 1,\"scanned_count\":-1}'::jsonb",
    "result='{\"schema_version\": 1,\"secret\":\"hidden\"}'::jsonb",
    "state='RUNNING'", "lease_until=now()", "completed_at=now()"])
def test_job_state_and_progress_constraints_reject_inconsistent_storage(f, assignment):
    async def run():
        async with f.db() as db, db.begin():
            row = (await db.execute(text(INSERT_JOB), {"hid": f.hid, "key": "constraints", "payload": json.dumps(PAYLOAD)})).mappings().one()
            with pytest.raises(DBAPIError) as error:
                async with db.begin_nested():
                    await db.execute(text(f"UPDATE scheduled_jobs SET {assignment} WHERE household_id=:hid AND id=:jid"), {"hid": f.hid, "jid": row["id"]})
            assert error.value.orig.sqlstate in {"23514", "55000"}
            await db.rollback()
    asyncio.run(run())


def test_job_key_bound_counts_original_whitespace(f):
    async def run():
        async with f.db() as db, db.begin():
            for key in [" " * 1000 + "key", "x" * 201, "", "   "]:
                with pytest.raises(DBAPIError) as error:
                    async with db.begin_nested():
                        await db.execute(text(INSERT_JOB), {"hid": f.hid, "key": key, "payload": json.dumps(PAYLOAD)})
                assert error.value.orig.sqlstate == "23514"
            row = (await db.execute(text(INSERT_JOB), {"hid": f.hid, "key": "x" * 200, "payload": json.dumps(PAYLOAD)})).mappings().one()
            assert len(row["job_key"]) == 200
    asyncio.run(run())

# Step 3 execution tests use real runtime connections and retained unique households.
from datetime import datetime, timezone
from test_inventory_lots import product, receipt
from test_inventory_checkout import configure_timezone, snapshot
from test_inventory_expiry import freeze_clock


def enqueue(f, **kwargs):
    response = f.request("POST", "/inventory/expiry-runs", json={}, **kwargs)
    assert response.status_code == 202, response.text
    return response.json()


def jobs(f):
    from app.lifecycle.jobs import ExpiryJobs
    return ExpiryJobs(f.db)


async def finish(f, claim):
    worker = jobs(f)
    while True:
        result = await worker.batch(claim)
        if result["state"] != "RUNNING":
            return result


def effects(f):
    return query(f, "SELECT * FROM expiration_alerts WHERE household_id=:hid ORDER BY lot_id,local_date")


def expire(f, jid):
    async def run():
        async with f.db() as db, db.begin():
            await db.execute(text("UPDATE scheduled_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE household_id=:hid AND id=:jid"), {"hid": f.hid, "jid": jid})
    asyncio.run(run())


def test_duplicate_daily_runs_create_one_job_and_one_alert_per_natural_key(f, monkeypatch):
    configure_timezone(f)
    receipt(f, product(f), expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    first = enqueue(f, key="enqueue")
    assert first == enqueue(f, key="enqueue")
    assert enqueue(f)["id"] == first["id"]
    before = snapshot(f)
    saved = query(f, "SELECT response_status,response_body FROM idempotency_requests WHERE household_id=:hid AND request_key='enqueue'")[0]
    assert saved["response_status"] == 200 and saved["response_body"] == first
    async def run():
        dispatched = await jobs(f).dispatch(after_id=f.hid - 1, limit=1)
        assert dispatched["job_ids"] == [first["id"]]
        claim = await jobs(f).claim(job_id=first["id"])
        assert claim and claim.attempt_count == 1
        async with f.db() as db:
            assert not await db.scalar(text("SELECT count(*) FROM expiration_alerts WHERE household_id=:hid"), {"hid": f.hid})
        result = await finish(f, claim)
        assert result["state"] == "SUCCEEDED"
        assert await jobs(f).claim(job_id=first["id"]) is None
        assert (await jobs(f).dispatch(after_id=f.hid - 1, limit=1))["job_ids"] == [first["id"]]
    asyncio.run(run())
    assert len(effects(f)) == 1
    assert snapshot(f) == before
    assert enqueue(f)["state"] == "SUCCEEDED"
    # Transport replay is the original saved 202 body, even after work completes.
    assert enqueue(f, key="enqueue") == first
    status = f.request("GET", f"/inventory/expiry-runs/{first['id']}")
    assert status.status_code == 200 and status.json()["warning_count"] == 1
    assert all(word not in status.text for word in ("lease_token", "payload", "checkpoint", "lease_until"))


def test_different_local_dates_create_distinct_daily_alerts(f, monkeypatch):
    configure_timezone(f)
    receipt(f, product(f), expires_on="2026-11-12")
    ids = []
    for instant in ["2026-11-10T17:00:00+00:00", "2026-11-11T17:00:00+00:00"]:
        freeze_clock(monkeypatch, instant)
        ids.append(enqueue(f)["id"])
        async def run():
            await finish(f, await jobs(f).claim(job_id=ids[-1]))
        asyncio.run(run())
    assert len(set(ids)) == 2
    assert [str(a["local_date"]) for a in effects(f)] == ["2026-11-11", "2026-11-12"]


def test_expiry_batch_failure_rolls_back_alerts_checkpoint_and_completion(f, monkeypatch):
    from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
    configure_timezone(f)
    receipt(f, product(f), expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    job = enqueue(f)
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    original = SqlAlchemyExpiryJobRepository.insert_alert
    async def fail(self, values):
        await original(self, values)
        assert await self.session.scalar(text("SELECT count(*) FROM expiration_alerts WHERE job_id=:jid"), {"jid": job["id"]}) == 1
        raise RuntimeError("private injected fault after INSERT")
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyExpiryJobRepository, "insert_alert", fail)
        with pytest.raises(RuntimeError):
            asyncio.run(jobs(f).batch(claim))
    row = query(f, "SELECT * FROM scheduled_jobs WHERE household_id=:hid")[0]
    assert row["checkpoint"] == row["result"] == {"schema_version": 1}
    assert row["state"] == "RUNNING" and row["completed_at"] is None and not effects(f)
    asyncio.run(finish(f, claim))
    assert len(effects(f)) == 1


def test_crash_after_commit_before_ack_replays_completed_run(f, monkeypatch):
    configure_timezone(f)
    receipt(f, product(f), expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    job = enqueue(f, key="lost-ack")
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    completed = asyncio.run(finish(f, claim))
    before = effects(f)
    assert asyncio.run(jobs(f).batch(claim)) == completed
    assert enqueue(f, key="lost-ack") == job
    assert effects(f) == before


def test_expiry_batches_resume_without_missing_or_duplicating_lots(f, monkeypatch):
    configure_timezone(f)
    p = product(f)
    lots = [receipt(f, p, expires_on="2026-11-12").json() for _ in range(103)]
    freeze_clock(monkeypatch)
    job = enqueue(f)
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    first = asyncio.run(jobs(f).batch(claim))
    assert first["state"] == "RUNNING" and first["scanned_count"] == 100
    checkpoint = query(f, "SELECT checkpoint FROM scheduled_jobs WHERE household_id=:hid")[0]["checkpoint"]
    assert checkpoint == {"schema_version": 1, "high_water_id": lots[-1]["id"], "last_lot_id": lots[99]["id"]}
    late = receipt(f, p, expires_on="2026-11-12").json()
    expire(f, job["id"])
    reclaimed = asyncio.run(jobs(f).claim(job_id=job["id"]))
    # A later batch fault retains exactly the earlier committed batch.
    from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
    original = SqlAlchemyExpiryJobRepository.insert_alert
    async def fail_later(self, values):
        await original(self, values)
        raise RuntimeError("Later batch fails after a real INSERT")
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyExpiryJobRepository, "insert_alert", fail_later)
        with pytest.raises(RuntimeError):
            asyncio.run(jobs(f).batch(reclaimed))
    assert len(effects(f)) == 100
    assert query(f, "SELECT checkpoint FROM scheduled_jobs WHERE household_id=:hid")[0]["checkpoint"] == checkpoint
    result = asyncio.run(finish(f, reclaimed))
    assert result["scanned_count"] == result["warning_count"] == 103
    assert {a["lot_id"] for a in effects(f)} == {a["id"] for a in lots}
    assert late["id"] not in {a["lot_id"] for a in effects(f)}


def test_expiry_retry_exhaustion_is_visible_and_preserves_stock(f, monkeypatch):
    configure_timezone(f)
    receipt(f, product(f), expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    job = enqueue(f)
    before = snapshot(f)
    schedule = query(f, "SELECT run_after FROM scheduled_jobs WHERE household_id=:hid")[0]
    for attempt, delay in [(1, 60), (2, 300), (3, None)]:
        claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
        assert claim.attempt_count == attempt
        result = asyncio.run(jobs(f).fail(claim, "INVENTORY_RETRY_EXHAUSTED"))
        row = query(f, "SELECT *,extract(epoch FROM lease_until-clock_timestamp()) AS delay FROM scheduled_jobs WHERE household_id=:hid")[0]
        assert row["run_after"] == schedule["run_after"]
        assert asyncio.run(jobs(f).claim(job_id=job["id"])) is None
        if delay:
            assert delay - 5 < row["delay"] <= delay
            assert row["lease_token"] != claim.token
            from app.lifecycle.jobs import LeaseLost
            with pytest.raises(LeaseLost):
                asyncio.run(jobs(f).batch(claim))
            expire(f, job["id"])
        else:
            assert result["state"] == "FAILED" and row["completed_at"]
            assert row["lease_until"] is row["lease_token"] is None
    status = f.request("GET", f"/inventory/expiry-runs/{job['id']}").json()
    assert status["state"] == "FAILED" and status["error_code"] == "INVENTORY_RETRY_EXHAUSTED"
    assert snapshot(f) == before and not effects(f)


def test_queued_run_crossing_local_midnight_has_explicit_stale_outcome(f, monkeypatch):
    configure_timezone(f)
    receipt(f, product(f), expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    job = enqueue(f)
    freeze_clock(monkeypatch, "2026-11-11T17:00:00+00:00")
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    result = asyncio.run(finish(f, claim))
    assert result["state"] == "SUCCEEDED" and result["outcome_code"] == "SKIPPED_STALE"
    assert result["attempt_count"] == 1 and not effects(f)
    rows = query(f, "SELECT * FROM scheduled_jobs WHERE household_id=:hid ORDER BY id")
    assert len(rows) == 2 and rows[1]["state"] == "READY"
    assert rows[1]["payload"]["local_date"] == "2026-11-12"


def test_timezone_change_and_late_expiry_edit_follow_approved_rescan_policy(f, monkeypatch):
    configure_timezone(f)
    lot = receipt(f, product(f), expires_on="2026-11-12").json()
    freeze_clock(monkeypatch, "2026-11-11T12:00:00+00:00")
    job = enqueue(f)
    # Authorized settings command changes timezone but retains the same local day.
    response = f.client.patch(f"/api/v1/households/{f.hid}", headers=f.actors["OWNER"].headers,
                              json={"settings": {"timezone": "UTC"}})
    assert response.status_code == 200, response.text
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    assert asyncio.run(finish(f, claim))["outcome_code"] == "SKIPPED_STALE"
    assert enqueue(f)["id"] == job["id"] and not effects(f)
    freeze_clock(monkeypatch, "2026-11-12T12:00:00+00:00")
    second = enqueue(f)
    asyncio.run(finish(f, asyncio.run(jobs(f).claim(job_id=second["id"]))))
    prior = effects(f)
    assert f.request("PATCH", f"/inventory-lots/{lot['id']}", json={"expires_on": "2026-11-01", "reason": "Late correction"}).status_code == 200
    assert enqueue(f)["id"] == second["id"]
    assert asyncio.run(jobs(f).claim(job_id=second["id"])) is None
    assert effects(f) == prior and str(prior[0]["expires_on_snapshot"]) == "2026-11-12"


def test_one_invalid_household_does_not_abort_other_expiry_jobs(f, monkeypatch):
    configure_timezone(f, "No/Zone")
    async def setup():
        async with f.db() as db, db.begin():
            await db.execute(text("UPDATE household_settings SET values='{" + '"timezone":"UTC"' + "}'::jsonb WHERE household_id=:hid"), {"hid": f.other_hid})
    asyncio.run(setup())
    freeze_clock(monkeypatch)
    result = asyncio.run(jobs(f).dispatch(after_id=f.hid - 1, limit=2))
    assert result["diagnostics"] == [{"household_id": f.hid, "error_code": "INVENTORY_TIMEZONE_REQUIRED"}]
    assert len(result["job_ids"]) == 1 and result["last_household_id"] == f.other_hid
    assert not query(f, "SELECT id FROM scheduled_jobs WHERE household_id=:hid")


@pytest.mark.parametrize("zone", [None, "", 42, "No/Zone", "../UTC"])
def test_expiry_enqueue_requires_valid_timezone_without_defaults(f, zone):
    configure_timezone(f, zone)
    before = snapshot(f)
    response = f.request("POST", "/inventory/expiry-runs", json={})
    assert response.status_code == 422 and response.json()["error_code"] == "INVENTORY_TIMEZONE_REQUIRED"
    assert not query(f, "SELECT id FROM scheduled_jobs WHERE household_id=:hid")
    assert not query(f, "SELECT id FROM idempotency_requests WHERE household_id=:hid AND operation LIKE '%expiry-runs%'")
    assert snapshot(f) == before


def test_expiry_enqueue_contract_is_registered():
    from app.main import create_app
    schema = create_app().openapi()
    path = "/api/v1/households/{household_id}/inventory/expiry-runs"
    assert path in schema["paths"], "Step 3 enqueue route must exist"
    assert schema["paths"][path]["post"]["responses"]["202"]


def test_expiry_internal_enqueue_storage(f, monkeypatch):
    from app.lifecycle.jobs import evaluation, summary
    from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
    configure_timezone(f)
    freeze_clock(monkeypatch)
    async def run():
        async with f.db() as db, db.begin():
            repository = SqlAlchemyExpiryJobRepository(db)
            day, zone = await evaluation(repository, f.hid)
            row = await repository.enqueue(f.hid, day, zone)
            assert row["state"] == "READY"
            assert summary(row)["attempt_count"] == 0
    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["empty", "archived", "invalid_timezone", "third_crash"])
def test_expiry_completion_paths_obey_frozen_guard_and_lease_constraints(f, monkeypatch, outcome):
    configure_timezone(f)
    if outcome != "empty":
        receipt(f, product(f), expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    job = enqueue(f)
    if outcome == "archived":
        async def archive():
            async with f.db() as db, db.begin():
                await db.execute(text("UPDATE households SET archived_at=clock_timestamp() WHERE id=:hid"), {"hid": f.hid})
        asyncio.run(archive())
    if outcome == "invalid_timezone":
        configure_timezone(f, None)
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    assert claim.attempt_count == 1
    if outcome == "third_crash":
        for attempt in [2, 3]:
            expire(f, job["id"])
            claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
            assert claim.attempt_count == attempt
        expire(f, job["id"])
        assert asyncio.run(jobs(f).claim(job_id=job["id"])) is None
        result = f.request("GET", f"/inventory/expiry-runs/{job['id']}").json()
        assert result["state"] == "FAILED" and result["error_code"] == "INVENTORY_RETRY_EXHAUSTED"
    elif outcome == "invalid_timezone":
        result = asyncio.run(jobs(f).work(claim))
        assert result["error_code"] == "INVENTORY_TIMEZONE_REQUIRED" and result["state"] == "RUNNING"
        assert not effects(f)
        row = query(f, "SELECT checkpoint,result FROM scheduled_jobs WHERE household_id=:hid")[0]
        assert row["checkpoint"] == row["result"] == {"schema_version": 1}
        return
    else:
        result = asyncio.run(jobs(f).work(claim))
        assert result["state"] == "SUCCEEDED"
        assert result["outcome_code"] == ("SKIPPED_ARCHIVED" if outcome == "archived" else "COMPLETED")
    row = query(f, "SELECT * FROM scheduled_jobs WHERE household_id=:hid")[0]
    assert row["completed_at"] and row["lease_until"] is row["lease_token"] is None
    assert not effects(f)


@pytest.mark.parametrize("zone,instant,day", [
    ("Asia/Ho_Chi_Minh", "2026-11-10T16:59:59+00:00", "2026-11-10"),
    ("Asia/Ho_Chi_Minh", "2026-11-10T17:00:00+00:00", "2026-11-11"),
    ("America/New_York", "2026-11-01T05:59:59+00:00", "2026-11-01"),
    ("America/New_York", "2026-11-01T06:00:00+00:00", "2026-11-01"),
    ("America/New_York", "2026-03-08T06:59:59+00:00", "2026-03-08"),
    ("America/New_York", "2026-03-08T07:00:00+00:00", "2026-03-08"),
])
def test_expiry_job_resolves_one_local_date_for_batch_across_midnight_and_dst(f, monkeypatch, zone, instant, day):
    configure_timezone(f, zone)
    p = product(f)
    for _ in range(2):
        receipt(f, p, expires_on=day)
    calls = freeze_clock(monkeypatch, instant)
    job = enqueue(f)
    assert len(calls) == 1
    claim = asyncio.run(jobs(f).claim(job_id=job["id"]))
    asyncio.run(finish(f, claim))
    assert len(calls) == 2  # Once for enqueue, once for the whole batch, never per lot.
    assert {str(a["local_date"]) for a in effects(f)} == {day}
    assert len(effects(f)) == 2
    row = query(f, "SELECT job_key FROM scheduled_jobs WHERE household_id=:hid")[0]
    assert row["job_key"] == f"inventory-expiry:v1:{day}"
    assert {a["alert_kind"] for a in effects(f)} == {"WARNING"}
    assert {str(a["expires_on_snapshot"]) for a in effects(f)} == {day}


def test_dedicated_expiry_worker_fails_closed_without_household_lock_capability(f, finance_database_urls, monkeypatch):
    import os
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.lifecycle.jobs import ExpiryJobs
    raw = os.environ["INVENTORY_EXPIRY_WORKER_DATABASE_URL"]
    worker, runtime = make_url(raw), make_url(finance_database_urls[1])
    assert worker.database.startswith("p03_finance_test_")
    assert (worker.host, worker.port, worker.database) == (runtime.host, runtime.port, runtime.database)
    assert worker.username == os.environ["INVENTORY_EXPIRY_WORKER_ROLE"] and worker.username != runtime.username
    configure_timezone(f)
    receipt(f, product(f), expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    job = enqueue(f)
    async def run():
        engine = create_async_engine(raw, poolclass=NullPool)
        try:
            dedicated = ExpiryJobs(async_sessionmaker(engine, expire_on_commit=False))
            claim = await dedicated.claim(job_id=job["id"])
            assert claim is not None  # Job-only coordination has sufficient grants.
            with pytest.raises(DBAPIError) as error:
                await dedicated.batch(claim)
            assert error.value.orig.sqlstate == "42501"
            # Existing runtime can prove application behavior; production worker
            # lock provisioning stays OPEN-10, without broadening any grant.
            await finish(f, claim)
        finally:
            await engine.dispose()
    asyncio.run(run())
    assert len(effects(f)) == 1


def test_expiry_producer_applies_eligibility_without_mutating_history(f, monkeypatch):
    configure_timezone(f)
    p = product(f)
    eligible = receipt(f, p, expires_on="2026-11-12").json()
    receipt(f, p, expires_on=None)
    receipt(f, p, expires_on="2027-01-01")
    terminal = receipt(f, p, expires_on="2026-11-01").json()
    assert f.request("POST", "/disposals", json={"allocations": [{"lot_id": terminal["id"], "quantity": "5", "unit_id": p["base_unit_id"]}], "reason_code": "EXPIRED"}).status_code == 201
    archived = receipt(f, p, expires_on="2026-11-01").json()
    assert f.request("POST", f"/inventory-lots/{archived['id']}/archive", json={"reason": "Retain"}).status_code == 200
    other = product(f, name="Archived product")
    receipt(f, other, expires_on="2026-11-01")
    assert f.request("POST", f"/products/{other['id']}/archive", json={}).status_code == 200
    freeze_clock(monkeypatch)
    job = enqueue(f)
    before = snapshot(f)
    result = asyncio.run(finish(f, asyncio.run(jobs(f).claim(job_id=job["id"]))))
    assert result["scanned_count"] == 6 and result["warning_count"] == 1 and result["expired_count"] == 0
    assert [a["lot_id"] for a in effects(f)] == [eligible["id"]]
    assert snapshot(f) == before
