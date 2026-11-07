"""Registration and verification application transactions only.

Step 2 never issues access, session, or refresh tokens. Authentication of own-user
routes consumes existing Bearer credentials; login belongs to a later step.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain import normalize_email
from app.identity.dto import RegistrationResult, RegisterRequest
from app.identity.infrastructure.email import EmailProvider
from app.identity.infrastructure.models import AuthChallenge, AuthRateLimit, User
from app.identity.infrastructure.rate_limits import SqlAlchemyRateLimitStorage
from app.identity.infrastructure.security import Argon2PasswordHasher, token_digest


class IdentityRequestError(Exception):
    """Generic public failure; never contains credentials or provider details."""


class AuthService:
    def __init__(self, session: AsyncSession, provider: EmailProvider | None = None, *, clock=None):
        self.session = session
        self.provider = provider
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.hasher = Argon2PasswordHasher()

    async def _challenge(self, user: User, now: datetime) -> str:
        await self.session.execute(update(AuthChallenge).where(
            AuthChallenge.user_id == user.id,
            AuthChallenge.purpose == "VERIFY_EMAIL",
            AuthChallenge.consumed_at.is_(None),
        ).values(consumed_at=now))
        token = secrets.token_urlsafe(32)
        self.session.add(AuthChallenge(
            user_id=user.id, purpose="VERIFY_EMAIL", token_digest=token_digest(token),
            created_at=now, expires_at=now + timedelta(hours=24),
        ))
        await self.session.flush()
        return token

    async def _deliver(self, email: str, token: str) -> None:
        if self.provider is None:
            raise IdentityRequestError()
        try:
            await self.provider.send(recipient=email, subject="Verify your email", body=token)
        except Exception:
            # Delivery is after commit: retain PENDING and its limits on failure.
            # Never log the exception; providers may include the secret body.
            raise IdentityRequestError() from None

    async def register(self, request: RegisterRequest) -> RegistrationResult:
        email = normalize_email(request.email)
        encoded = await run_in_threadpool(self.hasher.hash, request.password.get_secret_value())
        try:
            async with self.session.begin():
                user = User(email=email, email_key=email, password_hash=encoded,
                            locale=request.locale, state="PENDING")
                self.session.add(user)
                await self.session.flush()
                token = await self._challenge(user, self.clock())
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) != "23505":
                raise
            if self.provider is None:
                raise IdentityRequestError() from None
            return RegistrationResult()
        if self.provider is None:
            raise IdentityRequestError()
        try:
            await self._deliver(email, token)
        except IdentityRequestError:
            # Match duplicates without exposing provider delivery failures.
            return RegistrationResult()
        return RegistrationResult()

    async def resend(self, user_id: int) -> RegistrationResult:
        now = self.clock()
        email = token = None
        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is not None and user.state == "PENDING":
                latest, count = (await self.session.execute(select(
                    func.max(AuthChallenge.created_at), func.count(AuthChallenge.id),
                ).where(AuthChallenge.user_id == user.id,
                        AuthChallenge.purpose == "VERIFY_EMAIL",
                        AuthChallenge.created_at > now - timedelta(hours=24)))).one()
                if count < 5 and (latest is None or now - latest >= timedelta(seconds=60)):
                    token = await self._challenge(user, now)
                    email = user.email
        if token is not None:
            await self._deliver(email, token)
        return RegistrationResult()

    async def confirm(self, token: str, ip: str) -> RegistrationResult:
        now = self.clock()
        # Rolling-hour buckets avoid a reset at a wall-clock hour boundary.
        # The advisory lock serializes per-IP updates and checks across workers.
        secret = os.environ["JWT_SECRET"].encode()
        subject = hmac.new(secret, ip.encode(), hashlib.sha256).hexdigest()
        async with self.session.begin():
            await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"),
                                       {"key": int(subject[:15], 16)})
            attempts = await self.session.scalar(select(func.coalesce(func.sum(
                AuthRateLimit.attempts
            ), 0)).where(
                AuthRateLimit.scope == "verify_ip",
                AuthRateLimit.subject_digest == subject,
                AuthRateLimit.window_started_at > now - timedelta(hours=1),
            ))
            allowed = attempts < 10
            if allowed:
                await SqlAlchemyRateLimitStorage(self.session).increment(
                    scope="verify_ip", subject_digest=subject, window_started_at=now)
        if not allowed:
            raise IdentityRequestError()
        valid = False
        async with self.session.begin():
            digest = token_digest(token)
            owner_id = await self.session.scalar(select(AuthChallenge.user_id).where(
                AuthChallenge.token_digest == digest, AuthChallenge.purpose == "VERIFY_EMAIL"))
            if owner_id is not None:
                user = await self.session.scalar(select(User).where(User.id == owner_id).with_for_update())
                challenge = await self.session.scalar(select(AuthChallenge).where(
                    AuthChallenge.token_digest == digest, AuthChallenge.purpose == "VERIFY_EMAIL",
                ).with_for_update())
                if (user.state == "PENDING" and challenge.consumed_at is None
                        and challenge.expires_at > now):
                    challenge.consumed_at = now
                    user.state = "ACTIVE"
                    user.verified_at = now
                    valid = True
        if not valid:
            raise IdentityRequestError()
        return RegistrationResult()

    async def change_email(self, user_id: int, email: str) -> RegistrationResult:
        now = self.clock()
        email = normalize_email(email)
        try:
            async with self.session.begin():
                user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
                if user is None or user.state not in {"PENDING", "ACTIVE"}:
                    raise IdentityRequestError()
                if user.email_key == email:
                    return RegistrationResult()
                user.email = user.email_key = email
                user.state = "PENDING"
                user.verified_at = None
                # Changing the address invalidates old proofs. Delivery is requested
                # through resend, which retains the per-user cooldown and quota.
                await self.session.execute(update(AuthChallenge).where(
                    AuthChallenge.user_id == user.id,
                    AuthChallenge.purpose == "VERIFY_EMAIL",
                    AuthChallenge.consumed_at.is_(None),
                ).values(consumed_at=now))
                await self.session.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) != "23505":
                raise
            return RegistrationResult()
        return RegistrationResult()
