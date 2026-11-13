"""P05-OPEN-01/03/07 PROPOSALS: authorized reads with one explicit local date."""
import base64
import binascii
from datetime import datetime, timezone
import json
from app.inventory import authorization as policy
from app.inventory.domain import InventoryRequestError
from app.inventory.ports import InventoryRepository
from app.inventory.service import canonical
from app.lifecycle.domain import freshness, household_zone
from app.lifecycle.dto import LifecyclePage, ExpirationAlertPage, ExpirationAlertResponse
from app.lifecycle.ports import LifecycleRepository


def utc_now():
    return datetime.now(timezone.utc)


def invalid():
    return InventoryRequestError(422, "INVENTORY_INVALID_INPUT")


class LifecycleService:
    def __init__(self, session, repository: LifecycleRepository,
                 inventory: InventoryRepository, access, commands=None):
        self.session, self.repository, self.inventory, self.access = session, repository, inventory, access
        self.commands = commands

    async def _object(self, hid, resource, identifier):
        row = await self.inventory.get(resource, hid, identifier)
        if row is None:
            raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
        return row

    async def _filters(self, hid, filters):
        for key, resource in (("product_id", "products"), ("lot_id", "inventory-lots")):
            if filters.get(key) is not None:
                row = await self._object(hid, resource, filters[key])
                if key == "lot_id" and filters.get("product_id") is not None and row["product_id"] != filters["product_id"]:
                    raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")

    async def _cursor(self, hid, resource, cursor, scope, evaluation=None):
        if not cursor:
            return None
        try:
            if len(cursor) > 2048:
                raise ValueError()
            decoded = json.loads(base64.b64decode(cursor.encode(), altchars=b"-_", validate=True))
            previous = decoded["scope"]
            position = decoded["position"]
            if (not isinstance(previous, list) or len(previous) != 3
                or type(previous[0]) is not int or previous[1] != resource
                or type(position) is not int or not 0 < position <= 9223372036854775807):
                raise ValueError()
            if previous[0] != hid:
                raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
            if previous != scope:
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error):
            raise invalid() from None
        # A forged scope cannot make a foreign cursor ID visible.
        if resource == "lifecycle":
            await self._object(hid, "inventory-lots", position)
        elif await self.repository.alert(hid, position) is None:
            raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
        if evaluation is not None and decoded.get("evaluation") != evaluation:
            raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
        return position

    @staticmethod
    def _next(rows, limit, scope, evaluation=None):
        if len(rows) <= limit:
            return None
        values = {"scope": scope, "position": rows[limit - 1]["id"]}
        if evaluation is not None:
            values["evaluation"] = evaluation
        return base64.urlsafe_b64encode(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).decode()

    async def lifecycle(self, actor, hid, limit=50, cursor=None, **filters):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            await self._filters(hid, filters)
            # Scope checks precede timezone validation, including cursor positions.
            scope = canonical([hid, "lifecycle", filters])
            position = await self._cursor(hid, "lifecycle", cursor, scope)
            name = await self.inventory.household_timezone(hid)
            local_date = utc_now().astimezone(household_zone(name)).date()
            evaluation = [local_date.isoformat(), name]
            if cursor:
                # Already structurally/scope validated above; never sample the clock again.
                decoded = json.loads(base64.urlsafe_b64decode(cursor))
                if decoded.get("evaluation") != evaluation:
                    raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
            rows = await self.repository.lot_page(hid, limit + 1, position, filters, local_date)
            items = []
            for row in rows[:limit]:
                kind, days = freshness(row["expires_on"], local_date)
                items.append(row | {"lot_id": row["id"], "lot_archived_at": row["archived_at"],
                    "activity_state": "ACTIVE" if row["remaining_quantity"] > 0 else "TERMINAL",
                    "freshness": kind, "days_left": days, "local_date": local_date, "timezone": name})
            return LifecyclePage.model_validate({"items": items, "next_cursor": self._next(rows, limit, scope, evaluation),
                "local_date": local_date, "timezone": name}).model_dump(mode="json")

    async def alerts(self, actor, hid, limit=50, cursor=None, **filters):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            await self._filters(hid, filters)
            start, end = filters.get("local_date_from"), filters.get("local_date_to")
            if start is not None and end is not None and start > end:
                raise invalid()
            scope = canonical([hid, "alerts", filters])
            position = await self._cursor(hid, "alerts", cursor, scope)
            rows = await self.repository.alert_page(hid, limit + 1, position, filters)
            return ExpirationAlertPage.model_validate({"items": rows[:limit], "next_cursor": self._next(rows, limit, scope)}).model_dump(mode="json")

    async def alert(self, actor, hid, identifier):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            row = await self.repository.alert(hid, identifier)
            if row is None:
                raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
            return ExpirationAlertResponse.model_validate(row).model_dump(mode="json")


    async def enqueue(self, actor, hid, body, key):
        """PROPOSAL OPEN-07: reuse inventory's complete command/replay protocol."""
        from app.inventory.service import InventoryService
        from app.lifecycle.jobs import evaluation, summary
        from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
        repository = SqlAlchemyExpiryJobRepository(self.session)
        async def effect(context):
            # InventoryService._command has authorized current MANAGE access and
            # locked the household before reserving the transport key.
            day, zone = await evaluation(repository, hid)
            # PROPOSAL: frozen revision 4 permits saved status 200/201/204 only.
            # Encode this endpoint's success as 200 internally; both first and
            # replayed responses map to HTTP 202 below, preserving the exact body.
            # A literal stored 202 would require a separately approved migration.
            return 200, summary(await repository.enqueue(hid, day, zone))
        _, result = await InventoryService(self.session, self.inventory, self.access, self.commands)._command(
            actor, hid, f"POST /households/{hid}/inventory/expiry-runs", key,
            body.model_dump(mode="python"), effect)
        return 202, result

    async def expiry_run(self, actor, hid, identifier):
        from app.lifecycle.jobs import summary
        from app.lifecycle.infrastructure.repositories import SqlAlchemyExpiryJobRepository
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            row = await SqlAlchemyExpiryJobRepository(self.session).job(hid, identifier)
            if row is None:
                raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
            return summary(row)
