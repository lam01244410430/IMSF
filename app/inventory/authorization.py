"""P04-OPEN-13 route proposals reuse fixed explicit identity grants."""

from app.identity.permissions import PermissionCode
from app.finance.domain import FinanceRequestError
from app.inventory.domain import InventoryRequestError

READ = PermissionCode.VIEW
MANAGE = PermissionCode.INVENTORY_MANAGE


class InventoryHouseholdAccess:
    """Reuse the identity-compatible locked adapter; map only inventory errors."""

    def __init__(self, access):
        self.access = access

    async def resolve(self, *args, **kwargs):
        try:
            return await self.access.resolve(*args, **kwargs)
        except FinanceRequestError as exc:
            raise InventoryRequestError(
                exc.status_code, exc.code.replace("FINANCE_", "INVENTORY_", 1)
            ) from None
