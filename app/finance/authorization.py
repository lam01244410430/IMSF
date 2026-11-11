"""Explicit endpoint mapping; existing identity grants remain authoritative."""
from app.finance.domain import FinanceRequestError, HouseholdContext
from app.identity.permissions import PermissionCode

# OPEN-10 PROPOSAL: administration uses finance.post, reads household.view.
READ = PermissionCode.VIEW
ADMINISTER = PermissionCode.FINANCE_POST
DRAFT = PermissionCode.FINANCE_DRAFT


def require_draft_editor(context: HouseholdContext, transaction: dict, *, check_status: bool = True) -> None:
    # OPEN-06 PROPOSAL: MEMBER edits only own retained DRAFTs. Rank is not a grant.
    if context.role == "MEMBER" and context.member_id != transaction["created_by_member_id"]:
        raise FinanceRequestError(403, "FINANCE_FORBIDDEN")
    if check_status and transaction["status"] != "DRAFT":
        raise FinanceRequestError(409, "FINANCE_DRAFT_REQUIRED")
