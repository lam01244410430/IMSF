# Draft REST API contracts
Use /api/v1. Resolve explicit household context and enforce membership and permission. Generate OpenAPI from Pydantic DTOs. Proposed list contract uses bounded cursor pagination and stable ordering. Encode amounts and quantities as decimal strings.

| Route groups | Draft methods and contracts |
|---|---|
| /auth | POST registration, login, refresh, logout, password changes and recovery. Accept credential DTOs and return session DTOs or 204. Rate limit public operations. |
| /users /households /household-members | GET current user and households. POST creation and invitations. PATCH/DELETE membership with permission. Return user, household, or member DTOs. |
| /accounts /transactions /transaction-items /ledger | GET resources. POST account, transaction, or reversal. Accept items, payments, and an idempotency key for posting. Return transaction ID and status. Ledger queries are read-only. |
| /products /inventory /inventory-lots /inventory-movements | GET products, stock, lots, and movements. POST/PATCH products and POST explicit adjustments. Return product or stock DTOs. |
| /consumption /disposals /expiration-alerts | POST quantity, unit, reason, and idempotency key and return movement summaries. GET history and alerts. |
| /recipes /recipe-recommendations | GET recipes and recommendations. POST/PATCH recipes. Return recipe and ingredient availability details. |
| /analytics /notifications /system | GET reports, notifications, and health. PATCH notification state. Expose only minimal health status publicly. |

Use 200/201/204 on success. Error fields are error_code, details, and request_id. Use 401 for invalid authentication, 403 for insufficient permission, 404 for invisible objects, 409 for state or idempotency conflicts, 422 for invalid input, and 429 for rate limits. Clients localize stable error codes. Endpoint fields and permission matrices await phase review.

## P06-01 Step 2 (PROPOSAL implementation)

GET household `/inventory/valuation` and `/inventory/valuation/{lot_id}` use
existing all-six-role VIEW authorization and a REPEATABLE READ, READ ONLY
report transaction. See [the valuation contract](../docs/api/inventory-reports.md).
Rows tie out fixed lot cost against net movement quantities; totals group only
observed known-cost currencies. Unknown-cost lots expose quantities and null
values, never estimates. Purchase mismatches/reversed originals return issues
with 200. Archived rows remain visible. No finance writer/contract, migration,
waste report, currency-summary route, P07 or P08 work is included. New report
limits beyond reused list bounds remain Step 4 proposals.

## P06-01 Step 3 waste (PROPOSAL implementation)

GET household `/inventory/waste-report` adds all-six-role VIEW waste sections,
reason/month breakdowns, paginated product rows, explicit received-value
denominators/rates, unknown-cost quantities and nonblocking reconciliation.
See [the waste contract](../docs/api/inventory-reports.md#waste-report--p06-01-step-3-proposal).
Always require shared household timezone validation, even without dates; scoped
product 404 precedes it. Dates select root occurred_at and lot received_at;
corrections stay with their original reason/month. Reason leaves the known-cost
denominator intact and narrows unknown by_reason only. Reuse precision 80 and
one REPEATABLE READ, READ ONLY transaction. No stock/finance/history writes.

P06-OPEN-02/09/10 defaults join Step 2 defaults as PROPOSALS; all OPEN items stay
open through closure. Currency summary and 366-day/1,000-row caps remain Step 4.
Waste adds uncapped root-event result materialization to the carried full-lot
totals scan; output pagination does not bound work. Existing finance limits,
identity/settings/roles, P05 OPEN-09 UNRESOLVED and other carried decisions stay
unchanged.
