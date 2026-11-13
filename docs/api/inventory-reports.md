# Inventory valuation reads — P06-01 Step 2

Status: **PROPOSAL implementation**, authorized for Step 2 on 2026-11-13.
Lam approved implementing the plan's Q1–Q8 default direction. P06-OPEN-01
through P06-OPEN-10 remain OPEN until P06 closure; passing tests do not decide
a policy gate. This document covers lot valuation only.

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

Waste reporting, the finance currency summary, date scopes and Step 4 report
maximums are subsequent steps. All carried P05/P04/P03/P02 decisions, the
P01-01 label and proposed ADR-0005 remain unchanged.
