"""Step 2 acceptance against real, explicitly disposable PostgreSQL.

Login is intentionally absent: a pre-existing session fixture exercises the
PENDING verification-only principal. A test-only probe exercises the ACTIVE
backend gate; household operations and invitation acceptance are later scope.
"""
import asyncio
import base64
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.dependencies import get_db, get_email_provider, require_active_user
from app.identity.auth_service import AuthService, IdentityRequestError
from app.identity.dto import RegistrationResult, RegisterRequest, UserResponse, VerifyEmailRequest
from app.identity.infrastructure.email import NoOpEmailProvider
from app.identity.infrastructure.models import AuthChallenge, AuthRateLimit, AuthSession, User
from app.identity.infrastructure.security import Argon2PasswordHasher, token_digest
from app.main import create_app

PASSWORD = "registration-test-password"
PREFIX = "/api/v1"


class RecordingEmail(NoOpEmailProvider):
    """Capture only in test memory; never print or deliver to a real mailbox."""
    def __init__(self):
        self.messages = []

    async def send(self, *, recipient, subject, body):
        self.messages.append((recipient, body))


@pytest.fixture(autouse=True)
def jwt_configuration(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_ISSUER", "registration-test-issuer")
    monkeypatch.setenv("JWT_AUDIENCE", "registration-test-audience")


@pytest.fixture
def database(identity_database):
    engine = create_async_engine(identity_database, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    async def cleanup():
        # Only this explicit disposable DB is touched. Keep seed roles intact.
        async with engine.begin() as connection:
            for table in ("auth_challenges", "auth_rate_limits", "auth_sessions", "users"):
                await connection.execute(text(f"DELETE FROM {table}"))
        await engine.dispose()
    asyncio.run(cleanup())


@pytest.fixture
def http(database):
    provider = RecordingEmail()
    app = create_app()

    async def session():
        async with database() as db:
            yield db

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_email_provider] = lambda: provider
    with TestClient(app) as client:
        yield client, provider, app


async def registered(factory, provider, *, email="person@example.test", now=None):
    async with factory() as db:
        service = AuthService(db, provider, clock=(lambda: now) if now else None)
        result = await service.register(RegisterRequest(email=email, password=PASSWORD))
    async with factory() as db:
        user = await db.scalar(select(User).where(User.email_key == email.strip().lower()))
        return user.id, result


async def snapshot(factory):
    async with factory() as db:
        return (list((await db.scalars(select(User).order_by(User.id))).all()),
                list((await db.scalars(select(AuthChallenge).order_by(AuthChallenge.id))).all()))


async def existing_access(factory, user_id, **overrides):
    now = datetime.now(timezone.utc)
    async with factory() as db, db.begin():
        record = AuthSession(user_id=user_id, expires_at=now + timedelta(days=1),
                             csrf_digest="a" * 64, **overrides)
        db.add(record)
        await db.flush()
        session_id = record.id
    # Test fixture only: production Step 2 has no token-issuance path.
    return jwt.encode({"sub": str(user_id), "sid": session_id, "iat": now,
                       "exp": now + timedelta(minutes=15),
                       "iss": os.environ["JWT_ISSUER"], "aud": os.environ["JWT_AUDIENCE"]},
                      os.environ["JWT_SECRET"], algorithm="HS256")


def test_registration_normalization_argon2_and_digest_only(database):
    async def scenario():
        provider = RecordingEmail()
        now = datetime.now(timezone.utc)
        _, result = await registered(database, provider, email=" Person@Example.TEST ", now=now)
        users, challenges = await snapshot(database)
        user, challenge = users[0], challenges[0]
        assert user.email == user.email_key == "person@example.test"
        assert user.state == "PENDING" and user.verified_at is None
        assert user.password_hash.startswith("$argon2id$")
        assert Argon2PasswordHasher().verify(PASSWORD, user.password_hash)
        token = provider.messages[0][1]
        assert len(base64.urlsafe_b64decode(token + "=")) == 32
        assert challenge.token_digest == token_digest(token)
        assert challenge.purpose == "VERIFY_EMAIL"
        assert challenge.expires_at - challenge.created_at == timedelta(hours=24)
        assert challenge.created_at == now and challenge.consumed_at is None
        assert token not in repr(challenge.__dict__)
        assert token not in result.model_dump_json() and PASSWORD not in result.model_dump_json()
    asyncio.run(scenario())


def test_normalized_duplicate_email_race(database):
    async def scenario():
        provider = RecordingEmail()
        async def register(email):
            async with database() as db:
                return await AuthService(db, provider).register(RegisterRequest(email=email, password=PASSWORD))
        results = await asyncio.gather(register(" Race@Example.TEST "), register("race@example.test"))
        assert results[0] == results[1]
        users, challenges = await snapshot(database)
        assert len(users) == len(challenges) == len(provider.messages) == 1
        assert users[0].email_key == "race@example.test"
    asyncio.run(scenario())


@pytest.mark.parametrize("length", [0, 11, 129])
def test_password_rejected_outside_bounds(length):
    with pytest.raises(ValidationError):
        RegisterRequest(email="person@example.test", password="p" * length)


@pytest.mark.parametrize("length", [12, 128])
def test_password_accepted_at_bounds(database, length):
    async def scenario():
        async with database() as db:
            await AuthService(db, NoOpEmailProvider()).register(
                RegisterRequest(email="person@example.test", password="p" * length))
        users, _ = await snapshot(database)
        assert Argon2PasswordHasher().verify("p" * length, users[0].password_hash)
    asyncio.run(scenario())


def test_pending_verification_only_state_and_household_gate(http, database):
    client, provider, app = http
    response = client.post(PREFIX + "/auth/register", json={"email": "person@example.test", "password": PASSWORD})
    assert response.status_code == 202
    user_id = asyncio.run(snapshot(database))[0][0].id
    token = asyncio.run(existing_access(database, user_id))
    headers = {"Authorization": "Bearer " + token}
    response = client.get(PREFIX + "/users/me", headers=headers)
    assert response.status_code == 200 and response.json()["state"] == "PENDING"
    assert set(response.json()) == {"id", "email", "locale", "state", "verified_at"}

    @app.get("/test-only-active-gate")
    async def probe(user: Annotated[UserResponse, Depends(require_active_user)]):
        return {"allowed": True}

    assert client.get("/test-only-active-gate", headers=headers).status_code == 403
    assert client.post(PREFIX + "/auth/email-verification/resend", headers=headers).status_code == 202
    assert client.post(PREFIX + "/auth/email-verification/confirm", json={"token": provider.messages[0][1]}).status_code == 200
    assert client.get("/test-only-active-gate", headers=headers).status_code == 200
    assert client.get(PREFIX + "/users/me", headers=headers).json()["state"] == "ACTIVE"


def test_confirm_single_use_and_concurrent_replay(database):
    async def scenario():
        provider = RecordingEmail()
        await registered(database, provider)
        token = provider.messages[0][1]
        async def confirm(ip):
            async with database() as db:
                try:
                    await AuthService(db, provider).confirm(token, ip)
                    return True
                except IdentityRequestError:
                    return False
        assert sorted(await asyncio.gather(confirm("192.0.2.1"), confirm("192.0.2.2"))) == [False, True]
        assert await confirm("192.0.2.1") is False
        users, challenges = await snapshot(database)
        assert users[0].state == "ACTIVE" and users[0].verified_at is not None
        assert challenges[0].consumed_at is not None
    asyncio.run(scenario())


def test_expiry_boundary_rejected(database):
    async def scenario():
        provider = RecordingEmail()
        now = datetime.now(timezone.utc)
        await registered(database, provider, now=now)
        async with database() as db:
            with pytest.raises(IdentityRequestError):
                await AuthService(db, provider, clock=lambda: now + timedelta(hours=24)).confirm(
                    provider.messages[0][1], "192.0.2.3")
        users, challenges = await snapshot(database)
        assert users[0].state == "PENDING" and challenges[0].consumed_at is None
    asyncio.run(scenario())


def test_resend_invalidation_cooldown_and_rolling_day_quota(database):
    async def scenario():
        provider = RecordingEmail()
        now = datetime.now(timezone.utc)
        user_id, _ = await registered(database, provider, now=now)
        old = provider.messages[0][1]
        async def resend(at):
            async with database() as db:
                await AuthService(db, provider, clock=lambda: at).resend(user_id)
        await resend(now + timedelta(seconds=59))
        assert len(provider.messages) == 1
        await resend(now + timedelta(seconds=60))
        assert len(provider.messages) == 2
        async with database() as db:
            with pytest.raises(IdentityRequestError):
                await AuthService(db, provider, clock=lambda: now + timedelta(seconds=61)).confirm(old, "192.0.2.4")
        for minute in range(2, 5):
            await resend(now + timedelta(minutes=minute))
        assert len(provider.messages) == 5
        await resend(now + timedelta(minutes=5))
        assert len(provider.messages) == 5
        users, challenges = await snapshot(database)
        assert len(challenges) == 5
        assert sum(c.consumed_at is None for c in challenges) == 1
        assert users[0].state == "PENDING"
        await resend(now + timedelta(hours=24))
        assert len(provider.messages) == 6
    asyncio.run(scenario())


def test_concurrent_resend_serializes_user_quota(database):
    async def scenario():
        provider = RecordingEmail()
        now = datetime.now(timezone.utc)
        user_id, _ = await registered(database, provider, now=now)
        async def resend():
            async with database() as db:
                await AuthService(db, provider, clock=lambda: now + timedelta(seconds=60)).resend(user_id)
        await asyncio.gather(resend(), resend(), resend())
        _, challenges = await snapshot(database)
        assert len(provider.messages) == len(challenges) == 2
        assert sum(c.consumed_at is None for c in challenges) == 1
    asyncio.run(scenario())


def test_verification_attempts_rolling_hour_per_ip_persist_failures(database):
    async def scenario():
        provider = RecordingEmail()
        now = datetime.now(timezone.utc)
        await registered(database, provider, now=now)
        async def confirm(token, ip, at):
            async with database() as db:
                return await AuthService(db, provider, clock=lambda: at).confirm(token, ip)
        for i in range(10):
            with pytest.raises(IdentityRequestError):
                await confirm("invalid", "192.0.2.5", now + timedelta(seconds=i))
        token = provider.messages[0][1]
        with pytest.raises(IdentityRequestError):
            await confirm(token, "192.0.2.5", now + timedelta(minutes=1))
        async with database() as db:
            counters = (await db.scalars(select(AuthRateLimit))).all()
            assert sum(c.attempts for c in counters) == 10
            assert all(c.subject_digest != "192.0.2.5" for c in counters)
        await confirm(token, "192.0.2.5", now + timedelta(hours=1))
        assert (await snapshot(database))[0][0].state == "ACTIVE"
    asyncio.run(scenario())


def test_concurrent_invalid_confirm_attempts_cannot_exceed_ip_quota(database):
    async def scenario():
        now = datetime.now(timezone.utc)
        async def confirm():
            async with database() as db:
                with pytest.raises(IdentityRequestError):
                    await AuthService(db, NoOpEmailProvider(), clock=lambda: now).confirm("invalid", "192.0.2.6")
        await asyncio.gather(*(confirm() for _ in range(12)))
        async with database() as db:
            assert await db.scalar(select(func.sum(AuthRateLimit.attempts))) == 10
    asyncio.run(scenario())


def test_other_ip_has_independent_verification_budget(database):
    async def scenario():
        provider = RecordingEmail()
        await registered(database, provider)
        for _ in range(10):
            async with database() as db:
                with pytest.raises(IdentityRequestError):
                    await AuthService(db, provider).confirm("invalid", "192.0.2.7")
        async with database() as db:
            await AuthService(db, provider).confirm(provider.messages[0][1], "192.0.2.8")
    asyncio.run(scenario())


def test_change_own_email_invalidates_prior_challenges(http, database):
    client, provider, _ = http
    user_id, _ = asyncio.run(registered(database, provider))
    original = provider.messages[0][1]
    token = asyncio.run(existing_access(database, user_id))
    response = client.patch(PREFIX + "/auth/email", json={"email": " New@Example.TEST "},
                            headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200
    users, challenges = asyncio.run(snapshot(database))
    assert users[0].email_key == "new@example.test" and users[0].state == "PENDING"
    assert challenges[0].consumed_at is not None
    assert client.post(PREFIX + "/auth/email-verification/confirm", json={"token": original}).status_code == 400
    assert len(provider.messages) == 1  # New delivery uses the bounded resend path.


def test_active_change_email_requires_new_verification(database):
    async def scenario():
        provider = RecordingEmail()
        now = datetime.now(timezone.utc)
        user_id, _ = await registered(database, provider, now=now)
        async with database() as db:
            await AuthService(db, provider, clock=lambda: now).confirm(provider.messages[0][1], "192.0.2.9")
        async with database() as db:
            await AuthService(db, provider, clock=lambda: now).change_email(user_id, "new@example.test")
        users, _ = await snapshot(database)
        assert users[0].state == "PENDING" and users[0].verified_at is None
        async with database() as db:
            await AuthService(db, provider, clock=lambda: now + timedelta(seconds=60)).resend(user_id)
        assert provider.messages[-1][0] == "new@example.test"
        async with database() as db:
            await AuthService(db, provider, clock=lambda: now + timedelta(seconds=61)).confirm(
                provider.messages[-1][1], "192.0.2.9")
        assert (await snapshot(database))[0][0].state == "ACTIVE"
    asyncio.run(scenario())


def test_duplicate_email_change_rolls_back_challenge_and_user(database):
    async def scenario():
        provider = RecordingEmail()
        user_id, _ = await registered(database, provider)
        await registered(database, provider, email="taken@example.test")
        before = await snapshot(database)
        async with database() as db:
            await AuthService(db, provider).change_email(user_id, "taken@example.test")
        after = await snapshot(database)
        assert [u.email_key for u in before[0]] == [u.email_key for u in after[0]]
        assert [c.consumed_at for c in before[1]] == [c.consumed_at for c in after[1]]
        assert len(provider.messages) == 2
    asyncio.run(scenario())


def test_absent_provider_pending_and_generic_error_no_token(http, database):
    client, _, app = http
    app.dependency_overrides[get_email_provider] = lambda: None
    payload = {"email": "person@example.test", "password": PASSWORD}
    first = client.post(PREFIX + "/auth/register", json=payload)
    duplicate = client.post(PREFIX + "/auth/register", json=payload)
    assert first.status_code == duplicate.status_code == 400
    assert first.json()["error_code"] == duplicate.json()["error_code"]
    users, challenges = asyncio.run(snapshot(database))
    assert len(users) == len(challenges) == 1 and users[0].state == "PENDING"
    for response in (first, duplicate):
        assert set(response.json()) == {"error_code", "details", "request_id"}
        assert PASSWORD not in response.text and challenges[0].token_digest not in response.text
        assert response.headers["Cache-Control"] == "no-store"


def test_provider_failure_retains_pending_and_redacts_exception(http, database, caplog):
    client, _, app = http
    class BrokenProvider:
        async def send(self, *, recipient, subject, body):
            raise RuntimeError("provider-secret:" + body)
    app.dependency_overrides[get_email_provider] = lambda: BrokenProvider()
    response = client.post(PREFIX + "/auth/register", json={"email": "person@example.test", "password": PASSWORD})
    assert response.status_code == 202
    assert response.json() == RegistrationResult().model_dump()
    assert set(response.json()) == {"message"}
    users, challenges = asyncio.run(snapshot(database))
    assert len(users) == len(challenges) == 1 and users[0].state == "PENDING"
    for secret in ("provider-secret", PASSWORD, challenges[0].token_digest):
        assert secret not in response.text + caplog.text


def test_duplicate_email_with_failing_provider_matches_new_email_failure(http, database, caplog):
    client, _, app = http
    class BrokenProvider:
        def __init__(self):
            self.tokens = []

        async def send(self, *, recipient, subject, body):
            self.tokens.append(body)
            raise RuntimeError("provider-secret:" + body)

    provider = BrokenProvider()
    app.dependency_overrides[get_email_provider] = lambda: provider
    payload = {"email": "person@example.test", "password": PASSWORD}
    first = client.post(PREFIX + "/auth/register", json=payload)
    before = asyncio.run(snapshot(database))
    duplicate = client.post(PREFIX + "/auth/register", json=payload)
    assert first.status_code == duplicate.status_code == 202
    assert first.json() == duplicate.json() == RegistrationResult().model_dump()
    assert set(first.json()) == {"message"}
    users, challenges = asyncio.run(snapshot(database))
    assert len(users) == len(challenges) == len(provider.tokens) == 1
    assert users[0].state == "PENDING"
    assert [u.id for u in users] == [u.id for u in before[0]]
    assert [c.id for c in challenges] == [c.id for c in before[1]]
    for response in (first, duplicate):
        for secret in ("provider-secret", PASSWORD, provider.tokens[0], challenges[0].token_digest):
            assert secret not in response.text + caplog.text


@pytest.mark.parametrize("route,payload,secret", [
    ("/auth/register", {"email": "person@example.test", "password": "too-short"}, "too-short"),
    ("/auth/email-verification/confirm", {"token": "s" * 257}, "s" * 257),
    ("/auth/email-verification/confirm", {"token": "opaque-secret"}, "opaque-secret"),
])
def test_validation_and_confirmation_errors_redact_tokens(http, route, payload, secret, caplog):
    response = http[0].post(PREFIX + route, json=payload)
    assert response.status_code in {400, 422}
    assert secret not in response.text + caplog.text
    assert set(response.json()) == {"error_code", "details", "request_id"}


def test_input_dto_json_excludes_secrets():
    assert "never-show-this-password" not in RegisterRequest(
        email="person@example.test", password="never-show-this-password").model_dump_json()
    assert "never-show-this-token" not in VerifyEmailRequest(token="never-show-this-token").model_dump_json()


@pytest.mark.parametrize("mutation", ["revoked", "expired", "disabled", "idle", "absolute"])
def test_invalid_session_or_disabled_user_denied(http, database, mutation):
    client, provider, _ = http
    user_id, _ = asyncio.run(registered(database, provider))
    now = datetime.now(timezone.utc)
    overrides = {"revoked_at": now} if mutation == "revoked" else (
        {"last_activity_at": now - timedelta(days=15)} if mutation == "idle" else (
            {"created_at": now - timedelta(days=91)} if mutation == "absolute" else {}))
    token = asyncio.run(existing_access(database, user_id, **overrides))
    if mutation in {"disabled", "expired"}:
        async def mutate():
            async with database() as db, db.begin():
                await db.execute(update(User).values(state="DISABLED") if mutation == "disabled" else
                                 update(AuthSession).values(expires_at=now - timedelta(seconds=1)))
        asyncio.run(mutate())
    headers = {"Authorization": "Bearer " + token}
    assert client.get(PREFIX + "/users/me", headers=headers).status_code == 401
    assert client.patch(PREFIX + "/auth/email", json={"email": "new@example.test"}, headers=headers).status_code == 401
    assert (asyncio.run(snapshot(database)))[0][0].email_key == "person@example.test"


@pytest.mark.parametrize("kind", ["missing", "bad_signature", "wrong_algorithm", "wrong_issuer", "wrong_audience", "expired", "wrong_user"])
def test_invalid_bearer_denied(http, database, kind):
    client, provider, _ = http
    user_id, _ = asyncio.run(registered(database, provider))
    token = asyncio.run(existing_access(database, user_id))
    claims = jwt.decode(token, options={"verify_signature": False})
    if kind == "wrong_issuer":
        claims["iss"] = "wrong"
    if kind == "wrong_audience":
        claims["aud"] = "wrong"
    if kind == "expired":
        claims["exp"] = int(datetime.now(timezone.utc).timestamp()) - 1
    if kind == "wrong_user":
        claims["sub"] = str(user_id + 100000)
    token = jwt.encode(claims, secrets.token_urlsafe(48) if kind == "bad_signature" else os.environ["JWT_SECRET"],
                       algorithm="HS384" if kind == "wrong_algorithm" else "HS256")
    headers = {} if kind == "missing" else {"Authorization": "Bearer " + token}
    assert client.get(PREFIX + "/users/me", headers=headers).status_code == 401


def test_startup_requires_environment_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET must contain at least 32 bytes"):
        with TestClient(create_app()):
            pass


def test_exact_route_scope_and_openapi(http):
    schema = http[0].get("/openapi.json").json()
    identity = {path: set(methods) for path, methods in schema["paths"].items() if path.startswith(PREFIX)}
    assert identity == {
        PREFIX + "/auth/register": {"post"},
        PREFIX + "/auth/login": {"post"},
        PREFIX + "/auth/refresh": {"post"},
        PREFIX + "/auth/logout": {"post"},
        PREFIX + "/auth/email-verification/resend": {"post"},
        PREFIX + "/auth/email-verification/confirm": {"post"},
        PREFIX + "/auth/email": {"patch"},
        PREFIX + "/users/me": {"get"},
    }
    for path in ("/auth/password-reset", "/households"):
        assert http[0].post(PREFIX + path, json={}).status_code == 404


def test_resend_delivery_failure_is_generic_202(http, database):
    client, provider, _ = http
    past = datetime.now(timezone.utc) - timedelta(minutes=2)
    user_id, _ = asyncio.run(registered(database, provider, now=past))
    token = asyncio.run(existing_access(database, user_id))
    async def fail(**kwargs):
        raise RuntimeError("private provider detail")
    provider.send = fail
    response = client.post(PREFIX + "/auth/email-verification/resend",
                           headers={"Authorization": "Bearer " + token})
    assert response.status_code == 202
    assert response.json() == RegistrationResult().model_dump()
    assert "private" not in response.text
