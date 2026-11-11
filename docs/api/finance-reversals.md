# Finance full reversals (P03-01 Step 4)

Implemented on top of Step 3 posting and settlement. OPEN-07, OPEN-08, OPEN-11 and OPEN-14 remain **PROPOSALS**, not approved policy gates. This document describes their implemented proposal contracts. Generated OpenAPI provides the concrete DTO schemas.

All paths below are relative to `/api/v1/households/{household_id}`. Every request requires an active user, current session and current household membership. Objects outside the selected household return 404. Archived households remain readable and reject writes, including saved-success replays, with 409.

| Method and path | Permission | Success |
|---|---|---|
| POST `/transactions/{transaction_id}/reversals` | OWNER, FINANCE_MANAGER (`finance.reverse`) | 201 ReversalResponse |

ADMIN, INVENTORY_MANAGER, MEMBER and VIEWER receive 403. A missing or invisible original returns 404. A DRAFT, a REVERSAL transaction, or an already-reversed original returns 409 `FINANCE_REVERSAL_INELIGIBLE`. Only one full reversal of a POSTED INCOME, EXPENSE, TRANSFER or OPENING is supported. There is no partial-reversal command.

## Request and response

`ReversalCreate` requires only `reason`, a string of 1–1000 characters after whitespace stripping. Missing, blank or oversized reasons and unknown fields return 422 `FINANCE_INVALID_INPUT`. Clients cannot supply amounts, accounts, currencies, actor, posting time or reversal links.

`ReversalResponse` contains `original_transaction_id`, `reversal_transaction` (TransactionResponse), `payment_ids` and `ledger_entry_ids`. The ID lists identify the newly appended mirrors, in original-ID order. Amounts in the nested response remain decimal strings.

The reversal header is REVERSAL/POSTED with the original household, currency and total, `original_transaction_id`, the required `reversal_reason`, the acting member and no category/items. Both `occurred_at` and `posted_at` use the same server posting instant; the event is never backdated to the original occurrence or settlement time. The original header, items, payments and ledger rows remain unchanged. Original GET derives `is_reversed` and `reversal_transaction_id` from the unique posted reversal link.

## Exact mirrors and balances

Every original settled payment produces one new payment on the reversal transaction, preserving account, currency, amount, transaction amount and method. Direction flips IN to OUT or OUT to IN. `reverses_payment_id` identifies the original; `settled_at` is the reversal posting instant and `created_by_member_id` is the acting member. `exchange_rate` and `external_reference` are null. This is a bookkeeping correction, not a new external payment execution; the original external reference remains inspectable on the original payment through the link.

Every original ledger entry produces one new entry with the same account/currency and the exact negation of its stored signed amount. No new exchange-rate lookup, rounding or amount recomputation occurs. The new entry references the reversal transaction and the mirrored payment corresponding to its original payment, with `reverses_entry_id` set and `posted_at` equal to the reversal posting instant. A hypothetical original entry without a payment is mirrored with a null payment link; normal P03 posting always creates payment-linked entries.

After insertion, the service re-reads the reversal ledger rows from persistence. For each affected `(account_id, currency_code)`, the exact Decimal sum of original entries plus persisted mirrors must equal zero. A violation returns 409 `FINANCE_REVERSAL_INCOMPLETE` and rolls back the entire command. Balances remain derived from ledger rows; no stored balance is updated.

**OPEN-08 PROPOSAL:** a posted unpaid bill with no settled payments or entries may receive a header-only full reversal. Both returned ID lists are empty. No zero ledger row is inserted.

**OPEN-11 PROPOSAL reversal exception:** an archived account permits an otherwise eligible audited reversal, so historical financial effects can be canceled. Ordinary posting and additional settlement keep their existing archived-account rejection. An archived household still blocks the command and replays.

## Locks, idempotency and atomic failure

The application locks the original before eligibility checks and locks all affected accounts in ascending ID order, including accounts referenced by payments or ledger entries. Posting and additional settlement use the same original/account lock protocol. A racing payment either commits first and is included in the reversal, or sees the committed reversal and returns 409; no late unmirrored payment commits on the reversed original.

**OPEN-14 PROPOSAL:** `Idempotency-Key` is required, with 1–128 visible ASCII characters excluding spaces. Missing/invalid keys return 422. Durable keys are scoped by household, acting membership, HTTP method, normalized route/target and command version. The normalized reason participates in the request hash. A same-key/same-body retry returns the saved 201 response byte for byte; a changed reason with the same scoped key returns 409 `FINANCE_IDEMPOTENCY_CONFLICT`. Current user/session/member/role and household write access are checked before every replay.

Header, all mirrored payments/entries, audit and final idempotency response commit in one application-owned transaction. Any failure rolls back all effects and leaves the key reusable. The existing `_command` retries the entire transaction, including authorization and key reservation, at most three times for transient serialization/deadlock/connection failures. Exhaustion returns 409 `FINANCE_RETRY_EXHAUSTED`. SQL unique violations map to 409 `FINANCE_CONFLICT`. Different-key competing reversals serialize; only one commits. Existing partial unique indexes protect the reversal header and each original payment/entry link. No migration is introduced and revisions 4 and 5 remain unchanged.

Each successful reversal records one `FINANCE_REVERSED` audit event targeting the new transaction. It contains the acting member, reversal target ID, currency/total, `original_transaction_id` and `reversal_reason`. No existing commercial or reconciliation history is rewritten.

## Eligibility integration and deferred work

**OPEN-07 PROPOSAL:** refund creation is unsupported and P03 has no refund or inventory persistence. Under the original/account locks, Step 4 explicitly passes the available empty prior-refund link list to `require_full_reversal_eligible`. The guard rejects unresolved linked refunds (including drafts) with 409 `FINANCE_UNRESOLVED_REFUND` and allows resolved/reversed refunds. Its refusal is tested at the pure-domain and HTTP wiring levels. No HTTP-level refund/inventory link can currently be seeded. Before such persistence is introduced, its adapter must load every relevant link under these locks and enforce stock-effect eligibility consistently; this step does not claim inventory-effect enforcement against a nonexistent module.

Reconciliation tables/endpoints arrive in Step 5. New reversal entries have their own later posting time and are outstanding for a later session. Existing ledger rows remain byte-identical; Step 4 has no closed-session state to reopen or modify. FX, refund creation, inventory and partial reversals remain deferred.
