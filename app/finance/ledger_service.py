"""Step 2 application transactions: accounts, categories, retained DRAFTs only."""
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from uuid import uuid4

from sqlalchemy.exc import DBAPIError

from app.finance import authorization as policy
from app.finance.domain import FinanceRequestError, validate_draft
from app.finance.dto import AccountResponse, CategoryResponse, ItemResponse, TransactionResponse
from app.finance.money import canonical_decimal
from app.finance.ports import FinanceRepository, HouseholdAccess

RESPONSES = {"accounts": AccountResponse, "categories": CategoryResponse, "transactions": TransactionResponse, "items": ItemResponse}


def canonical(value):
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {key: canonical(child) for key, child in value.items()}
    if isinstance(value, list):
        return [canonical(child) for child in value]
    return value


class LedgerService:
    def __init__(self, session, repository: FinanceRepository, access: HouseholdAccess):
        self.session = session
        self.repository = repository
        self.access = access

    async def _object(self, resource, hid, identifier, *, lock=False):
        result = await self.repository.get(resource, hid, identifier, lock=lock)
        if result is None:
            raise FinanceRequestError(404, "FINANCE_NOT_FOUND")
        return result

    async def _currency(self, code):
        currency = await self.repository.currency(code)
        if currency is None:
            raise FinanceRequestError(422, "FINANCE_UNKNOWN_CURRENCY")
        return currency["minor_units"]

    async def _validate(self, hid, header, items):
        scale = await self._currency(header["currency_code"])
        validate_draft(header, items, scale)
        if header.get("category_id") is not None:
            category = await self._object("categories", hid, header["category_id"])
            if category["archived_at"] is not None:
                raise FinanceRequestError(409, "FINANCE_CATEGORY_ARCHIVED")
            if header["kind"] != category["kind"]:
                raise FinanceRequestError(422, "FINANCE_CATEGORY_KIND")

    async def _audit(self, hid, context, action, resource, row):
        details = {key: canonical(row[key]) for key in ("currency_code", "total_amount", "transaction_id") if key in row}
        await self.repository.audit({"household_id": hid, "actor_member_id": context.member_id,
            "request_id": str(uuid4()), "action": action, "target_type": resource,
            "target_id": str(row["id"]), "details": details})

    async def _command(self, actor, hid, permission, operation, key, body, effect, *, transaction_id=None):
        # OPEN-14 PROPOSAL subset: durable draft-scope keys; final contract in Step 3.
        if not isinstance(key, str) or not re.fullmatch(r"[\x21-\x7e]{1,128}", key):
            raise FinanceRequestError(422, "FINANCE_INVALID_IDEMPOTENCY_KEY")
        operation = f"{operation}:v1"
        digest = hashlib.sha256(json.dumps(canonical({"path": operation, "household_id": hid, "body": body}),
            sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        for attempt in range(3):
            try:
                async with self.session.begin():
                    context = await self.access.resolve(actor, hid, permission, write=True)
                    transaction = None
                    if transaction_id is not None:
                        transaction = await self._object("transactions", hid, transaction_id, lock=True)
                        policy.require_draft_editor(context, transaction)
                    # Authorization, creator and current session checks precede EVERY replay.
                    reservation, saved = await self.repository.reserve({"household_id": hid,
                        "actor_member_id": context.member_id, "operation": operation,
                        "request_key": key, "request_hash": digest})
                    if saved:
                        if saved["request_hash"] != digest:
                            raise FinanceRequestError(409, "FINANCE_IDEMPOTENCY_CONFLICT")
                        return saved["response_status"], saved["response_body"]
                    status, result = await effect(context, transaction)
                    await self.repository.complete(reservation, status, result)
                    return status, result
            except ValueError:
                raise FinanceRequestError(422, "FINANCE_INVALID_VALUE") from None
            except DBAPIError as exc:
                sqlstate = getattr(exc.orig, "sqlstate", None)
                if sqlstate in {"40001", "40P01"} and attempt < 2:
                    continue  # Whole transaction restarts, including access and reservation.
                if sqlstate in {"23505", "55000", "40001", "40P01"}:
                    raise FinanceRequestError(409, "FINANCE_CONFLICT") from None
                if sqlstate == "23503":
                    raise FinanceRequestError(404, "FINANCE_NOT_FOUND") from None
                if sqlstate == "23514":
                    raise FinanceRequestError(422, "FINANCE_INVALID_VALUE") from None
                raise

    async def currencies(self, actor, hid):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            return await self.repository.currencies()

    async def get(self, actor, hid, resource, identifier):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            row = await self._object(resource, hid, identifier)
            if resource == "transactions":
                row = await self.repository.transaction_result(hid, identifier)
            return RESPONSES[resource].model_validate(row).model_dump(mode="json")

    async def page(self, actor, hid, resource, limit=50, cursor=None, **filters):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            position = None
            if cursor:
                try:
                    if len(cursor) > 2048:
                        raise ValueError()
                    decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                    if decoded["scope"] != [hid, resource, filters]:
                        raise ValueError()
                    position = decoded["position"]
                    if resource == "transactions":
                        instant = datetime.fromisoformat(position[0])
                        if instant.tzinfo is None or len(position) != 2:
                            raise ValueError()
                    elif len(position) != 1:
                        raise ValueError()
                    if type(position[-1]) is not int or not 0 < position[-1] <= 9223372036854775807:
                        raise ValueError()
                except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
                    raise FinanceRequestError(422, "FINANCE_INVALID_CURSOR") from None
            rows = await self.repository.page(resource, hid, limit + 1, position, filters)
            next_cursor = None
            if len(rows) > limit:
                rows = rows[:limit]
                last = rows[-1]
                position = [last["occurred_at"].isoformat(), last["id"]] if resource == "transactions" else [last["id"]]
                next_cursor = base64.urlsafe_b64encode(json.dumps({"scope": [hid, resource, filters], "position": position},
                    sort_keys=True, separators=(",", ":")).encode()).decode()
            results = []
            for row in rows:
                if resource == "transactions":
                    row = await self.repository.transaction_result(hid, row["id"])
                results.append(RESPONSES[resource].model_validate(row).model_dump(mode="json"))
            return {"items": results, "next_cursor": next_cursor}

    async def create_reference(self, actor, hid, resource, body, key):
        values = body.model_dump()
        async def effect(context, _):
            if resource == "accounts":
                await self._currency(values["currency_code"])
            row = await self.repository.create(resource, values | {"household_id": hid})
            await self._audit(hid, context, "FINANCE_" + resource.upper() + "_CREATED", resource, row)
            return 201, RESPONSES[resource].model_validate(row).model_dump(mode="json")
        return await self._command(actor, hid, policy.ADMINISTER, f"POST /households/{hid}/{resource}", key, values, effect)

    async def archive(self, actor, hid, resource, identifier, key):
        async def effect(context, _):
            row = await self._object(resource, hid, identifier, lock=True)
            row = await self.repository.update(resource, hid, identifier, {"archived_at": row["archived_at"] or datetime.now(timezone.utc)})
            await self._audit(hid, context, "FINANCE_" + resource.upper() + "_ARCHIVED", resource, row)
            return 204, None
        return await self._command(actor, hid, policy.ADMINISTER,
            f"POST /households/{hid}/{resource}/{identifier}/archive", key, {}, effect)

    async def create_draft(self, actor, hid, body, key):
        values = body.model_dump()
        async def effect(context, _):
            header = {k: v for k, v in values.items() if k != "items"}
            await self._validate(hid, header, values["items"])
            row = await self.repository.create("transactions", header | {"household_id": hid,
                "created_by_member_id": context.member_id, "status": "DRAFT"})
            for item in values["items"]:
                await self.repository.create("items", item | {"household_id": hid, "transaction_id": row["id"]})
            await self._audit(hid, context, "FINANCE_DRAFT_CREATED", "transaction", row)
            return 201, TransactionResponse.model_validate(await self.repository.transaction_result(hid, row["id"])).model_dump(mode="json")
        return await self._command(actor, hid, policy.DRAFT, f"POST /households/{hid}/transactions", key, values, effect)

    async def patch_draft(self, actor, hid, identifier, body, key):
        values = body.model_dump(exclude_unset=True)
        async def effect(context, transaction):
            items = await self.repository.items(hid, identifier)
            await self._validate(hid, transaction | values, items)
            row = await self.repository.update("transactions", hid, identifier, values)
            await self._audit(hid, context, "FINANCE_DRAFT_UPDATED", "transaction", row)
            return 200, TransactionResponse.model_validate(await self.repository.transaction_result(hid, identifier)).model_dump(mode="json")
        return await self._command(actor, hid, policy.DRAFT, f"PATCH /households/{hid}/transactions/{identifier}",
                                   key, values, effect, transaction_id=identifier)

    async def item(self, actor, hid, transaction_id, body, key, *, item_id=None):
        values = body.model_dump(exclude_unset=item_id is not None)
        method = "POST" if item_id is None else "PATCH"
        path = f"{method} /households/{hid}/transactions/{transaction_id}/items" + (f"/{item_id}" if item_id is not None else "")
        async def effect(context, transaction):
            items = await self.repository.items(hid, transaction_id)
            if item_id is not None:
                item = next((row for row in items if row["id"] == item_id), None)
                if item is None:
                    raise FinanceRequestError(404, "FINANCE_NOT_FOUND")
                updated = [row | values if row["id"] == item_id else row for row in items]
            else:
                updated = items + [values]
            await self._validate(hid, transaction, updated)
            row = (await self.repository.create("items", values | {"household_id": hid, "transaction_id": transaction_id})
                   if item_id is None else await self.repository.update("items", hid, item_id, values))
            await self._audit(hid, context, "FINANCE_DRAFT_ITEM_ADDED" if item_id is None else "FINANCE_DRAFT_ITEM_UPDATED", "transaction_item", row)
            return (201 if item_id is None else 200), ItemResponse.model_validate(row).model_dump(mode="json")
        return await self._command(actor, hid, policy.DRAFT, path, key, values, effect, transaction_id=transaction_id)
