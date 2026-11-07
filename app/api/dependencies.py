"""Step 2 authentication: consume existing Bearer credentials, never issue them."""
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.identity.auth_service import AuthService
from app.identity.dto import UserResponse
from app.identity.infrastructure.email import EmailProvider
from app.identity.infrastructure.models import AuthSession, User

bearer = HTTPBearer(auto_error=False)


def jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret.encode()) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 bytes")
    return secret


async def get_db():
    url = get_settings().database_url
    if not url:
        raise HTTPException(status_code=503)
    async with get_session_factory(url)() as session:
        yield session


# Deployment may override this dependency with a configured provider. There is no
# console fallback, provider credential, or implicit production no-op delivery.
def get_email_provider() -> EmailProvider | None:
    return None


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[EmailProvider | None, Depends(get_email_provider)],
) -> AuthService:
    return AuthService(session, provider)


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    if credentials is None:
        raise HTTPException(status_code=401)
    # Issuer/audience are deployment identifiers, not JWT-controlled values.
    # Until configured, authenticated routes fail closed. No refresh encryption
    # key is needed here because Step 2 does not implement refresh or issuance.
    issuer = os.environ.get("JWT_ISSUER")
    audience = os.environ.get("JWT_AUDIENCE")
    if not issuer or not audience:
        raise HTTPException(status_code=401)
    try:
        claims = jwt.decode(
            credentials.credentials, jwt_secret(), algorithms=["HS256"],
            issuer=issuer, audience=audience,
            options={"require": ["sub", "sid", "iat", "exp", "iss", "aud"]},
        )
        if (not isinstance(claims["sub"], str) or not claims["sub"].isdigit()
                or type(claims["sid"]) is not int or claims["sid"] <= 0):
            raise ValueError()
        user_id, session_id = int(claims["sub"]), claims["sid"]
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
        raise HTTPException(status_code=401) from None
    now = datetime.now(timezone.utc)
    async with session.begin():
        user = await session.scalar(select(User).join(AuthSession, AuthSession.user_id == User.id).where(
            User.id == user_id, User.state.in_(["PENDING", "ACTIVE"]),
            AuthSession.id == session_id, AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
            AuthSession.created_at > now - timedelta(days=90),
            AuthSession.last_activity_at > now - timedelta(days=14),
        ))
        if user is None:
            raise HTTPException(status_code=401)
        return UserResponse.model_validate(user)


async def require_active_user(user: Annotated[UserResponse, Depends(current_user)]) -> UserResponse:
    """Backend gate for future household routes; PENDING never grants access.

    Membership and composite ownership checks remain mandatory in that later
    scope. This state gate alone does not authorize any household operation.
    """
    if user.state != "ACTIVE":
        raise HTTPException(status_code=403)
    return user
