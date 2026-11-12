# Session handoff
2026-11-06 Local database and REST verification completed. P02-02 remains in progress, with health routes as the only wired HTTP endpoints. See [verification evidence](verification-2026-11-06.md) and [sandbox usage](../tools/postgrest/README.md). Peter is the documented Muse coordinator, but live collaboration was not verified. Existing working-tree changes were preserved.

2026-11-04 Engineering materials and draft ADRs are available. Start with PROJECT_STATUS.md, the task board, and memory-bank/15-open-questions.md. After user approval, begin P02-01 by verifying the toolchain. Authentication, authorization, and domain implementation follow in separate tasks.
Keep files in English and communicate with the user in Vietnamese.

2026-11-05 Resume Phase 01 database review from the [PostgreSQL V1 schema specification](../docs/database/schema-v1.md). Resolve the phase-specific policy gates before translating it to Alembic revisions. Use the migration acceptance section as the PostgreSQL test checklist.

For frontend design, select an Awesome DESIGN.md reference before starting. See the [UI and UX guidelines](../memory-bank/11-ui-ux-guidelines.md).

2026-11-06 Local Graphify outputs are available in `graphify-out/`. Read the [verification record](graphify-verification-2026-11-06.md) before relying on inferred relationships or extraction placeholders. P02-02 remains in progress.

2026-11-06 User authorized publication to lam01244410430/IMSF. See [publication evidence](github-publication-2026-11-06.md). P02-02 remains in progress; remote CI requires separate confirmation.

2026-11-12 P05-01 Step 2 handoff: working tree on `task/P05-01-lifecycle-reads`, base/HEAD c22ea83, no commit/push/deploy/PR. Review [the Step 2 contract](../docs/api/inventory-lifecycle.md) and [verification record](p0501-step2-verification.md). Revisions 1–7 and all carried policy items remain frozen. OPEN-04/05/08 DDL-only choices are PROPOSALS; the contract explicitly lists deferred execution choices. Exact production worker credentials/provisioning and restricted household-lock helper remain OPEN-10. Do not start a worker or add a producer before Step 3 lease/dedup contracts and tests. Independent tester reproduction/merge approval belong to the coordinator's next gate.
