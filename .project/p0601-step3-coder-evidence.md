# P06-01 Step 3 worker evidence — 2026-11-13

Branch `task/P06-01-waste-report`, base/HEAD
`e3bbf12e2d112bc47f2595c16efe57ae56638481`. Initial branch/HEAD/status/checksum
checks matched: clean Git, plan MD5 `b7fb975eadd475a61507e487810b4a23`.
The full plan was read before code. The user authorizes Step 3 only, implementing
Q1–Q8 default directions as PROPOSALS. P06 OPEN decisions all remain OPEN until
closure. No commit, push, PR, deployment, production data change or migration.

## Implementation and acceptance

[The API contract](../docs/api/inventory-reports.md#waste-report--p06-01-step-3-proposal)
records GET `H/inventory/waste-report`, all six VIEW roles, scoped ownership,
required timezone and exact DTOs. Thin route; report service owns a single
REPEATABLE READ, READ ONLY transaction, and repository SELECTs only. Reuse Step 2
precision 80, fixed cost times correction-netted quantities, cursor pattern and
Limit/Cursor. Extended recursive attribution carries each root's ID/occurred_at.
No valuation/purchase-link rewrite or currency-summary implementation.

Waste is DISPOSE only, using recorded reasons and absolute net deltas per root.
Corrections retain the root's month/reason. Consumption, expired-lot consumption
and cooking are not waste. Same-period known-cost received value supplies the
per-currency denominator; reason does not filter receipts. Rates are Decimal
division at precision 80, serialized strings, null only for a zero denominator.
Unknown-cost disposal/consumption quantities remain unpriced, IDs first 100
ascending with complete count. The specific Step 3 reason rule narrows unknown
by_reason only. Historical archived rows are included. Product pagination does
not narrow totals, breakdowns, unknown cost or reconciliation.

The section-5 test asserts the complete response: VND disposed 3 kg / 50000;
EXPIRED 1 / 20000, SPOILED 2 / 30000; November 2026 bucket 3 / 50000;
denominator 260000 (200000 + 60000); rate expected from Decimal 50000/260000
with localcontext precision 80. Unknown L2: disposed 0, consumed 5, its sole
contributor lot ID/count 1; product row 3 / 50000. TIED_OUT, zero issues.

Read-only proof: complete serialized rows of every public household-owned table
match before and after unfiltered, reason-filtered and paginated requests. A
separate runtime transaction commits a real DISPOSE between authorization and
the report SELECT; the current report still sees disposed 0, next request sees
1 / 20000. Observed transaction settings are exactly `repeatable read`, `on`.
No grant/trigger bypass. Additional tests prove local-midnight month boundaries,
December corrections affecting November roots, zero-net roots disappearing,
archived visibility, known-zero costs and overcorrection mismatch reporting.

## Verification ledger

All pytest runs use fresh disposable `postgres:16-alpine` (observed 16.15),
384m memory, 512m swap allowance, CPU 0.65, max WAL 64MB; separate migrator,
runtime and worker identities, guarded p02_test_/p03_finance_test_ fixtures.
`MALLOC_ARENA_MAX=2`, existing `.venv/bin/python` (Python 3.14). Each container is
stopped/removed after its run. PID 9375/port 8000 is untouched.

- RED fixture: missing route 404 as expected; 1 failed, 19 deselected, 1 warning
  in 4.08s; exit 1, runner 14.77s. Container stop/remove 0/0.
- Initial targeted: 9 passed, 10 failed, 19 deselected in 23.26s; exit 1,
  runner 30.82s. Failures were test setup: OTHER requires text and the foreign
  product POST requires an idempotency key. Corrected test helpers only.
- Required waste tests: 19 passed, 19 deselected, 1 warning in 29.74s;
  exit 0, runner 37.23s, stop/remove 0/0.
- Final waste with boundary/overcorrection/archive/identifier coverage:
  **23 passed, 19 deselected, 1 warning in 52.30s**, exit **0**,
  runner 59.69s; stop/remove 0/0.
- Existing regression: **91 passed, 1 warning in 114.09s (0:01:54)**,
  exit **0**, runner 123.97s, stop/remove 0/0. Files discovered before running:
  tests/test_inventory_lifecycle.py, tests/test_inventory_lifecycle_integration.py,
  tests/test_inventory_movements.py, tests/test_inventory_expiry.py, plus the
  existing exact-route/OpenAPI test in tests/test_identity_registration.py.
  Thus 90 existing lifecycle/disposal tests plus one route-compatibility check.
- Independent read-only whole-change review: no Critical/Important/Minor
  findings requiring changes within Step 3. Report:
  `/tmp/p0601-step3-independent-review.md`. Reviewer inspected actual diff,
  logs and OpenAPI snapshots; did not independently rerun tests. Full suite
  remains required; review is not merge authorization.
- Full suite (final): **1199 passed, 1 warning in 1801.93s (0:30:01)**,
  pytest exit **-15** (known post-summary interpreter shutdown hang;
  SIGTERM 120.4s after the summary; container stop/remove 0/0; runner
  elapsed 1932.26s). 1199 = 1176 floor + 23 new waste tests. The first
  full-suite attempt was killed at 84% with no summary when the Codex
  worker session ended on its usage limit; the coordinator re-ran the
  identical full suite directly with the same runner and no code change
  between attempts. This is not claimed as exit 0.

Exact commands/exit codes/timings are in `/tmp/p0601-step3-commands.jsonl`,
logs `/tmp/p0601-step3-*.log`; runner `/tmp/p0601-step3-run.py` follows the
Step 2 disposable pattern. Final result is `/tmp/p0601-step3-result.md`.

## OpenAPI and compatibility

Baseline regenerated on verified HEAD e3bbf12 before edits: **79 paths / 127
schemas**. New tree: **80 paths / 140 schemas**. Exactly one added GET path:
`/api/v1/households/{household_id}/inventory/waste-report`. No removed or changed
existing paths/schemas. Added 13 schemas: WasteAmount, WasteCurrencySection,
WasteDenominator, WasteIssue, WasteIssues, WastePeriod, WastePeriodRow,
WasteProductRow, WasteReasonRow, WasteReconciliation, WasteReport,
WasteUnknownCost, WasteUnknownReason. Full snapshots/delta are retained under
`/tmp/p0601-step3-openapi-{baseline,new,delta}.json`. The exact-route allow-list
adds exactly the new GET, preserving exact equality and all old expectations.

## P3 and Step 4 inputs

1. **New uncapped event materialization:** Step 2 already scans movements and
   matching lots for totals. Waste additionally returns nonzero per-root
   DISPOSE/CONSUME event rows to the application, beyond one valuation row per
   lot. Totals/denominator still read all matching lots. By-product pagination
   limits output only; it does not bound scans, recursion or month buckets.
   Carry this explicitly to Step 4 under P06-OPEN-07 / carried scan P3 work.
2. Overcorrection can leave opposite-signed disposal roots on a lot. Per-root
   absolute values then differ from valuation's per-lot absolute signed net;
   return HTTP 200/TIE_OUT_MISMATCH with complete count/first 100 issue IDs.
   P06 closure must consider the proposal; no P04 correction policy is changed.

The **366-day cap and 1,000-row report cap are deferred to Step 4**. Summary,
P07/P08, FX, stored snapshots, email, identity/settings/roles and existing finance
contract limits remain outside this step. No carried P05 OPEN, P3-2,
P04-OPEN-11/16, P02-02 leftover, P01-01 label or ADR-0005 decision changes.
No scope deviation; the extra boundary tests substantiate requested invariants.
Coordinator testing/review and P06 closure remain separate gates.
