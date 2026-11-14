# Finance currency summary — P06 Step 4 PROPOSAL

Status: **PROPOSAL implementation** of Q1–Q8 default directions. All P06 OPEN
items remain OPEN until the separate closure decision. Let
`H = /api/v1/households/{household_id}`.

GET `H/finance/currency-summary` returns `CurrencySummaryPage`. Permission is
VIEW for OWNER, ADMIN, FINANCE_MANAGER, INVENTORY_MANAGER, MEMBER and VIEWER.
Missing authentication returns 401 `FINANCE_UNAUTHENTICATED`; an outsider or
removed member receives 404 `FINANCE_NOT_FOUND`. The existing finance error
envelope is `{error_code, details, request_id}`. Archived household/account/lot/
product history remains readable.

The thin route reuses `finance_actor`, `Principal`, `Limit`, `Cursor` and
`FinanceRoute`. `FinanceReportService` owns one REPEATABLE READ, READ ONLY
transaction covering current household READ authorization and every aggregate.
Both repositories use SELECT only and the same session. Inventory valuation
SQL is reused directly through `valuation_aggregates`, without opening a second
transaction or calling existing unbounded finance report/payment services.
Authentication's existing read precedes the report transaction. A later request
can see later commits; a cursor does not freeze data across requests.

## Query and bounds

| Parameter | Contract |
|---|---|
| `currency` | Optional Literal VND/JPY/USD/EUR/BHD; another code returns 422 `FINANCE_INVALID_INPUT` |
| `limit` | Default 50, minimum 1, maximum 200; invalid values return 422 `FINANCE_INVALID_INPUT` |
| `cursor` | Optional base64 JSON position, maximum 2048 characters, bound to household, resource and currency filter |

There are no date parameters and no timezone requirement. A valid currency with
no observed data returns `sections: []`. Sections are sorted by currency code
and paged in memory over at most five currencies. Cursor scope is
`[hid, "finance/currency-summary", {"currency": currency-or-null}]`; its position
is the last returned currency code. Malformed cursors and changed household or
filter return 422 `FINANCE_INVALID_CURSOR`. Route-level query validation,
including an overlength cursor, follows existing `FINANCE_INVALID_INPUT` mapping.

The P06 Step 4 PROPOSAL 1,000-row cap means **no repository query returns more
than 1,000 rows to Python**, not a truncation of source data. Pages fetch at
most `limit + 1` (201). Aggregate queries return one result row, including SQL
arrays of grouped facts. Identifier/issue lists contain first 100 identifiers
with complete counts. Finance inputs group items and ledger entries in SQL;
Python never scans source items, entries or lots. Account balance lists and
monthly breakdowns retain their complete existing shapes; this bound does not
cap SQL scan work, recursive ancestry depth, nested aggregate payload size or
account cardinality. Existing finance route limits are unchanged.

## Response DTOs

These are the exact fields; there is no overall or cross-currency money total.
All money fields are exact Decimal strings, never JSON numbers/floats. Nullable
lot values distinguish unknown cost from known zero cost. No conversion, rate,
rounding, minor-unit quantization or household-default currency is used.

| DTO | Fields |
|---|---|
| `CurrencySummaryPage` | `sections: list[CurrencySummarySection]`, `next_cursor: str|null`, `unknown_cost: CurrencySummaryUnknownCost`, `reconciliation: CurrencySummaryReconciliation` |
| `CurrencySummarySection` | `currency: str`, `purchase: CurrencySummaryPurchase`, `lots: CurrencySummaryLots`, `ledger_balances: list[CurrencySummaryLedgerBalance]` |
| `CurrencySummaryPurchase` | `linked_total: decimal-string`, `linked_item_count: int`, `unlinked_total: decimal-string`, `unlinked_item_count: int` |
| `CurrencySummaryLots` | `received_value`, `remaining_value`, `consumed_value`, `disposed_value`, `returned_value`, `adjusted_out_value` (each decimal-string or null) |
| `CurrencySummaryLedgerBalance` | `account_id: int`, `balance: decimal-string` |
| `CurrencySummaryUnknownCost` | `count: int`, `lot_ids: list[int]` |
| `CurrencySummaryIssue` | `lot_id: int`, `currency: str|null`, `code: TIE_OUT_MISMATCH / PURCHASE_MISMATCH / REVERSED_ORIGINAL` |
| `CurrencySummaryIssues` | `count: int`, `items: list[CurrencySummaryIssue]` |
| `CurrencySummaryReconciliation` | `currencies`, `purchase_linked_item_count`, `purchase_unlinked_item_count`, `purchase_mismatch_count`, `reversed_original_count`, `unknown_cost_count`, `tie_out_mismatch_count` (integers), `issues: CurrencySummaryIssues` |

## Source and reconciliation semantics

A currency is observed in POSTED EXPENSE items, lot cost (or the linked purchase
currency of an unknown-cost lot), or account-matching ledger entries. Unpriced
GIFT/MANUAL lots with no currency do not invent a currency section.

Purchase sums use only items of `kind='EXPENSE'`, `status='POSTED'` transactions,
grouped by transaction `currency_code`. DRAFT and REVERSAL transactions are
excluded from these sums. LINKED means at least one household lot references
the item's ID, using EXISTS so split receipts count/sum the item exactly once.
UNLINKED includes finance-only items and product-annotated items with no receipt.
They remain explicit, never silently disappear. Both totals sum exact
`net_amount`; no values are inferred from lot costs.

The six lot values reuse the valuation aggregate and its recursive correction
attribution. All six are null for a currency without any known-cost lot, and
exact sums (including known zero) otherwise. Unknown-cost lots contribute no
money. `unknown_cost` is global even with a currency filter: complete count and
first 100 lot IDs ascending, without quantity/value fields in this DTO. Detailed
unknown quantities remain available in valuation. Other reconciliation facts
cover the selected currency scope, before pagination. `currencies` counts that
full selected scope, not only the current page.

Balances use `sum(signed_amount)` over entries matching household, account ID
**and the account's currency**, the same filter as finance integrity. An account
with no entries is omitted; an account whose entries net to zero remains with
zero balance. Reversal ledger entries are included normally. Archived accounts
are included, ordered by account ID. Balances are not combined across accounts
or currencies.

A POSTED EXPENSE original with a POSTED REVERSAL child is flagged using valuation's
EXISTS definition. Its purchase amount remains in EXPENSE totals and its lots
keep their values. Reversal is a report issue, never an exclusion or a new
permission to reverse stock-linked transactions. `reversed_original_count`,
`purchase_mismatch_count` and `tie_out_mismatch_count` count affected lots, as
in the shared valuation aggregate (not distinct transaction headers).

Issues are complete-count plus first 100, ordered by lot ID and then tie-out,
purchase mismatch, reversed original. Their currency is lot cost currency,
otherwise linked purchase currency, otherwise null. Quantity/value tie-out and
purchase comparisons are exactly valuation's: received = remaining + consumed
+ disposed + returned + adjusted-out; purchase received value and currency must
match the full linked item. Split-lot comparisons do not allocate item amounts.
Reads return 200 with issues and never repair retained records.

## Worked two-currency acceptance fixture

`test_currency_summary_two_currencies_no_combined_total` extends plan §5.
L1/L2/L3 retain their exact VND fixture values. Add a USD PURCHASE lot of 3 kg at
5 USD/kg, consume 1 and dispose 1: remaining 1 kg. Add VND finance-only expense
30000 and a product-annotated unreceived expense 10000. Both are POSTED, unlinked.
A USD DRAFT expense is excluded. Payments settle the VND 200000 and 30000 and
the USD 15; USD income 2 contributes only to the ledger. Another USD account has
an income 4 and its full reversal, nets to zero, and is archived. A BHD account
without entries is omitted.

| Currency | Linked total/count | Unlinked total/count | Received | Remaining | Consumed | Disposed | Returned | Adjusted out | Account balances |
|---|---|---|---|---|---|---|---|---|---|---|
| USD | 15 / 1 | 0 / 0 | 15 | 5 | 5 | 5 | 0 | 0 | -13; archived account 0 |
| VND | 200000 / 1 | 40000 / 2 | 260000 | 130000 | 80000 | 50000 | 0 | 0 | -230000 |

Unknown cost: L2 only, count 1. Reconciliation: currencies 2, linked items 2,
unlinked items 2, purchase mismatch 0, reversed original 0, unknown cost 1,
tie-out mismatch 0, issues count 0. No money is combined across these rows.
Verification status and actual timings are recorded in
[Step 4 worker evidence](../../.project/p0601-step4-coder-evidence.md).
