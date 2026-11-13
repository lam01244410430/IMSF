# P06-01 Step 2 worker evidence — 2026-11-13

Base/HEAD `3d4587e69aaf3bc5b972aeb25e0399462a4b9eb4`, branch
`task/P06-01-valuation-reads`; initial working tree clean. Authorized scope:
lot valuation reads only. All implemented P06 defaults are **PROPOSALS**, and
all P06 OPEN decisions remain OPEN until closure. No commit, push, PR or deploy.

The [API contract](../docs/api/inventory-reports.md) documents the two GET
routes, exact costing, correction netting, full-scope currency totals, purchase
linkage, explicit unknown-cost quantities and historical visibility. The
application uses one REPEATABLE READ, READ ONLY report transaction; repository
SELECTs only. Migration head stays `000000000008`. Existing finance contracts,
identity/settings/roles and all carried decisions are unchanged.

## Verified arithmetic

| Lot (kg, VND) | Received | Remaining | Consumed | Disposed | Returned | Adjusted-out |
|---|---:|---:|---:|---:|---:|---:|
| L1 PURCHASE at 20000 | 200000 | 100000 | 80000 | 20000 | 0 | 0 |
| L2 GIFT, unknown cost | null | null | null | null | null | null |
| L3 MANUAL at 15000 | 60000 | 30000 | 0 | 30000 | 0 | 0 |
| Known-cost VND totals | 260000 | 130000 | 80000 | 50000 | 0 | 0 |

L1 quantities: 10 = 5 + 4 + 1 + 0 + 0. L2: 5 = 0 + 5 + 0 + 0 + 0,
terminal CONSUMED; its consumed 5 kg remains unpriced in the explicit unknown
section. L3: 4 = 2 + 0 + 2 + 0 + 0. L1's received value 200000 agrees with
linked item net_amount 200000. A separate fixture received at 18000 reports
180000 versus 200000, PURCHASE_MISMATCH and HTTP 200; existing lot cost never
changes.

Read-only tests compare complete JSON rows of every public household-owned
table before/after page and detail GETs. This includes stock, movements, finance,
history, audit and operational records. An independent runtime transaction
commits a real stock deduction between report authorization and data SELECT;
the current report retains the old snapshot and the next report sees the new
state. The report connection observes `repeatable read` and `read_only=on`.

## Verification ledger

Tests use fresh disposable PostgreSQL 16.15 (`postgres:16-alpine`) containers,
384m memory / 512m total swap allowance / CPU 0.65 / max WAL 64MB; separate
migrator/runtime/worker identities and guarded p02_test_/p03_finance_test_
fixtures. `MALLOC_ARENA_MAX=2` on every pytest invocation. Containers stop and
remove after each run. No process on port 8000 is started or stopped.

- RED: missing valuation route, HTTP 404; 1 failed, 14 deselected, 1 warning
  in 3.75s, exit 1. Initial green: 14 passed, 1 failed (test helper mistakenly
  used `movement_ids` instead of existing adjustment `movement_id`); corrected
  helper. This test setup error did not require a production change.
- `python -m pytest -q tests/test_p06_01_reports.py -k valuation`: **18 passed,
  1 warning in 41.70s**, exit **0**. Previous corroborating run: 17 passed,
  1 warning in 31.58s, exit 0, before the issue-cap/overcompensation test was added.
- Final-review P2 fix RED: unknown-only money totals were an empty list;
  regression failed as expected, 1 failed, 18 deselected, 1 warning in 3.21s,
  exit 1. Corrected DTO/service to return null only for a nonempty wholly
  unknown-cost scope; empty scopes retain [], known-zero/mixed scopes retain
  currency lists. Updated API proposal and recomputed OpenAPI.
- Post-review targeted valuation: **19 passed, 1 warning in 42.77s**, exit **0**.
- Existing targeted regression: **194 passed, 1 warning in 146.36s (0:02:26)**,
  exit **0**, covering test_inventory_lots.py, test_inventory_movements.py,
  test_inventory_integrity.py, test_inventory_authorization.py,
  test_finance_inventory_reversal.py and test_finance_transactions.py.
- Full suite: see first-run failure and final full-suite evidence below.
- Independent read-only code review: `/tmp/p0601-step2-independent-review.md`.
  One P2, no P1 or additional P2; the P2 was corrected with the RED/GREEN
  evidence above. Independent review did not rerun tests; final fix validation
  is the worker's actual run, not an invented second reviewer approval.

Exact commands, exit codes and redacted logs are retained on the EC2 in
`/tmp/p0601-step2-commands.jsonl` and `/tmp/p0601-step2-*.log`. Final requested
worker report: `/tmp/p0601-step2-result.md`.

OpenAPI was generated before edits at the verified base and after implementation:
**77 paths / 118 schemas → 79 paths / 127 schemas**. Added only the two valuation
GET paths; no existing path/schema changed or removed. Added schemas:
LotValuationPage, LotValuationResponse, UnknownCostLot, UnknownCostSection,
ValuationCurrencyTotal, ValuationIssue, ValuationIssues, ValuationPurchase,
ValuationReconciliation. Full recomputed schemas and delta are retained under
`/tmp/p0601-step2-openapi-{baseline,new,delta}.json`.

## P3 findings and handoff

1. Existing correction commands permit overcompensating a linked deduction.
   Proposed absolute per-kind netting can then fail the tie-out while the stock
   projection is valid. A persisted test proves the report returns 200 with
   TIE_OUT_MISMATCH instead of inventing a balancing entry. This is input to
   P06-OPEN-01 closure; no P04 correction policy is re-decided.
2. Matching-lot scans for totals currently have no row cap; Step 4 owns bounds.
   List output reuses default 50/max 200 and issue/unknown identifiers are capped
   at 100 with complete counts. Existing finance contract limits remain unchanged.

A split PURCHASE lot compares against its linked item's full net amount, as
proposed; no pro-rata allocation is introduced. Today's stock-linked reversal
refusal remains intact; the reversal-report test seeds a defensive historical
unpaid-reversal fixture through runtime SQL without bypassing triggers/grants.

Waste, currency summary, P07/P08, migration/snapshot/FX work and P06 closure
remain deferred. P05 OPEN items, P3-2, P04-OPEN-11/16, P02-02 leftovers, P01-01
and ADR-0005 keep their previous state. Coordinator review/closure is separate
from worker implementation and passing tests.

## First full-run compatibility correction

1 failed, 1175 passed, 1 warning in 2428.19s (0:40:28); pytest exit -15. The exact global route allow-list in tests/test_identity_registration.py omitted only the two newly authorized GET paths; all valuation tests passed. Added exactly those two GET expectations and a proposal comment, retaining the exact-equality guard and every old route. No identity behavior changed. The first run remains a recorded failure, not passing evidence. The process stuck after its summary; SIGTERM after134.82s is recorded in /tmp/p0601-step2-full-shutdown.json; container cleanup returned0. Fresh combined scope/valuation regression: 20 passed, 1 warning in 46.49s; exit 0. This existing compatibility-test file is a necessary deviation from the proposed file list.

## Final full-suite gate

`MALLOC_ARENA_MAX=2 /home/ubuntu/IMSF/.venv/bin/python -m pytest -q`: `1176 passed, 1 warning in 2537.39s (0:42:17)`; pytest exit **-15**. The complete passing summary was printed before interpreter shutdown stuck; the worker sent SIGTERM to this run's pytest PID only after the recorded post-summary wait. This is the known host shutdown artifact, not exit 0. See `/tmp/p0601-step2-full-final-shutdown.json`. SIGTERM was sent 170.38 seconds after the complete summary output.

The 1176 printed passing tests comprise the 1157-test baseline plus 19 new valuation tests. The new tests also passed independently in the targeted post-review run (19, exit 0); six existing inventory/finance files passed separately (194, exit 0). One existing Starlette TestClient deprecation warning persists; no dependency change is included. The full-suite container stop/removal both returned 0. Final diff and scope checks are recorded in `/tmp/p0601-step2-result.md`.
