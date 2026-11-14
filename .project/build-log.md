# Build log
- 2026-11-06 Installed a separate local PostgREST 16.0/PostgreSQL 16.15 sandbox. All 18 existing project tests, REST smoke checks, dependency checks, and compilation passed. See [verification evidence](verification-2026-11-06.md).
- 2026-11-04 Inspected Git and the workspace. The initial workspace contained only .git and master had no commits. Application builds, migrations, and tests belong to later phases.
- 2026-11-04 Static checks covered 72 files, metadata and references for 14 skills, local Markdown links, Mermaid diagram types, and traceability task IDs. Diagram rendering and runtime validation remain pending.
- 2026-11-05 Added the Phase 01 PostgreSQL V1 design. Static checks verified 39 unique relation contracts and local links across seven design and project records. PostgreSQL migrations and runtime checks remain pending.
- 2026-11-05 Recorded Awesome DESIGN.md as a required frontend design reference in repository instructions and UI and UX guidelines.

- 2026-11-06 Generated the local Graphify knowledge graph (414 nodes, 515 edges, 56 communities). Structural export checks passed with extraction-quality warnings. See [graph verification](graphify-verification-2026-11-06.md).

- 2026-11-06 Prepared the user-authorized IMSF GitHub upload. All 18 tests and dependency/syntax checks passed; synchronized CI disposable database configuration. See [publication evidence](github-publication-2026-11-06.md).

- 2026-11-13 P05-01 Step 5 closure review on `task/P05-01-closure-review` (HEAD 9d81253): full suite 1157 passed, 0 failed, 0 skipped, 1 warning on a fresh disposable PostgreSQL database (pytest process exit -15 — known host limitation, printed summary is the evidence); targeted P05 files 343 passed; /health and /health/ready 200; migration chain base → 000000000008 verified with standalone rehearsals 15/15 PASS; OpenAPI unchanged vs 9d81253 (77 paths / 118 schemas). Documentation and project records only; no production code, test or migration change. See /tmp/p0501-step5-result.md.

- 2026-11-13 P06-01 Step 2 on `task/P06-01-valuation-reads` from `3d4587e`:
  lot valuation reads implemented as PROPOSALS; final targeted valuation 19 passed,
  1 warning in 42.77s, exit 0; existing regressions 194 passed in 146.36s, exit 0,
  on fresh disposable PostgreSQL. Independent review P2 null totals fixed RED/GREEN.
  Recomputed OpenAPI
  77/118 → 79/127 paths/schemas, existing contracts unchanged. Full verification
  and P3 notes are recorded in [Step 2 evidence](p0601-step2-coder-evidence.md).
  No migration, commit, push, PR or deployment. P06 closure remains pending.

- P06-01 Step 2 final full suite: 1176 passed, 1 warning in 2537.39s (0:42:17); pytest exit -15. Known post-summary shutdown hang; SIGTERM recorded explicitly. Disposable container stop/removal both 0; targeted final valuation 19 and existing inventory/finance 194 both exit 0. See Step 2 evidence.

- 2026-11-13 P06-01 Step 3 on `task/P06-01-waste-report` from `e3bbf12`:
  waste report implemented as PROPOSALS; targeted waste **23 passed** in 52.30s,
  exit 0 (fresh disposable PostgreSQL), exact section-5 math and read-only
  snapshot/concurrency proof. OpenAPI recomputed 79/127 → 80/140 paths/schemas;
  existing contracts unchanged. Remaining regression/full/review evidence is
  tracked in [Step 3 evidence](p0601-step3-coder-evidence.md). Step 4 owns
  366-day/1,000-row caps and uncapped lot/event work. No commit/push/PR/deploy.

- 2026-11-14 P06 Step 4 PROPOSAL on `task/P06-01-currency-summary` from `5deea4f`:
  currency summary and report maximums; SQL aggregates replace full-lot/root/
  product materialization. RED 11 failed (after correcting test-only INCOME
  fixture), initial GREEN excluding 1001-row tests 51 passed in 113.59s,
  exit 0. Final targeted 9 passed in 20.03s, scale 2 in 209.48s, regression
  516 in 390.29s (all exit 0). Full 1210 passed in 3439.84s, pytest -15 after
  complete summary, runner 3569.91s; stop/remove 0/0, no container left.
  OpenAPI 80/140 to 81/149, one GET/nine schemas only; independent static
  review no new P1/P2/P3. See [Step 4 evidence](p0601-step4-coder-evidence.md).
  No commit/push/deploy/migration or P06 closure; earlier OPEN items unchanged.

- 2026-11-14 P06-01 Step 5 closure review on `task/P06-01-closure-review`
  from `bc5b6ed`: docs only — no production code, test, migration, route or
  DTO change. Full suite 1210 passed, 1 warning in 2402.96s (0:40:02) on a
  fresh disposable PostgreSQL DB (pytest exit -15 after the runner's SIGTERM
  120.65s post-summary, known shutdown hang — 11th occurrence counting one
  final full-suite run per step; printed summary is the evidence, not an
  exit-0 run); container stop/remove 0/0. OpenAPI regenerated 81 paths /
  149 schemas, identical to the Step 4 new spec (77/118 at P05-01 closure →
  81/149: exactly four new GETs and 31 new schemas, nothing existing changed
  or removed). Migration head stays 000000000008. Docs correct stale
  Step-4-deferral wording (finding F-1) and record closure verdicts (a)–(h)
  with carried P3 dispositions for Lam's separate closure decision. See
  [Step 5 evidence](p0601-step5-coder-evidence.md). No commit/push/deploy/
  merge/closure; coordinator tester/reviewer and Lam's approvals remain
  separate.
