# Traceability matrix
Evidence update on 2026-11-06 covers P02-01 health checks and P02-02 migration, household composite ownership constraints, and rollback checks. ID-01 request authorization acceptance remains pending. See the [verification record](verification-2026-11-06.md).

| Requirement | Task | Design | Planned evidence |
|---|---|---|---|
| ID-01 Household isolation | P02-02 | ADR-0002, ADR-0006 | Denied requests and composite foreign keys |
| FIN-01 Auditable ledger | P03-01 | ADR-0003 | Reversal, concurrent posting, reconciliation |
| INV-01 Purchase lot traceability | P04-01 | ADR-0004 | Rollback, duplicate requests, competing deductions |
| LIFE-01 Expiry and disposal | P05-01 | ADR-0005 | Time zone boundaries, deduplication, partial deductions |
| WASTE-01 Lot valuation | P06-01 | Business rules and algorithms | Valuation reconciled separately from cash entries |
| REC-01 Deterministic matching | P07-01 | ADR-0008 | Ties, expired lots, and essential shortages |
| UX-01 Three accessible locales | P08-01 | ADR-0007 | Locale switching, keyboard paths, error states |
| OPS-01 Recoverable release | P09-01, P10-01 | Operations and checklist | Recovery rehearsal and release approval |

The [PostgreSQL V1 schema specification](../docs/database/schema-v1.md) maps ID-01 to ownership and authorization, FIN-01 to finance, INV-01 and LIFE-01 to inventory and lifecycle, WASTE-01 to lot costing, REC-01 to recipes, and OPS-01 to jobs and migration acceptance. Runtime evidence remains planned.

Analysis evidence on 2026-11-06: the [local knowledge graph](graphify-verification-2026-11-06.md) supports navigation only and does not satisfy product requirement acceptance.

Publication verification on 2026-11-06 reran all 18 existing tests successfully; see [publication evidence](github-publication-2026-11-06.md). Full ID-01 HTTP authorization acceptance remains pending.

2026-11-12 P05-01 Step 2 traceability: LIFE-01 date/freshness/timezone and historical provenance reads, ID-01 all-six-role VIEW/isolation/composite FKs, INV-01 unchanged stock/history through read paths, and OPS-01 additive migration/grants/history-safe downgrade are mapped to the four `tests/test_inventory_expiry*.py` files. See [actual Step 2 evidence](p0501-step2-coder-evidence.md). Lifecycle execution/deduplication/concurrency acceptance remains Step 3, and broader partial-deduction acceptance remains Step 4. P05 delivery awaits Lam's closure acceptance.

2026-11-13 P05-01 Step 5 closure review: LIFE-01 date/freshness/timezone, deduplication and partial-deduction acceptance are re-verified on the Step 4 tree — full suite 1157 passed, targeted P05 files 343 passed, CLOSED P2-1 race regression 10/10 passed; ID-01 all-six-role VIEW/isolation/composite FKs rechecked through the targeted expiry/lifecycle/authorization files; INV-01 unchanged stock/history through read and job paths (no stock/finance writer in app/lifecycle, re-grepped); OPS-01 additive migration/grants/history-safe downgrade re-verified by standalone rehearsals (15/15 PASS: populated rev-7 upgrade preserves all rows, downgrade refuses 55000 with history, empty downgrade preserves rev-7 history) and OpenAPI compatibility (77 paths / 118 schemas, unchanged vs 9d81253). Health 200/200 on a fresh DB. Known host limitation: full-suite pytest process exit -15 (printed summary is the evidence). See [Step 5 evidence](/tmp/p0501-step5-result.md) (EC2; copy at ~/workspace/user/files/P05-01-step5-result.md).

2026-11-13 P06-01 Step 2: WASTE-01 fixed-lot valuation/unknown cost/per-currency sums and purchase linkage, INV-01 correction-netted quantities and retained history, ID-01 VIEW for all six roles/isolation/removed-member denial, and FIN-01 unchanged purchase provenance map to `tests/test_p06_01_reports.py`. [Step 2 evidence](p0601-step2-coder-evidence.md) records exact fixture arithmetic, read-only snapshots and compatibility. This is proposal implementation evidence, not P06 closure or waste-report acceptance.
