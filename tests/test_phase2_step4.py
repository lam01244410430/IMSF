"""Phase 2 Step 4 tests: equipment maintenance + ledger (design §3.5,
§5.1, §5.6, §6.4, §9 Gate D).

Runs against the disposable ``imsf_v2_test`` database (same pattern as
the Step 2/3 test files) so the dev DB is never touched. Maintenance
logging is exercised over HTTP via the TestClient; the ledger link is
verified both through the maintenance response and by direct SQL count
on ``transactions``.

Contract notes (from the coordinator brief + Worker A implementation):
- POST /api/v2/equipments/{id}/maintenance returns 201 with
  {log, equipment, transaction}; ``transaction`` is null when no cost
  was logged (the brief does not pin the status code; 201 matches the
  other POST-create endpoints in this codebase).
- ``type`` <-> ``device_type``, ``name`` <-> ``brand_model``.
- Missing ``type`` on equipment create -> 400 (explicit check in the
  implementation, matching the brief; design §5.1 writes ``type?`` but
  the brief pins it required).
- A zero cost creates no transaction (transactions.amount CHECK > 0);
  only cost > 0 creates one. Tests here use cost > 0.
"""

import os
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import jwt
import pytest
import sqlalchemy as sa
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent

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

SHANGHAI = ZoneInfo("Asia/Shanghai")

PERFORMED_1 = "2026-11-10T10:00:00+08:00"
PERFORMED_2 = "2026-12-01T09:00:00+08:00"


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


def mk_equipment(hid, **overrides):
    body = {"household_id": hid, "name": "Daikin FTXM",
            "type": "air_conditioner"}
    body.update(overrides)
    r = client.post("/api/v2/equipments", json=body,
                    headers=SERVICE_HEADERS)
    assert r.status_code == 201, r.text
    return r.json()


def get_equipment(eid, headers=SERVICE_HEADERS):
    return client.get(f"/api/v2/equipments/{eid}", headers=headers)


def list_equipments(hid, headers=SERVICE_HEADERS):
    r = client.get("/api/v2/equipments", params={"household_id": hid},
                   headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def log_maintenance(eid, headers=SERVICE_HEADERS, **overrides):
    body = {"performed_at": PERFORMED_1, "maintenance_type": "cleaning"}
    body.update(overrides)
    return client.post(f"/api/v2/equipments/{eid}/maintenance",
                       json=body, headers=headers)


def list_history(eid, headers=SERVICE_HEADERS, **params):
    r = client.get(f"/api/v2/equipments/{eid}/maintenance",
                   params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def count_maintenance_transactions(db_engine, hid):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM transactions"
                 " WHERE household_id=:h AND category='maintenance'"),
            {"h": uuid.UUID(hid)},
        ).scalar_one()


def maintenance_transactions(db_engine, hid):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT id, type, amount, currency, occurred_at,"
                 " receipt_id FROM transactions"
                 " WHERE household_id=:h AND category='maintenance'"
                 " ORDER BY occurred_at"),
            {"h": uuid.UUID(hid)},
        ).all()


def count_logs(db_engine, eid):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM equipment_maintenance_logs"
                 " WHERE equipment_id=:eid"),
            {"eid": uuid.UUID(eid)},
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


# --- Gate D: maintenance + ledger (§9) -------------------------------------

def test_maintenance_with_cost_creates_transaction_and_updates_dates(
        db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, maintenance_interval_days=90)
    eid = eq["id"]
    assert eq["status"] == "active"
    assert eq["last_maintained_at"] is None
    assert eq["next_maintenance_date"] is None

    r = log_maintenance(eid, cost=120.50, currency="CNY",
                        maintenance_type="filter_replace",
                        note="thay lọc gió")
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"log", "equipment", "transaction"}

    log = body["log"]
    assert log["equipment_id"] == eid
    assert log["maintenance_type"] == "filter_replace"
    assert log["note"] == "thay lọc gió"
    assert log["cost"] == 120.50
    assert log["currency"] == "CNY"
    assert datetime.fromisoformat(log["performed_at"]) == \
        datetime.fromisoformat(PERFORMED_1)

    # §3.5: last_maintained_at = performed_at; next = performed date
    # + interval (2026-11-10 + 90 days = 2027-02-08).
    equip = body["equipment"]
    assert datetime.fromisoformat(equip["last_maintained_at"]) == \
        datetime.fromisoformat(PERFORMED_1)
    assert equip["next_maintenance_date"] == "2027-02-08"

    # Exactly 1 maintenance transaction, linked from the log (§3.5).
    assert count_maintenance_transactions(db_engine, hid) == 1
    txn = body["transaction"]
    assert txn is not None
    assert txn["id"] == log["transaction_id"]
    assert txn["type"] == "expense"
    assert txn["category"] == "maintenance"
    assert txn["amount"] == 120.50
    assert txn["currency"] == "CNY"
    assert txn["receipt_id"] is None
    assert datetime.fromisoformat(txn["occurred_at"]) == \
        datetime.fromisoformat(PERFORMED_1)
    rows = maintenance_transactions(db_engine, hid)
    assert len(rows) == 1
    assert str(rows[0][0]) == txn["id"]
    assert float(rows[0][2]) == 120.50

    # The equipment row itself (GET) agrees with the response.
    got = get_equipment(eid)
    assert got.status_code == 200, got.text
    assert got.json()["last_maintained_at"] == \
        equip["last_maintained_at"]
    assert got.json()["next_maintenance_date"] == "2027-02-08"


def test_maintenance_without_cost_creates_no_transaction(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, maintenance_interval_days=90)
    eid = eq["id"]

    r = log_maintenance(eid, maintenance_type="cleaning")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["transaction"] is None
    assert body["log"]["transaction_id"] is None
    assert body["log"]["cost"] is None
    assert body["log"]["currency"] is None
    assert count_maintenance_transactions(db_engine, hid) == 0
    assert count_logs(db_engine, eid) == 1
    # Dates are still updated even without a cost.
    assert datetime.fromisoformat(
        body["equipment"]["last_maintained_at"]) == \
        datetime.fromisoformat(PERFORMED_1)
    assert body["equipment"]["next_maintenance_date"] == "2027-02-08"


def test_second_maintenance_updates_dates_and_history(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, maintenance_interval_days=90)
    eid = eq["id"]

    r1 = log_maintenance(eid, cost=50.00, currency="CNY")
    assert r1.status_code == 201, r1.text
    r2 = log_maintenance(eid, performed_at=PERFORMED_2, cost=80.00,
                         currency="CNY", maintenance_type="repair")
    assert r2.status_code == 201, r2.text

    # Dates updated again from the later performed_at:
    # 2026-12-01 + 90 days = 2027-03-01.
    equip = r2.json()["equipment"]
    assert datetime.fromisoformat(equip["last_maintained_at"]) == \
        datetime.fromisoformat(PERFORMED_2)
    assert equip["next_maintenance_date"] == "2027-03-01"

    # History: 2 logs, newest first.
    history = list_history(eid)
    assert len(history) == 2
    assert history[0]["id"] == r2.json()["log"]["id"]
    assert history[1]["id"] == r1.json()["log"]["id"]
    assert datetime.fromisoformat(history[0]["performed_at"]) == \
        datetime.fromisoformat(PERFORMED_2)
    assert history[0]["maintenance_type"] == "repair"
    assert history[0]["cost"] == 80.00
    assert history[1]["cost"] == 50.00

    # One transaction per costed maintenance (2 total, in order).
    assert count_maintenance_transactions(db_engine, hid) == 2
    rows = maintenance_transactions(db_engine, hid)
    assert [float(r[2]) for r in rows] == [50.00, 80.00]
    assert str(rows[0][0]) == r1.json()["log"]["transaction_id"]
    assert str(rows[1][0]) == r2.json()["log"]["transaction_id"]
    # The second log links to the second transaction, not the first.
    assert history[0]["transaction_id"] == str(rows[1][0])
    assert history[1]["transaction_id"] == str(rows[0][0])


def test_maintenance_null_interval_next_date_stays_null(db_engine):
    hid = mk_household()
    # No maintenance_interval_days -> NULL interval.
    eq = mk_equipment(hid)
    assert eq["maintenance_interval_days"] is None
    eid = eq["id"]

    r = log_maintenance(eid, maintenance_type="inspection")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["equipment"]["next_maintenance_date"] is None
    assert datetime.fromisoformat(
        body["equipment"]["last_maintained_at"]) == \
        datetime.fromisoformat(PERFORMED_1)
    assert body["log"]["id"] is not None
    assert count_logs(db_engine, eid) == 1


def test_maintenance_validation(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, maintenance_interval_days=90)
    eid = eq["id"]

    # Cost without currency -> 400 (§5.4).
    r = log_maintenance(eid, cost=50.00)
    assert r.status_code == 400, r.text
    # Cost negative -> 400/422.
    r = log_maintenance(eid, cost=-10.00, currency="CNY")
    assert r.status_code in (400, 422), r.text
    # Bad currency -> 400/422 (USD is valid since P2-06).
    r = log_maintenance(eid, cost=50.00, currency="XXX")
    assert r.status_code in (400, 422), r.text
    # Bad maintenance_type -> 422.
    r = log_maintenance(eid, maintenance_type="deep_clean")
    assert r.status_code == 422, r.text
    # Missing performed_at -> 422.
    r = client.post(f"/api/v2/equipments/{eid}/maintenance",
                    json={"maintenance_type": "cleaning"},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 422, r.text
    # Missing type on equipment create -> 400.
    r = client.post("/api/v2/equipments",
                    json={"household_id": hid, "name": "No type"},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 400, r.text
    # Missing household_id on equipment create -> 422.
    r = client.post("/api/v2/equipments",
                    json={"name": "X", "type": "air_conditioner"},
                    headers=SERVICE_HEADERS)
    assert r.status_code == 422, r.text

    # None of the invalid attempts created a log or a transaction.
    assert count_logs(db_engine, eid) == 0
    assert count_maintenance_transactions(db_engine, hid) == 0
    assert list_history(eid) == []
    # The equipment itself is unchanged (no dates set).
    got = get_equipment(eid).json()
    assert got["last_maintained_at"] is None
    assert got["next_maintenance_date"] is None


def test_maintenance_history_order_and_limit(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, maintenance_interval_days=90)
    eid = eq["id"]
    log_maintenance(eid, maintenance_type="cleaning")
    log_maintenance(eid, performed_at=PERFORMED_2,
                    maintenance_type="inspection")

    history = list_history(eid)
    assert [datetime.fromisoformat(h["performed_at"]) for h in history] == [
        datetime.fromisoformat(PERFORMED_2),
        datetime.fromisoformat(PERFORMED_1)]
    # limit=1 returns exactly the newest log.
    page = list_history(eid, limit=1)
    assert len(page) == 1
    assert page[0]["id"] == history[0]["id"]
    # offset=1 returns the older log.
    page2 = list_history(eid, limit=1, offset=1)
    assert len(page2) == 1
    assert page2[0]["id"] == history[1]["id"]


def test_unknown_equipment_404(db_engine):
    unknown = str(uuid.uuid4())
    assert get_equipment(unknown).status_code == 404
    assert client.patch(f"/api/v2/equipments/{unknown}",
                        json={"status": "retired"},
                        headers=SERVICE_HEADERS).status_code == 404
    assert client.delete(f"/api/v2/equipments/{unknown}",
                         headers=SERVICE_HEADERS).status_code == 404
    assert log_maintenance(unknown).status_code == 404
    r = client.get(f"/api/v2/equipments/{unknown}/maintenance",
                   headers=SERVICE_HEADERS)
    assert r.status_code == 404, r.text


def test_equipments_403_other_household(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, maintenance_interval_days=90)
    eid = eq["id"]
    log_maintenance(eid, cost=10.00, currency="CNY")
    other = other_user_headers(db_engine)

    assert client.get("/api/v2/equipments",
                      params={"household_id": hid},
                      headers=other).status_code == 403
    assert client.post("/api/v2/equipments",
                       json={"household_id": hid, "name": "X",
                             "type": "air_conditioner"},
                       headers=other).status_code == 403
    assert get_equipment(eid, headers=other).status_code == 403
    assert client.patch(f"/api/v2/equipments/{eid}",
                        json={"status": "retired"},
                        headers=other).status_code == 403
    assert client.delete(f"/api/v2/equipments/{eid}",
                         headers=other).status_code == 403
    assert log_maintenance(eid, headers=other).status_code == 403
    r = client.get(f"/api/v2/equipments/{eid}/maintenance", headers=other)
    assert r.status_code == 403, r.text
    # A household id that belongs to nobody -> 403 as well.
    assert client.get("/api/v2/equipments",
                      params={"household_id": str(uuid.uuid4())},
                      headers=SERVICE_HEADERS).status_code == 403
    # Nothing above changed the equipment, its log or its transaction.
    assert get_equipment(eid).json()["status"] == "active"
    assert count_logs(db_engine, eid) == 1
    assert count_maintenance_transactions(db_engine, hid) == 1


def test_delete_with_logs_409_without_logs_204(db_engine):
    hid = mk_household()
    with_logs = mk_equipment(hid, name="With logs",
                             type="air_conditioner")
    log_maintenance(with_logs["id"], cost=10.00, currency="CNY")
    without_logs = mk_equipment(hid, name="No logs",
                                type="range_hood")

    r = client.delete(f"/api/v2/equipments/{with_logs['id']}",
                      headers=SERVICE_HEADERS)
    assert r.status_code == 409, r.text
    # The equipment (and its log) still exists after the 409.
    assert get_equipment(with_logs["id"]).status_code == 200
    assert count_logs(db_engine, with_logs["id"]) == 1

    r = client.delete(f"/api/v2/equipments/{without_logs['id']}",
                      headers=SERVICE_HEADERS)
    assert r.status_code == 204, r.text
    assert get_equipment(without_logs["id"]).status_code == 404


def test_patch_interval_recomputes_next_date_and_status_retired(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, maintenance_interval_days=90)
    eid = eq["id"]
    log_maintenance(eid, cost=10.00, currency="CNY")
    assert get_equipment(eid).json()["next_maintenance_date"] == "2027-02-08"

    # §6.4: changing the interval recomputes the next date from
    # last_maintained_at (2026-11-10 + 30 days = 2026-12-10).
    r = client.patch(f"/api/v2/equipments/{eid}",
                     json={"maintenance_interval_days": 30},
                     headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["maintenance_interval_days"] == 30
    assert r.json()["next_maintenance_date"] == "2026-12-10"
    assert datetime.fromisoformat(r.json()["last_maintained_at"]) == \
        datetime.fromisoformat(PERFORMED_1)

    # PATCH status -> retired works.
    r = client.patch(f"/api/v2/equipments/{eid}",
                     json={"status": "retired"}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "retired"
    assert r.json()["next_maintenance_date"] == "2026-12-10"


def test_patch_interval_without_last_maintained_keeps_next_null(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid)
    eid = eq["id"]
    assert eq["next_maintenance_date"] is None
    # No last_maintained_at yet: §6.4 recompute has nothing to work
    # from, so the next date stays NULL while the interval is stored.
    r = client.patch(f"/api/v2/equipments/{eid}",
                     json={"maintenance_interval_days": 60},
                     headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["maintenance_interval_days"] == 60
    assert r.json()["next_maintenance_date"] is None


def test_list_days_until_maintenance(db_engine):
    hid = mk_household()
    today = today_shanghai()
    # Equipment A: next date 2027-02-08 via a maintenance log.
    eq_a = mk_equipment(hid, name="A", type="air_conditioner",
                        maintenance_interval_days=90)
    log_maintenance(eq_a["id"], cost=10.00, currency="CNY")
    # Equipment B: no next date at all.
    eq_b = mk_equipment(hid, name="B", type="range_hood")

    rows = list_equipments(hid)
    assert len(rows) == 2
    # Newest first: B was created after A.
    assert [r["id"] for r in rows] == [eq_b["id"], eq_a["id"]]
    by_id = {r["id"]: r for r in rows}
    expected_days = (date(2027, 2, 8) - today).days
    assert by_id[eq_a["id"]]["next_maintenance_date"] == "2027-02-08"
    assert by_id[eq_a["id"]]["days_until_maintenance"] == expected_days
    assert by_id[eq_b["id"]]["next_maintenance_date"] is None
    assert by_id[eq_b["id"]]["days_until_maintenance"] is None


def test_maintenance_on_retired_equipment_allowed(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, maintenance_interval_days=90)
    eid = eq["id"]
    r = client.patch(f"/api/v2/equipments/{eid}",
                     json={"status": "retired"}, headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "retired"

    # The design does not forbid logging maintenance on a retired
    # equipment (§3.5/§6.4 set no status gate): it must succeed and
    # update the dates + ledger exactly like on an active one.
    r = log_maintenance(eid, cost=25.00, currency="VND",
                        maintenance_type="repair")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["equipment"]["status"] == "retired"
    assert body["equipment"]["next_maintenance_date"] == "2027-02-08"
    assert body["transaction"] is not None
    assert body["transaction"]["currency"] == "VND"
    assert body["transaction"]["amount"] == 25.00
    assert count_maintenance_transactions(db_engine, hid) == 1


# --- Equipment CRUD + PATCH coverage (§5.1, §5.6) --------------------------

def test_equipment_crud_name_type_mapping_and_defaults(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, name="Daikin FTXM", type="air_conditioner",
                      usage_per_week=3, maintenance_interval_days=90)
    # Responses carry both name and type, mapped from brand_model /
    # device_type (§5.6).
    assert eq["name"] == "Daikin FTXM"
    assert eq["type"] == "air_conditioner"
    assert eq["brand_model"] == "Daikin FTXM"
    assert eq["device_type"] == "air_conditioner"
    assert eq["status"] == "active"
    assert eq["usage_per_week"] == 3
    assert eq["maintenance_interval_days"] == 90
    assert eq["household_id"] == hid
    assert eq["days_until_maintenance"] is None

    # GET by id returns the same row.
    got = get_equipment(eq["id"])
    assert got.status_code == 200, got.text
    assert got.json()["name"] == "Daikin FTXM"

    # PATCH name / type / usage fields.
    r = client.patch(f"/api/v2/equipments/{eq['id']}",
                     json={"name": "Mitsubishi MSZ", "type": "range_hood",
                           "usage_per_week": 5, "usage_intensity": "high",
                           "household_size": 4},
                     headers=SERVICE_HEADERS)
    assert r.status_code == 200, r.text
    patched = r.json()
    assert patched["name"] == "Mitsubishi MSZ"
    assert patched["type"] == "range_hood"
    assert patched["brand_model"] == "Mitsubishi MSZ"
    assert patched["device_type"] == "range_hood"
    assert patched["usage_per_week"] == 5
    assert patched["usage_intensity"] == "high"
    assert patched["household_size"] == 4
    assert patched["status"] == "active"

    # A second equipment lists newest first.
    eq2 = mk_equipment(hid, name="Second", type="washing_machine")
    rows = list_equipments(hid)
    assert [x["id"] for x in rows] == [eq2["id"], eq["id"]]


def test_patch_validation(db_engine):
    hid = mk_household()
    eq = mk_equipment(hid, maintenance_interval_days=90)
    eid = eq["id"]

    # Empty PATCH -> 400.
    r = client.patch(f"/api/v2/equipments/{eid}", json={},
                     headers=SERVICE_HEADERS)
    assert r.status_code == 400, r.text
    # Bad status -> 422.
    r = client.patch(f"/api/v2/equipments/{eid}",
                     json={"status": "broken"}, headers=SERVICE_HEADERS)
    assert r.status_code == 422, r.text
    # Bad usage_intensity -> 422.
    r = client.patch(f"/api/v2/equipments/{eid}",
                     json={"usage_intensity": "extreme"},
                     headers=SERVICE_HEADERS)
    assert r.status_code == 422, r.text
    # Interval 0 / negative usage_per_week -> 422 (pydantic bounds).
    r = client.patch(f"/api/v2/equipments/{eid}",
                     json={"maintenance_interval_days": 0},
                     headers=SERVICE_HEADERS)
    assert r.status_code == 422, r.text
    r = client.patch(f"/api/v2/equipments/{eid}",
                     json={"usage_per_week": -1}, headers=SERVICE_HEADERS)
    assert r.status_code == 422, r.text

    # Nothing above changed the equipment.
    got = get_equipment(eid).json()
    assert got["status"] == "active"
    assert got["maintenance_interval_days"] == 90
    assert got["usage_per_week"] is None
    assert got["usage_intensity"] is None
