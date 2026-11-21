# IMSF

**IMSF is the NEW system — a full rewrite: Household Inventory, Expense & Community Recipe System.** Renamed from IMSF-v2 in the November 2026 reform; IMSF v1 was removed in the same reform. This repo has its own port, database, and deployment.

## Stack

- **API:** FastAPI (Python 3.12) on port **8002** — `GET /health`, API under `/api/v2`
- **Database:** PostgreSQL 16, database `imsf` (container `imsf-db`, host port 127.0.0.1:55434)
- **Queue/cache:** Redis (container `imsf-redis`, host port 127.0.0.1:6379)
- **AI:** self-hosted Qwen 2.5 14B via Ollama on the GPU VM (`GPU_HOST`, ephemeral IP — see `.env.example`)
- **OCR:** Baidu 通用票据识别 (receipt recognition)

## Quick start (Oregon host)

```bash
cp .env.example .env   # fill in real values; never commit .env
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
set -a; source /home/ubuntu/imsf.env; set +a   # host env file (0600)
alembic upgrade head
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8002
curl http://127.0.0.1:8002/health   # {"status": "ok"}
```

## Layout

- `app/` — FastAPI application (`main.py`, `config.py`; `/api/v2` routers land in Step 1)
- `alembic/` — migrations (`versions/` empty until Step 1)
- `worker/` — receipt-processing worker (placeholder; implemented in Step 2)
- `tests/` — pytest suite

## Phase 1 spec

See `IMSF-v2-phase1-api-db-design.md` (13 tables, Alembic 0001+0002,
`/api/v2`, worker pipeline, 2% reconciliation rule, 50-receipt eval).
