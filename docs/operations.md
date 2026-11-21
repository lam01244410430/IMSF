# IMSF — Operations note

Short, verified facts for whoever runs the live system. Last updated in
Dashboard Phase A (2026-11-22, branch `task/DASH-A-header-darkmode`).
Nothing here is a guess: every item was read from the live host or the code.

## Backend — Oregon EC2 (52.13.176.85)

- **Live API:** uvicorn on port **8002** (`app.main:app`), behind Caddy on
  port 80. Caddy proxies `/api/v2/*` → 127.0.0.1:8002 and `/api/chat*` →
  127.0.0.1:5000 (Guiyan agent — do not touch).
- **Start/restart:** `/tmp/start_uvicorn_imsf.sh` — run detached with
  `setsid nohup` (a plain `nohup ... &` over SSH dies when the session
  drops). The script has **no `--reload`**: uvicorn does **NOT auto-reload
  after a merge**. After every merge that changes the backend, kill the old
  process, restart on main with that script, and verify `/health` plus the
  OpenAPI routes.
- **Root path quirk:** `GET http://52.13.176.85/` returns **200 with an
  empty body** — Caddy has no handle for `/`, so this is expected, not an
  error. Real API traffic is under `/api/v2/*` (unknown path → 404 JSON
  from uvicorn).
- **Vercel backend mirror:** https://imsf-api.vercel.app serves `/health`
  + OpenAPI only. It is **not** the working backend; Oregon :8002 is.
- **Protection Bypass for Automation:** a bypass secret was added to the
  backend Vercel project (`prj_HSPRBiXTF4DtdRtRjMUXUi4TVruD`) by `vercel
  curl` during Phase 1B. Revoke it from the Vercel dashboard when
  convenient.

## Daily cron — 08:00 Asia/Shanghai

```
0 8 * * * cd /home/ubuntu/IMSF && set -a; . /home/ubuntu/imsf.env; set +a; .venv/bin/python -m app.jobs.daily && .venv/bin/python -m app.jobs.send_wechat >> /home/ubuntu/imsf-jobs.log 2>&1
```

- Env file `/home/ubuntu/imsf.env` is mode **0600**, owned by `ubuntu`.
  Never print it, never commit it.

## Email login (Phase 2, migration 0006)

- Endpoints `POST /api/v2/auth/email/register` and `/login`; passwords are
  argon2id hashes (`password_hash` column). **No email verification in v1**
  (no SMTP) and **no forgot/reset/change-password endpoint**.
- **Admin password reset (server-side only):**
  `/home/ubuntu/IMSF/scripts/admin_reset_password.py` — run on the server
  over SSH. There is no HTTP reset flow.
- **Two separate user rows:** a person with both a WeChat account and an
  email account has **two separate rows in `users`** in v1 (no linking).
- **Email validation, verified from code (2026-11-22):** the endpoints use
  pydantic `EmailStr` (`app/api/auth.py`) with `email-validator==2.4.0`
  (`requirements.txt`); no `check_deliverability` is configured anywhere,
  so validation is **syntax-only — no DNS/MX deliverability check**. A
  syntactically valid but nonexistent domain (e.g.
  `user@nonexistent-domain-xyz123.com`) **passes**. Rejected: missing `@`,
  single-label domains (`a@b`, `user@localhost`), IP-literal domains, and
  reserved/special-use names (`.invalid` TLD). The app strips whitespace
  and lowercases the whole address before storage; invalid syntax returns
  422. Pydantic version in the live venv: 2.14.4.

## /knowledge and the GPU

- **GPU host `qwen-gpu-server` is OFF** on Lam's order (since 2026-11-21).
  Do not start it without Lam's explicit order; its external IP is
  ephemeral and may change on restart.
- While the GPU is off, **live `/knowledge` search returns 500** (the
  embedding service is unreachable). Re-check citations when Lam restarts
  the GPU. Everything else on the website works without the GPU.

## Dark mode + header (Dashboard Phase A, 2026-11-22)

- Two DaisyUI themes in `web/src/index.css`: `imsf-swiss` (light,
  default) + `imsf-swiss-dark`. All custom CSS colours are
  `var(--im-*)` — no hardcoded hex outside the theme blocks and the
  variable definitions.
- **Theme choice:** localStorage `imsf.theme` (`light` | `dark`),
  default light. An inline script in `web/index.html` applies it
  before first paint (no flash of the wrong theme). If a CSP is ever
  added, that script needs `'unsafe-inline'` or a hash.
  `prefers-color-scheme` is never consulted anywhere.
- **Toggle:** in every header (landing, public, auth, app topbar) +
  the 我的 page (segmented 外观 control). Both read the same
  `ThemeProvider` context.
- **Logo:** `web/src/assets/logo-dark.svg` is the dark wordmark; the
  header swaps `src` by theme.
- **Verify both themes:** build `web/` (`npm run build`), then check
  the landing / login / register pages at 1280px + 375px in light and
  dark, the language dropdown open (must read as a flat extension of
  the header — no shadow), and a hard reload with
  `localStorage['imsf.theme']='dark'` (first paint must already be
  dark).

## Website deploys

- Website: https://imsf-web.vercel.app (Vercel project `imsf-web`,
  Git-linked to `main`, deploys `web/dist/`; `/api/*` rewrites to
  `http://52.13.176.85/api/*` via `web/vercel.json`). A push to `main`
  redeploys it; pushes to other branches do not change the live site.
- Custom domain `imsf.whodesignthis.com` is still deferred: it needs Lam's
  DNS step (A record `imsf` → 52.13.176.85).
