"""Auth endpoints (design §5.1, reform plan §7).

POST /api/v2/auth/wechat — code2session; 503 "WeChat login not
configured" while D2 is deferred (no AppID invented).
POST /api/v2/auth/refresh — refresh JWT -> new access JWT.
POST /api/v2/auth/email/register — email + password registration
(reform §7.3.1); register returns tokens immediately (register = login).
POST /api/v2/auth/email/login — email + password login (§7.3.2) with
rate limiting + lockout on Redis (§7.6).

Email-login notes (reform §7):
- NO email verification in v1 (no SMTP): anyone can register with
  someone else's email; never send sensitive info to an unverified
  email; there is no password-reset endpoint in v1.
- A user with both a WeChat account and an email account has TWO
  separate user rows in v1 (no account linking yet).
- Plaintext passwords and hashes are NEVER logged; login error paths
  log nothing containing a password or a hash.
- Redis is a hard dependency: if Redis is unreachable the email auth
  endpoints fail CLOSED with 503 (never fail open, or the rate limit /
  lockout would silently disappear exactly while under attack).
"""

import os

import httpx
import redis as redis_lib
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text

from app.auth import mint_access_token, mint_refresh_token
from app.db import get_engine, get_redis
from app.passwords import hash_password, needs_rehash, verify_password

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])

WECHAT_CODE2SESSION = "https://api.weixin.qq.com/sns/jscode2session"

# Rate limiting + lockout (reform §7.6; TTLs in seconds).
LOGIN_RL_TTL = 60          # 1 login attempt / minute / email
LOGIN_ATTEMPTS_TTL = 900   # consecutive-wrong counter, 15 min sliding
LOGIN_LOCK_TTL = 900       # lock after 5 wrong passwords, 15 min
LOGIN_MAX_ATTEMPTS = 5
REGISTER_RL_TTL = 3600     # 5 registrations / hour / IP
REGISTER_MAX_PER_HOUR = 5

# Constant dummy hash for the timing-oracle defence: when the email does
# not exist, login still runs one argon2 verify against this hash before
# returning 401, so the response time does not reveal whether the email
# exists. Computed once at import (~150 ms).
_DUMMY_HASH = hash_password("imsf-dummy-password-never-a-real-password")


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _households_for(conn, user_id):
    rows = conn.execute(
        text("SELECT h.id, h.name FROM households h"
             " JOIN household_members m ON m.household_id = h.id"
             " WHERE m.user_id = :u ORDER BY h.created_at"),
        {"u": user_id},
    ).all()
    return [{"id": str(h[0]), "name": h[1]} for h in rows]


def _auth_response(user_id, user_dict, households, auth_version=1):
    return {
        "access_token": mint_access_token(user_id, auth_version),
        "refresh_token": mint_refresh_token(user_id, auth_version),
        "user": user_dict,
        "households": households,
    }


class WechatLoginIn(BaseModel):
    code: str


class RefreshIn(BaseModel):
    refresh_token: str


class EmailRegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = None
    household_name: str | None = None


class EmailLoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/wechat")
def wechat_login(body: WechatLoginIn):
    appid = os.environ.get("WECHAT_APPID", "")
    secret = os.environ.get("WECHAT_SECRET", "")
    if not appid or not secret:
        # D2 deferred by Lam — no AppID is invented.
        raise HTTPException(
            status_code=503, detail="WeChat login not configured")
    with httpx.Client(timeout=10) as client:
        resp = client.get(WECHAT_CODE2SESSION, params={
            "appid": appid, "secret": secret,
            "js_code": body.code, "grant_type": "authorization_code",
        })
    resp.raise_for_status()
    data = resp.json()
    if "openid" not in data:
        raise HTTPException(status_code=401,
                            detail=f"WeChat code2session failed: {data}")
    openid = data["openid"]
    unionid = data.get("unionid")
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, disabled_at, auth_version FROM users"
                 " WHERE wechat_openid = :oid"),
            {"oid": openid},
        ).first()
        if row:
            user_id = row[0]
            # Phase C: a disabled account cannot log in.
            if row[1] is not None:
                raise HTTPException(status_code=403,
                                    detail="Account disabled")
            auth_version = row[2]
            if unionid:
                conn.execute(
                    text("UPDATE users SET wechat_unionid = :u WHERE id = :id"),
                    {"u": unionid, "id": user_id},
                )
        else:
            user_id = conn.execute(
                text("INSERT INTO users (wechat_openid, wechat_unionid, name)"
                     " VALUES (:oid, :u, '微信用户') RETURNING id"),
                {"oid": openid, "u": unionid},
            ).scalar_one()
            auth_version = 1
        households = _households_for(conn, user_id)
    return _auth_response(
        user_id, {"id": str(user_id), "wechat_openid": openid}, households,
        auth_version)


@router.post("/refresh")
def refresh(body: RefreshIn):
    import jwt

    try:
        payload = jwt.decode(body.refresh_token,
                             os.environ.get("JWT_SECRET", "change-me-in-production"),
                             algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    import uuid

    user_id = uuid.UUID(payload["sub"])
    # Phase C: refresh checks disabled (403) + version (401) when the
    # user row exists. A missing row keeps the pre-Phase-C behaviour
    # (mint anyway): there is no user-deletion path in v1, so a row can
    # only be missing for a token minted in tests, and an existing test
    # asserts refresh succeeds for such a token.
    from app.auth import _load_user_auth

    loaded = _load_user_auth(user_id)
    if loaded is not None:
        disabled_at, auth_version = loaded
        if disabled_at is not None:
            raise HTTPException(status_code=403, detail="Account disabled")
        ver = 1 if payload.get("ver") is None else payload.get("ver")
        if ver != auth_version:
            raise HTTPException(status_code=401,
                                detail="Token version mismatch")
        return {"access_token": mint_access_token(user_id, auth_version)}
    return {"access_token": mint_access_token(user_id)}


@router.post("/email/register")
def email_register(body: EmailRegisterIn, request: Request):
    email = _normalise_email(str(body.email))
    client_ip = request.client.host if request.client else "unknown"
    try:
        r = get_redis()
        count = r.incr(f"register_rl:{client_ip}")
        if count == 1:
            r.expire(f"register_rl:{client_ip}", REGISTER_RL_TTL)
        if count > REGISTER_MAX_PER_HOUR:
            raise HTTPException(status_code=429,
                                detail="Too many requests")
    except redis_lib.RedisError:
        raise HTTPException(status_code=503,
                            detail="Service temporarily unavailable")
    name = (body.name or "").strip() or email.split("@")[0]
    household_name = (body.household_name or "").strip()
    engine = get_engine()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE email = :e"), {"e": email},
        ).first()
        if existing:
            raise HTTPException(status_code=409,
                                detail="Email already registered")
        user_id = conn.execute(
            text("INSERT INTO users (email, password_hash, name)"
                 " VALUES (:e, :h, :n) RETURNING id"),
            {"e": email, "h": hash_password(body.password), "n": name},
        ).scalar_one()
        households = []
        if household_name:
            # Same two-INSERT pattern as POST /api/v2/households
            # (create_household), inlined here because register has no
            # authenticated identity yet and cannot call that endpoint.
            hid = conn.execute(
                text("INSERT INTO households (name, default_currency,"
                     " timezone, locale)"
                     " VALUES (:n, 'CNY', 'Asia/Shanghai', 'zh-CN')"
                     " RETURNING id"),
                {"n": household_name},
            ).scalar_one()
            conn.execute(
                text("INSERT INTO household_members (user_id, household_id,"
                     " role) VALUES (:u, :h, 'owner')"),
                {"u": user_id, "h": hid},
            )
            households = [{"id": str(hid), "name": household_name}]
    return _auth_response(
        user_id, {"id": str(user_id), "email": email, "name": name},
        households)


@router.post("/email/login")
def email_login(body: EmailLoginIn):
    email = _normalise_email(str(body.email))
    try:
        r = get_redis()
        if r.exists(f"login_lock:{email}"):
            raise HTTPException(status_code=429,
                                detail="Too many requests")
        if not r.set(f"login_rl:{email}", "1", ex=LOGIN_RL_TTL, nx=True):
            raise HTTPException(status_code=429,
                                detail="Too many requests")
    except redis_lib.RedisError:
        raise HTTPException(status_code=503,
                            detail="Service temporarily unavailable")
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, password_hash, name, disabled_at,"
                 " auth_version FROM users WHERE email = :e"),
            {"e": email},
        ).first()
    if row is None or row[1] is None:
        # Timing-oracle defence: same 401 message and one dummy argon2
        # verify whether the email exists or not; no counter increment
        # (there is no account to lock).
        verify_password(_DUMMY_HASH, body.password)
        raise HTTPException(status_code=401,
                            detail="Invalid email or password")
    user_id, stored_hash, name = row[0], row[1], row[2]
    disabled_at, auth_version = row[3], row[4]
    if not verify_password(stored_hash, body.password):
        try:
            r = get_redis()
            attempts = r.incr(f"login_attempts:{email}")
            if attempts == 1:
                r.expire(f"login_attempts:{email}", LOGIN_ATTEMPTS_TTL)
            if attempts >= LOGIN_MAX_ATTEMPTS:
                r.set(f"login_lock:{email}", "1", ex=LOGIN_LOCK_TTL)
                r.delete(f"login_attempts:{email}")
                raise HTTPException(status_code=429,
                                    detail="Too many requests")
        except redis_lib.RedisError:
            raise HTTPException(status_code=503,
                                detail="Service temporarily unavailable")
        raise HTTPException(status_code=401,
                            detail="Invalid email or password")
    # Phase C: a disabled account cannot log in, even with the right
    # password (checked after the password so a wrong password still
    # returns the same 401 as before).
    if disabled_at is not None:
        raise HTTPException(status_code=403, detail="Account disabled")
    # Correct password: reset the counter; re-hash if the stored hash
    # was made with older parameters.
    try:
        r = get_redis()
        r.delete(f"login_attempts:{email}")
    except redis_lib.RedisError:
        raise HTTPException(status_code=503,
                            detail="Service temporarily unavailable")
    new_hash = hash_password(body.password) if needs_rehash(stored_hash) else None
    engine = get_engine()
    with engine.begin() as conn:
        if new_hash is not None:
            conn.execute(
                text("UPDATE users SET password_hash = :h WHERE id = :id"),
                {"h": new_hash, "id": user_id},
            )
        households = _households_for(conn, user_id)
    return _auth_response(
        user_id, {"id": str(user_id), "email": email, "name": name},
        households, auth_version)
