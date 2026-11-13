"""Scoped lifecycle and expiry-job persistence; no stock writer."""
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


# PROPOSAL OPEN-04/05/08: coordination and alert writes only; caller owns UoW.
from datetime import timedelta
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from app.identity.infrastructure.models import HouseholdSettings
from app.lifecycle.infrastructure.models import ScheduledJob


class SqlAlchemyExpiryJobRepository:
    def __init__(self, session):
        self.session = session

    async def now(self):
        return await self.session.scalar(sa.select(sa.func.clock_timestamp()))

    async def active_households(self, after_id, limit):
        return list((await self.session.scalars(sa.select(Household.id).where(
            Household.id > after_id, Household.archived_at.is_(None)
        ).order_by(Household.id).limit(limit))).all())

    async def lock_household(self, hid):
        # Reuse inventory's household FOR UPDATE serialization prefix (its access
        # adapter locks user -> household -> member -> session). System execution
        # has no user/member to lock or impersonate. No job lock is held yet.
        row = (await self.session.execute(sa.select(Household.__table__).where(
            Household.id == hid).with_for_update())).mappings().one_or_none()
        return dict(row) if row else None

    async def timezone(self, hid):
        values = await self.session.scalar(sa.select(HouseholdSettings.values).where(
            HouseholdSettings.household_id == hid))
        return values.get("timezone") if isinstance(values, dict) else None

    async def valid_timezone(self, name):
        return await self.session.scalar(sa.select(sa.func.public.inventory_expiry_timezone_valid(name)))

    async def enqueue(self, hid, local_date, timezone):
        table = ScheduledJob.__table__
        key = f"inventory-expiry:v1:{local_date.isoformat()}"
        await self.session.execute(insert(table).values(household_id=hid, job_key=key,
            kind="INVENTORY_EXPIRY", run_after=sa.func.clock_timestamp(),
            payload={"schema_version": 1, "local_date": local_date.isoformat(), "timezone": timezone}
        ).on_conflict_do_nothing(index_elements=["household_id", "job_key"]))
        return dict((await self.session.execute(sa.select(table).where(
            table.c.household_id == hid, table.c.job_key == key))).mappings().one())

    async def job(self, hid, identifier, *, lock=False):
        table = ScheduledJob.__table__
        statement = sa.select(table).where(table.c.household_id == hid,
            table.c.id == identifier, table.c.kind == "INVENTORY_EXPIRY")
        row = (await self.session.execute(statement.with_for_update() if lock else statement)).mappings().one_or_none()
        return dict(row) if row else None

    async def claim_due(self, job_id):
        table = ScheduledJob.__table__
        c = table.c
        statement = sa.select(table).where(c.kind == "INVENTORY_EXPIRY", sa.or_(
            sa.and_(c.state == "READY", c.run_after <= sa.func.clock_timestamp()),
            sa.and_(c.state == "RUNNING", c.lease_until <= sa.func.clock_timestamp())))
        if job_id is not None:
            statement = statement.where(c.id == job_id)
        row = (await self.session.execute(statement.order_by(c.run_after, c.id).limit(1)
            .with_for_update(skip_locked=True))).mappings().one_or_none()
        return dict(row) if row else None

    async def update_claim(self, row, token):
        table = ScheduledJob.__table__
        return dict((await self.session.execute(sa.update(table).where(
            table.c.household_id == row["household_id"], table.c.id == row["id"]
        ).values(state="RUNNING", attempt_count=row["attempt_count"] + 1,
            lease_token=token, lease_until=sa.func.clock_timestamp() + timedelta(seconds=60),
            error_code=None).returning(*table.c))).mappings().one())

    async def abandon_exhausted(self, row):
        # Expired third claim (process death) has no live owner. Job row is locked
        # by claim_due; no fourth claim or source/alert effect is permitted.
        table = ScheduledJob.__table__
        await self.session.execute(sa.update(table).where(table.c.id == row["id"],
            table.c.household_id == row["household_id"]).values(state="FAILED",
            completed_at=sa.func.clock_timestamp(), lease_token=None, lease_until=None,
            error_code="INVENTORY_RETRY_EXHAUSTED"))

    async def high_water(self, hid):
        return await self.session.scalar(sa.select(sa.func.coalesce(sa.func.max(InventoryLot.id), 0))
            .where(InventoryLot.household_id == hid))

    async def source_page(self, hid, last, high, limit):
        # Committed observation per batch under the household lock. No stock
        # SKIP LOCKED and no lot projection writes. Scan every bounded source ID,
        # applying alert eligibility in the application layer before inserts.
        lot = InventoryLot
        rows = (await self.session.execute(sa.select(lot, Product.archived_at).join(
            Product, (Product.household_id == lot.household_id) & (Product.id == lot.product_id)
        ).where(lot.household_id == hid, lot.id > last, lot.id <= high)
            .order_by(lot.id).limit(limit))).all()
        return [record(row) | {"product_archived_at": archived} for row, archived in rows]

    async def insert_alert(self, values):
        identifier = await self.session.scalar(insert(ExpirationAlert).values(**values)
            .on_conflict_do_nothing(index_elements=["household_id", "lot_id", "alert_kind", "local_date"])
            .returning(ExpirationAlert.id))
        return int(identifier is not None)

    async def fenced_update(self, hid, identifier, token, **values):
        table = ScheduledJob.__table__
        row = (await self.session.execute(sa.update(table).where(
            table.c.household_id == hid, table.c.id == identifier,
            table.c.state == "RUNNING", table.c.lease_token == token,
            table.c.lease_until > sa.func.clock_timestamp()
        ).values(**values).returning(*table.c))).mappings().one_or_none()
        return dict(row) if row else None
