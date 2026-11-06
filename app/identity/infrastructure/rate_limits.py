"""Rate-limit storage only; endpoint enforcement is outside Step 1."""

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.infrastructure.models import AuthRateLimit

# MANAGER PROPOSAL (merge gate): login 10/hour/IP and 5/hour/email_key.
# Future application errors must be generic and must not enumerate accounts.
# Subjects should be keyed HMAC digests, never plaintext IPs/emails. Application
# policy owns the hour alignment, key management, rejection, and retention.
LOGIN_IP_LIMIT = 10
LOGIN_EMAIL_LIMIT = 5


class SqlAlchemyRateLimitStorage:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def increment(self, *, scope: str, subject_digest: str, window_started_at: datetime) -> int:
        statement = insert(AuthRateLimit).values(
            scope=scope, subject_digest=subject_digest,
            window_started_at=window_started_at, attempts=1,
        ).on_conflict_do_update(
            index_elements=["scope", "subject_digest", "window_started_at"],
            set_={"attempts": AuthRateLimit.attempts + 1},
        ).returning(AuthRateLimit.attempts)
        # Atomic increment, but no commit: the future caller must persist failed
        # attempts independently of an authentication transaction that rolls back.
        return (await self.session.execute(statement)).scalar_one()
