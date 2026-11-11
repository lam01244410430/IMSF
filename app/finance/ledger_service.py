"""Application-owned finance commands and read-only ledger projections."""
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from uuid import uuid4

from sqlalchemy.exc import DBAPIError

from app.finance import authorization as policy
from app.finance.domain import FinanceRequestError, require_full_reversal_eligible, validate_draft, validate_settlement
from app.finance.dto import (AccountResponse, BalanceResponse, CategoryResponse, ItemResponse,
    LedgerEntryResponse, PaymentBatchResponse, ReversalResponse, TransactionResponse, TransactionPost)
from app.finance.money import canonical_decimal
from app.finance.ports import FinanceRepository, HouseholdAccess, ReversalEffects

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
    def __init__(self, session, repository: FinanceRepository, access: HouseholdAccess, reversal_effects: ReversalEffects | None = None):
        self.session = session
        self.repository = repository
        self.access = access
        self.reversal_effects = reversal_effects

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
        # P04-OPEN-01/13 PROPOSAL: paired DRAFT annotations are scoped reads.
        for item in items:
            if (item.get("product_id") is None) != (item.get("base_quantity") is None):
                raise FinanceRequestError(422, "FINANCE_INVALID_VALUE")
            if item.get("product_id") is not None:
                product = await self.repository.product(hid, item["product_id"])
                if product is None:
                    raise FinanceRequestError(404, "FINANCE_NOT_FOUND")
                if product["archived_at"] is not None:
                    raise FinanceRequestError(409, "FINANCE_CONFLICT")
                if item["base_quantity"] <= 0:
                    raise FinanceRequestError(422, "FINANCE_INVALID_VALUE")
        if header.get("category_id") is not None:
            category = await self._object("categories", hid, header["category_id"])
            if category["archived_at"] is not None:
                raise FinanceRequestError(409, "FINANCE_CATEGORY_ARCHIVED")
            if header["kind"] != category["kind"]:
                raise FinanceRequestError(422, "FINANCE_CATEGORY_KIND")

    async def _audit(self, hid, context, action, resource, row):
        details = {key: canonical(row[key]) for key in ("currency_code", "total_amount", "transaction_id",
            "original_transaction_id", "reversal_reason") if key in row}
        await self.repository.audit({"household_id": hid, "actor_member_id": context.member_id,
            "request_id": str(uuid4()), "action": action, "target_type": resource,
            "target_id": str(row["id"]), "details": details})

    async def _command(self, actor, hid, permission, operation, key, body, effect, *, transaction_id=None, draft_only=True):
        # OPEN-14 PROPOSAL: durable successful commands; no provisional commit.
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
                        if draft_only:
                            policy.require_draft_editor(context, transaction, check_status=False)
                    # Authorization, creator and current session checks precede EVERY replay.
                    reservation, saved = await self.repository.reserve({"household_id": hid,
                        "actor_member_id": context.member_id, "operation": operation,
                        "request_key": key, "request_hash": digest})
                    if saved:
                        if saved["request_hash"] != digest:
                            raise FinanceRequestError(409, "FINANCE_IDEMPOTENCY_CONFLICT")
                        return saved["response_status"], saved["response_body"]
                    if transaction is not None and draft_only:
                        policy.require_draft_editor(context, transaction)
                    status, result = await effect(context, transaction)
                    await self.repository.complete(reservation, status, result)
                    return status, result
            except ValueError:
                raise FinanceRequestError(422, "FINANCE_INVALID_VALUE") from None
            except DBAPIError as exc:
                sqlstate = getattr(exc.orig, "sqlstate", None)
                transient = (sqlstate in {"40001", "40P01", "57P01"}
                             or bool(sqlstate and sqlstate.startswith("08")) or exc.connection_invalidated)
                if transient and attempt < 2:
                    continue  # Whole transaction restarts, including access and reservation.
                if transient:
                    raise FinanceRequestError(409, "FINANCE_RETRY_EXHAUSTED") from None
                if sqlstate in {"23505", "55000"}:
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


    async def settle(self, actor, hid, identifier, body, key, *, posting):
        values = body.model_dump()
        for payment in values["payments"]:
            if payment["transaction_amount"] is None:
                payment["transaction_amount"] = payment["amount"]

        async def effect(context, transaction):
            return await self._settle_in_uow(context, hid, identifier, transaction, values, posting=posting)

        return await self._command(actor, hid, policy.ADMINISTER,
            f"POST /households/{hid}/transactions/{identifier}/{'post' if posting else 'payments'}",
            key, values, effect, transaction_id=identifier, draft_only=False)

    async def post_in_uow(self, context, household_id, transaction_id, body: TransactionPost):
        """P04-OPEN-07 PROPOSAL: caller owns authorization, key and transaction.

        No nested command, reservation or commit. Acquire the same original and
        ordered account locks and use precisely the public settlement engine.
        """
        transaction = await self._object("transactions", household_id, transaction_id, lock=True)
        values = body.model_dump()
        for payment in values["payments"]:
            if payment["transaction_amount"] is None:
                payment["transaction_amount"] = payment["amount"]
        _, result = await self._settle_in_uow(
            context, household_id, transaction_id, transaction, values, posting=True
        )
        return result

    async def _settle_in_uow(self, context, hid, identifier, transaction, values, *, posting):
        if transaction["status"] != ("DRAFT" if posting else "POSTED"):
            raise FinanceRequestError(409, "FINANCE_DRAFT_REQUIRED" if posting else "FINANCE_POSTED_REQUIRED")
        result = await self.repository.transaction_result(hid, identifier)
        if result["is_reversed"]:
            raise FinanceRequestError(409, "FINANCE_TRANSACTION_REVERSED")
        if posting:
            await self._validate(hid, transaction, result["items"])
        scale = await self._currency(transaction["currency_code"])
        validate_settlement(transaction, result["items"], values["payments"], result["settled_amount"], scale, posting=posting)
        # Ordered account locks protect opening-first-entry and archive races;
        # the transaction row protects duplicate posting and cumulative payment.
        for account_id in sorted({p["account_id"] for p in values["payments"]}):
            account = await self._object("accounts", hid, account_id, lock=True)
            if account["archived_at"] is not None:
                raise FinanceRequestError(409, "FINANCE_ACCOUNT_ARCHIVED")
            if account["currency_code"] != transaction["currency_code"]:
                raise FinanceRequestError(422, "FINANCE_FX_UNSUPPORTED")
            if transaction["kind"] == "OPENING" and await self.repository.has_entries(hid, account_id):
                raise FinanceRequestError(409, "FINANCE_OPENING_NOT_FIRST")
        # One posting instant for both transfer legs. occurred_at never drives
        # ledger order. Negative balances are allowed (OPEN-11 PROPOSAL).
        instant = datetime.now(timezone.utc)
        if posting:
            await self.repository.update("transactions", hid, identifier, {"status": "POSTED", "posted_at": instant})
        payments = []
        for payment in values["payments"]:
            row = await self.repository.create("payments", payment | {"household_id": hid,
                "transaction_id": identifier, "created_by_member_id": context.member_id, "settled_at": payment["settled_at"] or instant})
            payments.append(row)
            await self.repository.create("ledger", {"household_id": hid, "transaction_id": identifier,
                "account_id": row["account_id"], "currency_code": row["currency_code"], "payment_id": row["id"],
                "signed_amount": row["amount"] if row["direction"] == "IN" else -row["amount"], "posted_at": instant})
        await self._audit(hid, context, "FINANCE_POSTED" if posting else "FINANCE_PAYMENTS_CREATED", "transaction", transaction)
        result = await self.repository.transaction_result(hid, identifier)
        if posting:
            return 200, TransactionResponse.model_validate(result).model_dump(mode="json")
        return 201, PaymentBatchResponse.model_validate({"transaction_id": identifier, "payments": payments,
            "settled_amount": result["settled_amount"], "remaining_amount": result["remaining_amount"]}).model_dump(mode="json")

    async def reverse(self, actor, hid, identifier, body, key):
        values = body.model_dump()

        async def effect(context, transaction):
            # _command already holds the original row lock: settlement cannot
            # append a payment between this snapshot and the committed reversal.
            result = await self.repository.transaction_result(hid, identifier)
            original_payments = await self.repository.payments(hid, identifier)
            original_entries = await self.repository.ledger_entries(hid, identifier)
            account_ids = {row["account_id"] for row in original_payments + original_entries}
            for account_id in sorted(account_ids):
                await self._object("accounts", hid, account_id, lock=True)
                # OPEN-11 PROPOSAL reversal exception: archived accounts allow
                # audited correction of history, without new external execution.
            # P04-OPEN-10/11 PROPOSALS: real facts under the original lock.
            # Existing P03 unresolved-refund rule has priority over stock refusal.
            if self.reversal_effects is None:
                raise RuntimeError("ReversalEffects must be configured")
            effects = await self.reversal_effects.load_locked(hid, identifier)
            require_full_reversal_eligible(result, list(effects.unresolved_refunds))
            if effects.stock_lot_ids:
                raise FinanceRequestError(409, "FINANCE_STOCK_EFFECT_UNRESOLVED")
            instant = datetime.now(timezone.utc)
            reversal = await self.repository.create("transactions", {
                "household_id": hid, "kind": "REVERSAL", "status": "POSTED",
                "currency_code": result["currency_code"], "total_amount": result["total_amount"],
                "category_id": None, "original_transaction_id": identifier,
                "reversal_reason": values["reason"], "created_by_member_id": context.member_id,
                "occurred_at": instant, "posted_at": instant})
            payment_map = {}
            for payment in original_payments:
                mirror = await self.repository.create("payments", {
                    name: payment[name] for name in ("account_id", "currency_code", "amount", "transaction_amount", "method_code")
                } | {"household_id": hid, "transaction_id": reversal["id"],
                    "direction": "IN" if payment["direction"] == "OUT" else "OUT",
                    "reverses_payment_id": payment["id"], "settled_at": instant,
                    "created_by_member_id": context.member_id, "exchange_rate": None, "external_reference": None})
                payment_map[payment["id"]] = mirror["id"]
            entry_ids = []
            for entry in original_entries:
                mirror = await self.repository.create("ledger", {
                    "household_id": hid, "transaction_id": reversal["id"],
                    "account_id": entry["account_id"], "currency_code": entry["currency_code"],
                    "signed_amount": -entry["signed_amount"], "posted_at": instant,
                    "reverses_entry_id": entry["id"],
                    "payment_id": payment_map[entry["payment_id"]] if entry["payment_id"] is not None else None})
                entry_ids.append(mirror["id"])
            # OPEN-08 PROPOSAL: unpaid bills produce only a reversal header.
            # Assert exact cancellation from persisted rows, never planned mirrors.
            persisted = await self.repository.ledger_entries(hid, reversal["id"])
            totals = {}
            for entry in original_entries + persisted:
                scope = (entry["account_id"], entry["currency_code"])
                totals[scope] = totals.get(scope, Decimal(0)) + entry["signed_amount"]
            if any(amount != 0 for amount in totals.values()):
                raise FinanceRequestError(409, "FINANCE_REVERSAL_INCOMPLETE")
            await self._audit(hid, context, "FINANCE_REVERSED", "transaction", reversal)
            return 201, ReversalResponse.model_validate({"original_transaction_id": identifier,
                "reversal_transaction": await self.repository.transaction_result(hid, reversal["id"]),
                "payment_ids": list(payment_map.values()), "ledger_entry_ids": entry_ids}).model_dump(mode="json")

        return await self._command(actor, hid, policy.REVERSE,
            f"POST /households/{hid}/transactions/{identifier}/reversals", key, values,
            effect, transaction_id=identifier, draft_only=False)

    async def payments(self, actor, hid, identifier):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            await self._object("transactions", hid, identifier)
            result = await self.repository.transaction_result(hid, identifier)
            return PaymentBatchResponse.model_validate({"transaction_id": identifier,
                "payments": await self.repository.payments(hid, identifier),
                "settled_amount": result["settled_amount"], "remaining_amount": result["remaining_amount"]}).model_dump(mode="json")

    @staticmethod
    def _instant(value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise FinanceRequestError(422, "FINANCE_OFFSET_REQUIRED")
        return value.astimezone(timezone.utc) if value is not None else None

    @staticmethod
    def _encode_cursor(scope, row):
        return base64.urlsafe_b64encode(json.dumps({"scope": canonical(scope),
            "position": [row["posted_at"].isoformat(), row["id"]]}, sort_keys=True, separators=(",", ":")).encode()).decode()

    @staticmethod
    def _decode_cursor(cursor, scope):
        if cursor is None:
            return None
        try:
            if len(cursor) > 2048:
                raise ValueError()
            data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            position = data["position"]
            if (data["scope"] != canonical(scope) or not isinstance(position, list) or len(position) != 2
                or not isinstance(position[0], str) or type(position[1]) is not int or not 0 < position[1] <= 9223372036854775807):
                raise ValueError()
            if datetime.fromisoformat(position[0]).utcoffset() is None:
                raise ValueError()
            return position
        except (ValueError, TypeError, KeyError, IndexError, UnicodeError):
            raise FinanceRequestError(422, "FINANCE_INVALID_CURSOR") from None

    async def ledger(self, actor, hid, *, account_id=None, date_from=None, date_to=None, cursor=None, limit=50):
        date_from, date_to = self._instant(date_from), self._instant(date_to)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise FinanceRequestError(422, "FINANCE_INVALID_DATE_RANGE")
        scope = [hid, "ledger:v1", account_id, date_from, date_to]
        position = self._decode_cursor(cursor, scope)
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            if account_id is not None:
                await self._object("accounts", hid, account_id)
            rows = await self.repository.ledger(hid, account_id, date_from, date_to, position, limit + 1)
            next_cursor = self._encode_cursor(scope, rows[limit - 1]) if len(rows) > limit else None
            return {"items": [LedgerEntryResponse.model_validate(r).model_dump(mode="json") for r in rows[:limit]],
                "next_cursor": next_cursor}

    async def balance(self, actor, hid, account_id, *, as_of=None, cursor=None):
        as_of = self._instant(as_of)
        scope = [hid, "balance:v1", account_id]
        position = self._decode_cursor(cursor, scope)
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            account = await self._object("accounts", hid, account_id)
            result = await self.repository.balance(hid, account_id, as_of, position)
            return BalanceResponse.model_validate({"account_id": account_id, "currency_code": account["currency_code"],
                "balance": result["balance"], "cursor": self._encode_cursor(scope, result) if result["id"] is not None else None}).model_dump(mode="json")
