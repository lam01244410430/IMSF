"""Auth for IMSF Phase 1 (design §5).

Two bearer schemes, both checked by ``require_auth``:
- JWT access token (HS256, 15 min), ``sub`` = user UUID, ``typ`` = "access".
- Service token (env ``IMSF_SERVICE_TOKEN``), eval/demo only. It maps to
  a dedicated service user row (``wechat_openid = 'imsf-service'``),
  created on first use, so household-membership checks work uniformly.

Refresh tokens are JWTs with ``typ`` = "refresh" (7 days).

Phase C (admin dashboard, contract §1.2): both token types carry a
``ver`` claim = the user's ``auth_version`` at mint time. ``require_auth``
(and ``optional_auth``) check the account is enabled (``disabled_at``
NULL) and the token version matches the row; a disabled account gets
403, a stale version gets 401. Tokens minted before this change have
no ``ver`` claim: a missing ``ver`` is treated as version 1. Disabling
or re-enabling a user (and a password reset) bumps ``auth_version``,
so old tokens stay invalid even after re-enable.
"""

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from app.db import get_engine

log = logging.getLogger("imsf-auth")

bearer_scheme = HTTPBearer(auto_error=False)

SERVICE_OPENID = "imsf-service"
SERVICE_USER_NAME = "IMSF service (eval/demo)"


def _jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "change-me-in-production")


def _service_token() -> str:
    return os.environ.get("IMSF_SERVICE_TOKEN", "")


def mint_access_token(user_id: uuid.UUID, auth_version: int = 1) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "typ": "access", "ver": auth_version,
         "exp": now + timedelta(minutes=15), "iat": now},
        _jwt_secret(), algorithm="HS256",
    )


def mint_refresh_token(user_id: uuid.UUID, auth_version: int = 1) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "typ": "refresh", "ver": auth_version,
         "exp": now + timedelta(days=7), "iat": now},
        _jwt_secret(), algorithm="HS256",
    )


def get_or_create_service_user() -> uuid.UUID:
    """Return the id of the dedicated service-token user (create if needed)."""
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM users WHERE wechat_openid = :oid"),
            {"oid": SERVICE_OPENID},
        ).first()
        if row:
            return row[0]
        return conn.execute(
            text("INSERT INTO users (wechat_openid, name) "
                 "VALUES (:oid, :name) RETURNING id"),
            {"oid": SERVICE_OPENID, "name": SERVICE_USER_NAME},
        ).scalar_one()


class Identity:
    def __init__(self, user_id: uuid.UUID, via_service_token: bool):
        self.user_id = user_id
        self.via_service_token = via_service_token


def _load_user_auth(user_id: uuid.UUID):
    """(disabled_at, auth_version) for a user, or None if no such row."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT disabled_at, auth_version FROM users"
                 " WHERE id = :id"),
            {"id": user_id},
        ).first()
    if row is None:
        return None
    return row[0], row[1]


def _check_user_auth(user_id: uuid.UUID, token_ver) -> None:
    """Phase C enabled + version check (contract §1.2).

    Raises 401 when the user does not exist or the token version is
    stale (a missing ``ver`` claim counts as version 1), and 403 when
    the account is disabled. Service-token identities never reach
    here (they skip this check by design).
    """
    loaded = _load_user_auth(user_id)
    if loaded is None:
        raise HTTPException(status_code=401, detail="User not found")
    disabled_at, auth_version = loaded
    if disabled_at is not None:
        raise HTTPException(status_code=403, detail="Account disabled")
    ver = 1 if token_ver is None else token_ver
    if ver != auth_version:
        raise HTTPException(status_code=401,
                            detail="Token version mismatch")


def get_admin_user_ids() -> set[uuid.UUID]:
    """Admin allowlist from env ``IMSF_ADMIN_USER_IDS`` (contract §1.3).

    Comma-separated user UUIDs. Empty / missing / malformed (any entry
    not a UUID) grants NOBODY admin access. Never authorize by email.
    Read on every call so a config change takes effect on restart
    without a code change.
    """
    raw = os.environ.get("IMSF_ADMIN_USER_IDS", "")
    ids: set[uuid.UUID] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(uuid.UUID(part))
        except ValueError:
            return set()
    return ids


def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Identity:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = creds.credentials
    service = _service_token()
    if service and secrets.compare_digest(token, service):
        return Identity(get_or_create_service_user(), via_service_token=True)
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="Not an access token")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    _check_user_auth(user_id, payload.get("ver"))
    return Identity(user_id, via_service_token=False)

def optional_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Identity | None:
    """Identity when a valid bearer token is sent, else None.

    For public endpoints (recipe list/detail): anonymous readers are
    never 401'd. A missing credential is anonymous; an expired /
    invalid token is also treated as anonymous (the web client
    refreshes before calling, so a stale token here means the caller
    is effectively logged out). A disabled account or a stale token
    version likewise degrades to anonymous instead of raising.
    """
    if creds is None or not creds.credentials:
        return None
    token = creds.credentials
    service = _service_token()
    if service and secrets.compare_digest(token, service):
        return Identity(get_or_create_service_user(),
                        via_service_token=True)
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != "access":
        return None
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None
    try:
        _check_user_auth(user_id, payload.get("ver"))
    except HTTPException:
        return None
    return Identity(user_id, via_service_token=False)


def require_admin(
    ident: Identity = Depends(require_auth),
) -> Identity:
    """Shared admin dependency for the whole admin router (§1.3).

    Order: valid JWT (401, via ``require_auth``, which already enforces
    enabled + version) -> service-token identities are never admin
    (403) -> user id must be in the ``IMSF_ADMIN_USER_IDS`` allowlist
    (403). Denied attempts are logged by the caller / server log, not
    written to the audit table.
    """
    if ident.via_service_token:
        # Denied attempts go to the structured server log only,
        # never to the audit table (contract §1.3). No token is logged.
        log.warning("admin denied: service-token identity")
        raise HTTPException(status_code=403,
                            detail="Service token is not an admin")
    if ident.user_id not in get_admin_user_ids():
        log.warning("admin denied: user_id=%s not in allowlist",
                    ident.user_id)
        raise HTTPException(status_code=403, detail="Not an admin")
    return ident


def require_household_member(household_id: uuid.UUID, ident: Identity) -> None:
    """400 if the household does not belong to the caller (design §5.4)."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM household_members "
                 "WHERE user_id = :u AND household_id = :h"),
            {"u": ident.user_id, "h": household_id},
        ).first()
    if not row:
        raise HTTPException(
            status_code=400, detail="household_id does not belong to user"
        )


def require_household_member_403(household_id: uuid.UUID, ident: Identity) -> None:
    """403 if the household does not belong to the caller.

    Phase 2 design §5.4: the NEW Phase 2 endpoints return 403 here,
    unlike the Phase 1 ``require_household_member`` (400) which the
    Phase 1 endpoints keep.
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM household_members "
                 "WHERE user_id = :u AND household_id = :h"),
            {"u": ident.user_id, "h": household_id},
        ).first()
    if not row:
        raise HTTPException(
            status_code=403, detail="household_id does not belong to user"
        )


def require_receipt_household(receipt_household_id: uuid.UUID, ident: Identity) -> None:
    """403 if the receipt belongs to another household (design §5.4)."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM household_members "
                 "WHERE user_id = :u AND household_id = :h"),
            {"u": ident.user_id, "h": receipt_household_id},
        ).first()
    if not row:
        raise HTTPException(
            status_code=403, detail="Receipt does not belong to user's household"
        )
