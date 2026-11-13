"""Lifecycle route matrix, enqueue replay and isolation, real JWT/runtime DB."""
import asyncio
import base64
import json
import pytest
from sqlalchemy import text
from test_inventory_lots import product, receipt
from test_inventory_checkout import configure_timezone
from test_inventory_expiry import persist_alert, freeze_clock

ROLES = ["OWNER", "ADMIN", "FINANCE_MANAGER", "INVENTORY_MANAGER", "MEMBER", "VIEWER"]


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("route", ["/inventory/lifecycle", "/expiration-alerts", "/expiration-alerts/{id}", "/inventory/expiry-runs/{job_id}", "/inventory/expiry-runs"])
def test_expiry_route_matrix_matches_all_six_confirmed_roles(f, role, route):
    configure_timezone(f)
    lot = receipt(f, product(f), expires_on="2026-11-12").json()
    alert = persist_alert(f, lot)
    write = route == "/inventory/expiry-runs"
    r = f.request("POST" if write else "GET", route.format(id=alert["id"], job_id=alert["job_id"]), role=role, **({"json": {}} if write else {}))
    if write and role not in {"OWNER", "INVENTORY_MANAGER"}:
        assert r.status_code == 403, r.text
        return
    assert r.status_code == (202 if write else 200), r.text
    assert "lease_token" not in r.text and "payload" not in r.text
    assert "checkpoint" not in r.text


def test_expiry_path_filter_cursor_and_job_ids_are_household_scoped(f, monkeypatch):
    configure_timezone(f)
    lot = receipt(f, product(f), expires_on="2026-11-12").json()
    a = persist_alert(f, lot)
    persist_alert(f, lot, local_date="2026-11-12")
    freeze_clock(monkeypatch)
    receipt(f, {"id": lot["product_id"], "base_unit_id": product(f)["base_unit_id"]})
    for route, foreign_params in [("/inventory/lifecycle", {"lot_id": lot["id"]}),
                                  ("/inventory/lifecycle", {"product_id": lot["product_id"]}),
                                  ("/expiration-alerts", {"lot_id": lot["id"]})]:
        headers = f.actors["OUTSIDER"].headers
        url = f"/api/v1/households/{f.other_hid}{route}"
        assert f.client.get(url, headers=headers, params=foreign_params).status_code == 404
        cursor = f.request("GET", route, params={"limit": 1}).json()["next_cursor"]
        assert cursor
        assert f.client.get(url, headers=headers, params={"cursor": cursor}).status_code == 404
        # Tampering with scope does not make a foreign position readable.
        data = json.loads(base64.urlsafe_b64decode(cursor))
        data["scope"][0] = f.other_hid
        forged = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        assert f.client.get(url, headers=headers, params={"cursor": forged}).status_code == 404
    assert f.client.get(f"/api/v1/households/{f.other_hid}/expiration-alerts/{a['id']}", headers=headers).status_code == 404
    # Step 3 extends the same foreign-household isolation to job status/enqueue.
    assert f.client.get(f"/api/v1/households/{f.other_hid}/inventory/expiry-runs/{a['job_id']}", headers=f.actors["OUTSIDER"].headers).status_code == 404
    assert f.request("POST", "/inventory/expiry-runs", role="OUTSIDER", json={}).status_code == 404


@pytest.mark.parametrize("state,status", [("PENDING", 403), ("DISABLED", 401), ("REMOVED", 404), ("REVOKED", 401)])
@pytest.mark.parametrize("route", ["/inventory/lifecycle", "/expiration-alerts", "/expiration-alerts/{id}", "/inventory/expiry-runs/{job_id}"])
def test_expiry_reads_recheck_current_identity_session_membership(f, state, status, route):
    configure_timezone(f)
    alert = persist_alert(f, receipt(f, product(f), expires_on="2026-11-12").json())
    async def change():
        async with f.db() as db, db.begin():
            actor = f.actors["VIEWER"]
            if state in {"PENDING", "DISABLED"}:
                await db.execute(text("UPDATE users SET state=:state WHERE id=:id"), {"state": state, "id": actor.id})
            elif state == "REMOVED":
                await db.execute(text("UPDATE household_members SET removed_at=now() WHERE household_id=:hid AND id=:id"), {"hid": f.hid, "id": actor.member_id})
            else:
                await db.execute(text("UPDATE auth_sessions SET revoked_at=now() WHERE id=:id"), {"id": actor.session_id})
    asyncio.run(change())
    assert f.request("GET", route.format(id=alert["id"], job_id=alert["job_id"]), role="VIEWER").status_code == status


@pytest.mark.parametrize("change,status", [("PENDING",403),("DISABLED",401),("REMOVED",404),("REVOKED",401),("ROLE",403),("ARCHIVED",409)])
def test_expiry_enqueue_replay_rechecks_current_access(f, change, status):
    configure_timezone(f)
    r = f.request("POST", "/inventory/expiry-runs", role="INVENTORY_MANAGER", key="replay", json={})
    assert r.status_code == 202, r.text
    async def mutate():
        async with f.db() as db, db.begin():
            actor = f.actors["INVENTORY_MANAGER"]
            if change in {"PENDING", "DISABLED"}:
                await db.execute(text("UPDATE users SET state=:state WHERE id=:id"), {"state": change,"id": actor.id})
            elif change == "REMOVED":
                await db.execute(text("UPDATE household_members SET removed_at=now() WHERE id=:id"), {"id": actor.member_id})
            elif change == "REVOKED":
                await db.execute(text("UPDATE auth_sessions SET revoked_at=now() WHERE id=:id"), {"id": actor.session_id})
            elif change == "ROLE":
                await db.execute(text("UPDATE household_members SET role_id=(SELECT id FROM roles WHERE code='VIEWER') WHERE id=:id"), {"id": actor.member_id})
            else:
                await db.execute(text("UPDATE households SET archived_at=now() WHERE id=:hid"), {"hid": f.hid})
    asyncio.run(mutate())
    assert f.request("POST", "/inventory/expiry-runs", role="INVENTORY_MANAGER", key="replay", json={}).status_code == status


@pytest.mark.parametrize("body,key", [({},False), ({},"bad key"), ({"date":"2026-11-11"},"extra"), ({"timezone":"UTC"},"extra"), ({"kind":"OTHER"},"extra")])
def test_expiry_enqueue_rejects_client_overrides_and_invalid_key(f, body, key):
    configure_timezone(f)
    assert f.request("POST", "/inventory/expiry-runs", json=body, key=key).status_code == 422
