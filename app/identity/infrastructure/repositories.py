"""Async persistence helpers. The application owns begin/commit/rollback.

Lock ordering for future workflows: user, household, acting member, session,
then token/challenge. These helpers do not constitute authorization.
"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain import normalize_email
from app.identity.infrastructure.models import (
    AuthChallenge, AuthSession, Household, HouseholdInvitation,
    HouseholdMember, RefreshToken, User,
)


class SqlAlchemyIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, record: object) -> None:
        self.session.add(record)
        await self.session.flush()

    async def user_by_email(self, email: str, *, lock: bool = False) -> User | None:
        statement = select(User).where(User.email_key == normalize_email(email))
        return await self.session.scalar(statement.with_for_update() if lock else statement)

    async def active_member(self, household_id: int, user_id: int, *, lock: bool = False) -> HouseholdMember | None:
        statement = select(HouseholdMember).where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.user_id == user_id,
            HouseholdMember.removed_at.is_(None),
        )
        return await self.session.scalar(statement.with_for_update() if lock else statement)

    async def lock_household(self, household_id: int) -> Household | None:
        return await self.session.scalar(select(Household).where(Household.id == household_id).with_for_update())

    async def lock_session(self, session_id: int, user_id: int) -> AuthSession | None:
        return await self.session.scalar(select(AuthSession).where(
            AuthSession.id == session_id, AuthSession.user_id == user_id,
        ).with_for_update())

    async def lock_refresh(self, session_id: int, digest: str) -> RefreshToken | None:
        # Lock the owning session first in the future application workflow.
        return await self.session.scalar(select(RefreshToken).where(
            RefreshToken.session_id == session_id, RefreshToken.token_digest == digest,
        ).with_for_update())

    async def lock_invitation(self, household_id: int, digest: str) -> HouseholdInvitation | None:
        return await self.session.scalar(select(HouseholdInvitation).where(
            HouseholdInvitation.household_id == household_id,
            HouseholdInvitation.token_digest == digest,
        ).with_for_update())

    async def lock_challenge(self, user_id: int, purpose: str, digest: str) -> AuthChallenge | None:
        return await self.session.scalar(select(AuthChallenge).where(
            AuthChallenge.user_id == user_id, AuthChallenge.purpose == purpose,
            AuthChallenge.token_digest == digest,
        ).with_for_update())

    async def clear_expired_grace(self, now: datetime) -> None:
        await self.session.execute(update(RefreshToken).where(
            RefreshToken.grace_expires_at <= now,
        ).values(successor_ciphertext=None, grace_expires_at=None))
