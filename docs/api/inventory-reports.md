# Inventory reports — P06-01 Steps 2–3

Status: **PROPOSAL implementation**, authorized for Step 2 on 2026-11-13.
Lam approved implementing the plan's Q1–Q8 default direction. P06-OPEN-01
through P06-OPEN-10 remain OPEN until P06 closure; passing tests do not decide
a policy gate. This document covers valuation and the additive Step 3 waste proposal.

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
The Step 4 scan/row-cap and wider report-bounds work remains deferred; there
is currently no cap on the number of matching lots read to derive totals.
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
summary and wider report maximums remain Step 4 work. All carried P05/P04/P03/P02 decisions, the
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

**Step 4 inputs (P06-OPEN-07 / carried scan P3):** the proposed 366-day cap and
1,000-row report cap are explicitly deferred. Matching-lot totals/denominator
still read all matching lots as in Step 2. Waste additionally materializes
nonzero per-root disposal/consumption event rows, rather than only one row per
lot: this is a **new uncapped event-result scan/materialization** beyond Step 2's
lot-result scan (Step 2 already traverses movements). Output pagination does not
bound either scan, correction-chain work or monthly buckets. Step 4 must include
this input in its bounds design; existing finance contract limits are unchanged.

The section-5 fixture is 3 kg / 50000 VND: EXPIRED 1 / 20000, SPOILED 2 / 30000,
November 2026 bucket 3 / 50000, denominator 260000, rate `50000 / 260000` at
precision 80. Unknown L2 contributes consumed 5 and disposed 0, never money.
All three breakdowns tie out and reconciliation is TIED_OUT with no issues.
See [Step 3 evidence](../../.project/p0601-step3-coder-evidence.md).
