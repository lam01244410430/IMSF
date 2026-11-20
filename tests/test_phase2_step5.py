"""Phase 2 Step 5 tests: RAG retrieval + alias lookup (design §7, §9 Gates E + F).

Runs against the disposable ``imsf_v2_test`` database (same pattern as
the Step 2/3/4 test files) so the dev DB is never touched.

Two tiers, by design (§9: Gate E/F need the model, the rest must not):

- DETERMINISTIC (must pass on CI, no live model): ``app.rag.embed_texts``
  is monkeypatched with a fixed fake embedder whose vectors make the
  cosine similarities known exactly, so retrieval logic, the 0.35
  threshold (§7.3), the topic filter, and the endpoint validation are
  tested without the GPU. The 5-doc test fixture is ingested into the
  TEST db with the REAL ingest script (``scripts/ingest_knowledge.py``)
  but with the stubbed embedder, so the stored vectors are the fake
  ones — consistent within the test.
- LIVE (skip gracefully when bge-m3 is unreachable — same pattern as
  ``test_qwen_vl_if_available``): the same 5-doc fixture is ingested
  with REAL bge-m3 embeddings, then Gate E is checked end to end
  (butter top-1 + FoodKeeper source, nonsense query -> []).

Gate F (alias, §3.6/§6.3) is deterministic by design: the Qwen parse
is mocked (canned dict, same pattern as the Step 3 worker tests), so
the test proves the alias path works even when Qwen is wrong or
absent — no live model is needed for it, and the worker never calls
Qwen or RAG for the alias line (the matched canonical has a seed
shelf life, so the RAG step is not consulted either).

Contract notes (from Worker A's implementation):
- ``search_knowledge`` returns ``[{title, source, content, score}]``
  with similarity >= 0.35, best first; ``[]`` when nothing clears it.
- ``GET /api/v2/knowledge/search``: ``q`` required, ``topic`` in
  ``shelf_life|maintenance``, ``k`` in 1..10; bad values -> 400
  (not 422), no JWT -> 401. Knowledge is global reference data, so
  no ``household_id`` is required.
- Alias order (§6.3): exact canonical -> alias -> Qwen suggestion ->
  unmatched. A printed line carries a size/quantity suffix
  (\"农夫山泉 550ml\" in the Step 3 ground-truth fixtures), so the
  alias step matches when the normalised raw name STARTS WITH a
  seeded alias (longest alias wins); exact-only lookup would never
  fire for those lines and Gate F could not pass — see
  ``app.reconcile.match_alias``.
- Shelf-life fallback (§7.3): seed > RAG > +3 days. RAG is consulted
  only when the matched canonical's seed shelf life is NULL, and a
  RAG failure degrades to +3 days, never fails the job.
"""

import importlib.util
import json
import logging
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import jwt
import pytest
import sqlalchemy as sa
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
KNOWLEDGE_FIXTURE = FIXTURES / "knowledge_test_fixture.jsonl"

# --- env for the app under test (must be set before importing app) -------
os.environ.setdefault("IMSF_V2_SERVICE_TOKEN", "test-service-token")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

BASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://imsf_v2:imsf_v2@127.0.0.1:55434/imsf_v2",
)
TEST_DB = "imsf_v2_test"


def _test_url() -> str:
    url = urlparse(BASE_URL)
    return urlunparse(url._replace(path=f"/{TEST_DB}"))


os.environ["DATABASE_URL"] = _test_url()

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import mint_access_token  # noqa: E402
from app.main import app  # noqa: E402
from app.reconcile import (  # noqa: E402
    expiry_for,
    match_alias,
    resolve_canonical,
)

client = TestClient(app)
SERVICE_HEADERS = {
    "Authorization": f"Bearer {os.environ['IMSF_V2_SERVICE_TOKEN']}"
}
SHANGHAI = ZoneInfo("Asia/Shanghai")

BUTTER_TITLE = "Butter — refrigerator and freezer storage"
CHEESE_TITLE = "Hard cheese (cheddar, Swiss, parmesan) — refrigerator and freezer storage"
SUGAR_TITLE = "Granulated sugar — pantry storage"
BEKO_TITLE = "Range hood — clean the grease filter every month (Beko)"
DAIKIN_TITLE = "Air conditioner — clean the air filter every two weeks (Daikin)"
FOODKEEPER_SOURCE = "USDA FoodKeeper (public domain, CC0 1.0)"
BUTTER_QUERY = "how long does butter keep in the fridge?"
NONSENSE_QUERY = "quantum entanglement spaceship warp drive repair manual"
FILTER_QUERY = "how often should I clean the filter?"

# A test-only canonical with NULL seed shelf life (inserted into the
# TEST db only — the 20 seed ingredients all have a seed shelf life,
# so the seed-NULL branch of §7.3 cannot be exercised with seeds).
NULL_SHELF_INGREDIENT = "Bơ lạt"


@pytest.fixture(scope="module", autouse=True)
def test_db():
    from alembic import command
    from alembic.config import Config

    admin = sa.create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB},
        ).first()
        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _test_url())
    command.upgrade(cfg, "head")
    engine = sa.create_engine(_test_url())
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE transactions, knowledge_documents, inventory_items,"
            " receipt_lines, receipts, household_members, households,"
            " users RESTART IDENTITY CASCADE"))
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(test_db):
    yield test_db
    with test_db.begin() as conn:
        conn.execute(text(
            "TRUNCATE transactions, knowledge_documents, inventory_items,"
            " receipt_lines, receipts, household_members, households,"
            " users RESTART IDENTITY CASCADE"))
        conn.execute(
            text("DELETE FROM master_ingredients"
                 " WHERE canonical_name = :n"),
            {"n": NULL_SHELF_INGREDIENT})


# --- helpers ---------------------------------------------------------------

def mk_household(name="Test Home"):
    r = client.post("/api/v2/households",
                    json={"name": name, "timezone": "Asia/Shanghai"},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def jwt_headers(db_engine):
    """A JWT for a real user row (knowledge search needs auth only)."""
    user_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone, name)"
                 " VALUES (:id, :p, 'RAG Tester')"),
            {"id": user_id, "p": "13800008888"},
        )
    return {"Authorization": f"Bearer {mint_access_token(user_id)}"}


def upload_image(household_id, png_name="step3_a_yonghui.png"):
    with open(FIXTURES / png_name, "rb") as fh:
        r = client.post(
            "/api/v2/receipts",
            data={"household_id": household_id},
            files={"image": (png_name, fh, "image/png")},
            headers=SERVICE_HEADERS)
    assert r.status_code == 202, r.text
    return r.json()["id"]


def pop_job():
    from app.db import get_redis
    job = None
    for _ in range(30):
        raw = get_redis().lpop("imsf-v2:receipt-jobs")
        if raw:
            job = json.loads(raw)
            break
        time.sleep(0.5)
    assert job is not None, "no job on imsf-v2:receipt-jobs after upload"
    return job


def run_receipt_with_parse(monkeypatch, parsed):
    """Upload a fixture image and run the worker with a canned Qwen
    parse (same pattern as the Step 3 worker tests). The OCR provider
    is mocked and the parse dict is used verbatim, so no live model
    is called. Returns (household_id, receipt_id, status)."""
    import worker.main as worker_main

    from app.db import get_redis
    get_redis().delete("imsf-v2:receipt-jobs")
    monkeypatch.setenv("OCR_PROVIDER", "mock")
    monkeypatch.setattr(worker_main, "parse_receipt_text",
                        lambda *a, **k: json.loads(json.dumps(parsed)))
    hid = mk_household()
    rid = upload_image(hid)
    job = pop_job()
    assert job["receipt_id"] == rid
    return hid, rid, worker_main.process_job(job)


def count_knowledge(db_engine, topic=None):
    with db_engine.connect() as conn:
        if topic is None:
            return conn.execute(
                text("SELECT count(*) FROM knowledge_documents")
            ).scalar_one()
        return conn.execute(
            text("SELECT count(*) FROM knowledge_documents"
                 " WHERE topic = :t"),
            {"t": topic},
        ).scalar_one()


def inventory_for_receipt(db_engine, rid):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT ii.raw_name, ii.canonical_ingredient_id,"
                 " ii.auto_expiry_date, mi.canonical_name"
                 " FROM inventory_items ii LEFT JOIN master_ingredients mi"
                 " ON mi.id = ii.canonical_ingredient_id"
                 " WHERE ii.receipt_id = :r ORDER BY ii.raw_name"),
            {"r": uuid.UUID(rid)},
        ).all()


def insert_null_shelf_ingredient(db_engine):
    with db_engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO master_ingredients (canonical_name, category,"
                 " default_storage_zone, default_shelf_life_days)"
                 " VALUES (:n, 'sữa', 'fridge', NULL) RETURNING id"),
            {"n": NULL_SHELF_INGREDIENT},
        ).scalar_one()


def today_shanghai():
    return datetime.now(SHANGHAI).date()


@pytest.fixture
def worker_log():
    """Capture the imsf-v2-worker logger with a handler attached to
    that logger itself (not via pytest's caplog).

    Why not caplog: in the full suite an earlier test module imports
    worker.main first, and after that caplog.text comes back empty
    for this logger even though the worker does log (proven by the
    module-only run, where caplog works, vs the full run, where the
    same assertions see ''). A handler on the logger itself does not
    depend on pytest's root-logger capture state.
    """
    records = []

    class _ListHandler(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = _ListHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("imsf-v2-worker")
    old_level = logger.level
    old_disabled = logger.disabled
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Alembic's fileConfig (run by every test module's migration
    # fixture from alembic.ini's [loggers] section) disables existing
    # loggers it does not know about, so a worker logger created by an
    # earlier module (test_phase2_ledger imports worker.main) arrives
    # here with disabled=True; re-enable it for this test.
    logger.disabled = False
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.disabled = old_disabled


def worker_log_text(records):
    return "\n".join(records)


# --- fake embedder (deterministic tier) ------------------------------------
#
# One basis direction per fixture doc (1024-dim unit vectors), so the
# cosine similarity between a query and a doc is known exactly:
# same direction -> 1.0, different directions -> 0.0. The threshold
# sentinels are unit vectors at a known angle to the butter direction
# (0.34 = just below the 0.35 threshold, 0.36 = just above it).

DIM = 1024


def _basis(i):
    vec = [0.0] * DIM
    vec[i] = 1.0
    return vec


def fake_embed_texts(texts):
    out = []
    for raw in texts:
        low = (raw or "").lower()
        if "threshold_below" in low:
            vec = [0.0] * DIM
            vec[0] = 0.34
            vec[5] = math.sqrt(1.0 - 0.34 ** 2)
            out.append(vec)
        elif "threshold_above" in low:
            vec = [0.0] * DIM
            vec[0] = 0.36
            vec[5] = math.sqrt(1.0 - 0.36 ** 2)
            out.append(vec)
        elif "butter" in low:
            out.append(_basis(0))
        elif "hard cheese" in low or "cheddar" in low:
            out.append(_basis(1))
        elif "sugar" in low:
            out.append(_basis(2))
        elif "beko" in low or "grease filter" in low:
            out.append(_basis(3))
        elif "daikin" in low or "air filter" in low:
            out.append(_basis(4))
        elif "filter" in low:
            # Generic filter question: equally close to both
            # maintenance docs (similarity 1/sqrt(2) each).
            vec = [0.0] * DIM
            vec[3] = math.sqrt(2) / 2
            vec[4] = math.sqrt(2) / 2
            out.append(vec)
        else:
            out.append(_basis(5))
    return out


def _load_ingest_module():
    spec = importlib.util.spec_from_file_location(
        "ingest_knowledge",
        REPO_ROOT / "scripts" / "ingest_knowledge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ingest_fixture_stubbed(monkeypatch):
    """Ingest the 5-doc test fixture with the REAL ingest script but
    the stubbed embedder (both import sites patched). Returns the
    ingest module's exit code."""
    import app.rag as rag_mod

    monkeypatch.setattr(rag_mod, "embed_texts", fake_embed_texts)
    mod = _load_ingest_module()
    monkeypatch.setattr(mod, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(sys, "argv", [
        "ingest_knowledge.py", "--file", str(KNOWLEDGE_FIXTURE),
        "--topic", "shelf_life"])
    return mod.main()


def _ollama_bge3_available():
    """Skip helper for the live tier (same pattern as
    test_qwen_vl_if_available)."""
    import httpx

    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    try:
        tags = httpx.get(f"{base}/api/tags", timeout=10).json()
    except Exception as exc:
        pytest.skip(f"Ollama not reachable: {exc}")
    models = [m.get("name", "") for m in tags.get("models", [])]
    if not any(n.startswith("bge-m3") for n in models):
        pytest.skip("bge-m3 model not pulled (pull failed or pending)")


def ingest_fixture_live():
    """Ingest the 5-doc test fixture with REAL bge-m3 embeddings via
    the real ingest script as a subprocess."""
    r = subprocess.run(
        [sys.executable, "scripts/ingest_knowledge.py", "--file",
         str(KNOWLEDGE_FIXTURE), "--topic", "shelf_life"],
        cwd=str(REPO_ROOT), env=dict(os.environ),
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ingested=5" in r.stdout, r.stdout + r.stderr


# --- Gate E, deterministic tier (§7.3, §9) ---------------------------------

def test_search_top1_with_source_stubbed(db_engine, monkeypatch):
    from app.rag import search_knowledge

    assert ingest_fixture_stubbed(monkeypatch) == 0
    assert count_knowledge(db_engine) == 5
    assert count_knowledge(db_engine, "shelf_life") == 3
    assert count_knowledge(db_engine, "maintenance") == 2
    results = search_knowledge(BUTTER_QUERY, k=3)
    assert len(results) == 1, results
    top = results[0]
    assert top["title"] == BUTTER_TITLE
    assert top["source"].startswith(FOODKEEPER_SOURCE)
    assert top["content"].startswith("Butter: refrigerate")
    assert top["score"] == pytest.approx(1.0, abs=1e-6)


def test_search_no_match_returns_empty_stubbed(db_engine, monkeypatch):
    from app.rag import search_knowledge

    assert ingest_fixture_stubbed(monkeypatch) == 0
    assert search_knowledge(NONSENSE_QUERY, k=3) == []
    assert search_knowledge(
        "yesterday I dreamed about purple elephants", k=3) == []


def test_search_threshold_respected_stubbed(db_engine, monkeypatch):
    from app.rag import search_knowledge

    assert ingest_fixture_stubbed(monkeypatch) == 0
    # Similarity 0.34 < 0.35 -> excluded, even though it is the
    # nearest document.
    assert search_knowledge("THRESHOLD_BELOW butter", k=3) == []
    # Similarity 0.36 >= 0.35 -> kept, with the exact score.
    kept = search_knowledge("THRESHOLD_ABOVE butter", k=3)
    assert len(kept) == 1, kept
    assert kept[0]["title"] == BUTTER_TITLE
    assert kept[0]["score"] == pytest.approx(0.36, abs=1e-4)


def test_search_topic_filter_stubbed(db_engine, monkeypatch):
    from app.rag import search_knowledge

    assert ingest_fixture_stubbed(monkeypatch) == 0
    # No topic: both maintenance docs, nothing else above threshold.
    all_topics = search_knowledge(FILTER_QUERY, k=3)
    assert {r["title"] for r in all_topics} == {BEKO_TITLE, DAIKIN_TITLE}
    assert all(r["score"] == pytest.approx(math.sqrt(2) / 2, abs=1e-4)
               for r in all_topics)
    # topic=maintenance: same two docs.
    maint = search_knowledge(FILTER_QUERY, topic="maintenance", k=3)
    assert {r["title"] for r in maint} == {BEKO_TITLE, DAIKIN_TITLE}
    # topic=shelf_life: no shelf-life doc is close to a filter
    # question, so the filter restricts the answer to nothing.
    assert search_knowledge(FILTER_QUERY, topic="shelf_life", k=3) == []


def test_search_empty_query_raises(db_engine):
    from app.rag import search_knowledge

    with pytest.raises(ValueError):
        search_knowledge("   ")


def test_ingest_dedup_skips_second_run(db_engine, monkeypatch):
    assert ingest_fixture_stubbed(monkeypatch) == 0
    assert count_knowledge(db_engine) == 5
    # Same file again: app-level dedup (§7.3) skips every row.
    assert ingest_fixture_stubbed(monkeypatch) == 0
    assert count_knowledge(db_engine) == 5


def test_shelf_life_days_for_stubbed(db_engine, monkeypatch):
    import app.rag as rag_mod

    assert ingest_fixture_stubbed(monkeypatch) == 0
    # Butter passage: first "N days" range is "1-2 days" (room
    # temperature) -> lower bound 1, per the documented extraction
    # rule in app/rag.py (range -> lower bound, food-safety
    # conservative). No Qwen call is needed: the regex hits.
    found = rag_mod.shelf_life_days_for("butter")
    assert found is not None
    assert found["days"] == 1
    assert found["source"].startswith(FOODKEEPER_SOURCE)
    # No document above threshold -> no answer, never invented.
    assert rag_mod.shelf_life_days_for(NONSENSE_QUERY) is None


# --- Gate E, endpoint validation (§5.1) ------------------------------------

def test_knowledge_search_endpoint_validation(db_engine, monkeypatch):
    assert ingest_fixture_stubbed(monkeypatch) == 0
    headers = jwt_headers(db_engine)

    # No JWT -> 401.
    r = client.get("/api/v2/knowledge/search", params={"q": "butter"})
    assert r.status_code == 401, r.text
    # Missing q -> 400; empty q -> 400.
    r = client.get("/api/v2/knowledge/search", headers=headers)
    assert r.status_code == 400, r.text
    r = client.get("/api/v2/knowledge/search",
                   params={"q": "   "}, headers=headers)
    assert r.status_code == 400, r.text
    # Bad topic -> 400; k outside 1..10 -> 400.
    r = client.get("/api/v2/knowledge/search",
                   params={"q": "butter", "topic": "bogus"}, headers=headers)
    assert r.status_code == 400, r.text
    r = client.get("/api/v2/knowledge/search",
                   params={"q": "butter", "k": 0}, headers=headers)
    assert r.status_code == 400, r.text
    r = client.get("/api/v2/knowledge/search",
                   params={"q": "butter", "k": 11}, headers=headers)
    assert r.status_code == 400, r.text
    # Valid request -> 200 with the cited top-1 (stubbed embedder).
    r = client.get("/api/v2/knowledge/search",
                   params={"q": BUTTER_QUERY, "k": 3}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["title"] == BUTTER_TITLE
    assert body[0]["source"].startswith(FOODKEEPER_SOURCE)
    assert set(body[0]) == {"title", "source", "content", "score"}
    # k at the edges of the allowed range is accepted.
    r = client.get("/api/v2/knowledge/search",
                   params={"q": BUTTER_QUERY, "k": 1}, headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    r = client.get("/api/v2/knowledge/search",
                   params={"q": BUTTER_QUERY, "k": 10}, headers=headers)
    assert r.status_code == 200, r.text


# --- Gate E, live tier (real bge-m3; skipped without the GPU) -------------

def test_live_butter_top1_with_source(db_engine):
    _ollama_bge3_available()
    from app.rag import search_knowledge

    ingest_fixture_live()
    assert count_knowledge(db_engine) == 5
    results = search_knowledge(BUTTER_QUERY, k=3)
    assert results, "bge-m3 returned nothing above 0.35 for butter"
    top = results[0]
    assert top["title"] == BUTTER_TITLE
    assert top["source"].startswith(FOODKEEPER_SOURCE)
    assert top["score"] >= 0.35


def test_live_nonsense_returns_empty(db_engine):
    _ollama_bge3_available()
    from app.rag import search_knowledge

    ingest_fixture_live()
    assert search_knowledge(NONSENSE_QUERY, k=3) == []


def test_live_topic_filter_maintenance_only(db_engine):
    _ollama_bge3_available()
    from app.rag import search_knowledge

    ingest_fixture_live()
    maint = search_knowledge(FILTER_QUERY, topic="maintenance", k=3)
    assert {r["title"] for r in maint} == {BEKO_TITLE, DAIKIN_TITLE}
    shelf = search_knowledge(FILTER_QUERY, topic="shelf_life", k=3)
    assert all(r["title"] not in (BEKO_TITLE, DAIKIN_TITLE)
               for r in shelf)


def test_live_shelf_life_days_for_butter(db_engine):
    _ollama_bge3_available()
    import app.rag as rag_mod

    ingest_fixture_live()
    found = rag_mod.shelf_life_days_for("butter")
    assert found is not None
    assert found["days"] == 1
    assert found["source"].startswith(FOODKEEPER_SOURCE)


# --- Gate F: alias lookup, resolve order (§3.6, §6.3) ----------------------

def _fake_maps():
    water = {"id": uuid.uuid4(), "name": "Nước suối",
             "zone": "pantry", "shelf_life": 365}
    milk = {"id": uuid.uuid4(), "name": "Sữa tươi",
            "zone": "fridge", "shelf_life": 5}
    master = {"nướcsuối": water, "sữatươi": milk}
    return master, water, milk


def test_resolve_alias_prefix_beats_wrong_qwen_suggestion():
    master, water, milk = _fake_maps()
    # Printed line carries the size suffix "550ml"; the seeded alias
    # is the brand alone. The alias must still win over Qwen's WRONG
    # suggestion (Sữa tươi).
    assert resolve_canonical("农夫山泉 550ml", "Sữa tươi", master,
                             alias_map={"农夫山泉": water}) is water
    assert match_alias("农夫山泉 550ml", {"农夫山泉": water}) is water


def test_resolve_alias_exact_still_works():
    master, water, milk = _fake_maps()
    assert resolve_canonical("农夫山泉", "Sữa tươi", master,
                             alias_map={"农夫山泉": water}) is water


def test_resolve_alias_longest_prefix_wins():
    master, water, milk = _fake_maps()
    aliases = {"农夫": milk, "农夫山泉": water}
    assert resolve_canonical("农夫山泉 550ml", None, master,
                             alias_map=aliases) is water


def test_resolve_exact_canonical_first():
    master, water, milk = _fake_maps()
    assert resolve_canonical("Nước suối", "Sữa tươi", master,
                             alias_map={"农夫山泉": water}) is water


def test_resolve_unknown_brand_falls_through():
    master, water, milk = _fake_maps()
    # Unknown brand: not an alias, so it falls through to Qwen's
    # suggestion, and to unmatched when Qwen has none.
    assert resolve_canonical("娃哈哈纯净水", "Nước suối", master,
                             alias_map={"农夫山泉": water}) is water
    assert resolve_canonical("娃哈哈纯净水", None, master,
                             alias_map={"农夫山泉": water}) is None
    assert resolve_canonical("娃哈哈纯净水", "Không có", master,
                             alias_map={"农夫山泉": water}) is None


def test_worker_alias_wins_over_wrong_qwen_suggestion(
        db_engine, monkeypatch, worker_log):
    """Gate F (§9): the line "农夫山泉 550ml" maps to "Nước suối"
    via the seeded alias even though Qwen suggests a WRONG canonical
    (Sữa tươi). No live model is called: the parse is canned and the
    matched canonical has a seed shelf life, so RAG is not consulted
    either. The worker log records matched_via='alias'."""
    parsed = {
        "store_name": "Test", "purchased_at": "2026-11-20T09:00:00+08:00",
        "total_amount": 4.00, "currency": "CNY",
        "lines": [{"raw_name": "农夫山泉 550ml", "quantity": 1,
                   "unit": "瓶", "price": 4.00,
                   "canonical_name": "Sữa tươi", "is_stock_item": True}],
    }
    hid, rid, status = run_receipt_with_parse(monkeypatch, parsed)
    assert status == "completed"
    rows = inventory_for_receipt(db_engine, rid)
    assert len(rows) == 1, rows
    assert rows[0][0] == "农夫山泉 550ml"
    assert rows[0][3] == "Nước suối"
    text = worker_log_text(worker_log)
    assert "matched_via=alias" in text
    assert "raw='农夫山泉 550ml'" in text


def test_worker_alias_wins_when_qwen_suggests_nothing(
        db_engine, monkeypatch, worker_log):
    """Gate F, Qwen-absent variant: the alias resolves the line even
    when Qwen suggests no canonical at all."""
    parsed = {
        "store_name": "Test", "purchased_at": "2026-11-20T09:00:00+08:00",
        "total_amount": 4.00, "currency": "CNY",
        "lines": [{"raw_name": "农夫山泉 550ml", "quantity": 1,
                   "unit": "瓶", "price": 4.00,
                   "canonical_name": None, "is_stock_item": True}],
    }
    hid, rid, status = run_receipt_with_parse(monkeypatch, parsed)
    assert status == "completed"
    rows = inventory_for_receipt(db_engine, rid)
    assert len(rows) == 1
    assert rows[0][3] == "Nước suối"
    assert "matched_via=alias" in worker_log_text(worker_log)


def test_worker_unknown_brand_falls_through_to_qwen(
        db_engine, monkeypatch, worker_log):
    """Unknown brand is NOT an alias: it resolves via Qwen's
    suggestion (matched_via='qwen')."""
    parsed = {
        "store_name": "Test", "purchased_at": "2026-11-20T09:00:00+08:00",
        "total_amount": 4.00, "currency": "CNY",
        "lines": [{"raw_name": "娃哈哈纯净水", "quantity": 1,
                   "unit": "瓶", "price": 4.00,
                   "canonical_name": "Nước suối", "is_stock_item": True}],
    }
    hid, rid, status = run_receipt_with_parse(monkeypatch, parsed)
    assert status == "completed"
    rows = inventory_for_receipt(db_engine, rid)
    assert len(rows) == 1
    assert rows[0][3] == "Nước suối"
    assert "matched_via=qwen" in worker_log_text(worker_log)


def test_worker_unknown_brand_no_suggestion_stays_unmatched(
        db_engine, monkeypatch, worker_log):
    """Unknown brand with no Qwen suggestion stays unmatched
    (canonical NULL, +3 day fallback expiry)."""
    parsed = {
        "store_name": "Test", "purchased_at": "2026-11-20T09:00:00+08:00",
        "total_amount": 4.00, "currency": "CNY",
        "lines": [{"raw_name": "娃哈哈纯净水", "quantity": 1,
                   "unit": "瓶", "price": 4.00,
                   "canonical_name": None, "is_stock_item": True}],
    }
    hid, rid, status = run_receipt_with_parse(monkeypatch, parsed)
    assert status == "completed"
    rows = inventory_for_receipt(db_engine, rid)
    assert len(rows) == 1
    assert rows[0][1] is None  # canonical_ingredient_id
    assert rows[0][3] is None
    assert str(rows[0][2]) == str(today_shanghai() + timedelta(days=3))
    assert "matched_via=unmatched" in worker_log_text(worker_log)


# --- Shelf-life fallback order: seed > RAG > +3 (§7.3) ---------------------

def test_expiry_for_seed_beats_rag():
    canon = {"shelf_life": 5}
    added = today_shanghai()
    assert expiry_for(canon, added, rag_shelf_life_days=45) == \
        added + timedelta(days=5)


def test_expiry_for_rag_when_seed_null():
    canon = {"shelf_life": None}
    added = today_shanghai()
    assert expiry_for(canon, added, rag_shelf_life_days=45) == \
        added + timedelta(days=45)


def test_expiry_for_plus3_when_no_rag():
    canon = {"shelf_life": None}
    added = today_shanghai()
    assert expiry_for(canon, added, rag_shelf_life_days=None) == \
        added + timedelta(days=3)
    assert expiry_for(None, added, rag_shelf_life_days=45) == \
        added + timedelta(days=3)


def test_worker_seed_shelf_life_wins_over_rag(db_engine, monkeypatch):
    """Seed > RAG: "Thịt ba chỉ" has seed 3 days. The RAG lookup
    must not even be called, and expiry is added + 3."""
    import worker.main as worker_main

    calls = []

    def stub(name):
        calls.append(name)
        return {"days": 45, "source": "test", "content": "x"}

    monkeypatch.setattr(worker_main, "shelf_life_days_for", stub)
    parsed = {
        "store_name": "Test", "purchased_at": "2026-11-20T09:00:00+08:00",
        "total_amount": 20.00, "currency": "CNY",
        "lines": [{"raw_name": "Thịt ba chỉ", "quantity": 1,
                   "unit": "斤", "price": 20.00,
                   "canonical_name": "Thịt ba chỉ",
                   "is_stock_item": True}],
    }
    hid, rid, status = run_receipt_with_parse(monkeypatch, parsed)
    assert status == "completed"
    assert calls == []
    rows = inventory_for_receipt(db_engine, rid)
    assert len(rows) == 1
    added = today_shanghai()
    assert str(rows[0][2]) == str(added + timedelta(days=3))


def test_worker_rag_shelf_life_used_when_seed_null(db_engine, monkeypatch):
    """Seed NULL + RAG hit: expiry is added + RAG days (45)."""
    import worker.main as worker_main

    insert_null_shelf_ingredient(db_engine)
    monkeypatch.setattr(
        worker_main, "shelf_life_days_for",
        lambda name: {"days": 45, "source": "test", "content": "x"}
        if name == NULL_SHELF_INGREDIENT else None)
    parsed = {
        "store_name": "Test", "purchased_at": "2026-11-20T09:00:00+08:00",
        "total_amount": 10.00, "currency": "CNY",
        "lines": [{"raw_name": NULL_SHELF_INGREDIENT, "quantity": 1,
                   "unit": "盒", "price": 10.00,
                   "canonical_name": NULL_SHELF_INGREDIENT,
                   "is_stock_item": True}],
    }
    hid, rid, status = run_receipt_with_parse(monkeypatch, parsed)
    assert status == "completed"
    rows = inventory_for_receipt(db_engine, rid)
    assert len(rows) == 1
    assert rows[0][3] == NULL_SHELF_INGREDIENT
    added = today_shanghai()
    assert str(rows[0][2]) == str(added + timedelta(days=45))


def test_worker_no_rag_answer_falls_back_to_plus3(db_engine, monkeypatch):
    """Seed NULL + RAG no answer: expiry is added + 3."""
    import worker.main as worker_main

    insert_null_shelf_ingredient(db_engine)
    monkeypatch.setattr(worker_main, "shelf_life_days_for",
                        lambda name: None)
    parsed = {
        "store_name": "Test", "purchased_at": "2026-11-20T09:00:00+08:00",
        "total_amount": 10.00, "currency": "CNY",
        "lines": [{"raw_name": NULL_SHELF_INGREDIENT, "quantity": 1,
                   "unit": "盒", "price": 10.00,
                   "canonical_name": NULL_SHELF_INGREDIENT,
                   "is_stock_item": True}],
    }
    hid, rid, status = run_receipt_with_parse(monkeypatch, parsed)
    assert status == "completed"
    rows = inventory_for_receipt(db_engine, rid)
    assert len(rows) == 1
    added = today_shanghai()
    assert str(rows[0][2]) == str(added + timedelta(days=3))


def test_worker_rag_failure_falls_back_to_plus3(db_engine, monkeypatch):
    """Seed NULL + RAG lookup raising (Ollama down): the job still
    completes and expiry is added + 3 — RAG never fails the job."""
    import worker.main as worker_main

    insert_null_shelf_ingredient(db_engine)

    def failing_stub(name):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(worker_main, "shelf_life_days_for", failing_stub)
    parsed = {
        "store_name": "Test", "purchased_at": "2026-11-20T09:00:00+08:00",
        "total_amount": 10.00, "currency": "CNY",
        "lines": [{"raw_name": NULL_SHELF_INGREDIENT, "quantity": 1,
                   "unit": "盒", "price": 10.00,
                   "canonical_name": NULL_SHELF_INGREDIENT,
                   "is_stock_item": True}],
    }
    hid, rid, status = run_receipt_with_parse(monkeypatch, parsed)
    assert status == "completed"
    rows = inventory_for_receipt(db_engine, rid)
    assert len(rows) == 1
    added = today_shanghai()
    assert str(rows[0][2]) == str(added + timedelta(days=3))
