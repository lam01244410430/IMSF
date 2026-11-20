"""Phase 2 Step 2 tests: spending ledger (design §3.1, §5.1, §5.3, §9 Gate A).

Runs against the disposable ``imsf_v2_test`` database (same pattern as
the Step 1/2/3 test files) so the dev DB is never touched. The worker
is exercised via ``process_job`` called directly, with the Qwen parse
monkeypatched to a canned §6.3 dict — the real model is verified by
the live curl gates, not by pytest. The transactions/summary API is
exercised over HTTP via the TestClient.
"""

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import jwt
import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

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

client = TestClient(app)
SERVICE_HEADERS = {
    "Authorization": f"Bearer {os.environ['IMSF_V2_SERVICE_TOKEN']}"
}

CANNED_PARSED = {
    "store_name": "永辉超市",
    "purchased_at": "2026-11-20T09:12:00+08:00",
    "total_amount": 56.10,
    "currency": "CNY",
    "lines": [
        {"raw_name": "农夫山泉 550ml", "quantity": 2, "unit": "瓶",
         "price": 4.00, "canonical_name": "Nước suối", "is_stock_item": True},
        {"raw_name": "鸡蛋", "quantity": 1, "unit": "盒",
         "price": 12.80, "canonical_name": "Trứng gà", "is_stock_item": True},
        {"raw_name": "大米 5kg", "quantity": 1, "unit": "袋",
         "price": 32.50, "canonical_name": "Gạo", "is_stock_item": True},
        {"raw_name": "青菜", "quantity": 1, "unit": "斤",
         "price": 6.80, "canonical_name": "Rau cải", "is_stock_item": True},
    ],
}


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
            "TRUNCATE transactions, inventory_items, receipt_lines,"
            " receipts, household_members, households, users"
            " RESTART IDENTITY CASCADE"))
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(test_db):
    yield test_db
    with test_db.begin() as conn:
        conn.execute(text(
            "TRUNCATE transactions, inventory_items, receipt_lines,"
            " receipts, household_members, households, users"
            " RESTART IDENTITY CASCADE"))


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


def run_receipt(monkeypatch, parsed=None, png_name="synthetic_receipt.png"):
    """Upload + run the worker with a canned Qwen parse. Returns
    (household_id, receipt_id, status, job)."""
    import worker.main as worker_main

    monkeypatch.setenv("OCR_PROVIDER", "mock")
    parsed = parsed if parsed is not None else CANNED_PARSED
    monkeypatch.setattr(worker_main, "parse_receipt_text",
                        lambda *a, **k: json.loads(json.dumps(parsed)))
    hid = mk_household()
    rid = upload_image(hid, png_name)
    job = pop_job()
    assert job["receipt_id"] == rid
    return hid, rid, worker_main.process_job(job), job


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _confirm_body_from_detail(detail, price_overrides=None):
    lines = []
    for ln in detail["lines"]:
        price = (price_overrides or {}).get(ln["raw_name"], ln["price"])
        lines.append({"line_id": ln["id"], "quantity": ln["quantity"],
                      "unit": ln["unit"], "price": price,
                      "is_stock_item": ln["is_stock_item"]})
    return {"lines": lines}


def get_receipt_detail(rid):
    r = client.get(f"/api/v2/receipts/{rid}", headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def list_transactions(hid, **params):
    r = client.get("/api/v2/transactions",
                   params={"household_id": hid, **params},
                   headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def count_receipt_transactions(db_engine, rid):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM transactions WHERE receipt_id=:rid"),
            {"rid": uuid.UUID(rid)},
        ).scalar_one()


def other_user_headers(db_engine):
    """A JWT for a user with no membership in any household."""
    other_user = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone, name)"
                 " VALUES (:id, :p, 'Other')"),
            {"id": other_user, "p": "13800009999"},
        )
    token = jwt.encode(
        {"sub": str(other_user), "typ": "access"},
        os.environ["JWT_SECRET"], algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# --- Gate A: one transaction per receipt -----------------------------------

def test_worker_completed_creates_exactly_one_transaction(db_engine, monkeypatch):
    hid, rid, status, _job = run_receipt(monkeypatch)
    assert status == "completed"
    assert count_receipt_transactions(db_engine, rid) == 1
    rows = list_transactions(hid)
    assert len(rows) == 1
    txn = rows[0]
    assert txn["receipt_id"] == rid
    assert txn["type"] == "expense"
    assert txn["amount"] == 56.10
    assert txn["currency"] == "CNY"
    assert txn["category"] == "food"
    assert datetime.fromisoformat(txn["occurred_at"]) == datetime.fromisoformat(
        "2026-11-20T09:12:00+08:00")


def test_receipt_transaction_duplicate_blocked(db_engine, monkeypatch):
    hid, rid, status, job = run_receipt(monkeypatch)
    assert status == "completed"
    assert count_receipt_transactions(db_engine, rid) == 1
    # A second INSERT with the same receipt_id is blocked by the
    # partial unique index ux_transactions_receipt (§3.1).
    with pytest.raises(IntegrityError):
        with db_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO transactions (household_id, receipt_id,"
                     " type, amount, currency, category, occurred_at)"
                     " VALUES (:h, :rid, 'expense', 56.10, 'CNY', 'food',"
                     " now())"),
                {"h": uuid.UUID(hid), "rid": uuid.UUID(rid)},
            )
    # Re-running the worker on the already-completed receipt is a
    # no-op (it is skipped, not re-processed) — still exactly 1 row.
    import worker.main as worker_main
    assert worker_main.process_job(job) == "completed"
    assert count_receipt_transactions(db_engine, rid) == 1


def test_needs_review_creates_no_transaction(db_engine, monkeypatch):
    parsed = load_fixture("step3_e_mismatch")
    hid, rid, status, _job = run_receipt(monkeypatch, parsed=parsed,
                                         png_name="step3_e_mismatch.png")
    assert status == "needs_review"
    assert count_receipt_transactions(db_engine, rid) == 0


def test_confirm_completed_creates_transaction(db_engine, monkeypatch):
    parsed = load_fixture("step3_e_mismatch")
    hid, rid, status, _job = run_receipt(monkeypatch, parsed=parsed,
                                         png_name="step3_e_mismatch.png")
    assert status == "needs_review"
    assert count_receipt_transactions(db_engine, rid) == 0
    d = get_receipt_detail(rid)
    body = _confirm_body_from_detail(d, {"食盐": 13.80})
    r = client.post(f"/api/v2/receipts/{rid}/confirm", json=body,
                    headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert count_receipt_transactions(db_engine, rid) == 1
    rows = list_transactions(hid)
    assert len(rows) == 1
    txn = rows[0]
    assert txn["receipt_id"] == rid
    assert txn["type"] == "expense"
    assert txn["amount"] == 100.00
    assert txn["currency"] == d["currency"]
    assert txn["category"] == "food"


# --- Manual transactions: CRUD ---------------------------------------------

def test_manual_transaction_crud(db_engine):
    hid = mk_household()
    # Create 3 manual rows with distinct dates (newest first on list).
    def create(**kw):
        body = {"household_id": hid, "type": "expense", "amount": 10.00,
                "currency": "CNY", "category": "food",
                "occurred_at": "2026-11-10T10:00:00+08:00"}
        body.update(kw)
        r = client.post("/api/v2/transactions", json=body,
                        headers=SERVICE_HEADERS)
        assert r.status_code == 201, r.text
        return r.json()

    t_food = create()
    t_income = create(type="income", amount=50.00, category="other",
                      occurred_at="2026-11-11T10:00:00+08:00")
    t_house = create(amount=20.00, category="household",
                     occurred_at="2026-11-12T10:00:00+08:00")
    assert t_food["receipt_id"] is None
    assert t_income["type"] == "income"

    rows = list_transactions(hid)
    assert [x["id"] for x in rows] == [t_house["id"], t_income["id"],
                                       t_food["id"]]

    # PATCH: amount + note on the household row.
    r = client.patch(f"/api/v2/transactions/{t_house['id']}",
                     json={"amount": 25.00, "note": "mua đồ dùng"},
                     headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 25.00
    assert r.json()["note"] == "mua đồ dùng"
    assert r.json()["category"] == "household"

    # DELETE the income row -> 204, then it is gone from the list.
    r = client.delete(f"/api/v2/transactions/{t_income['id']}",
                      headers=SERVICE_HEADERS)
    assert r.status_code == 204, r.text
    rows = list_transactions(hid)
    assert [x["id"] for x in rows] == [t_house["id"], t_food["id"]]

    # receipt_id is never accepted from the client (§5.1).
    r = client.post("/api/v2/transactions",
                    json={"household_id": hid, "type": "expense",
                          "amount": 5.00, "currency": "CNY",
                          "category": "food",
                          "occurred_at": "2026-11-13T10:00:00+08:00",
                          "receipt_id": str(uuid.uuid4())},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 422, r.text


def test_patch_delete_receipt_transaction_409(db_engine, monkeypatch):
    hid, rid, status, _job = run_receipt(monkeypatch)
    assert status == "completed"
    txn = list_transactions(hid)[0]
    assert txn["receipt_id"] == rid
    r = client.patch(f"/api/v2/transactions/{txn['id']}",
                     json={"amount": 1.00}, headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text
    r = client.delete(f"/api/v2/transactions/{txn['id']}",
                      headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text
    # Still exactly 1 row, unchanged.
    assert count_receipt_transactions(db_engine, rid) == 1
    assert list_transactions(hid)[0]["amount"] == 56.10


def test_manual_transaction_validation(db_engine):
    hid = mk_household()
    base = {"household_id": hid, "type": "expense", "amount": 10.00,
            "currency": "CNY", "category": "food",
            "occurred_at": "2026-11-10T10:00:00+08:00"}

    def post(**overrides):
        body = dict(base)
        body.update(overrides)
        return client.post("/api/v2/transactions", json=body,
                           headers=SERVICE_HEADERS)

    assert post(amount=0).status_code == 422
    assert post(amount=-5).status_code == 422
    assert post(currency="USD").status_code == 422
    assert post(category="travel").status_code == 422
    assert post(type="transfer").status_code == 422
    body = dict(base)
    del body["occurred_at"]
    assert client.post("/api/v2/transactions", json=body,
                       headers=SERVICE_HEADERS).status_code == 422
    # PATCH with nothing to update -> 400.
    txn = post().json()
    assert client.patch(f"/api/v2/transactions/{txn['id']}", json={},
                        headers=SERVICE_HEADERS).status_code == 400
    # PATCH with an invalid category -> 422.
    assert client.patch(f"/api/v2/transactions/{txn['id']}",
                        json={"category": "travel"},
                        headers=SERVICE_HEADERS).status_code == 422
    # Unknown transaction id -> 404.
    assert client.patch(f"/api/v2/transactions/{uuid.uuid4()}",
                        json={"amount": 1.00},
                        headers=SERVICE_HEADERS).status_code == 404
    assert client.delete(f"/api/v2/transactions/{uuid.uuid4()}",
                         headers=SERVICE_HEADERS).status_code == 404


# --- Spending summary (§5.3) ------------------------------------------------

def _seed_summary_data(db_engine, monkeypatch):
    """Completed CNY receipt (56.10 food) + manual rows. Returns hid."""
    hid, rid, status, _job = run_receipt(monkeypatch)
    assert status == "completed"

    def create(**kw):
        body = {"household_id": hid, "type": "expense", "amount": 10.00,
                "currency": "CNY", "category": "food",
                "occurred_at": "2026-11-10T10:00:00+08:00"}
        body.update(kw)
        r = client.post("/api/v2/transactions", json=body,
                        headers=SERVICE_HEADERS)
        assert r.status_code == 201, r.text
        return r.json()

    create(amount=100.00, category="household",
           occurred_at="2026-11-15T10:00:00+08:00")
    # Income is excluded from the expense summary (§5.3).
    create(type="income", amount=500.00, category="other",
           occurred_at="2026-11-16T10:00:00+08:00")
    create(amount=200000, currency="VND", category="food",
           occurred_at="2026-11-17T10:00:00+08:00")
    return hid


def _summary(hid, currency):
    r = client.get("/api/v2/spending/summary",
                   params={"household_id": hid, "currency": currency,
                           "from": "2026-11-01T00:00:00+08:00",
                           "to": "2026-12-01T00:00:00+08:00"},
                   headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def test_spending_summary_per_currency(db_engine, monkeypatch):
    hid = _seed_summary_data(db_engine, monkeypatch)
    cny = _summary(hid, "CNY")
    assert cny["currency"] == "CNY"
    assert cny["total"] == 156.10  # 56.10 receipt + 100.00 household
    assert {x["category"]: x["total"] for x in cny["by_category"]} == {
        "food": 56.10, "household": 100.00}
    assert cny["by_month"] == [{"month": "2026-11", "total": 156.10}]
    vnd = _summary(hid, "VND")
    assert vnd["currency"] == "VND"
    assert vnd["total"] == 200000
    assert vnd["by_category"] == [{"category": "food", "total": 200000}]
    assert vnd["by_month"] == [{"month": "2026-11", "total": 200000}]
    # Totals match direct SQL SUM per currency (§9 Gate A).
    with db_engine.connect() as conn:
        for cur, expected in (("CNY", 156.10), ("VND", 200000)):
            got = conn.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM transactions"
                     " WHERE household_id=:h AND currency=:cur"
                     " AND type='expense'"),
                {"h": uuid.UUID(hid), "cur": cur},
            ).scalar_one()
            assert float(got) == expected, (cur, got)


def test_spending_summary_missing_currency_400(db_engine, monkeypatch):
    hid = _seed_summary_data(db_engine, monkeypatch)
    r = client.get("/api/v2/spending/summary",
                   params={"household_id": hid,
                           "from": "2026-11-01T00:00:00+08:00",
                           "to": "2026-12-01T00:00:00+08:00"},
                   headers=SERVICE_HEADERS)
    assert r.status_code == 400, r.text
    # Bad group_by -> 400; bad date -> 400.
    r = client.get("/api/v2/spending/summary",
                   params={"household_id": hid, "currency": "CNY",
                           "group_by": "day"}, headers=SERVICE_HEADERS)
    assert r.status_code == 400, r.text
    r = client.get("/api/v2/spending/summary",
                   params={"household_id": hid, "currency": "CNY",
                           "from": "not-a-date"}, headers=SERVICE_HEADERS)
    assert r.status_code == 400, r.text


def test_spending_summary_date_range(db_engine, monkeypatch):
    hid = _seed_summary_data(db_engine, monkeypatch)
    # Only 2026-11-10..11-16 is inside this window: the 100.00
    # household expense (11-15) and the 500.00 income (excluded).
    r = client.get("/api/v2/spending/summary",
                   params={"household_id": hid, "currency": "CNY",
                           "from": "2026-11-10T00:00:00+08:00",
                           "to": "2026-11-16T00:00:00+08:00"},
                   headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 100.00
    assert r.json()["by_category"] == [{"category": "household",
                                         "total": 100.00}]


# --- Household scoping: 403 (§5.4) ------------------------------------------

def test_transactions_403_other_household(db_engine, monkeypatch):
    hid, rid, status, _job = run_receipt(monkeypatch)
    assert status == "completed"
    txn = list_transactions(hid)[0]
    other = other_user_headers(db_engine)
    # List + summary for a household that is not the caller's -> 403.
    assert client.get("/api/v2/transactions",
                      params={"household_id": hid},
                      headers=other).status_code == 403
    assert client.get("/api/v2/spending/summary",
                      params={"household_id": hid, "currency": "CNY"},
                      headers=other).status_code == 403
    # PATCH / DELETE someone else's transaction -> 403.
    assert client.patch(f"/api/v2/transactions/{txn['id']}",
                        json={"amount": 1.00},
                        headers=other).status_code == 403
    assert client.delete(f"/api/v2/transactions/{txn['id']}",
                         headers=other).status_code == 403
    # A household id that belongs to nobody -> 403 as well.
    assert client.get("/api/v2/transactions",
                      params={"household_id": str(uuid.uuid4())},
                      headers=SERVICE_HEADERS).status_code == 403
    # The receipt transaction is untouched.
    assert count_receipt_transactions(db_engine, rid) == 1
