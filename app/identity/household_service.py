"""Household application transactions with fresh membership and explicit grants."""
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select

from app.identity.domain import normalize_email
from app.identity.household_dto import HouseholdResponse, InvitationResponse, MemberResponse
from app.identity.infrastructure.models import (
    AuditLog, Household, HouseholdInvitation, HouseholdMember, HouseholdSettings, Role, User,
)
from app.identity.infrastructure.repositories import SqlAlchemyIdentityRepository
from app.identity.infrastructure.security import token_digest
from app.identity.permissions import PermissionCode as P, allows, can_grant


class HouseholdRequestError(Exception):
    """Stable public status; no credentials or internal error details."""
    def __init__(self, *, status_code):
        self.status_code = status_code
        super().__init__()


class HouseholdService:
    def __init__(self, session, provider=None, *, clock=None):
        self.session = session
        self.provider = provider
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.repository = SqlAlchemyIdentityRepository(session)

    async def _user(self, user_id, *, lock=False):
        statement = select(User).where(User.id == user_id)
        user = await self.session.scalar(statement.with_for_update() if lock else statement)
        if user is None or user.state != "ACTIVE":
            raise HouseholdRequestError(status_code=403)
        return user

    async def _context(self, user_id, household_id, permission, *, write=False):
        await self._user(user_id, lock=write)
        household = (await self.repository.lock_household(household_id) if write else
                     await self.session.get(Household, household_id))
        member = await self.repository.active_member(household_id, user_id)
        if household is None or member is None:
            raise HouseholdRequestError(status_code=404)
        role = await self.session.scalar(select(Role.code).where(Role.id == member.role_id))
        if not allows(role, permission):
            raise HouseholdRequestError(status_code=403)
        if write and household.archived_at is not None:
            raise HouseholdRequestError(status_code=409)
        return household, member, role

    async def _role_id(self, code):
        return await self.session.scalar(select(Role.id).where(Role.code == code))

    async def _target(self, household_id, member_id):
        member = await self.session.scalar(select(HouseholdMember).where(
            HouseholdMember.id == member_id, HouseholdMember.household_id == household_id,
            HouseholdMember.removed_at.is_(None)))
        if member is None:
            raise HouseholdRequestError(status_code=404)
        role = await self.session.scalar(select(Role.code).where(Role.id == member.role_id))
        return member, role

    async def _owners(self, household_id):
        await self.session.flush()
        count = await self.session.scalar(select(func.count()).select_from(HouseholdMember).join(
            Role, Role.id == HouseholdMember.role_id).join(User, User.id == HouseholdMember.user_id).where(
                HouseholdMember.household_id == household_id, HouseholdMember.removed_at.is_(None),
                Role.code == "OWNER", User.state == "ACTIVE"))
        if not count:
            raise HouseholdRequestError(status_code=409)

    def _audit(self, household_id, actor, action, target_type, target_id):
        self.session.add(AuditLog(household_id=household_id, actor_member_id=actor.id,
            event_at=self.clock(), request_id=str(uuid4()), action=action,
            target_type=target_type, target_id=str(target_id), details={}))

    async def _household_result(self, household):
        settings = await self.session.get(HouseholdSettings, household.id)
        return HouseholdResponse(id=household.id, name=household.name, created_at=household.created_at,
            archived_at=household.archived_at, settings=settings.values if settings else {})

    def _member_result(self, member, role):
        return MemberResponse(id=member.id, user_id=member.user_id, role=role, joined_at=member.joined_at)

    def _invitation_result(self, invitation, role):
        return InvitationResponse.model_validate({
            **{name: getattr(invitation, name) for name in InvitationResponse.model_fields if name != "role"},
            "role": role,
        })

    async def create(self, user_id, body):
        async with self.session.begin():
            await self._user(user_id, lock=True)
            household = Household(name=body.name)
            self.session.add(household)
            await self.session.flush()
            # A new row is already exclusively owned by this transaction.
            await self.repository.lock_household(household.id)
            self.session.add(HouseholdSettings(household_id=household.id, values={}))
            member = HouseholdMember(household_id=household.id, user_id=user_id,
                                     role_id=await self._role_id("OWNER"))
            self.session.add(member)
            await self.session.flush()
            await self._owners(household.id)
            self._audit(household.id, member, "HOUSEHOLD_CREATED", "household", household.id)
            return await self._household_result(household)

    async def get(self, user_id, household_id):
        async with self.session.begin():
            household, _, _ = await self._context(user_id, household_id, P.VIEW)
            return await self._household_result(household)

    async def list_own(self, user_id):
        async with self.session.begin():
            await self._user(user_id)
            households = (await self.session.scalars(select(Household).join(
                HouseholdMember, HouseholdMember.household_id == Household.id).where(
                    HouseholdMember.user_id == user_id, HouseholdMember.removed_at.is_(None)
                ).order_by(Household.id))).all()
            return [await self._household_result(household) for household in households]

    async def patch(self, user_id, household_id, body):
        async with self.session.begin():
            household, actor, role = await self._context(user_id, household_id, P.SETTINGS, write=True)
            values = body.settings.model_dump(exclude_none=True) if body.settings else {}
            if role != "OWNER" and (body.name is not None or "currency" in values):
                raise HouseholdRequestError(status_code=403)
            if body.name is not None:
                household.name = body.name
            settings = await self.session.get(HouseholdSettings, household_id)
            if settings is None:
                settings = HouseholdSettings(household_id=household_id, values={})
                self.session.add(settings)
            settings.values = {**settings.values, **values}
            self._audit(household_id, actor, "HOUSEHOLD_UPDATED", "household", household_id)
            await self.session.flush()
            return await self._household_result(household)

    async def archive(self, user_id, household_id):
        async with self.session.begin():
            household, actor, _ = await self._context(user_id, household_id, P.ARCHIVE, write=True)
            household.archived_at = self.clock()
            self._audit(household_id, actor, "HOUSEHOLD_ARCHIVED", "household", household_id)

    async def members(self, user_id, household_id):
        async with self.session.begin():
            await self._context(user_id, household_id, P.VIEW)
            rows = (await self.session.execute(select(HouseholdMember, Role.code).join(
                Role, Role.id == HouseholdMember.role_id).where(
                    HouseholdMember.household_id == household_id, HouseholdMember.removed_at.is_(None)
                ).order_by(HouseholdMember.id))).all()
            return [self._member_result(member, role) for member, role in rows]

    async def change_role(self, user_id, household_id, member_id, role):
        async with self.session.begin():
            _, actor, actor_role = await self._context(user_id, household_id, P.MEMBERS, write=True)
            target, old_role = await self._target(household_id, member_id)
            if actor.id == target.id or not can_grant(actor_role, old_role) or not can_grant(actor_role, role):
                raise HouseholdRequestError(status_code=403)
            target.role_id = await self._role_id(role)
            await self._owners(household_id)
            self._audit(household_id, actor, "MEMBER_ROLE_CHANGED", "household_member", target.id)
            return self._member_result(target, role)

    async def remove(self, user_id, household_id, member_id):
        async with self.session.begin():
            _, actor, actor_role = await self._context(user_id, household_id, P.MEMBERS, write=True)
            target, role = await self._target(household_id, member_id)
            if not can_grant(actor_role, role):
                raise HouseholdRequestError(status_code=403)
            target.removed_at = self.clock()
            await self._owners(household_id)
            self._audit(household_id, actor, "MEMBER_REMOVED", "household_member", target.id)

    async def transfer(self, user_id, household_id, member_id):
        async with self.session.begin():
            _, actor, _ = await self._context(user_id, household_id, P.TRANSFER, write=True)
            target, _ = await self._target(household_id, member_id)
            state = await self.session.scalar(select(User.state).where(User.id == target.user_id))
            if target.id == actor.id or state != "ACTIVE":
                raise HouseholdRequestError(status_code=409)
            target.role_id = await self._role_id("OWNER")
            actor.role_id = await self._role_id("ADMIN")
            await self._owners(household_id)
            self._audit(household_id, actor, "OWNERSHIP_TRANSFERRED", "household_member", target.id)

    async def invite(self, user_id, household_id, body):
        async with self.session.begin():
            _, actor, role = await self._context(user_id, household_id, P.MEMBERS, write=True)
            if not can_grant(role, body.role):
                raise HouseholdRequestError(status_code=403)
            now = self.clock()
            email = normalize_email(body.email)
            prior = (await self.session.scalars(select(HouseholdInvitation).where(
                HouseholdInvitation.household_id == household_id, HouseholdInvitation.email_key == email,
                HouseholdInvitation.accepted_at.is_(None), HouseholdInvitation.revoked_at.is_(None)))).all()
            for invitation in prior:
                prior_role = await self.session.scalar(select(Role.code).where(Role.id == invitation.role_id))
                if not can_grant(role, prior_role):
                    raise HouseholdRequestError(status_code=403)
            for invitation in prior:
                invitation.revoked_at = now
                self._audit(household_id, actor, "INVITATION_REVOKED", "household_invitation", invitation.id)
            await self.session.flush()
            raw = secrets.token_urlsafe(32)
            invitation = HouseholdInvitation(household_id=household_id, email_key=email,
                role_id=await self._role_id(body.role), inviter_member_id=actor.id,
                token_digest=token_digest(raw), created_at=now, expires_at=now + timedelta(days=7))
            self.session.add(invitation)
            await self.session.flush()
            await self._owners(household_id)
            self._audit(household_id, actor, "INVITATION_CREATED", "household_invitation", invitation.id)
            result = self._invitation_result(invitation, body.role)
        # Delivery happens after commit. Never disclose or log tokens/provider errors.
        if self.provider is not None:
            try:
                await self.provider.send(recipient=email, subject="Household invitation", body=raw)
            except Exception:
                return result
            async with self.session.begin():
                stored = await self.session.get(HouseholdInvitation, result.id)
                stored.emailed_at = self.clock()
                result = self._invitation_result(stored, body.role)
        return result

    async def revoke(self, user_id, household_id, invitation_id):
        async with self.session.begin():
            _, actor, role = await self._context(user_id, household_id, P.MEMBERS, write=True)
            invitation = await self.session.scalar(select(HouseholdInvitation).where(
                HouseholdInvitation.household_id == household_id, HouseholdInvitation.id == invitation_id))
            if invitation is None:
                raise HouseholdRequestError(status_code=404)
            invited_role = await self.session.scalar(select(Role.code).where(Role.id == invitation.role_id))
            if not can_grant(role, invited_role):
                raise HouseholdRequestError(status_code=403)
            if invitation.accepted_at is not None or invitation.revoked_at is not None:
                raise HouseholdRequestError(status_code=409)
            invitation.revoked_at = self.clock()
            await self._owners(household_id)
            self._audit(household_id, actor, "INVITATION_REVOKED", "household_invitation", invitation.id)

    async def accept(self, user_id, household_id, raw):
        async with self.session.begin():
            user = await self._user(user_id, lock=True)
            household = await self.repository.lock_household(household_id)
            invitation = await self.repository.lock_invitation(household_id, token_digest(raw))
            now = self.clock()
            if (household is None or invitation is None or invitation.email_key != user.email_key
                    or invitation.accepted_at is not None or invitation.revoked_at is not None
                    or invitation.expires_at <= now):
                raise HouseholdRequestError(status_code=404)
            if household.archived_at is not None:
                raise HouseholdRequestError(status_code=409)
            inviter, inviter_role = await self._target(household_id, invitation.inviter_member_id)
            inviter_state = await self.session.scalar(select(User.state).where(User.id == inviter.user_id))
            role = await self.session.scalar(select(Role.code).where(Role.id == invitation.role_id))
            if inviter_state != "ACTIVE" or not can_grant(inviter_role, role):
                raise HouseholdRequestError(status_code=403)
            member = await self.session.scalar(select(HouseholdMember).where(
                HouseholdMember.household_id == household_id, HouseholdMember.user_id == user_id))
            if member is not None and member.removed_at is None:
                raise HouseholdRequestError(status_code=409)
            if member is None:
                member = HouseholdMember(household_id=household_id, user_id=user_id,
                                         role_id=invitation.role_id, joined_at=now)
                self.session.add(member)
            else:
                member.role_id, member.removed_at, member.joined_at = invitation.role_id, None, now
            invitation.accepted_at = now
            await self._owners(household_id)
            self._audit(household_id, member, "INVITATION_ACCEPTED", "household_invitation", invitation.id)
            return self._member_result(member, role)
