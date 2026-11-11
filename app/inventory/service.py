"""P04-OPEN-07/08/13 proposals: transaction-owned Step 2/3 commands."""

import base64
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import re
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.inventory import fefo
from sqlalchemy.exc import DBAPIError
from app.inventory import authorization as policy
from app.inventory.domain import InventoryRequestError, terminal_state
from app.inventory.dto import (
    ProductCategoryResponse,
    ProductResponse,
    LotResponse,
    MovementResponse,
    UnitResponse,
    ConversionResponse,
    AdjustmentResponse,
    ConsumptionResponse,
    DisposalResponse,
    StockCommandResponse,
)
from app.inventory.units import convert, quantity
from app.inventory.ports import InventoryRepository, CommandRecords
from app.finance.ledger_service import canonical as finance_canonical

RESPONSES = {
    "product-categories": ProductCategoryResponse,
    "products": ProductResponse,
    "inventory-lots": LotResponse,
    "inventory-movements": MovementResponse,
    "measurement-units": UnitResponse,
    "unit-conversions": ConversionResponse,
    "inventory-adjustments": AdjustmentResponse,
    "consumption": ConsumptionResponse,
    "disposals": DisposalResponse,
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

    async def _command(
        self, actor, hid, operation, key, values, effect, *, permission=policy.MANAGE, additional_permissions=()
    ):
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
                        actor, hid, permission, write=True
                    )
                    # P04-OPEN-07/13 PROPOSAL: intersection checked before replay.
                    for required in additional_permissions:
                        await self.access.resolve(actor, hid, required, write=True)
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
        """Receipt command using the single movement writer and Step 2 locks.

        Caller owns authorization, key and transaction. P04-OPEN-07 PROPOSAL:
        future checkout reuses this seam, never a nested public command.
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
        await self._write_movement_in_uow(
            context, hid, lot, "RECEIPT", amount,
            occurred_at=values["received_at"], reason=values["reason"],
            transaction_id=purchase["original_transaction_id"] if purchase else None,
        )
        await self._audit(
            hid, context, "inventory-lots", lot, "RECEIVED", values["reason"]
        )
        return await self._response("inventory-lots", hid, lot)


    async def deduct_in_uow(self, context, hid, values):
        """P04-OPEN-02/05/07/08/12 PROPOSAL: reusable stock-only FEFO seam.

        Caller owns authorization, reservation and transaction. Resolve the local
        date once per attempt, then collect ALL allocations before any write.
        """
        pids = sorted({line["product_id"] for line in values["items"]})
        # Retain the original/account/item prefix required by purchase triggers.
        purchases = await self.repository.lock_purchases(
            hid, await self.repository.stock_purchase_ids(hid, pids)
        )
        products = await self.repository.lock_products(hid, pids)
        if len(products) != len(pids):
            raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
        products = {p["id"]: p for p in products}
        name = await self.repository.household_timezone(hid)
        try:
            if not isinstance(name, str) or not name:
                raise ValueError()
            zone = ZoneInfo(name)
        except (ValueError, ZoneInfoNotFoundError):
            raise InventoryRequestError(422, "INVENTORY_TIMEZONE_REQUIRED") from None
        local_date = datetime.now(timezone.utc).astimezone(zone).date()
        amounts = {}
        with localcontext() as ctx:
            ctx.prec = 80
            for line in values["items"]:
                pid = line["product_id"]
                amounts[pid] = amounts.get(pid, Decimal(0)) + await self._base_quantity(line, products[pid])
        lots = await self.repository.lock_fefo_lots(hid, pids, local_date)
        for lot in lots:
            iid = lot["purchase_item_id"]
            if iid is not None:
                purchase = purchases.get(iid)
                # If a new source appeared after discovery, roll back rather
                # than acquiring the purchase prefix after product/lot locks.
                if purchase is None or purchase["product_id"] != lot["product_id"]:
                    raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
                if (purchase["kind"] != "EXPENSE" or purchase["status"] != "POSTED"
                        or purchase["is_reversed"]):
                    raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
        plans = fefo.allocate(hid, amounts, products, lots, local_date=local_date)
        result = {"movement_ids": [], "consumption_record_ids": [], "disposal_record_ids": [],
                  "adjustment_ids": [], "allocations": [], "refund_inventory_link_ids": []}
        for lot, amount in plans:
            purchase = purchases.get(lot["purchase_item_id"])
            movement, detail, updated = await self._write_movement_in_uow(
                context, hid, lot, "CONSUME", -amount, reason=values.get("reason"),
                reason_code=values["reason_code"],
                transaction_id=purchase["original_transaction_id"] if purchase else None,
            )
            result["movement_ids"].append(movement["id"])
            result["consumption_record_ids"].append(detail["id"])
            result["allocations"].append({"product_id": lot["product_id"], "lot_id": lot["id"],
                "base_quantity": amount, "remaining_quantity": updated["remaining_quantity"]})
            await self._audit(hid, context, "inventory-movements", movement, "CONSUME", values.get("reason"))
        return StockCommandResponse.model_validate(result).model_dump(mode="json")

    async def _locked_stock(self, hid, lot_ids):
        """P04-OPEN-07 PROPOSAL: reuse Step 2 locks, refresh after waiting.

        Movement SQL guards also lock purchases, even for consumption/disposal;
        acquire their entire prefix before products to preserve the protocol.
        """
        discovered = [await self._object("inventory-lots", hid, lid)
                      for lid in sorted(set(lot_ids))]
        purchases = await self.repository.lock_purchases(hid, [
            lot["purchase_item_id"] for lot in discovered
            if lot["purchase_item_id"] is not None
        ])
        for lot in discovered:
            iid = lot["purchase_item_id"]
            if iid is not None:
                purchase = purchases.get(iid)
                if purchase is None or purchase["product_id"] != lot["product_id"]:
                    raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
                if (purchase["kind"] != "EXPENSE" or purchase["status"] != "POSTED"
                        or purchase["is_reversed"]):
                    raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
        pids = sorted({lot["product_id"] for lot in discovered})
        products = await self.repository.lock_products(hid, pids)
        lots = await self.repository.lock_lots(hid, pids)
        requested = set(lot_ids)
        locked = [lot for lot in lots if lot["id"] in requested]
        if len(locked) != len(requested) or len(products) != len(pids):
            raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
        return {p["id"]: p for p in products}, locked, purchases

    async def _base_quantity(self, values, product, *, counted=False):
        value = values["counted_quantity" if counted else "quantity"]
        source, target = values["unit_id"], product["base_unit_id"]
        factor = await self.repository.factor(source, target)
        try:
            # Validate units even for a zero count; convert() requires positive.
            converted = convert(Decimal(1) if value == 0 else value,
                                source, target, factor)
            return Decimal(0) if value == 0 else converted
        except ValueError:
            raise InventoryRequestError(422, "INVENTORY_UNIT_CONVERSION_INVALID") from None

    async def _write_movement_in_uow(
        self, context, hid, lot, kind, delta, *, occurred_at=None, reason=None,
        transaction_id=None, reason_code=None, counted_quantity=None,
        correction_of_movement_id=None,
    ):
        """Single stock writer, extended from Step 2 receipts.

        P04-OPEN-03/04/05/07 PROPOSAL: append event + exactly aligned detail,
        then projection/terminal in caller's UoW under original/product/lot locks.
        Receipt projection is initialized by lot creation, exactly once.
        """
        movement = await self.repository.create("inventory-movements", {
            "household_id": hid, "lot_id": lot["id"], "kind": kind,
            "quantity_delta": delta,
            "occurred_at": occurred_at or datetime.now(timezone.utc),
            "actor_member_id": context.member_id, "transaction_id": transaction_id,
            "reason": reason, "correction_of_movement_id": correction_of_movement_id,
        })
        detail = None
        detail_resource = {"CONSUME": "consumption", "DISPOSE": "disposals",
                           "ADJUST_IN": "inventory-adjustments",
                           "ADJUST_OUT": "inventory-adjustments"}.get(kind)
        if detail_resource:
            fields = ({"counted_quantity": counted_quantity, "reason": reason}
                      if detail_resource == "inventory-adjustments"
                      else {"reason_code": reason_code})
            detail = await self.repository.create(detail_resource, fields | {
                "household_id": hid, "movement_id": movement["id"],
            })
        if kind != "RECEIPT":
            with localcontext() as ctx:
                ctx.prec = 80
                remaining = lot["remaining_quantity"] + delta
            lot = await self.repository.update("inventory-lots", hid, lot["id"], {
                "remaining_quantity": remaining,
                "terminal_state": terminal_state(
                    remaining, await self.repository.negative_kinds(hid, lot["id"])
                ),
            })
        return movement, detail, lot

    async def stock_command(self, actor, hid, resource, body, key, *, lot_id=None):
        """P04-OPEN-03/04/05/08/10/11/13 PROPOSAL explicit-lot commands.

        RETURN is stock-only and appends an unresolved association. It never
        creates payments/ledger entries or resolves existing refund links.
        """
        values = body.model_dump()
        path = (f"inventory-lots/{lot_id}/returns" if resource == "returns" else resource)
        permission = policy.RECORD if resource in {"consumption", "disposals"} else policy.MANAGE

        async def effect(context):
            lines = (values["allocations"] if resource in {"consumption", "disposals"}
                     else [values | {"lot_id": lot_id if resource == "returns" else values["lot_id"]}])
            products, lots, purchases = await self._locked_stock(hid, [line["lot_id"] for line in lines])
            by_id = {lot["id"]: lot for lot in lots}
            amounts = {}
            # Exact base conversion then normalize repeated lot demands BEFORE
            # availability validation. One event/detail per normalized lot.
            with localcontext() as ctx:
                ctx.prec = 80
                for line in lines:
                    lot = by_id[line["lot_id"]]
                    amount = await self._base_quantity(
                        line, products[lot["product_id"]],
                        counted=resource == "inventory-adjustments",
                    )
                    amounts[lot["id"]] = amounts.get(lot["id"], Decimal(0)) + amount
            plans = []
            for lot in lots:  # Same locked product/FEFO order for writes.
                product = products[lot["product_id"]]
                archived = lot["archived_at"] is not None or product["archived_at"] is not None
                if archived and resource == "consumption":
                    raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
                if archived and not values.get("reason"):
                    raise InventoryRequestError(422, "INVENTORY_INVALID_INPUT")
                amount = amounts[lot["id"]]
                if resource == "inventory-adjustments":
                    if amount > lot["received_quantity"] or amount == lot["remaining_quantity"]:
                        raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
                    correction = values["correction_of_movement_id"]
                    if correction is not None:
                        old = await self._object("inventory-movements", hid, correction)
                        if old["lot_id"] != lot["id"]:
                            raise InventoryRequestError(404, "INVENTORY_NOT_FOUND")
                    with localcontext() as ctx:
                        ctx.prec = 80
                        delta = amount - lot["remaining_quantity"]
                    kind = "ADJUST_IN" if delta > 0 else "ADJUST_OUT"
                else:
                    # Aggregate bounds and availability checked once per lot.
                    quantity(amount)
                    if amount > lot["remaining_quantity"]:
                        raise InventoryRequestError(409, "INVENTORY_STOCK_SHORTAGE")
                    if resource == "returns" and lot["purchase_item_id"] is None:
                        raise InventoryRequestError(409, "INVENTORY_STATE_CONFLICT")
                    delta = -amount
                    kind = {"consumption": "CONSUME", "disposals": "DISPOSE", "returns": "RETURN"}[resource]
                plans.append((lot, kind, delta))
            result = {"movement_ids": [], "consumption_record_ids": [],
                      "disposal_record_ids": [], "adjustment_ids": [],
                      "allocations": [], "refund_inventory_link_ids": []}
            for lot, kind, delta in plans:
                purchase = purchases.get(lot["purchase_item_id"])
                movement, detail, updated = await self._write_movement_in_uow(
                    context, hid, lot, kind, delta, reason=values.get("reason"),
                    transaction_id=purchase["original_transaction_id"] if purchase else None,
                    reason_code=values.get("reason_code"),
                    counted_quantity=amounts[lot["id"]] if resource == "inventory-adjustments" else None,
                    correction_of_movement_id=values.get("correction_of_movement_id"),
                )
                result["movement_ids"].append(movement["id"])
                if detail:
                    result[{"CONSUME": "consumption_record_ids", "DISPOSE": "disposal_record_ids",
                            "ADJUST_IN": "adjustment_ids", "ADJUST_OUT": "adjustment_ids"}[kind]].append(detail["id"])
                if kind == "RETURN":
                    link = await self.repository.create_refund_link({
                        "household_id": hid,
                        "original_transaction_id": purchase["original_transaction_id"],
                        "purchase_item_id": lot["purchase_item_id"], "lot_id": lot["id"],
                        "return_movement_id": movement["id"],
                        "created_by_member_id": context.member_id, "reason": values["reason"],
                    })
                    result["refund_inventory_link_ids"].append(link["id"])
                result["allocations"].append({
                    "product_id": lot["product_id"], "lot_id": lot["id"],
                    "base_quantity": abs(delta), "remaining_quantity": updated["remaining_quantity"],
                })
                await self._audit(hid, context, "inventory-movements", movement,
                                  kind, values.get("reason"))
            if resource == "inventory-adjustments":
                return 201, await self._response(resource, hid, detail)
            return 201, StockCommandResponse.model_validate(result).model_dump(mode="json")

        return await self._command(actor, hid, f"POST /households/{hid}/{path}",
                                   key, values, effect, permission=permission)
