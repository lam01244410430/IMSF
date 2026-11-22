"""Dashboard Phase C admin tests (contract §1-§4).

Covers: all 13 admin endpoints with the 4 identities (anonymous ->
401, ordinary user -> 403, disabled admin -> 403, valid admin ->
200); the disable/re-enable flow incl. auth_version invalidating old
tokens and the sole-admin self-disable block; audit rows on mutation
+ on household-records inspection; knowledge 503 when the embedding
service is unreachable; the daily cron's job_runs recording; and the
0009 migration upgrade + downgrade on a scratch database.

Runs against the disposable ``imsf_test`` database (same pattern as
the Step 2/3/4 and email-auth test files) so the dev DB is never
touched. ``IMSF_ADMIN_USER_IDS`` is set in the TEST environment only
(monkeypatch), never in /home/ubuntu/imsf.env.
"""

import os
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- env for the app under test (must be set before importing app) -------
os.environ.setdefault("IMSF_SERVICE_TOKEN", "test-service-token")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.pop("IMSF_ADMIN_USER_IDS", None)
os.environ.pop("IMSF_GPU_EXPECTED_OFF", None)

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

import app.api.knowledge as knowledge_api  # noqa: E402
from app.auth import mint_access_token, mint_refresh_token  # noqa: E402
from app.db import get_redis  # noqa: E402
from app.main import app  # noqa: E402
from app.passwords import hash_password  # noqa: E402

client = TestClient(app)

TRUNCATE_SQL = (
    "TRUNCATE admin_audit_events, job_runs, transactions,"
    " shopping_lists, shopping_list_items,"
    " notifications, equipment_maintenance_logs,"
    " knowledge_documents, inventory_items, receipt_lines,"
    " receipts, equipments, community_recipes, recipe_ingredients,"
    " household_members, households, users"
    " RESTART IDENTITY CASCADE"
)


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
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(test_db):
    yield test_db
    with test_db.begin() as conn:
        conn.execute(text(TRUNCATE_SQL))


def _db():
    return sa.create_engine(_test_url())


def create_user(email=None, openid=None, name="Test User"):
    """Insert a user row satisfying ck_users_login_channel.

    An email user needs a password_hash too (email alone is not a
    login method); a WeChat user needs the openid. The default
    password for email users is "Password123".
    """
    user_id = uuid.uuid4()
    engine = _db()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email, password_hash,"
                 " wechat_openid, name)"
                 " VALUES (:id, :e, :h, :o, :n)"),
            {"id": user_id, "e": email,
             "h": hash_password("Password123") if email else None,
             "o": openid, "n": name},
        )
    engine.dispose()
    return user_id


def create_household(owner_id, name="House"):
    hid = uuid.uuid4()
    engine = _db()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO households (id, name, default_currency,"
                 " timezone, locale)"
                 " VALUES (:id, :n, 'CNY', 'Asia/Shanghai', 'zh-CN')"),
            {"id": hid, "n": name},
        )
        conn.execute(
            text("INSERT INTO household_members (user_id, household_id,"
                 " role) VALUES (:u, :h, 'owner')"),
            {"u": owner_id, "h": hid},
        )
    engine.dispose()
    return hid


def seed_household_data(hid, owner_id):
    """One receipt + transaction + inventory item + equipment."""
    engine = _db()
    with engine.begin() as conn:
        receipt_id = conn.execute(
            text("INSERT INTO receipts (household_id,"
                 " uploaded_by_user_id, image_url, store_name,"
                 " total_amount, currency, status)"
                 " VALUES (:h, :u, '/x.jpg', 'Test Store', 12.50,"
                 " 'CNY', 'failed') RETURNING id"),
            {"h": hid, "u": owner_id},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO transactions (household_id, receipt_id,"
                 " type, amount, currency, category, occurred_at, note)"
                 " VALUES (:h, :r, 'expense', 12.50, 'CNY', 'food',"
                 " now(), 'test note')"),
            {"h": hid, "r": receipt_id},
        )
        conn.execute(
            text("INSERT INTO inventory_items (household_id, receipt_id,"
                 " raw_name, quantity, unit, currency, storage_zone,"
                 " added_date, status)"
                 " VALUES (:h, :r, 'milk', 1, 'bottle', 'CNY', 'fridge',"
                 " CURRENT_DATE, 'fresh')"),
            {"h": hid, "r": receipt_id},
        )
        conn.execute(
            text("INSERT INTO equipments (household_id, device_type,"
                 " brand_model, status)"
                 " VALUES (:h, 'fridge', 'Test Fridge', 'active')"),
            {"h": hid},
        )
    engine.dispose()
    return receipt_id


def seed_recipe(title="Seed Soup", status="draft", author="Seed Author"):
    recipe_id = uuid.uuid4()
    engine = _db()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO community_recipes (id, title, cover_image,"
                 " steps_json, cook_time, likes_count, status, author)"
                 " VALUES (:id, :t, NULL, CAST('[]' AS jsonb), 30, 0,"
                 " :s, :a)"),
            {"id": recipe_id, "t": title, "s": status, "a": author},
        )
    engine.dispose()
    return recipe_id


def auth_version(user_id):
    engine = _db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT auth_version FROM users WHERE id = :id"),
            {"id": user_id},
        ).first()
    engine.dispose()
    return row[0] if row else None


def user_row(user_id):
    engine = _db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, disabled_at, auth_version FROM users"
                 " WHERE id = :id"),
            {"id": user_id},
        ).first()
    engine.dispose()
    return row


def audit_rows(action=None):
    engine = _db()
    with engine.connect() as conn:
        if action:
            rows = conn.execute(
                text("SELECT actor_user_id, action, target_type,"
                     " target_id, reason, outcome FROM admin_audit_events"
                     " WHERE action = :a ORDER BY created_at"),
                {"a": action},
            ).all()
        else:
            rows = conn.execute(
                text("SELECT actor_user_id, action, target_type,"
                     " target_id, reason, outcome FROM admin_audit_events"
                     " ORDER BY created_at"),
            ).all()
    engine.dispose()
    return rows


def headers_for(user_id, ver=1):
    return {"Authorization": f"Bearer {mint_access_token(user_id, ver)}"}


def set_admins(monkeypatch, *user_ids):
    monkeypatch.setenv("IMSF_ADMIN_USER_IDS",
                       ",".join(str(u) for u in user_ids))


# --- (a) access-control matrix: all 13 endpoints x 4 identities ---------


GET_ENDPOINTS = [
    "/me",
    "/stats",
    "/users",
    "/users/{uid}",
    "/households/{hid}/records?type=receipts&reason=matrix-check",
    "/health",
    "/jobs",
    "/receipt-jobs",
    "/recipes",
    "/audit-events",
]


@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_get_endpoints_matrix(db_engine, monkeypatch, path):
    admin_id = create_user(email="admin-matrix@example.com")
    other_admin = create_user(email="admin2-matrix@example.com")
    ordinary_id = create_user(email="ordinary-matrix@example.com")
    disabled_admin_id = create_user(email="disabled-matrix@example.com")
    target_id = create_user(email="target-matrix@example.com",
                            name="Target Person")
    hid = create_household(target_id)
    seed_household_data(hid, target_id)
    # Disable the disabled-admin AFTER minting their token: the token
    # itself is well-formed, the account is what fails the check.
    engine = _db()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET disabled_at = now() WHERE id = :id"),
            {"id": disabled_admin_id},
        )
    engine.dispose()
    set_admins(monkeypatch, admin_id, other_admin, disabled_admin_id)
    url = (path.replace("{uid}", str(target_id))
               .replace("{hid}", str(hid)))
    full = f"/api/v2/admin{url}"
    # Anonymous -> 401.
    assert client.get(full).status_code == 401
    # Ordinary user -> 403.
    assert client.get(full,
                      headers=headers_for(ordinary_id)).status_code == 403
    # Disabled admin -> 403.
    assert client.get(
        full, headers=headers_for(disabled_admin_id)).status_code == 403
    # Valid admin -> 200 + no-store.
    r = client.get(full, headers=headers_for(admin_id))
    assert r.status_code == 200, (full, r.text)
    assert r.headers.get("Cache-Control") == "no-store"
    # Service token -> 403 (never an admin). Use the token from the
    # environment: imsf.env may set a real one, and setdefault above
    # does not override an already-set value.
    service_token = os.environ.get("IMSF_SERVICE_TOKEN",
                                   "test-service-token")
    r = client.get(full, headers={"Authorization": "Bearer "
                                  f"{service_token}"})
    assert r.status_code == 403


def test_mutation_endpoints_matrix(db_engine, monkeypatch):
    admin_id = create_user(email="admin-mut@example.com")
    ordinary_id = create_user(email="ordinary-mut@example.com")
    target_id = create_user(email="target-mut@example.com")
    recipe_id = seed_recipe()
    set_admins(monkeypatch, admin_id)
    cases = [
        ("PATCH", f"/api/v2/admin/users/{target_id}/status",
         {"disabled": True, "reason": "matrix check"}),
        ("POST", "/api/v2/admin/recipes",
         {"title": "Matrix Recipe"}),
        ("PATCH", f"/api/v2/admin/recipes/{recipe_id}",
         {"title": "Matrix Renamed"}),
    ]
    for method, url, body in cases:
        call = client.patch if method == "PATCH" else client.post
        assert call(url, json=body).status_code == 401
        assert call(url, json=body,
                    headers=headers_for(ordinary_id)).status_code == 403
        r = call(url, json=body, headers=headers_for(admin_id))
        assert r.status_code == 200, (method, url, r.text)
        assert r.headers.get("Cache-Control") == "no-store"


def test_no_admin_when_allowlist_missing_or_malformed(db_engine,
                                                       monkeypatch):
    admin_id = create_user(email="admin-noenv@example.com")
    monkeypatch.delenv("IMSF_ADMIN_USER_IDS", raising=False)
    r = client.get("/api/v2/admin/me", headers=headers_for(admin_id))
    assert r.status_code == 403
    monkeypatch.setenv("IMSF_ADMIN_USER_IDS", "not-a-uuid")
    r = client.get("/api/v2/admin/me", headers=headers_for(admin_id))
    assert r.status_code == 403
    monkeypatch.setenv("IMSF_ADMIN_USER_IDS",
                       f"{admin_id},not-a-uuid")
    r = client.get("/api/v2/admin/me", headers=headers_for(admin_id))
    assert r.status_code == 403


# --- (b) disable / re-enable flow ------------------------------------------


def test_disable_reenable_invalidates_tokens(db_engine, monkeypatch):
    from app.passwords import hash_password

    admin_id = create_user(email="admin-flow@example.com")
    user_id = create_user(email="flow-user@example.com")
    engine = _db()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET password_hash = :h WHERE id = :id"),
            {"h": hash_password("Password123"), "id": user_id},
        )
    engine.dispose()
    set_admins(monkeypatch, admin_id)
    assert auth_version(user_id) == 1
    old_access = mint_access_token(user_id, 1)
    old_refresh = mint_refresh_token(user_id, 1)

    # Disable: version bumps. While disabled, the old tokens fail
    # the disabled check first (403, contract §1.3 order) and email
    # login 403s.
    r = client.patch(f"/api/v2/admin/users/{user_id}/status",
                     json={"disabled": True, "reason": "abuse report"},
                     headers=headers_for(admin_id))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "disabled"
    assert r.json()["disabled_at"] is not None
    assert auth_version(user_id) == 2
    r = client.post("/api/v2/auth/refresh",
                    json={"refresh_token": old_refresh})
    assert r.status_code == 403
    r = client.get("/api/v2/knowledge/search?q=milk",
                   headers={"Authorization": f"Bearer {old_access}"})
    assert r.status_code == 403
    get_redis().delete("login_rl:flow-user@example.com")
    r = client.post("/api/v2/auth/email/login",
                    json={"email": "flow-user@example.com",
                          "password": "Password123"})
    assert r.status_code == 403

    # Re-enable: version bumps AGAIN, so the pre-disable token is
    # still invalid after re-enable.
    r = client.patch(f"/api/v2/admin/users/{user_id}/status",
                     json={"disabled": False, "reason": "appeal upheld"},
                     headers=headers_for(admin_id))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "enabled"
    assert r.json()["disabled_at"] is None
    assert auth_version(user_id) == 3
    r = client.post("/api/v2/auth/refresh",
                    json={"refresh_token": old_refresh})
    assert r.status_code == 401
    get_redis().delete("login_rl:flow-user@example.com")
    r = client.post("/api/v2/auth/email/login",
                    json={"email": "flow-user@example.com",
                          "password": "Password123"})
    assert r.status_code == 200, r.text
    # The fresh login token carries the current version.
    import jwt

    payload = jwt.decode(
        r.json()["access_token"],
        os.environ.get("JWT_SECRET", "test-jwt-secret"),
        algorithms=["HS256"])
    assert payload["ver"] == 3


def test_status_requires_reason_and_404(db_engine, monkeypatch):
    admin_id = create_user(email="admin-reason@example.com")
    target_id = create_user(email="target-reason@example.com")
    set_admins(monkeypatch, admin_id)
    url = f"/api/v2/admin/users/{target_id}/status"
    assert client.patch(url, json={"disabled": True},
                        headers=headers_for(admin_id)).status_code == 400
    assert client.patch(url, json={"disabled": True, "reason": "  "},
                        headers=headers_for(admin_id)).status_code == 400
    assert client.patch(url, json={"reason": "x"},
                        headers=headers_for(admin_id)).status_code == 400
    r = client.patch(f"/api/v2/admin/users/{uuid.uuid4()}/status",
                     json={"disabled": True, "reason": "x"},
                     headers=headers_for(admin_id))
    assert r.status_code == 404


def test_sole_admin_self_disable_blocked(db_engine, monkeypatch):
    admin_id = create_user(email="sole-admin@example.com")
    set_admins(monkeypatch, admin_id)
    r = client.patch(f"/api/v2/admin/users/{admin_id}/status",
                     json={"disabled": True, "reason": "oops"},
                     headers=headers_for(admin_id))
    assert r.status_code == 400
    assert user_row(admin_id)[1] is None  # still enabled
    # With a second admin configured, self-disable is allowed.
    admin2_id = create_user(email="second-admin@example.com")
    set_admins(monkeypatch, admin_id, admin2_id)
    r = client.patch(f"/api/v2/admin/users/{admin_id}/status",
                     json={"disabled": True, "reason": "stepping down"},
                     headers=headers_for(admin_id))
    assert r.status_code == 200, r.text
    assert user_row(admin_id)[1] is not None


# --- (c) audit rows ----------------------------------------------------------


def test_audit_rows_on_mutation_and_inspection(db_engine, monkeypatch):
    admin_id = create_user(email="admin-audit@example.com")
    target_id = create_user(email="target-audit@example.com")
    hid = create_household(target_id)
    seed_household_data(hid, target_id)
    seed_recipe()
    set_admins(monkeypatch, admin_id)
    assert audit_rows() == []

    r = client.patch(f"/api/v2/admin/users/{target_id}/status",
                     json={"disabled": True, "reason": "audit test"},
                     headers=headers_for(admin_id))
    assert r.status_code == 200
    r = client.post("/api/v2/admin/recipes",
                    json={"title": "Audit Soup"},
                    headers=headers_for(admin_id))
    assert r.status_code == 200
    created_id = r.json()["id"]
    r = client.get(
        f"/api/v2/admin/households/{hid}/records"
        "?type=transactions&reason=audit+inspection",
        headers=headers_for(admin_id))
    assert r.status_code == 200
    assert r.json()["total"] == 1

    rows = audit_rows()
    by_action = {row[1]: row for row in rows}
    assert set(by_action) == {"user_disabled", "recipe_created",
                              "household_records_inspected"}
    assert by_action["user_disabled"][0] == admin_id
    assert by_action["user_disabled"][2] == "user"
    assert by_action["user_disabled"][3] == str(target_id)
    assert by_action["user_disabled"][4] == "audit test"
    assert by_action["user_disabled"][5] == "success"
    assert by_action["recipe_created"][3] == created_id
    assert by_action["household_records_inspected"][3] == str(hid)
    assert by_action["household_records_inspected"][4] == \
        "audit inspection"

    # The audit list endpoint itself exposes the rows (no edit/delete).
    r = client.get("/api/v2/admin/audit-events",
                   headers=headers_for(admin_id))
    assert r.status_code == 200
    assert r.json()["total"] == 3
    r = client.get("/api/v2/admin/audit-events?action=user_disabled",
                   headers=headers_for(admin_id))
    assert r.json()["total"] == 1
    r = client.get(
        f"/api/v2/admin/audit-events?target_id={target_id}",
        headers=headers_for(admin_id))
    assert r.json()["total"] == 1


# --- endpoint shapes ---------------------------------------------------------


def test_users_search_filters_and_no_openid(db_engine, monkeypatch):
    admin_id = create_user(email="admin-search@example.com")
    email_id = create_user(email="findme@example.com", name="Alice A")
    create_user(openid="wx-openid-123", name="Bob B")
    create_user(email="other@example.com", name="Alice C")
    set_admins(monkeypatch, admin_id)
    h = headers_for(admin_id)

    r = client.get("/api/v2/admin/users?q=findme@example.com", headers=h)
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] == str(email_id)
    r = client.get("/api/v2/admin/users?q=Alice", headers=h)
    assert r.json()["total"] == 2
    r = client.get("/api/v2/admin/users?q=wx-openid-123", headers=h)
    assert r.json()["total"] == 1  # exact-openid lookup, server-side
    r = client.get("/api/v2/admin/users?login_method=wechat", headers=h)
    assert r.json()["total"] == 1
    assert all(i["login_method"] == "wechat"
               for i in r.json()["items"])
    r = client.get("/api/v2/admin/users?login_method=email", headers=h)
    assert r.json()["total"] == 3
    assert "wx-openid-123" not in r.text  # openid never returned
    assert "wechat_openid" not in r.text
    r = client.get("/api/v2/admin/users?status=disabled", headers=h)
    assert r.json()["total"] == 0
    r = client.get("/api/v2/admin/users?status=bogus", headers=h)
    assert r.status_code == 400
    r = client.get("/api/v2/admin/users?limit=101", headers=h)
    assert r.status_code == 400


def test_user_detail_counts_and_404(db_engine, monkeypatch):
    admin_id = create_user(email="admin-detail@example.com")
    target_id = create_user(email="target-detail@example.com")
    hid = create_household(target_id)
    seed_household_data(hid, target_id)
    set_admins(monkeypatch, admin_id)
    r = client.get(f"/api/v2/admin/users/{target_id}",
                   headers=headers_for(admin_id))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["households"] == [{"household_id": str(hid),
                                   "name": "House", "role": "owner"}]
    assert body["counts"] == {"receipts": 1, "transactions": 1,
                              "inventory_items": 1, "equipments": 1}
    assert "password_hash" not in r.text
    r = client.get(f"/api/v2/admin/users/{uuid.uuid4()}",
                   headers=headers_for(admin_id))
    assert r.status_code == 404


def test_household_records_requires_type_and_reason(db_engine, monkeypatch):
    admin_id = create_user(email="admin-records@example.com")
    target_id = create_user(email="target-records@example.com")
    hid = create_household(target_id)
    seed_household_data(hid, target_id)
    set_admins(monkeypatch, admin_id)
    h = headers_for(admin_id)
    base = f"/api/v2/admin/households/{hid}/records"
    assert client.get(base, headers=h).status_code == 400
    assert client.get(f"{base}?type=receipts",
                      headers=h).status_code == 400
    assert client.get(f"{base}?type=bogus&reason=x",
                      headers=h).status_code == 400
    assert client.get(f"{base}?type=receipts&reason=",
                      headers=h).status_code == 400
    for rtype, total in (("receipts", 1), ("transactions", 1),
                         ("inventory", 1), ("equipment", 1)):
        r = client.get(f"{base}?type={rtype}&reason=check",
                       headers=h)
        assert r.status_code == 200, (rtype, r.text)
        assert r.json()["total"] == total
    assert len(audit_rows("household_records_inspected")) == 4
    r = client.get(f"/api/v2/admin/households/{uuid.uuid4()}/records"
                   "?type=receipts&reason=x", headers=h)
    assert r.status_code == 404


def test_me_and_stats(db_engine, monkeypatch):
    admin_id = create_user(email="admin-me@example.com", name="Boss")
    wechat_id = create_user(openid="wx-admin-1", name="WeChat Boss")
    target_id = create_user(email="target-me@example.com")
    hid = create_household(target_id)
    seed_household_data(hid, target_id)
    seed_recipe(title="Published One", status="published")
    seed_recipe(title="Hidden One", status="hidden")
    seed_recipe(title="Draft One", status="draft")
    set_admins(monkeypatch, admin_id, wechat_id)
    r = client.get("/api/v2/admin/me", headers=headers_for(admin_id))
    assert r.json() == {
        "user_id": str(admin_id), "name": "Boss",
        "email": "admin-me@example.com", "login_method": "email",
        "capabilities": ["users:read", "users:write", "recipes:write",
                         "audit:read", "system:read"]}
    r = client.get("/api/v2/admin/me", headers=headers_for(wechat_id))
    assert r.json()["login_method"] == "wechat"
    r = client.get("/api/v2/admin/stats", headers=headers_for(admin_id))
    assert r.status_code == 200, r.text
    counts = r.json()["counts"]
    assert counts["users"] == 3
    assert counts["households"] == 1
    assert counts["receipts"] == 1
    assert counts["transactions"] == 1
    assert counts["inventory_items"] == 1
    assert counts["published_recipes"] == 1
    assert counts["draft_recipes"] == 1
    assert counts["hidden_recipes"] == 1
    exc = r.json()["exceptions"]
    assert exc["failed_receipt_jobs"] == 1
    assert exc["overdue_cron"] is False
    assert "ollama (knowledge search)" in \
        exc["unavailable_dependencies"]


def test_health_shape_and_gpu_flag(db_engine, monkeypatch):
    admin_id = create_user(email="admin-health@example.com")
    set_admins(monkeypatch, admin_id)
    h = headers_for(admin_id)
    monkeypatch.delenv("IMSF_GPU_EXPECTED_OFF", raising=False)
    r = client.get("/api/v2/admin/health", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"checked_at", "api", "postgres", "redis",
                         "gpu", "cron", "receipt_worker", "vercel"}
    assert body["api"]["status"] == "healthy"
    assert body["api"]["version"] == "0.1.0"
    assert body["postgres"]["status"] == "healthy"
    assert body["redis"]["status"] == "healthy"
    # GPU off and not configured off -> unavailable.
    assert body["gpu"]["status"] == "unavailable"
    assert body["gpu"]["expected_off"] is False
    assert body["gpu"]["embedding_model"] == "bge-m3"
    assert body["gpu"]["affected"] == ["knowledge search"]
    # next_run is 08:00 Asia/Shanghai.
    assert body["cron"]["next_run"].endswith("+08:00")
    assert body["cron"]["next_run"][11:16] == "08:00"
    assert body["cron"]["last_run"] is None  # no job_runs rows yet
    assert body["cron"]["status"] == "unknown"
    # Receipt worker: no heartbeat mechanism exists -> unknown.
    worker = body["receipt_worker"]
    assert worker["status"] == "unknown"
    assert worker["heartbeat_at"] is None
    assert worker["failed"] == 0
    # Queue depth is live Redis state shared with other tests, so it
    # is only asserted to be a non-negative int, never an exact 0.
    assert isinstance(worker["queued"], int) and worker["queued"] >= 0
    assert body["vercel"]["api_note"] == "hollow/unconfigured"
    # With the expected-off flag, the same offline GPU is expected.
    monkeypatch.setenv("IMSF_GPU_EXPECTED_OFF", "1")
    r = client.get("/api/v2/admin/health", headers=h)
    assert r.json()["gpu"]["status"] == "offline_expected"
    assert r.json()["gpu"]["expected_off"] is True


def test_jobs_empty_then_after_daily_run(db_engine, monkeypatch):
    from app.jobs.daily import run_daily

    admin_id = create_user(email="admin-jobs@example.com")
    set_admins(monkeypatch, admin_id)
    h = headers_for(admin_id)
    engine = _db()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job_runs"))
    engine.dispose()
    r = client.get("/api/v2/admin/jobs", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["history"] == []
    assert r.json()["cron"]["last_run"] is None
    assert r.json()["worker_heartbeat"] == {"at": None,
                                            "status": "unknown"}
    counts = run_daily()
    assert counts == {"lazy_created": 0, "lazy_skipped": 0,
                      "maint_created": 0, "maint_skipped": 0}
    r = client.get("/api/v2/admin/jobs", headers=h)
    assert len(r.json()["history"]) == 1
    row = r.json()["history"][0]
    assert row["job_name"] == "daily"
    assert row["status"] == "success"
    assert row["notifications_created"] == 0
    assert row["duration_ms"] is not None
    assert row["finished_at"] is not None
    assert r.json()["cron"]["last_run"] is not None
    assert r.json()["cron"]["last_success"] is not None


def test_receipt_jobs_real_state(db_engine, monkeypatch):
    admin_id = create_user(email="admin-rj@example.com")
    target_id = create_user(email="target-rj@example.com")
    hid = create_household(target_id)
    seed_household_data(hid, target_id)
    set_admins(monkeypatch, admin_id)
    r = client.get("/api/v2/admin/receipt-jobs",
                   headers=headers_for(admin_id))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    item = r.json()["items"][0]
    assert item["status"] == "failed"
    assert item["store_name"] == "Test Store"
    assert item["total_amount"] == 12.5
    assert item["currency"] == "CNY"
    assert item["household_id"] == str(hid)


def test_recipes_admin_crud_and_public_visibility(db_engine, monkeypatch):
    admin_id = create_user(email="admin-recipes@example.com")
    set_admins(monkeypatch, admin_id)
    h = headers_for(admin_id)

    # Create: title required, status always draft, author_id NULL.
    assert client.post("/api/v2/admin/recipes", json={},
                       headers=h).status_code == 400
    r = client.post("/api/v2/admin/recipes",
                    json={"title": "Admin Soup", "author": "Seed Bot",
                          "category": "soup", "language": "zh",
                          "ingredients": [{"name": "water",
                                           "amount": 500,
                                           "unit": "ml"}]},
                    headers=h)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["status"] == "draft"
    assert created["author"] == "Seed Bot"
    recipe_id = created["id"]
    engine = _db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT author_id FROM community_recipes WHERE id = :id"),
            {"id": recipe_id},
        ).first()
        assert row[0] is None
        ing = conn.execute(
            text("SELECT raw_name, amount, unit FROM recipe_ingredients"
                 " WHERE recipe_id = :id"),
            {"id": recipe_id},
        ).all()
        assert [(i[0], float(i[1]), i[2]) for i in ing] == \
            [("water", 500.0, "ml")]
    engine.dispose()

    # Admin list sees drafts; the public list does not.
    r = client.get("/api/v2/admin/recipes?status=draft", headers=h)
    assert r.json()["total"] == 1
    r = client.get("/api/v2/recipes")
    assert r.json()["total"] == 0

    # Publish -> public; hide -> gone from public list AND detail.
    r = client.patch(f"/api/v2/admin/recipes/{recipe_id}",
                     json={"status": "published"}, headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "published"
    r = client.get("/api/v2/recipes")
    assert r.json()["total"] == 1
    r = client.patch(f"/api/v2/admin/recipes/{recipe_id}",
                     json={"status": "hidden"}, headers=h)
    assert r.json()["status"] == "hidden"
    r = client.get("/api/v2/recipes")
    assert r.json()["total"] == 0
    r = client.get(f"/api/v2/recipes/{recipe_id}")
    assert r.status_code == 404

    # Unknown fields / bad status -> 400; unknown recipe -> 404.
    r = client.patch(f"/api/v2/admin/recipes/{recipe_id}",
                     json={"servings": 4}, headers=h)
    assert r.status_code == 400
    r = client.patch(f"/api/v2/admin/recipes/{recipe_id}",
                     json={"status": "pending"}, headers=h)
    assert r.status_code == 400
    r = client.patch(f"/api/v2/admin/recipes/{uuid.uuid4()}",
                     json={"title": "x"}, headers=h)
    assert r.status_code == 404
    r = client.patch(f"/api/v2/admin/recipes/{recipe_id}",
                     json={}, headers=h)
    assert r.status_code == 400
    assert len(audit_rows("recipe_created")) == 1
    assert len(audit_rows("recipe_updated")) == 2


# --- (d) knowledge 503 -------------------------------------------------------


def test_knowledge_503_when_embedding_unreachable(db_engine, monkeypatch):
    user_id = create_user(email="rag-user@example.com")
    h = headers_for(user_id)

    def _boom(*args, **kwargs):
        raise httpx.ConnectError(
            "boom", request=httpx.Request("POST", "http://127.0.0.1:11434"))

    monkeypatch.setattr(knowledge_api, "search_knowledge", _boom)
    r = client.get("/api/v2/knowledge/search?q=milk", headers=h)
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == \
        "Knowledge search unavailable: embedding service is offline"


def test_knowledge_503_live_ollama_down(db_engine):
    """No monkeypatch: on this host Ollama is unreachable (GPU off)."""
    user_id = create_user(email="rag-live@example.com")
    r = client.get("/api/v2/knowledge/search?q=milk",
                   headers=headers_for(user_id))
    if r.status_code == 200:
        pytest.skip("Ollama is reachable here; live-503 not observable")
    assert r.status_code == 503, r.text


# --- (e) migration 0009 upgrade + downgrade on a scratch DB -----------------


def test_migration_0009_upgrade_downgrade(monkeypatch):
    from alembic import command
    from alembic.config import Config

    mig_db = "imsf_test_mig0009"
    url = urlparse(BASE_URL)
    mig_url = urlunparse(url._replace(path=f"/{mig_db}"))
    admin = sa.create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {mig_db}"))
        conn.execute(text(f"CREATE DATABASE {mig_db}"))
    admin.dispose()
    try:
        # alembic/env.py reads DATABASE_URL from the environment and
        # overrides the Config URL, so the scratch URL must go through
        # the environment for these commands.
        monkeypatch.setenv("DATABASE_URL", mig_url)
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
        cfg.set_main_option("sqlalchemy.url", mig_url)
        engine = sa.create_engine(mig_url)

        def has_table(name):
            with engine.connect() as conn:
                return conn.execute(
                    text("SELECT 1 FROM information_schema.tables"
                         " WHERE table_name = :n"),
                    {"n": name},
                ).first() is not None

        def has_column(table, column):
            with engine.connect() as conn:
                return conn.execute(
                    text("SELECT 1 FROM information_schema.columns"
                         " WHERE table_name = :t AND column_name = :c"),
                    {"t": table, "c": column},
                ).first() is not None

        command.upgrade(cfg, "0008")
        assert not has_table("admin_audit_events")
        assert not has_table("job_runs")
        assert not has_column("users", "disabled_at")
        assert not has_column("users", "auth_version")

        command.upgrade(cfg, "0009")
        assert has_table("admin_audit_events")
        assert has_table("job_runs")
        assert has_column("users", "disabled_at")
        assert has_column("users", "auth_version")

        command.downgrade(cfg, "0008")
        assert not has_table("admin_audit_events")
        assert not has_table("job_runs")
        assert not has_column("users", "disabled_at")
        assert not has_column("users", "auth_version")

        command.upgrade(cfg, "head")
        assert has_table("admin_audit_events")
        assert has_table("job_runs")
        engine.dispose()
    finally:
        admin = sa.create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(
                text(f"DROP DATABASE IF EXISTS {mig_db} WITH (FORCE)"))
        admin.dispose()


# --- audit-events date filters ------------------------------------------------


def test_audit_events_date_filters(db_engine, monkeypatch):
    admin_id = create_user(email="admin-dates@example.com")
    target_id = create_user(email="target-dates@example.com")
    set_admins(monkeypatch, admin_id)
    h = headers_for(admin_id)
    client.patch(f"/api/v2/admin/users/{target_id}/status",
                 json={"disabled": True, "reason": "date test"}, headers=h)
    today = date.today().isoformat()
    r = client.get(f"/api/v2/admin/audit-events?from={today}", headers=h)
    assert r.json()["total"] == 1
    r = client.get(f"/api/v2/admin/audit-events?to={today}", headers=h)
    assert r.json()["total"] == 1
    r = client.get("/api/v2/admin/audit-events?from=2000-01-01&to=2000-01-02",
                   headers=h)
    assert r.json()["total"] == 0
    r = client.get("/api/v2/admin/audit-events?from=not-a-date", headers=h)
    assert r.status_code == 400
