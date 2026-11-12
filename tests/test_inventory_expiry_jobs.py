"""Step 2 persistence only. Claim, fencing and execution belong to Step 3."""
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
