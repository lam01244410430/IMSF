"""Opt-in disposable DB fixtures. Never create/drop DBs or derive dev URLs."""
import asyncio
import os
import re
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import command
from alembic.config import Config
from app.core.config import get_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def table_names(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return set((await connection.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ))).scalars())
    finally:
        await engine.dispose()


def migrate(revision: str, *, downgrade: bool = False) -> None:
    get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        if downgrade:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)
    finally:
        get_settings.cache_clear()


@pytest.fixture(scope="session")
def disposable_database_url():
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        pytest.fail("Set DATABASE_URL to a fresh disposable database")
    url = make_url(raw)
    name = url.database or ""
    if (url.drivername != "postgresql+psycopg"
        or not re.fullmatch(r"p02_test_[a-z0-9_]+", name)
        or os.environ.get("P02_DISPOSABLE_DATABASE") != name):
        pytest.fail("Refusing DB: require p02_test_* and matching P02_DISPOSABLE_DATABASE")
    if asyncio.run(table_names(raw)):
        pytest.fail("Disposable database must be fresh: public tables already exist")
    get_settings.cache_clear()
    yield raw
    get_settings.cache_clear()


@pytest.fixture
def identity_database(disposable_database_url):
    migrate("head")
    # Leave schema for operator inspection; every data write rolls back.
    return disposable_database_url


@pytest.fixture(autouse=True)
def refresh_grace_configuration(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("REFRESH_GRACE_KEY", Fernet.generate_key().decode())


async def cleanup_identity_database(engine):
    """FK-safe data cleanup for the explicitly disposable identity test DB only."""
    async with engine.begin() as connection:
        for table in (
            "refresh_tokens", "auth_challenges", "auth_audit_events", "auth_sessions",
            "auth_rate_limits", "audit_logs", "household_invitations", "household_members",
            "household_settings", "households", "users",
        ):
            await connection.execute(text(f"DELETE FROM {table}"))
    await engine.dispose()


@pytest.fixture(scope="session")
def finance_database_urls():
    """PROPOSAL OPEN-13: separate operator-provisioned, retained disposable DB.

    No identity refusal checks are relaxed. No retained finance cleanup occurs.
    Credentials are read only from environment and never included in failures.
    """
    migrator = os.environ.get("FINANCE_MIGRATOR_DATABASE_URL", "")
    runtime = os.environ.get("FINANCE_RUNTIME_DATABASE_URL", "")
    owner_url, runtime_url = make_url(migrator), make_url(runtime)
    name = owner_url.database or ""
    if (not re.fullmatch(r"p03_finance_test_[a-z0-9_]+", name)
        or os.environ.get("P03_DISPOSABLE_DATABASE") != name
        or owner_url.drivername != "postgresql+psycopg"
        or runtime_url.drivername != "postgresql+psycopg"
        or (owner_url.host, owner_url.port, name) != (runtime_url.host, runtime_url.port, runtime_url.database)
        or owner_url.username == runtime_url.username
        or runtime_url.username != os.environ.get("FINANCE_RUNTIME_ROLE")):
        pytest.fail("Refusing finance DB: require separate configured disposable DB and runtime role")
    if asyncio.run(table_names(migrator)):
        pytest.fail("Finance disposable database must be fresh")
    previous = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = migrator
        migrate("head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()

    async def verify_runtime():
        engine = create_async_engine(runtime)
        try:
            async with engine.connect() as connection:
                row = (await connection.execute(text("""SELECT r.rolsuper, r.rolcreaterole,
                    r.rolcreatedb, c.relowner = r.oid AS owns_table,
                    pg_has_role(current_user, c.relowner, 'MEMBER') AS owner_member
                    FROM pg_roles r CROSS JOIN pg_class c
                    WHERE r.rolname=current_user AND c.oid='households'::regclass"""))).one()
                assert tuple(row) == (False, False, False, False, False)
                assert not await connection.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')"))
        finally:
            await engine.dispose()
    asyncio.run(verify_runtime())
    return migrator, runtime


@pytest.fixture
def finance_db(finance_database_urls):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy.pool import NullPool
    engine = create_async_engine(finance_database_urls[1], poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(engine.dispose())


@pytest.fixture
def f(finance_db, monkeypatch):
    """Real JWT/session authentication; unique households retained, never deleted."""
    import secrets
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from uuid import uuid4
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.api.dependencies import get_db
    from app.identity.infrastructure.models import AuthSession, Household, HouseholdMember, HouseholdSettings, Role, User
    from app.identity.session_service import session_security
    from app.main import create_app

    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_ISSUER", "finance-test")
    monkeypatch.setenv("JWT_AUDIENCE", "finance-test")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://testserver")

    async def setup():
        now = datetime.now(timezone.utc)
        actors = {}
        async with finance_db() as db, db.begin():
            household = Household(name="Finance test " + uuid4().hex)
            other = Household(name="Other finance test " + uuid4().hex)
            db.add_all([household, other])
            await db.flush()
            db.add_all([HouseholdSettings(household_id=household.id, values={}),
                        HouseholdSettings(household_id=other.id, values={})])
            roles = dict((await db.execute(select(Role.code, Role.id))).all())
            for role in ("OWNER", "ADMIN", "FINANCE_MANAGER", "INVENTORY_MANAGER", "MEMBER", "VIEWER", "OUTSIDER"):
                email = uuid4().hex + "@example.test"
                user = User(email=email, email_key=email, state="ACTIVE", password_hash="test-only-unused")
                db.add(user)
                await db.flush()
                member = HouseholdMember(household_id=other.id if role == "OUTSIDER" else household.id,
                                         user_id=user.id, role_id=roles["OWNER" if role == "OUTSIDER" else role])
                family = AuthSession(user_id=user.id, created_at=now, last_activity_at=now,
                                     expires_at=now + timedelta(days=1), csrf_digest="a" * 64)
                db.add_all([member, family])
                await db.flush()
                token = session_security().encode_access({"sub": str(user.id), "sid": family.id,
                    "iat": now, "exp": now + timedelta(minutes=15)})
                actors[role] = SimpleNamespace(id=user.id, member_id=member.id, session_id=family.id,
                                               headers={"Authorization": "Bearer " + token})
            return household.id, other.id, actors
    hid, other_hid, actors = asyncio.run(setup())
    app = create_app()
    async def session():
        async with finance_db() as db:
            yield db
    app.dependency_overrides[get_db] = session
    with TestClient(app, base_url="https://testserver") as client:
        def request(method, path, *, role="OWNER", key=None, **kwargs):
            headers = dict(actors[role].headers)
            if key is not False:
                headers["Idempotency-Key"] = key if key is not None else uuid4().hex
            headers.update(kwargs.pop("headers", {}))
            return client.request(method, f"/api/v1/households/{hid}" + path, headers=headers, **kwargs)
        yield SimpleNamespace(hid=hid, other_hid=other_hid, actors=actors, client=client,
                              app=app, request=request, db=finance_db)
