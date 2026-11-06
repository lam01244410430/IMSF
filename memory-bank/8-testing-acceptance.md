# Testing and acceptance
Use pytest for domain rules and real PostgreSQL for foreign keys, migrations, idempotency, rollback, and concurrency. Use HTTPX for FastAPI schemas, permissions, and errors. Use Vitest and Testing Library for interaction and Playwright for critical workflows.
Cover duplicate checkout, ledger reconciliation, full checkout rollback, concurrent deductions, cross-household references, expiry boundaries, job deduplication, waste aggregation, and exclusion of expired ingredients.
Require evidence for changed paths and critical invariants. Set overall coverage thresholds with the CI baseline. Record commands, results, and unverified scope for each phase.
