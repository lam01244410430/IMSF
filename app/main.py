"""Application factory with identity and explicit browser protections."""
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.auth import router as auth_router
from app.api.households import router as households_router
from app.api.finance import router as finance_router
from app.api.inventory import router as inventory_router
from app.inventory.domain import InventoryRequestError
from app.finance.domain import FinanceRequestError
from app.api.dependencies import jwt_secret
from app.identity.session_service import session_security, SessionCsrfError
from app.api.browser import allowed_origins
from fastapi.middleware.cors import CORSMiddleware
from app.api.health import router as health_router
from app.identity.auth_service import IdentityRequestError
from app.identity.household_service import HouseholdRequestError
from app.identity.dto import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    jwt_secret()  # MANAGER PROPOSAL: minimum 32-byte environment secret.
    session_security()
    allowed_origins()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="family-finance-inventory", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(),
                       allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "Idempotency-Key"])
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(households_router)
    app.include_router(finance_router)
    app.include_router(inventory_router)

    async def identity_error(request: Request, exc: Exception):
        status = exc.status_code if isinstance(exc, (HTTPException, HouseholdRequestError)) else (
            422 if isinstance(exc, RequestValidationError) else (403 if isinstance(exc, SessionCsrfError) else 400))
        # FastAPI validation errors normally echo input. Never serialize them:
        # malformed passwords and verification tokens are still secrets.
        return JSONResponse(status_code=status, content=ErrorResponse(
            request_id=str(uuid4()),
        ).model_dump(), headers={"Cache-Control": "no-store"})

    async def finance_error(request: Request, exc: FinanceRequestError):
        return JSONResponse(status_code=exc.status_code, content={
            "error_code": exc.code, "details": {}, "request_id": str(uuid4()),
        }, headers={"Cache-Control": "no-store"})

    app.add_exception_handler(FinanceRequestError, finance_error)
    app.add_exception_handler(InventoryRequestError, finance_error)
    app.add_exception_handler(HouseholdRequestError, identity_error)
    app.add_exception_handler(SessionCsrfError, identity_error)
    app.add_exception_handler(IdentityRequestError, identity_error)
    app.add_exception_handler(RequestValidationError, identity_error)
    app.add_exception_handler(HTTPException, identity_error)
    return app


app = create_app()
