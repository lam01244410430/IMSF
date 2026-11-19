"""Auth endpoints (design §5.1).

POST /api/v2/auth/wechat — code2session; 503 "WeChat login not
configured" while D2 is deferred (no AppID invented).
POST /api/v2/auth/refresh — refresh JWT -> new access JWT.
"""

import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import mint_access_token, mint_refresh_token
from app.db import get_engine

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])

WECHAT_CODE2SESSION = "https://api.weixin.qq.com/sns/jscode2session"


class WechatLoginIn(BaseModel):
    code: str


class RefreshIn(BaseModel):
    refresh_token: str


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
            text("SELECT id FROM users WHERE wechat_openid = :oid"),
            {"oid": openid},
        ).first()
        if row:
            user_id = row[0]
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
        households = conn.execute(
            text("SELECT h.id, h.name FROM households h"
                 " JOIN household_members m ON m.household_id = h.id"
                 " WHERE m.user_id = :u ORDER BY h.created_at"),
            {"u": user_id},
        ).all()
    return {
        "access_token": mint_access_token(user_id),
        "refresh_token": mint_refresh_token(user_id),
        "user": {"id": str(user_id), "wechat_openid": openid},
        "households": [{"id": str(h[0]), "name": h[1]} for h in households],
    }


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

    return {"access_token": mint_access_token(uuid.UUID(payload["sub"]))}
