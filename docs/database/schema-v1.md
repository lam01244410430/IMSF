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


## P05 Step 2 implementation note — PROPOSAL

Revision 8 adds immutable scoped expiration_alerts with observed expiry/timezone/job provenance and scheduled_jobs storage with frozen scheduling payload, controlled state/progress columns and versioned bounded JSONB. Both preserve history with database guards; empty-only downgrade locks new relations before refusing SQLSTATE 55000 on any retained row. Existing revision-7 FEFO indexing remains; a separate household/date expiry scan index covers positive dated lots. New role provisioning fails closed for explicit separate runtime/worker roles; exact production provisioning remains open. See [the Step 2 contract](../api/inventory-lifecycle.md) for proposed payload bounds, permissions and explicitly deferred OPEN-04/05/08 execution choices. No producer, backfill, claim/fencing implementation, stock writer, recipient inbox or email is added in Step 2. Revisions 1–7 remain unchanged.

Step 3 adds the expiry-job execution protocol and standing in-app alert records (PROPOSALS OPEN-03/04/05/06/07/08): a bounded dispatcher enqueuing one canonical household/local-day job, jobs-only SKIP LOCKED claims with fresh random lease tokens, household-first fenced effect batches of at most 100 lots with checkpoint/high-water resume, INSERT ON CONFLICT deduplication on the alert natural key, three claims total with lease-based retry delays, explicit stale/archived skip outcomes, and no backfill or completed-day rerun. A job never writes stock or finance and never deletes history.

Step 4 integrates lifecycle state into the existing lot GETs (PROPOSALS OPEN-01/03/07): LotReadPage/LotReadResponse with REQUIRED freshness/days_left/local_date/timezone, and required standing_alerts (at most 5 latest summaries per lot) on every LifecycleResponse. Reads perform no stock, finance, history or operational writes. The exact partial-deduction examples are proven (consume 2 of 5, dispose 1, dispose 2 → 3/2/0, terminal MIXED; FEFO demand 4 splits -2/-2 leaving 0/1, demand 6 fails whole with zero effects). OPEN-09 stays UNRESOLVED: the explicit-lot route has no date filter and keeps its current behavior, including MEMBER consumption of expired stock.

Step 5 (closure review, branch task/P05-01-closure-review, HEAD 9d81253) changes no production code, test or migration. Full suite 1157 passed on a fresh disposable DB; targeted P05 files 343 passed; health 200/200; OpenAPI unchanged vs 9d81253 (77 paths / 118 schemas); migration rehearsals 15/15 PASS (populated rev-7 upgrade preserves all rows; downgrade refuses 55000 with history; empty downgrade preserves rev-7 history). Revisions 1–8 SHA256-frozen vs 9d81253 (8/8 MATCH). Known host limitation: the full-suite pytest process does not exit cleanly on the 1 GB EC2 host (printed summary is the evidence; process exit -15). P05-01 becomes Delivered only when Lam accepts the closure evidence.
