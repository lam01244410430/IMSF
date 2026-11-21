# Product

IMSF — a family household management system: snap a receipt and the fridge
and the expense book are both recorded. Built for families who cook at home,
track what they spend, and want nothing wasted.

> Source: IMSF reform plan (`IMSF-cai-cach-ke-hoach.md`, 2026-11-21, Lam
> approved the whole reform 2026-11-21 20:51, new name IMSF) and the shipped
> IMSF-v2 Phases 1–2 + frontend FE-01–FE-04. Written by hand following the
> Impeccable `init` flow — the `/impeccable init` slash command is not
> available to this agent, so this file is the manual equivalent. No fact
> here is inferred beyond the plan and the shipped code; anything still
> undecided is marked as such.

## Platform

- **web** — a standalone website in `web/` (Vite + React + TypeScript),
  containing the landing page, auth pages, app shell, and blog.
- **WeChat Mini Program** — the existing Taro build (`frontend/`) stays for
  the Mini Program only. Taro H5 was retired in Reform Phase 5
  (decision §10 Q1 of the plan); the H5 build target was removed from
  frontend CI and the website is `web/`.

## Stack

- Backend: Python FastAPI, API `/api/v2`, on Oregon EC2 :8002 behind Caddy
  :80; PostgreSQL + Redis. No API change in this reform.
- Website (`web/`): Vite 8.3.8 + React 18.3.1 + TypeScript 5.9.3 +
  Tailwind CSS 4.3.0 + DaisyUI 5.8.2 (themes `imsf-swiss` light +
  `imsf-swiss-dark`, default light, choice in localStorage
  `imsf.theme`), react-router-dom
  6.x. MUI is the fallback only and is NOT installed in `web/`.
- Mini Program (`frontend/`): Taro 4.3.3 + React 18 + MUI 9.5.0 (H5) +
  NutUI 3.0.20 (Mini Program). Never mix DaisyUI + MUI in one app.
- Design method: Impeccable (pbakaus/impeccable v4.10.0) — a design skill
  for coding agents, NOT a component library; nothing to import.

## Users

- **Primary user:** a family that cooks at home — one household, several
  members sharing one fridge and one expense book.
- **Situation:** after grocery shopping, someone photographs the receipt;
  during the week, members check what is about to expire and what was spent.
- **Job to be done:** know what food is in the fridge and when it expires,
  know what the household spent and on what, and cook from what is about to
  expire instead of wasting it.
- **China-first:** default language zh-CN, default currency CNY, default
  timezone Asia/Shanghai; Vietnamese and English interfaces supported.
  Receipt OCR covers simplified-Chinese and Vietnamese supermarket receipts.

## Product Purpose

One receipt photo drives two records: the ingredients go into the fridge
with shelf-life reminders, and the spending goes into the expense book.
Around that core, IMSF provides:

1. **Receipt scan** — photograph a receipt; OCR + LLM extract items, prices
   and totals; the user confirms, then items enter the fridge and the
   expense is booked.
2. **Smart fridge + Lazy Tracking** — every ingredient has a shelf-life
   reminder; when something is about to expire, IMSF asks one question and
   the user answers in one tap (finished it, or keep three more days).
3. **Expense book** — manual entries or automatic booking from receipts;
   monthly view, by-category totals, 14 currencies summed only within one
   currency, never mixed, never converted.
4. **Community recipes** — a public blog (`/blog`) sharing recipes, so
   families can see what others cooked from soon-to-expire ingredients;
   like/save, and one-tap shopping lists (posting + comments deferred).
5. **Appliance maintenance** — purchase date and maintenance cycle per
   appliance, reminders before due, records always checkable.

## Positioning

- IMSF is **one household system** (scan + fridge + ledger + recipes +
  maintenance), not a catalogue of separate products and not an enterprise
  reporting tool. It is designed for a family's daily cooking, bookkeeping
  and fridge management.
- Free for family use. No paid plan, no advertising in the interface
  (advertising-free is a product commitment to confirm, plan §4.4).
- The website's three modes (Impeccable): landing = Persuade, app =
  Operate, blog = Read.

## Operating Context

- **China-first, GFW reality:** Google Fonts and Google-hosted assets are
  blocked in China, so the site uses **system fonts only** and self-hosts
  every asset (icons as local SVG files, no icon font via CDN, no emoji as
  icons). Nothing is fetched from a third-party CDN at runtime.
- **14 currencies, no conversion:** CNY, VND, USD, EUR, HKD, THB, MYR,
  SGD, IDR, PHP, KHR, LAK, MMK, BND. Amounts are summed only within one
  currency.
- **Auth split:** website uses **email + password** login (register/login
  endpoints, argon2id); the WeChat Mini Program uses **WeChat login**.
  Tokens use the existing keys `imsf2.access_token` /
  `imsf2.refresh_token` / `imsf2.household_id`, single-flight refresh.
- **WeChat template messages are NOT available:** Lam's Mini Program
  account has no template-message function (error 48001, confirmed
  2026-11-21). Notifications run on the in-app channel (the designed
  fallback). Do not design a flow that depends on WeChat template messages.
- **No automatic shutdown of the GPU host; no deployment without Lam's
  separate approval.** Verification green auto-pushes/auto-merges; deploy
  still needs his word.
- **Dark mode (Dashboard Phase A, 2026-11-22):** two DaisyUI themes,
  `imsf-swiss` (light, default) + `imsf-swiss-dark`; the choice is
  stored in localStorage `imsf.theme` and applied before first paint
  by an inline script in `web/index.html` (no flash of the wrong
  theme). `prefers-color-scheme` is never consulted. The toggle sits
  in every header (landing, public, auth, app topbar) + the 我的 page
  (segmented 外观 control). All custom CSS colours are `var(--im-*)`
  (see DESIGN.md); the header follows the page theme. The language
  dropdown panel is âm tường — same background as the header, no
  shadow, one hairline — in both themes. The hero is a solid dark
  band (no gradient, no mock screenshot) with the real dashboard
  screenshot inside it: `web/public/dashboard-hero.png` (1280×860,
  light theme, from the Phase B verification session 2026-11-22 —
  real `/app/dashboard` data; the milk row was inserted directly
  into the DB, see the plan note).
- **User dashboard (Dashboard Phase B, 2026-11-22):** `/app/dashboard`
  is the post-login destination (D1 — replaces the Q2 redirect to
  `/app/upload`); the sidebar's first item is 仪表盘 (icon `home`),
  there is no 首页 nav item and no duplicate 拍照 nav item
  (`/app/upload` stays reachable via the sidebar 拍照 button + the
  mobile FAB). 7 widgets, all from existing endpoints: monthly
  spending (household default currency, top 3 categories), expiring
  soon (Lazy Tracking 1-tap 已用完 / 再放三天), recent transactions
  (8), quick actions, fridge counts, upcoming maintenance (dated
  only, overdue first), unread notifications. The notifications
  widget is non-navigating — there is no notifications page and no
  mark-as-read endpoint; the unread count reuses the bell's
  client-side "seen" set (`imsf2.notifications_seen`) and the hint
  points at the topbar bell. Every widget has an honest empty state
  for a new household. Layout: desktop 12-column grid (8+4 / 8+4 /
  4+4+4), mobile 1 column, quick actions a 2×2 grid. Hero image:
  `web/public/dashboard-hero.png` — the 1280 light screenshot from
  the Phase B verification session (milk row visible, chip 还剩 2 天).
- **Dark error-text correction (R3):** the plan's dark error `#EF5350`
  is 4.38:1 on card surfaces (below 4.5:1), so dark error *text* is
  `#FF8A80` (6.69:1 on cards); `#EF5350` survives only as DaisyUI
  `--color-error` (a background) with dark content `#1A1C1A`.
- **Known light-theme gap (R7, documented, not fixed):** the light
  input border `#E3E3E4` on white is 1.28:1 (below WCAG 1.4.11's 3:1
  for UI boundaries) — kept deliberately to avoid visibly changing
  the approved light design; the `:focus-visible` ring is the focused
  boundary. The dark input border `#6E756E` passes (3.62:1 / 3.22:1).

## Capabilities and Constraints

Capabilities (shipped): Phase 1 receipt pipeline (OCR → Qwen 14B JSON
contract → 2% reconciliation → inventory) with 13 tables; Phase 2 (fridge,
transactions, per-currency spending summary, notifications, shopping lists,
equipment maintenance, RAG shelf-life) with 20 tables; Phase 3 email login
(migration 0006) with 22 tables; frontend FE-01–FE-04 (Taro + MUI/NutUI,
Swiss style, desktop shell ≥1024px).

Constraints that future work must preserve:

- **Swiss anchor + one accent:** fresh bright white surfaces, hairline
  1px dividers, left-aligned type, and a single accent, dark orange
  `#C2410C`. No decorative gradients of any kind.
- **System font stack only** — `"PingFang SC", "Hiragino Sans GB",
  "Microsoft YaHei", system-ui, -apple-system, "Segoe UI", sans-serif`.
  No Google Fonts, no web fonts at all.
- **No guessed blue:** the guessed info blue `#1565C0` was deleted; info
  states fall back to accent + icon. Green `#2E7D32` is semantic success
  only.
- **No fabricated content:** no invented reviews, star ratings, user
  counts, prices, or legal text. Empty review slots stay visibly empty
  until real feedback exists; the privacy-policy / terms pages stay
  "being written" until real text exists.
- **Known open gaps (do not paper over):** D-F3 added receipt lines
  return 422 on the current backend (confirm only UPDATEs, never
  INSERTs — needs a backend change); SMS OTP H5 login, offline
  queue and WebSocket are deferred. (Dark mode shipped in Dashboard
  Phase A; the `#D32F2F` error-text gap is closed too — all light
  error text is now `#B71C1C`.)

## Brand Commitments

- **Name:** IMSF (product-facing). `IMSF-v2` is an internal repo/brand
  block name and does not appear on the landing page.
- **Visual identity:** Swiss anchor (see DESIGN.md), accent `#C2410C`,
  fresh bright white, no cream / warm paper.
- **Language:** UI copy in zh-CN by default; every user-facing string
  exists in zh-CN, vi and en.
- **Honesty:** the product never claims what it cannot do — the FAQ
  answer about login states the post-reform truth (web = email, Mini
  Program = WeChat), and the reviews section shows empty slots rather
  than invented testimonials.

## Evidence on Hand

- Reform plan `IMSF-cai-cach-ke-hoach.md` (§§1–11, 17 decisions Q1–Q17
  approved by Lam 2026-11-21 20:51).
- Design docs `IMSF-v2-phase1-api-db-design.md` and
  `IMSF-v2-phase2-api-db-design.md`; frontend design doc + Figma file
  `IMSF-v2` (`jL0zlVLR9NxURqHV5OOZaq`, Screen 1 built; MCP blocked on
  Starter tool-call limit).
- Shipped code: backend main @ 20c908b (Phase 2 email login); frontend
  FE-01–FE-04 on main; live API on Oregon :8002; H5 at
  https://imsf-v2-web.vercel.app (verified working via Vercel proxy).
- DaisyUI decision: Codex verdict 2026-11-21 ~20:47 — DaisyUI 5.8.2 +
  Tailwind v4 for `web/`, Impeccable for quality control, MUI as fallback.
- The >90% receipt-eval gate still needs 50 real simplified-Chinese +
  Vietnamese supermarket receipts (the Taiwan B2B invoice dataset Lam
  uploaded is NOT usable for it).

## Product Principles

1. **One photo, two records.** Every flow is judged by whether the
   receipt-to-fridge-and-ledger path gets shorter.
2. **Verify by looking.** Ship only what a real render at real sizes
   proves: screenshots at 375px / 768px / 1024px / 1280px, computed
   styles, and test counts — never an agent's self-report alone.
3. **Nothing invented.** Meanings, conclusions, numbers and copy come
   from a source or a draft Lam approved; a field the source lacks stays
   empty.
4. **Small decisions without asking, Lam-only choices brought once.**
   Verify-green auto-pushes and auto-merges; deploy needs Lam's separate
   approval.
5. **Plans first, then small implementation steps after scope is
   approved.** Proposals stay proposals until Lam confirms them.

## Accessibility & Inclusion

- All text ≥ 4.5:1 contrast against its background in BOTH themes
  (contrast table in DESIGN.md, dark palette added in Dashboard
  Phase A). Never use `#79747E` (outline) as text colour; never use
  warning `#B45309` on white at 12px.
- Every interactive element has a visible `:focus-visible` outline:
  2px solid `var(--im-focus)` (`#9A3412` light / `#F97316` dark),
  offset 2px.
- Real links and buttons (not divs with click handlers), labels on
  inputs, `aria-current` on the active nav item, `aria-expanded` /
  `aria-controls` on the FAQ accordion.
- Touch targets ≥ 44px; sidebar nav items are 48px high × 240px wide.
- No information hidden behind hover: labels are always visible; icons
  are decorative (`aria-hidden="true"`).
