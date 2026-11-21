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
  sizes except as an outline.
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
- **Semantic error `#D32F2F`**, error container `#FCE8E6`. Known gap:
  `#D32F2F` on `#FCE8E6` is 4.23:1 (below 4.5:1) — fix when the chip is
  rebuilt on the web app; do not ship new text at that ratio.
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
  | `#D32F2F` | `#FCE8E6` | 4.23:1 | **no — known gap** |

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
- **Landing header:** sticky, 64px, white, 1px bottom hairline
  `#E3E3E4`, horizontal padding 24px (16px mobile). Left: logo + name
  IMSF + 4 menu items (功能 / 使用方法 / 菜谱 / 常见问题). Right:
  language switcher (中文 / Tiếng Việt / English) + 登录 text button +
  注册 filled accent button (radius 20px, height 44px). Below 768px:
  logo + compact switcher + hamburger; menu + auth move into a drawer.
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

- **Status chip:** text + icon, never colour alone. Known gap: failed
  chip `#D32F2F` on `#FCE8E6` is 4.23:1 — fix on rebuild.

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
