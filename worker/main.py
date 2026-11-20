"""Receipt-processing worker (design §6).

Redis consumer on ``imsf-v2:receipt-jobs``; job =
{"receipt_id", "household_id", "image_path", "attempts"}.

Implements §6.2 steps 1-6, including the Step 3 additions:
- canonical mapping refinement (``app.reconcile.resolve_canonical``):
  raw_name exact match, then Qwen's suggested canonical_name, else
  NULL = explicitly unmatched; matched/unmatched counts are logged.
- Phase 2 Step 5 (design §3.6 / §6.3): alias lookup between the exact
  match and the Qwen suggestion (``load_alias_map``), with
  ``matched_via`` logged per line ('exact' / 'alias' / 'qwen' /
  'unmatched') — Gate F checks a seeded alias maps without a Qwen
  call for that line.
- Phase 2 Step 5 (design §7.3): when a matched ingredient's seed
  shelf life is NULL, the RAG shelf life (``app.rag``) is used before
  the +3 day fallback (seed > RAG > +3); a RAG failure never fails
  the job, it degrades to +3 days.
- the §6.4 2% reconciliation (``app.reconcile.check_reconciliation``),
  run AFTER persisting receipt_lines and BEFORE creating
  inventory_items. On needs_review the lines ARE persisted (so the user
  can see/correct them), inventory is NOT created, and processed_at IS
  set (it marks the end of processing, not success). The Step 2
  interim behaviour (using the lines sum when Qwen returned
  total_amount null) is REMOVED: a null/<=0 total now means
  needs_review ("không đọc được tổng tiền") per §6.4. The upload-time
  total_amount 0.00 placeholder is kept only until the worker writes
  the real total; when the total is unreadable the row keeps 0.00 and
  the receipt is needs_review.

Retries: max 3 attempts, backoff 5s → 30s → 120s (§6.5). A bad job
never crashes the worker: every per-job exception is caught, logged,
and the receipt is marked failed (or requeued while attempts remain).
Config errors (Baidu not configured) and Qwen JSON errors (already
retried once inside the parse step) fail immediately without requeue.
On failed, processed_at is also set (same "end of processing" rule).
"""

import json
import logging
import os
import sys
import time
import traceback
import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import redis as redis_lib
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import bindparam, text

from app.db import QUEUE_KEY, get_engine, get_redis
from app.ledger import insert_receipt_transaction
from app.ocr import run_ocr
from app.ocr_baidu import BaiduNotConfiguredError
from app.qwen import QwenParseError, parse_receipt_text
from app.rag import shelf_life_days_for
from app.reconcile import (check_reconciliation, insert_inventory_item,
                           match_alias, resolve_canonical)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("imsf-v2-worker")

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = [5, 30, 120]  # §6.5
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


def load_alias_map(conn, master_map: dict[str, dict]) -> dict[str, dict]:
    """alias (normalised) -> master_ingredients entry (§3.6 / §6.3).

    Reads ``master_ingredient_aliases`` (alias + master_ingredient_id)
    and maps each alias, normalised with the same ``normalize_name``
    rule as the canonical names, to the canonical entry it points at.
    Aliases whose master_ingredient_id is not in ``master_map`` are
    skipped (stale alias rows must not break the worker).
    """
    by_id = {entry["id"]: entry for entry in master_map.values()}
    rows = conn.execute(
        text("SELECT alias, master_ingredient_id"
             " FROM master_ingredient_aliases")
    ).all()
    alias_map: dict[str, dict] = {}
    for alias, ingredient_id in rows:
        entry = by_id.get(ingredient_id)
        if entry is not None:
            alias_map[_norm(alias)] = entry
    return alias_map


def _matched_via(raw_name: str, suggested_canonical_name,
                 master_map: dict, alias_map: dict) -> str:
    """Derive the mapping route for one line (Gate F, §9).

    'exact' if the normalised raw_name is a canonical name, 'alias'
    if it starts with a seeded alias (see app.reconcile.match_alias —
    printed lines carry a size suffix, so exact-only alias lookup
    never fires), 'qwen' if Qwen's suggestion matched a canonical
    name, else 'unmatched'. Mirrors resolve_canonical's order
    exactly — it is a log label, not a second resolution.
    """
    norm = _norm(raw_name)
    if norm in master_map:
        return "exact"
    if match_alias(raw_name, alias_map) is not None:
        return "alias"
    if suggested_canonical_name and _norm(suggested_canonical_name) \
            in master_map:
        return "qwen"
    return "unmatched"


def _rag_shelf_life_days(canonical_name: str, cache: dict) -> int | None:
    """RAG shelf-life days for one canonical name, cached per job.

    Returns None when RAG has no answer OR when the lookup itself
    fails (bge-m3 not pulled, Ollama down, Qwen extraction failed):
    a RAG failure must never fail the receipt job — the caller falls
    back to +3 days (§7.3: seed > RAG > +3).
    """
    if canonical_name not in cache:
        try:
            found = shelf_life_days_for(canonical_name)
            cache[canonical_name] = found["days"] if found else None
        except Exception as exc:  # noqa: BLE001 — RAG is best-effort here
            log.warning("RAG shelf-life lookup failed for %r: %s",
                        canonical_name, exc)
            cache[canonical_name] = None
    return cache[canonical_name]


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
        # processed_at marks the end of processing, not success (§6.4
        # note in app.reconcile): it is set on failed as well.
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE receipts SET status='failed',"
                     " error_message=:msg, processed_at=now(),"
                     " updated_at=now() WHERE id=:rid"),
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

        # Step 1: pending -> processing. A requeued job (attempts > 0)
        # still shows 'processing' from its previous attempt, so it
        # must be accepted too — otherwise a retry would be skipped
        # and the receipt stuck in 'processing' forever (found in the
        # Step 3 gates: receipts (b)/(c) hit the 120s Qwen timeout
        # once, were requeued, and their retries would have skipped).
        # Single worker + BLPOP means no concurrent double-processing.
        allowed = ("pending", "failed", "processing") if attempts > 0 \
            else ("pending", "failed")
        with engine.begin() as conn:
            stmt = text(
                "UPDATE receipts SET status='processing', updated_at=now()"
                " WHERE id=:rid AND status IN :allowed"
            ).bindparams(bindparam("allowed", expanding=True))
            updated = conn.execute(
                stmt, {"rid": receipt_id, "allowed": allowed},
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
            aliases = load_alias_map(conn, master)
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

        # Step 4: canonical mapping (order in app.reconcile:
        # raw_name exact match, then alias (§3.6), then Qwen's suggested
        # canonical_name, else NULL = explicitly unmatched). The alias
        # step runs BEFORE any Qwen-suggestion use, so a seeded alias
        # never costs an LLM call for that line (Gate F, §9).
        lines = parsed.get("lines") or []
        total = parsed.get("total_amount")  # may be None -> §6.4 needs_review
        currency = parsed.get("currency") or "CNY"
        if currency not in ("CNY", "VND"):
            currency = "CNY"
        purchased_at = _parse_purchased_at(parsed.get("purchased_at"))
        store_name = parsed.get("store_name")
        added = datetime.now(SHANGHAI).date()

        # Steps 5-6 (one transaction): persist the receipt header +
        # ALL receipt_lines, run the §6.4 reconciliation on the
        # persisted lines, then either mark needs_review (no inventory)
        # or create inventory_items and mark completed.
        matched = 0
        unmatched = 0
        inventory_created = 0
        rag_cache: dict = {}  # canonical_name -> RAG days|None, per job
        with engine.begin() as conn:
            # Header: the real total when Qwen read one; when it did
            # not, the row keeps the upload-time 0.00 placeholder and
            # the reconciliation below sends it to needs_review.
            conn.execute(
                text("UPDATE receipts SET store_name=:store,"
                     " purchased_at=:purchased, total_amount=:total,"
                     " currency=:cur, ocr_raw_text=:ocr,"
                     " updated_at=now() WHERE id=:rid"),
                {"store": store_name, "purchased": purchased_at,
                 "total": _dec(total) if total is not None else Decimal("0"),
                 "cur": currency, "ocr": ocr_text, "rid": receipt_id},
            )
            resolved = []  # (line dict, canon entry|None, line_id)
            for i, ln in enumerate(lines, start=1):
                raw_name = str(ln.get("raw_name") or "").strip() or "?"
                quantity = _dec(ln.get("quantity"), Decimal("0"))
                unit = str(ln.get("unit") or "").strip() or "个"
                price = _dec(ln.get("price"))
                is_stock = bool(ln.get("is_stock_item", True))
                canon = resolve_canonical(
                    raw_name, ln.get("canonical_name"), master,
                    alias_map=aliases)
                via = _matched_via(raw_name, ln.get("canonical_name"),
                                   master, aliases)
                log.info("job receipt=%s line %d raw=%r matched_via=%s"
                         " canon=%s",
                         receipt_id, i, raw_name, via,
                         canon["name"] if canon else None)
                if canon is not None:
                    matched += 1
                else:
                    unmatched += 1
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
                resolved.append(({
                    "raw_name": raw_name, "quantity": quantity,
                    "unit": unit, "price": price,
                    "is_stock_item": is_stock}, canon, line_id))
            # §6.4: lines_total = SUM(price) over ALL persisted lines.
            lines_total = conn.execute(
                text("SELECT COALESCE(SUM(price), 0) FROM receipt_lines"
                     " WHERE receipt_id=:rid"),
                {"rid": receipt_id},
            ).scalar_one()
            ok, error_msg = check_reconciliation(
                lines_total, _dec(total) if total is not None else None)
            log.info("job receipt=%s mapping matched=%d unmatched=%d"
                     " lines_total=%.2f total=%s reconcile=%s",
                     receipt_id, matched, unmatched, float(lines_total),
                     str(total), "ok" if ok else error_msg)
            if not ok:
                # Lines ARE persisted so the user can see/correct them;
                # inventory is NOT created; processed_at IS set.
                conn.execute(
                    text("UPDATE receipts SET status='needs_review',"
                         " error_message=:msg, processed_at=now(),"
                         " updated_at=now() WHERE id=:rid"),
                    {"msg": error_msg, "rid": receipt_id},
                )
                log.info("job receipt=%s NEEDS_REVIEW: %s",
                         receipt_id, error_msg)
                return "needs_review"
            for line, canon, line_id in resolved:
                if line["is_stock_item"] and line["quantity"] > 0:
                    # §7.3 expiry fallback seed > RAG > +3: RAG is
                    # consulted ONLY when the seed shelf life is NULL,
                    # and only once per canonical name per job (cache).
                    # A RAG failure degrades to +3, never fails the job.
                    rag_days = None
                    if canon is not None \
                            and canon.get("shelf_life") is None:
                        rag_days = _rag_shelf_life_days(
                            canon["name"], rag_cache)
                    insert_inventory_item(
                        conn, household_id, receipt_id, line_id,
                        line["raw_name"], canon, line["quantity"],
                        line["unit"], line["price"], currency, added,
                        rag_shelf_life_days=rag_days)
                    inventory_created += 1
            # §3.1: the receipt's one ledger row, in the SAME DB
            # transaction as the inventory creation — a receipt never
            # completes without it, and ux_transactions_receipt
            # blocks a second one.
            insert_receipt_transaction(
                conn, household_id, receipt_id, _dec(total), currency,
                purchased_at)
            conn.execute(
                text("UPDATE receipts SET status='completed',"
                     " error_message=NULL, processed_at=now(),"
                     " updated_at=now() WHERE id=:rid"),
                {"rid": receipt_id},
            )
        log.info("job receipt=%s COMPLETED lines=%d matched=%d unmatched=%d"
                 " inventory=%d total=%s",
                 receipt_id, len(lines), matched, unmatched,
                 inventory_created, str(total))
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
