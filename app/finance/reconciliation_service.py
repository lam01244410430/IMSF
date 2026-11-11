"""Read-only book integrity and retained manual observations.

OPEN-09/10/14 PROPOSALS: exact closure, existing permission gates, durable keys.
The only writes here are sessions, matches, audit and idempotency records.
"""
import base64
from datetime import datetime, timezone
from decimal import Decimal
import json
from uuid import uuid4

from app.finance import authorization as policy
from app.finance.domain import FinanceRequestError
from app.finance.dto import IntegrityReport, ReconciliationReport
from app.finance.ledger_service import LedgerService, canonical
from app.finance.money import exact_decimal

ZERO = Decimal("0")
INTERNAL_CODES = {"PAYMENT_LEDGER_MISSING", "PAYMENT_LEDGER_MISMATCH", "TRANSFER_UNBALANCED",
                  "OVERSETTLED", "REVERSAL_INCOMPLETE"}


def issue(code, *, account_id=None, currency_code=None, transaction_id=None,
          payment_id=None, ledger_entry_id=None, expected=ZERO, actual=ZERO):
    return {"code": code, "account_id": account_id, "currency_code": currency_code,
            "transaction_id": transaction_id, "payment_id": payment_id, "ledger_entry_id": ledger_entry_id,
            "expected_amount": expected, "actual_amount": actual}


def detect_integrity(transactions, payments, entries):
    """Compare settled payments, full transfer legs and reversal mirrors, never bill cash totals."""
    issues = []
    for p in payments:
        linked = [e for e in entries if e["payment_id"] == p["id"]]
        expected = p["amount"] if p["direction"] == "IN" else -p["amount"]
        common = {"account_id": p["account_id"], "currency_code": p["currency_code"],
                  "transaction_id": p["transaction_id"], "payment_id": p["id"], "expected": expected}
        if not linked:
            issues.append(issue("PAYMENT_LEDGER_MISSING", **common))
        elif len(linked) != 1 or any(e["signed_amount"] != expected or any(e[k] != p[k]
            for k in ("account_id", "currency_code", "transaction_id")) for e in linked):
            issues.append(issue("PAYMENT_LEDGER_MISMATCH", **common,
                ledger_entry_id=linked[0]["id"], actual=sum((e["signed_amount"] for e in linked), ZERO)))
    payment_ids = {p["id"] for p in payments}
    for e in entries:
        if e["payment_id"] not in payment_ids:
            issues.append(issue("PAYMENT_LEDGER_MISMATCH", account_id=e["account_id"],
                currency_code=e["currency_code"], transaction_id=e["transaction_id"],
                ledger_entry_id=e["id"], payment_id=e["payment_id"], actual=e["signed_amount"]))
    for t in transactions:
        if t["status"] != "POSTED":
            continue
        ps = [p for p in payments if p["transaction_id"] == t["id"]]
        es = [e for e in entries if e["transaction_id"] == t["id"]]
        scopes = sorted({(r["account_id"], r["currency_code"]) for r in ps + es})
        if t["kind"] in {"INCOME", "EXPENSE"}:
            total = sum((p["transaction_amount"] for p in ps), ZERO)
            if total > t["total_amount"]:
                for aid, cc in scopes:
                    issues.append(issue("OVERSETTLED", account_id=aid, currency_code=cc,
                        transaction_id=t["id"], expected=t["total_amount"], actual=total))
        if t["kind"] == "TRANSFER":
            total = sum((e["signed_amount"] for e in es), ZERO)
            if (len(es) != 2 or total != 0 or len({e["account_id"] for e in es}) != 2
                or sorted(e["signed_amount"] for e in es) != [-t["total_amount"], t["total_amount"]]):
                for aid, cc in scopes or [(None, t["currency_code"])]:
                    issues.append(issue("TRANSFER_UNBALANCED", account_id=aid, currency_code=cc,
                        transaction_id=t["id"], actual=total))
        if t["kind"] == "REVERSAL":
            originals = [e for e in entries if e["transaction_id"] == t["original_transaction_id"]]
            original_payments = [p for p in payments if p["transaction_id"] == t["original_transaction_id"]]
            old_entries = {e["id"]: e for e in originals}
            old_payments = {p["id"]: p for p in original_payments}
            new_payments = {p["id"]: p for p in ps}
            all_rows = originals + es + original_payments + ps
            for aid, cc in sorted({(r["account_id"], r["currency_code"]) for r in all_rows}):
                old = [e for e in originals if (e["account_id"], e["currency_code"]) == (aid, cc)]
                new = [e for e in es if (e["account_id"], e["currency_code"]) == (aid, cc)]
                old_ps = [p for p in original_payments if (p["account_id"], p["currency_code"]) == (aid, cc)]
                new_ps = [p for p in ps if (p["account_id"], p["currency_code"]) == (aid, cc)]
                expected = -sum((e["signed_amount"] for e in old), ZERO)
                actual = sum((e["signed_amount"] for e in new), ZERO)
                broken = actual != expected or len(old) != len(new) or len(old_ps) != len(new_ps)
                broken |= {e["reverses_entry_id"] for e in new} != {e["id"] for e in old}
                broken |= {p["reverses_payment_id"] for p in new_ps} != {p["id"] for p in old_ps}
                bad_entry = None
                for e in new:
                    target = old_entries.get(e["reverses_entry_id"])
                    mirror_payment = new_payments.get(e["payment_id"])
                    if (target is None or e["signed_amount"] != -target["signed_amount"] or
                        any(e[k] != target[k] for k in ("account_id", "currency_code")) or
                        mirror_payment is None or mirror_payment["reverses_payment_id"] != target["payment_id"]):
                        broken = True
                        bad_entry = e
                for p in new_ps:
                    target = old_payments.get(p["reverses_payment_id"])
                    if (target is None or any(p[k] != target[k] for k in
                        ("account_id", "currency_code", "amount", "transaction_amount")) or
                        p["direction"] != ("OUT" if target["direction"] == "IN" else "IN")):
                        broken = True
                if broken:
                    if bad_entry is not None:
                        target = old_entries.get(bad_entry["reverses_entry_id"])
                        expected = -target["signed_amount"] if target else ZERO
                        actual = bad_entry["signed_amount"]
                    issues.append(issue("REVERSAL_INCOMPLETE", account_id=aid, currency_code=cc,
                        transaction_id=t["id"], ledger_entry_id=bad_entry["id"] if bad_entry else None,
                        expected=expected, actual=actual))

    return issues


class ReconciliationService(LedgerService):
    """Reuse the established transaction/idempotency protocol without changing posting."""

    async def _sources(self, hid, *, closed_at=None):
        ts = await self.repository.reconciliation_rows(hid, "transactions")
        ps = await self.repository.reconciliation_rows(hid, "payments")
        es = await self.repository.reconciliation_rows(hid, "ledger")
        if closed_at is not None:
            ts = [t for t in ts if t["posted_at"] is not None and t["posted_at"] <= closed_at]
            visible_transactions = {t["id"] for t in ts}
            later_payment_ids = {e["payment_id"] for e in es if e["posted_at"] > closed_at}
            # PostgreSQL now()/created_at is transaction-start time: a settlement
            # waiting behind close can start earlier but post later. Its payment
            # belongs to that later ledger event, never to the closed snapshot.
            ps = [p for p in ps if p["created_at"] <= closed_at and
                  p["transaction_id"] in visible_transactions and p["id"] not in later_payment_ids]
            es = [e for e in es if e["posted_at"] <= closed_at]
        return ts, ps, es

    async def integrity_issues(self, hid):
        """Query-only detector seam; also used by rollback-only migrator corruption tests."""
        return detect_integrity(*await self._sources(hid))

    async def integrity(self, actor, hid, account_id=None, currency_code=None):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            if currency_code is not None:
                await self._currency(currency_code)
            if account_id is not None:
                await self._object("accounts", hid, account_id)
            accounts = await self.repository.reconciliation_rows(hid, "accounts")
            # Same ordered locks as posting: every summary and issue sees committed
            # payment/ledger pairs, including both legs of a transfer.
            for a in accounts:
                await self._object("accounts", hid, a["id"], lock=True)
            ts, ps, es = await self._sources(hid)
            summaries = []
            for a in accounts:
                if ((account_id is not None and a["id"] != account_id) or
                    (currency_code is not None and a["currency_code"] != currency_code)):
                    continue
                selected = [e for e in es if e["account_id"] == a["id"] and e["currency_code"] == a["currency_code"]]
                summaries.append({"account_id": a["id"], "currency_code": a["currency_code"],
                    "balance": sum((e["signed_amount"] for e in selected), ZERO), "entry_count": len(selected),
                    "payment_count": sum(p["account_id"] == a["id"] and p["currency_code"] == a["currency_code"] for p in ps)})
            issues = [i for i in detect_integrity(ts, ps, es) if
                (account_id is None or i["account_id"] == account_id) and
                (currency_code is None or i["currency_code"] == currency_code)]
            return IntegrityReport.model_validate({"accounts": summaries, "integrity_issues": issues}).model_dump(mode="json")

    async def _locked_session(self, hid, sid, *, open_only=False):
        candidate = await self._object("reconciliations", hid, sid)
        await self._object("accounts", hid, candidate["account_id"], lock=True)
        row = await self._object("reconciliations", hid, sid, lock=True)
        if open_only and row["state"] != "OPEN":
            raise FinanceRequestError(409, "FINANCE_SESSION_CLOSED")
        return row

    async def _report(self, hid, s):
        closed_at = s["closed_at"]
        aid, cc, cutoff = s["account_id"], s["currency_code"], s["cutoff_ledger_entry_id"] or 0
        ts, ps, es = await self._sources(hid, closed_at=closed_at)
        scoped = [e for e in es if e["account_id"] == aid and e["currency_code"] == cc]
        eligible = [e for e in scoped if e["id"] <= cutoff]
        matches = await self.repository.reconciliation_rows(hid, "matches")
        # CLOSED reports reconstruct active matching at close time. Later sessions
        # may match earlier outstanding entries without changing this observation.
        active = [m for m in matches if (closed_at is None and m["unmatched_at"] is None) or
            (closed_at is not None and m["matched_at"] <= closed_at and
             (m["unmatched_at"] is None or m["unmatched_at"] > closed_at))]
        matched_ids = sorted(m["ledger_entry_id"] for m in active if m["session_id"] == s["id"])
        matched_any = {m["ledger_entry_id"] for m in active}
        unmatched = [e["id"] for e in eligible if e["id"] not in matched_any]
        matched_total = sum((e["signed_amount"] for e in eligible if e["id"] in matched_ids), ZERO)
        previous = ZERO
        if s["previous_session_id"] is not None:
            prior = await self._object("reconciliations", hid, s["previous_session_id"])
            previous = prior["statement_balance"]
        expected = previous + matched_total
        difference = s["statement_balance"] - expected
        # Exclude later target-account payments/entries from the cutoff detector;
        # retain other legs so a valid transfer is assessed as a complete transfer.
        later_payments = {e["payment_id"] for e in scoped if e["id"] > cutoff}
        bounded_entries = [e for e in es if e["account_id"] != aid or e["id"] <= cutoff]
        bounded_payments = [p for p in ps if p["id"] not in later_payments]
        bounded_tids = {r["transaction_id"] for r in bounded_entries + bounded_payments if r["account_id"] == aid}
        bounded_ts = [t for t in ts if t["id"] in bounded_tids or t["original_transaction_id"] in bounded_tids]
        issues = [i for i in detect_integrity(bounded_ts, bounded_payments, bounded_entries)
                  if i["account_id"] == aid and i["currency_code"] == cc]
        base = {"account_id": aid, "currency_code": cc}
        if difference:
            issues.append(issue("STATEMENT_DIFFERENCE", **base, expected=expected, actual=s["statement_balance"]))
        if unmatched:
            issues.append(issue("UNMATCHED_LEDGER", **base, ledger_entry_id=unmatched[0],
                actual=sum((e["signed_amount"] for e in eligible if e["id"] in unmatched), ZERO)))
        if closed_at is None and any(e["id"] > cutoff for e in scoped):
            issues.append(issue("CUTOFF_STALE", **base, ledger_entry_id=max(e["id"] for e in scoped)))
        eligible_close = not difference and not any(i["code"] in INTERNAL_CODES | {"CUTOFF_STALE"} for i in issues)
        return ReconciliationReport.model_validate(s | {"session_id": s["id"],
            "previous_statement_balance": previous, "matched_entry_ids": matched_ids,
            "active_matches": [{"match_id": m["id"], "ledger_entry_id": m["ledger_entry_id"]}
                               for m in active if m["session_id"] == s["id"]], "matched_total": matched_total,
            "expected_closing_balance": expected, "difference": difference, "unmatched_entry_ids": unmatched,
            "unmatched_count": len(unmatched), "integrity_issues": issues,
            "close_eligible": eligible_close and (not unmatched or closed_at is not None)}).model_dump(mode="json")

    async def report(self, actor, hid, sid):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            return await self._report(hid, await self._locked_session(hid, sid))

    async def sessions(self, actor, hid, limit=50, cursor=None, account_id=None):
        async with self.session.begin():
            await self.access.resolve(actor, hid, policy.READ, write=False)
            if account_id is not None:
                await self._object("accounts", hid, account_id)
            scope = [hid, "reconciliations:v1", account_id]
            position = None
            if cursor is not None:
                try:
                    data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                    pos = data["position"]
                    if data["scope"] != scope or type(pos) is not int or not 0 < pos <= 9223372036854775807:
                        raise ValueError()
                    position = [pos]
                except (ValueError, TypeError, KeyError, UnicodeError):
                    raise FinanceRequestError(422, "FINANCE_INVALID_CURSOR") from None
            rows = await self.repository.page("reconciliations", hid, limit+1, position, {"account_id": account_id})
            next_cursor = None
            if len(rows) > limit:
                rows = rows[:limit]
                next_cursor = base64.urlsafe_b64encode(json.dumps({"scope": scope, "position": rows[-1]["id"]}).encode()).decode()
            # Lock in account order, not page order, to avoid opposite-order readers.
            for aid in sorted({r["account_id"] for r in rows}):
                await self._object("accounts", hid, aid, lock=True)
            return {"items": [await self._report(hid, await self._object("reconciliations", hid, r["id"])) for r in rows],
                    "next_cursor": next_cursor}

    async def _reconciliation_audit(self, hid, context, action, row, report, **extra):
        await self.repository.audit({"household_id": hid, "actor_member_id": context.member_id,
            "request_id": str(uuid4()), "action": "FINANCE_RECONCILIATION_"+action,
            "target_type": "reconciliation_session", "target_id": str(row["id"]),
            "details": canonical({k: report[k] for k in ("session_id", "account_id", "currency_code",
                "statement_balance", "matched_total", "expected_closing_balance", "difference", "cutoff_ledger_entry_id")}) | extra})

    async def create_session(self, actor, hid, body, key):
        values = body.model_dump()
        async def effect(context, _):
            account = await self._object("accounts", hid, values["account_id"], lock=True)
            if await self.repository.currency(values["currency_code"]) is None:
                raise FinanceRequestError(422, "FINANCE_INVALID_INPUT")
            if account["currency_code"] != values["currency_code"]:
                raise FinanceRequestError(422, "FINANCE_CURRENCY_MISMATCH")
            scale = await self._currency(values["currency_code"])
            try:
                exact_decimal(values["statement_balance"], scale)
            except ValueError:
                raise FinanceRequestError(422, "FINANCE_INVALID_INPUT") from None
            if await self.repository.reconciliation_open(hid, account["id"]):
                raise FinanceRequestError(409, "FINANCE_SESSION_ALREADY_OPEN")
            prior = await self.repository.reconciliation_anchor(hid, account["id"], values["currency_code"])
            s = await self.repository.create("reconciliations", values | {"household_id": hid,
                "opened_by_member_id": context.member_id, "previous_session_id": prior["id"] if prior else None,
                "cutoff_ledger_entry_id": await self.repository.reconciliation_cutoff(hid, account["id"])})
            report = await self._report(hid, s)
            await self._reconciliation_audit(hid, context, "CREATED", s, report)
            return 201, report
        # date is normalized explicitly: the established canonicalizer handles
        # datetime and Decimal, while this DTO adds a date-only observation label.
        hashed = values | {"statement_date": values["statement_date"].isoformat()}
        return await self._command(actor, hid, policy.ADMINISTER, f"POST /households/{hid}/reconciliations", key, hashed, effect)

    async def mutate(self, actor, hid, sid, action, body, key, *, match_id=None):
        values = body.model_dump()
        async def effect(context, _):
            s = await self._locked_session(hid, sid, open_only=True)
            extra = {}
            if action == "matches":
                e = await self._object("ledger", hid, values["ledger_entry_id"])
                if (e["account_id"] != s["account_id"] or e["currency_code"] != s["currency_code"] or
                    e["id"] > (s["cutoff_ledger_entry_id"] or 0)):
                    raise FinanceRequestError(422, "FINANCE_MATCH_ENTRY_INVALID")
                matches = await self.repository.reconciliation_rows(hid, "matches")
                if any(m["ledger_entry_id"] == e["id"] and m["unmatched_at"] is None for m in matches):
                    raise FinanceRequestError(409, "FINANCE_MATCH_CONFLICT")
                m = await self.repository.create("matches", {"household_id": hid, "session_id": sid,
                    "account_id": s["account_id"], "ledger_entry_id": e["id"], "matched_by_member_id": context.member_id,
                    "matched_at": datetime.now(timezone.utc)})
                extra = {"match_id": m["id"], "ledger_entry_id": e["id"]}
                audit_action, status = "MATCHED", 201
            elif action == "unmatch":
                m = await self._object("matches", hid, match_id, lock=True)
                if m["session_id"] != sid:
                    raise FinanceRequestError(404, "FINANCE_NOT_FOUND")
                if m["unmatched_at"] is not None:
                    raise FinanceRequestError(409, "FINANCE_MATCH_CONFLICT")
                await self.repository.update("matches", hid, match_id, {"unmatched_at": datetime.now(timezone.utc),
                    "unmatched_by_member_id": context.member_id})
                extra = {"match_id": match_id, "ledger_entry_id": m["ledger_entry_id"], "reason": values["reason"]}
                audit_action, status = "UNMATCHED", 200
            elif action == "refresh-cutoff":
                # OPEN-09 PROPOSAL: explicit refresh changes only this high-water ID.
                s = await self.repository.update("reconciliations", hid, sid,
                    {"cutoff_ledger_entry_id": await self.repository.reconciliation_cutoff(hid, s["account_id"])})
                audit_action, status = "CUTOFF_REFRESHED", 200
            elif action == "close":
                # OPEN-09 PROPOSAL: zero tolerance and exact outstanding SET; no
                # client balance, preview or acknowledgment can override books.
                report = await self._report(hid, s)
                if (Decimal(report["difference"]) != 0 or any(i["code"] in INTERNAL_CODES | {"CUTOFF_STALE"}
                    for i in report["integrity_issues"]) or
                    set(values["acknowledged_outstanding_entry_ids"]) != set(report["unmatched_entry_ids"])):
                    raise FinanceRequestError(409, "FINANCE_RECONCILIATION_NOT_CLOSABLE")
                prior = await self.repository.reconciliation_anchor(hid, s["account_id"], s["currency_code"])
                if (prior["id"] if prior else None) != s["previous_session_id"]:
                    raise FinanceRequestError(409, "FINANCE_RECONCILIATION_NOT_CLOSABLE")
                s = await self.repository.update("reconciliations", hid, sid, {"state": "CLOSED",
                    "closed_at": datetime.now(timezone.utc), "closed_by_member_id": context.member_id})
                extra = {"acknowledged_outstanding_entry_ids": sorted(set(values["acknowledged_outstanding_entry_ids"]))}
                audit_action, status = "CLOSED", 200
            else:
                raise ValueError("Unknown reconciliation command")
            report = await self._report(hid, s)
            await self._reconciliation_audit(hid, context, audit_action, s, report, **extra)
            return status, report
        suffix = f"matches/{match_id}/unmatch" if action == "unmatch" else action
        return await self._command(actor, hid, policy.ADMINISTER,
            f"POST /households/{hid}/reconciliations/{sid}/{suffix}", key, values, effect)
