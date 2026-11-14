# PostgreSQL V1 schema specification

Status is proposed for Phase 01 review. The target is PostgreSQL 16+ with async SQLAlchemy and Alembic in the existing modular monolith. This specification expands ADR-0002 through ADR-0006 and ADR-0008. The [core ERD](../diagrams/database-erd.mmd) is an orientation diagram. The contracts below are the migration design reference.

## Storage and ownership

- Use generated BIGINT identity primary keys unless a key is explicitly defined. All columns listed below are required unless marked optional. Use TIMESTAMPTZ for instants, DATE for calendar dates, and TEXT with checks for finite code sets. Store event instants with server defaults. Use JSONB for audit details, job arguments and saved response bodies.
- Scoped rows have a required household_id referencing households. Each scoped identity table exposes UNIQUE (household_id, id). Every scoped relationship uses both columns in its FK, including optional references. Optional references keep household_id required and allow only the target ID to be null. Use restrictive deletes and explicit archival for objects with history.
- Use NUMERIC(20,6) for amounts and base quantities and NUMERIC(30,12) for rates and unit costs. Reject non-finite values, overflow and input with unsupported fractional digits before SQL coercion. Currency metadata determines accepted monetary scale. Reject zero for signed events. Serialize decimals as strings.
- Use application authorization on every scoped read and write. Resolve IDs within the authorized household. Historical actor references use retained membership IDs. Use distinct migration and runtime credentials. Grant ledger, movement and audit inserts and reads without update or delete privileges on those relations.
- Use normalized keys for login, role and currency codes. Use the application's IANA time zone validation. Use en, vi and zh-Hans as locale codes. Archive selectable objects without losing historical joins.

## Identity and household

| Relation | Columns beyond the standard key and scope | Keys and checks |
|---|---|---|
| users | email, email_key, password_hash, locale, state, created_at, optional verified_at | Global. Unique email_key. State PENDING, ACTIVE or DISABLED. |
| households | name, created_at, optional archived_at | Global root. |
| household_settings | household_id, timezone, locale, reporting_currency, warning_days | Scope is the PK. Currency FK. Default warning_days is 3 and must be nonnegative. |
| roles | code | Global reference. Unique code. Seed OWNER, ADMIN, FINANCE_MANAGER, INVENTORY_MANAGER, MEMBER and VIEWER. |
| permissions | code | Global reference. Unique code. |
| role_permissions | role_id, permission_id | Global mapping. Composite PK and reference FKs. |
| household_members | user_id, role_id, joined_at, optional removed_at | Unique (household_id, user_id). Active membership requires removed_at IS NULL. Retain the ID on reactivation. |
| household_invitations | email_key, role_id, inviter_member_id, token_digest, expires_at, optional accepted_at, optional revoked_at | Unique digest. Acceptance and revocation are mutually exclusive. Lock and consume invitation once. |
| auth_sessions | user_id, created_at, expires_at, optional revoked_at | Global per-user session family. |
| refresh_tokens | session_id, token_digest, issued_at, expires_at, optional consumed_at | Global. Unique digest. Lock the session during rotation. Replay of a consumed token revokes its family in a committed transaction. |
| auth_challenges | user_id, purpose, token_digest, expires_at, optional consumed_at | Global. Unique digest. Purpose VERIFY_EMAIL or RESET_PASSWORD. Consume atomically and revoke sessions on password reset. |
| audit_logs | event_at, request_id, action, target_type, optional target_id, optional actor_member_id, details | Scoped append-only audit. Null actor denotes a system action. Target descriptors are historical data and are never resolved as authorization. |
| auth_audit_events | event_at, request_id, event_code, optional user_id | Global security events. Store neither credentials nor token material. |

Serialize ownership changes by locking the household and require at least one active OWNER after each mutation. Lock the acting membership on sensitive writes so revocation and authorization have a consistent order.


> Identity implementation note (2026-11-09, migrations 000000000002–
> 000000000003, branch task/P02-02-password-reset, HEAD 123bdd9):
> the identity tables in this section are implemented as listed, with the
> following differences from the table above, all verified in code and
> tests. (a) household_settings is implemented as a JSONB `values` bag
> defaulting to `{}` — the structured columns timezone / locale /
> reporting_currency / warning_days (default 3) in the table above are
> superseded for identity; defaults are open decision 6. (b) The
> auth_rate_limits table is implemented but not described in this document;
> see app/identity/infrastructure/models.py and migration 000000000003.
> (c) Implemented columns not listed above: auth_sessions.csrf_digest +
> last_activity_at; refresh_tokens.successor_id + successor_ciphertext +
> grace_expires_at (grace_expires_at = consumed_at + 10 seconds, enforced
> by check ck_refresh_grace); auth_challenges.failed_attempts;
> household_invitations.emailed_at. (d) The core ERD
> (docs/diagrams/database-erd.mmd) remains an orientation diagram: it omits
> auth_sessions, auth_challenges, auth_rate_limits, auth_audit_events and
> household_invitations, and draws USERS -> REFRESH_TOKENS directly.

## Finance

| Relation | Columns beyond the standard key and scope | Keys and checks |
|---|---|---|
| currencies | code, minor_units | Global. Code PK, three uppercase letters, scale 0 through 6. Version policy before changing denominations in use. |
| accounts | name, currency_code, created_at, optional archived_at | Currency FK. Unique (household_id, id, currency_code) for currency-bound references. Opening balance is a posted entry. |
| categories | name, kind, optional archived_at | Kind INCOME or EXPENSE. Unique household, kind and name. |
| transactions | kind, status, occurred_at, currency_code, total_amount, created_by_member_id, optional category_id, optional original_transaction_id, optional posted_at | Kind INCOME, EXPENSE, TRANSFER, REFUND, REVERSAL or OPENING. Status DRAFT or POSTED. Nonnegative total. Posted timestamp required only for POSTED. Link refunds and reversals to original transaction. One posted full reversal per original via partial unique index. |
| transaction_items | transaction_id, line_no, description, quantity, net_amount, optional product_id, optional base_quantity | Unique per transaction and line_no. Positive quantities, nonnegative net. Product and base quantity must appear together. Expose unique (household_id, id, product_id) for purchase lot FK. |
| transaction_payments | transaction_id, account_id, currency_code, amount, transaction_amount, direction, settled_at, optional exchange_rate | Positive amounts. Direction IN or OUT. Composite FK includes account currency. transaction_amount is the applied amount in transaction currency. Equal currencies require identical amounts and no rate. Different currencies require a positive rate. |
| account_ledger_entries | transaction_id, account_id, currency_code, signed_amount, posted_at, optional payment_id, optional reverses_entry_id | Composite FK includes account currency. Enforce payment belongs to the same transaction, account and currency with a composite FK to its unique tuple. Unique payment when present and unique reversal target when present. |
| reconciliation_sessions | account_id, currency_code, statement_date, statement_balance, state, opened_by_member_id, optional closed_at | Currency-bound account FK. State OPEN or CLOSED. Closed state requires closed_at. |
| reconciliation_matches | session_id, account_id, ledger_entry_id, matched_at | Unique ledger entry. Include account_id in both composite FKs and expose corresponding parent unique tuples. |

Account balances are the sum of signed ledger entries by account and currency. Partial settlement is derived from the sum of applied payments. Lock the transaction and affected accounts in ascending ID order before creating payments and ledger entries. Validate line totals, direction, currency, category, transfer legs, and overpayment in the application transaction. Posted commercial fields are immutable. Transfers record two opposite account entries. Cross-currency legs retain both exact amounts and the rate used. Lock the original transaction for refunds and reversals. Cap cumulative refunds at the settled refundable amount and verify original account and currency rules. A full reversal mirrors each original entry, links it once, and is allowed only when prior refunds and stock effects can be resolved consistently. A purchase refund with a physical return records outbound movements in the same transaction. A cash-only refund records no stock movement. Closing reconciliation locks the account and session and checks the statement against the matched entry set and previously reconciled balance. Financial history is retained.

> **Finance implementation note (P03-01, delivered 2026-11-11; branch
> task/P03-01-reconciliation, HEAD 8859d05):** the finance tables in this
> section are implemented as listed, with the following differences from the
> table above, all verified in code and tests. (a) Ten relations are
> implemented, not nine: `idempotency_requests` is an additional table
> (actor_member_id, operation, request_key 1–128 visible ASCII, request_hash
> sha256 hex, response_status 200/201/204, response_body JSONB) and is not
> described in this document; see
> app/finance/infrastructure/models.py and migration 000000000004.
> (b) `transactions.kind` accepts INCOME, EXPENSE, TRANSFER, OPENING,
> REVERSAL only — REFUND is not a kind in the implemented check; REFUND
> input is rejected (OPEN-07 deferred). `transactions` adds
> `reversal_reason` (1–1000 chars, mandatory for REVERSAL) and the partial
> unique index `uq_transactions_reversal` (one POSTED full reversal per
> original). (c) `transaction_items` has no `product_id` / `base_quantity`
> columns in P03-01 (product links are P04); only transaction_id, line_no,
> description, quantity, net_amount are implemented. (d)
> `transaction_payments` adds `method_code` (nullable),
> `external_reference` (nullable, ≤ 200), `reverses_payment_id`,
> `created_at`, `created_by_member_id`; the `exchange_rate` column exists
> (NUMERIC(30,12), nullable) but check `ck_payments_same_currency`
> enforces `amount = transaction_amount AND exchange_rate IS NULL` —
> the cross-currency legs/rates in the table above are NOT implemented
> (OPEN-03 deferred). (e) `account_ledger_entries` enforces
> `signed_amount <> 0` and the partial unique indexes
> `uq_ledger_payment` and `uq_ledger_reversal` (one payment / one reversal
> target). (f) `reconciliation_sessions` adds `statement_source`
> (BANK_STATEMENT/CASH_COUNT), `statement_reference` (≤ 200),
> `previous_session_id`, `closed_by_member_id`,
> `cutoff_ledger_entry_id`, `created_at`, and the partial unique index
> `uq_reconciliation_open` (one OPEN session per account);
> `reconciliation_matches` adds `matched_by_member_id`,
> `unmatched_at`, `unmatched_by_member_id` with the partial unique index
> `uq_reconciliation_active_match` — withdrawn matches are retained, never
> deleted. (g) History protection is enforced by DB triggers, not only by
> the service: `finance_reject_history_change` (no DELETE/TRUNCATE on
> history tables, no UPDATE on the ledger), `finance_guard_posted_header` /
> `finance_guard_posted_child` (POSTED immutability),
> `finance_guard_account_currency` and `finance_guard_currency`
> (denomination immutability), `finance_guard_runtime_audit`, and the
> idempotency update/commit guards plus the reconciliation session/match
> guards. (h) Currency seed (migration 000000000004): VND(0), JPY(0),
> USD(2), EUR(2), BHD(3); no XTS row is seeded. (i) Downgrade refuses
> when financial history exists (SQLSTATE 55000) and succeeds only on an
> empty DB; see the Step 5 verification. (j) The core ERD
> (docs/diagrams/database-erd.mmd) remains an orientation diagram: it does
> not show the finance tables as implemented (nor the identity tables).
> The Finance prose above still describes cross-currency legs/rates, refund
> caps, and physical-return integration — none of that is implemented in
> P03-01 (deferred: FX OPEN-03, refunds OPEN-07, inventory P04).

## Inventory and lifecycle

| Relation | Columns beyond the standard key and scope | Keys and checks |
|---|---|---|
| measurement_units | code, dimension | Global, unique code. |
| unit_conversions | from_unit_id, to_unit_id, factor | Global, composite PK. Positive factor, distinct units, same dimension. Expose unique unit ID and dimension tuples for dimension-bound FKs. Convert only with an explicit factor or identity. |
| product_categories | name, optional archived_at | Unique household and name. |
| products | name, base_unit_id, optional category_id, optional archived_at | Global unit FK. Base unit is immutable once stock history exists. |
| inventory_lots | product_id, source_kind, received_at, received_quantity, remaining_quantity, optional purchase_item_id, optional expires_on, optional cost_currency, optional unit_cost, optional terminal_state | Source PURCHASE, GIFT or MANUAL. Purchase requires item FK including product ID. Positive receipt and 0 <= remaining <= received. Cost currency and nonnegative cost are paired. Terminal state required at zero and absent above zero. |
| inventory_movements | lot_id, kind, quantity_delta, occurred_at, optional actor_member_id, optional transaction_id, optional reason | Signed delta. RECEIPT and ADJUST_IN positive. CONSUME, DISPOSE, RETURN and ADJUST_OUT negative. One receipt per lot via partial unique index. |
| inventory_adjustments | movement_id, counted_quantity, reason | Unique movement. Nonnegative count. Adjustment event kind and delta checked against prior balance. |
| consumption_records | movement_id, optional cooking_history_id | Unique movement, scoped FKs. |
| disposal_records | movement_id, reason_code | Unique movement, scoped FK. |
| expiration_alerts | lot_id, alert_kind, local_date, created_at | Unique household, lot, alert_kind and local_date. |

Create the lot and its receipt movement atomically. Validate purchase quantity across split lots under the purchase item lock. Stock commands lock product rows in ascending ID order, then eligible lot rows, recalculate against current quantities and write events and the lot projection in the same transaction. All commands that can affect FEFO eligibility use this protocol. Require SUM(quantity_delta) = remaining_quantity in reconciliation. Enforce event-kind alignment with lifecycle details in the service and use a single write path for each command. Excess found above the lot cap uses a separately sourced lot under the proposed baseline. Corrections preserve prior events. Terminal state design proposal uses CONSUMED, DISCARDED, RETURNED, ADJUSTED_OUT or MIXED based on the recorded depletion paths when stock reaches zero. Active state is derived from positive quantity. Undated lots are eligible after dated lots in the proposed baseline and report UNKNOWN freshness. Expiry day remains eligible. Sort by expires_on NULLS LAST, received_at, id. Cost remains fixed on the lot. Waste uses DISPOSE deltas times known lot cost grouped by currency, with unknown-cost quantities reported separately.

> **Inventory implementation note (P04-01, delivered 2026-11-12; branch
> task/P04-01-closure-review, HEAD 1512cbb):** the inventory tables in this section are implemented as
> listed, with the following differences from the tables above, all
> verified in code and tests. (a) Thirteen relations are implemented in
> revision 000000000007 (down-revision 000000000006): `measurement_units`,
> `unit_conversions`, `product_categories`, `products`,
> `inventory_lots`, `inventory_movements`, `inventory_adjustments`,
> `consumption_records`, `disposal_records`, `refund_inventory_links`,
> `recipes`, `recipe_ingredients`, `recipe_cooking_history`. (b)
> `expiration_alerts` is NOT created in P04-01 (P05-owned, per
> P04-OPEN-09); the `notifications` / `scheduled_jobs` rows in the
> Recipes section are likewise not implemented in P04, and
> `idempotency_requests` in that section already exists from P03-01
> finance. (c) `refund_inventory_links` is an extension beyond
> schema-v1 (original_transaction_id, purchase_item_id, lot_id,
> created_by_member_id, created_at, reason, return_movement_id,
> original_payment_id, original_ledger_entry_id, plus an implemented
> `return_kind` column defaulting to "RETURN" that the plan did not
> list); it is append-only and unresolved — no resolution endpoint, no
> REFUND transaction. (d) `inventory_lots` adds `archived_at` (not in
> the table above); `inventory_movements` adds `recorded_at` and
> `correction_of_movement_id`; `consumption_records` adds `reason_code`.
> (e) `transaction_items` (finance) gains the paired `product_id` /
> `base_quantity` columns with the pair-presence check and UNIQUE
> (household_id, id, product_id) — this SUPERSEDES item (c) of the
> finance implementation note above, which recorded their absence in
> P03-01; the pair exists only on new or editable DRAFT items, never as
> a backfill of posted rows. (f) History protection is enforced by DB
> deferred guards, not only by the service: projection
> `SUM(quantity_delta) = remaining_quantity`, one RECEIPT per lot,
> detail cardinality by kind, purchase-link aggregate checks (a
> DRAFT-linked lot INSERT is refused with SQLSTATE 55000), and the
> append-only history guards. (g) Currency seeds are unchanged from
> P03-01; lot costs are fixed explicitly supplied base-unit costs in
> the purchase currency, or a null pair when unknown. (h) Downgrade
> refuses when inventory history exists (SQLSTATE 55000) and succeeds
> only on an empty DB; see the Step 6 verification. (i) The core ERD
> (docs/diagrams/database-erd.mmd) remains an orientation diagram: it
> does not show the inventory tables as implemented (nor the identity
> or finance tables). The Inventory prose above still describes
> expiration alerts and waste valuation — neither is implemented in
> P04-01 (deferred: alerts/jobs P05, valuation P06).

> **Inventory implementation note (P04-01, delivered 2026-11-12; branch
> task/P04-01-closure-review, HEAD 1512cbb):** the inventory tables in this section are implemented as
> listed, with the following differences from the tables above, all
> verified in code and tests. (a) Thirteen relations are implemented in
> revision 000000000007 (down-revision 000000000006): `measurement_units`,
> `unit_conversions`, `product_categories`, `products`,
> `inventory_lots`, `inventory_movements`, `inventory_adjustments`,
> `consumption_records`, `disposal_records`, `refund_inventory_links`,
> `recipes`, `recipe_ingredients`, `recipe_cooking_history`. (b)
> `expiration_alerts` is NOT created in P04-01 (P05-owned, per
> P04-OPEN-09); the `notifications` / `scheduled_jobs` rows in the
> Recipes section are likewise not implemented in P04, and
> `idempotency_requests` in that section already exists from P03-01
> finance. (c) `refund_inventory_links` is an extension beyond
> schema-v1 (original_transaction_id, purchase_item_id, lot_id,
> created_by_member_id, created_at, reason, return_movement_id,
> original_payment_id, original_ledger_entry_id, plus an implemented
> `return_kind` column defaulting to "RETURN" that the plan did not
> list); it is append-only and unresolved — no resolution endpoint, no
> REFUND transaction. (d) `inventory_lots` adds `archived_at` (not in
> the table above); `inventory_movements` adds `recorded_at` and
> `correction_of_movement_id`; `consumption_records` adds `reason_code`.
> (e) `transaction_items` (finance) gains the paired `product_id` /
> `base_quantity` columns with the pair-presence check and UNIQUE
> (household_id, id, product_id) — this SUPERSEDES item (c) of the
> finance implementation note above, which recorded their absence in
> P03-01; the pair exists only on new or editable DRAFT items, never as
> a backfill of posted rows. (f) History protection is enforced by DB
> deferred guards, not only by the service: projection
> `SUM(quantity_delta) = remaining_quantity`, one RECEIPT per lot,
> detail cardinality by kind, purchase-link aggregate checks (a
> DRAFT-linked lot INSERT is refused with SQLSTATE 55000), and the
> append-only history guards. (g) Currency seeds are unchanged from
> P03-01; lot costs are fixed explicitly supplied base-unit costs in
> the purchase currency, or a null pair when unknown. (h) Downgrade
> refuses when inventory history exists (SQLSTATE 55000) and succeeds
> only on an empty DB; see the Step 6 verification. (i) The core ERD
> (docs/diagrams/database-erd.mmd) remains an orientation diagram: it
> does not show the inventory tables as implemented (nor the identity
> or finance tables). The Inventory prose above still describes
> expiration alerts and waste valuation — neither is implemented in
> P04-01 (deferred: alerts/jobs P05, valuation P06).

## Recipes and operations

| Relation | Columns beyond the standard key and scope | Keys and checks |
|---|---|---|
| recipes | name, servings, created_by_member_id, optional instructions, optional archived_at | Positive servings. |
| recipe_ingredients | recipe_id, line_no, product_id, quantity, unit_id, essential | Unique recipe and line number. Positive quantity. Require conversion to product base unit. |
| recipe_cooking_history | recipe_id, cooked_at, servings, actor_member_id, recipe_snapshot | Positive servings. Record the executed recipe snapshot and link resulting consumption records. |
| notifications | recipient_member_id, event_key, kind, payload, created_at, optional read_at | Unique household, recipient and event_key. Include stable localization code and validated payload. |
| notification_preferences | member_id, channel, enabled | Composite PK (household_id, member_id, channel). |
| scheduled_jobs | job_key, kind, state, run_after, attempt_count, payload, optional lease_until, optional lease_token, optional completed_at, optional error_code | Unique household and job_key. State READY, RUNNING, SUCCEEDED or FAILED. RUNNING requires lease fields. Nonnegative attempts. |
| idempotency_requests | actor_member_id, operation, request_key, request_hash, response_status, response_body, created_at | Unique household, actor, operation and request_key. Store bounded keys and validated response data. |

Recipe recommendations and reports use household-scoped reads and derive results from source records. Rank according to the [algorithm draft](../../memory-bank/6-algorithms.md). Cooking with stock deduction locks and updates all affected stock in one transaction. Workers claim due jobs with row locks and SKIP LOCKED, commit a lease, and fence completion with the lease token. Expired leases are reclaimable. Write database effects with the completion update under the same job lock and use source uniqueness for deduplication. Deliveries to external channels require a provider idempotency contract before enabling retries.

## Transaction and index contracts

- Every replayable write reserves the idempotency key using INSERT ON CONFLICT and stores the final successful response in the same transaction. The in-progress row may use a transaction-local provisional response, which must never commit. On conflict, read the committed row in a fresh statement, verify the canonical request hash, and return the saved response or HTTP 409. Recheck current authorization before replay. Rollback removes both the reservation and effects.
- Checkout validates and writes finance, payment entries, purchase items, lots, receipts and audit in one application transaction. Repositories share the unit of work. Keep account locks before product locks for cross-module operations. Retry transient deadlocks or serialization failures by restarting the entire unit of work with the same key.
- Index scoped referencing columns when they lack a suitable leading index. Add transactions (household_id, occurred_at DESC, id DESC), ledger (household_id, account_id, posted_at, id), movements (household_id, lot_id, occurred_at, id), and active lots (household_id, product_id, expires_on, received_at, id) WHERE remaining_quantity > 0. Add a separate expiry scan index (household_id, expires_on, id) over positive dated lots. Index notifications by household, recipient and descending created_at/id, jobs by state/run_after and state/lease_until, and membership by user for household discovery.
- Use stable cursor tie breakers. Start with source queries and reconcile projections before adding materialized summaries. Never aggregate money across currencies without an explicit conversion policy.

## Migration and acceptance

Create revisions in dependency order. Start with shared references and identity, then finance, inventory and lifecycle, recipes, and operations. Create products before linking finance items to products, and add the optional cooking link after cooking history exists. Seed reference codes deterministically. Add stricter constraints to populated databases only after validation and auditable backfill. Rehearse upgrade on empty and populated PostgreSQL databases. For populated production data use forward corrections or a rehearsed restore when downgrades would discard history.

Required evidence includes FK rejection for cross-household writes, scoped query authorization, last-owner and refresh-token races, currency precision and bounds, ledger reconciliation and competing refunds, checkout rollback after partial writes, concurrent same-key replay and payload conflict, simultaneous FEFO deductions, expiry and time zone boundaries, job fencing, and waste reconciliation. Run against real PostgreSQL under the runtime role. Verify deployment compatibility and backup recovery before release.

Proposed mixed depletion, undated stock, and adjustment handling require Phase 04–05 review. The [open decisions](../../memory-bank/15-open-questions.md) remain policy gates for retention, authentication, currency rounding and rates, valuation, and recipe substitutions. Transport, provider selection, and retention values are configurable policy decisions. No PostgreSQL migration or runtime acceptance evidence exists for this design revision.


## P05 lifecycle implementation note

Revision 8 (down-revision 000000000007) adds immutable scoped
expiration_alerts with observed expiry/timezone/job provenance and
scheduled_jobs storage with frozen scheduling payload, controlled
state/progress columns and versioned bounded JSONB. Both preserve history
with database guards; empty-only downgrade locks new relations before
refusing SQLSTATE 55000 on any retained row. Existing revision-7 FEFO
indexing remains; a separate household/date expiry scan index covers
positive dated lots. New role provisioning fails closed for explicit
separate runtime/worker roles; exact production provisioning remains open
(OPEN-10). Revisions 1–7 remain unchanged; revision 8 is frozen
(SHA256 d06bce727db50a5ef6a602580897335e674b64e2e828d619bffb43d3b27671ca,
verified 8/8 vs 9d81253 at the Step 5 closure review).

Step 2 (commit f595e26) adds the lifecycle/alert read paths and the
revision-8 persistence above: three VIEW reads (lifecycle list,
expiration-alert list/detail), one local date per request from the
household's configured IANA timezone (missing/invalid → 422
INVENTORY_TIMEZONE_REQUIRED, no fallback), freshness derived per read
(three-day WARNING threshold, UNKNOWN for undated lots — PROPOSAL
OPEN-01), and alert/job storage with the frozen DDL choices (PROPOSAL
OPEN-02/04/05/08, DDL only). No producer, backfill, claim/fencing
implementation, stock writer, recipient inbox or email is added in
Step 2.

Step 3 (commit 6eb9bbb) adds the expiry-job execution protocol and the
standing in-app alert records (PROPOSALS OPEN-03/04/05/06/07/08): a
bounded dispatcher enqueuing one canonical household/local-day job
(`inventory-expiry:v1:{local_date}`), jobs-only SKIP LOCKED claims with
a fresh random lease token, household-first fenced effect batches of at
most 100 lots with checkpoint/high-water resume, INSERT ON CONFLICT
deduplication on the alert natural key, three claims total with
lease-based retry delays, explicit stale/archived skip outcomes, and no
backfill or completed-day rerun. The enqueue/status routes (POST
expiry-runs → 202, GET expiry-runs/{job_id}) reuse the existing
idempotency/replay protocol; the persisted success status is encoded as
200 internally (frozen revision 4 permits 200/201/204 only) and mapped
to HTTP 202 — a literal stored 202 would require a separately approved
migration. A job never deducts, disposes, returns, adjusts or archives
stock, never writes finance/movement/cooking rows, and never deletes
history; it only reads inventory and writes alert/job records.

Step 4 (commit 9d81253) integrates lifecycle state into the existing lot
GETs and the lifecycle presentation (PROPOSALS OPEN-01/03/07): GET
inventory-lots returns LotReadPage and GET inventory-lots/{lot_id}
returns LotReadResponse, each with REQUIRED freshness/days_left/
local_date/timezone from the shared domain function; every
LifecycleResponse carries required standing_alerts (at most 5 latest
summaries per lot, by alert ID descending; the bound of 5 is a PROPOSAL).
Reads perform no stock, finance, history or operational writes, even
across household midnight. The two exact partial-deduction examples are
proven: consume 2 of 5 then dispose 1 then dispose 2 leaves 3/2/0 with
terminal MIXED, and a FEFO demand of 4 splits -2/-2 across two lots
while a demand of 6 fails whole with zero effects. FEFO ordering,
yesterday exclusion and expiry-day eligibility are unchanged.
OPEN-09 is UNRESOLVED: the explicit-lot route has no date filter and
keeps its current behavior, including MEMBER consumption of expired
stock; FEFO/cooking already exclude yesterday, and
partial-fulfillment success would be new behavior, not required by
partial-deduction acceptance.

Step 5 (commit 2e24a7d) is compatibility,
documentation and closure review only: no production code, test or
migration change. Full suite 1157 passed on a fresh
disposable DB; targeted P05 files 343 passed;
health 200/200; OpenAPI unchanged vs 9d81253 (77 paths / 118 schemas);
migration rehearsals 15/15 PASS (populated rev-7 upgrade preserves all
rows; downgrade refuses 55000 with history; empty downgrade preserves
rev-7 history). Known host limitation: the full-suite pytest process
does not exit cleanly on the 1 GB EC2 host (printed summary is the
evidence; process exit -15 after a documented SIGTERM following the
complete summary — seventh occurrence, zero test failures in any of them).

Still open after P05-01 (see .project/open-decisions.md at closure):
OPEN-01 freshness threshold/kinds and alert eligibility; OPEN-02
revision-8 persistence base as a decided policy (implemented as a
PROPOSAL); OPEN-03 notification delivery (inbox/read state/email);
OPEN-04 scheduling/cadence; OPEN-05 claim/fence/retry budgets;
OPEN-06 late edits, same-day rescan and backfill; OPEN-07 route/DTO
surface; OPEN-08 work bounds and source snapshot; OPEN-09 explicit-lot
expired consumption (UNRESOLVED); OPEN-10 worker provisioning and the
restricted household-lock helper; carried P3-2 (lots min_length),
P04-OPEN-11 resolution policy, P04-OPEN-16 archived-account
reconciliation, report/payload limits, and the P02 identity/deployment
follow-ups. P06 receives immutable lot costs/currency, movements/
disposals and unknown-cost facts for its valuation/denominator
decisions. P07 receives freshness/local-date/FEFO eligibility and the
retained consumption/cooking contracts for its matching/ranking/
substitution decisions. P08 receives stable localization codes and
read DTOs for later UI, without assuming email or an implemented
notification center.

## P06-01 Step 2 valuation implementation note (PROPOSAL, 2026-11-13)

Read-only valuation uses the existing lot, movement, product, transaction-item
and transaction relations at migration head `000000000008`. There is no new
relation, snapshot, migration, grant or writer. The application owns one
REPEATABLE READ, READ ONLY transaction per report request; the repository
SELECTs household-scoped rows with composite ownership joins.

Fixed lot cost times correction-netted per-kind quantities yields exact Decimal
strings. ADJUST_IN offsets adjusted-out. Unknown costs keep quantities and null
values, with explicit lot IDs; no estimate, zero substitution or FX is used.
Known values sum only within their observed currency. Archived lots/products/
households remain readable and archived lots are included by default, flagged.
Purchase mismatches and reversed originals are reported without blocking reads.
See [the valuation API proposal](../api/inventory-reports.md) for tie-out,
correction, split-receipt, pagination and unknown-cost semantics. An
underlying correction can overcompensate its source; absolute netting then
reports a tie-out issue (P3 input to P06-OPEN-01). Q1–Q8 defaults are authorized
for implementation as proposals; P06 OPEN decisions remain OPEN until closure.
All P05 and carried open items remain unchanged.

## P06-01 Step 3 waste implementation note (PROPOSAL)

The waste GET reads existing `inventory_lots`, `inventory_movements`,
`disposal_records` and household timezone settings at unchanged migration head
`000000000008`. No schema, grant, stored snapshot or writer is added. All reads,
authorization and settings use one REPEATABLE READ, READ ONLY report transaction.
Composite household ownership scopes every relation/join; archived data remains
readable. Recursive movement attribution extends Step 2 with the root ID and
root occurred_at: later corrections adjust the root's reason and local month.
Known waste uses per-root absolute net DISPOSE quantity times immutable lot cost;
consumption/expiry alone never classifies waste. P05 OPEN-09 stays UNRESOLVED.

P06-OPEN-02/09/10 default (a) directions are implemented as PROPOSALS: received
known-cost value in the same date/product/currency scope is the denominator;
reason filters the numerator, not receipts. Root occurred_at and received_at
use the required household timezone and open-ended local-date boundaries.
No cost/FX is invented. Unknown-cost quantities are explicit and unpriced.
Per-root versus per-lot absolute-net discrepancies are nonblocking report issues.
See [the exact API contract](../api/inventory-reports.md#waste-report--p06-01-step-3-proposal).

P06-OPEN-07's 366-day and 1,000-row caps remain Step 4 work. (Step 5 note: this
sentence is the historical Step 3 record; the caps were delivered in Step 4 —
see the Step 4 note below.) In addition to the
carried matching-lot totals scan, waste materializes uncapped root-event rows;
by-product output pagination bounds neither scan. This is a Step 4/P3 input,
not a fix or a decided closure gate. All P06 OPEN decisions remain OPEN.

## P06-01 Step 4 currency summary + bounds implementation note (PROPOSAL)

P06 Step 4 PROPOSAL adds one VIEW GET currency summary from existing finance and
inventory relations, without schema/grant changes or a migration. Head remains
`000000000008`. One REPEATABLE READ, READ ONLY transaction includes household
READ authorization and both repositories' SELECT-only aggregates. Finance sums
POSTED EXPENSE items once using lot-link EXISTS, separates unlinked purchases,
and sums ledger entries per account and matching account currency, including
archived/zero-balance accounts with entries and reversal postings. It never
calls existing unbounded integrity/report/payments services. Inventory valuation
aggregates are reused inside the same transaction; no valuation SQL is copied.

All money stays exact NUMERIC/Decimal text, grouped by observed seeded currency,
without conversion/default currency/combined total. Unknown-cost lots retain
null values and a global complete-count/first-100-ID summary, never estimates.
Purchase mismatches and reversed originals retain amounts/lot values and report
issues. The new [summary contract](../api/finance-currency-summary.md) lists the
exact DTOs, filter/paging and worked two-currency example.

P06-OPEN-07(a) bounds are implemented as PROPOSALS: default 50/max 200, scoped
cursor pages; waste-only two-ended date ranges allow 366 days and reject 367+.
The 1,000-row cap bounds rows returned from any report repository query to
Python. SQL aggregates cover the full scope, returning one row with complete
counts/totals; page SQL returns at most limit+1 (201), identifiers first 100.
It does not truncate inputs, cap recursive DB work, or redefine nested account/
month-list contracts. Existing finance route limits/parameters/responses stay
unchanged. See [inventory bounds](../api/inventory-reports.md#bounds--p06-step-4-proposal).

Carried P3 dispositions: Step 2 P3-2 full-lot totals materialization and Step 3
P3-1 uncapped root/product-result materialization are fixed through shared SQL
aggregates and bounded page fetches, with >1000-source-row tests. Step 3 P3-2
opposite-signed overcorrected roots is preserved: per-root absolute waste still
returns HTTP 200 with TIE_OUT_MISMATCH iff
`sum(abs(net_delta))*unit_cost <> abs(sum(net_delta))*unit_cost` per lot.
Recommendation for closure: explicitly accept this report interpretation or
separately decide signed-net/correction-writer policy; do not silently alter
retained-event meaning in this bounds refactor.

Step 3 P3-3: actual frozen revision `000000000007_inventory_core.py` lines
203–213 declares disposal `reason_code TEXT NOT NULL` with the four-code CHECK;
aligned-detail guards also apply. No NULL-reason classification is added.
Recommendation for closure: rely on enforced constraints for valid data and
separately decide defensive malformed-import/integrity handling. Both P3-2 and
P3-3 remain closure inputs, not decisions made by this worker.

All P06 OPEN decisions remain OPEN through closure despite implementing defaults
01–10. P05 OPEN-09 remains UNRESOLVED. No P05/P04/P03/P02 carried policy, P01-01
label, proposed ADR-0005, identity/settings/roles, P07/P08 or existing finance
contract limit is changed. No report writer, stored snapshot, FX, invented cost,
email, production data change, commit, push, deployment or closure claim.

## P06-01 Step 5 compatibility, documentation and closure review note (PROPOSAL)

Step 5 is docs-only: no production code, test, migration, route or DTO change.
Branch `task/P06-01-closure-review` from Step 4 merge `bc5b6ed`. It reviews
Steps 2–4, corrects stale Step-4-deferral wording in the API docs and
memory-bank (finding F-1 — three sentences in
`docs/api/inventory-reports.md`, two in `memory-bank/5-api-contracts.md`, and
the pointer added to the Step 3 note above; the Step 4 bounds were already
implemented and tested, only the prose lagged), and records closure verdicts
(a)–(h) for Lam's separate closure decision. No other doc/code contradiction
was found. Full evidence: `.project/p0601-step5-coder-evidence.md`; EC2 result
`/tmp/p0601-step5-result.md`.

(a) Task-board acceptance "Reconciled lot valuation and currency grouping" is
proven as implemented (PROPOSAL) by the plan §5 fixture's exact numbers on all
three routes — valuation L1 200000 = 100000 + 80000 + 20000, L2 quantities
5 = 0 + 5 + 0 + 0 + 0 with all values null, L3 60000 = 30000 + 0 + 30000;
waste disposed 3 kg / 50000 VND (EXPIRED 1 / 20000, SPOILED 2 / 30000),
denominator 260000, rate 50000/260000 at precision 80; currency summary two
sections (VND received 260000 / ledger −230000; USD received 15 / ledger −13),
no combined total, no conversion, no float — and by the OpenAPI delta below.
The acceptance holds as a PROPOSAL: P06-OPEN-01..10 remain OPEN for Lam.

(b) P06-OPEN-01..10 are all implemented as the recommended (a) defaults and all
stay OPEN for Lam to decide at the P06 closure; implementation and passing
tests decide none of them. What each decision needs is tabulated in
`memory-bank/15-open-questions.md` (Step 5 section).

(c) Carried P3 dispositions: Step 2 P3-1 (correction overcompensation) →
OPEN-01 closure decision (write-time correction constraints vs signed nets);
Step 2 P3-3 (VIEWER/MEMBER money visibility) → OPEN-06 closure decision;
Step 3 P3-2 (overcorrected opposite-signed roots) → closure accepts per-root
absolute waste or separately decides signed-net / correction-writer policy;
Step 3 P3-3 (NULL reason_code) → DDL-enforced NOT NULL + four-code CHECK in
revision 000000000007, defensive handling is a separate decision; Step 4
reviewer P3-1 (global unknown_cost under a currency filter) → closure
semantics; Step 4 reviewer P3-2 (summary unknown_cost count+lot_ids only) →
confirm the shape at closure; Step 4 reviewer P3-3 (shared aggregate fields
dropped by the valuation DTO) → recommended disposition is documenting the
shared-aggregate contract (follow-up cleanup vs documented summary-only use),
no code change in Step 5.

(d) P05-OPEN-14 input as delivered: new-surface maximums (default 50/max 200,
scoped cursor pages, waste-only 366-day cap, 1,000-row query-result bound) and
bounded SQL-aggregate inputs for the consumed finance reads; existing finance
contract limits unchanged. P05-OPEN-14 itself remains a release input, with
P09 owning hardening.

(e) Known limitations: full-suite pytest exit -15 (post-summary interpreter
shutdown hang on the 1 GB EC2 host) is recorded plainly in every P06 step; the
Step 5 exit code, duration and any SIGTERM record are in the Step 5 evidence
file. The Step 3 coder's first full-suite attempt died at 84% with no summary
on a Codex usage-limit hit (184,773 tokens); that step's count rests on two
complete independent re-runs, not on that attempt.

(f) OpenAPI delta across P06-01, regenerated from the running app: 77 paths /
118 schemas at P05-01 closure (3d4587e) → 81 / 149 at Step 5 (identical to the
Step 4 new spec) — exactly +4 GET paths (valuation, valuation/{lot_id},
waste-report, currency-summary) and +31 schemas (9 valuation + 13 waste + 9
summary); 0 removed, 0 changed. The identity exact-route test allow-list
carries exactly the same four GETs.

(g) Migration chain: head stays `000000000008`; no P06 migration exists.
Revisions 1–8 are frozen and untouched by Steps 2–5.

(h) Handoffs: P07 receives per-lot valuation + waste facts (read-only) plus the
unchanged P05 contracts (freshness/FEFO eligibility, consumption/cooking
contracts). P08/P09 receive stable report DTOs and the maximums as implemented (PROPOSAL; P06-OPEN-07 still OPEN)
(P06-OPEN-07) as hardening input.

Verification (Step 5, fresh disposable DB): full suite **1210 passed, 1 warning
in 2402.96s (0:40:02)**, pytest exit -15 after the runner's SIGTERM 120.65s
post-summary (known host shutdown hang — the 11th occurrence counting one
final full-suite run per step; printed summary is the evidence, not an exit-0
run). OpenAPI regenerated 81 paths / 149 schemas, identical to the Step 4 new
spec. No code, test or migration change in this step.

The 1,000-row cap is emergent (page ≤ 201 + one aggregate row + first-100
identifier/issue lists), with no literal `1000` constant in code; a future
change raising the page or identifier limits must re-derive and re-test the
bound. All P06 OPEN decisions remain OPEN; P06-01 is not closed or delivered
by this step.
