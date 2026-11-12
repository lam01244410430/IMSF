"""P05 Step 2 PROPOSALS: date-bound reads and immutable observed provenance."""
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from test_inventory_lots import product, receipt
from test_inventory_checkout import configure_timezone, snapshot
from test_finance_transactions import query


def freeze_clock(monkeypatch, instant="2026-11-10T17:00:00+00:00"):
    from app.lifecycle import service
    calls = []
    def now():
        calls.append(instant)
        return datetime.fromisoformat(instant)
    monkeypatch.setattr(service, "utc_now", now)
    return calls


def persist_alert(f, lot, *, hid=None, kind="WARNING", local_date="2026-11-11"):
    """Direct persistence fixture only; no production producer/executor."""
    async def run():
        async with f.db() as db, db.begin():
            values = {"hid": hid or f.hid, "lid": lot["id"], "kind": kind,
                      "day": local_date, "expiry": lot["expires_on"],
                      "payload": json.dumps({"schema_version": 1, "local_date": local_date,
                                             "timezone": "Asia/Ho_Chi_Minh"})}
            values["jid"] = await db.scalar(text("""INSERT INTO scheduled_jobs
                (household_id,job_key,kind,run_after,payload) VALUES
                (:hid,:day,'INVENTORY_EXPIRY',now(),CAST(:payload AS jsonb)) RETURNING id"""), values)
            return (await db.execute(text("""INSERT INTO expiration_alerts
                (household_id,lot_id,alert_kind,local_date,expires_on_snapshot,timezone,job_id)
                VALUES (:hid,:lid,:kind,CAST(:day AS date),CAST(:expiry AS date),'Asia/Ho_Chi_Minh',:jid)
                RETURNING *"""), values)).mappings().one()
    return dict(asyncio.run(run()))


def test_freshness_thresholds_and_unknown_are_separate_from_terminal_state(f, monkeypatch):
    configure_timezone(f)
    p = product(f)
    lots = [receipt(f, p, expires_on=day).json() for day in
            ["2026-11-15", "2026-11-14", "2026-11-11", "2026-11-10", None]]
    terminal = receipt(f, p, expires_on="2026-11-10").json()
    r = f.request("POST", "/disposals", json={"allocations": [{"lot_id": terminal["id"],
        "quantity": "5", "unit_id": p["base_unit_id"]}], "reason_code": "EXPIRED"})
    assert r.status_code == 201
    before = snapshot(f)
    calls = freeze_clock(monkeypatch)
    r = f.request("GET", "/inventory/lifecycle")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["local_date"] == "2026-11-11" and body["timezone"] == "Asia/Ho_Chi_Minh"
    assert [(x["freshness"], x["days_left"]) for x in body["items"]] == [
        ("FRESH", 4), ("WARNING", 3), ("WARNING", 0), ("EXPIRED", -1), ("UNKNOWN", None), ("EXPIRED", -1)]
    assert [x["lot_id"] for x in body["items"]] == [x["id"] for x in lots] + [terminal["id"]]
    assert body["items"][-1]["terminal_state"] == "DISCARDED"
    assert body["items"][-1]["activity_state"] == "TERMINAL"
    assert Decimal(body["items"][0]["remaining_quantity"]) == 5
    assert calls == ["2026-11-10T17:00:00+00:00"]
    assert snapshot(f) == before


@pytest.mark.parametrize("zone,instant,expected", [
    ("Asia/Ho_Chi_Minh", "2026-11-10T16:59:59+00:00", "2026-11-10"),
    ("Asia/Ho_Chi_Minh", "2026-11-10T17:00:00+00:00", "2026-11-11"),
    ("America/New_York", "2026-11-01T05:59:59+00:00", "2026-11-01"),
    ("America/New_York", "2026-11-01T06:00:00+00:00", "2026-11-01"),
    ("America/New_York", "2026-03-08T06:59:59+00:00", "2026-03-08"),
    ("America/New_York", "2026-03-08T07:00:00+00:00", "2026-03-08"),
])
def test_lifecycle_midnight_dst_fold_and_gap_use_one_local_date(f, monkeypatch, zone, instant, expected):
    configure_timezone(f, zone)
    p = product(f)
    receipt(f, p, expires_on=expected)
    receipt(f, p, expires_on=expected)
    calls = freeze_clock(monkeypatch, instant)
    r = f.request("GET", "/inventory/lifecycle")
    assert r.status_code == 200, r.text
    assert r.json()["local_date"] == expected
    assert [x["local_date"] for x in r.json()["items"]] == [expected, expected]
    assert [x["days_left"] for x in r.json()["items"]] == [0, 0]
    assert len(calls) == 1


def test_same_utc_instant_uses_each_households_iana_date(f, monkeypatch):
    configure_timezone(f, "Pacific/Kiritimati")
    async def setup():
        async with f.db() as db, db.begin():
            await db.execute(text("UPDATE household_settings SET values=CAST(:v AS jsonb) WHERE household_id=:hid"),
                             {"hid": f.other_hid, "v": '{"timezone":"America/Los_Angeles"}'})
    asyncio.run(setup())
    freeze_clock(monkeypatch, "2026-11-11T00:30:00+00:00")
    assert f.request("GET", "/inventory/lifecycle").json()["local_date"] == "2026-11-11"
    r = f.client.get(f"/api/v1/households/{f.other_hid}/inventory/lifecycle", headers=f.actors["OUTSIDER"].headers)
    assert r.status_code == 200 and r.json()["local_date"] == "2026-11-10"


@pytest.mark.parametrize("zone", [None, "", "No/Such_Zone", 42, "../UTC"])
def test_expiry_reads_require_valid_timezone_without_defaults_and_scope_first(f, zone):
    configure_timezone(f, zone)
    before = query(f, "SELECT values FROM household_settings WHERE household_id=:hid")
    r = f.request("GET", "/inventory/lifecycle")
    assert r.status_code == 422 and r.json()["error_code"] == "INVENTORY_TIMEZONE_REQUIRED"
    assert query(f, "SELECT values FROM household_settings WHERE household_id=:hid") == before
    assert f.request("GET", "/inventory/lifecycle", params={"lot_id": 9223372036854775807}).status_code == 404
    assert f.request("GET", "/inventory/lifecycle", role="OUTSIDER").status_code == 404
    assert f.request("GET", "/expiration-alerts").status_code == 200


def test_alert_eligibility_is_separate_from_historical_readability(f, monkeypatch):
    from app.lifecycle.domain import eligible_for_alert
    configure_timezone(f)
    p = product(f)
    lot = receipt(f, p, expires_on="2026-11-12").json()
    alert = persist_alert(f, lot)
    row = dict(query(f, "SELECT * FROM inventory_lots WHERE household_id=:hid")[0])
    assert eligible_for_alert(row, product_archived_at=None, household_archived_at=None)
    for changes in [{"expires_on": None}, {"remaining_quantity": Decimal(0), "terminal_state": "CONSUMED"},
                    {"archived_at": datetime.now(timezone.utc)}]:
        assert not eligible_for_alert(row | changes, product_archived_at=None, household_archived_at=None)
    assert not eligible_for_alert(row, product_archived_at=datetime.now(timezone.utc), household_archived_at=None)
    assert not eligible_for_alert(row, product_archived_at=None, household_archived_at=datetime.now(timezone.utc))
    assert f.request("POST", f"/inventory-lots/{lot['id']}/archive", json={"reason": "Retain"}).status_code == 200
    assert f.request("POST", f"/products/{p['id']}/archive", json={}).status_code == 200
    async def archive():
        async with f.db() as db, db.begin():
            await db.execute(text("UPDATE households SET archived_at=now() WHERE id=:hid"), {"hid": f.hid})
    asyncio.run(archive())
    freeze_clock(monkeypatch)
    assert f.request("GET", "/inventory/lifecycle").json()["items"][0]["lot_archived_at"] is not None
    assert f.request("GET", f"/expiration-alerts/{alert['id']}").status_code == 200


def test_expiry_edit_preserves_prior_alert_provenance(f):
    p = product(f)
    lot = receipt(f, p, expires_on="2026-11-12").json()
    alert = persist_alert(f, lot)
    before = f.request("GET", f"/expiration-alerts/{alert['id']}")
    persisted = query(f, "SELECT to_jsonb(a)::text AS value FROM expiration_alerts a WHERE household_id=:hid")
    assert before.status_code == 200, before.text
    assert f.request("PATCH", f"/inventory-lots/{lot['id']}", json={"expires_on": "2027-01-01", "reason": "Correct date"}).status_code == 200
    configure_timezone(f, None)
    after = f.request("GET", f"/expiration-alerts/{alert['id']}")
    assert after.content == before.content
    assert after.json()["expires_on_snapshot"] == "2026-11-12"
    assert after.json()["timezone"] == "Asia/Ho_Chi_Minh"
    assert query(f, "SELECT to_jsonb(a)::text AS value FROM expiration_alerts a WHERE household_id=:hid") == persisted


def test_alert_pages_are_bounded_and_cursors_bind_scope_filters(f):
    lot = receipt(f, product(f), expires_on="2026-11-12").json()
    alerts = [persist_alert(f, lot, local_date=d) for d in ["2026-11-09", "2026-11-10", "2026-11-11"]]
    first = f.request("GET", "/expiration-alerts", params={"limit": 2}).json()
    assert [x["id"] for x in first["items"]] == [x["id"] for x in alerts[:2]]
    second = f.request("GET", "/expiration-alerts", params={"limit": 2, "cursor": first["next_cursor"]})
    assert [x["id"] for x in second.json()["items"]] == [alerts[-1]["id"]]
    assert second.json()["next_cursor"] is None
    assert f.request("GET", "/expiration-alerts", params={"cursor": first["next_cursor"], "kind": "EXPIRED"}).status_code == 422
    r = f.request("GET", "/expiration-alerts", params={"local_date_from": "2026-11-10", "local_date_to": "2026-11-10", "lot_id": lot["id"], "kind": "WARNING"})
    assert [x["id"] for x in r.json()["items"]] == [alerts[1]["id"]]
    for params in [{"limit": 0}, {"limit": 201}, {"local_date_from": "2026-11-11", "local_date_to": "2026-11-10"}, {"cursor": "garbage"}]:
        assert f.request("GET", "/expiration-alerts", params=params).status_code == 422
    assert f.request("GET", "/expiration-alerts", params={"limit": 200}).status_code == 200


def test_lifecycle_cursor_cannot_mix_household_local_dates_or_timezone(f, monkeypatch):
    configure_timezone(f)
    p = product(f)
    for _ in range(3):
        receipt(f, p, expires_on="2026-11-12")
    freeze_clock(monkeypatch)
    first = f.request("GET", "/inventory/lifecycle", params={"limit": 1}).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = f.request("GET", "/inventory/lifecycle", params={"limit": 2, "cursor": first["next_cursor"]})
    assert len(second.json()["items"]) == 2 and second.json()["next_cursor"] is None
    assert f.request("GET", "/inventory/lifecycle", params={"limit": 201}).status_code == 422
    assert f.request("GET", "/inventory/lifecycle", params={"limit": 200}).status_code == 200
    assert f.request("GET", "/inventory/lifecycle", params={"cursor": first["next_cursor"], "freshness": "EXPIRED"}).status_code == 422
    fresh = f.request("GET", "/inventory/lifecycle", params={"freshness": "WARNING", "product_id": p["id"]}).json()
    assert len(fresh["items"]) == 3
    assert f.request("GET", "/inventory/lifecycle", params={"lot_id": fresh["items"][0]["lot_id"]}).json()["items"] == fresh["items"][:1]
    freeze_clock(monkeypatch, "2026-11-11T17:00:00+00:00")
    r = f.request("GET", "/inventory/lifecycle", params={"cursor": first["next_cursor"]})
    assert r.status_code == 409 and r.json()["error_code"] == "INVENTORY_STATE_CONFLICT"
    freeze_clock(monkeypatch)
    configure_timezone(f, "UTC")
    assert f.request("GET", "/inventory/lifecycle", params={"cursor": first["next_cursor"]}).status_code == 409


def test_default_page_size_is_50_and_freshness_filter_precedes_limit(f, monkeypatch):
    configure_timezone(f)
    p = product(f)
    # Real stock writer, one product; fixtures retained by unique household.
    for _ in range(51):
        assert receipt(f, p, expires_on="2026-11-12").status_code == 201
    freeze_clock(monkeypatch)
    page = f.request("GET", "/inventory/lifecycle").json()
    assert len(page["items"]) == 50 and page["next_cursor"]
    assert f.request("GET", "/inventory/lifecycle", params={"freshness": "EXPIRED", "limit": 1}).json()["items"] == []
