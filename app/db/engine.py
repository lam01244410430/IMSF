"""Async SQLAlchemy engine/session, built from DATABASE_URL only."""

import asyncio
import sys

# psycopg async cannot use the Windows ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_engine_url: str | None = None


def get_engine(database_url: str) -> AsyncEngine:
    global _engine, _engine_url
    if _engine is None or _engine_url != database_url:
        _engine = create_async_engine(database_url)
        _engine_url = database_url
    return _engine


def get_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(database_url), expire_on_commit=False)


async def dispose_engine() -> None:
    global _engine, _engine_url
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _engine_url = None