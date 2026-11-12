"""Scoped bounded lifecycle reads. No stock writer or operational producer."""
from sqlalchemy import select
from app.finance.infrastructure.repositories import record
from app.identity.infrastructure.models import Household
from app.inventory.infrastructure.models import InventoryLot, Product
from app.lifecycle.infrastructure.models import ExpirationAlert


class SqlAlchemyLifecycleRepository:
    def __init__(self, session):
        self.session = session

    async def lot_page(self, hid, limit, position, filters, local_date):
        lot = InventoryLot
        statement = select(lot, Product.archived_at, Household.archived_at).join(
            Product, (Product.household_id == lot.household_id) & (Product.id == lot.product_id)
        ).join(Household, Household.id == lot.household_id).where(lot.household_id == hid)
        if position is not None:
            statement = statement.where(lot.id > position)
        for name in ("product_id", "lot_id"):
            if filters.get(name) is not None:
                statement = statement.where((lot.id if name == "lot_id" else lot.product_id) == filters[name])
        # PROPOSAL OPEN-01: predicates match pure freshness(), before LIMIT.
        match filters.get("freshness"):
            case "UNKNOWN":
                statement = statement.where(lot.expires_on.is_(None))
            case "EXPIRED":
                statement = statement.where(lot.expires_on < local_date)
            case "WARNING":
                statement = statement.where(lot.expires_on >= local_date,
                                            lot.expires_on - local_date <= 3)
            case "FRESH":
                statement = statement.where(lot.expires_on - local_date > 3)
        rows = (await self.session.execute(statement.order_by(lot.id).limit(limit))).all()
        return [record(row) | {"product_archived_at": pa, "household_archived_at": ha}
                for row, pa, ha in rows]

    async def alert(self, hid, identifier):
        row = await self.session.scalar(select(ExpirationAlert).where(
            ExpirationAlert.household_id == hid, ExpirationAlert.id == identifier))
        return record(row) if row else None

    async def alert_page(self, hid, limit, position, filters):
        alert = ExpirationAlert
        statement = select(alert).where(alert.household_id == hid)
        if position is not None:
            statement = statement.where(alert.id > position)
        for key, value in filters.items():
            if value is None:
                continue
            if key == "local_date_from":
                statement = statement.where(alert.local_date >= value)
            elif key == "local_date_to":
                statement = statement.where(alert.local_date <= value)
            else:
                statement = statement.where(getattr(alert, "alert_kind" if key == "kind" else key) == value)
        return [record(row) for row in (await self.session.scalars(
            statement.order_by(alert.id).limit(limit))).all()]
