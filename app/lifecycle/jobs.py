"""Expiry orchestration; OPEN-03/04/05/06/08/10 PROPOSALS for merge review.

PROPOSAL: claim-first skips (READY -> RUNNING -> SUCCEEDED with skip code).
Frozen revision 8's guard allows READY -> READY/RUNNING only, and terminal
jobs are immutable. Stale/archived work MUST be claimed before completion.
Direct READY -> terminal would require a NEW migration; never edit revision 8.

Frozen-DDL resolutions (PROPOSALS):
(a) run_after is immutable. Handled failures stay RUNNING, rotate the token to
invalidate the owner, and set lease_until to DB time + 60/300 seconds as the
reclaim not-before marker. Third failure is terminal. No READY lease is invented.
(b) Payload requires exactly schema_version/local_date/valid IANA timezone.
Invalid configuration at dispatch is a sanitized per-household diagnostic, not a
fabricated job/timezone. An existing valid-payload job can record that failure.
(c) There is NO inventory_expiry_lock_household() helper. Reuse inventory's
household FOR UPDATE prefix before job locks. Revision-8 SELECT-only dedicated
worker cannot acquire it: production least-privilege provisioning remains OPEN-10.
No new function, stock grant, credential, actor impersonation or scheduler here.
(d) All terminal writes atomically set completed_at and NULL both lease columns.
(e) Only frozen v1 checkpoint/result keys are written; uppercase outcome codes.

PROPOSAL defaults: current-day daily identity; dispatch 15-minute cadence (not
installed), 100 households/page and 100 lots/batch, 60-second lease, three claims.
Batches observe committed inventory separately, not a lifetime snapshot. Alerts
and checkpoint roll back together; earlier committed batches remain on failure.
High-water excludes later receipts. Completed daily work never reruns; late edits
wait for the next local day. Timezone-only drift on the same date skips without
creating an infinite same-key replacement. No backfill or stock/finance writer.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from app.inventory.domain import InventoryRequestError
from app.lifecycle import service as lifecycle_clock
from app.lifecycle.domain import household_zone, freshness, eligible_for_alert
from app.lifecycle.dto import ExpiryRunResponse
from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository


class LeaseLost(Exception):
    """The entire current effect transaction must roll back."""


@dataclass(frozen=True)
class Claim:
    household_id: int
    job_id: int
    token: str
    attempt_count: int


def transient(exc):
    """Same classification as inventory's three-transaction-attempt commands."""
    state = getattr(exc.orig, "sqlstate", None)
    return (state in {"40001", "40P01", "57P01"}
            or bool(state and state.startswith("08")) or exc.connection_invalidated)


async def evaluation(repository, hid):
    name = await repository.timezone(hid)
    zone = household_zone(name)
    if not await repository.valid_timezone(name):
        raise InventoryRequestError(422, "INVENTORY_TIMEZONE_REQUIRED")
    return lifecycle_clock.utc_now().astimezone(zone).date(), name


def summary(row):
    result = row["result"]
    return ExpiryRunResponse.model_validate({
        key: row[key] for key in ("id", "kind", "state", "attempt_count", "run_after", "completed_at", "error_code")
    } | {"local_date": row["payload"]["local_date"], "timezone": row["payload"]["timezone"],
         "scanned_count": result.get("scanned_count", 0), "warning_count": result.get("warning_count", 0),
         "expired_count": result.get("expired_count", 0), "outcome_code": result.get("outcome_code")}
    ).model_dump(mode="json")


class ExpiryJobs:
    """System context with caller-supplied session factory; no actor or stock API.

    batch() exposes transaction failure to its caller. work() runs at most one
    claimed attempt across batches, recording sanitized handled failures. Hosts
    call dispatch()/claim()/work() explicitly; no scheduler is started on import.
    """
    def __init__(self, sessions):
        self.sessions = sessions

    async def dispatch(self, *, after_id=0, limit=100):
        if not 1 <= limit <= 100 or after_id < 0:
            raise ValueError("Dispatch page must be bounded")
        async with self.sessions() as session, session.begin():
            ids = await SqlAlchemyExpiryJobRepository(session).active_households(after_id, limit)
        result = {"job_ids": [], "diagnostics": [], "last_household_id": ids[-1] if ids else after_id}
        for hid in ids:
            try:
                # One transaction per household: invalid configuration cannot
                # abort other households or manufacture an invalid-payload row.
                async with self.sessions() as session, session.begin():
                    repository = SqlAlchemyExpiryJobRepository(session)
                    household = await repository.lock_household(hid)
                    if household is None or household["archived_at"] is not None:
                        continue
                    day, zone = await evaluation(repository, hid)
                    row = await repository.enqueue(hid, day, zone)
                    result["job_ids"].append(row["id"])
            except InventoryRequestError as exc:
                result["diagnostics"].append({"household_id": hid, "error_code": exc.code})
        return result

    async def claim(self, *, job_id=None):
        # Short, jobs-only SKIP LOCKED transaction. No household/source effects.
        async with self.sessions() as session, session.begin():
            repository = SqlAlchemyExpiryJobRepository(session)
            row = await repository.claim_due(job_id)
            if row is None:
                return None
            if row["attempt_count"] >= 3:
                await repository.abandon_exhausted(row)
                return None
            token = uuid4().hex
            row = await repository.update_claim(row, token)
            return Claim(row["household_id"], row["id"], token, row["attempt_count"])

    async def _locked(self, repository, claim):
        household = await repository.lock_household(claim.household_id)
        row = await repository.job(claim.household_id, claim.job_id, lock=True)
        if row is None:
            raise LeaseLost()
        # A lost acknowledgement can replay a persisted terminal summary, but
        # never changes a terminal row or grants an old owner new effects.
        if row["state"] in {"SUCCEEDED", "FAILED"}:
            return household, row
        if (row["state"] != "RUNNING" or row["lease_token"] != claim.token
                or row["lease_until"] <= await repository.now()):
            raise LeaseLost()
        return household, row

    async def _save(self, repository, claim, **values):
        row = await repository.fenced_update(claim.household_id, claim.job_id, claim.token, **values)
        if row is None:
            raise LeaseLost()
        return summary(row)

    async def _complete(self, repository, claim, row, outcome):
        return await self._save(repository, claim, state="SUCCEEDED",
            completed_at=sa.func.clock_timestamp(), lease_until=None, lease_token=None,
            error_code=None, result=row["result"] | {"outcome_code": outcome})

    async def batch(self, claim):
        for attempt in range(3):
            try:
                async with self.sessions() as session, session.begin():
                    repository = SqlAlchemyExpiryJobRepository(session)
                    household, row = await self._locked(repository, claim)
                    if row["state"] in {"SUCCEEDED", "FAILED"}:
                        return summary(row)
                    if household is None or household["archived_at"] is not None:
                        return await self._complete(repository, claim, row, "SKIPPED_ARCHIVED")
                    day, zone = await evaluation(repository, claim.household_id)
                    if row["payload"]["local_date"] != day.isoformat() or row["payload"]["timezone"] != zone:
                        if row["payload"]["local_date"] != day.isoformat():
                            await repository.enqueue(claim.household_id, day, zone)
                        return await self._complete(repository, claim, row, "SKIPPED_STALE")
                    checkpoint = dict(row["checkpoint"])
                    if "high_water_id" not in checkpoint:
                        checkpoint["high_water_id"] = await repository.high_water(claim.household_id)
                    lots = await repository.source_page(claim.household_id,
                        checkpoint.get("last_lot_id", 0), checkpoint["high_water_id"], 100)
                    result = {"schema_version": 1, "scanned_count": row["result"].get("scanned_count", 0),
                        "warning_count": row["result"].get("warning_count", 0), "expired_count": row["result"].get("expired_count", 0)}
                    for lot in lots:
                        result["scanned_count"] += 1
                        if not eligible_for_alert(lot, product_archived_at=lot["product_archived_at"], household_archived_at=None):
                            continue
                        kind, _ = freshness(lot["expires_on"], day)
                        if kind in {"WARNING", "EXPIRED"}:
                            inserted = await repository.insert_alert({"household_id": claim.household_id,
                                "lot_id": lot["id"], "job_id": claim.job_id, "alert_kind": kind,
                                "local_date": day, "timezone": zone, "expires_on_snapshot": lot["expires_on"]})
                            result["warning_count" if kind == "WARNING" else "expired_count"] += inserted
                    if lots:
                        checkpoint["last_lot_id"] = lots[-1]["id"]
                    values = {"checkpoint": checkpoint, "result": result, "error_code": None}
                    if len(lots) < 100 or checkpoint.get("last_lot_id", 0) >= checkpoint["high_water_id"]:
                        values.update(state="SUCCEEDED", completed_at=sa.func.clock_timestamp(),
                            lease_until=None, lease_token=None, result=result | {"outcome_code": "COMPLETED"})
                    else:
                        values["lease_until"] = sa.func.clock_timestamp() + timedelta(seconds=60)
                    # DB clock checked again after actual inserts, under the job
                    # lock. Zero rows raises and rolls back alerts + progress.
                    return await self._save(repository, claim, **values)
            except DBAPIError as exc:
                if transient(exc) and attempt < 2:
                    continue
                raise

    async def fail(self, claim, code):
        # Only internal allow-listed diagnostics: never save raw exceptions.
        if code not in {"INVENTORY_TIMEZONE_REQUIRED", "INVENTORY_RETRY_EXHAUSTED", "INVENTORY_EXPIRY_FAILED"}:
            raise ValueError("Unsupported expiry failure code")
        async with self.sessions() as session, session.begin():
            repository = SqlAlchemyExpiryJobRepository(session)
            _, row = await self._locked(repository, claim)
            if row["state"] in {"SUCCEEDED", "FAILED"}:
                return summary(row)
            values = {"error_code": code}
            if row["attempt_count"] >= 3:
                values.update(state="FAILED", completed_at=sa.func.clock_timestamp(), lease_token=None, lease_until=None)
            else:
                # Rotate away the owner's token: its future batch cannot use
                # this still-unexpired lease as permission during retry delay.
                delay = 60 if row["attempt_count"] == 1 else 300
                values.update(lease_token=uuid4().hex,
                    lease_until=sa.func.clock_timestamp() + timedelta(seconds=delay))
            return await self._save(repository, claim, **values)

    async def work(self, claim):
        try:
            while True:
                result = await self.batch(claim)
                if result["state"] != "RUNNING":
                    return result
        except LeaseLost:
            raise
        except InventoryRequestError:
            return await self.fail(claim, "INVENTORY_TIMEZONE_REQUIRED")
        except DBAPIError as exc:
            return await self.fail(claim, "INVENTORY_RETRY_EXHAUSTED" if transient(exc) else "INVENTORY_EXPIRY_FAILED")
        except Exception:
            return await self.fail(claim, "INVENTORY_EXPIRY_FAILED")
