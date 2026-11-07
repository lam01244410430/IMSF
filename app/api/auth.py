"""Thin Step 2 routes. No login, refresh, reset, or household endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import current_user, get_auth_service
from app.identity.auth_service import AuthService
from app.identity.dto import (
    ChangeEmailRequest, RegisterRequest, RegistrationResult, UserResponse,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/api/v1")
Service = Annotated[AuthService, Depends(get_auth_service)]
OwnUser = Annotated[UserResponse, Depends(current_user)]


@router.post("/auth/register", response_model=RegistrationResult, status_code=202)
async def register(body: RegisterRequest, service: Service):
    return await service.register(body)


@router.post("/auth/email-verification/resend", response_model=RegistrationResult)
async def resend(user: OwnUser, service: Service):
    return await service.resend(user.id)


@router.post("/auth/email-verification/confirm", response_model=RegistrationResult)
async def confirm(body: VerifyEmailRequest, request: Request, service: Service):
    # Uvicorn must not trust arbitrary forwarded headers. Rate limits use the
    # transport peer; production proxy trust must be restricted by deployment.
    return await service.confirm(body.token.get_secret_value(),
                                 request.client.host if request.client else "unknown")


@router.patch("/auth/email", response_model=RegistrationResult)
async def change_email(body: ChangeEmailRequest, user: OwnUser, service: Service):
    return await service.change_email(user.id, body.email)


@router.get("/users/me", response_model=UserResponse)
async def me(user: OwnUser):
    return user
