"""Identity infrastructure adapter; no private HouseholdService contract."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from app.finance.domain import Actor, FinanceRequestError, HouseholdContext
from app.identity.infrastructure.models import AuthSession, Household, HouseholdMember, Role, User
from app.identity.permissions import allows


class SqlAlchemyHouseholdAccess:
    def __init__(self, session):
        self.session = session

    async def resolve(self, actor: Actor, household_id: int, permission: str, *, write: bool) -> HouseholdContext:
        async def one(model, *conditions):
            statement = select(model).where(*conditions).execution_options(populate_existing=True)
            return await self.session.scalar(statement.with_for_update() if write else statement)
        # Identity-compatible lock prefix: user → household → member → auth session.
        user = await one(User, User.id == actor.user_id)
        if user is None or user.state == "DISABLED":
            raise FinanceRequestError(401, "FINANCE_UNAUTHENTICATED")
        if user.state != "ACTIVE":
            raise FinanceRequestError(403, "FINANCE_FORBIDDEN")
        household = await one(Household, Household.id == household_id)
        member = await one(HouseholdMember, HouseholdMember.household_id == household_id,
                           HouseholdMember.user_id == actor.user_id, HouseholdMember.removed_at.is_(None))
        if household is None or member is None:
            raise FinanceRequestError(404, "FINANCE_NOT_FOUND")
        family = await one(AuthSession, AuthSession.id == actor.session_id, AuthSession.user_id == actor.user_id)
        now = datetime.now(timezone.utc)
        if (family is None or family.revoked_at is not None or family.expires_at <= now
            or family.created_at <= now - timedelta(days=90)
            or family.last_activity_at <= now - timedelta(days=14)):
            raise FinanceRequestError(401, "FINANCE_UNAUTHENTICATED")
        role = await self.session.scalar(select(Role.code).where(Role.id == member.role_id))
        if not allows(role, permission):
            raise FinanceRequestError(403, "FINANCE_FORBIDDEN")
        if write and household.archived_at is not None:
            raise FinanceRequestError(409, "FINANCE_HOUSEHOLD_ARCHIVED")
        return HouseholdContext(member_id=member.id, role=role)
