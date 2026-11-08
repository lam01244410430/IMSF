"""Password recovery gates on a fresh, explicitly disposable PostgreSQL."""
import asyncio
import base64
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from test_identity_sessions import configuration, database, seed, records, PASSWORD
from app.api.dependencies import get_db, get_email_provider
from app.identity.auth_service import AuthService, IdentityRequestError
from app.identity.infrastructure.models import AuthChallenge, AuthSession, AuthRateLimit, User, RefreshToken
from app.identity.infrastructure.security import token_digest, Argon2PasswordHasher
from app.main import create_app
from fastapi.testclient import TestClient

BASE = "/api/v1/auth/password-reset"
NEW = "new-password-for-reset"


class Mail:
    def __init__(self):
        self.messages = []

    async def send(self, **message):
        self.messages.append(message)


@pytest.fixture
def http(database):
    app, mail = create_app(), Mail()
    async def db():
        async with database() as session:
            yield session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_email_provider] = lambda: mail
    with TestClient(app, base_url="https://testserver") as client:
        yield client, mail, app


async def invoke(factory, mail, method, *args, now=None):
    async with factory() as db:
        return await getattr(AuthService(db, mail, clock=(lambda: now) if now else None), method)(*args)


async def requested(factory, mail, state="ACTIVE", now=None):
    uid = await seed(factory, state=state)
    await invoke(factory, mail, "request_password_reset", "person@example.test", "request-ip", now=now)
    return uid, mail.messages[-1]["body"]


def test_generic_request_all_states_and_unknown(http, database, caplog):
    client, mail, _ = http
    for state in ("ACTIVE", "DISABLED", "PENDING"):
        asyncio.run(seed(database, state=state, email=state.lower() + "@example.test"))
    responses = [client.post(BASE + "/request", json={"email": email + "@example.test"})
                 for email in ("active", "unknown", "disabled", "pending")]
    assert [r.status_code for r in responses] == [200] * 4
    assert all(r.json() == responses[0].json() for r in responses)
    challenges = asyncio.run(records(database, AuthChallenge))
    assert len(challenges) == 2
    users = asyncio.run(records(database, User))
    disabled_id = next(u.id for u in users if u.state == "DISABLED")
    assert all(c.user_id != disabled_id for c in challenges)
    for message in mail.messages:
        raw = message["body"]
        assert len(base64.urlsafe_b64decode(raw + "=")) == 32
        assert any(c.token_digest == token_digest(raw) for c in challenges)
        assert raw not in caplog.text + "".join(r.text for r in responses)
    assert all(c.expires_at - c.created_at == timedelta(minutes=60) for c in challenges)


def test_request_email_and_ip_limits_and_hour_boundary(database):
    async def scenario():
        mail, now = Mail(), datetime.now(timezone.utc)
        await seed(database)
        for i in range(4):
            await invoke(database, mail, "request_password_reset", " Person@Example.TEST ", str(i), now=now)
        assert len(mail.messages) == 3
        await invoke(database, mail, "request_password_reset", "person@example.test", "new", now=now + timedelta(hours=1))
        assert len(mail.messages) == 4
        for i in range(6):
            await seed(database, email=f"u{i}@example.test")
            await invoke(database, mail, "request_password_reset", f"u{i}@example.test", "shared", now=now)
        assert len(mail.messages) == 9
    asyncio.run(scenario())


def test_second_request_invalidates_first_and_replay(http, database):
    client, mail, _ = http
    asyncio.run(seed(database))
    for _ in range(2):
        assert client.post(BASE + "/request", json={"email": "person@example.test"}).status_code == 200
    old, raw = [m["body"] for m in mail.messages]
    assert client.post(BASE + "/confirm", json={"token": old, "password": NEW}).status_code == 400
    assert client.post(BASE + "/confirm", json={"token": raw, "password": NEW}).status_code == 200
    assert client.post(BASE + "/confirm", json={"token": raw, "password": NEW}).status_code == 400
    assert all(c.consumed_at for c in asyncio.run(records(database, AuthChallenge)))


@pytest.mark.parametrize("minutes,allowed", [(59, True), (60, False)])
def test_expiry(database, minutes, allowed):
    async def scenario():
        mail, now = Mail(), datetime.now(timezone.utc)
        _, raw = await requested(database, mail, now=now)
        if allowed:
            await invoke(database, mail, "confirm_password_reset", raw, NEW, "confirm", now=now + timedelta(minutes=minutes))
        else:
            with pytest.raises(IdentityRequestError):
                await invoke(database, mail, "confirm_password_reset", raw, NEW, "confirm", now=now + timedelta(minutes=minutes))
    asyncio.run(scenario())


def test_five_failed_confirms_invalidate_and_persist(database):
    async def scenario():
        mail = Mail()
        _, raw = await requested(database, mail)
        for i in range(5):
            with pytest.raises(IdentityRequestError):
                await invoke(database, mail, "confirm_password_reset", raw, PASSWORD, f"confirm-{i}")
        c = (await records(database, AuthChallenge))[0]
        assert c.failed_attempts == 5 and c.consumed_at is not None
        with pytest.raises(IdentityRequestError):
            await invoke(database, mail, "confirm_password_reset", raw, NEW, "fresh-ip")
    asyncio.run(scenario())


def test_confirm_shares_request_ip_budget(http, database):
    client, mail, _ = http
    asyncio.run(seed(database))
    client.post(BASE + "/request", json={"email": "person@example.test"})
    raw = mail.messages[0]["body"]
    for _ in range(4):
        assert client.post(BASE + "/confirm", json={"token": "wrong", "password": NEW}).status_code == 400
    assert client.post(BASE + "/confirm", json={"token": raw, "password": NEW}).status_code == 400
    assert asyncio.run(records(database, AuthChallenge))[0].consumed_at is None


@pytest.mark.parametrize("length,status", [(11, 400), (12, 200), (128, 200), (129, 400)])
def test_password_bounds(http, database, length, status, caplog):
    client, mail, _ = http
    _, raw = asyncio.run(requested(database, mail))
    response = client.post(BASE + "/confirm", json={"token": raw, "password": "p" * length})
    assert response.status_code == status
    assert raw not in response.text + caplog.text
    if status == 200:
        user = asyncio.run(records(database, User))[0]
        assert user.password_hash.startswith("$argon2id$")
        assert Argon2PasswordHasher().verify("p" * length, user.password_hash)


@pytest.mark.parametrize("state", ["PENDING", "DISABLED"])
def test_state_never_changes(database, state):
    async def scenario():
        mail = Mail()
        uid, raw = await requested(database, mail, state="PENDING")
        if state == "DISABLED":
            async with database() as db, db.begin():
                await db.execute(update(User).where(User.id == uid).values(state=state))
            with pytest.raises(IdentityRequestError):
                await invoke(database, mail, "confirm_password_reset", raw, NEW, "confirm")
        else:
            await invoke(database, mail, "confirm_password_reset", raw, NEW, "confirm")
        user = (await records(database, User))[0]
        assert user.state == state and user.verified_at is None
        assert Argon2PasswordHasher().verify(PASSWORD if state == "DISABLED" else NEW, user.password_hash)
    asyncio.run(scenario())


def test_success_revokes_every_family_and_notification(http, database, caplog):
    client, mail, _ = http
    asyncio.run(seed(database))
    logins = [client.post("/api/v1/auth/login", json={"email": "person@example.test", "password": PASSWORD}) for _ in range(2)]
    refresh = [r.cookies["refresh_token"] for r in logins]
    client.post(BASE + "/request", json={"email": "person@example.test"})
    raw = mail.messages[-1]["body"]
    response = client.post(BASE + "/confirm", json={"token": raw, "password": NEW})
    assert response.status_code == 200
    assert len(mail.messages) == 2
    notice = mail.messages[-1]
    assert notice["subject"] == "Password changed"
    for secret in (raw, token_digest(raw), NEW, PASSWORD, "http", "://"):
        assert secret not in notice["body"]
    for login, token in zip(logins, refresh):
        assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + login.json()["access_token"]}).status_code == 401
        client.cookies.set("refresh_token", token, domain="testserver.local", path="/api/v1/auth/")
        assert client.post("/api/v1/auth/refresh", headers={"Origin": "https://testserver"}).status_code == 400
    assert all(f.revoked_at for f in asyncio.run(records(database, AuthSession)))
    assert all(t.consumed_at for t in asyncio.run(records(database, RefreshToken)))
    assert client.post("/api/v1/auth/login", json={"email": "person@example.test", "password": NEW}).status_code == 200
    assert raw not in response.text + caplog.text


def test_no_provider_and_provider_failure_same_success(http, database, caplog):
    client, mail, app = http
    _, raw = asyncio.run(requested(database, mail))
    app.dependency_overrides[get_email_provider] = lambda: None
    response = client.post(BASE + "/confirm", json={"token": raw, "password": NEW})
    assert response.status_code == 200 and len(mail.messages) == 1
    assert client.post(BASE + "/request", json={"email": "person@example.test"}).status_code == 200
    assert len(mail.messages) == 1
    class Broken:
        async def send(self, **message):
            raise RuntimeError("private-provider:" + message["body"])
    app.dependency_overrides[get_email_provider] = lambda: Broken()
    assert client.post(BASE + "/request", json={"email": "person@example.test"}).status_code == 200
    assert "private-provider" not in caplog.text and raw not in response.text + caplog.text


def test_concurrent_requests_and_confirms(database):
    async def scenario():
        mail = Mail()
        await seed(database)
        await asyncio.gather(*(invoke(database, mail, "request_password_reset", "person@example.test", str(i)) for i in range(3)))
        challenges = await records(database, AuthChallenge)
        assert sum(c.consumed_at is None for c in challenges) == 1
        active = next(c for c in challenges if c.consumed_at is None)
        raw = next(m["body"] for m in mail.messages if token_digest(m["body"]) == active.token_digest)
        async def confirm(ip):
            try:
                await invoke(database, mail, "confirm_password_reset", raw, NEW, ip)
                return True
            except IdentityRequestError:
                return False
        assert sorted(await asyncio.gather(confirm("a"), confirm("b"))) == [False, True]
    asyncio.run(scenario())


def test_confirm_ip_budget_independent_and_rolls_over(database):
    async def scenario():
        now, mail = datetime.now(timezone.utc), Mail()
        _, raw = await requested(database, mail, now=now)
        for _ in range(5):
            with pytest.raises(IdentityRequestError):
                await invoke(database, mail, "confirm_password_reset", "unknown-token", NEW, "exhausted", now=now)
        with pytest.raises(IdentityRequestError):
            await invoke(database, mail, "confirm_password_reset", raw, NEW, "exhausted", now=now)
        # At the rolling boundary the IP is allowed again, but the token has
        # expired independently; a fresh request proves the renewed budget.
        await invoke(database, mail, "request_password_reset", "person@example.test", "exhausted", now=now + timedelta(hours=1))
        assert len(mail.messages) == 2
        async with database() as db:
            counters = list((await db.scalars(select(AuthRateLimit))).all())
            assert all(c.subject_digest not in {"exhausted", "person@example.test"} for c in counters)
    asyncio.run(scenario())


def test_reset_transaction_rolls_back_all_mutations(database, monkeypatch):
    async def scenario():
        from app.identity.session_service import SessionService
        mail = Mail()
        _, raw = await requested(database, mail)
        async with database() as db:
            await SessionService(db).login("person@example.test", PASSWORD, "login")
        async with database() as db:
            execute = db.execute
            async def fail_refresh_update(statement, *args, **kwargs):
                if getattr(getattr(statement, "table", None), "name", None) == "refresh_tokens":
                    raise RuntimeError("injected transaction failure")
                return await execute(statement, *args, **kwargs)
            monkeypatch.setattr(db, "execute", fail_refresh_update)
            with pytest.raises(RuntimeError, match="injected transaction failure"):
                await AuthService(db, mail).confirm_password_reset(raw, NEW, "confirm")
        assert Argon2PasswordHasher().verify(PASSWORD, (await records(database, User))[0].password_hash)
        assert all(f.revoked_at is None for f in await records(database, AuthSession))
        assert all(c.consumed_at is None for c in await records(database, AuthChallenge))
        assert len(mail.messages) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [
    {"token": "private-token" * 30, "password": NEW},
    {"token": "private-token", "password": 123},
    {"token": "private-token", "password": NEW, "email": "private@example.test"},
])
def test_malformed_confirm_redacted(http, payload, caplog):
    response = http[0].post(BASE + "/confirm", json=payload)
    assert response.status_code == 422
    assert "private-token" not in response.text + caplog.text
    assert NEW not in response.text + caplog.text
    assert set(response.json()) == {"error_code", "details", "request_id"}


@pytest.mark.parametrize("provider_mode", ["none", "broken"])
def test_notification_failure_does_not_change_success(http, database, provider_mode, caplog):
    from app.identity.dto import PasswordResetConfirmed
    client, mail, app = http
    _, raw = asyncio.run(requested(database, mail))
    class Broken:
        async def send(self, **message):
            raise RuntimeError("private-notification:" + message["body"])
    app.dependency_overrides[get_email_provider] = lambda: None if provider_mode == "none" else Broken()
    response = client.post(BASE + "/confirm", json={"token": raw, "password": NEW})
    assert response.status_code == 200
    assert response.json() == PasswordResetConfirmed().model_dump()
    assert len(mail.messages) == 1
    assert "private-notification" not in caplog.text + response.text
    assert raw not in caplog.text + response.text
