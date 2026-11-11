"""Independent six-role matrix against every Step 2 HTTP method/path."""
import asyncio

import pytest
from sqlalchemy import text

from test_finance_transactions import DRAFT, create_draft, query

ROUTES = [
    ("GET", "/currencies", None, 200),
    ("POST", "/accounts", {"name": "New", "currency_code": "USD"}, 201),
    ("GET", "/accounts", None, 200), ("GET", "/accounts/{aid}", None, 200),
    ("POST", "/accounts/{aid}/archive", None, 204),
    ("POST", "/categories", {"name": "New", "kind": "EXPENSE"}, 201),
    ("GET", "/categories", None, 200), ("POST", "/categories/{cid}/archive", None, 204),
    ("POST", "/transactions", DRAFT, 201),
    ("PATCH", "/transactions/{tid}", {"total_amount": "13"}, 200),
    ("POST", "/transactions/{tid}/items", {"line_no": 2, "description": "New", "quantity": "1", "net_amount": "1"}, 201),
    ("PATCH", "/transactions/{tid}/items/{iid}", {"description": "Edited"}, 200),
    ("GET", "/transactions", None, 200), ("GET", "/transactions/{tid}", None, 200),
]
# Independently enumerated indices; never derive expected grants from production permissions.
EXPECTED = {
    "OWNER": {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13},
    "ADMIN": {0, 2, 3, 6, 12, 13},
    "FINANCE_MANAGER": {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13},
    "INVENTORY_MANAGER": {0, 2, 3, 6, 12, 13},
    "MEMBER": {0, 2, 3, 6, 8, 9, 10, 11, 12, 13},
    "VIEWER": {0, 2, 3, 6, 12, 13},
}


@pytest.mark.parametrize("role", EXPECTED)
@pytest.mark.parametrize("route_index", range(len(ROUTES)))
def test_every_step2_route_role_matrix(f, role, route_index):
    aid = f.request("POST", "/accounts", json={"name": "Cash", "currency_code": "USD"}).json()["id"]
    cid = f.request("POST", "/categories", json={"name": "Services", "kind": "EXPENSE"}).json()["id"]
    draft = create_draft(f, role="MEMBER")
    method, path, body, success = ROUTES[route_index]
    path = path.format(aid=aid, cid=cid, tid=draft["id"], iid=draft["items"][0]["id"])
    response = f.request(method, path, role=role, **({"json": body} if body is not None else {}))
    assert response.status_code == (success if route_index in EXPECTED[role] else 403), response.text


def test_member_draft_only_and_creator_rule(f):
    draft = create_draft(f)
    for method, suffix, body in [("PATCH", "", {"total_amount": "1"}),
        ("POST", "/items", {"line_no": 2, "description": "x", "quantity": "1", "net_amount": "1"}),
        ("PATCH", f"/items/{draft['items'][0]['id']}", {"description": "x"})]:
        assert f.request(method, f"/transactions/{draft['id']}" + suffix, role="MEMBER", json=body).status_code == 403
        assert f.request(method, f"/transactions/{draft['id']}" + suffix, role="FINANCE_MANAGER", json=body).status_code in {200, 201}


@pytest.mark.parametrize("change,expected", [("PENDING", 403), ("DISABLED", 401), ("removed", 404),
    ("expired", 401), ("revoked", 401), ("demoted", 403)])
def test_pending_disabled_removed_and_expired_session_denied(f, change, expected):
    actor = f.actors["MEMBER"]
    first = f.request("POST", "/transactions", role="MEMBER", key="replay", json=DRAFT)
    assert first.status_code == 201
    async def alter():
        async with f.db() as db, db.begin():
            if change in {"PENDING", "DISABLED"}:
                await db.execute(text("UPDATE users SET state=:state WHERE id=:id"), {"state": change, "id": actor.id})
            elif change == "removed":
                await db.execute(text("UPDATE household_members SET removed_at=now() WHERE id=:id"), {"id": actor.member_id})
            elif change == "demoted":
                await db.execute(text("UPDATE household_members SET role_id=(SELECT id FROM roles WHERE code='VIEWER') WHERE id=:id"), {"id": actor.member_id})
            else:
                column = "expires_at" if change == "expired" else "revoked_at"
                await db.execute(text(f"UPDATE auth_sessions SET {column}=now() WHERE id=:id"), {"id": actor.session_id})
    asyncio.run(alter())
    assert f.request("POST", "/transactions", role="MEMBER", key="replay", json=DRAFT).status_code == expected
    assert len(query(f, "SELECT id FROM transactions WHERE household_id=:hid")) == 1


def test_cross_household_path_and_body_ids_are_404(f):
    draft = create_draft(f)
    other_base = f"/api/v1/households/{f.other_hid}"
    headers = f.actors["OUTSIDER"].headers | {"Idempotency-Key": "foreign"}
    other_cat = f.client.post(other_base + "/categories", headers=headers, json={"name": "Other", "kind": "EXPENSE"}).json()["id"]
    other_draft = f.client.post(other_base + "/transactions", headers=headers, json=DRAFT).json()
    assert f.request("POST", "/transactions", json=DRAFT | {"category_id": other_cat}).status_code == 404
    for method, path, body in [("GET", f"/transactions/{other_draft['id']}", None),
        ("PATCH", f"/transactions/{other_draft['id']}", {"total_amount": "1"}),
        ("PATCH", f"/transactions/{draft['id']}/items/{other_draft['items'][0]['id']}", {"description": "x"}),
        ("GET", "/transactions", None)]:
        response = f.request(method, path, role="OUTSIDER" if path == "/transactions" else "OWNER",
                             **({"json": body} if body else {}))
        assert response.status_code == 404


def test_archived_household_rejects_finance_writes_and_replays(f):
    first = f.request("POST", "/transactions", key="saved", json=DRAFT)
    assert first.status_code == 201
    assert f.client.post(f"/api/v1/households/{f.hid}/archive", headers=f.actors["OWNER"].headers).status_code == 204
    assert f.request("POST", "/transactions", key="saved", json=DRAFT).status_code == 409
    assert f.request("GET", "/transactions").status_code == 200


@pytest.mark.parametrize("extra", [{"created_by_member_id": 1}, {"household_id": 1}, {"status": "POSTED"},
    {"posted_at": "2026-11-10T00:00:00Z"}, {"balance": "100"}, {"original_transaction_id": 1},
    {"exchange_rate": "1"}, {"payments": []}, {"product_id": 1}])
def test_forbid_client_actor_status_balance_and_reversal_fields(f, extra):
    assert f.request("POST", "/transactions", json=DRAFT | extra).status_code == 422


def test_idempotency_header_cors_and_error_compatibility(f):
    response = f.client.options(f"/api/v1/households/{f.hid}/transactions", headers={
        "Origin": "https://testserver", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization,Content-Type,Idempotency-Key"})
    assert response.status_code == 200
    error = f.request("POST", "/transactions", key=False, json=DRAFT)
    assert error.status_code == 422 and set(error.json()) == {"error_code", "details", "request_id"}


def test_step3_to_5_routes_are_absent(f):
    paths = f.app.openapi()["paths"]
    for path in paths:
        if "households/{household_id}" in path:
            assert not any(word in path for word in ("/payments", "/post", "/reversals", "/ledger", "/balance", "/reconciliations"))
            if any(word in path for word in ("/accounts", "/categories", "/transactions", "/currencies")):
                assert "delete" not in paths[path]


@pytest.mark.parametrize("change,expected", [("removed", 404), ("archive", 409), ("revoked", 401), ("demoted", 403)])
def test_removal_archive_and_revocation_between_bearer_and_application_checks(f, monkeypatch, change, expected):
    import httpx
    from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
    original = SqlAlchemyHouseholdAccess.resolve
    async def run():
        entered, resume = asyncio.Event(), asyncio.Event()
        async def paused(self, actor, hid, permission, *, write):
            if write and actor.user_id == f.actors["MEMBER"].id:
                entered.set()
                await resume.wait()
            return await original(self, actor, hid, permission, write=write)
        monkeypatch.setattr(SqlAlchemyHouseholdAccess, "resolve", paused)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app), base_url="https://testserver") as client:
            task = asyncio.create_task(client.post(f"/api/v1/households/{f.hid}/transactions",
                headers=f.actors["MEMBER"].headers | {"Idempotency-Key": "race"}, json=DRAFT))
            await asyncio.wait_for(entered.wait(), timeout=10)
            async with f.db() as db, db.begin():
                actor = f.actors["MEMBER"]
                sql, params = {
                    "removed": ("UPDATE household_members SET removed_at=now() WHERE id=:id", {"id": actor.member_id}),
                    "archive": ("UPDATE households SET archived_at=now() WHERE id=:id", {"id": f.hid}),
                    "revoked": ("UPDATE auth_sessions SET revoked_at=now() WHERE id=:id", {"id": actor.session_id}),
                    "demoted": ("UPDATE household_members SET role_id=(SELECT id FROM roles WHERE code='VIEWER') WHERE id=:id", {"id": actor.member_id}),
                }[change]
                await db.execute(text(sql), params)
            resume.set()
            assert (await task).status_code == expected
    asyncio.run(run())
    for table in ("transactions", "idempotency_requests", "audit_logs"):
        assert query(f, f"SELECT count(*) AS n FROM {table} WHERE household_id=:hid")[0]["n"] == 0


def test_token_expiring_after_current_user_check_still_returns_401(monkeypatch):
    """Reproduce the second-decode boundary with a real expired signed token.

    current_user may already have verified JWT time before awaiting its DB query.
    The finance dependency must handle expiration when it resumes afterward.
    """
    import secrets
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from app.api.finance import finance_actor
    from app.identity.session_service import session_security
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_ISSUER", "expiry-boundary")
    monkeypatch.setenv("JWT_AUDIENCE", "expiry-boundary")
    now = datetime.now(timezone.utc)
    token = session_security().encode_access({"sub": "1", "sid": 1,
        "iat": now - timedelta(minutes=16), "exp": now - timedelta(seconds=1)})
    with pytest.raises(HTTPException) as failure:
        finance_actor(SimpleNamespace(id=1), HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert failure.value.status_code == 401
