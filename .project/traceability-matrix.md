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

2026-11-12 P05-01 Step 2 traceability: LIFE-01 date/freshness/timezone and historical provenance reads, ID-01 all-six-role VIEW/isolation/composite FKs, INV-01 unchanged stock/history through read paths, and OPS-01 additive migration/grants/history-safe downgrade are mapped to the four `tests/test_inventory_expiry*.py` files. See [actual Step 2 evidence](p0501-step2-verification.md). Lifecycle execution/deduplication/concurrency acceptance remains Step 3, and broader partial-deduction acceptance remains Step 4. P05 delivery awaits Lam's closure acceptance.
