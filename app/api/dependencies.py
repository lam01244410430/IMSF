"""Bearer authentication and database-resolved household authorization."""
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
from app.identity.infrastructure.security import jwt_secret
from app.identity.infrastructure.repositories import SqlAlchemyIdentityRepository

bearer = HTTPBearer(auto_error=False)


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
    # key is needed here: access-token validation never decrypts refresh material.
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


async def require_household_member(
    household_id: int,
    user: Annotated[UserResponse, Depends(require_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Resolve current membership from persistence, never from token claims."""
    async with session.begin():
        member = await SqlAlchemyIdentityRepository(session).active_member(household_id, user.id)
        if member is None:
            raise HTTPException(status_code=404)
        return member


def get_session_service(session: Annotated[AsyncSession, Depends(get_db)]):
    from app.identity.session_service import SessionService
    return SessionService(session)


def require_household_permission(permission: str):
    """Reusable fail-closed gate for future household endpoint groups."""
    async def check(
        member: Annotated[object, Depends(require_household_member)],
        session: Annotated[AsyncSession, Depends(get_db)],
    ):
        from app.identity.infrastructure.models import Role
        from app.identity.permissions import allows
        async with session.begin():
            role = await session.scalar(select(Role.code).where(Role.id == member.role_id))
            if not allows(role, permission):
                raise HTTPException(status_code=403)
        return member
    return check
