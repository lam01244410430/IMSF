"""Step 3 session invariants against an explicitly disposable PostgreSQL."""
import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.dependencies import get_db, require_active_user, require_household_member
from app.identity.auth_service import IdentityRequestError
from app.identity.infrastructure.models import AuthSession, AuthAuditEvent, RefreshToken, User
from app.identity.infrastructure.security import Argon2PasswordHasher, token_digest
from app.identity.session_service import SessionService
from app.main import create_app

PASSWORD = "sessions-test-password"
BASE = "/api/v1/auth"


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_ISSUER", "sessions-test")
    monkeypatch.setenv("JWT_AUDIENCE", "sessions-test")
    monkeypatch.setenv("REFRESH_GRACE_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://testserver")


@pytest.fixture
def database(identity_database):
    engine = create_async_engine(identity_database, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    async def cleanup():
        async with engine.begin() as connection:
            for table in (
                "refresh_tokens",
                "auth_challenges",
                "auth_audit_events",
                "auth_sessions",
                "auth_rate_limits",
                "audit_logs",
                "household_invitations",
                "household_members",
                "households",
                "users",
            ):
                await connection.execute(text(f"DELETE FROM {table}"))
        await engine.dispose()
    asyncio.run(cleanup())


@pytest.fixture
def http(database):
    app = create_app()
    async def db():
        async with database() as session:
            yield session
    app.dependency_overrides[get_db] = db

    @app.get("/active-probe")
    async def active(user: Annotated[object, Depends(require_active_user)]):
        return {"ok": True}

    @app.get("/membership-probe/{household_id}")
    async def member(value: Annotated[object, Depends(require_household_member)]):
        return {"ok": True}

    with TestClient(app, base_url="https://testserver") as client:
        yield client


async def seed(factory, state="ACTIVE", email="person@example.test"):
    async with factory() as db, db.begin():
        user = User(email=email, email_key=email, state=state,
                    password_hash=Argon2PasswordHasher().hash(PASSWORD))
        db.add(user)
        await db.flush()
        return user.id


async def call(factory, method, *args, now=None):
    async with factory() as db:
        return await getattr(SessionService(db, clock=(lambda: now) if now else None), method)(*args)


async def records(factory, model):
    async with factory() as db:
        return list((await db.scalars(select(model).order_by(model.id))).all())


def login(client, **values):
    return client.post(BASE + "/login", json={"email": " Person@Example.TEST ", "password": PASSWORD, **values})


def test_login_jwt_cookie_and_live_backend_gate(http, database):
    uid = asyncio.run(seed(database))
    response = login(http)
    assert response.status_code == 200
    body = response.json()
    claims = jwt.decode(body["access_token"], os.environ["JWT_SECRET"], algorithms=["HS256"],
                        issuer="sessions-test", audience="sessions-test")
    assert claims["sub"] == str(uid) and claims["exp"] - claims["iat"] == 900
    cookie = response.headers["set-cookie"]
    assert all(value in cookie for value in ("HttpOnly", "Secure", "SameSite=lax", "Path=/api/v1/auth/"))
    assert body["access_token"] not in cookie and PASSWORD not in response.text
    assert response.headers["cache-control"] == "no-store"
    headers = {"Authorization": "Bearer " + body["access_token"]}
    assert http.get("/active-probe", headers=headers).status_code == 200
    assert http.get("/membership-probe/999", headers=headers).status_code == 404
    async def disable():
        async with database() as db, db.begin():
            await db.execute(update(User).values(state="DISABLED"))
    asyncio.run(disable())
    assert http.get("/active-probe", headers=headers).status_code == 401


def test_generic_login_failures(http, database):
    asyncio.run(seed(database, state="DISABLED"))
    responses = [login(http), login(http, password="wrong"), login(http, email="unknown@example.test")]
    assert [r.status_code for r in responses] == [400] * 3
    bodies = [r.json() for r in responses]
    for body in bodies:
        body.pop("request_id")
    assert bodies[0] == bodies[1] == bodies[2]
    assert asyncio.run(records(database, AuthSession)) == []


def test_pending_verification_only(http, database):
    asyncio.run(seed(database, state="PENDING"))
    body = login(http).json()
    headers = {"Authorization": "Bearer " + body["access_token"]}
    assert body["state"] == "PENDING"
    assert http.get("/active-probe", headers=headers).status_code == 403
    assert http.get("/membership-probe/999", headers=headers).status_code == 403
    assert http.post(BASE + "/refresh", headers={"Origin": "https://testserver"}).status_code == 400
    assert http.post(BASE + "/email-verification/resend", headers=headers).status_code == 202
    assert http.patch(BASE + "/email", headers=headers, json={"email": "new@example.test"}).status_code == 200
    assert http.post(BASE + "/logout", headers={"X-CSRF-Token": body["csrf_token"]}).status_code == 204


@pytest.mark.parametrize("scope,limit", [("email", 5), ("ip", 10)])
def test_login_limits_persist_and_roll(database, scope, limit):
    async def scenario():
        await seed(database)
        now = datetime.now(timezone.utc)
        for i in range(limit):
            email = "person@example.test" if scope == "email" else f"unknown{i}@example.test"
            with pytest.raises(IdentityRequestError):
                await call(database, "login", email, "wrong", "192.0.2.1", now=now)
        with pytest.raises(IdentityRequestError):
            await call(database, "login", "person@example.test", PASSWORD, "192.0.2.1", now=now)
        await call(database, "login", "person@example.test", PASSWORD, "192.0.2.1", now=now + timedelta(hours=1))
    asyncio.run(scenario())


def test_rotation_parallel_grace_last_activity_and_expiry(database):
    async def scenario():
        await seed(database)
        now = datetime.now(timezone.utc)
        original = await call(database, "login", "person@example.test", PASSWORD, "ip", now=now)
        initial = (await records(database, AuthSession))[0]
        assert initial.expires_at == now + timedelta(days=14)
        assert original[2] == initial.expires_at
        later = now + timedelta(seconds=1)
        a, b = await asyncio.gather(*(call(database, "refresh", original[1], now=later) for _ in range(2)))
        assert a[1] == b[1] != original[1]
        assert a[0]["csrf_token"] == b[0]["csrf_token"]
        assert len(await records(database, RefreshToken)) == 2
        family = (await records(database, AuthSession))[0]
        assert family.last_activity_at == later and family.expires_at == later + timedelta(days=14)
        assert a[2] == min(later + timedelta(days=30), family.expires_at)
        tokens = await records(database, RefreshToken)
        assert tokens[0].successor_ciphertext and original[1].encode() not in tokens[0].successor_ciphertext
        assert tokens[1].token_digest == token_digest(a[1])
    asyncio.run(scenario())


@pytest.mark.parametrize("different_successor", [False, True])
def test_replay_revokes_committed_family(database, different_successor):
    async def scenario():
        await seed(database)
        now = datetime.now(timezone.utc)
        original = await call(database, "login", "person@example.test", PASSWORD, "ip", now=now)
        successor = await call(database, "refresh", original[1], now=now)
        if different_successor:
            successor = await call(database, "refresh", successor[1], now=now)
        with pytest.raises(IdentityRequestError):
            await call(database, "refresh", original[1], now=now + timedelta(seconds=1 if different_successor else 10))
        assert (await records(database, AuthSession))[0].revoked_at is not None
        with pytest.raises(IdentityRequestError):
            await call(database, "refresh", successor[1], now=now + timedelta(seconds=11))
    asyncio.run(scenario())


def test_cap_and_absolute_expiry(database):
    async def scenario():
        await seed(database)
        now = datetime.now(timezone.utc)
        sessions = []
        for i in range(11):
            sessions.append(await call(database, "login", "person@example.test", PASSWORD, "ip", now=now + timedelta(hours=i)))
        families = await records(database, AuthSession)
        assert len(families) == 11 and sum(f.revoked_at is None for f in families) == 10
        assert families[0].revoked_at is not None
        assert (await records(database, AuthAuditEvent))[0].event_code == "SESSION_CAP_REVOKED"
        # Keep refreshing within idle limits until the absolute bound is reached.
        raw = sessions[-1][1]
        start = families[-1].created_at
        for days in (13, 26, 39, 52, 65, 78, 89):
            result = await call(database, "refresh", raw, now=start + timedelta(days=days))
            raw = result[1]
        family = (await records(database, AuthSession))[-1]
        assert family.expires_at == start + timedelta(days=90) == result[2]
        with pytest.raises(IdentityRequestError):
            await call(database, "refresh", raw, now=start + timedelta(days=90))
    asyncio.run(scenario())


@pytest.mark.parametrize("headers,status", [({},403), ({"Origin":"https://evil.test"},403),
    ({"Origin":"null"},403), ({"Referer":"https://testserver.evil.test/path"},403),
    ({"Origin":"https://evil.test", "Referer":"https://testserver/path"},403),
    ({"Origin":"https://testserver"},200), ({"Referer":"https://testserver/path"},200)])
def test_refresh_origin_and_referer(http, database, headers, status):
    asyncio.run(seed(database))
    login(http)
    assert http.post(BASE + "/refresh", headers=headers).status_code == status


def test_logout_csrf_and_family_revocation(http, database):
    asyncio.run(seed(database))
    body = login(http).json()
    raw = http.cookies.get("refresh_token")
    assert http.post(BASE + "/logout").status_code == 403
    assert http.post(BASE + "/logout", headers={"X-CSRF-Token":"wrong"}).status_code == 403
    assert (asyncio.run(records(database, AuthSession)))[0].revoked_at is None
    response = http.post(BASE + "/logout", headers={"X-CSRF-Token":body["csrf_token"]})
    assert response.status_code == 204 and "Max-Age=0" in response.headers["set-cookie"]
    assert "Path=/api/v1/auth/" in response.headers["set-cookie"]
    assert http.get("/api/v1/users/me", headers={"Authorization":"Bearer " + body["access_token"]}).status_code == 401
    http.cookies.set("refresh_token", raw, path="/api/v1/auth/")
    assert http.post(BASE + "/refresh", headers={"Origin":"https://testserver"}).status_code == 400


def test_startup_keys_and_cors(monkeypatch):
    monkeypatch.delenv("REFRESH_GRACE_KEY")
    with pytest.raises(RuntimeError, match="REFRESH_GRACE_KEY"):
        with TestClient(create_app()):
            pass
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="explicit origins"):
        create_app()


def test_membership_reresolved_on_each_request(http, database):
    from app.identity.infrastructure.models import Household, HouseholdMember, Role
    uid = asyncio.run(seed(database))
    async def membership():
        async with database() as db, db.begin():
            household = Household(name="Session test")
            db.add(household)
            await db.flush()
            role = await db.scalar(select(Role.id).where(Role.code == "VIEWER"))
            db.add(HouseholdMember(household_id=household.id, user_id=uid, role_id=role))
            return household.id
    hid = asyncio.run(membership())
    headers = {"Authorization": "Bearer " + login(http).json()["access_token"]}
    assert http.get(f"/membership-probe/{hid}", headers=headers).status_code == 200
    async def remove():
        async with database() as db, db.begin():
            await db.execute(update(HouseholdMember).values(removed_at=datetime.now(timezone.utc)))
    asyncio.run(remove())
    assert http.get(f"/membership-probe/{hid}", headers=headers).status_code == 404
    async def cleanup():
        async with database() as db, db.begin():
            await db.execute(text("DELETE FROM household_members"))
            await db.execute(text("DELETE FROM households"))
    asyncio.run(cleanup())


def test_cors_allowlist(http):
    for origin, allowed in (("https://testserver", True), ("https://evil.test", False)):
        response = http.options(BASE + "/refresh", headers={"Origin": origin,
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "X-CSRF-Token"})
        assert (response.headers.get("access-control-allow-origin") == origin) is allowed
        assert response.headers.get("access-control-allow-origin") != "*"


def test_replay_revokes_even_after_email_returns_user_to_pending(database):
    async def scenario():
        uid = await seed(database)
        now = datetime.now(timezone.utc)
        original = await call(database, "login", "person@example.test", PASSWORD, "ip", now=now)
        await call(database, "refresh", original[1], now=now)
        async with database() as db, db.begin():
            await db.execute(update(User).where(User.id == uid).values(state="PENDING"))
        with pytest.raises(IdentityRequestError):
            await call(database, "refresh", original[1], now=now + timedelta(seconds=10))
        assert (await records(database, AuthSession))[0].revoked_at is not None
    asyncio.run(scenario())
