"""Household contracts; invitation credentials are input-only."""
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.identity.domain import RoleCode
from app.identity.dto import EmailInput, VerifyEmailRequest


class HouseholdCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locale: Literal["en", "vi", "zh-Hans"] | None = None
    timezone: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Invalid timezone") from None
        return value


class HouseholdPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    settings: SettingsPatch | None = None


class HouseholdResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    archived_at: datetime | None
    settings: dict[str, str]


class MemberResponse(BaseModel):
    id: int
    user_id: int
    role: RoleCode
    joined_at: datetime


class RolePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: RoleCode


class InvitationCreate(EmailInput):
    role: RoleCode


class InvitationAccept(VerifyEmailRequest):
    pass


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    household_id: int
    email_key: str
    role: RoleCode
    inviter_member_id: int
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    emailed_at: datetime | None


class OwnershipTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_id: int = Field(gt=0)
