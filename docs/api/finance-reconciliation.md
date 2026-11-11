# Finance reconciliation

OPEN-09, OPEN-10 and OPEN-14 remain **PROPOSALS**, pending Lam's closure confirmation. Implementation and tests do not constitute policy approval.

All paths below follow `/api/v1/households/{household_id}`. Existing authentication and household isolation apply. OPEN-10 **PROPOSAL**: reads use `household.view` (all six roles); mutations use `finance.post` (OWNER and FINANCE_MANAGER). Archived households permit reads but reject writes and saved-response replays.

| Method | Path | Body | Success |
|---|---|---|---|
| GET | `/finance/integrity` | Query: optional `account_id`, `currency_code` | 200 |
| POST | `/reconciliations` | Create observation | 201 |
| GET | `/reconciliations` | Query: `limit` 1–200 (default 50), scoped `cursor`, optional `account_id` | 200 |
| GET | `/reconciliations/{session_id}` | — | 200 |
| POST | `/reconciliations/{session_id}/matches` | `{"ledger_entry_id":123}` | 201 |
| POST | `/reconciliations/{session_id}/matches/{match_id}/unmatch` | `{"reason":"Incorrect selection"}` | 200 |
| GET | `/reconciliations/{session_id}/discrepancies` | — | 200 |
| POST | `/reconciliations/{session_id}/close` | `{"acknowledged_outstanding_entry_ids":[]}` | 200 |
| POST | `/reconciliations/{session_id}/refresh-cutoff` | `{}` | 200 |

Create example (manual test observation only):

```json
{"account_id":123,"currency_code":"USD","statement_date":"2026-11-11","statement_balance":"12.30","statement_source":"BANK_STATEMENT","statement_reference":"November closing balance"}
```

The account and catalog currency must agree. Balance is a signed decimal string with currency precision; floats, excess precision, unknown currency and extra fields are rejected. `statement_source` is BANK_STATEMENT or CASH_COUNT. `statement_reference` is nullable, maximum 200 characters. Withdrawal reason is required, stripped, 1–1000 characters. Server owns actors, times, state, prior anchor and cutoff.

OPEN-09 **PROPOSAL** semantics:

- Lock account before session; at creation capture latest CLOSED session in the same account/currency and the maximum ledger entry ID. Only one OPEN session per account. Empty ledger cutoff is null. Statement date is a label, never an eligibility boundary.
- Book balance is the sum of posted ledger amounts. Integrity compares settled payments with exactly one matching ledger entry, expected IN positive and OUT negative. Partial bills use payments rather than header totals. Transfers require two full opposite account legs. Over-settlement and incomplete reversal mirrors are reported. Reversal validation checks each original entry/payment link and exact opposite amount/direction, even when aggregate totals net to zero.
- Match only entries in this household/account/currency at or below cutoff. One active match anywhere per entry. Withdrawal retains row/time/actor and audits reason; re-match creates another row. No deletion.
- `expected_closing_balance = previous_statement_balance + matched_total`; first previous balance is zero. Opening balance requires an actual posted OPENING entry. `difference = statement_balance - expected_closing_balance`. Currencies are never combined.
- Report fields: `session_id`, account/currency, state, observation source/reference/date, actors/timestamps, `previous_session_id`, `previous_statement_balance`, `cutoff_ledger_entry_id`, `matched_entry_ids`, `active_matches` (each with `match_id` and `ledger_entry_id`), `matched_total`, `expected_closing_balance`, `statement_balance`, `difference`, `unmatched_entry_ids`, `unmatched_count`, `integrity_issues`, `close_eligible`. The same computation serves create/get/discrepancies/mutations. Match creation and reads expose active match IDs in the report, so FINANCE_MANAGER can withdraw a match without audit-log access.
- Unmatched IDs are entries at or below cutoff without an active match in any session. Outstanding timing differences are separate from internal integrity defects. An OPEN preview with outstanding entries has `close_eligible=false` until exact acknowledgment is supplied to close; no acknowledgment is persisted by a preview. A CLOSED report reflects acknowledgment accepted at closure.
- Close rechecks persisted matches and the previous anchor under account then session locks. **Zero tolerance**: exact zero difference, no internal integrity failure, no stale cutoff. The acknowledgment **set** must equal exactly current outstanding IDs, including when empty. No client totals are accepted. Successful close retains actor/time and audits acknowledged IDs.
- New postings make an OPEN cutoff stale. Explicit refresh updates only cutoff; existing matches remain, new entries become eligible and unmatched. Refresh is audited. Same key replays saved bytes; a fresh key with no new posting yields the same cutoff/report.
- CLOSED sessions and matches are immutable, with no reopen. CLOSED reports reconstruct matches active at close time; later sessions matching earlier outstanding entries cannot rewrite that report. Later postings, even with backdated `occurred_at`, and reversal entries remain for later sessions. Posting time and ID govern eligibility.

Integrity GET returns `accounts` summaries (`account_id`, `currency_code`, `balance`, `entry_count`, `payment_count`) plus typed `integrity_issues`. Each issue includes code, relevant account/currency/transaction/payment/ledger IDs (nullable), and decimal-string `expected_amount`/`actual_amount`. Codes: PAYMENT_LEDGER_MISSING, PAYMENT_LEDGER_MISMATCH, TRANSFER_UNBALANCED, OVERSETTLED, REVERSAL_INCOMPLETE. Session reports additionally include STATEMENT_DIFFERENCE, UNMATCHED_LEDGER, CUTOFF_STALE. Reports never correct corruption.

OPEN-14 **PROPOSAL**: every mutation requires a 1–128 visible ASCII `Idempotency-Key`; operation/target/version and canonical body scope the saved result. Successful commands commit effect, audit and saved response atomically. Same key/body replays byte-identical success; changed body conflicts. Authorization is rechecked before replay. Three whole-transaction transient attempts follow the existing finance command protocol. Successful keys have no P03 expiry/purge. A saved success may replay after closure; a new command against CLOSED returns 409.

| Error code | Status / meaning |
|---|---|
| FINANCE_NOT_FOUND | 404 invisible or missing household/account/session/match/entry |
| FINANCE_INVALID_INPUT | 422 invalid DTO, precision, unknown create currency or missing/malformed header |
| FINANCE_UNKNOWN_CURRENCY | 422 unknown integrity filter currency |
| FINANCE_CURRENCY_MISMATCH | 422 session currency differs from account |
| FINANCE_INVALID_CURSOR | 422 malformed or differently scoped cursor |
| FINANCE_SESSION_ALREADY_OPEN | 409 second OPEN observation for account |
| FINANCE_SESSION_CLOSED | 409 new mutation of CLOSED session |
| FINANCE_MATCH_CONFLICT | 409 entry already actively matched or match already withdrawn |
| FINANCE_MATCH_ENTRY_INVALID | 422 wrong account/currency or entry above cutoff |
| FINANCE_RECONCILIATION_NOT_CLOSABLE | 409 difference, integrity failure, stale cutoff, changed anchor or inexact acknowledgment |
| FINANCE_CONFLICT | 409 database uniqueness/guard conflict |
| FINANCE_IDEMPOTENCY_CONFLICT | 409 changed payload with saved key |
| FINANCE_INVALID_IDEMPOTENCY_KEY | 422 application-level invalid key |
| FINANCE_RETRY_EXHAUSTED | 409 transient attempts exhausted |

Existing finance authentication/authorization codes remain unchanged. Errors retain `{error_code,details,request_id}`, with `details={}`. Read discrepancies to learn why close is blocked.

No bank feed, import, payment execution, fabricated statement lines, automatic balancing entries, amount edits, FX conversion, refund or inventory persistence. Statements are user observations, not independently verified evidence. OPEN-07 HTTP-level linked refund/inventory reversal refusal remains a **P04 follow-up** requiring real persistence; P03 offers guard-level and wiring-level evidence only. Report source scans currently cover household history without a maximum; OPEN-14 report/payload limits remain a release follow-up. Runtime credentials cannot bypass immutability; migrator access is reserved for deployment and rollback-only corruption testing.
