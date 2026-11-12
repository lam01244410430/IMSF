"""P05-OPEN-01 PROPOSAL: calendar freshness is independent of terminal history."""
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.inventory.domain import InventoryRequestError


def household_zone(name: object) -> ZoneInfo:
    try:
        if not isinstance(name, str) or not name:
            raise ValueError()
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        raise InventoryRequestError(422, "INVENTORY_TIMEZONE_REQUIRED") from None


def freshness(expires_on: date | None, local_date: date) -> tuple[str, int | None]:
    """PROPOSAL: three-day WARNING; undated lots have UNKNOWN freshness."""
    if expires_on is None:
        return "UNKNOWN", None
    days = (expires_on - local_date).days
    return ("FRESH" if days > 3 else "WARNING" if days >= 0 else "EXPIRED"), days


def eligible_for_alert(lot: dict, *, product_archived_at, household_archived_at) -> bool:
    """PROPOSAL eligibility contract only; no alert producer exists in Step 2."""
    return (lot["remaining_quantity"] > 0 and lot["terminal_state"] is None
            and lot["expires_on"] is not None and lot["archived_at"] is None
            and product_archived_at is None and household_archived_at is None)
