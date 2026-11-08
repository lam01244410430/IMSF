"""Thin identity routes; application services own session transactions."""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, HTTPException

from app.api.dependencies import current_user, get_auth_service, get_session_service
from app.identity.auth_service import AuthService
from app.identity.dto import (
    ChangeEmailRequest, RegisterRequest, RegistrationResult, UserResponse,
    VerifyEmailRequest, LoginRequest, SessionResult,
    PasswordResetRequest, PasswordResetConfirmRequest, PasswordResetResult, PasswordResetConfirmed,
)

router = APIRouter(prefix="/api/v1")
Service = Annotated[AuthService, Depends(get_auth_service)]
OwnUser = Annotated[UserResponse, Depends(current_user)]


@router.post("/auth/register", response_model=RegistrationResult, status_code=202)
async def register(body: RegisterRequest, service: Service):
    return await service.register(body)


@router.post("/auth/email-verification/resend", response_model=RegistrationResult, status_code=202)
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


Sessions = Annotated[object, Depends(get_session_service)]
COOKIE_PATH = "/api/v1/auth/"


def set_refresh(response, raw, expires):
    response.set_cookie("refresh_token", raw, httponly=True, secure=True,
                        samesite="lax", path=COOKIE_PATH, expires=expires)
    response.headers["Cache-Control"] = "no-store"


@router.post("/auth/login", response_model=SessionResult)
async def login(body: LoginRequest, request: Request, response: Response, service: Sessions):
    result, raw, expires = await service.login(body.email, body.password.get_secret_value(),
        request.client.host if request.client else "unknown")
    set_refresh(response, raw, expires)
    return result


@router.post("/auth/refresh", response_model=SessionResult)
async def refresh(request: Request, response: Response, service: Sessions):
    from app.api.browser import require_refresh_origin
    require_refresh_origin(request)
    result, raw, expires = await service.refresh(request.cookies.get("refresh_token", ""))
    set_refresh(response, raw, expires)
    return result


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, service: Sessions):
    csrf = request.headers.get("X-CSRF-Token")
    if not csrf:
        raise HTTPException(status_code=403)
    await service.logout(request.cookies.get("refresh_token", ""), csrf)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie("refresh_token", path=COOKIE_PATH, secure=True,
                           httponly=True, samesite="lax")
    return response


@router.post("/auth/password-reset/request", response_model=PasswordResetResult)
async def request_password_reset(body: PasswordResetRequest, request: Request,
                                 background_tasks: BackgroundTasks, response: Response, service: Service):
    response.headers["Cache-Control"] = "no-store"
    return await service.request_password_reset(body.email,
        request.client.host if request.client else "unknown", schedule=background_tasks.add_task)


@router.post("/auth/password-reset/confirm", response_model=PasswordResetConfirmed)
async def confirm_password_reset(body: PasswordResetConfirmRequest, request: Request,
                                 background_tasks: BackgroundTasks, response: Response, service: Service):
    response.headers["Cache-Control"] = "no-store"
    return await service.confirm_password_reset(body.token.get_secret_value(), body.password.get_secret_value(),
        request.client.host if request.client else "unknown", schedule=background_tasks.add_task)
