"""P04-OPEN-07/08/13 proposals: transaction-owned Step 2 commands only."""

import base64
from datetime import date, datetime, timezone
from decimal import localcontext
import hashlib
import json
import re
from uuid import uuid4
from sqlalchemy.exc import DBAPIError
from app.inventory import authorization as policy
from app.inventory.domain import InventoryRequestError
from app.inventory.dto import (
    ProductCategoryResponse,
    ProductResponse,
    LotResponse,
    MovementResponse,
    UnitResponse,
    ConversionResponse,
)
from app.inventory.units import convert
from app.inventory.ports import InventoryRepository, CommandRecords
from app.finance.ledger_service import canonical as finance_canonical

RESPONSES = {
    "product-categories": ProductCategoryResponse,
    "products": ProductResponse,
    "inventory-lots": LotResponse,
    "inventory-movements": MovementResponse,
    "measurement-units": UnitResponse,
    "unit-conversions": ConversionResponse,
}


def canonical(value):
    if isinstance(value, datetime):
        return finance_canonical(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    return finance_canonical(value)


class InventoryService:
    def __init__(
        self, session, repository: InventoryRepository, access, commands: CommandRecords
    ):
        self.session, self.repository, self.access, self.commands = (
            session,
            repository,
            access,
            commands,
        )

    async def _object(self, resource, hid, identifier, *, lock=False):
        row = await self.repository.get(resource, hid, identifier, lock=lock)
        if row is None:
            raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
        return row

    async def _response(self, resource, hid, row):
        if resource == "inventory-lots":
            row = row | {
                "receipt_movement_id": await self.repository.receipt_id(hid, row["id"])
            }
        return RESPONSES[resource].model_validate(row).model_dump(mode="json")

    async def _audit(self, hid, context, resource, row, action, reason=None):
        await self.commands.audit(
            {
                "household_id": hid,
                "actor_member_id": context.member_id,
                "request_id": str(uuid4()),
                "action": "INVENTORY_" + action,
                "target_type": resource,
                "target_id": str(row["id"]),
                "details": {"reason": reason} if reason else {},
            }
        )

    async def _command(self, actor, hid, operation, key, values, effect):
        if not isinstance(key, str) or not re.fullmatch(r"[\x21-\x7e]{1,128}", key):
            raise InventoryRequestError(422, "INVENTORY_INVALID_IDEMPOTENCY_KEY")
        operation = f"{operation}:v1"
        digest = hashlib.sha256(
            json.dumps(
                canonical({"path": operation, "household_id": hid, "body": values}),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        ).hexdigest()
        for attempt in range(3):
            try:
                async with self.session.begin():
                    context = await self.access.resolve(
                        actor, hid, policy.MANAGE, write=True
                    )
                    reservation, saved = await self.commands.reserve(
                        {
                            "household_id": hid,
                            "actor_member_id": context.member_id,
                            "operation": operation,
                            "request_key": key,
                            "request_hash": digest,
                        }
                    )
                    if saved:
                        if saved["request_hash"] != digest:
                            raise InventoryRequestError(
                                409, "INVENTORY_IDEMPOTENCY_CONFLICT"
                            )
                        return saved["response_status"], saved["response_body"]
                    status, result = await effect(context)
                    await self.commands.complete(reservation, status, result)
                    return status, result
            except ValueError:
                raise InventoryRequestError(422, "INVENTORY_INVALID_INPUT") from None
            except DBAPIError as exc:
                state = getattr(exc.orig, "sqlstate", None)
                transient = (
                    state in {"40001", "40P01", "57P01"}
                    or bool(state and state.startswith("08"))
                    or exc.connection_invalidated
                )
                if transient and attempt < 2:
                    continue
                if transient:
                    raise InventoryRequestError(
                        409, "INVENTORY_RETRY_EXHAUSTED"
                    ) from None
                if state in {"23505", "55000"}:
                    raise InventoryRequestError(
                        409, "INVENTORY_STATE_CONFLICT"
                    ) from None
                if state == "23503":
                    raise InventoryRequestError(404, "INVENTORY_NOT_FOUND") from None
                if state == "23514":
                    raise InventoryRequestError(
                        422, "INVENTORY_INVALID_INPUT"
                    ) from None
                raise

    async def get(self, actor, hid, resource, identifier):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            return await self._response(
                resource, hid, await self._object(resource, hid, identifier)
            )

    async def page(self, actor, hid, resource, limit=50, cursor=None, **filters):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            for name, target in [
                ("product_id", "products"),
                ("category_id", "product-categories"),
                ("lot_id", "inventory-lots"),
            ]:
                if filters.get(name) is not None:
                    await self._object(target, hid, filters[name])
            scope = canonical([hid, resource, filters])
            position = None
            if cursor:
                try:
                    if len(cursor) > 2048:
                        raise ValueError()
                    decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                    position = decoded["position"]
                    if (
                        decoded["scope"] != scope
                        or not isinstance(position, list)
                        or len(position) != (2 if resource == "unit-conversions" else 1)
                    ):
                        raise ValueError()
                    if any(
                        type(v) is not int or not 0 < v <= 9223372036854775807
                        for v in position
                    ):
                        raise ValueError()
                except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
                    raise InventoryRequestError(
                        422, "INVENTORY_INVALID_INPUT"
                    ) from None
            rows = await self.repository.page(
                resource, hid, limit + 1, position, filters
            )
            next_cursor = None
            if len(rows) > limit:
                rows = rows[:limit]
                last = rows[-1]
                position = (
                    [last["from_unit_id"], last["to_unit_id"]]
                    if resource == "unit-conversions"
                    else [last["id"]]
                )
                next_cursor = base64.urlsafe_b64encode(
                    json.dumps(
                        {"scope": scope, "position": position},
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).decode()
            return {
                "items": [await self._response(resource, hid, row) for row in rows],
                "next_cursor": next_cursor,
            }

    async def _validate_product(self, hid, values):
        if (
            "base_unit_id" in values
            and await self.repository.unit(values["base_unit_id"]) is None
        ):
            raise InventoryRequestError(422, "INVENTORY_INVALID_INPUT")
        if values.get("category_id") is not None:
            category = await self._object(
                "product-categories", hid, values["category_id"], lock=True
            )
            if category["archived_at"] is not None:
                raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")

    async def create_reference(self, actor, hid, resource, body, key):
        values = body.model_dump()

        async def effect(context):
            if resource == "products":
                await self._validate_product(hid, values)
            row = await self.repository.create(resource, values | {"household_id": hid})
            await self._audit(hid, context, resource, row, "CREATED")
            return 201, await self._response(resource, hid, row)

        return await self._command(
            actor, hid, f"POST /households/{hid}/{resource}", key, values, effect
        )

    async def _lock_eligibility(self, hid, resource, identifier):
        row = await self._object(resource, hid, identifier)
        pid = row["product_id"] if resource == "inventory-lots" else identifier
        products = await self.repository.lock_products(hid, [pid])
        if not products:
            raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
        lots = await self.repository.lock_lots(hid, [pid])
        return (
            next(lot for lot in lots if lot["id"] == identifier)
            if resource == "inventory-lots"
            else products[0]
        )

    async def patch(self, actor, hid, resource, identifier, body, key):
        values = body.model_dump(exclude_unset=True)

        async def effect(context):
            reason = values.get("reason")
            updates = {k: v for k, v in values.items() if k != "reason"}
            if resource == "products":
                await self._validate_product(hid, updates)
                row = await self._lock_eligibility(hid, resource, identifier)
                if (
                    "base_unit_id" in updates
                    and updates["base_unit_id"] != row["base_unit_id"]
                    and await self.repository.has_history(hid, identifier)
                ):
                    raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
            elif resource == "inventory-lots":
                await self._lock_eligibility(hid, resource, identifier)
            else:
                await self._object(resource, hid, identifier, lock=True)
            row = await self.repository.update(resource, hid, identifier, updates)
            await self._audit(hid, context, resource, row, "METADATA_UPDATED", reason)
            return 200, await self._response(resource, hid, row)

        return await self._command(
            actor,
            hid,
            f"PATCH /households/{hid}/{resource}/{identifier}",
            key,
            values,
            effect,
        )

    async def archive(self, actor, hid, resource, identifier, body, key):
        values = body.model_dump()

        async def effect(context):
            row = (
                await self._lock_eligibility(hid, resource, identifier)
                if resource in {"products", "inventory-lots"}
                else await self._object(resource, hid, identifier, lock=True)
            )
            row = await self.repository.update(
                resource,
                hid,
                identifier,
                {"archived_at": row["archived_at"] or datetime.now(timezone.utc)},
            )
            await self._audit(
                hid, context, resource, row, "ARCHIVED", values.get("reason")
            )
            return 200, await self._response(resource, hid, row)

        return await self._command(
            actor,
            hid,
            f"POST /households/{hid}/{resource}/{identifier}/archive",
            key,
            values,
            effect,
        )

    async def receive(self, actor, hid, body, key):
        values = body.model_dump()

        async def effect(context):
            return 201, await self.receive_in_uow(context, hid, values)

        return await self._command(
            actor, hid, f"POST /households/{hid}/inventory-lots", key, values, effect
        )

    async def receive_in_uow(self, context, hid, values):
        """The single receipt writer. Caller owns authorization, key and transaction.

        P04-OPEN-07 proposal. Future checkout reuses this seam, never a nested
        public command. No other stock command is enabled in Step 2.
        """
        purchase = None
        if values["purchase_item_id"] is not None:
            purchase = await self.repository.lock_purchase(
                hid, values["purchase_item_id"]
            )
            if purchase is None:
                raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
            if purchase["product_id"] != values["product_id"]:
                raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
            if (
                purchase["kind"] != "EXPENSE"
                or purchase["status"] != "POSTED"
                or purchase["is_reversed"]
            ):
                raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
            if (
                values["cost_currency"] is not None
                and values["cost_currency"] != purchase["currency_code"]
            ):
                raise InventoryRequestError(422, "INVENTORY_INVALID_INPUT")
        products = await self.repository.lock_products(hid, [values["product_id"]])
        if not products:
            raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
        product = products[0]
        await self.repository.lock_lots(hid, [product["id"]])
        if product["archived_at"] is not None:
            raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
        try:
            amount = convert(
                values["quantity"],
                values["unit_id"],
                product["base_unit_id"],
                await self.repository.factor(
                    values["unit_id"], product["base_unit_id"]
                ),
            )
        except ValueError:
            raise InventoryRequestError(
                422, "INVENTORY_UNIT_CONVERSION_INVALID"
            ) from None
        if purchase:
            with localcontext() as ctx:
                ctx.prec = 80
                if (
                    await self.repository.split_received(
                        hid, values["purchase_item_id"]
                    )
                    + amount
                    > purchase["base_quantity"]
                ):
                    raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
        lot = await self.repository.create(
            "inventory-lots",
            {
                k: values[k]
                for k in (
                    "product_id",
                    "source_kind",
                    "purchase_item_id",
                    "received_at",
                    "expires_on",
                    "cost_currency",
                    "unit_cost",
                )
            }
            | {
                "household_id": hid,
                "received_quantity": amount,
                "remaining_quantity": amount,
            },
        )
        await self.repository.create(
            "inventory-movements",
            {
                "household_id": hid,
                "lot_id": lot["id"],
                "kind": "RECEIPT",
                "quantity_delta": amount,
                "occurred_at": values["received_at"],
                "actor_member_id": context.member_id,
                "transaction_id": purchase["original_transaction_id"]
                if purchase
                else None,
                "reason": values["reason"],
            },
        )
        await self._audit(
            hid, context, "inventory-lots", lot, "RECEIVED", values["reason"]
        )
        return await self._response("inventory-lots", hid, lot)
