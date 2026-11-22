"""Daily expiry / maintenance scan (design §6.1).

``python -m app.jobs.daily`` — run once a day at 08:00 Asia/Shanghai
from cron. Creates ``notifications`` rows only; it never sends WeChat
messages itself (see ``app.jobs.send_wechat``, design §8).

For each household, "today" is computed in the household's own
timezone (``households.timezone``, fallback ``Asia/Shanghai`` when
missing/invalid):

1. ``inventory_items`` with ``status != 'consumed'`` and
   ``auto_expiry_date = today`` get one ``lazy_tracking`` notification
   for the household owner (design §6.2).
2. ``equipments`` with ``status='active'`` and
   ``next_maintenance_date = today`` get one ``maintenance_reminder``
   notification for the household owner.

Idempotency is enforced by the database, not by remembering runs:
the partial unique indexes ``ux_notifications_open_lazy`` /
``ux_notifications_open_maint`` (design §3.4, migration 0003) allow at
most one open notification per referenced item, and every INSERT uses
``ON CONFLICT ... DO NOTHING`` so a re-run creates zero duplicates.
The scan matches ``auto_expiry_date = today`` exactly — items already
past expiry with no notification are NOT re-notified, which is what
makes "no re-send if unanswered after 2 days" (design §3.4) hold.

Phase C (contract §4): every run writes one ``job_runs`` row
(running at start, success/failed at finish, with duration and the
notifications count), so the admin dashboard can show the cron
history. Recording is best-effort: if the table is missing the scan
still runs and only logs a warning.

NOTE on the ON CONFLICT form: migration 0003 creates those indexes
with ``CREATE UNIQUE INDEX`` (not a UNIQUE CONSTRAINT), so
``ON CONFLICT ON CONSTRAINT ux_notifications_open_lazy`` is invalid
Postgres ("constraint ... does not exist" — verified 2026-11-20 on a
temp table). The column + predicate form used below is the correct
one for a partial unique index, and it was verified to skip the
second insert (rowcount 0) and to allow a fresh insert once the old
row is ``responded`` (the slot frees, design §5.2).

NOTE on inventory status: design §6.1 says ``status='active'`` but
the real Phase 1 check constraint is
``status IN ('fresh', 'expiring', 'expired', 'consumed')``
(migration 0001), so the scan uses ``status != 'consumed'`` instead.

A failure in one household/item never fails the whole run: errors
are caught per household and per item, logged, and the scan
continues. Exit code is 0 even when nothing was created.
"""

import json
import logging
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text

from app.db import get_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("imsf-jobs-daily")

DEFAULT_TZ = "Asia/Shanghai"

# Partial-unique-index predicates from migration 0003 (§3.4). These
# must match the index definitions exactly for ON CONFLICT inference.
LAZY_CONFLICT = (
    "(ref_type, ref_id) WHERE type = 'lazy_tracking'"
    " AND status IN ('sent', 'delivered', 'read')"
)
MAINT_CONFLICT = (
    "(ref_type, ref_id) WHERE type = 'maintenance_reminder'"
    " AND status IN ('sent', 'delivered', 'read')"
)


def _household_today(timezone: str | None):
    """(tz_name, today) for a household; falls back to Asia/Shanghai."""
    name = (timezone or "").strip() or DEFAULT_TZ
    try:
        tz = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("invalid household timezone %r, using %s",
                    timezone, DEFAULT_TZ)
        name = DEFAULT_TZ
        tz = ZoneInfo(DEFAULT_TZ)
    return name, datetime.now(tz).date()


def _find_owner(conn, household_id):
    """user_id of the household owner, or None (design §6.2)."""
    return conn.execute(
        text("SELECT user_id FROM household_members"
             " WHERE household_id = :hid AND role = 'owner' LIMIT 1"),
        {"hid": household_id},
    ).scalar_one_or_none()


def _insert_notification(conn, user_id, household_id, ntype, ref_type,
                         ref_id, payload, conflict):
    """INSERT ... ON CONFLICT DO NOTHING. Returns 1 created, 0 skipped."""
    result = conn.execute(
        text(
            "INSERT INTO notifications (user_id, household_id, type,"
            " ref_type, ref_id, channel, payload_json, status)"
            " VALUES (:uid, :hid, :type, :ref_type, :ref_id, 'in_app',"
            " CAST(:payload AS jsonb), 'sent')"
            f" ON CONFLICT {conflict} DO NOTHING"
        ),
        {"uid": user_id, "hid": household_id, "type": ntype,
         "ref_type": ref_type, "ref_id": ref_id,
         "payload": json.dumps(payload, ensure_ascii=False)},
    )
    return result.rowcount


def scan_lazy_tracking(engine, household_id, owner_id, today):
    """Create lazy_tracking notifications for items expiring today.

    Returns (created, skipped).
    """
    with engine.connect() as conn:
        items = conn.execute(
            text("SELECT id, raw_name, auto_expiry_date FROM inventory_items"
                 " WHERE household_id = :hid AND status != 'consumed'"
                 " AND auto_expiry_date = :today"),
            {"hid": household_id, "today": today},
        ).all()
    created = skipped = 0
    for item_id, raw_name, expiry_date in items:
        payload = {"item_name": raw_name,
                   "expiry_date": str(expiry_date),
                   "actions": ["used_up", "extended"]}
        try:
            with engine.begin() as conn:
                n = _insert_notification(
                    conn, owner_id, household_id, "lazy_tracking",
                    "inventory_item", item_id, payload, LAZY_CONFLICT)
            if n:
                created += 1
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001 — per-item, keep going
            log.error("lazy_tracking item=%s household=%s failed: %s",
                      item_id, household_id, exc)
    return created, skipped


def scan_maintenance(engine, household_id, owner_id, today):
    """Create maintenance_reminder notifications due today.

    Returns (created, skipped).
    """
    with engine.connect() as conn:
        equipments = conn.execute(
            text("SELECT id, device_type, brand_model,"
                 " next_maintenance_date FROM equipments"
                 " WHERE household_id = :hid AND status = 'active'"
                 " AND next_maintenance_date = :today"),
            {"hid": household_id, "today": today},
        ).all()
    created = skipped = 0
    for eq_id, device_type, brand_model, next_date in equipments:
        payload = {"equipment_name": brand_model or device_type,
                   "next_maintenance_date": str(next_date)}
        try:
            with engine.begin() as conn:
                n = _insert_notification(
                    conn, owner_id, household_id, "maintenance_reminder",
                    "equipment", eq_id, payload, MAINT_CONFLICT)
            if n:
                created += 1
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001 — per-item, keep going
            log.error("maintenance_reminder equipment=%s household=%s"
                      " failed: %s", eq_id, household_id, exc)
    return created, skipped


def _record_job_start(engine):
    """Insert a ``job_runs`` row (status=running); return its id or None.

    Phase C (contract §4). Returns None — and only logs — when the
    table does not exist yet (migration not applied) so the scan
    itself never fails because recording is unavailable.
    """
    try:
        with engine.begin() as conn:
            return conn.execute(
                text("INSERT INTO job_runs (job_name, started_at, status)"
                     " VALUES ('daily', now(), 'running') RETURNING id"),
            ).scalar_one()
    except Exception as exc:  # noqa: BLE001 — recording is best-effort
        log.warning("job_runs start record failed (continuing scan): %s",
                    exc)
        return None


def _record_job_finish(engine, run_id, started_ms, counts, error=None):
    """Update the ``job_runs`` row to success/failed (best-effort)."""
    if run_id is None:
        return
    duration_ms = int(time.monotonic() * 1000 - started_ms)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE job_runs SET finished_at = now(),"
                     " status = :status,"
                     " notifications_created = :n, error = :err,"
                     " duration_ms = :dur WHERE id = :id"),
                {"status": "failed" if error else "success",
                 "n": counts["lazy_created"] + counts["maint_created"],
                 "err": str(error)[:1000] if error else None,
                 "dur": duration_ms, "id": run_id},
            )
    except Exception as exc:  # noqa: BLE001 — recording is best-effort
        log.warning("job_runs finish record failed: %s", exc)


def run_daily() -> dict:
    """Run the scan for every household. Returns the count dict."""
    engine = get_engine()
    started_ms = int(time.monotonic() * 1000)
    run_id = _record_job_start(engine)
    counts = {"lazy_created": 0, "lazy_skipped": 0,
              "maint_created": 0, "maint_skipped": 0}
    error = None
    try:
        with engine.connect() as conn:
            households = conn.execute(
                text("SELECT id, timezone FROM households")
            ).all()
        for household_id, timezone in households:
            try:
                tz_name, today = _household_today(timezone)
                with engine.connect() as conn:
                    owner_id = _find_owner(conn, household_id)
                if owner_id is None:
                    log.warning("household=%s has no owner, skipping"
                                " notifications for today=%s",
                                household_id, today)
                    continue
                log.info("household=%s tz=%s today=%s owner=%s",
                         household_id, tz_name, today, owner_id)
                lc, ls = scan_lazy_tracking(engine, household_id, owner_id,
                                            today)
                mc, ms = scan_maintenance(engine, household_id, owner_id,
                                          today)
                counts["lazy_created"] += lc
                counts["lazy_skipped"] += ls
                counts["maint_created"] += mc
                counts["maint_skipped"] += ms
            except Exception as exc:  # noqa: BLE001 — per-household, keep going
                log.error("household=%s scan failed: %s", household_id, exc)
    except Exception as exc:  # top-level failure: record + re-raise
        error = exc
        raise
    finally:
        _record_job_finish(engine, run_id, started_ms, counts, error)
    return counts


def main() -> int:
    counts = run_daily()
    # One summary line for the cron log (design §6.1 step 3).
    print(f"daily scan done: lazy_tracking created="
          f"{counts['lazy_created']} skipped={counts['lazy_skipped']},"
          f" maintenance_reminder created={counts['maint_created']}"
          f" skipped={counts['maint_skipped']}")
    log.info("daily scan done: %s", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
