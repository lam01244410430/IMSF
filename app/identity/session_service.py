"""Session application transactions, serialized per user and family."""
import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import func, select, text
from starlette.concurrency import run_in_threadpool

from app.identity.auth_service import AuthService, IdentityRequestError
from app.identity.domain import normalize_email
from app.identity.infrastructure.models import AuthAuditEvent, AuthRateLimit, AuthSession, RefreshToken, User
from app.identity.infrastructure.rate_limits import SqlAlchemyRateLimitStorage
from app.identity.infrastructure.security import IdentitySecurity, token_digest, jwt_secret


def session_security():
    return IdentitySecurity(issuer=os.environ.get("JWT_ISSUER", ""),
                            audience=os.environ.get("JWT_AUDIENCE", ""))


@lru_cache(maxsize=1)
def dummy_password_hash():
    from app.identity.infrastructure.security import Argon2PasswordHasher
    return Argon2PasswordHasher().hash(secrets.token_urlsafe(32))


class SessionCsrfError(IdentityRequestError):
    """Cookie mutation rejected without exposing credential details."""


class SessionService(AuthService):
    async def login(self, email, password, ip):
        now = self.clock()
        email = normalize_email(email)
        allowed = True
        # MANAGER PROPOSAL: rolling 10/IP + 5/email per hour, committed on failure.
        async with self.session.begin():
            for scope, value, limit in (("login_ip", ip, 10), ("login_email", email, 5)):
                subject = hmac.new(jwt_secret().encode(), value.encode(), hashlib.sha256).hexdigest()
                await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"),
                                           {"key": int(subject[:15], 16)})
                count = await self.session.scalar(select(func.coalesce(func.sum(AuthRateLimit.attempts), 0)).where(
                    AuthRateLimit.scope == scope, AuthRateLimit.subject_digest == subject,
                    AuthRateLimit.window_started_at > now - timedelta(hours=1)))
                allowed = allowed and count < limit
                if count < limit:
                    await SqlAlchemyRateLimitStorage(self.session).increment(
                        scope=scope, subject_digest=subject, window_started_at=now)
        if not allowed:
            raise IdentityRequestError()
        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.email_key == email).with_for_update())
            # Do equal-cost password work for unknown accounts as well.
            encoded = user.password_hash if user else await run_in_threadpool(dummy_password_hash)
            valid = await run_in_threadpool(self.hasher.verify, password, encoded)
            if not valid or user is None or user.state == "DISABLED":
                raise IdentityRequestError()
            families = list((await self.session.scalars(select(AuthSession).where(
                AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthSession.created_at > now - timedelta(days=90),
                AuthSession.last_activity_at > now - timedelta(days=14)).order_by(AuthSession.last_activity_at, AuthSession.id).with_for_update())).all())
            if len(families) >= 10:
                families[0].revoked_at = now
                self.session.add(AuthAuditEvent(user_id=user.id, event_at=now,
                    request_id=str(uuid4()), event_code="SESSION_CAP_REVOKED"))
            csrf = secrets.token_urlsafe(32)
            family = AuthSession(user_id=user.id, created_at=now, last_activity_at=now,
                expires_at=now + timedelta(days=14), csrf_digest=token_digest(csrf))
            self.session.add(family)
            await self.session.flush()
            raw, token = await self._issue(family, now)
            return self._result(user, family, csrf, now), raw, token.expires_at

    def _result(self, user, family, csrf, now):
        return {"access_token": session_security().encode_access({"sub": str(user.id), "sid": family.id,
                "iat": now, "exp": now + timedelta(minutes=15)}), "token_type": "bearer",
                "expires_in": 900, "csrf_token": csrf, "state": user.state}

    async def _issue(self, family, now):
        raw = secrets.token_urlsafe(32)
        record = RefreshToken(session_id=family.id, token_digest=token_digest(raw), issued_at=now,
                              expires_at=min(now + timedelta(days=30), family.expires_at))
        self.session.add(record)
        await self.session.flush()
        return raw, record

    async def _locked(self, raw):
        owner = (await self.session.execute(select(AuthSession.user_id, AuthSession.id).join(
            RefreshToken, RefreshToken.session_id == AuthSession.id).where(
            RefreshToken.token_digest == token_digest(raw)))).first()
        if owner is None:
            return None, None, None
        user = await self.session.scalar(select(User).where(User.id == owner.user_id).with_for_update())
        family = await self.session.scalar(select(AuthSession).where(AuthSession.id == owner.id).with_for_update())
        token = await self.session.scalar(select(RefreshToken).where(RefreshToken.token_digest == token_digest(raw)).with_for_update())
        return user, family, token

    async def refresh(self, raw):
        now = self.clock()
        result = None
        async with self.session.begin():
            user, family, token = await self._locked(raw)
            now = self.clock()  # Evaluate deadlines after any lock wait.
            if family and not family.revoked_at and family.expires_at > now and (
                    family.created_at + timedelta(days=90) > now
                    and family.last_activity_at + timedelta(days=14) > now):
                if token.consumed_at is not None:
                    successor = await self.session.get(RefreshToken, token.successor_id)
                    if (token.grace_expires_at and now < token.grace_expires_at
                            and successor.consumed_at is None and token.successor_ciphertext):
                        if user.state != "ACTIVE":
                            raise IdentityRequestError()
                        material = session_security().decrypt_successor(token.successor_ciphertext,
                            grace_expires_at=token.grace_expires_at, now=now)
                        raw_next, csrf = material.split(":", 1)
                        family.last_activity_at = now
                        family.expires_at = min(family.created_at + timedelta(days=90), now + timedelta(days=14))
                        successor.expires_at = min(successor.issued_at + timedelta(days=30), family.expires_at)
                        result = self._result(user, family, csrf, now), raw_next, successor.expires_at
                    else:
                        family.revoked_at = now
                elif token.expires_at > now and user.state == "ACTIVE":
                    family.last_activity_at = now
                    family.expires_at = min(family.created_at + timedelta(days=90), now + timedelta(days=14))
                    csrf = secrets.token_urlsafe(32)
                    family.csrf_digest = token_digest(csrf)
                    raw_next, successor = await self._issue(family, now)
                    token.consumed_at = now
                    token.successor_id = successor.id
                    token.grace_expires_at = now + timedelta(seconds=10)
                    # MANAGER PROPOSAL: exact successor + CSRF encrypted with separate env key.
                    token.successor_ciphertext = session_security().encrypt_successor(raw_next + ":" + csrf)
                    result = self._result(user, family, csrf, now), raw_next, successor.expires_at
            if token and token.grace_expires_at and token.grace_expires_at <= now:
                token.successor_ciphertext = None
                token.grace_expires_at = None
        if result is None:
            raise IdentityRequestError()
        return result

    async def logout(self, raw, csrf):
        async with self.session.begin():
            _, family, _ = await self._locked(raw)
            if family is None or not hmac.compare_digest(family.csrf_digest, token_digest(csrf)):
                raise SessionCsrfError()
            family.revoked_at = self.clock()
