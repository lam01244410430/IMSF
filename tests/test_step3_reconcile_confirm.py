"""Step 3 tests: §6.4 reconciliation, canonical mapping, confirm (§5.1).

Runs against the disposable ``imsf_v2_test`` database (same pattern as
the Step 1/2 test files) so the dev DB is never touched. The worker is
exercised via ``process_job`` called directly, with the Qwen parse
monkeypatched to a canned §6.3 dict loaded from the Step 3 fixture
ground-truth JSONs — the real model is verified by the live curl
gates, not by pytest. The confirm endpoint is exercised over HTTP
via the TestClient.
"""

import json
import os
import time
import uuid
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
import sqlalchemy as sa
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"

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

from app.main import app  # noqa: E402
from app.reconcile import check_reconciliation, resolve_canonical  # noqa: E402

client = TestClient(app)
SERVICE_HEADERS = {
    "Authorization": f"Bearer {os.environ['IMSF_V2_SERVICE_TOKEN']}"
}


def load_fixture(name: str) -> dict:
    """Ground-truth JSON doubles as the canned §6.3 parse dict."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


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
            "TRUNCATE inventory_items, receipt_lines, receipts,"
            " household_members, households, users RESTART IDENTITY CASCADE"))
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(test_db):
    yield test_db
    with test_db.begin() as conn:
        conn.execute(text(
            "TRUNCATE inventory_items, receipt_lines, receipts,"
            " household_members, households, users RESTART IDENTITY CASCADE"))


def mk_household(name="Test Home"):
    r = client.post("/api/v2/households", json={"name": name},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def upload_image(household_id, png_name):
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


def run_receipt(monkeypatch, fixture_name, png_name=None):
    """Upload a fixture image and run the worker on it with a canned
    Qwen parse (the fixture's ground truth). Returns (receipt_id, status).
    """
    import worker.main as worker_main

    monkeypatch.setenv("OCR_PROVIDER", "mock")
    parsed = load_fixture(fixture_name)
    monkeypatch.setattr(worker_main, "parse_receipt_text",
                        lambda *a, **k: json.loads(json.dumps(parsed)))
    hid = mk_household()
    rid = upload_image(hid, png_name or f"{fixture_name}.png")
    job = pop_job()
    assert job["receipt_id"] == rid
    return rid, worker_main.process_job(job)


def get_detail(rid):
    r = client.get(f"/api/v2/receipts/{rid}", headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


# --- §6.4 reconciliation unit tests (design examples, Decimal-exact) -----

def test_reconcile_116pct_off_passes():
    # §6.4 example: total 86.50, lines 85.50 -> 1.16% <= 2% -> pass.
    ok, msg = check_reconciliation(Decimal("85.50"), Decimal("86.50"))
    assert ok is True
    assert msg is None


def test_reconcile_289pct_off_fails():
    # §6.4 example: total 86.50, lines 84.00 -> 2.89% > 2% -> fail.
    ok, msg = check_reconciliation(Decimal("84.00"), Decimal("86.50"))
    assert ok is False
    assert "2.89%" in msg
    assert "tổng dòng lệch" in msg


def test_reconcile_exactly_2pct_passes():
    # Rule is STRICTLY greater than: exactly 2.00% passes.
    ok, msg = check_reconciliation(Decimal("98.00"), Decimal("100.00"))
    assert ok is True
    assert msg is None
    ok, msg = check_reconciliation(Decimal("102.00"), Decimal("100.00"))
    assert ok is True
    assert msg is None


def test_reconcile_null_total_needs_review():
    ok, msg = check_reconciliation(Decimal("56.10"), None)
    assert ok is False
    assert msg == "không đọc được tổng tiền"


def test_reconcile_zero_total_needs_review():
    ok, msg = check_reconciliation(Decimal("56.10"), Decimal("0"))
    assert ok is False
    assert msg == "không đọc được tổng tiền"
    ok, msg = check_reconciliation(Decimal("56.10"), Decimal("-5"))
    assert ok is False
    assert msg == "không đọc được tổng tiền"


# --- canonical mapping order (task 1) --------------------------------------

def _master_map():
    return {
        "gạo": {"id": uuid.uuid4(), "name": "Gạo", "zone": "pantry",
                "shelf_life": 180},
        "trứnggà": {"id": uuid.uuid4(), "name": "Trứng gà",
                    "zone": "fridge", "shelf_life": 21},
    }


def test_resolve_canonical_raw_exact_match_first():
    m = _master_map()
    # (a) the printed raw_name itself is a canonical name.
    assert resolve_canonical("Gạo", None, m)["name"] == "Gạo"
    # (a) wins over (b): raw matches even when Qwen suggested otherwise.
    assert resolve_canonical("Gạo", "Trứng gà", m)["name"] == "Gạo"


def test_resolve_canonical_suggested_match():
    m = _master_map()
    # (b) Qwen's suggestion, normalised (whitespace/case-insensitive).
    got = resolve_canonical("鸡蛋", " Trứng  Gà ", m)
    assert got is not None and got["name"] == "Trứng gà"


def test_resolve_canonical_unmatched_is_none():
    m = _master_map()
    # (c) neither the raw name nor the suggestion is in master.
    assert resolve_canonical("可口可乐 330ml", None, m) is None
    assert resolve_canonical("可口可乐 330ml", "Coca-Cola", m) is None


# --- worker: mapping + reconciliation through process_job -------------------

def test_worker_unmatched_line_stays_null(db_engine, monkeypatch):
    rid, status = run_receipt(monkeypatch, "step3_c_unmatched")
    assert status == "completed"
    d = get_detail(rid)
    assert d["status"] == "completed"
    assert len(d["lines"]) == 3
    coke = [ln for ln in d["lines"] if "可口可乐" in ln["raw_name"]]
    assert len(coke) == 1
    assert coke[0]["canonical_ingredient_id"] is None
    assert coke[0]["canonical_name"] is None
    matched = sum(1 for ln in d["lines"]
                  if ln["canonical_ingredient_id"] is not None)
    unmatched = sum(1 for ln in d["lines"]
                    if ln["canonical_ingredient_id"] is None)
    assert (matched, unmatched) == (2, 1)
    assert d["inventory_created"] == 3  # incl. the unmatched line


def test_worker_null_total_needs_review(db_engine, monkeypatch):
    import worker.main as worker_main

    monkeypatch.setenv("OCR_PROVIDER", "mock")
    parsed = load_fixture("step3_a_yonghui")
    parsed["total_amount"] = None
    monkeypatch.setattr(worker_main, "parse_receipt_text",
                        lambda *a, **k: json.loads(json.dumps(parsed)))
    hid = mk_household()
    rid = upload_image(hid, "step3_a_yonghui.png")
    job = pop_job()
    assert worker_main.process_job(job) == "needs_review"
    d = get_detail(rid)
    assert d["status"] == "needs_review"
    assert d["error_message"] == "không đọc được tổng tiền"
    assert d["total_amount"] == 0.00  # upload-time placeholder kept
    assert len(d["lines"]) == 4  # lines ARE persisted for correction
    assert d["inventory_created"] == 0
    assert d["processed_at"] is not None  # end of processing, not success


def test_worker_mismatch_needs_review(db_engine, monkeypatch):
    rid, status = run_receipt(monkeypatch, "step3_e_mismatch")
    assert status == "needs_review"
    d = get_detail(rid)
    assert d["status"] == "needs_review"
    assert "5.00%" in d["error_message"]
    assert d["total_amount"] == 100.00
    lines_sum = sum(ln["price"] for ln in d["lines"])
    assert lines_sum == 95.00
    assert len(d["lines"]) == 5
    assert d["inventory_created"] == 0
    assert d["processed_at"] is not None


def test_worker_discount_line_counts_in_sum(db_engine, monkeypatch):
    rid, status = run_receipt(monkeypatch, "step3_b_hema")
    assert status == "completed"
    d = get_detail(rid)
    assert d["status"] == "completed"
    assert d["total_amount"] == 19.40
    assert len(d["lines"]) == 3
    disc = [ln for ln in d["lines"] if ln["price"] < 0]
    assert len(disc) == 1
    assert disc[0]["is_stock_item"] is False
    assert disc[0]["price"] == -5.00
    # Discount line counts in the 2% sum but creates no inventory.
    assert d["inventory_created"] == 2


# --- confirm endpoint (§5.1, §5.4) ------------------------------------------

def _confirm_body_from_detail(detail, price_overrides=None):
    lines = []
    for ln in detail["lines"]:
        price = (price_overrides or {}).get(ln["raw_name"], ln["price"])
        lines.append({"line_id": ln["id"], "quantity": ln["quantity"],
                      "unit": ln["unit"], "price": price,
                      "is_stock_item": ln["is_stock_item"]})
    return {"lines": lines}


def test_confirm_fixes_mismatch_then_second_confirm_409(db_engine, monkeypatch):
    rid, status = run_receipt(monkeypatch, "step3_e_mismatch")
    assert status == "needs_review"
    d = get_detail(rid)
    # Fix one line price so the lines sum (100.00) matches the total.
    body = _confirm_body_from_detail(d, {"食盐": 13.80})
    r = client.post(f"/api/v2/receipts/{rid}/confirm", json=body,
                    headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    d2 = r.json()
    assert d2["status"] == "completed"
    assert d2["error_message"] is None
    assert d2["inventory_created"] == 5
    assert sum(ln["price"] for ln in d2["lines"]) == 100.00
    salt = [ln for ln in d2["lines"] if ln["raw_name"] == "食盐"][0]
    assert salt["price"] == 13.80
    # Second confirm on the now-completed receipt -> 409.
    r2 = client.post(f"/api/v2/receipts/{rid}/confirm", json=body,
                     headers=SERVICE_HEADERS)
    assert r2.status_code == 409, r2.text


def test_confirm_still_off_stays_needs_review(db_engine, monkeypatch):
    rid, status = run_receipt(monkeypatch, "step3_e_mismatch")
    assert status == "needs_review"
    d = get_detail(rid)
    # 96.00 vs 100.00 = 4.00% off -> still needs_review, lines saved.
    body = _confirm_body_from_detail(d, {"食盐": 9.80})
    r = client.post(f"/api/v2/receipts/{rid}/confirm", json=body,
                    headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    d2 = r.json()
    assert d2["status"] == "needs_review"
    assert "4.00%" in d2["error_message"]
    assert d2["inventory_created"] == 0
    salt = [ln for ln in d2["lines"] if ln["raw_name"] == "食盐"][0]
    assert salt["price"] == 9.80
    assert d2["processed_at"] is not None


def test_confirm_on_completed_receipt_409(db_engine, monkeypatch):
    rid, status = run_receipt(monkeypatch, "step3_a_yonghui")
    assert status == "completed"
    d = get_detail(rid)
    body = _confirm_body_from_detail(d)
    r = client.post(f"/api/v2/receipts/{rid}/confirm", json=body,
                    headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text


def test_confirm_validation_422(db_engine, monkeypatch):
    rid, status = run_receipt(monkeypatch, "step3_e_mismatch")
    assert status == "needs_review"
    d = get_detail(rid)
    base = _confirm_body_from_detail(d)
    # quantity <= 0 -> 422.
    bad = {"lines": [dict(base["lines"][0], quantity=0)]}
    assert client.post(f"/api/v2/receipts/{rid}/confirm", json=bad,
                       headers=SERVICE_HEADERS).status_code == 422
    # line_id not part of this receipt -> 422.
    bad = {"lines": [dict(base["lines"][0], line_id=str(uuid.uuid4()))]}
    assert client.post(f"/api/v2/receipts/{rid}/confirm", json=bad,
                       headers=SERVICE_HEADERS).status_code == 422
    # negative price on a stock line -> 422.
    bad = {"lines": [dict(base["lines"][0], price=-1.00)]}
    assert client.post(f"/api/v2/receipts/{rid}/confirm", json=bad,
                       headers=SERVICE_HEADERS).status_code == 422
    # ... but a negative price IS allowed on a non-stock line.
    disc = {"lines": [dict(base["lines"][0], price=-1.00,
                           is_stock_item=False)]}
    r = client.post(f"/api/v2/receipts/{rid}/confirm", json=disc,
                    headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "needs_review"  # sum now 94.00 vs 100


def test_confirm_missing_receipt_404(db_engine):
    body = {"lines": [{"line_id": str(uuid.uuid4()), "quantity": 1,
                       "unit": "袋", "price": 1.00, "is_stock_item": True}]}
    r = client.post(f"/api/v2/receipts/{uuid.uuid4()}/confirm", json=body,
                    headers=SERVICE_HEADERS)
    assert r.status_code == 404, r.text
