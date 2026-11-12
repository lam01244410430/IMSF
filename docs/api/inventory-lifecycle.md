# Inventory lifecycle reads — P05-01 Step 2

All new P05 contracts and policies below are **PROPOSALS**, implemented for merge review under the approved Step 2 scope. Passing tests do not decide OPEN items. P04 inventory writers, terminal states, FEFO ordering and the confirmed role matrix remain authoritative.

With `H = /api/v1/households/{household_id}`, Step 2 adds:

| Method/path | Response | Access |
|---|---|---|
| GET H/inventory/lifecycle | LifecyclePage | VIEW: OWNER, ADMIN, FINANCE_MANAGER, INVENTORY_MANAGER, MEMBER, VIEWER |
| GET H/expiration-alerts | ExpirationAlertPage | Same VIEW roles |
| GET H/expiration-alerts/{alert_id} | ExpirationAlertResponse | Same VIEW roles |

Each read revalidates ACTIVE user, live Bearer session and current membership through the existing household-access adapter. Archived households remain readable. Invisible household/path/filter/cursor IDs return 404 `INVENTORY_NOT_FOUND`. Step 2 introduces no write permission or expiry-run endpoint.

## Lifecycle evaluation

**PROPOSAL OPEN-01/07:** `days_left = expires_on - local_date`. More than three days is FRESH, zero through three is WARNING, negative is EXPIRED, and an undated lot is UNKNOWN with null days_left. These are derived on each read, never stored on lots. Each request samples the UTC clock once, converts to the explicitly configured household IANA timezone and shares that local date across all returned lots.

Missing, empty, non-string or invalid `household_settings.values["timezone"]` returns 422 `INVENTORY_TIMEZONE_REQUIRED`. There is no UTC, host, browser or settings-default fallback and no settings mutation. Household authorization and referenced-object scope checks precede this error.

`LifecyclePage` contains `items`, `next_cursor`, `local_date`, `timezone`. Each item contains lot_id, household_id, product_id, received_at, exact decimal-string received_quantity/remaining_quantity, expires_on, lot_archived_at, product_archived_at, household_archived_at, activity_state (ACTIVE for positive quantity, TERMINAL otherwise), the retained terminal_state, freshness, days_left, local_date and timezone. CONSUMED/DISCARDED/RETURNED/ADJUSTED_OUT/MIXED labels are never replaced by calendar freshness. Terminal and archived rows remain visible.

Optional filters: positive BIGINT product_id/lot_id and freshness (FRESH/WARNING/EXPIRED/UNKNOWN). A lot/product filter mismatch returns 404. The freshness predicate is applied before SQL LIMIT. Pages ascend by lot ID, default to 50 and accept 1–200. Cursors bind household, filters and evaluation date/timezone. Foreign scope/position returns 404, mismatched filters or malformed cursor returns 422 `INVENTORY_INVALID_INPUT`, and a stale date/timezone returns 409 `INVENTORY_STATE_CONFLICT`. Restart pagination after a conflict. Cursors describe live reads, not a frozen stock snapshot.

**PROPOSAL OPEN-01/03:** only positive, dated, nonterminal, unarchived lots of unarchived products in active households qualify for future NEW alerts. The pure eligibility predicate records this contract; Step 2 has no producer and creates no alerts automatically.

## Historical alerts

**PROPOSAL OPEN-02/03/07:** pages contain `items` and `next_cursor`, ascending by alert ID, default 50, maximum 200. Optional filters are scoped lot_id, kind (WARNING/EXPIRED), inclusive local_date_from/local_date_to. An inverted range returns 422. Cursors bind household and filters. Detail and list responses expose only id, household_id, lot_id, alert_kind, local_date, created_at, expires_on_snapshot, timezone and job_id. Job IDs are provenance, not authorization to a job administration API. There is no lease token, internal payload, checkpoint, exception or credential in a response.

Historical reads do not require a currently valid timezone: observed date, expiry and timezone are immutable provenance. Later expiry edits, consumption, disposal, archive or timezone changes do not rewrite alerts. Standing household records are the proposed in-app data contract only; there is no email, recipient inbox, read state or frontend notification center in Step 2.

## Persistence and downgrade

**PROPOSAL OPEN-02/10:** revision 8 follows revision 7. Alerts have scoped lot/job composite RESTRICT foreign keys and unique `(household_id,lot_id,alert_kind,local_date)`. Runtime SELECT/INSERT only, with database UPDATE/DELETE/TRUNCATE history guards. Job scope/key/kind/original run_after/payload/created_at are immutable. Column-scoped updates permit only state, attempt_count, lease_until, lease_token, completed_at, error_code, checkpoint and result. DELETE/TRUNCATE are prohibited. No cascade removes history.

Downgrade locks both new relations in ACCESS EXCLUSIVE mode before checking history. Any job or alert (including terminal work) refuses with SQLSTATE 55000. The transaction leaves schema, rows and grants intact. Empty-only downgrade drops revision-8 objects and the additive expiry index, retaining every revision-7 row. Owner-controlled function metadata records source SELECT grants added by revision 8; downgrade removes only these additions and preserves pre-existing worker read grants. Revisions 1–7 are frozen.

**PROPOSAL OPEN-04/05/08, DDL only:** job_key is an opaque nonempty string of at most 200 characters, scoped uniquely to a household. Kind is INVENTORY_EXPIRY. The four stored states are READY/RUNNING/SUCCEEDED/FAILED, attempt_count is nonnegative, RUNNING requires paired nonempty lease_token/lease_until, other states have neither; terminal states require completed_at. New rows start READY with zero attempts and empty versioned progress/result. Terminal outcomes are immutable. These storage guards do not implement claim or lease fencing.

Payload, checkpoint and result are JSONB objects, at most 4096 UTF-8 bytes each with numeric `schema_version: 1`. Payload requires exactly local_date (valid ISO calendar date) and timezone (validated timezone name). Checkpoint allows optional nonnegative BIGINT high_water_id/last_lot_id. Result allows optional nonnegative BIGINT scanned_count/warning_count/expired_count and a bounded uppercase outcome_code; no outcome-code meaning is selected yet. Unknown keys are rejected. Error codes and lease tokens have bounded storage. This server-owned payload has no public input route.

Deferred by name to Step 3: OPEN-04 daily job-key generation, dispatcher cadence, explicit enqueue timing/current-day scheduling; OPEN-05 claim/reclaim and SKIP LOCKED protocol, lease duration/renewal, token/time fencing of effects, attempt budget, retry delays/classification, terminal failure recovery; OPEN-08 batch size, source high-water capture, observation/snapshot semantics, checkpoint advancement, atomic alert/checkpoint effects, late-arrival treatment and resume algorithm. OPEN-06 date drift, same-day rescan/backfill and late-edit policy are also deferred. There is no dispatcher, enqueue, executor, second stock writer or history cleanup.

## Privilege provisioning remains open

**PROPOSAL OPEN-10:** migration requires explicit existing `FINANCE_RUNTIME_ROLE` and distinct `INVENTORY_EXPIRY_WORKER_ROLE`. Both must be unprivileged, separate from migration ownership, with no public schema CREATE. The worker must have no role memberships (including NOINHERIT SET ROLE paths) or effective table/column write privileges on any existing business relation; preflight refuses such configuration before DDL. No production credentials are created.

Migration grants SELECT/INSERT and sequence USAGE/SELECT on new relations, controlled job UPDATE columns to both roles, and household/settings/product/lot SELECT to the worker. Validation functions have PUBLIC execution revoked and only the required roles receive EXECUTE. Household SELECT alone does not grant FOR UPDATE. Exact operator provisioning, the restricted household-lock helper, worker invocation, system context/logging and failed-job recovery remain OPEN-10 for Step 3 review. No worker may run with these unfinished execution contracts.

Disposable verification uses the existing p02_test_* / p03_finance_test_* guarded fixtures, separate migrator/runtime credentials, and explicit INVENTORY_EXPIRY_WORKER_DATABASE_URL for the actual worker-credential grant probe on that same disposable finance DB. Revision-8 rehearsals require a separate fresh p05_rehearsal_test_* database with EXPIRY_REHEARSAL_DATABASE_URL and matching P05_REHEARSAL_DATABASE. Source-schema USAGE is an operator prerequisite for the configured roles. No history DELETE cleanup or development/production database is used. Remote CI is not established by local tests.
