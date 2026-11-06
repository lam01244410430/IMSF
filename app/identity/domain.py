"""Identity values; application workflows are intentionally outside Step 1."""

from enum import StrEnum


class UserState(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class ChallengePurpose(StrEnum):
    VERIFY_EMAIL = "VERIFY_EMAIL"
    RESET_PASSWORD = "RESET_PASSWORD"


class RoleCode(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    FINANCE_MANAGER = "FINANCE_MANAGER"
    INVENTORY_MANAGER = "INVENTORY_MANAGER"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


def normalize_email(email: str) -> str:
    # MANAGER PROPOSAL (merge gate): trim + lowercase; globally unique email_key.
    key = email.strip().lower()
    if not key:
        raise ValueError("Email is required")
    return key


def validate_password(password: str) -> None:
    # MANAGER PROPOSAL (merge gate): 12-128 characters, Argon2id, no class rules.
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must contain 12-128 characters")


# USER DECISION 2026-11-06: in-app email reset stays. Manual recovery is only
# for lost-email access, outside the application; there is no in-app bypass.
