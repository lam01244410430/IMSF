"""Application factory: health plus registration and email verification only."""
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.auth import router as auth_router
from app.api.dependencies import jwt_secret
from app.api.health import router as health_router
from app.identity.auth_service import IdentityRequestError
from app.identity.dto import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    jwt_secret()  # Required at startup, even though Step 2 never issues JWTs.
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="family-finance-inventory", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(auth_router)

    async def identity_error(request: Request, exc: Exception):
        status = exc.status_code if isinstance(exc, HTTPException) else (
            422 if isinstance(exc, RequestValidationError) else 400)
        # FastAPI validation errors normally echo input. Never serialize them:
        # malformed passwords and verification tokens are still secrets.
        return JSONResponse(status_code=status, content=ErrorResponse(
            request_id=str(uuid4()),
        ).model_dump(), headers={"Cache-Control": "no-store"})

    app.add_exception_handler(IdentityRequestError, identity_error)
    app.add_exception_handler(RequestValidationError, identity_error)
    app.add_exception_handler(HTTPException, identity_error)
    return app


app = create_app()
