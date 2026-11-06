# Local PostgREST smoke environment

Run from the repository root in PowerShell with Docker Desktop running Linux containers.

```powershell
& ./tools/postgrest/start.ps1
./.venv/Scripts/python.exe tools/postgrest/smoke.py
```

PostgreSQL listens on localhost port 5544 and PostgREST on localhost port 3033. The existing application database on port 5433 is separate. Startup generates passwords in the Git-ignored `.env.local` file in this directory. Keep that file private and retain it while reusing containers.

The dedicated `rest_smoke` database has a restricted login role, a read-only anonymous role, and one explicitly synthetic health fixture. Only `rest_probe` is exposed. Open <http://127.0.0.1:3033/> for OpenAPI or <http://127.0.0.1:3033/health> for the probe. Smoke checks verify OpenAPI discovery, filtered reads, denied writes, hidden users, and an unchanged fixture.

Stop without deleting storage using this command.

```powershell
docker compose --project-name family-rest-smoke --env-file tools/postgrest/.env.local -f tools/postgrest/compose.yaml stop
```

This is a disposable local test environment. Application workflows continue through FastAPI application services. These REST checks establish PostgREST connectivity and restricted access only. See the [official tutorial](https://docs.postgrest.org/en/stable/tutorials/tut0.html).
