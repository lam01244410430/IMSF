"""Health endpoints (P02-01 scope only: no auth, no household context)."""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.engine import get_engine

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    url = get_settings().database_url
    if not url:
        return JSONResponse(status_code=503, content={"status": "degraded"})
    try:
        engine = get_engine(url)
        async with asyncio.timeout(5):
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("readiness check failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "degraded"})
    return JSONResponse(status_code=200, content={"status": "ok"})