# GitHub publication verification - 2026-11-06

Target: https://github.com/lam01244410430/IMSF.git. User explicitly authorized uploading this project. The remote main branch initially contains only README.md in commit 4b37794886f2e5fbffbe0d56582259d7ea02e7f4. Preserve that commit as an ancestor; do not force-push.

Scope includes the current in-progress application snapshot, project documentation, and shareable Graphify outputs. Ignore environment files, Graphify caches, interpreter/root paths, manifests, and intermediate extraction audits.

Evidence before publication:
- All 18 existing tests passed, no skips, with 39 deprecation warnings, on a newly created isolated p02_test_publish_* database in the existing local PostgreSQL sandbox.
- pip check: no broken requirements. compileall for app, alembic, migrations, and tests passed.
- Credential-pattern scan returned zero matches; no candidate file exceeded 10 MB. This is a limited pattern scan, not a complete security audit.
- Read-only review identified that the candidate CI workflow did not create its configured database and lacked the current disposable-database opt-in. Configure the fresh service database as p02_test_ci and set matching DATABASE_URL/P02_DISPOSABLE_DATABASE.
- Remote workflow execution remains unverified until GitHub returns a result for the published commit.
- P02-02 remains in progress. Existing tests cover database constraints and health, not completed identity HTTP authorization workflows.
