# P06-01 Step 5 worker evidence — 2026-11-14

Branch `task/P06-01-closure-review`, base/HEAD `bc5b6ed` (Step 4 merge).
Initial clean tree, branch, HEAD and plan MD5
`b7fb975eadd475a61507e487810b4a23` verified before any work. Plan §2–§10 read
in full; Step 2/3/4 result, test and review files read in full before writing
anything. Only Step 5 is authorized. Docs only: no production code, test,
migration, route or DTO change. No commit, push, PR, merge, deployment,
production data change or migration. The live full-suite floor is 1210 passed
(the plan §6 "1157" figure is the P05-01 floor, never the P06 floor).

## What Step 5 changed (docs only)

- `docs/database/schema-v1.md`: Step 5 closure-review note (verdicts (a)–(h),
  carried P3 dispositions, P05-OPEN-14 input, OpenAPI delta, migration chain,
  P07/P08 handoffs, 1,000-row-cap pinning); one pointer added to the historical
  Step 3 note marking the 366-day/1,000-row caps as delivered in Step 4.
- `docs/api/inventory-reports.md`: header updated to Steps 2–5; finding F-1
  fixed in place (three stale Step-4-deferral sentences corrected and marked);
  new "Closure review — P06 Step 5" section with verdicts (a)–(h), carried P3
  dispositions, P05-OPEN-14 input, known limitations, OpenAPI delta, migration
  chain, handoffs, and the emergent 1,000-row-cap pinning (Step 4 reviewer O-1).
- `docs/api/finance-currency-summary.md`: new "Closure review — P06 Step 5"
  section recording the Step 4 reviewer P3-1/P3-2/P3-3 dispositions and O-1.
- `memory-bank/5-api-contracts.md`: two stale Step-4-deferral sentences fixed
  (F-1); new "P06 Step 5 closure review" section.
- `memory-bank/15-open-questions.md`: new "P06 Step 5 closure review status"
  section — every P06-OPEN-01..10 item with what its closure decision needs,
  carried P3 dispositions, P05-OPEN-14 input, known limitations, handoffs.
- `.project/task-board.md`: P06-01 row now "In progress — Step 5 closure review
  PROPOSAL (docs only); closure pending" — never Delivered.
- `.project/current-phase.md`, `.project/build-log.md`,
  `.project/session-handoff.md`, `.project/traceability-matrix.md`,
  `PROJECT_STATUS.md`: Step 5 IN PROGRESS records (see below); none claims
  delivery or closure.
- This file (new): `.project/p0601-step5-coder-evidence.md`.

No `.py`, migration, test or route file changed. No P05 OPEN item, P3-2,
P04-OPEN-11/16, P02-02 leftover, P01-01 label or ADR-0005 is re-decided.
ADR-0005 is not expanded. The P01-01 label is unchanged (Conditionally
approved).

## Finding F-1 (doc staleness, fixed in this step)

Three sentences in `docs/api/inventory-reports.md` still described Step 4
bounds work as deferred/pending although Step 4 had delivered it: the
valuation "Query and visibility" paragraph ("The Step 4 scan/row-cap and wider
report-bounds work remains deferred"), the "remain Step 4 work" sentence after
the acceptance fixture, and the waste "Step 4 inputs" paragraph (future-tense
"Step 4 must include"). Two more stale sentences in
`memory-bank/5-api-contracts.md` (Step 2: limits "remain Step 4 proposals";
Step 3: caps "remain Step 4"), and the Step 3 note in
`docs/database/schema-v1.md` ("caps remain Step 4 work") with no pointer to the
superseding Step 4 note. Each is corrected in place and marked "(Step 5
correction F-1)". No code contradicted the docs: the Step 4 SQL-aggregate
bounds were already implemented and tested; only the prose lagged. No other
doc/code contradiction was found in Step 5.

## Verification ledger

Every run uses `/tmp/p0601-step5-run.py` (copied from the Step 4 runner with
step4→step5 tokens replaced; AST-checked), fresh disposable
postgres:16-alpine 16.15, 384m/512m memory caps, 0.65 CPU, separate
migrator/runtime/worker roles, guarded test DBs and MALLOC_ARENA_MAX=2.
Bare `python` is absent; invoke the runner with `.venv/bin/python`.
PID 9375/port 8000 is untouched. Commands and container cleanup evidence are
in `/tmp/p0601-step5-commands.jsonl`; logs `/tmp/p0601-step5-*.log`.

- Final full suite, one attempt: **1210 passed, 1 warning in 2402.96s
  (0:40:02)**, pytest exit **-15**, runner **2535.27s**. Runner sent SIGTERM
  120.65s after the complete passing summary for the known post-summary
  interpreter shutdown hang. This is not an exit-0 full run. Container
  stop/remove 0/0. 1210 = 1157 P05-01 floor + 53 new P06 tests (19 valuation +
  23 waste + 11 summary/bounds/scale); no failed, errored or skipped tests.
  The single warning is the pre-existing StarletteDeprecationWarning about
  `httpx` with `starlette.testclient`. Exact observation/shutdown artifacts:
  /tmp/p0601-step5-full-summary-observation.json and
  /tmp/p0601-step5-full-shutdown.json; run record in
  /tmp/p0601-step5-commands.jsonl. PostgreSQL 16.15 on x86_64-pc-linux-musl.
  No pre-summary kill or repeated full run occurred.

- OpenAPI regenerated from the running app with
  `/tmp/p0601-step5-openapi.py` (copy of the Step 4 tester script):
  current spec **81 paths / 149 schemas**, identical to the Step 4 new spec.
  Spec identical to the Step 4 new spec (detail-dict equality). Delta vs the
  P05-01 baseline (77/118, `/tmp/p0601-step2-openapi-baseline.json`): exactly
  +4 GET paths (valuation, valuation/{lot_id}, waste-report,
  currency-summary) and +31 schemas (9 valuation + 13 waste + 9 summary);
  0 removed, 0 changed. Delta file `/tmp/p0601-step5-openapi-delta.json`;
  new spec `/tmp/p0601-step5-openapi-new.json`.
- Identity exact-route allow-list (`tests/test_identity_registration.py`)
  carries exactly the same four new GETs — cross-checked by grep, no other
  route expectation changed.
- Migration chain: `alembic heads` → `000000000008 (head)`; no migration file
  in the diff; revisions 1–8 frozen and untouched.
- Docs diff: `git diff --check` clean (see result file); `git diff --stat`
  shows only `.md` files (see result file). No `.py`, migration, test or
  `.env` file in the diff.

## Closure verdicts (a)–(h) — short form

(a) Task-board acceptance "Reconciled lot valuation and currency grouping":
PROVEN as implemented (PROPOSAL) — §5 fixture exact numbers on all three
routes (valuation L1 200000 = 100000 + 80000 + 20000, L2 quantities tie out
with all values null, L3 60000 = 30000 + 0 + 30000; waste 3 kg / 50000 VND,
denominator 260000, rate 50000/260000 at precision 80; summary VND 260000 /
−230000 and USD 15 / −13, no combined total), plus OpenAPI 77/118 → 81/149.
Holds as a PROPOSAL only: P06-OPEN-01..10 remain OPEN for Lam.

(b) P06-OPEN-01..10: all implemented as the recommended (a) defaults, all stay
OPEN for Lam to decide at the P06 closure. What each decision needs is
tabulated in `memory-bank/15-open-questions.md` (Step 5 section).

(c) Carried P3 dispositions:
- Step 2 P3-1 (correction overcompensation → TIE_OUT_MISMATCH): closure
  decision under P06-OPEN-01 — write-time correction constraints (a P04
  change) vs signed nets in the report model.
- Step 2 P3-3 (VIEWER/MEMBER money visibility): closure decision under
  P06-OPEN-06 — confirm all-six-role VIEW or restrict the routes (b)/(c).
- Step 3 P3-2 (overcorrected opposite-signed roots): closure accepts per-root
  absolute waste or separately decides signed-net / correction-writer policy;
  do not silently change retained-event meaning.
- Step 3 P3-3 (NULL reason_code): DDL-enforced NOT NULL + four-code CHECK in
  revision 000000000007; rely on the enforced constraint for valid data;
  defensive malformed-import/integrity handling is a separate decision.
- Step 4 reviewer P3-1 (global unknown_cost under a currency filter): closure
  semantics — confirm the documented global-unknown_cost contract for filtered
  summaries, or align the summary with valuation/waste by filtering
  unknown_cost on summary_currency.
- Step 4 reviewer P3-2 (summary unknown_cost count+lot_ids only, no quantities
  by kind): confirm the shape at closure, or add quantities by kind to
  CurrencySummaryUnknownCost (a DTO change, not a Step 5 change).
- Step 4 reviewer P3-3 (shared aggregate fields dropped by the valuation DTO):
  recommended disposition — document the shared-aggregate contract (the
  reversed_original_count / tie_out_mismatch_count fields exist for the
  currency-summary consumer; the valuation DTO intentionally does not surface
  them); the alternative follow-up cleanup is trimming the valuation select.
  Either is a post-closure follow-up, not a Step 5 code change.

(d) P05-OPEN-14 input as delivered: new-surface maximums (default 50/max 200,
scoped cursor pages, waste-only 366-day cap, 1,000-row query-result bound) and
bounded SQL-aggregate inputs for the consumed finance reads; existing finance
contract limits unchanged. P05-OPEN-14 itself remains a release input, with
P09 owning hardening.

(e) Known limitations, stated plainly: the full-suite pytest process again
did not exit cleanly — **1210 passed, 1 warning in 2402.96s (0:40:02)**,
pytest exit **-15** after the runner's SIGTERM 120.65s post-summary. This is
the 11th occurrence counting one final full-suite run per step (7 at P05-01
plus the Step 2, Step 3 and Step 4 finals; the Step 2 earlier failed full run
also exited -15). Zero test failures in any of them; the printed summary is
the evidence, never claimed as exit 0. The Step 3 coder's
first full-suite attempt died at 84% with no summary on a Codex usage-limit
hit (184,773 tokens); that step's count rests on two complete independent
re-runs, not on that attempt.

(f) OpenAPI delta across P06-01: 77 paths / 118 schemas (P05-01 closure,
3d4587e) → 81 / 149 (Step 5, regenerated and identical to the Step 4 new
spec). Exactly +4 GET paths and +31 schemas; 0 removed, 0 changed.

(g) Migration chain: head stays `000000000008`; no P06 migration exists.

(h) Handoffs: P07 receives per-lot valuation + waste facts (read-only) plus
the unchanged P05 contracts (freshness/FEFO eligibility, consumption/cooking
contracts). P08/P09 receive stable report DTOs and the maximums as implemented (PROPOSAL; P06-OPEN-07 still OPEN)
(P06-OPEN-07) as hardening input.

## Deviations and exclusions

None from the plan §6 Step 5 row. Docs-only step; no code change was needed
and none was made. The Step 4 reviewer observation O-1 (the 1,000-row cap is
emergent, with no literal `1000` constant in code) is pinned in the docs: the
cap follows from page fetch ≤ 201 + one aggregate row + first-100
identifier/issue lists; any future change raising the page or identifier
limits must re-derive and re-test the bound. A named constant is a
post-closure follow-up, not a Step 5 change.

No P05 OPEN item, P3-2, P04-OPEN-11/16, P02-02 leftover, P01-01 label or
ADR-0005 is re-decided. No commit, push, PR, deployment, production-data
change or P06 closure. Coordinator tester/reviewer stages and Lam's merge and
closure approvals remain separate gates.
