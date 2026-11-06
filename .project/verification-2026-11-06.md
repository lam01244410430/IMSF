# Local verification on 2026-11-06

## Evidence

- Docker Desktop 4.88.1 / engine 29.7.2 is running. Existing `v10-db-1` provides PostgreSQL 16 on port 5433.
- Installed official image `postgrest/postgrest:v16.0`, digest `sha256:45674266ef004bc6676f98b12132f1da042de8b5237eff4e7af3c7bf6c510bfb`.
- Started separate Compose project `family-rest-smoke`. Verified PostgreSQL 16.15 and PostgREST 16.0. Ports 5544 and 3033 bind to 127.0.0.1.
- `./.venv/Scripts/python.exe tools/postgrest/smoke.py` passed OpenAPI, filtered GET, denied POST, hidden users, and unchanged fixture checks. The initial constant-view fixture rejected writes as non-updatable before permission evaluation. A SELECT-only table fixture allowed the intended permission check to pass.
- Created a fresh `p02_test_audit_<timestamp>` database with `docker exec family-rest-smoke-db-1 createdb -U postgres <name>`. Set `DATABASE_URL` using the generated sandbox password and `P02_DISPOSABLE_DATABASE` to that name. Ran `./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`. Result was 18 passed, 39 deprecation warnings, no skips. Coverage includes health/readiness, upgrade-downgrade-upgrade, metadata parity, seeded roles, and 14 invalid-write constraint cases with rollback checks.
- `./.venv/Scripts/python.exe -m pip check` reported no broken requirements. `./.venv/Scripts/python.exe -m compileall -q app migrations` and `git diff --check` passed. Git also reported line-ending conversion notices.

## Progress and limitations

P02-01 has commit `14a903b`. P02-02 is in progress with domain primitives, persistence helpers, security adapters, models and migration 000000000002 in the working tree. FastAPI registers health routes only. Registration, login, rotation, and household authorization HTTP workflows remain unfinished. Existing tests establish database constraints. Full authorization and concurrency acceptance remain pending. Finance, inventory, recipes, and frontend remain planned.

Warnings concern Windows asyncio policies scheduled for removal in Python 3.16 and Starlette's httpx TestClient integration. No project test failure was reproduced. Full security review and independent reviewer sign-off remain pending.

The multi-agent document contains historical claims of empty Git history and P02-02 being planned. Current Git history and task-board status supersede those claims.

## Coordination

Project records identify Peter in Muse as coordinator and Codex on lampro as executor. The desktop chat inventory showed only this project chat active and no chat named Peter. Peter's live Muse activity was not verified.
