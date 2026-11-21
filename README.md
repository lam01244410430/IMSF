# IMSF

**IMSF — Household Inventory, Expense & Community Recipe System (full rewrite).**
Renamed from IMSF-v2 in the November 2026 reform; IMSF v1 was removed in the
same reform. This repo has its own port, database, and deployment.

## Where it runs

- **Website:** https://imsf-web.vercel.app — `web/` (Vite + React + TS +
  DaisyUI 5.8.2 + Tailwind v4, theme `imsf-swiss`); routes `/`, `/login`,
  `/register`, `/app/*` (login required), `/blog`, `/blog/:id`, `/knowledge`.
  API calls go through the Vercel proxy `/api/*` → Oregon.
- **Working backend:** FastAPI on Oregon EC2 (52.13.176.85) port **8002** —
  `GET /health`, API under `/api/v2`. See `docs/operations.md`.
- **Backend mirror:** https://imsf-api.vercel.app — `/health` + OpenAPI only,
  not the working backend.
- **WeChat Mini Program:** `frontend/` (Taro) — Mini Program only. The Taro
  H5 build is retired (Phase 5): no H5 target in CI, nothing serves it; the
  website is `web/`.

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

Website: `cd web && npm ci && npm run dev` (build: `npm run build`).

## Layout

- `app/` — FastAPI application (`main.py`, `config.py`, `/api/v2` routers)
- `web/` — standalone website (Vite + React + TS + DaisyUI); `PRODUCT.md` /
  `DESIGN.md` at the repo root are its hand-written Impeccable equivalents
- `frontend/` — Taro React app for the WeChat Mini Program only
- `alembic/` — migrations (head: 0007, recipe likes/saves)
- `worker/` — receipt-processing worker (Redis queue)
- `tests/` — pytest suite
- `docs/` — operator notes (`docs/operations.md`)

## Design docs

- `IMSF-v2-phase1-api-db-design.md` (13 tables, Alembic 0001+0002,
  `/api/v2`, worker pipeline, 2% reconciliation rule, 50-receipt eval)
- `IMSF-v2-phase2-api-db-design.md` (fridge, transactions, spending,
  notifications, shopping lists, maintenance, RAG)
- `IMSF-v2-frontend-design.md` (Taro Mini Program design; §8.8 records the
  retired H5 target)
- Reform plan: `IMSF-cai-cach-ke-hoach.md` (kept outside the repo, in the
  operator's files)
