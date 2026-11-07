"""Explicit public identity contracts; credentials are input-only."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.identity.domain import normalize_email


class EmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def email_key(cls, value: str) -> str:
        value = normalize_email(value)
        if value.count("@") != 1 or any(c.isspace() for c in value):
            raise ValueError("Invalid email")
        local, domain = value.split("@")
        if not local or not domain:
            raise ValueError("Invalid email")
        return value


class RegisterRequest(EmailInput):
    password: SecretStr = Field(min_length=12, max_length=128, exclude=True)
    locale: Literal["en", "vi", "zh-Hans"] = "en"


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: SecretStr = Field(min_length=1, max_length=256, exclude=True)


class ChangeEmailRequest(EmailInput):
    pass


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    locale: str
    state: Literal["PENDING", "ACTIVE", "DISABLED"]
    verified_at: datetime | None


class RegistrationResult(BaseModel):
    # Identical for duplicates, delivery failures, and successful submissions.
    message: str = "If eligible, verification instructions will be sent."


class ErrorResponse(BaseModel):
    error_code: str = "IDENTITY_REQUEST_FAILED"
    details: str = "Unable to complete the request."
    request_id: str
