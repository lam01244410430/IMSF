"""Receipt-processing worker (design §6).

Redis consumer on ``imsf-v2:receipt-jobs``; job =
{"receipt_id", "household_id", "image_path", "attempts"}.

Implements §6.2 steps 1, 2, 3, 4 and 6, SKIPPING the 2% reconciliation
check (Step 3 adds it — see §6.4): on a successful parse, persist
receipt_lines for ALL lines and inventory_items for is_stock_item
lines, set status completed + processed_at.

Retries: max 3 attempts, backoff 5s → 30s → 120s (§6.5). A bad job
never crashes the worker: every per-job exception is caught, logged,
and the receipt is marked failed (or requeued while attempts remain).
Config errors (Baidu not configured) and Qwen JSON errors (already
retried once inside the parse step) fail immediately without requeue.
"""

import json
import logging
import os
import sys
import time
import traceback
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import redis as redis_lib
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import text

from app.db import QUEUE_KEY, get_engine, get_redis
from app.ocr import run_ocr
from app.ocr_baidu import BaiduNotConfiguredError
from app.qwen import QwenParseError, parse_receipt_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("imsf-v2-worker")

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = [5, 30, 120]  # §6.5
FALLBACK_SHELF_LIFE_DAYS = 3  # §6.2 step 6: unmatched item → +3 days
SHANGHAI = ZoneInfo("Asia/Shanghai")

# Errors that must NOT be retried: the outcome cannot change on retry.
NON_RETRYABLE = (BaiduNotConfiguredError, QwenParseError)


def _norm(name: str) -> str:
    return "".join(str(name).split()).lower()


def load_master_map(conn) -> dict[str, dict]:
    """canonical_name (normalised) -> {id, zone, shelf_life_days}."""
    rows = conn.execute(
        text("SELECT id, canonical_name, default_storage_zone,"
             " default_shelf_life_days FROM master_ingredients")
    ).all()
    return {
        _norm(r[1]): {"id": r[0], "name": r[1], "zone": r[2], "shelf_life": r[3]}
        for r in rows
    }


def _parse_purchased_at(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SHANGHAI)
        return dt
    except ValueError:
        return None


def _dec(value, default=Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return default


def process_job(job: dict) -> str:
    """Process one job. Returns the final receipt status.

    Raises nothing: all failures are recorded on the receipt row.
    """
    receipt_id = job.get("receipt_id")
    household_id = job.get("household_id")
    image_path = job.get("image_path")
    attempts = int(job.get("attempts") or 0)
    log.info("job receipt=%s household=%s attempts=%s",
             receipt_id, household_id, attempts)
    engine = get_engine()

    def mark_failed(message: str) -> str:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE receipts SET status='failed',"
                     " error_message=:msg, updated_at=now() WHERE id=:rid"),
                {"msg": message[:2000], "rid": receipt_id},
            )
        log.warning("job receipt=%s FAILED: %s", receipt_id, message)
        return "failed"

    try:
        if not receipt_id or not image_path:
            raise ValueError(f"job missing receipt_id/image_path: {job!r}")
        try:
            with open(image_path, "rb") as fh:
                image_bytes = fh.read()
        except OSError as exc:
            raise ValueError(f"cannot read receipt image {image_path}: {exc}")

        # Step 1: pending -> processing.
        with engine.begin() as conn:
            updated = conn.execute(
                text("UPDATE receipts SET status='processing', updated_at=now()"
                     " WHERE id=:rid AND status IN ('pending','failed')"),
                {"rid": receipt_id},
            ).rowcount
            if updated == 0:
                # Already being processed / already terminal — skip.
                row = conn.execute(
                    text("SELECT status FROM receipts WHERE id=:rid"),
                    {"rid": receipt_id},
                ).first()
                log.info("job receipt=%s skipped (status=%s)",
                         receipt_id, row[0] if row else "missing")
                return row[0] if row else "failed"

        # Step 2: OCR (provider from env OCR_PROVIDER).
        ocr = run_ocr(image_bytes)
        ocr_text = ocr["raw_text"]
        log.info("job receipt=%s OCR done (%d chars, provider=%s)",
                 receipt_id, len(ocr_text),
                 os.environ.get("OCR_PROVIDER", "baidu"))

        # Step 3: Qwen 14B parse (retry once on invalid JSON, per §6.2).
        with engine.connect() as conn:
            master = load_master_map(conn)
        parsed = None
        last_error: Exception | None = None
        for attempt_no in range(2):
            try:
                parsed = parse_receipt_text(
                    ocr_text,
                    canonical_names=[v["name"] for v in master.values()])
                break
            except QwenParseError as exc:
                last_error = exc
                log.warning("job receipt=%s Qwen parse attempt %d failed: %s",
                            receipt_id, attempt_no + 1, exc)
        if parsed is None:
            raise QwenParseError(str(last_error))

        # Step 4: canonical lookup (done inline below via master map).
        lines = parsed.get("lines") or []
        total = parsed.get("total_amount")
        if total is None:
            # STEP-2 INTERIM (ambiguity recorded): §6.4 (Step 3) will turn
            # a missing total into needs_review. Step 2 skips §6.4, so
            # fall back to the sum of lines to satisfy the NOT NULL
            # total_amount column; Step 3 replaces this with needs_review.
            total = sum(float(_dec(ln.get("price"))) for ln in lines)
            log.info("job receipt=%s Qwen returned no total; using "
                     "lines sum %.2f (Step 3 will needs_review this)",
                     receipt_id, total)
        currency = parsed.get("currency") or "CNY"
        if currency not in ("CNY", "VND"):
            currency = "CNY"
        purchased_at = _parse_purchased_at(parsed.get("purchased_at"))
        store_name = parsed.get("store_name")
        added = datetime.now(SHANGHAI).date()

        # Step 6: persist lines + inventory, mark completed.
        inventory_created = 0
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE receipts SET store_name=:store,"
                     " purchased_at=:purchased, total_amount=:total,"
                     " currency=:cur, ocr_raw_text=:ocr, status='completed',"
                     " error_message=NULL, processed_at=now(),"
                     " updated_at=now() WHERE id=:rid"),
                {"store": store_name, "purchased": purchased_at,
                 "total": _dec(total), "cur": currency,
                 "ocr": ocr_text, "rid": receipt_id},
            )
            for i, ln in enumerate(lines, start=1):
                raw_name = str(ln.get("raw_name") or "").strip() or "?"
                quantity = _dec(ln.get("quantity"), Decimal("0"))
                unit = str(ln.get("unit") or "").strip() or "个"
                price = _dec(ln.get("price"))
                is_stock = bool(ln.get("is_stock_item", True))
                canon = master.get(_norm(ln.get("canonical_name") or "")) \
                    or master.get(_norm(raw_name))
                line_id = conn.execute(
                    text("INSERT INTO receipt_lines (receipt_id, line_no,"
                         " raw_name, quantity, unit, price, currency,"
                         " canonical_ingredient_id, is_stock_item)"
                         " VALUES (:rid, :no, :raw, :qty, :unit, :price,"
                         " :cur, :canon, :stock) RETURNING id"),
                    {"rid": receipt_id, "no": i, "raw": raw_name,
                     "qty": quantity, "unit": unit, "price": price,
                     "cur": currency,
                     "canon": canon["id"] if canon else None,
                     "stock": is_stock},
                ).scalar_one()
                if is_stock and quantity > 0:
                    if canon and canon["shelf_life"] is not None:
                        expiry = added + timedelta(days=canon["shelf_life"])
                    else:
                        # Recorded fallback (§6.2 step 6).
                        expiry = added + timedelta(days=FALLBACK_SHELF_LIFE_DAYS)
                    conn.execute(
                        text("INSERT INTO inventory_items (household_id,"
                             " receipt_id, receipt_line_id, raw_name,"
                             " canonical_ingredient_id, quantity, unit,"
                             " price, currency, storage_zone, added_date,"
                             " auto_expiry_date, status)"
                             " VALUES (:h, :rid, :lid, :raw, :canon, :qty,"
                             " :unit, :price, :cur, :zone, :added, :exp,"
                             " 'fresh')"),
                        {"h": household_id, "rid": receipt_id,
                         "lid": line_id, "raw": raw_name,
                         "canon": canon["id"] if canon else None,
                         "qty": quantity, "unit": unit, "price": price,
                         "cur": currency,
                         "zone": canon["zone"] if canon else None,
                         "added": added, "exp": expiry},
                    )
                    inventory_created += 1
        log.info("job receipt=%s COMPLETED lines=%d inventory=%d total=%.2f",
                 receipt_id, len(lines), inventory_created, float(_dec(total)))
        return "completed"

    except NON_RETRYABLE as exc:
        return mark_failed(f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001 — worker must never crash (§6.5)
        log.error("job receipt=%s attempt %d error: %s\n%s",
                  receipt_id, attempts + 1, exc, traceback.format_exc())
        if attempts + 1 < MAX_ATTEMPTS:
            backoff = BACKOFF_SECONDS[min(attempts, len(BACKOFF_SECONDS) - 1)]
            log.info("job receipt=%s requeue after %ds backoff "
                     "(attempt %d/%d)", receipt_id, backoff,
                     attempts + 2, MAX_ATTEMPTS)
            time.sleep(backoff)
            job = dict(job)
            job["attempts"] = attempts + 1
            get_redis().rpush(QUEUE_KEY, json.dumps(job))
            return "requeued"
        return mark_failed(f"{type(exc).__name__}: {exc}")


def run_worker() -> None:
    redis_client = get_redis()
    log.info("worker started, listening on %s (provider=%s)",
             QUEUE_KEY, os.environ.get("OCR_PROVIDER", "baidu"))
    while True:
        try:
            item = redis_client.blpop(QUEUE_KEY, timeout=5)
        except RedisTimeoutError:
            continue  # normal idle timeout: no job arrived in 5s
        except Exception as exc:  # noqa: BLE001 — keep the loop alive
            log.error("redis blpop error: %s", exc)
            time.sleep(5)
            continue
        if not item:
            continue
        try:
            job = json.loads(item[1])
        except (ValueError, TypeError):
            log.error("dropping unparsable job payload: %r", item[1])
            continue
        try:
            process_job(job)
        except Exception:  # noqa: BLE001 — belt & braces; never die
            log.error("unexpected worker error:\n%s", traceback.format_exc())


if __name__ == "__main__":
    run_worker()
