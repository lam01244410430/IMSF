---
name: IMSF
description: Swiss family household system — fresh white, hairline dividers, one dark-orange accent.
colors:
  primary: "#C2410C"
  primary-deep: "#9A3412"
  primary-bright: "#EA580C"
  primary-tint: "#FFE0B2"
  primary-active-bg: "rgba(194,65,12,0.08)"
  surface: "#FFFFFF"
  background: "#F7F7F8"
  divider: "#E3E3E4"
  on-surface: "#1A1C1A"
  on-surface-variant: "#5F6368"
  success: "#2E7D32"
  error: "#D32F2F"
  error-container: "#FCE8E6"
  warning: "#B45309"
typography:
  h1:
    fontFamily: "\"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", system-ui, -apple-system, \"Segoe UI\", sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: "36px"
  h2:
    fontFamily: "\"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", system-ui, -apple-system, \"Segoe UI\", sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: "32px"
  body:
    fontFamily: "\"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", system-ui, -apple-system, \"Segoe UI\", sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "\"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", system-ui, -apple-system, \"Segoe UI\", sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  base: "4px"
  sidebar-item: "0px"
  header-button: "9999px"
spacing:
  sidebar-width: "240px"
  topbar-height: "64px"
  content-max-width: "1200px"
  nav-item-height: "48px"
  nav-item-padding-left: "24px"
  icon-gap: "12px"
  section-gap: "64px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.base}"
  button-primary-hover:
    backgroundColor: "{colors.primary-deep}"
    textColor: "{colors.surface}"
    rounded: "{rounded.base}"
  sidebar-nav-item:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.sidebar-item}"
    height: "{spacing.nav-item-height}"
  sidebar-nav-item-hover:
    backgroundColor: "{colors.background}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.sidebar-item}"
    height: "{spacing.nav-item-height}"
  sidebar-nav-item-active:
    backgroundColor: "{colors.primary-active-bg}"
    textColor: "{colors.primary}"
    rounded: "{rounded.sidebar-item}"
    height: "{spacing.nav-item-height}"
---

# Design System: IMSF

> Recorded from the shipped system (FE-02 Swiss style + FE-04 desktop
> web), following the Impeccable `document` flow — the `/impeccable
> document` slash command is not available to this agent, so this file is
> the manual equivalent. Tokens are normative; prose explains how to apply
> them. Source of truth for values: `frontend/src/ui/tokens.ts` (Taro)
> and the DaisyUI theme `imsf-swiss` in `web/src/index.css` (website).
> Do NOT copy the old `tokens.shape` (base 12 / button 20 / card 16) —
> the website uses 4px everywhere except the header buttons and the
> radius-0 sidebar items.

## Overview

IMSF's visual world is the **Swiss anchor**: fresh bright white surfaces,
one neutral grey, hairline 1px dividers, left-aligned type, and a single
dark-orange accent used with intent. No decorative gradients, no
cards-in-cards, no rounded icon tiles on headings, no cream or warm paper.
The accent is a deliberate deviation from the Swiss token International
Orange `#FF4F00` (Lam, 2026-11-21: `#FF4F00` is too harsh; `#C2410C` is
calmer and small orange text on white passes 4.5:1 at 5.18:1).

Three surfaces, three Impeccable modes: landing = Persuade, app =
Operate, blog = Read. The app is restraint and precision; the landing
earns attention with the same tokens, not a different palette.

## Colors

### Primary

- **Accent `#C2410C`** (Tailwind Orange 700) — the only brand/action
  colour. Filled buttons, active nav text and left bar, links, primary
  CTAs. White text on it is 5.18:1; `#C2410C` text on white is 5.18:1.
- **Accent dark `#9A3412`** — filled-button hover and the
  `:focus-visible` outline colour. Never a text colour on white at small
  sizes except as an outline. In dark the focus outline is `#F97316`;
  text-link hovers also use the focus colour (light `#9A3412`
  unchanged, dark `#F97316`) so they keep contrast on dark surfaces.
- **Accent bright `#EA580C`** — one step above the accent; sparing use
  only, never as body text.
- **Accent container `#FFE0B2`** — pale orange container; dark text
  `#1A1C1A` on it is 13.52:1.
- **Active tint `rgba(194,65,12,0.08)`** — the active sidebar-item
  background (kept exactly from FE-04, token `action.hover`).

### Secondary (omitted)

There is no secondary brand colour. Secondary, accent and info slots in
the DaisyUI theme all map to `#C2410C` with white content — one accent,
no second voice.

### Tertiary (omitted)

No tertiary colour. Semantic colours below are functional, not brand.

### Neutral

- **Surface `#FFFFFF`** — page and card background, sidebar background.
- **Background `#F7F7F8`** — the single neutral grey: page background
  behind white surfaces, sidebar hover background, trust-block band.
- **Divider / surface variant `#E3E3E4`** — hairlines, pressed states.
- **On-surface `#1A1C1A`** — primary text. On white 17.14:1; on
  `#F7F7F8` 16.01:1.
- **On-surface variant `#5F6368`** — secondary text and resting icons.
  On white 6.05:1; on `#F7F7F8` 5.65:1.
- **Outline `#79747E`** — never a text colour.

### Named Rules

- **Semantic green `#2E7D32` is success only** (completed / success
  states, check marks). It is the old brand green, demoted.
- **Semantic error `#D32F2F`**, error container `#FCE8E6`. Chip text is
  darkened to `#B71C1C` (fixed 2026-11-21, Phase 3 app pages):
  `#B71C1C` on `#FCE8E6` is 5.58:1 (passes 4.5:1). Dashboard Phase A
  (2026-11-22) unified ALL light error text to `#B71C1C` — no
  `#D32F2F` text remains in `web/` (`.field-error`, `.auth-banner`
  border, `.auth-countdown`, `.blog-action-error`).
- **Semantic warning `#B45309`** — never as 12px text on white.
- **No blue anywhere.** The guessed info blue `#1565C0` was deleted;
  info states fall back to accent + icon.
- **Contrast table (verified):**

  | Text | On | Ratio | Pass 4.5:1 |
  |---|---|---|---|
  | `#1A1C1A` | `#FFFFFF` | 17.14:1 | yes |
  | `#1A1C1A` | `#F7F7F8` | 16.01:1 | yes |
  | `#5F6368` | `#FFFFFF` | 6.05:1 | yes |
  | `#5F6368` | `#F7F7F8` | 5.65:1 | yes |
  | `#C2410C` | `#FFFFFF` | 5.18:1 | yes |
  | `#FFFFFF` | `#C2410C` | 5.18:1 | yes |
  | `#C2410C` | active tint on white | ≈5.18:1 | yes |
  | `#D32F2F` | `#FCE8E6` | 4.23:1 | **no — do not ship text at this ratio** |
  | `#B71C1C` | `#FCE8E6` | 5.58:1 | yes (chip text — the fix) |
  | `#B45309` | `#FFF7ED` | 4.73:1 | yes (warning chip) |
  | `#2E7D32` | `#E8F5E9` | 4.56:1 | yes (success chip) |
  | `#C2410C` | `#FDEDE8` | 4.55:1 | yes (accent chip) |

### Dark theme (`imsf-swiss-dark`, Dashboard Phase A, 2026-11-22)

- **Second DaisyUI theme** in `web/src/index.css`, `prefersdark: false`
  on both themes. Default **light**; the choice is stored in
  localStorage `imsf.theme` and applied before first paint by an
  inline script in `web/index.html`. `prefers-color-scheme` is never
  read. Toggle in every header + the 我的 page (segmented 外观
  control); the two controls share one context, so they can never
  disagree.
- **All custom CSS colours are `var(--im-*)`** (plain CSS `:root` /
  `[data-theme]` definitions, not inside the DaisyUI `@plugin`
  blocks). Light values are the previous hardcoded values (the light
  theme renders as before, except the two deliberate unifications
  below); dark values:

  | Variable | Light | Dark |
  |---|---|---|
  | `--im-bg` (page / header / drawer) | `#FFFFFF` | `#1A1C1A` |
  | `--im-surface` (cards, dialogs, inputs) | `#FFFFFF` | `#232625` |
  | `--im-surface-2` (bands, skeletons, tracks) | `#F7F7F8` | `#2A2E2C` |
  | `--im-text` | `#1A1C1A` | `#EDEDE8` |
  | `--im-muted` | `#5F6368` | `#A8AFA9` |
  | `--im-border` (hairlines) | `#E3E3E4` | `#2A2E2C` |
  | `--im-border-strong` (input borders) | `#E3E3E4` | `#6E756E` |
  | `--im-accent` (button bg) | `#C2410C` | `#C2410C` |
  | `--im-accent-text` (links, active nav) | `#C2410C` | `#F97316` |
  | `--im-accent-tint` (active bg) | `rgba(194,65,12,0.08)` | `rgba(249,115,22,0.12)` |
  | `--im-focus` (outline) | `#9A3412` | `#F97316` |
  | `--im-success-text` | `#2E7D32` | `#4CAF50` |
  | `--im-error-text` | `#B71C1C` | `#FF8A80` |
  | `--im-warning-text` | `#B45309` | `#F59E0B` |
  | `--im-hover` (hover bg on page bg) | `#F7F7F8` | `#232625` |
  | `--im-hover-on-surface` (hover bg on a card/surface) | `#F7F7F8` | `#2A2E2C` |
  | `--im-pressed` (pressed bg) | `#E3E3E4` | `#2A2E2C` |
  | `--im-accent-hover` (button hover bg) | `#9A3412` | `#9A3412` |
  | `--im-chip-error-bg` | `#FCE8E6` | `#2E1B19` |
  | `--im-chip-warning-bg` | `#FFF7ED` | `#2E2410` |
  | `--im-chip-success-bg` | `#E8F5E9` | `#1C2B1E` |
  | `--im-chip-accent-bg` | `#FDEDE8` | `#33200F` |
  | `--im-chip-neutral-bg` | `#F7F7F8` | `#2A2E2C` |
  | `--im-notice-success-border` | `#C8E6C9` | `#2E4A2E` |
  | `--im-notice-error-border` | `#F5C6CB` | `#5A2B28` |
  | `--im-notice-success-text` (notice success text) | `#1B5E20` | `#4CAF50` |
  | `--im-overlay` (drawer overlay) | `rgba(26,28,26,0.4)` | `rgba(0,0,0,0.6)` |
  | `--im-backdrop` (dialog backdrop) | `rgba(26,28,26,0.5)` | `rgba(0,0,0,0.6)` |
  | `--im-shadow` (`.notif-panel` shadow only) | `rgba(26,28,26,0.12)` | `rgba(0,0,0,0.4)` |
  | `--im-on-accent` (text on accent bg) | `#FFFFFF` | `#FFFFFF` |
  | `--im-error-solid` (`.btn-error` bg, notif badge) | `#B71C1C` | `#B71C1C` |
  | `--im-error-solid-hover` (`.btn-error` hover) | `#9C1B1B` | `#9C1B1B` |
  | `--im-hero-bg` / `--im-hero-text` / `--im-hero-muted` / `--im-hero-accent-text` / `--im-hero-check` | `#1A1C1A` / `#EDEDE8` / `#A8AFA9` / `#F97316` / `#4CAF50` | `#232625` / same / same / same / same |
- **Two deliberate light unifications:** all light error text is now
  `#B71C1C` (was `#D32F2F` in 4 places — `.field-error`,
  `.auth-banner` border, `.auth-countdown`, `.blog-action-error`);
  nothing else in light changed.
- **Correction R3:** the plan's dark error `#EF5350` is 4.38:1 on
  card surfaces, so dark error *text* is `#FF8A80`; `#EF5350` is kept
  only as DaisyUI `--color-error` (background) with dark content
  `#1A1C1A` (4.92:1).
- **Documented gap R7:** the light input border `#E3E3E4` on white is
  1.28:1 (below WCAG 1.4.11's 3:1) — kept deliberately; the dark
  border `#6E756E` passes (3.62:1 / 3.22:1).
- **Forbidden in dark (all measured):** `#C2410C` as text on dark
  (3.31:1); `#EA580C` as text on a dark card (4.29:1) or as a button
  background with white text (3.56:1); light success/error/warning
  (`#2E7D32` / `#D32F2F` / `#B45309`) as text on dark (~3.4:1);
  `#EF5350` as text on a dark card (4.38:1); white text on `#EF5350`
  (3.49:1). `#FFE0B2` and `#EA580C` are documented but unused in
  `web/` — no dark equivalents exist.
- **Header follows the page theme** (light header in light mode, dark
  header in dark mode — D3, NOT a fixed dark header). The language
  dropdown panel is **âm tường**: same `background` as the header
  (`var(--im-bg)`), `box-shadow: none`, `border-radius: 0`, edges
  aligned with the header, separated only by a 1px hairline at the
  panel's bottom edge. Any visible shadow or floating edge = FAIL.
  The notification panel (`.notif-panel`) is the one exception — it
  is a floating card and keeps its shadow.
- **Hero band:** the hero section is a full-width SOLID dark band (no
  gradient), single-column text, in both themes (light band `#1A1C1A`,
  dark band `#232625` + a 1px `#6E756E` bottom edge). The grey
  `.phone-mock` is deleted; no fabricated screenshot. The real
  dashboard screenshot is in place since Phase B:
  `web/public/dashboard-hero.png` (1280×860, light theme — chosen over
  the dark shot because the light shot separates cleanly from the dark
  band; the dark shot would blend into it). Shot 2026-11-22 from the
  live branch build against the Oregon backend, test account, real API
  data; the milk row was inserted directly into the DB (no POST /fridge
  endpoint exists). The figure sits inside the band below the CTAs
  (`.hero-shot`, hairline frame, 4px radius, caption in
  `--im-hero-muted`); above the fold, so no lazy-loading; width/height
  set to stop layout shift.
- **Logo:** `web/src/assets/logo-dark.svg` (same geometry as
  `logo.svg`, text `#EDEDE8`); the header swaps the `src` by theme.
  Never `filter: invert()` on the light logo (it turns the accent
  square cyan).

### User dashboard (`/app/dashboard`, Dashboard Phase B, 2026-11-22)

- **Grid:** 12 columns, 16px gaps, `align-items: start`; row 1
  spending (span 8) + expiring (span 4); row 2 recent (span 8) +
  quick actions (span 4, sticky); row 3 fridge + maintenance +
  notifications (span 4 each). Below 1024px a single column in the
  same order; quick actions are a 2×2 grid at all widths
  (`.dash-quick-list`).
- **Cards:** `var(--im-surface)` background, 1px `var(--im-border)`
  hairline, 4px radius, 16px padding, no shadows. Card headers are
  a 16px semibold title + a small accent "查看全部" link on the
  right (Figma "Dashboard (Community)" layout take: KPI row, wide
  list + narrow panel, consistent card headers — restyled to
  imsf-swiss; its pale blue-grey backgrounds, soft shadows, large
  radii and blue/purple accents were deliberately NOT taken).
- **Type:** 28px page title + spending total, 16px widget titles
  and count numbers, 14px body; 12px only inside the existing
  StatusChip (caption). One system font family, one accent
  (`#C2410C` light / `#F97316` accent text in dark); semantic
  colours only for expiry/maintenance status, always with text,
  never colour alone.

## Typography

- **System fonts only.** `"PingFang SC", "Hiragino Sans GB",
  "Microsoft YaHei", system-ui, -apple-system, "Segoe UI", sans-serif`.
  No Google Fonts, no web fonts, no Noto / Source Han (to avoid any
  confusion with Google standards). Fonts come from the user's own
  device, so the Great Firewall cannot block them.
- **Base:** 16px / 1.5, weight 400, colour `#1A1C1A`.
- **h1:** 28px mobile / 32px desktop, weight 700, `#1A1C1A`. Landing
  hero headline: 28px mobile / 32px desktop.
- **h2:** 24px, weight 700 (feature-block titles).
- **Labels / nav:** 14px. Sidebar labels 14px; footer household name
  13px, `onSurfaceVariant`.
- **No Inter, no single font for everything** — the stack is the system
  CJK stack, not a downloaded face.

### Hierarchy

Left-aligned type throughout (Swiss). One filled CTA per screen. Section
titles stand alone — no rounded icon tile above a heading. Numbers that
mark steps ("1 / 2 / 3") are large accent text (28px/700), not icon
tiles.

### Named Rules

- **The no-line rule for copy:** a label never wraps to hide meaning —
  the longest sidebar label, 消费统计 (4 chars + 20px icon), must not
  wrap at 240px width.
- **Grey text on coloured backgrounds is banned** — every text/background
  pair comes from the contrast table above.

## Layout

- **Desktop shell (≥1024px):** fixed left sidebar 240px + topbar 64px +
  content max-width 1200px, left-aligned. Sidebar: white `#FFFFFF`,
  1px right hairline `#E3E3E4`; brand block 64px; nav item 48px high,
  padding-left 24px; hairline divider between the two nav groups;
  full-width 拍照 button (margin 16px, height 48px); footer household
  name 13px.
- **Below 1024px:** the mobile layout — bottom nav + centre FAB, no
  sidebar. There is no separate tablet shell; 768–1023px uses the
  mobile layout widened, with blog grid at 2 columns and content
  padding 24px (max-width 720px).
- **Breakpoints:** xs 0, sm 768, md 1024, lg 1440, xl 1920. The only
  shell threshold is 1024px; 768px changes only blog columns and
  padding (24px instead of 16px).
- **Landing header:** sticky, 64px, white in light mode (dark in dark
  mode — the header follows the page theme), 1px bottom hairline,
  horizontal padding 24px (16px mobile). Left: logo + name IMSF + 4
  menu items (功能 / 使用方法 / 菜谱 / 常见问题). Right: theme toggle
  + language switcher (custom dropdown panel: name + short code
  EN / 中文 / VI + tick, âm tường — same background as the header, no
  shadow) + 登录 text button + 注册 filled accent button (radius
  20px, height 44px). Below 768px: logo + hamburger; menu + theme +
  language + auth move into a drawer.
- **Feature blocks:** flat sections separated by whitespace + hairline
  when needed, 64px apart, alternating left/right on desktop. No
  cards-in-cards.
- **Blog:** 3-column grid desktop, 2-column tablet, 1-column mobile.

## Elevation & Depth

- **Flat.** No shadows, no elevation scale: DaisyUI `--depth: 0`,
  `--noise: 0`. Separation comes from hairlines and whitespace, not
  shadow.
- **Hairline:** 1px `#E3E3E4` everywhere a divider is needed.

### Shadow Vocabulary (if applicable)

None — the system has no shadows by design.

### Named Rules

- **The flat-separation rule:** if two blocks need separation, use a
  hairline or 64px of whitespace — never a shadow or a nested card.
  Exceptions are documented in Phase 4 rulings (blog card shadow
  F-05, overlay panels F-14); the language dropdown panel is NOT an
  exception — it has no shadow by design (âm tường).

## Shapes

- **Base radius 4px** — buttons, fields, boxes, cards
  (`--radius-selector` / `--radius-field` / `--radius-box` = 4px).
- **Sidebar nav items: radius 0.** Items span the full sidebar width
  and the active left bar sits flush on the edge; rounding would make
  them look like floating chips, against the Swiss spirit.
- **Header buttons only: `rounded-full`.** The landing 注册 button is
  radius 20px / height 44px; this is the single exception.
- **Border:** 1px (`--border: 1px`).

## Components

### Buttons

- **Filled accent button:** background `#C2410C`, white text, 4px
  radius. Hover: `#9A3412`, white text unchanged. The sidebar 拍照
  button follows this, not the sidebar hover grey.
- **Text button:** accent `#C2410C` text, no background (landing 登录).
- **Transition:** `background-color 150ms ease-out, color 150ms
  ease-out`. Never transition `padding`, `margin`, `width` or
  `transform` — a pressed state must not shift layout bounds.

### Chips (if used)

- **Status chip:** text + icon, never colour alone. Fixed 2026-11-21
  (Phase 3): failed/expired chip text is `#B71C1C` on `#FCE8E6`
  (5.58:1); warning `#B45309` on `#FFF7ED` (4.73:1); success `#2E7D32`
  on `#E8F5E9` (4.56:1); accent `#C2410C` on `#FDEDE8` (4.55:1).

### Cards / Containers

- Flat white containers on the `#F7F7F8` page background, 4px radius,
  hairline border where a boundary is needed. Never a card inside a
  card.

### Inputs / Fields

- Rectangular, 4px radius, native up/down spinners removed on
  number/money inputs. Money/number inputs match other inputs.
  Labels on every field; focus-visible outline 2px solid `#9A3412`,
  offset 2px.

### Navigation

- **Sidebar nav item (website only — plain CSS, NOT Taro):**

  | State | Background | Text / icon | Left bar |
  |---|---|---|---|
  | Rest | white `#FFFFFF` | text `#1A1C1A`, icon `#5F6368` | transparent 3px placeholder |
  | Hover | light grey `#F7F7F8` | text/icon unchanged | none |
  | Active (current route) | accent tint `rgba(194,65,12,0.08)` | text + icon `#C2410C` | 3px `#C2410C`, full 48px height |
  | Hover + active | keep active background | accent `#C2410C` | 3px accent |
  | Focus-visible | as rest/hover | as rest/hover | as current state + outline 2px solid `#9A3412`, offset 2px |
  | Pressed (`:active`) | `#E3E3E4` | as current state | as current state |

  The left bar is a `::before` pseudo-element, absolute, `left: 0,
  width: 3px, height: 100%`; `padding-left: 24px` is unchanged in every
  state so text never jumps 3px when active toggles. Radius 0.
  Transition `background-color/color 150ms ease-out` only.
  On touch (`@media (hover: none)`) the `:hover` style is disabled
  entirely — no sticky hover after tap; `:active` gives the pressed
  feedback and the active-route state always shows where the user is.
  Labels are always fully visible; nothing is hover-only.
- **Topbar:** 64px, household / currency / timezone + login state.
  Shows the user id for now — no display name exists in the backend
  yet.
- **Mobile bottom nav:** 4 tabs + centre FAB, unchanged from the
  Taro app.
- **Icons:** 6 self-hosted SVGs (home, fridge, recipes, mine, edit,
  list) in `web/src/assets/icons/` — stroke 1.5px, 24px viewBox,
  rendered 20px, gap 12px before the label. Resting icon `#5F6368`,
  active icon `#C2410C`, `aria-hidden="true"`. No icon font, no CDN,
  no emoji.

### FAQ accordion (landing)

Each question is a full-width button (height ≥ 48px), question 16px/500
`#1A1C1A`, chevron SVG rotating when open; answer below at 14px/400.
One open at a time. `aria-expanded` + `aria-controls` on every button.

## Do's and Don'ts

### Do:

- Use the system font stack and self-hosted SVGs; verify zero external
  font requests in the built page.
- Keep one accent; let hairlines and whitespace do the separating.
- Keep sidebar text fixed: same `padding-left: 24px` in every state.
- Check the longest label (消费统计) at 240px and the 375px screenshots
  before shipping.
- Show the active route with tint + accent text + 3px bar — never with
  hover grey alone.

### Don't:

- Don't copy the old `tokens.shape` (base 12 / button 20 / card 16).
- Don't use gradients (especially purple-blue), cream/warm paper,
  guessed blue, or Inter.
- Don't put cards inside cards or rounded icon tiles on headings.
- Don't mix DaisyUI + MUI in one app; don't use NutUI on the web.
- Don't hide information behind hover; don't let `:hover` stick on
  touch.
- Don't invent reviews, counts, prices, or legal text to fill a layout.

## Phase 4 rulings (2026-11-22, Impeccable audit follow-up)

- **F-05 shadow — blog card shadow KEPT.** The blog card keeps its
  box-shadow (elevation 1 at rest / 2 on hover) per reform plan §6.2,
  which explicitly prescribes it. The flat/no-shadow theme rule does
  not apply to this component. Radius stays 4px per the theme rule.
- **F-13 CTA — pill exception is header-only.** The hero/final CTA is
  4px. The rounded-full/pill exception applies ONLY to header buttons
  (the landing 注册 button).
- **F-14 overlay panels — exempt from the flat/no-shadow rule.**
  Functional overlay panels (notification panel, dialogs, drawers)
  are exempt: their shadow is functional separation from the page,
  not decoration.
