"""Phase 2 Step 3 tests: fridge + Lazy Tracking + shopping lists
(design §3.2, §3.3, §3.4, §5.1, §5.2, §5.4, §6.1, §6.2, §8, §9 Gates B + C).

Runs against the disposable ``imsf_test`` database (same pattern as
the Step 1/2 test files) so the dev DB is never touched. The daily job
is exercised by importing ``app.jobs.daily`` and calling ``run_daily``
/ ``main`` directly — never by shelling out to the cron. The WeChat
sender is exercised as a module via subprocess with the WeChat env
scrubbed, so it must take the skip path and touch no rows.
"""

import json
import os
import subprocess
import sys
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

from app.jobs import daily as daily_job  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
SERVICE_HEADERS = {
    "Authorization": f"Bearer {os.environ['IMSF_SERVICE_TOKEN']}"
}

SHANGHAI = ZoneInfo("Asia/Shanghai")

# Canonical names from the Phase 1 seed (migration 0002). Looked up by
# name at seed time, never hardcoded as UUIDs.
RICE = "Gạo"
PORK = "Thịt ba chỉ"
MILK = "Sữa tươi"


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
            "TRUNCATE transactions, shopping_lists, shopping_list_items,"
            " notifications, equipment_maintenance_logs,"
            " knowledge_documents, inventory_items, receipt_lines,"
            " receipts, equipments, community_recipes, recipe_ingredients,"
            " household_members, households, users"
            " RESTART IDENTITY CASCADE"))
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(test_db):
    yield test_db
    with test_db.begin() as conn:
        conn.execute(text(
            "TRUNCATE transactions, shopping_lists, shopping_list_items,"
            " notifications, equipment_maintenance_logs,"
            " knowledge_documents, inventory_items, receipt_lines,"
            " receipts, equipments, community_recipes, recipe_ingredients,"
            " household_members, households, users"
            " RESTART IDENTITY CASCADE"))


# --- helpers ---------------------------------------------------------------

def today_shanghai():
    return datetime.now(SHANGHAI).date()


def mk_household(name="Test Home"):
    r = client.post("/api/v2/households",
                    json={"name": name, "timezone": "Asia/Shanghai"},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def owner_id(db_engine, hid):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT user_id FROM household_members"
                 " WHERE household_id=:h AND role='owner'"),
            {"h": uuid.UUID(hid)},
        ).scalar_one()


def master_id(db_engine, canonical_name):
    with db_engine.connect() as conn:
        mid = conn.execute(
            text("SELECT id FROM master_ingredients"
                 " WHERE canonical_name=:n"),
            {"n": canonical_name},
        ).scalar_one_or_none()
    assert mid is not None, f"no seed master ingredient {canonical_name!r}"
    return mid


def seed_item(db_engine, hid, canonical_name, quantity, unit, expiry,
              raw_name=None, status="fresh"):
    """Insert one inventory item directly (no receipt seeder exists)."""
    mid = master_id(db_engine, canonical_name)
    with db_engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO inventory_items (household_id, raw_name,"
                 " canonical_ingredient_id, quantity, unit, currency,"
                 " storage_zone, auto_expiry_date, status)"
                 " VALUES (:h, :raw, :mid, :q, :u, 'CNY', 'fridge',"
                 " :exp, :st) RETURNING id"),
            {"h": uuid.UUID(hid),
             "raw": raw_name or canonical_name, "mid": mid,
             "q": quantity, "u": unit, "exp": expiry, "st": status},
        ).scalar_one()


def seed_equipment(db_engine, hid, next_date, device_type="air_conditioner",
                   brand_model="Test AC"):
    with db_engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO equipments (household_id, device_type,"
                 " brand_model, status, next_maintenance_date)"
                 " VALUES (:h, :dt, :bm, 'active', :nd) RETURNING id"),
            {"h": uuid.UUID(hid), "dt": device_type, "bm": brand_model,
             "nd": next_date},
        ).scalar_one()


def seed_recipe(db_engine, hid, lines):
    """lines: [(canonical_name, raw_name, amount, unit), ...]."""
    with db_engine.begin() as conn:
        rid = conn.execute(
            text("INSERT INTO community_recipes (title, steps_json)"
                 " VALUES ('Test recipe', '[]'::jsonb) RETURNING id"),
        ).scalar_one()
        for canonical_name, raw_name, amount, unit in lines:
            mid = master_id(db_engine, canonical_name) \
                if canonical_name else None
            conn.execute(
                text("INSERT INTO recipe_ingredients (recipe_id,"
                     " canonical_ingredient_id, raw_name, amount, unit)"
                     " VALUES (:rid, :mid, :raw, :amt, :u)"),
                {"rid": rid, "mid": mid, "raw": raw_name,
                 "amt": amount, "u": unit},
            )
    return rid


def seed_notification(db_engine, hid, ntype, ref_type, ref_id,
                      sent_at=None, status="sent"):
    """Insert one notification row directly (bypasses the daily job)."""
    uid = owner_id(db_engine, hid)
    payload = {"item_name": "seeded", "expiry_date": "2026-11-20",
               "actions": ["used_up", "extended"]}
    with db_engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO notifications (user_id, household_id, type,"
                 " ref_type, ref_id, channel, payload_json, status,"
                 " sent_at) VALUES (:uid, :h, :t, :rt, :rid, 'in_app',"
                 " CAST(:p AS jsonb), :st, :sent) RETURNING id"),
            {"uid": uid, "h": uuid.UUID(hid), "t": ntype,
             "rt": ref_type, "rid": ref_id, "p": json.dumps(payload),
             "st": status,
             "sent": sent_at or datetime.now(SHANGHAI)},
        ).scalar_one()


def list_notifications(hid, headers=SERVICE_HEADERS, **params):
    r = client.get("/api/v2/notifications",
                   params={"household_id": hid, **params},
                   headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def count_notifications(db_engine, **where):
    clauses = " AND ".join(f"{k}=:{k}" for k in where) or "TRUE"
    with db_engine.connect() as conn:
        return conn.execute(
            text(f"SELECT count(*) FROM notifications WHERE {clauses}"),
            {k: (uuid.UUID(v) if isinstance(v, str) and k.endswith("_id")
                 else v) for k, v in where.items()},
        ).scalar_one()


def get_item(db_engine, item_id):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT status, auto_expiry_date, consumed_at"
                 " FROM inventory_items WHERE id=:iid"),
            {"iid": item_id},
        ).first()


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


# --- Gate B: Lazy Tracking (§9) --------------------------------------------

def test_daily_creates_lazy_and_maintenance_once(db_engine, capsys):
    hid = mk_household()
    today = today_shanghai()
    item_a = seed_item(db_engine, hid, PORK, 1, "kg", today,
                       raw_name="Thịt ba chỉ A")
    item_b = seed_item(db_engine, hid, MILK, 2, "L", today,
                       raw_name="Sữa tươi B")
    # Expiring tomorrow: no notification. Already consumed, expiring
    # today: no notification either (§6.1 matches active items only).
    seed_item(db_engine, hid, RICE, 1, "kg", today + timedelta(days=1),
              raw_name="Gạo tomorrow")
    seed_item(db_engine, hid, RICE, 1, "kg", today,
              raw_name="Gạo consumed", status="consumed")
    eq = seed_equipment(db_engine, hid, today)

    counts = daily_job.run_daily()
    assert counts == {"lazy_created": 2, "lazy_skipped": 0,
                      "maint_created": 1, "maint_skipped": 0}, counts

    rows = list_notifications(hid)
    assert len(rows) == 3
    by_ref = {r["ref_id"]: r for r in rows}
    assert set(by_ref) == {str(item_a), str(item_b), str(eq)}
    assert by_ref[str(item_a)]["type"] == "lazy_tracking"
    assert by_ref[str(item_b)]["type"] == "lazy_tracking"
    assert by_ref[str(eq)]["type"] == "maintenance_reminder"
    for r in rows:
        assert r["status"] == "sent"
        assert r["channel"] == "in_app"
        assert r["household_id"] == hid
    assert by_ref[str(item_a)]["payload_json"]["item_name"] == "Thịt ba chỉ A"
    assert by_ref[str(item_a)]["payload_json"]["actions"] == [
        "used_up", "extended"]

    # Second run: idempotent — 0 new notifications (§3.4, §6.1).
    counts2 = daily_job.run_daily()
    assert counts2 == {"lazy_created": 0, "lazy_skipped": 2,
                       "maint_created": 0, "maint_skipped": 1}, counts2
    assert len(list_notifications(hid)) == 3

    # The cron log summary line (§6.1 step 3) names created/skipped.
    assert daily_job.main() == 0
    out = capsys.readouterr().out
    assert "daily scan done:" in out
    assert "lazy_tracking created=0 skipped=2" in out
    assert "maintenance_reminder created=0 skipped=1" in out


def test_respond_used_up_consumes_item(db_engine):
    hid = mk_household()
    today = today_shanghai()
    item = seed_item(db_engine, hid, PORK, 1, "kg", today)
    assert daily_job.run_daily()["lazy_created"] == 1
    notif = list_notifications(hid, type="lazy_tracking")[0]

    r = client.post(f"/api/v2/notifications/{notif['id']}/respond",
                    json={"response": "used_up"}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "responded"
    assert body["response"] == "used_up"
    assert body["responded_at"] is not None

    status, _expiry, consumed_at = get_item(db_engine, item)
    assert status == "consumed"
    assert consumed_at is not None

    # Responding again -> 409 (§5.2: responded is terminal).
    r = client.post(f"/api/v2/notifications/{notif['id']}/respond",
                    json={"response": "used_up"}, headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text


def test_respond_extended_adds_days(db_engine):
    hid = mk_household()
    today = today_shanghai()
    item_default = seed_item(db_engine, hid, PORK, 1, "kg", today)
    item_five = seed_item(db_engine, hid, MILK, 2, "L", today)
    assert daily_job.run_daily()["lazy_created"] == 2
    notifs = {n["ref_id"]: n for n in
              list_notifications(hid, type="lazy_tracking")}
    assert len(notifs) == 2

    r = client.post(
        f"/api/v2/notifications/{notifs[str(item_default)]['id']}/respond",
        json={"response": "extended"}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "responded"
    assert r.json()["response"] == "extended"
    assert get_item(db_engine, item_default)[1] == today + timedelta(days=3)

    r = client.post(
        f"/api/v2/notifications/{notifs[str(item_five)]['id']}/respond",
        json={"response": "extended", "days": 5}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert get_item(db_engine, item_five)[1] == today + timedelta(days=5)

    # Either notification answered a second time -> 409.
    r = client.post(
        f"/api/v2/notifications/{notifs[str(item_default)]['id']}/respond",
        json={"response": "extended"}, headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text


def test_no_resend_after_two_days_unanswered(db_engine):
    hid = mk_household()
    today = today_shanghai()
    item = seed_item(db_engine, hid, PORK, 1, "kg", today)
    # An open lazy_tracking notification sent 2 days ago, never
    # answered: §3.4 says no re-send in Phase 2.
    sent_ago = datetime.now(SHANGHAI) - timedelta(days=2)
    seed_notification(db_engine, hid, "lazy_tracking", "inventory_item",
                      item, sent_at=sent_ago)
    assert count_notifications(db_engine, ref_id=str(item)) == 1

    counts = daily_job.run_daily()
    assert counts["lazy_created"] == 0
    assert counts["lazy_skipped"] == 1
    assert count_notifications(db_engine, ref_id=str(item)) == 1


def test_respond_consumed_item_409(db_engine):
    hid = mk_household()
    today = today_shanghai()
    item = seed_item(db_engine, hid, PORK, 1, "kg", today)
    assert daily_job.run_daily()["lazy_created"] == 1
    notif = list_notifications(hid, type="lazy_tracking")[0]
    r = client.post(f"/api/v2/fridge/{item}/consume", headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    # The linked item is already consumed: respond -> 409 (§6.2).
    r = client.post(f"/api/v2/notifications/{notif['id']}/respond",
                    json={"response": "used_up"}, headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text
    assert list_notifications(hid)[0]["status"] == "sent"


# --- Gate C: shopping lists (§9) -------------------------------------------

def _seed_recipe_household(db_engine):
    """Household + recipe: rice sufficient, pork partial, milk missing."""
    hid = mk_household()
    today = today_shanghai()
    seed_item(db_engine, hid, RICE, 5, "kg", today + timedelta(days=10))
    seed_item(db_engine, hid, PORK, 0.4, "kg", today + timedelta(days=10))
    rid = seed_recipe(db_engine, hid, [
        (RICE, "Gạo", 2, "kg"),
        (PORK, "Thịt ba chỉ", 1, "kg"),
        (MILK, "Sữa tươi", 2, "L"),
    ])
    return hid, rid


def test_from_recipe_generates_only_missing(db_engine):
    hid, rid = _seed_recipe_household(db_engine)
    r = client.post("/api/v2/shopping-lists/from-recipe",
                    json={"household_id": hid, "recipe_id": str(rid)},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "open"
    assert body["source_recipe_id"] == str(rid)
    items = {i["raw_name"]: i for i in body["items"]}
    # Rice is fully in the fridge (5 kg >= 2 kg): NO item (§3.2).
    assert "Gạo" not in items
    # Pork is partial: shortfall only (1 - 0.4 = 0.6 kg).
    assert set(items) == {"Thịt ba chỉ", "Sữa tươi"}
    assert items["Thịt ba chỉ"]["amount"] == 0.6
    assert items["Thịt ba chỉ"]["unit"] == "kg"
    assert items["Thịt ba chỉ"]["checked"] is False
    # Milk is missing entirely: full amount.
    assert items["Sữa tươi"]["amount"] == 2
    assert items["Sữa tươi"]["unit"] == "L"


def test_create_with_source_recipe_id_generates_same(db_engine):
    hid, rid = _seed_recipe_household(db_engine)
    r = client.post("/api/v2/shopping-lists",
                    json={"household_id": hid, "source_recipe_id": str(rid)},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    items = {i["raw_name"]: i for i in r.json()["items"]}
    assert set(items) == {"Thịt ba chỉ", "Sữa tươi"}
    assert items["Thịt ba chỉ"]["amount"] == 0.6
    assert items["Sữa tươi"]["amount"] == 2


def test_shopping_list_complete_flow(db_engine):
    hid = mk_household()
    r = client.post("/api/v2/shopping-lists", json={"household_id": hid},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    lst = r.json()
    assert lst["status"] == "open"
    assert lst["items"] == []
    lid = lst["id"]

    # Add 1 item by hand, tick it, then complete the list.
    r = client.post(f"/api/v2/shopping-lists/{lid}/items",
                    json={"raw_name": "Trứng gà", "amount": 1, "unit": "hộp"},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["checked"] is False

    r = client.patch(f"/api/v2/shopping-lists/{lid}/items/{item['id']}",
                     json={"checked": True}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["checked"] is True

    r = client.post(f"/api/v2/shopping-lists/{lid}/complete",
                    headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert r.json()["completed_at"] is not None
    assert r.json()["items"][0]["checked"] is True

    # Completing again -> 409 (open -> done is terminal, §5.2).
    r = client.post(f"/api/v2/shopping-lists/{lid}/complete",
                    headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text

    # A done list frees the one-open-list slot: a new list is 201.
    r = client.post("/api/v2/shopping-lists", json={"household_id": hid},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    # Status filter on the list endpoint.
    lists = client.get("/api/v2/shopping-lists",
                       params={"household_id": hid, "status": "done"},
                       headers=SERVICE_HEADERS).json()
    assert [x["id"] for x in lists] == [lid]
    lists = client.get("/api/v2/shopping-lists",
                       params={"household_id": hid, "status": "open"},
                       headers=SERVICE_HEADERS).json()
    assert len(lists) == 1 and lists[0]["id"] != lid


def test_second_open_list_409(db_engine):
    hid, rid = _seed_recipe_household(db_engine)
    r = client.post("/api/v2/shopping-lists", json={"household_id": hid},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    # A second open list -> 409 (§3.2), by either creation route.
    r = client.post("/api/v2/shopping-lists", json={"household_id": hid},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text
    r = client.post("/api/v2/shopping-lists/from-recipe",
                    json={"household_id": hid, "recipe_id": str(rid)},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text


def test_from_recipe_unknown_recipe_404(db_engine):
    hid = mk_household()
    unknown = str(uuid.uuid4())
    r = client.post("/api/v2/shopping-lists/from-recipe",
                    json={"household_id": hid, "recipe_id": unknown},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 404, r.text
    r = client.post("/api/v2/shopping-lists",
                    json={"household_id": hid, "source_recipe_id": unknown},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 404, r.text


def test_shopping_list_403_other_household(db_engine):
    hid = mk_household()
    r = client.post("/api/v2/shopping-lists", json={"household_id": hid},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    other = other_user_headers(db_engine)
    # List, create, items, complete — all 403 for another household.
    assert client.get(f"/api/v2/shopping-lists/{lid}",
                      headers=other).status_code == 403
    assert client.get("/api/v2/shopping-lists",
                      params={"household_id": hid},
                      headers=other).status_code == 403
    assert client.post("/api/v2/shopping-lists",
                       json={"household_id": hid},
                       headers=other).status_code == 403
    assert client.post(f"/api/v2/shopping-lists/{lid}/items",
                       json={"raw_name": "X"}, headers=other).status_code == 403
    assert client.post(f"/api/v2/shopping-lists/{lid}/complete",
                       headers=other).status_code == 403
    assert client.patch(f"/api/v2/shopping-lists/{lid}",
                        json={"status": "done"},
                        headers=other).status_code == 403
    assert client.delete(f"/api/v2/shopping-lists/{lid}",
                         headers=other).status_code == 403
    # Unknown list id -> 404 (with the owning credentials).
    assert client.get(f"/api/v2/shopping-lists/{uuid.uuid4()}",
                      headers=SERVICE_HEADERS).status_code == 404
    assert client.post(f"/api/v2/shopping-lists/{uuid.uuid4()}/complete",
                       headers=SERVICE_HEADERS).status_code == 404
    # The list is untouched.
    assert client.get(f"/api/v2/shopping-lists/{lid}",
                      headers=SERVICE_HEADERS).status_code == 200


def test_shopping_list_patch_delete_and_items(db_engine):
    hid = mk_household()
    r = client.post("/api/v2/shopping-lists", json={"household_id": hid},
                    headers=SERVICE_HEADERS)
    lid = r.json()["id"]

    def add(raw_name, amount, unit):
        r = client.post(f"/api/v2/shopping-lists/{lid}/items",
                        json={"raw_name": raw_name, "amount": amount,
                              "unit": unit}, headers=SERVICE_HEADERS)
        assert r.status_code == 201, r.text
        return r.json()

    item_a = add("Trứng gà", 1, "hộp")
    item_b = add("Rau cải", 0.5, "kg")
    # Item PATCH: amount + unit.
    r = client.patch(
        f"/api/v2/shopping-lists/{lid}/items/{item_b['id']}",
        json={"amount": 1.5, "unit": "kg"}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 1.5
    # Item PATCH with nothing -> 400; unknown item -> 404.
    assert client.patch(
        f"/api/v2/shopping-lists/{lid}/items/{item_b['id']}",
        json={}, headers=SERVICE_HEADERS).status_code == 400
    assert client.patch(
        f"/api/v2/shopping-lists/{lid}/items/{uuid.uuid4()}",
        json={"checked": True}, headers=SERVICE_HEADERS).status_code == 404
    # Item DELETE -> 204 and the item is gone from the list.
    r = client.delete(
        f"/api/v2/shopping-lists/{lid}/items/{item_a['id']}",
        headers=SERVICE_HEADERS)
    assert r.status_code == 204, r.text
    got = client.get(f"/api/v2/shopping-lists/{lid}",
                     headers=SERVICE_HEADERS).json()
    assert [i["id"] for i in got["items"]] == [item_b["id"]]

    # PATCH list to done works (§5.1); PATCH again -> 409.
    r = client.patch(f"/api/v2/shopping-lists/{lid}",
                     json={"status": "done"}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert r.json()["completed_at"] is not None
    r = client.patch(f"/api/v2/shopping-lists/{lid}",
                     json={"status": "done"}, headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text
    # Adding to a done list -> 409.
    r = client.post(f"/api/v2/shopping-lists/{lid}/items",
                    json={"raw_name": "Muối"}, headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text

    # DELETE list -> 204, then it is gone.
    r = client.delete(f"/api/v2/shopping-lists/{lid}",
                      headers=SERVICE_HEADERS)
    assert r.status_code == 204, r.text
    assert client.get(f"/api/v2/shopping-lists/{lid}",
                      headers=SERVICE_HEADERS).status_code == 404


# --- Fridge (§5.1, §5.2) ---------------------------------------------------

def test_fridge_list_days_left_and_filters(db_engine):
    hid = mk_household()
    today = today_shanghai()
    item_future = seed_item(db_engine, hid, PORK, 1, "kg",
                            today + timedelta(days=5))
    item_past = seed_item(db_engine, hid, MILK, 1, "L",
                          today - timedelta(days=2))
    item_soon = seed_item(db_engine, hid, RICE, 1, "kg",
                          today + timedelta(days=2))
    item_consumed = seed_item(db_engine, hid, RICE, 1, "kg",
                              today + timedelta(days=1), status="consumed")

    r = client.get("/api/v2/fridge", params={"household_id": hid},
                   headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    rows = {x["id"]: x for x in r.json()}
    # Default status=active excludes the consumed item.
    assert set(rows) == {str(item_future), str(item_past), str(item_soon)}
    assert rows[str(item_future)]["days_left"] == 5
    assert rows[str(item_past)]["days_left"] == -2
    assert rows[str(item_soon)]["days_left"] == 2
    assert rows[str(item_future)]["canonical_name"] == PORK
    assert rows[str(item_past)]["canonical_name"] == MILK

    # status=consumed returns only the consumed item.
    r = client.get("/api/v2/fridge",
                   params={"household_id": hid, "status": "consumed"},
                   headers=SERVICE_HEADERS)
    assert [x["id"] for x in r.json()] == [str(item_consumed)]

    # expiring_within_days=3: only the item expiring in 2 days
    # (past expiry and +5 days are both out of [today, today+3]).
    r = client.get("/api/v2/fridge",
                   params={"household_id": hid, "expiring_within_days": 3},
                   headers=SERVICE_HEADERS)
    assert [x["id"] for x in r.json()] == [str(item_soon)]

    # Another household's fridge -> 403.
    other = other_user_headers(db_engine)
    assert client.get("/api/v2/fridge", params={"household_id": hid},
                      headers=other).status_code == 403


def test_fridge_consume(db_engine):
    hid = mk_household()
    today = today_shanghai()
    item = seed_item(db_engine, hid, PORK, 1, "kg", today + timedelta(days=3))
    r = client.post(f"/api/v2/fridge/{item}/consume", headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "consumed"
    assert r.json()["consumed_at"] is not None
    # Second consume -> 409 (§5.4).
    r = client.post(f"/api/v2/fridge/{item}/consume", headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text
    # Unknown item -> 404; another household's item -> 403.
    assert client.post(f"/api/v2/fridge/{uuid.uuid4()}/consume",
                       headers=SERVICE_HEADERS).status_code == 404
    other = other_user_headers(db_engine)
    assert client.post(f"/api/v2/fridge/{item}/consume",
                       headers=other).status_code == 403


def test_fridge_extend(db_engine):
    hid = mk_household()
    today = today_shanghai()
    item_five = seed_item(db_engine, hid, PORK, 1, "kg", today)
    item_default = seed_item(db_engine, hid, MILK, 1, "L", today)
    item_consumed = seed_item(db_engine, hid, RICE, 1, "kg", today,
                              status="consumed")

    r = client.post(f"/api/v2/fridge/{item_five}/extend",
                    json={"days": 5}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["auto_expiry_date"] == (
        today + timedelta(days=5)).isoformat()

    # Default extend is +3 days (§5.1).
    r = client.post(f"/api/v2/fridge/{item_default}/extend",
                    json={}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["auto_expiry_date"] == (
        today + timedelta(days=3)).isoformat()

    # Extend a consumed item -> 409; unknown item -> 404; days=0 -> 400.
    assert client.post(f"/api/v2/fridge/{item_consumed}/extend",
                       json={"days": 3},
                       headers=SERVICE_HEADERS).status_code == 409
    assert client.post(f"/api/v2/fridge/{uuid.uuid4()}/extend",
                       json={"days": 3},
                       headers=SERVICE_HEADERS).status_code == 404
    assert client.post(f"/api/v2/fridge/{item_five}/extend",
                       json={"days": 0},
                       headers=SERVICE_HEADERS).status_code == 400


# --- Notifications list + respond validation (§5.1, §5.4, §6.2) ------------

def test_notifications_list_filters(db_engine):
    hid = mk_household()
    today = today_shanghai()
    item_a = seed_item(db_engine, hid, PORK, 1, "kg", today)
    item_b = seed_item(db_engine, hid, MILK, 1, "L", today)
    eq = seed_equipment(db_engine, hid, today)
    assert daily_job.run_daily()["lazy_created"] == 2
    # One older maintenance notification for a *different* equipment,
    # inserted directly (a second open reminder for the same equipment
    # would violate ux_notifications_open_maint, §3.4).
    eq2 = seed_equipment(db_engine, hid, today + timedelta(days=10),
                         brand_model="Test Fridge")
    old = datetime.now(SHANGHAI) - timedelta(hours=5)
    seed_notification(db_engine, hid, "maintenance_reminder", "equipment",
                      eq2, sent_at=old)

    rows = list_notifications(hid)
    assert len(rows) == 4
    # Newest first: the two just-created lazy rows and the daily
    # maintenance row precede the 5-hour-old one.
    assert rows[-1]["ref_id"] == str(eq2)
    assert {r["ref_id"] for r in rows[:3]} == {
        str(item_a), str(item_b), str(eq)}

    assert len(list_notifications(hid, type="lazy_tracking")) == 2
    assert len(list_notifications(hid, type="maintenance_reminder")) == 2
    assert len(list_notifications(hid, status="sent")) == 4
    assert list_notifications(hid, status="responded") == []
    assert list_notifications(hid, type="system") == []

    # Another household's notifications -> 403.
    other = other_user_headers(db_engine)
    assert client.get("/api/v2/notifications",
                      params={"household_id": hid},
                      headers=other).status_code == 403


def test_respond_validation(db_engine):
    hid = mk_household()
    today = today_shanghai()
    item = seed_item(db_engine, hid, PORK, 1, "kg", today)
    eq = seed_equipment(db_engine, hid, today)
    counts = daily_job.run_daily()
    assert counts["lazy_created"] == 1 and counts["maint_created"] == 1
    lazy = list_notifications(hid, type="lazy_tracking")[0]
    maint = list_notifications(hid, type="maintenance_reminder")[0]
    other = other_user_headers(db_engine)

    # Bad response value -> 400 (§5.4).
    r = client.post(f"/api/v2/notifications/{lazy['id']}/respond",
                    json={"response": "maybe"}, headers=SERVICE_HEADERS)
    assert r.status_code == 400, r.text
    # extended with days=31 -> 400 (§6.2: max 30).
    r = client.post(f"/api/v2/notifications/{lazy['id']}/respond",
                    json={"response": "extended", "days": 31},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 400, r.text
    # Responding a maintenance_reminder -> 409 (lazy_tracking only).
    r = client.post(f"/api/v2/notifications/{maint['id']}/respond",
                    json={"response": "used_up"}, headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text
    # Unknown notification id -> 404.
    r = client.post(f"/api/v2/notifications/{uuid.uuid4()}/respond",
                    json={"response": "used_up"}, headers=SERVICE_HEADERS)
    assert r.status_code == 404, r.text
    # Another household's notification -> 403.
    r = client.post(f"/api/v2/notifications/{lazy['id']}/respond",
                    json={"response": "used_up"}, headers=other)
    assert r.status_code == 403, r.text
    # Nothing above changed the notification or the item.
    assert list_notifications(hid, type="lazy_tracking")[0]["status"] == "sent"
    assert get_item(db_engine, item)[0] == "fresh"


# --- send_wechat skip path (§8) --------------------------------------------

def test_send_wechat_skips_without_config_and_touches_nothing(db_engine):
    hid = mk_household()
    today = today_shanghai()
    seed_item(db_engine, hid, PORK, 1, "kg", today)
    assert daily_job.run_daily()["lazy_created"] == 1
    before = count_notifications(db_engine, household_id=str(hid))
    assert before == 1

    env = {k: v for k, v in os.environ.items()
           if not k.startswith("WECHAT_")}
    env["DATABASE_URL"] = _test_url()
    proc = subprocess.run(
        [sys.executable, "-m", "app.jobs.send_wechat"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "send_wechat skipped" in proc.stdout
    assert "missing WeChat config" in proc.stdout
    # No notification row was created, modified or deleted.
    assert count_notifications(db_engine, household_id=str(hid)) == 1
    assert list_notifications(hid)[0]["status"] == "sent"
    assert list_notifications(hid)[0]["channel"] == "in_app"
