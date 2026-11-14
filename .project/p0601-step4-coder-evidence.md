# P06-01 Step 4 worker evidence — 2026-11-14

Branch `task/P06-01-currency-summary`, base/HEAD `5deea4f`. Initial clean tree,
branch, HEAD and plan MD5 `b7fb975eadd475a61507e487810b4a23` verified. Required
plan sections, Step 2/3 implementation, prior evidence and relevant memory read
before implementation. Only Step 4 is authorized. Q1–Q8 defaults remain
PROPOSALS; all P06 OPEN decisions remain OPEN until closure. No commit, push,
PR, merge, deployment, production data change or migration.

## Implementation and acceptance

[Summary contract](../docs/api/finance-currency-summary.md) adds exactly one GET,
all-six-role VIEW, exact DTOs and observed-currency grouping. Finance report
service owns one REPEATABLE READ, READ ONLY transaction, authorizes exactly as
LedgerService and uses two SELECT-only repositories with the same session.
Finance uses SQL aggregates, and inventory valuation SQL is reused, not copied.
No existing integrity/_report/payments unbounded path is called.

Valuation/waste now use shared recursive SQL aggregate definitions plus bounded
lot/product pages, at most 201 rows. Aggregate queries return one result row;
SQL counts/totals cover every scoped source row. First-100 identifiers have
complete counts. Waste alone rejects two-ended date spans above 366 days.
No date/timezone requirement is added to valuation or summary. Existing finance
contracts/limits remain unchanged. `lot_valuation` remains for page/detail rows;
unused `waste_totals` and amount helpers are removed.

Initial verified two-currency fixture: USD purchase linked 15/count 1,
unlinked 0/count 0; lots received/remaining/consumed/disposed/returned/adjusted
15/5/5/5/0/0; ledger -13 plus archived zero account. VND linked 200000/count 1,
unlinked 40000/count 2 (finance-only 30000 plus unreceived product 10000);
lots 260000/130000/80000/50000/0/0; ledger -230000. Unknown L2 count 1.
Reconciliation currencies 2, linked items 2, unlinked items 2, mismatch/reversed/
tie-out 0, unknown 1, issues 0. DRAFT EXPENSE and income/reversal kinds do not
enter purchase totals. No combined money key exists at any response depth.

Read-only proof: unchanged existing snapshot assertions plus the new summary
snapshot test observe exactly `(repeatable read, on)`. A separate runtime
transaction commits a real stock movement after access resolution: valuation
first sees 10 kg / remaining 200000, next sees 9 kg; waste first sees disposed
0, next sees 1 kg / 20000; summary first sees remaining 200000, next 180000.
Household snapshots compare complete serialized rows in every public table
with household_id before/after report reads, including pages and filters;
no stock/finance/history/audit/operational row changes. These passed in the
initial report run, required targeted run and final full suite.

## Verification ledger

Every run uses copied `/tmp/p0601-step4-run.py` (all step3/Step 3 tokens replaced),
fresh disposable postgres:16-alpine 16.15, 384m/512m memory caps, 0.65 CPU,
separate migrator/runtime/worker roles, guarded test DBs and MALLOC_ARENA_MAX=2.
Bare `python` is absent; invoke the same runner with `.venv/bin/python`.
PID 9375/port 8000 is untouched. Commands and container cleanup evidence are
in `/tmp/p0601-step4-commands.jsonl`; logs `/tmp/p0601-step4-*.log`.

- Baseline OpenAPI captured on clean HEAD before any repository edits: 80 paths,
  140 schemas, `/tmp/p0601-step4-openapi-baseline.json`.
- Initial RED on unchanged application: 11 failed, 42 deselected, 1 warning in
  14.95s, exit 1, runner 26.10s. Three test fixtures used INCOME without items;
  corrected tests only (existing posting requires item sums).
- Confirmed RED on unchanged application: 11 failed, 42 deselected, 1 warning
  in 16.86s, exit 1, runner 26.68s. Missing route/methods and date cap.
- Initial GREEN excluding two >1000-row tests: 51 passed, 2 deselected,
  1 warning in 113.59s, exit 0, runner 121.59s. All 42 existing report cases
  passed, including unchanged snapshot assertions and overcorrection behavior.
- Row-scale bounds: 2 passed, 51 deselected, 1 warning in 209.48s, exit 0,
  runner 216.92s; valuation call 103.70s, waste call 103.18s. Full 1001-lot
  and 1001-root fixtures retained, no reduction; totals/counts and bounded
  fetches verified. Every completed container stop/remove is 0/0.
- Expanded targeted coverage initially had 8 passed / 1 failed / 44 deselected
  in 19.51s, exit 1 (runner 26.40s): an added fixture tried a deduction after
  seeding a reversed purchase original. The unchanged writer correctly returned
  409 INVENTORY_STATE_CONFLICT. Removed that invalid extra fixture write;
  retained mismatch/reversal checks and split-receipt/ledger-only coverage.
- Required targeted: 9 passed, 44 deselected, 1 warning in 20.03s, exit 0,
  runner 29.32s. Split receipts count one purchase item; ledger-only currency,
  archived zero balance and no-entry-account omission verified.
- Independent static read-only review: PASS, no new P1/P2/P3. Reviewer inspected
  code/diff, records, existing logs and OpenAPI delta, did not run tests or
  modify repository. `/tmp/p0601-step4-independent-review.md`. This does not
  replace Peter's separate tester/reviewer gate or Lam's merge approval.
- Finance/inventory/identity regression: 516 passed, 1 warning in 390.29s
  (0:06:30), exit 0, runner 422.53s. Actual files: test_finance_transactions,
  test_finance_authorization, test_finance_reconciliation, test_finance_reversals,
  test_finance_inventory_reversal, test_inventory_integrity, test_inventory_lots,
  test_inventory_movements, test_inventory_checkout, test_inventory_lifecycle,
  test_identity_registration (all under tests/, .py). Requested test_finance.py,
  test_inventory.py, test_lifecycle.py and test_checkout.py do not exist; use
  these existing counterparts and retain all four requested existing files.
  Finance/integrity test sources are unchanged; identity allow-list adds only
  the required two lines. Container stop/remove 0/0.
- Final full suite, one attempt: **1210 passed, 1 warning in 3439.84s
  (0:57:19)**, pytest exit **-15**, runner **3569.91s**, wrapper exit 143.
  Runner sent SIGTERM 120.3s after the complete passing summary for the
  known post-summary interpreter shutdown hang. This is not an exit-0 full
  run. Container stop/remove 0/0. 1210 = 1199 baseline + 11 new cases; no
  failed/skipped tests. No pre-summary kill or repeated full run occurred.
  Observed about 1 GB swap during this slower run; no resource/test change.
  Exact observation/shutdown artifacts: /tmp/p0601-step4-full-summary-observation.json
  and /tmp/p0601-step4-full-shutdown.json.
- Static checks: Python AST parses all changed Python files; git diff --check
  clean; Alembic heads reports 000000000008 (head). Final OpenAPI comparison
  repeated with no changed/removed existing contract. Changed Markdown local
  file links pass. Exactly 20 Step 4 paths are uncommitted; docker ps is empty.

## OpenAPI and compatibility

Baseline 80/140 → 81/149. Exactly one added GET currency-summary and nine
added CurrencySummary schemas; no existing paths/schemas changed or removed.
Snapshots and delta are `/tmp/p0601-step4-openapi-{baseline,new,delta}.json`.
The delta verifies these exact existing paths unchanged (prefix H):
GET /ledger; GET /accounts/{account_id}/balance; GET /finance/integrity;
GET /transactions/{transaction_id}/payments (its POST also unchanged);
GET/POST /reconciliations; GET /reconciliations/{session_id};
POST /reconciliations/{session_id}/matches;
POST /reconciliations/{session_id}/matches/{match_id}/unmatch;
GET /reconciliations/{session_id}/discrepancies;
POST /reconciliations/{session_id}/close;
POST /reconciliations/{session_id}/refresh-cutoff.
The 516-test regression passes with existing finance/integrity files unchanged.
Only summary DTOs and the GET were added; the identity route allow-list
adds exactly the required comment plus one GET entry.

## P3 and Step 4 inputs

1. Step 2 P3-2 full-lot Python totals scan: replaced by shared SQL aggregates
   and bounded pages; 1001-lot test passed with full received value 20020000,
   checked/quantity/value-tied counts 1001 and direct fetch exactly 201.
2. Step 3 P3-1 uncapped per-root/product materialization: replaced by SQL
   aggregates and product keyset/LIMIT; 1001 roots passed, disposed 1001 kg /
   20020000 VND, denominator 20020000, unknown empty, TIED_OUT; direct fetch
   returns one product aggregate, at most the requested 201 rows.
3. Step 3 P3-2 overcorrected opposite-signed roots: preserved, initial GREEN
   existing test passes HTTP 200/TIE_OUT_MISMATCH. SQL keeps
   sum(abs(net_delta))*unit_cost <> abs(sum(net_delta))*unit_cost per lot.
   Recommend closure explicitly accept per-root absolute waste or separately
   decide signed-net/correction-writer policy, avoiding a silent meaning change.
4. Step 3 P3-3 NULL reason: frozen revision 7 lines 203–213 declares TEXT NOT
   NULL + four-code CHECK; aligned-detail guards also apply. No new reason
   semantics. Recommend closure rely on enforced valid-data constraints and
   separately decide defensive malformed-import/integrity handling.

## Deviations and exclusions

The task's 1001 one-kg disposals at 20000 VND/kg have exact value **20020000**,
not 20010000. Preserve every root and use exact arithmetic; denominator also
20020000. No reduced fixture or omitted event. The exact summary unknown-cost DTO has count/lot_ids only; the test prose
mentions quantities, which remain in valuation rather than adding forbidden
extra summary fields. Bare python interpreter alias
absence is handled by invoking the existing virtualenv Python, without changing
the copied runner. All other proposed Step 4 boundaries remain intact.

No migration (head 000000000008), snapshot table, FX, invented cost, report
writer, identity/settings/role change, existing finance limit change, P07/P08,
email, carried-policy decision or P06 closure. Coordinator testing/review and
Lam's merge approval remain separate gates.
