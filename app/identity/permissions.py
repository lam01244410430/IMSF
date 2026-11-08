"""Explicit endpoint-group grants. Rank is a grant ceiling, never inheritance."""
from enum import StrEnum

from app.identity.domain import RoleCode


class PermissionCode(StrEnum):
    VIEW = "household.view"
    SETTINGS = "household.settings"
    MEMBERS = "household.members"
    ARCHIVE = "household.archive"
    TRANSFER = "household.transfer"
    AUDIT = "audit.view"
    FINANCE_DRAFT = "finance.draft"
    FINANCE_POST = "finance.post"
    FINANCE_REVERSE = "finance.reverse"
    INVENTORY_MANAGE = "inventory.manage"
    MOVEMENT_RECORD = "inventory.consumption_disposal"
    COOK = "recipes.cook_deduct"
    RECIPE_EDIT = "recipes.edit"


P = PermissionCode
# Each role is enumerated independently; new permissions are denied by default.
ROLE_PERMISSIONS = {
    RoleCode.OWNER: frozenset({P.VIEW, P.SETTINGS, P.MEMBERS, P.ARCHIVE, P.TRANSFER, P.AUDIT,
                             P.FINANCE_DRAFT, P.FINANCE_POST, P.FINANCE_REVERSE,
                             P.INVENTORY_MANAGE, P.MOVEMENT_RECORD, P.COOK, P.RECIPE_EDIT}),
    RoleCode.ADMIN: frozenset({P.VIEW, P.SETTINGS, P.MEMBERS, P.AUDIT}),
    RoleCode.FINANCE_MANAGER: frozenset({P.VIEW, P.FINANCE_DRAFT, P.FINANCE_POST,
                                      P.FINANCE_REVERSE, P.RECIPE_EDIT}),
    RoleCode.INVENTORY_MANAGER: frozenset({P.VIEW, P.INVENTORY_MANAGE, P.MOVEMENT_RECORD, P.COOK}),
    RoleCode.MEMBER: frozenset({P.VIEW, P.FINANCE_DRAFT, P.MOVEMENT_RECORD, P.RECIPE_EDIT}),
    RoleCode.VIEWER: frozenset({P.VIEW}),
}


def allows(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def can_grant(actor: str, target: str) -> bool:
    if target not in ROLE_PERMISSIONS:
        return False
    return actor == RoleCode.OWNER or (actor == RoleCode.ADMIN and target in {
        RoleCode.FINANCE_MANAGER, RoleCode.INVENTORY_MANAGER, RoleCode.MEMBER, RoleCode.VIEWER,
    })
