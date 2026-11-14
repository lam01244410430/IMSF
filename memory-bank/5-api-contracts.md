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
waste report, currency-summary route, P07 or P08 work is included. Report
limits beyond reused list bounds were Step 4 proposals, delivered in Step 4
(see below). (Step 5 correction F-1: this sentence previously still said they
"remain Step 4 proposals".)

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
open through closure. Currency summary and 366-day/1,000-row caps were Step 4
work, delivered in Step 4 (see below). (Step 5 correction F-1: this sentence
previously still said they "remain Step 4".)
Waste adds uncapped root-event result materialization to the carried full-lot
totals scan; output pagination does not bound work. Existing finance limits,
identity/settings/roles, P05 OPEN-09 UNRESOLVED and other carried decisions stay
unchanged.

## P06 Step 4 PROPOSAL — currency summary and report maximums

GET household `/finance/currency-summary` adds `CurrencySummaryPage`, all-six-role
VIEW, optional seeded-code `currency`, default 50/max 200 and scoped currency
cursor pages. No dates/timezone requirement. Exact Decimal purchase linked/
unlinked totals, six nullable lot values and per-account same-currency ledger
balances stay in observed-currency sections; no combined total or conversion.
Global unknown-cost IDs/counts and nonblocking valuation issues are explicit.
See [the exact contract](../docs/api/finance-currency-summary.md).

This supersedes Step 2/3's historical bounds deferrals: waste-only date spans
are capped at 366 days (367 rejects INVENTORY_INVALID_INPUT), and report
repositories return at most 1,000 rows/query to Python (pages at most 201,
aggregates one row, identifier lists first 100 plus complete counts). Valuation/
waste full-scope SQL aggregates replace unbounded Python source scans. One
REPEATABLE READ, READ ONLY transaction remains authoritative per request.
Existing finance ledger/balance/integrity/payments/reconciliation contracts,
limits and dates remain unchanged. All P06 OPEN decisions remain OPEN.

## P06 Step 5 closure review (PROPOSAL, docs only)

Step 5 changes no production code, test, migration, route or DTO. It reviews
Steps 2–4, corrects stale Step-4-deferral wording in the API docs and this file
(finding F-1, see [inventory-reports.md](../docs/api/inventory-reports.md#closure-review--p06-step-5)),
and records closure verdicts (a)–(h) for Lam's separate closure decision.
OpenAPI regenerated from the app: 77 paths / 118 schemas at P05-01 closure →
81 / 149 at Step 5 (exactly the four new GETs and 31 new schemas; nothing
existing changed or removed; identical to the Step 4 new spec). Migration head
stays `000000000008`. Full suite re-run on a fresh disposable DB — see
[Step 5 evidence](../.project/p0601-step5-coder-evidence.md); the live floor is
1210 passed (the plan §6 "1157" figure is the P05-01 floor, not the P06 floor).
Carried P3 dispositions: Step 2 P3-1 → P06-OPEN-01 closure decision; Step 2 P3-3
→ P06-OPEN-06; Step 3 P3-2 → closure (accept per-root absolute waste or decide
signed-net/correction-writer policy); Step 3 P3-3 → DDL-enforced NOT NULL,
defensive handling separate; Step 4 reviewer P3-1 → closure semantics for
global unknown_cost under a currency filter; P3-2 → confirm the summary
unknown_cost shape at closure; P3-3 → recommended disposition is documenting
the shared-aggregate contract (follow-up cleanup vs documented summary-only
use). P07 receives per-lot valuation + waste facts (read-only); P08/P09 receive
stable report DTOs and the maximums as implemented (PROPOSAL; P06-OPEN-07 still OPEN) as hardening input. P06-OPEN-01..10
remain OPEN; P06-01 is not closed or delivered by this step.
