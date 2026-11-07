"""Cryptographic primitives only; no login, reset, or rotation workflow."""

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

import jwt
from cryptography.fernet import Fernet
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.identity.domain import validate_password


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hasher = PasswordHash((Argon2Hasher(),))

    def hash(self, password: str) -> str:
        validate_password(password)
        return self._hasher.hash(password)

    def verify(self, password: str, encoded: str) -> bool:
        return self._hasher.verify(password, encoded)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret.encode()) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 bytes")
    return secret


class IdentitySecurity:
    def __init__(self, *, issuer: str, audience: str) -> None:
        # MANAGER PROPOSAL (merge gate): HS256 via PyJWT; JWT_SECRET only from
        # process env, no default. Future identity startup MUST construct this
        # adapter and fail closed. Step 1 deliberately does not wire app startup.
        secret = os.environ.get("JWT_SECRET", "")
        grace_key = os.environ.get("REFRESH_GRACE_KEY", "")
        if len(secret.encode("utf-8")) < 32:
            raise RuntimeError("JWT_SECRET must contain at least 32 bytes")
        if not grace_key or grace_key == secret:
            raise RuntimeError("A separate REFRESH_GRACE_KEY is required")
        if not issuer or not audience:
            raise ValueError("JWT issuer and audience are required")
        self._secret = secret
        try:
            self._fernet = Fernet(grace_key.encode("ascii"))
        except (ValueError, UnicodeError):
            raise RuntimeError("REFRESH_GRACE_KEY must be a valid Fernet key") from None
        self._issuer = issuer
        self._audience = audience

    def encode_access(self, claims: dict[str, Any]) -> str:
        payload = {**claims, "iss": self._issuer, "aud": self._audience}
        if not {"sub", "sid", "iat", "exp"} <= payload.keys():
            raise ValueError("Missing access claims")
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def decode_access(self, token: str) -> dict[str, Any]:
        return jwt.decode(
            token, self._secret, algorithms=["HS256"],
            issuer=self._issuer, audience=self._audience,
            options={"require": ["sub", "sid", "iat", "exp", "iss", "aud"]},
        )

    def encrypt_successor(self, token: str) -> bytes:
        return self._fernet.encrypt(token.encode("utf-8"))

    def decrypt_successor(self, ciphertext: bytes, *, grace_expires_at: datetime, now: datetime | None = None) -> str:
        # The caller must lock the session and verify that the successor remains
        # current. Expired ciphertext is cleared through the repository in the
        # caller's transaction; this adapter never bypasses the grace deadline.
        if (now or datetime.now(timezone.utc)) >= grace_expires_at:
            raise ValueError("Refresh grace expired")
        return self._fernet.decrypt(ciphertext).decode("utf-8")
