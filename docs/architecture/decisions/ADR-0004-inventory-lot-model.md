# ADR-0004 inventory lot model

Status is accepted.

## Context

Inventory covers products, product categories, global measurement units
with explicit conversions, lots sourced PURCHASE/GIFT/MANUAL, immutable
movements RECEIPT/CONSUME/DISPOSE/RETURN/ADJUST_IN/OUT with aligned
detail rows, FEFO stock checkout, atomic purchase checkout (finance
posting + receipt in one transaction), minimum recipe inputs, and
stock-deducting cooking with an immutable snapshot — delivered in P04-01
Steps 2–6 and verified 2026-11-12 (986 tests on a fresh disposable DB,
branch task/P04-01-closure-review; closure verification numbers in the
closure README). Expiry jobs/notifications, waste/valuation reports, and
recipe matching/ranking/substitutions are OUT of P04-01 by approved scope
(P05/P06/P07 own those).

## Decision

- **Lots are the stock unit; movements are the only writer.**
  (P04-OPEN-01/07, decided Step 2 gate 2026-11-11.) Every quantity change
  passes one stock command path: a movement row, its required detail row,
  the lot projection update, and terminal-state derivation in the same
  transaction. `SUM(inventory_movements.quantity_delta) =
  inventory_lots.remaining_quantity` for every lot, enforced by deferred
  commit-time guards (verified: 0 mismatches; raw runtime projection
  edits refused SQLSTATE 55000). Runtime has SELECT/INSERT only on
  movements/adjustments/consumption/disposal/cooking-history/refund-links;
  lots allow only controlled projection and approved metadata UPDATEs.
- **Units are global, explicit, exact.** (P04-OPEN-01, decided Step 2
  gate.) Seeded units: g/kg MASS, ml/l VOLUME, each COUNT; explicit
  same-dimension directional factors only (kg→g 1000, g→kg 0.001, l→ml
  1000, ml→l 0.001). Base quantities are NUMERIC(20,6); conversion is
  exact to six decimals, never rounded; missing/incompatible/inexact
  conversion is rejected. A product's base unit is immutable once any
  stock history exists.
- **One receipt per lot; cost is fixed at receipt.** (P04-OPEN-04/15,
  decided Step 2 gate for the cap, Step 4 gate for cost input.) Lot
  creation and its single RECEIPT are atomic; receipt delta equals
  received quantity; initial remaining equals received. Split-lot
  receipts across one purchase item must not exceed the item base
  quantity. Cost is an explicitly supplied base-unit cost in the
  purchase currency, or a null pair when unknown — never zero for
  unknown, never auto-divided, no discount residual. Cost/source/
  quantity are immutable after creation.
- **Terminal state is derived at zero from depletion history.**
  (P04-OPEN-03, decided Step 2 gate for the labels, Step 3 gate for
  behavior.) Labels at remaining = 0: CONSUMED / DISCARDED / RETURNED /
  ADJUSTED_OUT for a single negative kind, MIXED for several; positive
  quantities have no terminal label (ACTIVE is derived). A lawful
  ADJUST_IN within the original cap reopens the lot and clears the
  terminal state; prior terminal history stays visible in movements.
- **Adjustments are counted-vs-found corrections, never rewrites.**
  (P04-OPEN-04, decided Step 2 gate for the cap, Step 3 gate for
  behavior.) Delta = counted base quantity − locked remaining; a no-op
  count returns 409 and writes no movement/key; over-cap counts conflict
  and excess found stock uses a separately sourced MANUAL lot — never
  inflate the original receipt. Old movements/details stay
  byte-identical; the correction links via `correction_of_movement_id`.
- **Consumption/disposal are explicit-lot, reason-coded commands.**
  (P04-OPEN-05, decided Step 3 gate.) Consumption reasons DAILY_USE /
  CHECKOUT / COOKING (COOKING server-only, never via a Step 3 route);
  disposal reasons EXPIRED / SPOILED / DAMAGED / OTHER (OTHER requires
  text). Explicit lot IDs, repeated lots normalized before validation,
  all-or-nothing. MEMBER may record explicit-lot consumption/disposal
  only — no products/lots/adjustments, no stock-deducting cooking.
- **Archived stock stays readable; ordinary selection is blocked.**
  (P04-OPEN-08, decided Step 2 gate for receipt, Step 3 gate for
  exceptions, Step 4 gate for checkout.) Archived products/lots remain
  in integrity/history; new receipts, ordinary consumption, checkout,
  and cooking cannot select them; reasoned adjustment/disposal/return
  under the existing permissions are allowed (including MEMBER disposal
  with reason). Expiry-only patch requires a reason, under locks;
  received time/quantity, product/source, and cost cannot be edited.
  **P3-1 DECIDED by Lam 2026-11-11:** the archived-product check in
  finance `_validate` stays as implemented in Step 2 — an archived
  product blocks DRAFT create/patch and settle-posting with 409
  `FINANCE_CONFLICT`; a DRAFT whose product was archived after creation
  stays unpostable/unpatchable unless the same patch clears the product
  pair. It is NOT narrowed to receipt-only.
- **FEFO is deterministic; expiry day is eligible.**
  (P04-OPEN-02, decided Step 4 gate.) Order is `(expires_on NULLS LAST,
  received_at, id)`; undated lots come after dated ones (UNKNOWN
  freshness); the expiry day itself is eligible, yesterday is excluded.
  One local date per transaction attempt comes from the household's
  configured IANA timezone (P04-OPEN-12, decided Step 4 gate and Step 5
  gate): missing/invalid timezone → 422 `INVENTORY_TIMEZONE_REQUIRED`;
  settings stay `{}`, no UTC or executor-timezone fallback. DST and
  local-midnight boundaries resolve to one local date.
- **Checkout is atomic across finance and inventory.**
  (P04-OPEN-07, decided Step 2 gate for the writer/adapter, Step 3 gate
  for returns, Step 4 gate for coordination, Step 5 gate for recipe
  locking.) One unit of work and one idempotency key per command; lock
  order is identity prefix → finance originals/accounts/items →
  products ascending ID → lots in FEFO order; re-read after locking; no
  SKIP LOCKED (skipping would change FEFO and manufacture shortage);
  three whole-command attempts. The narrow finance seam `post_in_uow`
  reuses existing settlement validation; the public `settle()` keeps its
  wrapper. Purchase checkout is the OWNER-only intersection of
  FINANCE_POST and INVENTORY_MANAGE (P04-OPEN-13, decided Step 4 gate):
  one transaction posts the EXPENSE and creates the PURCHASE lots/
  receipts — a failure after a real payment and first receipt rolls
  back everything (original stays DRAFT, zero finance/inventory
  effects). Stock-only checkout is OWNER/INVENTORY_MANAGER with FEFO;
  concurrent same-lot deductions have exactly one winner (one 201, one
  409 shortage).
- **Reversal blocks hold with real persisted links.**
  (P04-OPEN-10, decided Step 2 gate for storage/adapter, Step 3 gate
  for returns; P04-OPEN-11, decided Step 2/3/4 gates as implemented
  behavior.) `refund_inventory_links` is an append-only unresolved
  association to a real POSTED purchase, its real product item, and its
  real received lot, with optional RETURN/payment/ledger references.
  The real adapter `ReversalEffects.load_locked` replaces the literal
  `[]`; the mandatory HTTP test proves it (Step 2, rerun Steps 3–6):
  real purchase/item/lot/receipt/link, then HTTP reversal → 409
  `FINANCE_UNRESOLVED_REFUND`, byte-identical rows, zero effects,
  guard/loader unmocked. A RETURN appends its unresolved link under the
  shared lock and NEVER by itself resolves the link. Any unresolved
  stock effect blocks reversal with 409
  `FINANCE_STOCK_EFFECT_UNRESOLVED`; there is no automatic restocking
  and no resolved-state shortcut. The explicit physical-correction
  policy that would permit a reversal is still OPEN pre-release (see
  Risks) — no P04 step invented one.
- **Cooking uses the same writer and a frozen snapshot.**
  (P04-OPEN-06, decided Step 2 gate for the DDL, Step 5 gate for
  behavior.) Recipe/ingredient inputs are minimal and retained
  (add/patch only, no delete); duplicate products aggregate before
  FEFO; quantities scale by servings in Decimal and inexact base demand
  is rejected; ALL listed ingredients are required — no substitutes, no
  silent omission of optional shortages. The cooking history row holds
  an immutable JSONB snapshot of the executed recipe, factors, and
  allocations, linked to one consumption record per lot movement, all in
  the same transaction; later recipe edits cannot change prior history
  (proven: identical SHA-256 across edits). A shortage or failure on any
  ingredient leaves zero history/consumption/movement/projection/audit/
  key effects. COOK = OWNER/INVENTORY_MANAGER; RECIPE_EDIT = OWNER/
  FINANCE_MANAGER/MEMBER (INVENTORY_MANAGER cannot edit recipes).
- **Idempotency and error envelope.** (P04-OPEN-13, decided Step 2 gate
  for foundational contracts, Step 3 gate for routes, Step 4 gate for
  checkout, Step 5 gate for recipes/cooking.) The decided P03 OPEN-14
  standard extends to every inventory/checkout/recipe POST/PATCH (key
  1–128 visible ASCII, household/actor/method/route/target/version
  scope, canonical hash, saved success replay, current-permission
  recheck before replay, three whole-use-case attempts). Canonicalization
  covers inventory DATE expiry as well as Decimal/UTC datetimes
  (`2` ≡ `2.000000` replays byte-identical; changed `expires_on` → 409).
  Inventory errors use stable `INVENTORY_*` codes + request ID; finance
  errors keep `FINANCE_*` codes; identity bodies are unchanged.
- **Migration 7 is frozen; downgrade refuses with history.**
  (P04-OPEN-14, decided Step 2 gate.) Revision 000000000007 contains
  the complete core + minimal recipe/link DDL (13 relations), down-
  revision 000000000006; revisions 1–6 frozen. Runtime grants are
  fail-closed with a preflight when the runtime role is absent. Downgrade
  refuses with SQLSTATE 55000 when any inventory history exists and
  succeeds only on an empty DB.
- **Phase boundaries are preserved, not re-decided.**
  (P04-OPEN-09, decided Step 2 gate for DDL, Step 4 gate for checkout,
  Step 5 gate for cooking.) P04 delivers only the minimum FEFO/
  consumption/disposal/cook writer and records; P05 owns lifecycle
  workflows, expiry alerts/jobs, and operational deduplication;
  P07 owns matching, ranking, scoring, substitutions, and recommendation
  availability; P06 owns waste denominator, allocation/valuation
  reporting, and currency-grouped analytics. `expiration_alerts` has no
  DDL or producer in P04. No claim that P05, P06, or P07 is complete.

## Rationale

One writer and one lock order make concurrent deductions safe without
inventing a second stock path; the database guards (projection sum,
one-receipt-per-lot, detail cardinality, append-only history) are the
backstop when the service is bypassed. FEFO is a pure function of
(expiry, received time, id) under one household local date, so two
attempts cannot disagree about which lot is consumed first. Reversal
refusal is conservative by design: an unresolved stock association
blocks the reversal rather than silently restocking or deleting a
receipt, and the HTTP test proves it with real persisted rows instead
of a mocked guard. Cooking snapshots freeze what was executed, so a
later recipe edit can never rewrite history.

## Consequences

- Every stock change is an auditable event with a detail row; nothing
  is ever UPDATE/DELETE/TRUNCATEd out of history. Corrections append;
  they never rewrite.
- Purchase checkout couples finance and inventory in one transaction:
  either both post or neither does. Finance-only bills stay stock-neutral.
- A POSTED EXPENSE with a PURCHASE lot is unreversible until an
  explicit resolution policy exists (see Risks).
- The integrity report (`GET /inventory/integrity`, VIEW for all six
  roles, read-only, 8 categories computed from persisted data) gives an
  operational check without correcting anything: it reports, it never
  fixes.

## Risks

- P3-2 UNDECIDED: `PurchaseCheckoutCreate.lots` has no `min_length` —
  a finance-only EXPENSE can post via `/checkout/purchases` with
  `lots: []`. Lam has not answered whether to require ≥1 lot/item or
  allow it. It does not block the merge, but it must be decided before
  release.
- P04-OPEN-11 resolution policy UNDECIDED: the conservative refusal is
  decided and implemented, but the explicit physical-correction policy
  that would permit a reversal does not exist. Until it is decided,
  stock-linked originals stay unreversible by design.
- P2-1 closure limitation: no combined race test exists for an
  expiry-edit/adjustment racing a FEFO deduction with post-wait
  revalidation. Per-part coverage exists and the suite is 986 passed;
  Lam accepts the gap or requires the test before marking Delivered.
- P04-OPEN-16 UNDECIDED (P3-2 carried): an archived account can open a
  new reconciliation session; no check or test was introduced by P04.
  Must be decided before release.
- Report/payload limits (P04-OPEN-17): inventory `lots` has no
  `max_length` on purchase checkout (deductions cap at 100); finance
  payments/items/report ranges remain unbounded in places. Decide
  maximums before release.
- Snapshot `requested_quantity` is stored at full ~100-digit precision
  (display-only, no allocation effect) and is undocumented. Optional
  polish.

## Gate notes

- Scope approved by Lam 2026-11-11 (plan P04-01-plan-codex.md): inventory
  + checkout IN, FX/cash-refund-execution/bank-import/purge/frontend/
  expiry-jobs/waste-valuation/recipe-matching OUT; P04-OPEN-09 phase
  allocation as proposed.
- Step 2 gate approved 2026-11-11 (commit 97f40c6): P04-OPEN-01/03/04/
  06/07/08/09/10/11/13/14 decided as implemented. OPEN-07 HTTP evidence
  proven real in this step.
- Step 3 gate approved 2026-11-11 (commit 8e82229): P04-OPEN-03/04/05/
  07/08/10/11/13 decided as implemented. P3-1 decided by Lam 2026-11-11
  (keep the Step 2 archived-product rule).
- Step 4 gate approved 2026-11-11 (commit ad77b55): P04-OPEN-02/07/08/
  09/11/12/13/15 decided as implemented (Step 4 aspects).
- Step 5 gate approved 2026-11-11 (commit 0101b54): P04-OPEN-06/07/09/
  12/13 decided as implemented (Step 5 aspects).
- Step 6 gate approved 2026-11-12 (commit 1512cbb): integrity, compatibility, docs, closure review; no new OPEN
  decisions at this gate.
- P04-OPEN-15 decided at the Step 4 gate (cost storage/input); not
  decided at Step 2 (only the cost pair was stored, null if unknown).
- P04-OPEN-16/17/18/19 carried as open, not decided by P04.
- P01-01 remains Conditionally approved: this ADR is still "proposed"
  until Lam approves this draft; ADR-0005 (lifecycle state model) stays
  "proposed" — its implemented content (terminal states per P04-OPEN-03,
  FEFO per P04-OPEN-02) is recorded here, in the decision log, and in
  the schema-v1 inventory note; expanding the ADR-0005 text itself is a
  follow-up. The ERD still omits the implemented identity, finance, and
  inventory tables.

---
