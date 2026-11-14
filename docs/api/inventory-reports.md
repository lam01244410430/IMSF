# Inventory reports — P06-01 Steps 2–5

Status: **PROPOSAL implementation**, authorized for Step 2 on 2026-11-13.
Lam approved implementing the plan's Q1–Q8 default direction. P06-OPEN-01
through P06-OPEN-10 remain OPEN until P06 closure; passing tests do not decide
a policy gate. This document covers valuation, the additive Step 3 waste proposal,
P06 Step 4 PROPOSAL bounds, and the Step 5 closure review (docs only, no code
change). Step 5 corrects three stale Step-4-deferral sentences left in this file
(see Closure review, finding F-1) and records the closure verdicts (a)–(h).

Let `H = /api/v1/households/{household_id}`.

| Method/path | Response | Permission |
|---|---|---|
| GET `H/inventory/valuation` | `LotValuationPage` | VIEW, all six existing roles |
| GET `H/inventory/valuation/{lot_id}` | `LotValuationResponse` | VIEW, all six existing roles |

The controller injects the inventory report application service. The service
owns one PostgreSQL REPEATABLE READ, READ ONLY transaction, including current
household authorization, ownership checks and the report SELECT. The repository
only SELECTs. Rows, totals and reconciliation derive from the same snapshot.
A later request may see newly committed movements; pages do not pin a snapshot
across requests. No stock, cost, finance, history, audit or operational write is
performed. The existing authentication read runs before the report transaction.

## Query and visibility

The page accepts optional positive BIGINT `product_id` and `lot_id`, `currency`
(VND/JPY/USD/EUR/BHD), `archived`, `limit`, and `cursor`. A missing or
foreign-household product/lot filter returns 404. Unknown currency codes and
invalid inputs return 422 `INVENTORY_INVALID_INPUT`. Missing authentication is
401; outsiders and removed members receive 404 with the existing inventory
error envelope `{error_code, details, request_id}`.

Historical lots, products and households remain readable. Omitted `archived`
includes all lots; `false` excludes archived lots; `true` selects archived lots
only, following the existing inventory list convention. `archived_at` and
`product_archived_at` flag historical rows. Product or household archival does
not remove their lots from totals. This valuation read has no local-date filter
or freshness evaluation and requires no household timezone.

The existing list bound is reused: default 50, maximum 200; lot IDs ascend.
The cursor binds household, resource and all filters, and stores the last lot
ID. It is a position, not an authorization token. Changing household or filters
rejects the cursor with 422. Page-wide totals, unknown-cost entries and
reconciliation cover **all matching lots**, including earlier/later pages.
Since Step 4, totals/counts are computed by SQL aggregates over the full scope
and page fetches return at most 201 rows; see
[Bounds](#bounds--p06-step-4-proposal) below. (Step 5 correction F-1: this
paragraph previously still said the Step 4 scan/row-cap work "remains deferred".)
No existing finance contract limit changes.

## Proposed calculations and DTOs

Every row includes lot/product/base-unit IDs, source, receipt/expiry dates,
fixed cost/currency, terminal state, archival flags and these six quantities
and values: `received`, `remaining`, `consumed`, `disposed`, `returned`,
`adjusted_out`. Quantities use the product's base unit. All Decimal quantities,
costs and values serialize as exact strings. Computation uses precision 80,
covering storage bounds and totals without default-context rounding; no
quantization, float, estimate or currency conversion is used.

Received quantity is the lot's fixed `received_quantity`; remaining quantity
is its projection. Consumption, disposal and return are the absolute **net**
signed deltas attributed to each movement kind. Linked correction adjustments
inherit the original deduction kind, including correction chains. Ordinary
ADJUST_OUT/ADJUST_IN and corrections linked to receipts/adjustments contribute
`-sum(delta)` to adjusted-out; inbound stock therefore decreases adjusted-out
and may make it negative. Received quantity/cost is never rewritten.

For known cost, each quantity is multiplied by the fixed lot `unit_cost`.
`quantity_tied_out` and `value_tied_out` explicitly check:

`received = remaining + consumed + disposed + returned + adjusted_out`.

Existing correction commands permit overcompensating a linked deduction.
If its signed net becomes positive, absolute per-kind netting can fail this
identity even though the stock projection is correct. Such retained data
returns 200 with `TIE_OUT_MISMATCH`, not an invented balancing adjustment.
This is a P3 input for P06-OPEN-01 closure, not a change to P04 correction policy.

For a PURCHASE lot, `purchase` exposes `item_id`, `transaction_id`, `currency`,
`net_amount`, `reversed_original` and `status` (AGREEMENT, PURCHASE_MISMATCH or
UNKNOWN_COST). Known-cost received value is compared to the linked item's
full net amount and currency. There is no pro-rata allocation for split lots:
a partial lot may intentionally report PURCHASE_MISMATCH. A changed input
cost in a separate receipt fixture tests mismatches; existing lot costs remain
immutable. Mismatches and posted reversed originals are issues; the read
still returns 200 and retains lot values. Current reversal refusal rules are
unchanged. Non-purchase rows have `purchase: null`.

Unknown-cost lots (including PURCHASE with a priced finance item) have
`unknown_cost: true`, all six values null, unit cost/currency null,
`value_tied_out: null`, and quantities intact. They never acquire zero or
estimated money. Page `unknown_cost` contains a complete `count` and the first
100 ascending-lot entries with lot/product/base-unit IDs and six quantities
only. Quantities from different products or units are not combined.

`totals_by_currency` contains six summed values for each **observed known-cost
currency**. No overall money total is returned. For a nonempty scope with only
unknown costs, `totals_by_currency` is null; the explicit unknown section and
per-lot null values carry the unpriced scope. A truly empty scope returns an
empty list. An actually known zero cost remains known, with zero strings in
its observed currency section. These distinctions apply to the full matching
scope, even when the current page contains only unknown-cost rows.

`reconciliation` contains checked-lot, quantity/value tie-out, unknown-cost,
purchase-agreement, purchase-mismatch and purchase-unknown-cost counts.
`issues` contains the complete issue count and first 100 stable `{lot_id, code}`
entries, ascending by lot ID; within a lot: tie-out, purchase, reversal.
Per-lot `issues` remain available on detail reads. `reconciliation_status`
prioritizes TIE_OUT_MISMATCH, then PURCHASE_MISMATCH, then UNKNOWN_COST/TIED_OUT;
a reversal is independently flagged in `issues` and `purchase`.

## Acceptance fixture

Base unit kg, VND. L1 PURCHASE 10 at 20000, consumes 4 DAILY_USE and disposes
1 EXPIRED: received 200000 = remaining 100000 + consumed 80000 + disposed
20000 + returned 0 + adjusted-out 0. Linked item net amount 200000 agrees.
A separately received fixture at 18000 returns PURCHASE_MISMATCH and 200.

L2 GIFT 5 at unknown cost, consumes 5: quantities 5 = 0 + 5 + 0 + 0 + 0;
all six values null, terminal CONSUMED, explicit unknown-cost entry.

L3 MANUAL 4 at 15000, disposes 2 SPOILED: received 60000 = remaining 30000
+ consumed 0 + disposed 30000 + returned 0 + adjusted-out 0.

VND totals: received 260000, remaining 130000, consumed 80000, disposed 50000,
returned 0, adjusted-out 0. L2's 5 kg consumption remains unpriced.
See `tests/test_p06_01_reports.py` and the Step 2 engineering evidence.

Waste reporting and its date scope are documented below; the finance currency
summary is documented in [finance-currency-summary.md](finance-currency-summary.md)
and the wider report maximums in [Bounds](#bounds--p06-step-4-proposal) below
(both delivered as PROPOSALS in Step 4). (Step 5 correction F-1: this sentence
previously still said they "remain Step 4 work".) All carried P05/P04/P03/P02 decisions, the
P01-01 label and proposed ADR-0005 remain unchanged.

## Waste report — P06-01 Step 3 PROPOSAL

GET `H/inventory/waste-report` returns `WasteReport`, VIEW for all six existing
roles. Step 3 implements approved default directions as **PROPOSALS** under
P06-OPEN-02/09/10, carrying Step 2 defaults 01/03/04/05/06/08. All OPEN decisions
remain OPEN until P06 closure. No new writer, migration, snapshot table, cost
estimate, currency conversion, summary route or P07/P08 behavior is introduced.

Optional filters are `from_date`, `to_date` (ISO local dates), positive BIGINT
`product_id`, `reason` (EXPIRED/SPOILED/DAMAGED/OTHER), and `currency`
(VND/JPY/USD/EUR/BHD). Either or both dates may be omitted. Reversed dates give
422 `INVENTORY_INVALID_INPUT`. A missing or foreign product gives scoped 404
`INVENTORY_NOT_FOUND` **before** checking timezone. Authentication/membership
errors follow valuation. Archived lots/products/households remain included.

A configured, valid household timezone is **always required**, including
unfiltered requests, because monthly buckets need it. The report repository
SELECTs `household_settings.values`; shared `app.lifecycle.domain.household_zone`
validates it. Missing/invalid timezone gives 422 `INVENTORY_TIMEZONE_REQUIRED`
without fallback. The range is `[from_date 00:00, to_date + 1 day 00:00)` in that
zone, converted to UTC instants for comparisons. Events use the root movement's
`occurred_at`; receipts use lot `received_at`. Month buckets are local `YYYY-MM`.

Waste consists only of root DISPOSE movements linked to their recorded
`disposal_records.reason_code`. Each root's complete recursive correction chain
nets its signed deltas; event quantity is `abs(net)` and event value is that
quantity times fixed lot `unit_cost`. Corrections therefore repair the original
month/reason even if recorded later or outside the requested period. Zero-net
roots disappear. CONSUME events, including expired-lot consumption and cooking,
are never waste. P05 OPEN-09 remains UNRESOLVED.

For each observed known-cost currency, the denominator is received quantity
times unit cost summed over lots received inside the same period, with the same
product/currency filters. **Reason filters the known-cost waste numerator only;
it never filters the denominator.** A disposal in scope may therefore have no
receipt in scope. Rate is disposed value divided by that denominator, calculated
with `localcontext` precision 80, without quantization or minor-unit rounding.
Repeating ratios use the 80-digit Decimal division result. All quantities and
values serialize as strings, with insignificant fractional zeroes removed
without changing their value. No cross-currency total is returned.

The exact top-level fields are:

- `period`: `{from_date: date|null, to_date: date|null, timezone: str}`.
- `sections`: currency-ascending entries with `currency`,
  `disposed: {quantity, value}`, `by_reason`, `by_period`,
  `denominator: {basis: "total_received_value_known_cost", value,
  scope: "same period and filters"}`, and `waste_rate: str|null`.
- `by_product`: `{currency, product_id, quantity, value}` rows ordered by
  `(currency, product_id)`, containing nonzero disposal quantities only.
- `next_cursor`: continuation or null, for `by_product` only.
- `unknown_cost`: `{disposed_quantity, consumed_quantity, by_reason, lot_ids,
  count}`; quantities only, no money/value fields.
- `reconciliation`: `{status: "TIED_OUT"|"TIE_OUT_MISMATCH",
  issues: {count, items: [{lot_id, code: "TIE_OUT_MISMATCH"}]}}`.

`by_reason` has `{reason_code, quantity, value}` for nonzero disposed quantities
in EXPIRED/SPOILED/DAMAGED/OTHER order. `by_period` has `{period, quantity, value}`
for nonzero disposed months ascending. Sections exist for currencies observed
in either known-cost disposals or receipts in scope. Disposal-only currency:
denominator `"0"`, rate null. Receipt-only currency with a positive denominator:
disposed `"0"`, rate `"0"`. Rate is null exactly when denominator is zero,
including known zero cost. Empty or unknown-only scopes return `sections: []`
and `by_product: []`. Rates always appear with their denominator section.

Unknown-cost totals sum absolute net quantities per DISPOSE/CONSUME root in the
date/product/currency scope. All consumption reasons count as consumed only.
A currency filter excludes the null-cost/null-currency lots. Per the Step 3
contract, **reason narrows unknown disposed `by_reason` only**: unknown disposed
and consumed totals, contributor lot IDs/count retain all reasons. Unknown
`by_reason` entries contain `{reason_code, quantity}` only in the same fixed
order. Contributor IDs are ascending, first 100, with a complete distinct count;
only nonzero root events contribute. Unknown quantities are never estimated or
priced at zero. Cross-product quantities follow the proposed response contract;
`by_product` retains the product dimension for known-cost disposal quantities.

Reconciliation compares each lot's sum of per-root absolute disposed values to
`abs(sum(signed DISPOSE root nets)) * unit_cost` in the same date/reason scope.
The nonnegative per-lot differences also establish the comparison per currency.
Opposite-signed roots after overcorrection can differ; list affected lot IDs
ascending (first 100, complete count) and return HTTP 200 with TIE_OUT_MISMATCH.
By-reason, by-period and full by-product sums equal section disposed totals by
construction, from the same root values; no second check is added. Purchase
linkage belongs to valuation and is unnecessary for this report.

Reuse `Limit` (default 50, max 200) and `Cursor`. Cursor scope binds household,
route and all five filters (from/to/product/reason/currency); its position is the
last `(currency, product_id)`. Changed household/filters or malformed cursors
give 422 `INVENTORY_INVALID_INPUT`. Only by-product output is paginated; sections,
breakdowns, unknown cost and reconciliation cover the **complete scope** on
every page. Each request has one REPEATABLE READ, READ ONLY transaction covering
authorization, settings, ownership and report SELECTs. Snapshots do not persist
across separate page requests.

**Step 4 inputs (P06-OPEN-07 / carried scan P3) — DELIVERED in Step 4, kept here
as the historical Step 3 record:** at Step 3 the proposed 366-day cap and
1,000-row report cap were explicitly deferred. Matching-lot totals/denominator
then still read all matching lots as in Step 2. Waste additionally materialized
nonzero per-root disposal/consumption event rows, rather than only one row per
lot: this was a **new uncapped event-result scan/materialization** beyond Step 2's
lot-result scan (Step 2 already traverses movements). Output pagination did not
bound either scan, correction-chain work or monthly buckets. Step 4 delivered
the bounds design for this input (SQL aggregates + bounded page fetches; see
[Bounds](#bounds--p06-step-4-proposal)); existing finance contract limits are unchanged.
(Step 5 correction F-1: this paragraph previously still read as an open
"Step 4 must include" instruction.)

The section-5 fixture is 3 kg / 50000 VND: EXPIRED 1 / 20000, SPOILED 2 / 30000,
November 2026 bucket 3 / 50000, denominator 260000, rate `50000 / 260000` at
precision 80. Unknown L2 contributes consumed 5 and disposed 0, never money.
All three breakdowns tie out and reconciliation is TIED_OUT with no issues.
See [Step 3 evidence](../../.project/p0601-step3-coder-evidence.md).

## Bounds — P06 Step 4 PROPOSAL

This section supersedes the historical Step 2/3 deferral notes above. Valuation
and waste response fields and existing arithmetic remain unchanged. The new
[finance currency summary](finance-currency-summary.md) shares valuation SQL.

All three report pages reuse default 50 / maximum 200 (minimum 1); fetches return
at most `limit + 1` (201) rows. Waste allows a 366-day difference between both
supplied dates and rejects 367+ days with 422 `INVENTORY_INVALID_INPUT`, after
the existing reversed-date check. Either endpoint may remain open-ended.
Valuation and summary have no date parameters and no timezone requirement;
waste retains its required household timezone and local-date/month semantics.
Existing finance ledger date parameters and route limits are unchanged.

The 1,000-row cap means **no repository query returns over 1,000 rows to Python**.
It never truncates the source scope. `valuation_page_rows` fetches only ascending
lot IDs after the cursor; `valuation_aggregates` computes exact per-currency
NUMERIC sums, complete reconciliation counts and first-100 unknown/issue lists
in SQL over the full shared recursive attribution. `lot_valuation` remains the
pure-Python row helper for pages and the unchanged single-lot response.

`waste_aggregates` computes per-currency sections, denominator, reason/month
breakdowns, unknown quantities/counts and issue lists in SQL over the original
root attribution. `waste_product_rows` groups by currency/product and applies
cursor position plus SQL LIMIT. The old unbounded row methods and unused
`waste_totals`/amount helpers are removed. Each service calls the aggregate and
page method once inside its single REPEATABLE READ, READ ONLY transaction.
SQL aggregate results use text for decimal JSON fields; rate division retains
Python localcontext precision 80. Counts/totals cover all rows on every page.

This fixes Step 2 P3-2 full-lot materialization and Step 3 P3-1 uncapped event/
product-result materialization. The cap bounds repository result rows; it does
not bound database scanning/recursive work or nested month/account arrays.
No source data is discarded. The 1001-lot test proves full received value
20020000 VND, complete checked/tied counts 1001 and 201-row direct repository
fetch. The 1001-DISPOSE-root test uses 1001 kg at 20000 VND/kg: exact disposed
quantity 1001 and value **20020000**, denominator 20020000. The task's 20010000
numerator is an arithmetic typo; all 1001 one-kg roots are retained.

Step 3 P3-2 remains a closure input: overcorrected opposite-signed roots retain
per-root absolute waste and nonblocking TIE_OUT_MISMATCH. Closure should decide
whether to accept that reporting interpretation or separately constrain
correction writers/use signed nets; silently changing it would rewrite current
meaning. The per-lot SQL comparison is exactly
`sum(abs(net_delta))*unit_cost <> abs(sum(net_delta))*unit_cost`.

Step 3 P3-3 finding: revision 000000000007 declares
`disposal_records.reason_code TEXT NOT NULL` with the four-code CHECK and guards
aligned disposal details. No new NULL-reason semantics are introduced. Closure
should explicitly rely on those enforced constraints for valid data and decide
any defensive handling of malformed imports as a separate integrity policy.
All P06 OPEN items remain OPEN; this is implementation evidence only.

## Closure review — P06 Step 5 (docs only, 2026-11-14)

Step 5 changes **no production code, test, migration, route or DTO**. It reviews
Steps 2–4, corrects the docs, and records the closure verdicts (a)–(h) below for
Lam's separate closure decision. Full Step 5 evidence:
[Step 5 evidence](../../.project/p0601-step5-coder-evidence.md);
EC2 result `/tmp/p0601-step5-result.md`.

### Finding F-1 (doc staleness, fixed in this step)

Three sentences in this file still described Step 4 bounds work as deferred or
pending although Step 4 had delivered it: the valuation "Query and visibility"
paragraph, the "remain Step 4 work" sentence after the acceptance fixture, and
the waste "Step 4 inputs" paragraph (future-tense "Step 4 must include"). Each
is corrected in place above and marked "(Step 5 correction F-1)". The same
stale wording in `memory-bank/5-api-contracts.md` (Step 2 and Step 3 sections)
is corrected there, and the Step 3 note in `docs/database/schema-v1.md` gains a
pointer to the superseding Step 4 note. No code contradicted the docs: the
Step 4 SQL-aggregate bounds were already implemented and tested; only the prose
lagged. No other doc/code contradiction was found in Step 5.

### (a) Task-board acceptance — PROVEN as implemented (PROPOSAL)

"Reconciled lot valuation and currency grouping" is proven by the §5 fixture's
exact numbers on all three routes: valuation L1 200000 = 100000 + 80000 + 20000,
L2 quantities 5 = 0 + 5 + 0 + 0 + 0 with all values null, L3 60000 = 30000 + 0 +
30000; waste disposed 3 kg / 50000 VND (EXPIRED 1 / 20000, SPOILED 2 / 30000),
denominator 260000, rate 50000/260000 at precision 80; currency summary two
sections (VND received 260000 / ledger −230000; USD received 15 / ledger −13),
no combined total, no conversion, no float. OpenAPI: 77 paths / 118 schemas at
P05-01 closure → 81 / 149 at Step 5, exactly the four new GETs and 31 new
schemas, nothing existing changed or removed. The acceptance holds as a
PROPOSAL: P06-OPEN-01..10 remain OPEN for Lam (see (b)).

### (b) P06-OPEN-01..10 — all implemented as PROPOSALS, all stay OPEN for Lam

01 valuation method (a) per-lot unit_cost × deltas; 02 waste denominator (a)
same-scope received known-cost value; 03 unknown-cost (a) quantities only;
04 currency (a) observed-code grouping, no conversion; 05 reconciliation (a)
nonblocking issues, read returns 200; 06 roles (a) VIEW all six roles;
07 maximums (a) default 50/max 200, waste 366-day cap, 1,000-row query-result
bound; 08 money (a) exact Decimal strings, no rounding; 09 periods (a)
occurred_at/received_at, required household timezone, local months, open-ended
ranges allowed; 10 waste definition (a) DISPOSE-only by recorded reason code.
Each decision needs Lam's explicit confirmation at the P06 closure (or a stated
alternative (b)/(c)); implementation and passing tests decide none of them.

### (c) Carried P3 dispositions

- Step 2 P3-1 (correction overcompensation → TIE_OUT_MISMATCH): closure decision
  under P06-OPEN-01 — either constrain corrections at write time (a P04 change)
  or adopt signed nets in the report model (changes every consumer's
  consumed/disposed/adjusted_out semantics). Report stays honest (HTTP 200,
  issue listed, history preserved) either way.
- Step 2 P3-3 (VIEWER/MEMBER see per-lot money values): closure decision under
  P06-OPEN-06 — confirm all-six-role VIEW for the four report routes, or
  restrict the routes (options (b)/(c)); only route wiring would change.
- Step 3 P3-2 (overcorrected opposite-signed roots): closure decision — accept
  per-root absolute waste with nonblocking TIE_OUT_MISMATCH, or separately
  decide signed-net / correction-writer constraints. Do not silently change
  retained-event meaning.
- Step 3 P3-3 (NULL reason_code): DDL-enforced NOT NULL + four-code CHECK in
  revision 000000000007; rely on the enforced constraint for valid data.
  Defensive malformed-import/integrity handling is a separate decision, not
  part of this closure.
- Step 4 reviewer P3-1 (global unknown_cost under a currency filter): closure
  semantics — confirm the documented global-unknown_cost contract for filtered
  summaries, or align the summary with valuation/waste by filtering
  unknown_cost on summary_currency. See
  [finance-currency-summary.md](finance-currency-summary.md#closure-review--p06-step-5).
- Step 4 reviewer P3-2 (summary unknown_cost is count+lot_ids only, no
  quantities by kind): confirm the shape at closure, or add quantities by kind
  to CurrencySummaryUnknownCost (a DTO change, not a Step 5 change).
- Step 4 reviewer P3-3 (shared aggregate fields dropped by the valuation DTO):
  recommended disposition — document the shared-aggregate contract (the
  reversed_original_count / tie_out_mismatch_count fields exist for the
  currency-summary consumer; the valuation DTO intentionally does not surface
  them) while the alternative follow-up cleanup is trimming the valuation select;
  either is a post-closure follow-up, not a Step 5 code change. No response
  shape changes in this step.

### (d) P05-OPEN-14 input as delivered

Report/payload maximums for the new surfaces: default 50 / max 200, scoped
cursor pages, waste-only 366-day spans (367 rejects 422
INVENTORY_INVALID_INPUT), per-report query-result bound 1,000 rows to Python
(pages ≤ 201, aggregates one row, identifiers first 100 with complete counts).
The reports consume the existing finance reads only through bounded SQL
aggregates and never call the unbounded integrity/_report/payments paths.
Existing finance contract limits are unchanged; P05-OPEN-14 itself remains a
release input, with P09 owning hardening.

### (e) Known limitations, stated plainly

Full-suite pytest exit -15 (post-summary interpreter shutdown hang on the 1 GB
EC2 host) recurred in Step 5: **1210 passed, 1 warning in 2402.96s (0:40:02)**,
SIGTERM 120.65s after the complete summary — the 11th occurrence counting one
final full-suite run per step (7 at P05-01 plus the Step 2, Step 3 and Step 4
finals). The printed summary is the evidence, never claimed as exit 0.
The Step 3 coder's first full-suite attempt died at 84% with no summary on a
Codex usage-limit hit (184,773 tokens); the Step 3 count rests on two complete
independent re-runs, not on that attempt. Neither incident changes any number.

### (f) OpenAPI delta across P06-01

77 paths / 118 schemas (P05-01 closure, 3d4587e) → 81 / 149 (Step 5, regenerated
from the running app and verified identical to the Step 4 new spec): exactly
+4 GET paths (valuation, valuation/{lot_id}, waste-report, currency-summary)
and +31 schemas (9 valuation + 13 waste + 9 summary); 0 removed, 0 changed.
The identity exact-route test allow-list carries exactly the same four GETs.

### (g) Migration chain

Head stays `000000000008`; no P06 migration exists. Revisions 1–8 are frozen
and untouched by Steps 2–5.

### (h) Handoffs

P07 receives per-lot valuation + waste facts (read-only) plus the unchanged P05
contracts (freshness/FEFO eligibility, consumption/cooking contracts). P08/P09
receive stable report DTOs and the maximums as implemented (PROPOSAL; P06-OPEN-07 still OPEN) as hardening
input. P08 receives no frontend; P09 hardening itself is not done here.

### The 1,000-row cap, pinned (Step 4 reviewer observation O-1)

The cap has no literal `1000` constant in code: it is emergent from page fetch
≤ 201 + one aggregate row + first-100 identifier/issue lists per report query
(≈402 worst-case Python-visible rows for valuation/waste, ≈202 for the
summary). A future change raising the page or identifier limits could silently
breach it. Any such change must re-derive and re-test the bound; a named
constant is a post-closure follow-up, not a Step 5 change.
