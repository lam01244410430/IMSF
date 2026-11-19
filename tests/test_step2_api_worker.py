"""Step 2 tests: API (§5, except confirm) + worker (§6, minus 2% check).

Runs against a disposable ``imsf_v2_test`` database (same pattern as
test_db_constraints) so the dev DB is never touched. The worker is
exercised two ways: ``process_job`` called directly (with the Qwen
parse monkeypatched to a canned §6.3 dict — the real model is verified
by the live curl gates, not by pytest), and once as a real subprocess
to prove a bad job fails the receipt without killing the worker.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import jwt
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

client = TestClient(app)
# The token the app actually checks is read from the env at request time;
# keep the header in sync if the env already had a real token.
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


def upload_fixture(household_id, idem_key=None):
    headers = dict(SERVICE_HEADERS)
    if idem_key:
        headers["Idempotency-Key"] = idem_key
    with open(FIXTURES / "synthetic_receipt.png", "rb") as fh:
        r = client.post(
            "/api/v2/receipts",
            data={"household_id": household_id},
            files={"image": ("synthetic_receipt.png", fh, "image/png")},
            headers=headers)
    return r


# --- API + worker happy path (mock OCR, stubbed Qwen parse) ---------------

def test_upload_mock_completed(db_engine, monkeypatch):
    import worker.main as worker_main

    monkeypatch.setenv("OCR_PROVIDER", "mock")
    monkeypatch.setattr(worker_main, "parse_receipt_text",
                        lambda *a, **k: json.loads(json.dumps(CANNED_PARSED)))
    hid = mk_household()
    r = upload_fixture(hid)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "pending"
    rid = r.json()["id"]

    # The API pushed a job; process it synchronously like the worker would.
    # Retry the pop briefly: a live worker must not be running during
    # pytest (it would steal the job) — see the re-run procedure in the
    # night-shift log — but tolerate scheduling jitter.
    from app.db import get_redis
    job = None
    for _ in range(30):
        raw = get_redis().lpop("imsf-v2:receipt-jobs")
        if raw:
            job = json.loads(raw)
            break
        time.sleep(0.5)
    assert job is not None, "no job on imsf-v2:receipt-jobs after upload"
    assert job["receipt_id"] == rid
    assert worker_main.process_job(job) == "completed"

    detail = client.get(f"/api/v2/receipts/{rid}", headers=SERVICE_HEADERS)
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d["status"] == "completed"
    assert d["store_name"] == "永辉超市"
    assert d["total_amount"] == 56.10
    assert d["processed_at"] is not None
    assert len(d["lines"]) == 4
    assert d["inventory_created"] == 4
    names = [ln["raw_name"] for ln in d["lines"]]
    assert names == ["农夫山泉 550ml", "鸡蛋", "大米 5kg", "青菜"]
    assert d["lines"][0]["canonical_name"] == "Nước suối"
    assert all(ln["is_stock_item"] for ln in d["lines"])

    # Expiry: seed shelf lives (Nước suối 365, Trứng gà 21, Gạo 180,
    # Rau cải 4) from the added date (Asia/Shanghai today).
    today = __import__("datetime").datetime.now(
        ZoneInfo("Asia/Shanghai")).date()
    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT raw_name, auto_expiry_date, storage_zone"
                 " FROM inventory_items WHERE receipt_id=:rid"
                 " ORDER BY created_at"),
            {"rid": uuid.UUID(rid)},
        ).all()
    assert len(rows) == 4
    expected = {"农夫山泉 550ml": 365, "鸡蛋": 21, "大米 5kg": 180, "青菜": 4}
    for raw, expiry, zone in rows:
        assert expiry == today + timedelta(days=expected[raw]), (raw, expiry)
    assert {z for _, _, z in rows} == {"fridge", "pantry"}

    # List + status filter.
    lst = client.get("/api/v2/receipts",
                     params={"household_id": hid, "status": "completed"},
                     headers=SERVICE_HEADERS)
    assert lst.status_code == 200
    assert [x["id"] for x in lst.json()] == [rid]
    lst2 = client.get("/api/v2/receipts",
                      params={"household_id": hid, "status": "failed"},
                      headers=SERVICE_HEADERS)
    assert lst2.json() == []


def test_idempotency(db_engine):
    hid = mk_household()
    key = f"test-{uuid.uuid4()}"
    r1 = upload_fixture(hid, idem_key=key)
    r2 = upload_fixture(hid, idem_key=key)
    assert r1.status_code == 202 and r2.status_code == 202
    assert r1.json()["id"] == r2.json()["id"]
    with db_engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM receipts WHERE household_id=:h"),
            {"h": uuid.UUID(hid)},
        ).scalar_one()
    assert n == 1


def test_image_403_other_household(db_engine):
    hid = mk_household()
    r = upload_fixture(hid)
    rid = r.json()["id"]
    # A different user (JWT) with no membership in this household.
    other_user = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone, name) VALUES (:id, :p, 'Other')"),
            {"id": other_user, "p": "13800009999"},
        )
    token = jwt.encode(
        {"sub": str(other_user), "typ": "access"},
        os.environ["JWT_SECRET"], algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/v2/receipts/{rid}/image",
                      headers=headers).status_code == 403
    assert client.get(f"/api/v2/receipts/{rid}",
                      headers=headers).status_code == 403
    # Same household can view the image.
    img = client.get(f"/api/v2/receipts/{rid}/image", headers=SERVICE_HEADERS)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    # Missing receipt -> 404.
    assert client.get(f"/api/v2/receipts/{uuid.uuid4()}",
                      headers=SERVICE_HEADERS).status_code == 404


def test_upload_validation(db_engine):
    hid = mk_household()
    # No token -> 401.
    with open(FIXTURES / "synthetic_receipt.png", "rb") as fh:
        r = client.post("/api/v2/receipts", data={"household_id": hid},
                        files={"image": ("x.png", fh, "image/png")})
    assert r.status_code == 401
    # Wrong extension -> 400.
    r = client.post("/api/v2/receipts", data={"household_id": hid},
                    files={"image": ("x.txt", b"hello", "text/plain")},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 400
    # Household that is not the caller's -> 400.
    with open(FIXTURES / "synthetic_receipt.png", "rb") as fh:
        r = client.post("/api/v2/receipts",
                        data={"household_id": str(uuid.uuid4())},
                        files={"image": ("x.png", fh, "image/png")},
                        headers=SERVICE_HEADERS)
    assert r.status_code == 400


def test_auth_wechat_503_and_refresh(db_engine, monkeypatch):
    monkeypatch.delenv("WECHAT_APPID", raising=False)
    monkeypatch.delenv("WECHAT_SECRET", raising=False)
    r = client.post("/api/v2/auth/wechat", json={"code": "x"})
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]
    from app.auth import mint_refresh_token
    good = mint_refresh_token(uuid.uuid4())
    r = client.post("/api/v2/auth/refresh", json={"refresh_token": good})
    assert r.status_code == 200
    assert r.json()["access_token"]
    r = client.post("/api/v2/auth/refresh",
                    json={"refresh_token": "bogus"})
    assert r.status_code == 401


# --- Baidu client ----------------------------------------------------------

def test_baidu_not_configured():
    from app.ocr_baidu import BaiduNotConfiguredError, BaiduOCRClient
    with pytest.raises(BaiduNotConfiguredError, match="not configured"):
        BaiduOCRClient(api_key="", secret_key="").recognize(b"fake-bytes")


def test_baidu_mocked_http():
    import httpx
    from app.ocr_baidu import BaiduOCRClient

    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if "oauth/2.0/token" in str(request.url):
            return httpx.Response(200, json={
                "access_token": "tok123", "expires_in": 2592000})
        assert "ocr/v1/receipt" in str(request.url)
        return httpx.Response(200, json={
            "words_result": [{"words": "永辉超市"},
                             {"words": "农夫山泉 550ml 2瓶 4.00"},
                             {"words": "合计 56.10"}],
            "words_result_num": 3})

    client_ = BaiduOCRClient(api_key="k", secret_key="s",
                             transport=httpx.MockTransport(handler))
    out = client_.recognize(b"fake-bytes")
    assert out["raw_text"] == "永辉超市\n农夫山泉 550ml 2瓶 4.00\n合计 56.10"
    assert any("oauth/2.0/token" in u for u in seen_urls)


# --- Qwen-VL (only if the model pull succeeded) ----------------------------

def test_qwen_vl_if_available():
    import httpx
    from app.ocr import qwen_vl_transcribe

    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    try:
        tags = httpx.get(f"{base}/api/tags", timeout=10).json()
    except Exception as exc:
        pytest.skip(f"Ollama not reachable: {exc}")
    models = [m.get("name", "") for m in tags.get("models", [])]
    if not any(n.startswith("qwen2.5vl") for n in models):
        pytest.skip("qwen2.5vl model not pulled (pull failed or pending)")
    image = (FIXTURES / "synthetic_receipt.png").read_bytes()
    out = qwen_vl_transcribe(image, timeout=300)
    assert out["raw_text"].strip(), "Qwen-VL returned empty transcription"


# --- OCR failure path: worker stays alive ----------------------------------

def test_ocr_failure_worker_stays_alive(db_engine):
    from app.db import get_redis
    redis_client = get_redis()
    redis_client.delete("imsf-v2:receipt-jobs")

    env = dict(os.environ)
    env["DATABASE_URL"] = _test_url()
    env["OCR_PROVIDER"] = "baidu"
    env.pop("BAIDU_API_KEY", None)
    env.pop("BAIDU_SECRET_KEY", None)
    env["IMSF_V2_SERVICE_TOKEN"] = os.environ["IMSF_V2_SERVICE_TOKEN"]
    env["PYTHONPATH"] = str(REPO_ROOT)

    proc = subprocess.Popen(
        [sys.executable, "-m", "worker.main"],
        cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(3)  # let the worker connect to Redis
        assert proc.poll() is None, "worker died on startup"
        hid = mk_household()
        r = upload_fixture(hid)
        assert r.status_code == 202, r.text
        rid = r.json()["id"]
        deadline = time.time() + 90
        status, error = None, None
        while time.time() < deadline:
            d = client.get(f"/api/v2/receipts/{rid}", headers=SERVICE_HEADERS)
            status, error = d.json()["status"], d.json().get("error_message")
            if status == "failed":
                break
            time.sleep(2)
        assert status == "failed", f"receipt never failed (last={status})"
        assert error and "not configured" in error.lower(), error
        assert proc.poll() is None, "worker died after the bad job"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
