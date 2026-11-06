# Task board
| ID | Work | Depends on | Acceptance | Status |
|---|---|---|---|---|
| P00-01 | Repository discovery and governance | None | File and skill structure checks | Delivered |
| P01-01 | ADRs, ERD, [PostgreSQL schema specification](../docs/database/schema-v1.md), contracts, and traceability | P00-01 | Scope and key decisions reviewed | Conditionally approved |
| P02-01 | Toolchain, minimal service, Compose, Alembic, and CI | P01-01 | Python 3.14 dependencies, health checks, empty database migration, and CI verified | Delivered |
| P02-02 | Identity, households, and RBAC | P02-01 | Registration, login, rotation, isolation, and authorization tests | In progress |
| P03-01 | Ledger, payments, reversals, and reconciliation | P02-02 | Decimal precision, concurrent idempotency, and balance verification | Planned |
| P04-01 | Products, lots, movements, and checkout | P03-01 | Atomic rollback, ownership constraints, and concurrent deductions | Planned |
| P05-01 | FEFO, consumption, disposal, and expiry jobs | P04-01 | Time zone boundaries, partial deductions, and deduplication | Planned |
| P06-01 | Waste and financial reports | P05-01 | Reconciled lot valuation and currency grouping | Planned |
| P07-01 | Recipe matching and ranking | P05-01 | Stable order and expired lot exclusion | Planned |
| P08-01 | Frontend integration and three locales | P06-01, P07-01 | Critical E2E flows and keyboard paths | Planned |
| P09-01 | Security and reliability | P08-01 | Authorization audit, concurrency, and recovery rehearsal | Planned |
| P10-01 | Release and copyright evidence | P09-01 | Checklist, manuals, and release approval | Planned |
