# IMSF website (`web/`)

Standalone website for IMSF — landing + auth + app shell + blog — built
with Vite + React + TypeScript + Tailwind CSS v4 + DaisyUI 5. The Taro
app in `frontend/` stays for the WeChat Mini Program only.

## Stack (pinned exact)

- vite 8.3.8, @vitejs/plugin-react 6.3.0, react + react-dom 18.3.1,
  typescript 5.9.3, react-router-dom 6.30.6
- tailwindcss 4.3.0, @tailwindcss/vite 4.3.0, daisyui 5.8.2
- vitest 5.1.1 + jsdom + @testing-library/react (tests)

No MUI in this app (MUI is the fallback only — never mix DaisyUI + MUI).
No Google Fonts, no CDN assets: system font stack + self-hosted SVGs.

## Scripts

- `npm run dev` — dev server
- `npm run typecheck` — `tsc -b`
- `npm run lint` — oxlint
- `npm run test -- --run` — vitest (auth client + route guards)
- `npm run build` — `tsc -b && vite build`
- `npm run preview` — serve the production build (SPA fallback on)

## Theme

`src/index.css` registers the single DaisyUI theme `imsf-swiss`
(light only, dark mode off): accent `#C2410C`, surfaces `#FFFFFF` /
`#F7F7F8` / `#E3E3E4`, text `#1A1C1A` / `#5F6368`, radius 4px
(sidebar items radius 0, header buttons `rounded-full`). Tokens are
documented in the repo-root `DESIGN.md`; product truth in `PRODUCT.md`.

## Routes

- `/` landing (placeholder — Wave 2), `/login`, `/register`
  (placeholders — Wave 2 builds the forms)
- `/app/*` guarded (`RequireAuth` → `/login?next=<path>`):
  `/app`, `/app/upload`, `/app/fridge`, `/app/transactions`,
  `/app/spending`, `/app/mine`
- `/blog`, `/blog/:id` (placeholders — Wave 2)
- `*` 404

Auth client: `src/lib/auth.ts` — fetch-based, same-origin
`/api/v2/...`, localStorage keys `imsf2.access_token` /
`imsf2.refresh_token` / `imsf2.household_id`, single-flight refresh
(401 → refresh once → retry once; refresh fail → clear tokens →
`/login`). Ported from `frontend/src/services/auth.ts`.

## Deploy

Vercel, from `web/dist/`; `vercel.json` rewrites `/api/*` to the
Oregon backend via Caddy (`http://52.13.176.85/api/*`) and falls back
every other path to `/index.html` (SPA routing).
