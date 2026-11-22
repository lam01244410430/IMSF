"""Admin dashboard endpoints (Phase C, contract §2).

All 13 endpoints live under ``/api/v2/admin`` and share the
``require_admin`` dependency (contract §1.3): a valid JWT for an
enabled user whose id is in the ``IMSF_ADMIN_USER_IDS`` allowlist.
Every admin response sets ``Cache-Control: no-store``. Every admin
mutation and every sensitive read (household-records inspection)
writes one ``admin_audit_events`` row in the same transaction as the
mutation; denied attempts go to the structured server log only.

What this router deliberately does NOT do (v1 scope, plan §4.7):
no user/household deletion, no password reset on the UI, no account
linking/merging/impersonation, no bulk finance export, no role
management, no secret editing, no queue retry / cron rerun buttons.
"""

import json
import logging
import os
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import text

from app.auth import Identity, get_admin_user_ids, require_admin
from app.db import QUEUE_KEY, get_engine, get_redis
from app.rag import EMBEDDING_MODEL

log = logging.getLogger("imsf-admin")

router = APIRouter(prefix="/api/v2/admin", tags=["admin"])

CAPABILITIES = ["users:read", "users:write", "recipes:write",
                "audit:read", "system:read"]

RECIPE_STATUSES = ("draft", "published", "hidden")
RECORD_TYPES = ("receipts", "transactions", "inventory", "equipment")
RECIPE_EDITABLE = ("title", "description", "source_url", "category",
                   "language", "difficulty", "taste", "slug", "author",
                   "cover_image", "steps_json", "cook_time", "status")
RECIPE_CREATEABLE = ("description", "source_url", "category", "language",
                     "difficulty", "taste", "slug", "author", "cover_image",
                     "steps_json", "cook_time", "ingredients")

SHANGHAI = ZoneInfo("Asia/Shanghai")
VERCEL_WEB_URL = "https://imsf-web.vercel.app"
VERCEL_API_URL = "https://imsf-api.vercel.app"


def _commit() -> str:
    """Short git commit of the running checkout, or 'unknown'."""
    try:
        repo = Path(__file__).resolve().parent.parent.parent
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo,
            capture_output=True, text=True, timeout=5, check=False)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception as exc:  # noqa: BLE001 — commit is best-effort metadata
        log.debug("git commit lookup failed: %s", exc)
    return "unknown"


_COMMIT = _commit()


def _no_store(response: Response) -> None:
    """Router dependency: every admin response is never cached."""
    response.headers["Cache-Control"] = "no-store"


# require_admin + no-store apply to the whole router (contract §1.3).
router.dependencies = [Depends(require_admin), Depends(_no_store)]


def _page(limit: int, offset: int) -> tuple[int, int]:
    """Validate pagination the repo way (hand check -> 400, not 422)."""
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400,
                            detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=400,
                            detail="offset must be >= 0")
    return limit, offset


def _env() -> str | None:
    return (os.environ.get("IMSF_ENVIRONMENT")
            or os.environ.get("ENVIRONMENT") or None)


def _request_id(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("x-request-id")


def _audit(conn, actor: uuid.UUID, action: str, target_type: str,
           target_id: str, reason: str | None = None,
           outcome: str = "success", details: dict | None = None,
           request: Request | None = None) -> None:
    """Insert one audit row on the caller's (open) transaction."""
    conn.execute(
        text("INSERT INTO admin_audit_events (actor_user_id, action,"
             " target_type, target_id, reason, outcome, details,"
             " request_id, environment)"
             " VALUES (:actor, :action, :ttype, :tid, :reason,"
             " :outcome, CAST(:details AS jsonb), :rid, :env)"),
        {"actor": actor, "action": action, "ttype": target_type,
         "tid": target_id, "reason": reason, "outcome": outcome,
         "details": json.dumps(details) if details is not None else None,
         "rid": _request_id(request), "env": _env()},
    )


def _user_status(disabled_at) -> str:
    return "disabled" if disabled_at is not None else "enabled"


def _login_method(email, wechat_openid) -> str:
    return "email" if email else "wechat"


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


# --- cron helpers (shared by /health and /jobs) ----------------------------


def _next_run_8am(now_shanghai: datetime) -> datetime:
    """Next 08:00 Asia/Shanghai run (00:00 UTC)."""
    today_8 = now_shanghai.replace(hour=8, minute=0, second=0,
                                   microsecond=0)
    if now_shanghai < today_8:
        return today_8
    return today_8 + timedelta(days=1)


def _cron_summary(conn) -> dict:
    """Last daily-cron run / success / next run / status from job_runs.

    Honest when empty: last_run / last_success are null and status is
    "unknown" — never fabricated. Overdue = the 08:00 window passed
    (now past 08:15 Shanghai) with no successful run today.
    """
    row = conn.execute(
        text("SELECT started_at, finished_at, status FROM job_runs"
             " WHERE job_name = 'daily'"
             " ORDER BY started_at DESC LIMIT 1"),
    ).first()
    last_success = conn.execute(
        text("SELECT MAX(finished_at) FROM job_runs"
             " WHERE job_name = 'daily' AND status = 'success'"),
    ).scalar_one_or_none()
    now_sh = datetime.now(SHANGHAI)
    next_run = _next_run_8am(now_sh)
    if row is None:
        status = "unknown"
    elif (last_success is None
          or last_success.astimezone(SHANGHAI).date() != now_sh.date()) \
            and now_sh >= now_sh.replace(hour=8, minute=15, second=0,
                                         microsecond=0):
        status = "overdue"
    elif row[2] == "failed":
        status = "failed"
    else:
        status = "healthy"
    return {"last_run": _iso(row[0]) if row else None,
            "last_success": _iso(last_success),
            "next_run": next_run.isoformat(),
            "status": status}


def _cron_overdue(conn) -> bool:
    return _cron_summary(conn)["status"] == "overdue"


# --- dependency probes (short timeouts, contract §2 #7) --------------------


def _probe_postgres() -> tuple[str, int | None]:
    start = time.monotonic()
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar_one()
        return "healthy", int((time.monotonic() - start) * 1000)
    except Exception as exc:  # noqa: BLE001 — probe reports, never raises
        log.warning("admin health: postgres probe failed: %s", exc)
        return "unavailable", int((time.monotonic() - start) * 1000)


def _probe_redis() -> tuple[str, int | None]:
    start = time.monotonic()
    try:
        url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        client = redis_lib.Redis.from_url(
            url, decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return "healthy", int((time.monotonic() - start) * 1000)
    except Exception as exc:  # noqa: BLE001 — probe reports, never raises
        log.warning("admin health: redis probe failed: %s", exc)
        return "unavailable", int((time.monotonic() - start) * 1000)


def _probe_ollama() -> bool:
    try:
        base = os.environ.get("OLLAMA_BASE_URL",
                              "http://127.0.0.1:11434")
        with httpx.Client(timeout=2) as client:
            resp = client.get(f"{base}/api/tags")
        return resp.status_code < 500
    except Exception as exc:  # noqa: BLE001 — probe reports, never raises
        log.warning("admin health: ollama probe failed: %s", exc)
        return False


def _gpu_expected_off() -> bool:
    """Explicit 'expected off' configuration (plan §4.3).

    Env ``IMSF_GPU_EXPECTED_OFF`` = 1/true/yes means the GPU host is
    deliberately shut down (Lam's standing order: the GPU stays off
    unless he asks for a start), so an unreachable Ollama is reported
    as offline_expected rather than unavailable.
    """
    return os.environ.get("IMSF_GPU_EXPECTED_OFF", "").strip().lower() \
        in ("1", "true", "yes")


def _receipt_worker_state(conn) -> dict:
    """Real receipt-pipeline state; heartbeat is honestly unknown.

    There is no worker heartbeat mechanism in the codebase
    (worker/main.py only consumes the Redis list and updates
    receipts.status) — status is therefore always "unknown" and
    heartbeat_at null, never fabricated. Queue depth comes from the
    live Redis list; running/failed/oldest/last-completed come from
    the receipts table.
    """
    try:
        queued = get_redis().llen(QUEUE_KEY)
    except Exception as exc:  # noqa: BLE001 — report, never raise
        log.warning("admin health: receipt queue read failed: %s", exc)
        queued = None
    running = conn.execute(
        text("SELECT COUNT(*) FROM receipts WHERE status = 'processing'"),
    ).scalar_one()
    failed = conn.execute(
        text("SELECT COUNT(*) FROM receipts WHERE status = 'failed'"),
    ).scalar_one()
    oldest = conn.execute(
        text("SELECT MIN(created_at) FROM receipts"
             " WHERE status IN ('pending', 'processing')"),
    ).scalar_one_or_none()
    last_completed = conn.execute(
        text("SELECT MAX(processed_at) FROM receipts"
             " WHERE status = 'completed'"),
    ).scalar_one_or_none()
    return {"status": "unknown", "queued": queued, "running": running,
            "failed": failed, "oldest_waiting": _iso(oldest),
            "last_completed": _iso(last_completed), "heartbeat_at": None}


# --- 1. GET /me ------------------------------------------------------------


@router.get("/me")
def get_me(ident: Identity = Depends(require_admin)):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, name, email, wechat_openid FROM users"
                 " WHERE id = :id"),
            {"id": ident.user_id},
        ).first()
    if row is None:  # require_admin already proved the user exists
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": str(row[0]), "name": row[1], "email": row[2],
            "login_method": _login_method(row[2], row[3]),
            "capabilities": list(CAPABILITIES)}


# --- 2. GET /stats ----------------------------------------------------------


@router.get("/stats")
def get_stats():
    engine = get_engine()
    with engine.connect() as conn:
        def count(sql):
            return conn.execute(text(sql)).scalar_one()

        counts = {
            "users": count("SELECT COUNT(*) FROM users"),
            "households": count("SELECT COUNT(*) FROM households"),
            "receipts": count("SELECT COUNT(*) FROM receipts"),
            "transactions": count("SELECT COUNT(*) FROM transactions"),
            "inventory_items": count("SELECT COUNT(*) FROM inventory_items"),
            "published_recipes": count(
                "SELECT COUNT(*) FROM community_recipes"
                " WHERE status = 'published'"),
            "draft_recipes": count(
                "SELECT COUNT(*) FROM community_recipes"
                " WHERE status = 'draft'"),
            "hidden_recipes": count(
                "SELECT COUNT(*) FROM community_recipes"
                " WHERE status = 'hidden'"),
        }
        failed_jobs = count(
            "SELECT COUNT(*) FROM receipts WHERE status = 'failed'")
        overdue = _cron_overdue(conn)
    unavailable = []
    if not _probe_ollama():
        unavailable.append("ollama (knowledge search)")
    redis_status, _ = _probe_redis()
    if redis_status != "healthy":
        unavailable.append("redis")
    return {"counts": counts,
            "exceptions": {"failed_receipt_jobs": failed_jobs,
                           "overdue_cron": overdue,
                           "unavailable_dependencies": unavailable}}


# --- 3/4. Users -------------------------------------------------------------


@router.get("/users")
def list_users(q: str | None = Query(None),
               login_method: str | None = Query(None),
               status: str | None = Query(None),
               limit: int = Query(20), offset: int = Query(0)):
    limit, offset = _page(limit, offset)
    if q is not None and not q.strip():
        raise HTTPException(status_code=400,
                            detail="q must not be blank")
    if login_method is not None and login_method not in ("email", "wechat"):
        raise HTTPException(status_code=400,
                            detail="login_method must be 'email' or 'wechat'")
    if status is not None and status not in ("enabled", "disabled"):
        raise HTTPException(status_code=400,
                            detail="status must be 'enabled' or 'disabled'")
    where = []
    params: dict = {}
    if q is not None:
        where.append("(email = :q OR wechat_openid = :q"
                     " OR name ILIKE :qlike)")
        params["q"] = q.strip()
        params["qlike"] = f"%{q.strip()}%"
    if login_method == "email":
        where.append("email IS NOT NULL")
    elif login_method == "wechat":
        where.append("wechat_openid IS NOT NULL")
    if status == "enabled":
        where.append("disabled_at IS NULL")
    elif status == "disabled":
        where.append("disabled_at IS NOT NULL")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM users{clause}"), params,
        ).scalar_one()
        rows = conn.execute(
            text("SELECT id, name, email, wechat_openid, disabled_at,"
                 " created_at FROM users"
                 f"{clause} ORDER BY created_at DESC, id DESC"
                 " LIMIT :limit OFFSET :offset"),
            {**params, "limit": limit, "offset": offset},
        ).all()
    # NEVER return openid (exact-openid lookup is server-side only).
    items = [{"id": str(r[0]), "name": r[1], "email": r[2],
              "login_method": _login_method(r[2], r[3]),
              "status": _user_status(r[4]),
              "created_at": _iso(r[5])} for r in rows]
    return {"items": items, "total": total}


@router.get("/users/{user_id}")
def get_user(user_id: uuid.UUID):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, name, email, wechat_openid, disabled_at,"
                 " created_at FROM users WHERE id = :id"),
            {"id": user_id},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        households = conn.execute(
            text("SELECT h.id, h.name, m.role FROM households h"
                 " JOIN household_members m ON m.household_id = h.id"
                 " WHERE m.user_id = :u ORDER BY h.created_at"),
            {"u": user_id},
        ).all()
        hids = [h[0] for h in households]
        if hids:
            tx = conn.execute(
                text("SELECT COUNT(*) FROM transactions"
                     " WHERE household_id = ANY(:hids)"),
                {"hids": hids},
            ).scalar_one()
            inv = conn.execute(
                text("SELECT COUNT(*) FROM inventory_items"
                     " WHERE household_id = ANY(:hids)"),
                {"hids": hids},
            ).scalar_one()
            eq = conn.execute(
                text("SELECT COUNT(*) FROM equipments"
                     " WHERE household_id = ANY(:hids)"),
                {"hids": hids},
            ).scalar_one()
        else:
            tx = inv = eq = 0
        receipts = conn.execute(
            text("SELECT COUNT(*) FROM receipts"
                 " WHERE uploaded_by_user_id = :u"),
            {"u": user_id},
        ).scalar_one()
    return {"id": str(row[0]), "name": row[1], "email": row[2],
            "login_method": _login_method(row[2], row[3]),
            "status": _user_status(row[4]),
            "disabled_at": _iso(row[4]),
            "created_at": _iso(row[5]),
            "households": [{"household_id": str(h[0]), "name": h[1],
                            "role": h[2]} for h in households],
            "counts": {"receipts": receipts, "transactions": tx,
                       "inventory_items": inv, "equipments": eq}}


# --- 5. Household records (sensitive read, audited) ------------------------


_RECORD_QUERIES = {
    # Reuses the public shapes (no OCR raw text, no image data).
    "receipts": ("SELECT id, household_id, store_name, purchased_at,"
                 " total_amount, currency, status, error_message,"
                 " processed_at, created_at FROM receipts"
                 " WHERE household_id = :h"
                 " ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
                 "SELECT COUNT(*) FROM receipts WHERE household_id = :h"),
    "transactions": ("SELECT id, household_id, receipt_id, type, amount,"
                     " currency, category, occurred_at, note, created_at"
                     " FROM transactions WHERE household_id = :h"
                     " ORDER BY occurred_at DESC, id DESC"
                     " LIMIT :limit OFFSET :offset",
                     "SELECT COUNT(*) FROM transactions"
                     " WHERE household_id = :h"),
    "inventory": ("SELECT id, household_id, receipt_id, raw_name,"
                  " quantity, unit, price, currency, storage_zone,"
                  " added_date, auto_expiry_date, status, created_at"
                  " FROM inventory_items WHERE household_id = :h"
                  " ORDER BY added_date DESC, id DESC"
                  " LIMIT :limit OFFSET :offset",
                  "SELECT COUNT(*) FROM inventory_items"
                  " WHERE household_id = :h"),
    "equipment": ("SELECT id, household_id, device_type, brand_model,"
                  " usage_intensity, last_maintained_at,"
                  " next_maintenance_date, status, household_size"
                  " FROM equipments WHERE household_id = :h"
                  " ORDER BY created_at DESC"
                  " LIMIT :limit OFFSET :offset",
                  "SELECT COUNT(*) FROM equipments WHERE household_id = :h"),
}


def _record_row(rtype: str, row) -> dict:
    m = row._mapping
    if rtype == "receipts":
        return {"id": str(m["id"]), "household_id": str(m["household_id"]),
                "store_name": m["store_name"],
                "purchased_at": _iso(m["purchased_at"]),
                "total_amount": float(m["total_amount"]),
                "currency": m["currency"], "status": m["status"],
                "error_message": m["error_message"],
                "processed_at": _iso(m["processed_at"]),
                "created_at": _iso(m["created_at"])}
    if rtype == "transactions":
        return {"id": str(m["id"]), "household_id": str(m["household_id"]),
                "receipt_id": str(m["receipt_id"])
                if m["receipt_id"] else None,
                "type": m["type"], "amount": float(m["amount"]),
                "currency": m["currency"], "category": m["category"],
                "occurred_at": _iso(m["occurred_at"]), "note": m["note"],
                "created_at": _iso(m["created_at"])}
    if rtype == "inventory":
        return {"id": str(m["id"]), "household_id": str(m["household_id"]),
                "receipt_id": str(m["receipt_id"])
                if m["receipt_id"] else None,
                "raw_name": m["raw_name"],
                "quantity": float(m["quantity"]), "unit": m["unit"],
                "price": float(m["price"]) if m["price"] is not None else None,
                "currency": m["currency"],
                "storage_zone": m["storage_zone"],
                "added_date": str(m["added_date"])
                if m["added_date"] else None,
                "auto_expiry_date": str(m["auto_expiry_date"])
                if m["auto_expiry_date"] else None,
                "status": m["status"], "created_at": _iso(m["created_at"])}
    return {"id": str(m["id"]), "household_id": str(m["household_id"]),
            "device_type": m["device_type"],
            "brand_model": m["brand_model"],
            "usage_intensity": m["usage_intensity"],
            "last_maintained_at": _iso(m["last_maintained_at"]),
            "next_maintenance_date": str(m["next_maintenance_date"])
            if m["next_maintenance_date"] else None,
            "status": m["status"],
            "household_size": m["household_size"]}


@router.get("/households/{household_id}/records")
def household_records(household_id: uuid.UUID,
                      request: Request,
                      type: str | None = Query(None),
                      reason: str | None = Query(None),
                      limit: int = Query(20), offset: int = Query(0),
                      ident: Identity = Depends(require_admin)):
    limit, offset = _page(limit, offset)
    if type is None or type not in _RECORD_QUERIES:
        raise HTTPException(
            status_code=400,
            detail="type is required: receipts, transactions,"
                   " inventory or equipment")
    if reason is None or not reason.strip():
        raise HTTPException(status_code=400,
                            detail="reason is required")
    engine = get_engine()
    # Audit row in the SAME transaction as the read (contract §1.3).
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM households WHERE id = :h"),
            {"h": household_id},
        ).first()
        if exists is None:
            raise HTTPException(status_code=404,
                                detail="Household not found")
        _audit(conn, ident.user_id, "household_records_inspected",
               "household", str(household_id), reason.strip(),
               details={"type": type}, request=request)
        list_sql, count_sql = _RECORD_QUERIES[type]
        total = conn.execute(text(count_sql),
                             {"h": household_id}).scalar_one()
        rows = conn.execute(
            text(list_sql),
            {"h": household_id, "limit": limit, "offset": offset},
        ).all()
    return {"items": [_record_row(type, r) for r in rows], "total": total}


# --- 6. PATCH /users/{id}/status -------------------------------------------


@router.patch("/users/{user_id}/status")
def set_user_status(user_id: uuid.UUID, request: Request,
                    body: dict,
                    ident: Identity = Depends(require_admin)):
    if not isinstance(body.get("disabled"), bool):
        raise HTTPException(status_code=400,
                            detail="disabled (bool) is required")
    reason = body.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise HTTPException(status_code=400,
                            detail="reason is required")
    disabled = body["disabled"]
    # Sole-admin self-disable block (contract §1.3).
    if disabled and ident.user_id == user_id \
            and len(get_admin_user_ids()) == 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot disable the sole admin account")
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, name, email, wechat_openid, disabled_at,"
                 " auth_version FROM users WHERE id = :id"),
            {"id": user_id},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        was_disabled = row[4] is not None
        conn.execute(
            text("UPDATE users SET disabled_at ="
                 " CASE WHEN :d THEN now() ELSE NULL END,"
                 " auth_version = auth_version + 1 WHERE id = :id"),
            {"d": disabled, "id": user_id},
        )
        _audit(conn, ident.user_id,
               "user_disabled" if disabled else "user_reenabled",
               "user", str(user_id), reason.strip(),
               details={"was_disabled": was_disabled,
                        "disabled": disabled},
               request=request)
        updated = conn.execute(
            text("SELECT id, name, email, wechat_openid, disabled_at"
                 " FROM users WHERE id = :id"),
            {"id": user_id},
        ).first()
    assert updated is not None  # 404 was raised above when missing
    return {"id": str(updated[0]), "name": updated[1],
            "email": updated[2],
            "login_method": _login_method(updated[2], updated[3]),
            "status": _user_status(updated[4]),
            "disabled_at": _iso(updated[4])}


# --- 7. GET /health ---------------------------------------------------------


@router.get("/health")
def get_health():
    started = time.monotonic()
    engine = get_engine()
    pg_status, pg_ms = _probe_postgres()
    redis_status, redis_ms = _probe_redis()
    ollama_ok = _probe_ollama()
    expected_off = _gpu_expected_off()
    if ollama_ok:
        gpu_status = "healthy"
    elif expected_off:
        gpu_status = "offline_expected"
    else:
        gpu_status = "unavailable"
    with engine.connect() as conn:
        cron = _cron_summary(conn)
        worker = _receipt_worker_state(conn)
    api_ms = int((time.monotonic() - started) * 1000)
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "api": {"status": "healthy", "latency_ms": api_ms,
                "commit": _COMMIT, "version": "0.1.0"},
        "postgres": {"status": pg_status, "latency_ms": pg_ms},
        "redis": {"status": redis_status, "latency_ms": redis_ms},
        "gpu": {"status": gpu_status, "expected_off": expected_off,
                "embedding_model": EMBEDDING_MODEL,
                "affected": ["knowledge search"]},
        "cron": cron,
        "receipt_worker": worker,
        "vercel": {"web_url": VERCEL_WEB_URL, "api_url": VERCEL_API_URL,
                   "api_note": "hollow/unconfigured"},
    }


# --- 8. GET /jobs -----------------------------------------------------------


@router.get("/jobs")
def get_jobs(limit: int = Query(20)):
    limit, _ = _page(limit, 0)
    engine = get_engine()
    with engine.connect() as conn:
        cron = _cron_summary(conn)
        rows = conn.execute(
            text("SELECT id, job_name, started_at, finished_at, status,"
                 " notifications_created, error, duration_ms"
                 " FROM job_runs ORDER BY started_at DESC, id DESC"
                 " LIMIT :limit"),
            {"limit": limit},
        ).all()
    history = [{"id": str(r[0]), "job_name": r[1],
                "started_at": _iso(r[2]), "finished_at": _iso(r[3]),
                "status": r[4], "notifications_created": r[5],
                "error": r[6], "duration_ms": r[7]} for r in rows]
    return {"cron": cron, "history": history,
            "worker_heartbeat": {"at": None, "status": "unknown"}}


# --- 9. GET /receipt-jobs ---------------------------------------------------


@router.get("/receipt-jobs")
def get_receipt_jobs(limit: int = Query(20), offset: int = Query(0)):
    """Real receipt-job state from the receipts table.

    The pipeline has no separate durable job table: a job IS a receipt
    row (status pending/processing/completed/failed/needs_review,
    processed_at, error_message) plus the live Redis queue depth
    (see /health receipt_worker.queued). That real state is returned
    here; nothing is fabricated. If the receipts table itself were
    ever empty, items is honestly [] with total 0.
    """
    limit, offset = _page(limit, offset)
    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM receipts"),
        ).scalar_one()
        rows = conn.execute(
            text("SELECT id, household_id, store_name, purchased_at,"
                 " total_amount, currency, status, error_message,"
                 " processed_at, created_at FROM receipts"
                 " ORDER BY created_at DESC, id DESC"
                 " LIMIT :limit OFFSET :offset"),
            {"limit": limit, "offset": offset},
        ).all()
    items = [{"id": str(r[0]), "household_id": str(r[1]),
              "store_name": r[2],
              "purchased_at": _iso(r[3]),
              "total_amount": float(r[4]), "currency": r[5],
              "status": r[6], "error_message": r[7],
              "processed_at": _iso(r[8]),
              "created_at": _iso(r[9])} for r in rows]
    return {"items": items, "total": total}


# --- 10/11/12. Recipes ------------------------------------------------------


_RECIPE_ADMIN_COLS = ("id, author_id, title, cover_image, cook_time,"
                     " likes_count, status, created_at, updated_at,"
                     " description, source_url, category, language,"
                     " difficulty, taste, slug, author, steps_json")


def _recipe_admin_row(row) -> dict:
    m = row._mapping
    return {"id": str(m["id"]), "title": m["title"],
            "status": m["status"],
            # TEXT author = seed/source display name; author_id is
            # always NULL for admin-created seeds (contract §2 #11).
            "author": m["author"],
            "source_url": m["source_url"], "category": m["category"],
            "language": m["language"], "updated_at": _iso(m["updated_at"]),
            "description": m["description"],
            "difficulty": m["difficulty"], "taste": m["taste"],
            "slug": m["slug"], "cover_image": m["cover_image"],
            "steps_json": m["steps_json"], "cook_time": m["cook_time"],
            "likes_count": m["likes_count"],
            "created_at": _iso(m["created_at"])}


@router.get("/recipes")
def list_recipes_admin(status: str | None = Query(None),
                       limit: int = Query(20), offset: int = Query(0)):
    limit, offset = _page(limit, offset)
    if status is not None and status not in RECIPE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status must be 'draft', 'published' or 'hidden'")
    where = " WHERE status = :s" if status is not None else ""
    params: dict = {"s": status} if status is not None else {}
    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM community_recipes{where}"),
            params,
        ).scalar_one()
        rows = conn.execute(
            text(f"SELECT {_RECIPE_ADMIN_COLS} FROM community_recipes"
                 f"{where} ORDER BY updated_at DESC, id DESC"
                 " LIMIT :limit OFFSET :offset"),
            {**params, "limit": limit, "offset": offset},
        ).all()
    items = [{k: v for k, v in _recipe_admin_row(r).items()
              if k in ("id", "title", "status", "author", "source_url",
                       "category", "language", "updated_at")}
             for r in rows]
    return {"items": items, "total": total}


@router.post("/recipes")
def create_recipe_admin(request: Request, body: dict,
                        ident: Identity = Depends(require_admin)):
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    unknown = sorted(set(body) - {"title"} - set(RECIPE_CREATEABLE))
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"Unknown fields: {', '.join(unknown)}")
    steps_json = body.get("steps_json")
    if steps_json is None:
        steps_json = []
    if not isinstance(steps_json, (list, dict)):
        raise HTTPException(status_code=400,
                            detail="steps_json must be a list or object")
    cook_time = body.get("cook_time")
    if cook_time is not None and (
            isinstance(cook_time, bool)
            or not isinstance(cook_time, int)):
        raise HTTPException(status_code=400,
                            detail="cook_time must be an integer")
    ingredients = body.get("ingredients")
    if ingredients is not None and not isinstance(ingredients, list):
        raise HTTPException(status_code=400,
                            detail="ingredients must be a list")
    engine = get_engine()
    with engine.begin() as conn:
        recipe_id = conn.execute(
            text("INSERT INTO community_recipes (author_id, title,"
                 " cover_image, steps_json, cook_time, likes_count,"
                 " status, description, source_url, category, language,"
                 " difficulty, taste, slug, author)"
                 " VALUES (NULL, :title, :cover,"
                 " CAST(:steps AS jsonb), :cook, 0, 'draft',"
                 " :desc, :src, :cat, :lang, :diff, :taste, :slug, :aname)"
                 " RETURNING id"),
            {"title": title.strip(), "cover": body.get("cover_image"),
             "steps": json.dumps(steps_json), "cook": cook_time,
             "desc": body.get("description"), "src": body.get("source_url"),
             "cat": body.get("category"), "lang": body.get("language"),
             "diff": body.get("difficulty"), "taste": body.get("taste"),
             "slug": body.get("slug"), "aname": body.get("author")},
        ).scalar_one()
        for ing in ingredients or []:
            if not isinstance(ing, dict):
                raise HTTPException(
                    status_code=400,
                    detail="each ingredient must be an object")
            raw = ing.get("raw_name") or ing.get("name")
            if not isinstance(raw, str) or not raw.strip():
                raise HTTPException(
                    status_code=400,
                    detail="each ingredient needs a name")
            conn.execute(
                text("INSERT INTO recipe_ingredients (recipe_id,"
                     " raw_name, amount, unit, is_main_ingredient)"
                     " VALUES (:rid, :raw, :amt, :unit, FALSE)"),
                {"rid": recipe_id, "raw": raw.strip(),
                 "amt": ing.get("amount"), "unit": ing.get("unit") or ""},
            )
        _audit(conn, ident.user_id, "recipe_created", "recipe",
               str(recipe_id), None,
               details={"title": title.strip()}, request=request)
        row = conn.execute(
            text(f"SELECT {_RECIPE_ADMIN_COLS} FROM community_recipes"
                 " WHERE id = :id"),
            {"id": recipe_id},
        ).first()
    out = _recipe_admin_row(row)
    out["ingredients"] = ingredients or []
    return out


@router.patch("/recipes/{recipe_id}")
def update_recipe_admin(recipe_id: uuid.UUID, request: Request,
                        body: dict,
                        ident: Identity = Depends(require_admin)):
    unknown = sorted(set(body) - set(RECIPE_EDITABLE))
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"Unknown fields: {', '.join(unknown)}")
    if not body:
        raise HTTPException(status_code=400,
                            detail="nothing to update")
    if "status" in body and body["status"] not in RECIPE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status must be 'draft', 'published' or 'hidden'")
    if "title" in body and (not isinstance(body["title"], str)
                            or not body["title"].strip()):
        raise HTTPException(status_code=400,
                            detail="title must not be blank")
    if "steps_json" in body and body["steps_json"] is not None \
            and not isinstance(body["steps_json"], (list, dict)):
        raise HTTPException(status_code=400,
                            detail="steps_json must be a list or object")
    if "cook_time" in body and body["cook_time"] is not None and (
            isinstance(body["cook_time"], bool)
            or not isinstance(body["cook_time"], int)):
        raise HTTPException(status_code=400,
                            detail="cook_time must be an integer")
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(f"SELECT {_RECIPE_ADMIN_COLS} FROM community_recipes"
                 " WHERE id = :id"),
            {"id": recipe_id},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Recipe not found")
        sets = []
        params: dict = {"id": recipe_id}
        for key in RECIPE_EDITABLE:
            if key not in body:
                continue
            value = body[key]
            if key == "steps_json":
                sets.append("steps_json = CAST(:steps_json AS jsonb)")
                params["steps_json"] = json.dumps(value) \
                    if value is not None else None
            elif key == "title":
                sets.append("title = :title")
                params["title"] = value.strip()
            else:
                sets.append(f"{key} = :{key}")
                params[key] = value
        sets.append("updated_at = now()")
        conn.execute(
            text("UPDATE community_recipes SET " + ", ".join(sets)
                 + " WHERE id = :id"),
            params,
        )
        _audit(conn, ident.user_id, "recipe_updated", "recipe",
               str(recipe_id), None,
               details={"fields": sorted(body)}, request=request)
        updated = conn.execute(
            text(f"SELECT {_RECIPE_ADMIN_COLS} FROM community_recipes"
                 " WHERE id = :id"),
            {"id": recipe_id},
        ).first()
    return _recipe_admin_row(updated)


# --- 13. GET /audit-events --------------------------------------------------


@router.get("/audit-events")
def list_audit_events(action: str | None = Query(None),
                      target_id: str | None = Query(None),
                      from_: str | None = Query(None, alias="from"),
                      to: str | None = Query(None),
                      limit: int = Query(20), offset: int = Query(0)):
    limit, offset = _page(limit, offset)
    where = []
    params: dict = {}
    if action is not None:
        where.append("action = :action")
        params["action"] = action
    if target_id is not None:
        where.append("target_id = :tid")
        params["tid"] = target_id
    for name, value in (("from", from_), ("to", to)):
        if value is None:
            continue
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"{name} must be an ISO date")
        # A bare YYYY-MM-DD covers the whole day (UTC).
        if len(value) == 10:
            if name == "from":
                where.append("created_at >= :from_dt")
                params["from_dt"] = parsed.replace(tzinfo=timezone.utc)
            else:
                where.append("created_at < :to_dt")
                params["to_dt"] = (parsed + timedelta(days=1)).replace(
                    tzinfo=timezone.utc)
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if name == "from":
                where.append("created_at >= :from_dt")
                params["from_dt"] = parsed
            else:
                where.append("created_at <= :to_dt")
                params["to_dt"] = parsed
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM admin_audit_events{clause}"),
            params,
        ).scalar_one()
        rows = conn.execute(
            text("SELECT id, actor_user_id, action, target_type,"
                 " target_id, created_at, reason, outcome, details"
                 " FROM admin_audit_events"
                 f"{clause} ORDER BY created_at DESC, id DESC"
                 " LIMIT :limit OFFSET :offset"),
            {**params, "limit": limit, "offset": offset},
        ).all()
    items = [{"id": str(r[0]), "actor_user_id": str(r[1]),
              "action": r[2], "target_type": r[3], "target_id": r[4],
              "created_at": _iso(r[5]), "reason": r[6],
              "outcome": r[7], "details": r[8]} for r in rows]
    return {"items": items, "total": total}
