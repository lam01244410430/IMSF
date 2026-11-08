"""Thin household routes; all authorization and transactions live in the service."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_email_provider, require_active_user
from app.identity.dto import UserResponse
from app.identity.household_dto import (
    HouseholdCreate, HouseholdPatch, HouseholdResponse, InvitationAccept,
    InvitationCreate, InvitationResponse, MemberResponse, OwnershipTransfer, RolePatch,
)
from app.identity.household_service import HouseholdService
from app.identity.ports import EmailProvider

router = APIRouter(prefix="/api/v1/households")
ActiveUser = Annotated[UserResponse, Depends(require_active_user)]


def get_household_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[EmailProvider | None, Depends(get_email_provider)],
):
    return HouseholdService(session, provider)


Service = Annotated[HouseholdService, Depends(get_household_service)]


@router.post("", response_model=HouseholdResponse, status_code=201)
async def create(body: HouseholdCreate, user: ActiveUser, service: Service):
    return await service.create(user.id, body)


@router.get("", response_model=list[HouseholdResponse])
async def list_own(user: ActiveUser, service: Service):
    return await service.list_own(user.id)


@router.get("/{household_id}", response_model=HouseholdResponse)
async def get(household_id: int, user: ActiveUser, service: Service):
    return await service.get(user.id, household_id)


@router.patch("/{household_id}", response_model=HouseholdResponse)
async def patch(household_id: int, body: HouseholdPatch, user: ActiveUser, service: Service):
    return await service.patch(user.id, household_id, body)


@router.post("/{household_id}/archive", status_code=204)
async def archive(household_id: int, user: ActiveUser, service: Service):
    await service.archive(user.id, household_id)


@router.get("/{household_id}/members", response_model=list[MemberResponse])
async def members(household_id: int, user: ActiveUser, service: Service):
    return await service.members(user.id, household_id)


@router.patch("/{household_id}/members/{member_id}", response_model=MemberResponse)
async def change_role(household_id: int, member_id: int, body: RolePatch, user: ActiveUser, service: Service):
    return await service.change_role(user.id, household_id, member_id, body.role)


@router.delete("/{household_id}/members/{member_id}", status_code=204)
async def remove(household_id: int, member_id: int, user: ActiveUser, service: Service):
    await service.remove(user.id, household_id, member_id)


@router.post("/{household_id}/transfer", status_code=204)
async def transfer(household_id: int, body: OwnershipTransfer, user: ActiveUser, service: Service):
    await service.transfer(user.id, household_id, body.member_id)


@router.post("/{household_id}/invitations", response_model=InvitationResponse, status_code=201)
async def invite(household_id: int, body: InvitationCreate, user: ActiveUser, service: Service):
    return await service.invite(user.id, household_id, body)


@router.post("/{household_id}/invitations/accept", response_model=MemberResponse)
async def accept(household_id: int, body: InvitationAccept, user: ActiveUser, service: Service):
    return await service.accept(user.id, household_id, body.token.get_secret_value())


@router.delete("/{household_id}/invitations/{invitation_id}", status_code=204)
async def revoke(household_id: int, invitation_id: int, user: ActiveUser, service: Service):
    await service.revoke(user.id, household_id, invitation_id)
