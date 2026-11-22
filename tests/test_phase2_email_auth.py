"""Phase 2 email auth tests (reform plan SS7).

Covers: register (success + token shape + household creation +
normalisation, 409 duplicate, 422 bad email / short / >128 password,
429 register rate limit), login (success + token shape, single 401
message for both missing email and wrong password, 429 after 5 wrong
attempts, lock expiry, 429 for 1/min, attempts reset on success,
re-hash when needs_rehash), the 0006 migration gate on the disposable
DB, and WeChat login still present (503 path, no regression).

Runs against the disposable ``imsf_test`` database (same pattern as
the Step 2/3/4 test files) so the dev DB is never touched. Redis keys
for the rate limit / lockout are cleared before every test so tests
are independent; where a test needs to simulate time passing it
deletes the 60s ``login_rl`` flag or the lock key directly (equivalent
to the TTL expiring).
"""

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import jwt
import pytest
import sqlalchemy as sa
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- env for the app under test (must be set before importing app) -------
os.environ.setdefault("IMSF_SERVICE_TOKEN", "test-service-token")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

BASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://imsf:imsf@127.0.0.1:55434/imsf",
)
TEST_DB = "imsf_test"


def _test_url() -> str:
    url = urlparse(BASE_URL)
    return urlunparse(url._replace(path=f"/{TEST_DB}"))


os.environ["DATABASE_URL"] = _test_url()

from fastapi.testclient import TestClient  # noqa: E402

from app.db import get_redis  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

TRUNCATE_SQL = (
    "TRUNCATE transactions, shopping_lists, shopping_list_items,"
    " notifications, equipment_maintenance_logs,"
    " knowledge_documents, inventory_items, receipt_lines,"
    " receipts, equipments, community_recipes, recipe_ingredients,"
    " household_members, households, users"
    " RESTART IDENTITY CASCADE"
)

REDIS_PREFIXES = ("login_rl:", "login_attempts:", "login_lock:",
                  "register_rl:")


def _clear_rate_limit_keys():
    r = get_redis()
    keys = []
    for prefix in REDIS_PREFIXES:
        keys.extend(r.scan_iter(f"{prefix}*"))
    if keys:
        r.delete(*keys)


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
        conn.execute(text(TRUNCATE_SQL))
    _clear_rate_limit_keys()
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(test_db):
    yield test_db
    with test_db.begin() as conn:
        conn.execute(text(TRUNCATE_SQL))
    _clear_rate_limit_keys()


# --- helpers ---------------------------------------------------------------

def register(email, password="Password123", **extra):
    return client.post("/api/v2/auth/email/register",
                       json={"email": email, "password": password, **extra})


def login(email, password):
    return client.post("/api/v2/auth/email/login",
                       json={"email": email, "password": password})


def clear_login_rl(email):
    """Simulate a minute passing: drop the 1/min flag for this email."""
    get_redis().delete(f"login_rl:{email.strip().lower()}")


def get_user_row(email):
    engine = sa.create_engine(_test_url())
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, email, password_hash, name FROM users"
                 " WHERE email = :e"),
            {"e": email.strip().lower()},
        ).first()
    engine.dispose()
    return row


def decode_access(token):
    return jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])


# --- register --------------------------------------------------------------

def test_register_success_token_shape(db_engine):
    r = register("alice@example.com")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"access_token", "refresh_token", "user",
                         "households"}
    assert body["households"] == []
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["name"] == "alice"  # default: part before @
    assert "wechat_openid" not in body["user"]
    payload = decode_access(body["access_token"])
    assert payload["typ"] == "access"
    assert payload["sub"] == body["user"]["id"]
    assert decode_access(body["refresh_token"])["typ"] == "refresh"
    row = get_user_row("alice@example.com")
    assert row is not None
    assert row[2].startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert row[2] != "Password123"


def test_register_with_name_and_household(db_engine):
    r = register("bob@example.com", name="Bob",
                 household_name="The Bobs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["name"] == "Bob"
    assert len(body["households"]) == 1
    hid = body["households"][0]["id"]
    assert body["households"][0]["name"] == "The Bobs"
    engine = sa.create_engine(_test_url())
    with engine.connect() as conn:
        member = conn.execute(
            text("SELECT role FROM household_members"
                 " WHERE user_id = :u AND household_id = :h"),
            {"u": body["user"]["id"], "h": hid},
        ).first()
        house = conn.execute(
            text("SELECT default_currency, timezone, locale FROM households"
                 " WHERE id = :h"),
            {"h": hid},
        ).first()
    engine.dispose()
    assert member is not None and member[0] == "owner"
    assert house is not None and tuple(house) == ("CNY", "Asia/Shanghai",
                                                  "zh-CN")


def test_register_normalises_email(db_engine):
    r = register("Carol@Example.COM")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "carol@example.com"
    assert get_user_row("carol@example.com") is not None
    assert get_user_row("Carol@Example.COM") is not None  # same row


def test_register_duplicate_409(db_engine):
    assert register("dup@example.com").status_code == 200
    r = register("dup@example.com")
    assert r.status_code == 409
    assert r.json()["detail"] == "Email already registered"
    # Case-variant of the same address is the same duplicate.
    r = register("DUP@example.com")
    assert r.status_code == 409


def test_register_422_bad_email(db_engine):
    assert register("not-an-email").status_code == 422
    assert register("").status_code == 422


def test_register_422_password_length(db_engine):
    assert register("short@example.com", password="1234567").status_code == 422
    assert register("ok8@example.com", password="12345678").status_code == 200
    assert register("long@example.com",
                    password="x" * 129).status_code == 422
    assert register("ok128@example.com",
                    password="x" * 128).status_code == 200


def test_register_429_rate_limit(db_engine):
    for i in range(5):
        r = register(f"rl{i}@example.com")
        assert r.status_code == 200, r.text
    r = register("rl5@example.com")
    assert r.status_code == 429


# --- login -----------------------------------------------------------------

def test_login_success_token_shape(db_engine):
    assert register("login@example.com", household_name="Home").status_code == 200
    clear_login_rl("login@example.com")
    r = login("login@example.com", "Password123")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"access_token", "refresh_token", "user",
                         "households"}
    assert body["user"]["email"] == "login@example.com"
    assert len(body["households"]) == 1
    assert decode_access(body["access_token"])["typ"] == "access"


def test_login_email_case_insensitive(db_engine):
    assert register("case@example.com").status_code == 200
    clear_login_rl("case@example.com")
    r = login("CASE@Example.COM", "Password123")
    assert r.status_code == 200, r.text


def test_login_401_single_message(db_engine):
    assert register("real@example.com").status_code == 200
    clear_login_rl("real@example.com")
    r_missing = login("nobody@example.com", "Password123")
    clear_login_rl("real@example.com")
    r_wrong = login("real@example.com", "WrongPassword")
    assert r_missing.status_code == 401
    assert r_wrong.status_code == 401
    assert r_missing.json()["detail"] == "Invalid email or password"
    assert r_wrong.json()["detail"] == "Invalid email or password"


def test_login_429_one_per_minute(db_engine):
    assert register("once@example.com").status_code == 200
    clear_login_rl("once@example.com")
    assert login("once@example.com", "Password123").status_code == 200
    # Second login inside the same minute -> 429 (no password check).
    assert login("once@example.com", "Password123").status_code == 429


def test_login_lockout_after_5_wrong(db_engine):
    assert register("lock@example.com").status_code == 200
    for i in range(4):
        clear_login_rl("lock@example.com")
        r = login("lock@example.com", "WrongPassword")
        assert r.status_code == 401, f"attempt {i + 1}: {r.text}"
    clear_login_rl("lock@example.com")
    r = login("lock@example.com", "WrongPassword")
    assert r.status_code == 429, r.text
    # Still locked: even the right password is refused while locked.
    clear_login_rl("lock@example.com")
    r = login("lock@example.com", "Password123")
    assert r.status_code == 429
    assert get_redis().exists("login_lock:lock@example.com") == 1


def test_login_lock_expiry(db_engine):
    assert register("unlock@example.com").status_code == 200
    for _ in range(5):
        clear_login_rl("unlock@example.com")
        login("unlock@example.com", "WrongPassword")
    assert get_redis().exists("login_lock:unlock@example.com") == 1
    # Simulate the 15-min TTL expiring: drop the lock key.
    get_redis().delete("login_lock:unlock@example.com")
    clear_login_rl("unlock@example.com")
    r = login("unlock@example.com", "Password123")
    assert r.status_code == 200, r.text


def test_login_attempts_reset_on_success(db_engine):
    assert register("reset@example.com").status_code == 200
    for _ in range(2):
        clear_login_rl("reset@example.com")
        assert login("reset@example.com", "WrongPassword").status_code == 401
    assert get_redis().exists("login_attempts:reset@example.com") == 1
    clear_login_rl("reset@example.com")
    assert login("reset@example.com", "Password123").status_code == 200
    # Counter was reset: a fresh wrong password starts at 1, not 3.
    assert get_redis().exists("login_attempts:reset@example.com") == 0
    clear_login_rl("reset@example.com")
    assert login("reset@example.com", "WrongPassword").status_code == 401
    assert get_redis().get("login_attempts:reset@example.com") == "1"


def test_login_rehash_on_old_params(db_engine):
    from argon2 import PasswordHasher

    old_hash = PasswordHasher(time_cost=1, memory_cost=1024,
                              parallelism=1).hash("Password123")
    engine = sa.create_engine(_test_url())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (email, password_hash, name)"
                 " VALUES ('oldparams@example.com', :h, 'old')"),
            {"h": old_hash},
        )
    engine.dispose()
    clear_login_rl("oldparams@example.com")
    r = login("oldparams@example.com", "Password123")
    assert r.status_code == 200, r.text
    row = get_user_row("oldparams@example.com")
    assert row[2] != old_hash
    assert row[2].startswith("$argon2id$v=19$m=65536,t=3,p=4$")


def test_login_422_bad_body(db_engine):
    assert client.post("/api/v2/auth/email/login",
                       json={"email": "x@example.com"}).status_code == 422
    assert client.post("/api/v2/auth/email/login",
                       json={"email": "not-an-email",
                             "password": "x"}).status_code == 422


# --- passwords unit tests --------------------------------------------------

def test_passwords_hash_verify_rehash():
    from app.passwords import (hash_password, needs_rehash,
                               verify_password)

    h = hash_password("some secret password")
    assert h.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert verify_password(h, "some secret password") is True
    assert verify_password(h, "wrong password") is False
    assert verify_password("not-a-hash", "x") is False
    assert needs_rehash(h) is False


# --- WeChat login still present (no regression) ----------------------------

def test_wechat_login_still_present_503(monkeypatch):
    monkeypatch.delenv("WECHAT_APPID", raising=False)
    monkeypatch.delenv("WECHAT_SECRET", raising=False)
    r = client.post("/api/v2/auth/wechat", json={"code": "dummy"})
    assert r.status_code == 503
    assert r.json()["detail"] == "WeChat login not configured"


# --- migration gate (LAST: downgrades the disposable DB, then restores) ----

# NOTE (Phase 3 blog): this gate tracks alembic HEAD, not a fixed
# revision -- it was "0008" until migration 0010 landed.
def test_migration_0010_gate(test_db):
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _test_url())

    def current():
        from alembic.runtime.migration import MigrationContext

        engine = sa.create_engine(_test_url())
        with engine.connect() as conn:
            rev = MigrationContext.configure(conn).get_current_revision()
        engine.dispose()
        return rev

    assert current() == "0010"
    command.downgrade(cfg, "base")
    assert current() is None
    engine = sa.create_engine(_test_url())
    with engine.connect() as conn:
        tables = conn.execute(
            text("SELECT count(*) FROM information_schema.tables"
                 " WHERE table_schema = 'public'"
                 " AND table_name NOT LIKE 'pg_%'"
                 " AND table_name != 'alembic_version'")).scalar()
        users = conn.execute(
            text("SELECT count(*) FROM information_schema.tables"
                 " WHERE table_schema = 'public'"
                 " AND table_name = 'users'")).scalar()
    engine.dispose()
    assert tables == 0
    assert users == 0
    command.upgrade(cfg, "head")
    assert current() == "0010"
