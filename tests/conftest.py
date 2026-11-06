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
