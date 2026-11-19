"""Lazy DB / Redis clients.

Engines are created lazily (and cached per URL) so tests can point
DATABASE_URL at a disposable database before first use.
"""

import os

import redis
import sqlalchemy as sa

_engines: dict[str, sa.Engine] = {}
_redis_clients: dict[str, redis.Redis] = {}


def get_engine() -> sa.Engine:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://imsf_v2:imsf_v2@127.0.0.1:55434/imsf_v2"
    )
    if url not in _engines:
        _engines[url] = sa.create_engine(url, pool_pre_ping=True)
    return _engines[url]


def get_redis() -> redis.Redis:
    url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    if url not in _redis_clients:
        _redis_clients[url] = redis.Redis.from_url(url, decode_responses=True)
    return _redis_clients[url]


QUEUE_KEY = "imsf-v2:receipt-jobs"
IDEMPOTENCY_PREFIX = "imsf-v2:idempotency:"
IDEMPOTENCY_TTL_SECONDS = 24 * 3600  # design §5: 24h
