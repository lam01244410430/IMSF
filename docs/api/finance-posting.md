# Finance posting and settlement (P03-01 Step 3)

Implemented on top of retained Step 2 drafts. OPEN-05, OPEN-07, OPEN-11 and OPEN-14 remain **PROPOSALS**, not approved policy decisions. This document describes the implemented proposal contracts. Generated OpenAPI provides the concrete DTO schemas.

All paths below are relative to `/api/v1/households/{household_id}`. Every request requires an active user, current session and current household membership. Objects outside the selected household return 404. Archived households remain readable and reject finance writes with 409.

| Method and path | Permission | Success |
|---|---|---|
| POST `/transactions/{transaction_id}/post` | OWNER, FINANCE_MANAGER (`finance.post`) | 200 TransactionResponse |
| POST `/transactions/{transaction_id}/payments` | OWNER, FINANCE_MANAGER (`finance.post`) | 201 PaymentBatchResponse |
| GET `/transactions/{transaction_id}/payments` | All six roles | 200 PaymentBatchResponse |
| GET `/ledger` | All six roles | 200 LedgerPage |
| GET `/accounts/{account_id}/balance` | All six roles | 200 BalanceResponse |

ADMIN cannot post or settle. MEMBER can create and edit their own drafts, but cannot post or settle them. Posted header/item mutation continues to return **409**, consistent with Step 2. Input schema errors return 422. There are no reversal, reconciliation or refund endpoints in this step.

## Commands and amounts

`TransactionPost` requires a `payments` list, which may be empty for an unpaid INCOME/EXPENSE with a positive total. `PaymentBatchCreate` requires a nonempty `payments` list and a POSTED, non-reversed INCOME/EXPENSE. Transfer/opening settlement must finish during posting.

Each payment accepts `account_id`, `currency_code`, decimal-string `amount`, `direction` (`IN` or `OUT`), optional decimal-string `transaction_amount`, optional offset-aware `settled_at`, nullable `method_code` and nullable `external_reference` (maximum 200 characters). Omitted `transaction_amount` uses `amount`; if supplied it must equal `amount`. Omitted `settled_at` uses server posting time; explicit null is invalid. `method_code` accepts CASH, BANK_TRANSFER, CARD and OTHER. These are settled bookkeeping records with actor/time, not gateway attempts. Repeated external references are allowed and are never deduplication keys. Do not place bank credentials or card data in references; there are no PAN/account-secret fields or pending/failed gateway states. Server responses retain the reversal-payment link for the next step.

Money uses Decimal and the existing currency catalog precision; JSON input/output amounts are strings. Excess precision, nonpositive payments, any exchange-rate field, unequal amount fields, unsupported refund inputs and unknown fields are rejected. Posting requires a positive total. INCOME/EXPENSE require a nonempty item set with exact net sum equal to the total. Category references, when supplied, retain Step 2 kind and archive validation. Drafts may remain incomplete.

INCOME payments are IN; EXPENSE payments are OUT. Partial settlements derive `settled_amount` and `remaining_amount` from payment rows. Cumulative overpayment returns 409 and writes nothing. TRANSFER requires two full, opposite-direction legs against distinct accounts in the transaction currency, without items/category; derived settlement counts one leg. OPENING requires one full payment (IN for positive opening, OUT for negative opening), no items/category, and no previous ledger entry for that account. OPENING creates ledger history, never a mutable starting-balance field. Negative account balances are allowed without limits or fees. Archived accounts reject new posting and additional settlement. Reversal treatment of archived accounts is deferred to Step 4.

## Ledger and balance reads

Ledger filters are optional `account_id`, `date_from`, `date_to`, `cursor` and `limit` (default 50, range 1–200). Dates are offset-aware instants, inclusive, and refer to **ledger posting time**. Reversed ranges return 422. Ordering is descending `(posted_at, id)`. `next_cursor` is an opaque, filter/household-bound continuation; keep filters unchanged when following it. An unknown or foreign account filter returns 404.

Balance accepts optional offset-aware `as_of` (inclusive) and an opaque account/household-bound `cursor` returned by an earlier BalanceResponse. A balance cursor includes the last visible `(posted_at, id)` boundary; both filters together intersect their bounds. The sum and returned boundary are computed in one PostgreSQL statement/snapshot. An empty result returns zero and a null cursor. Ledger pagination cursors and balance boundary cursors have different scopes and are not interchangeable. Malformed or wrong-scope cursors return 422.

Both transfer legs use the same server posting instant. Later payments use their own server posting instant. `occurred_at` and optional historical `settled_at` remain business history and cannot backdate ledger/reconciliation order. No account balance or cache is stored or updated.

## Idempotency and failure behavior (OPEN-14 PROPOSAL)

Every finance POST/PATCH requires `Idempotency-Key`: 1–128 visible ASCII characters, excluding spaces. Missing/malformed keys return 422. Keys are durable and scoped by household, acting membership, HTTP method, normalized route/target and command version. Canonical hashes include the path, household, Decimal values, currency and normalized body. Successful keys have no P03 purge.

Current user/session/member/role and applicable MEMBER creator checks run before every replay. A saved success replays its saved status and body; deterministic JSON encoding also preserves response bytes. Replaying a successful draft edit after posting returns its saved draft response when current authorization still permits it; a new posted edit command returns 409. Changed payload with the same scoped key returns 409. Different keys cannot post one draft twice. A lost response after commit replays without a second effect.

Reservation, header changes, payments, ledger, audit and final key response commit together in one application-owned transaction. Deferred commit and successful-key immutability guards remain in revision 4. Failures roll back all effects and the key. Serialization/deadlock/connection failures restart the entire use case, including authorization and reservation, for at most three attempts; exhaustion returns 409 `FINANCE_RETRY_EXHAUSTED`. Each successful command records one audit event.

Finance routes return `{error_code, details, request_id}` with stable FINANCE-prefixed codes. Schema errors use `FINANCE_INVALID_INPUT`; authorization/session/state/overpayment/idempotency errors use their corresponding finance codes. Submitted values are not echoed. Existing identity response bodies and behavior are unchanged.

## Privilege correction and deferred work

Revision `000000000005_payment_append_only_grant.py`, down-revision `000000000004`, revokes runtime UPDATE on `transaction_payments`. It uses the quoted operator-provided `FINANCE_RUNTIME_ROLE`, following revision 4 provisioning. Configure that role for upgrades of existing databases; an unconfigured migration cannot identify an external runtime role. This additive privilege-only revision leaves revision 4 frozen, preserves rows, and keeps database triggers as a backstop if privileges are accidentally broadened. Its downgrade restores the revision 4 grant for disposable rehearsals. Future reconciliation migration numbering must follow this revision (the plan's proposed revision 5 is now occupied).

OPEN-07 PROPOSAL groundwork is `require_full_reversal_eligible`: a future Step 4 command must load original/refund links under its transaction locks and reject unresolved linked refunds. Refund creation remains unsupported. This pure eligibility guard does not implement reversal or inventory handling.

Still open: policy approval for all four proposals; final payload/report limits and DTO choices (including optional transaction amount/settlement time and distinct cursor scopes); refund/inventory eligibility integration in later steps; production runtime-role provisioning. FX, refunds, reversal/reconciliation endpoints, inventory, gateway integration and purge remain outside Step 3.
