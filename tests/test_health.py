"""Health endpoint tests (P02-01)."""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.engine import dispose_engine
from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_health_liveness_no_db() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_db_up(monkeypatch: pytest.MonkeyPatch) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set; DB-up readiness needs a database")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        response = _client().get("/health/ready")
    finally:
        asyncio.run(dispose_engine())
        get_settings.cache_clear()
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_db_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://127.0.0.1:59999/nodb")
    get_settings.cache_clear()
    try:
        response = _client().get("/health/ready")
    finally:
        asyncio.run(dispose_engine())
        get_settings.cache_clear()
    assert response.status_code == 503
    assert response.json() == {"status": "degraded"}