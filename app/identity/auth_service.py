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
from app.identity.infrastructure.models import (
    AuthChallenge, AuthRateLimit, Household, HouseholdMember, Role, User,
)
from app.identity.infrastructure.rate_limits import SqlAlchemyRateLimitStorage
from app.identity.infrastructure.security import Argon2PasswordHasher, token_digest, jwt_secret


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
            try:
                await self._deliver(email, token)
            except IdentityRequestError:
                pass
        return RegistrationResult()

    async def confirm(self, token: str, ip: str) -> RegistrationResult:
        now = self.clock()
        # Rolling-hour buckets avoid a reset at a wall-clock hour boundary.
        # The advisory lock serializes per-IP updates and checks across workers.
        secret = jwt_secret().encode()
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
                # Serialize state transitions with every membership/ownership write.
                # Lock all joined households (not only current OWNER memberships):
                # a concurrent transfer may promote this user while we wait.
                household_ids = (await self.session.scalars(select(HouseholdMember.household_id).where(
                    HouseholdMember.user_id == user_id, HouseholdMember.removed_at.is_(None)
                ).order_by(HouseholdMember.household_id))).all()
                for household_id in household_ids:
                    await self.session.scalar(select(Household).where(
                        Household.id == household_id).with_for_update())
                    role = await self.session.scalar(select(Role.code).join(
                        HouseholdMember, HouseholdMember.role_id == Role.id).where(
                            HouseholdMember.household_id == household_id,
                            HouseholdMember.user_id == user_id, HouseholdMember.removed_at.is_(None)))
                    if role == "OWNER":
                        others = await self.session.scalar(select(func.count()).select_from(HouseholdMember).join(
                            Role, Role.id == HouseholdMember.role_id).join(User, User.id == HouseholdMember.user_id).where(
                                HouseholdMember.household_id == household_id,
                                HouseholdMember.removed_at.is_(None), Role.code == "OWNER",
                                User.state == "ACTIVE", User.id != user_id))
                        if not others:
                            raise IdentityRequestError()
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

    async def _reset_budget(self, ip, now, email=None):
        """Committed rolling limits, including failed/unknown submissions.

        MANAGER PROPOSALS for merge review: shared request/confirm 5/hour/IP,
        request 3/hour/email_key. Request exhaustion still returns generic 200.
        """
        buckets = [("reset_ip", ip, 5)]
        if email is not None:
            buckets.append(("reset_email", email, 3))
        allowed = True
        async with self.session.begin():
            for scope, value, limit in buckets:
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
        return allowed

    async def _reset_deliver(self, email, subject, body):
        if self.provider is not None:
            try:
                await self.provider.send(recipient=email, subject=subject, body=body)
            except Exception:
                # Providers may include the secret body in exception messages.
                pass

    async def request_password_reset(self, email, ip, *, schedule=None):
        from app.identity.dto import PasswordResetResult
        email = normalize_email(email)
        now = self.clock()
        allowed = await self._reset_budget(ip, now, email)
        # Generate and digest on every path, including unknown/disabled users.
        raw = secrets.token_urlsafe(32)
        digest = token_digest(raw)
        recipient = None
        async with self.session.begin():
            user = await self.session.scalar(select(User).where(User.email_key == email).with_for_update())
            if allowed and user is not None and user.state != "DISABLED":
                now = self.clock()
                await self.session.execute(update(AuthChallenge).where(
                    AuthChallenge.user_id == user.id, AuthChallenge.purpose == "RESET_PASSWORD",
                    AuthChallenge.consumed_at.is_(None)).values(consumed_at=now))
                self.session.add(AuthChallenge(user_id=user.id, purpose="RESET_PASSWORD",
                    token_digest=digest, created_at=now, expires_at=now + timedelta(minutes=60)))
                await self.session.flush()
                recipient = user.email
        if recipient is not None:
            if schedule is None:
                await self._reset_deliver(recipient, "Reset your password", raw)
            else:
                # HTTP sends after the response, keeping provider latency/failure
                # out of public account-existence timing. No console fallback.
                schedule(self._reset_deliver, recipient, "Reset your password", raw)
        return PasswordResetResult()

    async def confirm_password_reset(self, raw, password, ip, *, schedule=None):
        from app.identity.dto import PasswordResetConfirmed
        from app.identity.infrastructure.models import AuthSession, RefreshToken
        now = self.clock()
        if not await self._reset_budget(ip, now):
            raise IdentityRequestError()
        valid = False
        recipient = None
        async with self.session.begin():
            digest = token_digest(raw)
            owner_id = await self.session.scalar(select(AuthChallenge.user_id).where(
                AuthChallenge.token_digest == digest, AuthChallenge.purpose == "RESET_PASSWORD"))
            if owner_id is not None:
                # Same lock ordering as login/refresh: user, then family/token.
                user = await self.session.scalar(select(User).where(User.id == owner_id).with_for_update())
                challenge = await self.session.scalar(select(AuthChallenge).where(
                    AuthChallenge.token_digest == digest, AuthChallenge.purpose == "RESET_PASSWORD").with_for_update())
                now = self.clock()
                if challenge.consumed_at is None and challenge.failed_attempts < 5:
                    eligible = user.state != "DISABLED" and challenge.expires_at > now
                    acceptable = 12 <= len(password) <= 128
                    if eligible and acceptable:
                        acceptable = not await run_in_threadpool(self.hasher.verify, password, user.password_hash)
                    if eligible and acceptable:
                        user.password_hash = await run_in_threadpool(self.hasher.hash, password)
                        await self.session.execute(update(AuthSession).where(
                            AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=now))
                        family_ids = select(AuthSession.id).where(AuthSession.user_id == user.id)
                        await self.session.execute(update(RefreshToken).where(
                            RefreshToken.session_id.in_(family_ids)).values(
                                consumed_at=func.coalesce(RefreshToken.consumed_at, now),
                                successor_ciphertext=None, grace_expires_at=None))
                        await self.session.execute(update(AuthChallenge).where(
                            AuthChallenge.user_id == user.id, AuthChallenge.purpose == "RESET_PASSWORD",
                            AuthChallenge.consumed_at.is_(None)).values(consumed_at=now))
                        recipient = user.email
                        valid = True
                    else:
                        challenge.failed_attempts += 1
                        if challenge.failed_attempts >= 5:
                            challenge.consumed_at = now
        # Raise outside the transaction: failed-attempt increments must persist.
        if not valid:
            raise IdentityRequestError()
        body = "Your password has changed. Please log in again."
        if schedule is None:
            await self._reset_deliver(recipient, "Password changed", body)
        else:
            schedule(self._reset_deliver, recipient, "Password changed", body)
        return PasswordResetConfirmed()
