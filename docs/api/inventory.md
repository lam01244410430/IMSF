# Inventory API — Steps 2/3/6

Steps 2/3/6 implement inventory contracts as **P04-OPEN PROPOSALS** for review, including OPEN-01/03/04/05/07/08/09/10/11/13/14/15. Implementation and test results do not decide these policies. Revision 7 remains frozen. P02 authorization and P03 finance decisions remain fixed. This document does not declare P04 delivered.

All paths below use `/api/v1/households/{household_id}`. Bearer authentication requires an ACTIVE user, a live session and current membership. Reads use `household.view` (all six roles). Reference/lot mutations, adjustments and returns require `inventory.manage` (OWNER and INVENTORY_MANAGER). Consumption/disposal require `inventory.consumption_disposal` (OWNER, INVENTORY_MANAGER and MEMBER). ADMIN, FINANCE_MANAGER and VIEWER cannot write inventory. There is no role inheritance.

| Resource | Enabled methods and paths |
|---|---|
| Measurement units | GET `/measurement-units` |
| Explicit directional conversions | GET `/unit-conversions` |
| Product categories | POST/GET `/product-categories`; GET/PATCH `/product-categories/{category_id}`; POST `/product-categories/{category_id}/archive` |
| Products | POST/GET `/products`; GET/PATCH `/products/{product_id}`; POST `/products/{product_id}/archive` |
| Receipt lots | POST/GET `/inventory-lots`; GET/PATCH `/inventory-lots/{lot_id}`; POST `/inventory-lots/{lot_id}/archive` |
| Immutable movement history | GET `/inventory-movements`; GET `/inventory-movements/{movement_id}` |
| Stock integrity (Step 6 PROPOSAL) | GET `/inventory/integrity` |
| Explicit lifecycle commands (Step 3 PROPOSAL) | POST/GET `/inventory-adjustments`, `/consumption`, `/disposals`; POST `/inventory-lots/{lot_id}/returns` |

Create returns 201; reads, patches and archives return 200. There is no DELETE, unarchive, unit administration or arbitrary movement write endpoint. Checkout and cooking/recipe routes are documented in [checkout](checkout.md) and [recipes and cooking](recipes-cooking.md). A single stock writer appends receipts and Step 3 movement/detail rows; each command owns one transaction. No `expiration_alerts` table is created; alerts remain P05-owned (P04-OPEN-09 proposal).

## Requests and reads

Names are trimmed, 1–200 characters. Reason text is trimmed, 1–1000 characters. Writes reject extra fields, client scope/actor IDs and projections. IDs are positive signed BIGINTs. Decimal values are JSON strings, never floats or JSON numbers; non-finite, exponent notation, overflow and excess significant scale are rejected before SQL coercion. Quantities use NUMERIC(20,6); costs/factors use NUMERIC(30,12). Offset-aware receipt instants normalize to UTC; expiry is an ISO date. No household timezone default is introduced.

- Category create/patch: `{ "name": "Dry food" }`. Archive body: `{}`. Category names are household-unique, including archived rows.
- Product create: `{ "name": "Rice", "base_unit_id": 1, "category_id": null }`. Product patch accepts name, base unit and category only; omitted fields are preserved, null category clears it. Duplicate product names are allowed; stable IDs identify products. Base unit changes conflict once any retained lot exists, including archived or depleted lots. Archived categories cannot be newly selected.
- Receipt: `{ "product_id": 1, "source_kind": "GIFT", "quantity": "500", "unit_id": 1, "received_at": "2026-11-11T10:00:00Z", "expires_on": null, "purchase_item_id": null, "cost_currency": null, "unit_cost": null, "reason": "Gift received" }`. Optional fields may be omitted. Sources are PURCHASE/GIFT/MANUAL. PURCHASE requires an existing product-linked item of an unreversed POSTED EXPENSE; GIFT/MANUAL forbid a purchase item. Purchase cost currency, if supplied, must equal the purchase currency. Cost is explicitly supplied per base unit, never derived by dividing finance totals; unknown cost remains a null pair. Cost allocation/valuation remains open for P06.
- Lot patch: `{ "expires_on": "2026-12-31", "reason": "Correct printed label" }`. Null clears expiry; omission preserves it. Receipt/source/product/cost/quantity cannot be patched. Expiry edits are audited under product/lot locks (P04-OPEN-08 proposal).
- Lot archive: `{ "reason": "Retain this stock history" }`. Product/category archive body: `{}`. Archived objects remain readable. Archived products block new receipts; no history is removed.

Lot responses include `id`, `household_id`, product/source/purchase reference, receipt time, expiry/archive, immutable `received_quantity`, projected `remaining_quantity`, optional fixed cost/currency, nullable `terminal_state` and `receipt_movement_id`. Decimal output uses strings. One lot and its unique RECEIPT commit together; the receipt delta equals the base received quantity. The sum of split PURCHASE lots cannot exceed the item's base quantity.

Movement responses expose ID/scope/lot/kind, signed decimal delta, business `occurred_at`, server `recorded_at`, retained actor/transaction/correction links and reason. Receipt commands produce only RECEIPT rows; listings also retain Step 3 lifecycle movement history.

The global migration-seeded catalog is g/kg MASS, ml/l VOLUME, each COUNT. Conversions are explicit kg→g 1000, g→kg 0.001, l→ml 1000, ml→l 0.001. Identity conversion is allowed; no reciprocal inference, graph traversal, mass/volume or pack/density conversion exists. Base conversion must be exactly representable to six decimals. For example 0.000001 g→kg is rejected instead of rounded. Referenced meanings are frozen.

The proposed terminal labels at zero are CONSUMED, DISCARDED, RETURNED, ADJUSTED_OUT or MIXED according to all retained negative movement kinds. Positive stock clears the terminal label. Deferred DB guards verify receipt uniqueness, movement sums, chronological caps, terminal derivation and exact lifecycle detail alignment. These invariants remain enforced by frozen revision 7 DDL and the shared writer.

## Pagination and isolation

Lists return `{ "items": [], "next_cursor": null }`, default 50/max 200. Opaque cursors bind household, resource and filters. Order is ascending ID; conversions use `(from_unit_id,to_unit_id)`. Product categories support `archived`; products support `category_id,archived`; lots support `product_id,source_kind,expires_from,expires_to,archived`; movements, consumption, disposals and adjustments support `lot_id`. Detail pages expose retained detail IDs, movement IDs, household scope, reason codes or counted quantity/reason; consumption includes its nullable server-only cooking link. Date range bounds are inclusive. Foreign-household referenced/filter/path IDs return 404 after permission checks. Archived-household reads remain available; mutations and success replay are denied.

## Idempotency and errors

Every POST/PATCH requires `Idempotency-Key`: 1–128 visible ASCII characters without spaces. Inventory extends the decided P03 standard: household/current actor/method/normalized target route/version scope, canonical Decimal/UTC datetime/DATE payload hash, durable reservation with conflict-safe insertion, saved status/body replay and current authorization before replay. Equivalent decimal formatting replays identical response bytes; changed payload conflicts. Effects, audit, key and response commit in one transaction. Refused/failed requests leave no committed key. Retryable DB failures restart the entire use case up to three attempts.

Errors use `{ "error_code": "INVENTORY_…", "details": {}, "request_id": "…" }`. Codes are proposals under P04-OPEN-13: 401 UNAUTHENTICATED, 403 FORBIDDEN, 404 NOT_FOUND, 422 INVALID_INPUT / INVALID_IDEMPOTENCY_KEY / UNIT_CONVERSION_INVALID, 409 STOCK_SHORTAGE / STATE_CONFLICT / HOUSEHOLD_ARCHIVED / IDEMPOTENCY_CONFLICT / RETRY_EXHAUSTED (each prefixed `INVENTORY_`). Details never expose SQL or credentials. Existing finance and identity error contracts retain their semantics.

## Finance compatibility and reversal evidence

New or editable DRAFT finance items may supply nullable paired `product_id` and `base_quantity`; both must be supplied together for patches, including clearing the pair. Base quantity is a positive exact decimal string. Reads expose both nullable fields. These are stock annotations only: existing finance permissions remain fixed and DRAFT edits/posting do not create inventory. Existing posted items remain unchanged; there is no backfill or commercial UPDATE.

A finance-facing `ReversalEffects.load_locked` port loads actual inventory/refund associations after original/account locks, then item/product/FEFO lot locks. The inventory adapter writes no finance rows. All receipt/link insertion paths also lock the original before products/lots; the SQL backstop rejects associations against reversed originals.

Append-only `refund_inventory_links` require a real live POSTED purchase, its item, its PURCHASE lot and retained creator. Composite FKs enforce scope and aggregate identity. Optional RETURN/payment/ledger references must belong to that aggregate; paired payment/ledger references must match the same payment/account/currency tuple. There is no public link administration, resolved flag, cash REFUND or financial settlement implementation.

Every persisted unresolved association blocks the existing finance reversal with **409 `FINANCE_UNRESOLVED_REFUND`** (fixed P03 behavior). A physical RETURN alone never resolves it. Separately, linked purchase stock blocks reversal with proposed **409 `FINANCE_STOCK_EFFECT_UNRESOLVED`** until a resolution policy is separately approved (P04-OPEN-11). No stock is automatically restored or erased. Unlinked finance-only reversals retain exact mirrors, archived-account correction and header-only unpaid reversal.

The first persisted-link HTTP evidence is `tests/test_finance_inventory_reversal.py::test_http_reversal_rejects_real_unresolved_refund_inventory_link_without_effects`, parameterized for OWNER and FINANCE_MANAGER. It commits real HTTP-created DRAFT→POSTED purchase/item/payment/ledger and PURCHASE receipt rows, inserts the link through the runtime repository, and compares original row bytes plus stock/detail/link snapshots before/after refusal. It checks zero reversal headers/mirrors/ledger/audit/committed request keys without replacing guard, loader, authorization or DB.

## Migration/runtime boundary

Frozen revision `000000000007_inventory_core.py` follows 6; revisions 1–6 are unchanged. It includes core, minimal recipe/cooking, nullable consumption/cooking and refund-link DDL so later steps implement commands without editing revision 7. `FINANCE_RUNTIME_ROLE` must explicitly identify an existing unprivileged non-owner role; absent/invalid provisioning fails closed. Unit catalogs are runtime read-only, history SELECT/INSERT-only, business UPDATE privileges column-scoped. Runtime has no history DELETE/TRUNCATE. Triggers retain history even if ordinary privileges are accidentally broadened. Repositories flush; application services commit.

Downgrade locks business/history and finance-item tables, then refuses retained inventory/recipe data or populated product annotations with SQLSTATE 55000. Empty-only downgrade removes new objects and retains revision-6 finance data. Deployment, production role changes and destructive rollback are outside this implementation authorization.


## Step 3 lifecycle commands — PROPOSAL

Every aspect in this section implements the Step 3 proposals for review;
none resolves its P04-OPEN gate. POST commands return 201; adjustment returns
`AdjustmentResponse`, consumption/disposal/return return `StockCommandResponse`.
History pages return 200.

- **P04-OPEN-04 PROPOSAL:** POST `/inventory-adjustments` accepts
  `{ "lot_id": 1, "counted_quantity": "3", "unit_id": 1,
  "reason": "Physical recount", "correction_of_movement_id": null }`.
  Count is nonnegative, converted exactly to base units. Delta is count minus
  locked remaining. Equal counts return 409 with no event/audit/success key;
  counts above received quantity return 409. Excess found stock requires a
  separately sourced MANUAL lot. Corrections append ADJUST_IN/ADJUST_OUT and
  one counted-quantity/reason detail, optionally referencing an existing
  movement on the same lot. Old rows, receipt cap and cost remain unchanged.
  `AdjustmentResponse` exposes `id`, `household_id`, `movement_id`, converted
  `counted_quantity` and `reason`; replay saves this same detail response.
- **P04-OPEN-05/13 PROPOSAL:** POST `/consumption` and `/disposals` accept
  `{ "allocations": [{ "lot_id": 1, "quantity": "1", "unit_id": 1 }],
  "reason_code": "DAILY_USE", "reason": null }`. Each list contains 1–100
  explicit-lot lines. Convert and combine repeated lot demands before validating
  availability. One all-or-nothing transaction writes one negative movement and
  one aligned detail per normalized lot. Consumption admits DAILY_USE/CHECKOUT;
  COOKING and cooking-history inputs are forbidden. Disposal admits
  EXPIRED/SPOILED/DAMAGED/OTHER; OTHER requires text. Text is trimmed, 1–1000
  characters. Shortage is 409 `INVENTORY_STOCK_SHORTAGE` with no effects/key.
- **P04-OPEN-08 PROPOSAL:** archived product/lot ordinary consumption conflicts;
  existing permissions permit explicitly reasoned adjustment/disposal/return,
  including MEMBER disposal with text. Archived records remain readable.
- **P04-OPEN-03 PROPOSAL:** zero stock derives CONSUMED/DISCARDED/RETURNED/
  ADJUSTED_OUT/MIXED from all historical negative kinds. Positive stock has null
  terminal state. Lawful ADJUST_IN may reopen within the original received cap;
  subsequent depletion still includes negative kinds before replenishment.
- **P04-OPEN-07 PROPOSAL:** retain the identity prefix and household serialization,
  then reserve the key; lock all involved originals ascending, accounts ascending,
  purchase items ascending, products ascending and lots in Step 2 FEFO order.
  Read projection/eligibility again under locks. No SKIP LOCKED. All movement
  kinds use the same writer, with deferred guards as a database backstop.
- **P04-OPEN-10/11 PROPOSAL:** POST `/inventory-lots/{lot_id}/returns` accepts
  `{ "quantity": "1", "unit_id": 1, "reason": "Return purchase" }` on a PURCHASE
  lot only. It writes a negative RETURN and one append-only unresolved
  `refund_inventory_links` association to the real original/item/lot/RETURN
  under the shared locks. It writes no transaction/payment/ledger rows.
  RETURN has no consumption/disposal/adjustment detail and never resolves
  refund associations or proves financial settlement. Reversal continues to
  refuse unresolved links, even after all purchased stock has been returned.

`StockCommandResponse` contains `movement_ids`, `consumption_record_ids`,
`disposal_record_ids`, `adjustment_ids`, `refund_inventory_link_ids` and
`allocations: [{product_id,lot_id,base_quantity,remaining_quantity}]`.
Irrelevant lists are empty. Allocation `base_quantity` is the absolute changed
quantity; signed delta is in movement history. Saved responses describe the
historical command outcome. Decimal strings may retain database scale.

No movement/history DELETE/PATCH, automatic undo, cash refund, checkout,
FEFO selection, cooking, expiry job or new migration is enabled by Step 3.
The broad Step 2 finance `_validate` archived-product check remains unchanged;
P3-1 DECIDED 2026-11-11 (Lam: keep the Step 2 rule — archived product blocks DRAFT create/patch and settle-posting with 409 FINANCE_CONFLICT; not narrowed to receipt-only). P04-OPEN-16 archived-account reconciliation is also
unchanged and open.


## Step 4 checkout integration — PROPOSAL

P04-OPEN-02/05/07/08/12/13 PROPOSALS now enable stock-only FEFO checkout via
`POST H/checkout/deductions`. P04-OPEN-07/13/15 PROPOSALS enable atomic purchase
checkout via `POST H/checkout/purchases`. See [the checkout contract](checkout.md)
for DTOs, exact full receipt allocation, permission intersection, timezone
requirements, lock order, rollback and replay semantics.

P04-OPEN-07 PROPOSAL: `deduct_in_uow` and existing `receive_in_uow` participate
in the caller's transaction and use the sole movement writer. Neither reserves
keys nor commits. FEFO takes an explicit local date; settings stay read-only.
P04-OPEN-09 PROPOSAL keeps cooking for Step 5 and expiry alerts/jobs for P05.
P04-OPEN-11 PROPOSAL remains unresolved: Step 2/3 reversal behavior is unchanged.
No migration or identity change is introduced by Step 4.


## Stock integrity read — Step 6 P04-OPEN-13 PROPOSAL

GET `/inventory/integrity` returns 200 `StockIntegrityReport`. It requires VIEW
(`household.view`), available to all six roles including VIEWER. This permission
exposes operational stock facts, with no audit-log access. Optional `product_id`
and `lot_id` are positive BIGINT filters; supplied together they intersect. Each
ID is checked within the household first; foreign or missing filter IDs return
404 `INVENTORY_NOT_FOUND`. Missing authentication returns 401; malformed filters
return 422. Archived products/lots and archived-household reads remain included.

The report is strictly read-only: SELECT queries never correct data, append
movements, change projections, write audits/keys, or resolve financial links.
All categories use one SQL statement snapshot, so committed movements, details
and finance links are observed together. No writer locks are acquired.

The response contains `limit_per_category: 100` and these category objects:

| Field | Counted entity and rule |
|---|---|
| `projection_mismatches` | Lots whose remaining quantity differs from sum of movement deltas |
| `receipt_anomalies` | Lots without exactly one RECEIPT or with receipt quantity differing from received quantity |
| `detail_misalignments` | Movements whose consumption/disposal/adjustment counts differ from their required kind; RECEIPT/RETURN require no such details |
| `source_cap_violations` | Purchase items whose total split received quantity exceeds base quantity; totals include all splits even with a lot filter |
| `terminal_state_inconsistencies` | Lots violating zero iff terminal label present, or whose label differs from historical negative-kind derivation |
| `purchase_link_inconsistencies` | PURCHASE lots not tracing to an unreversed POSTED EXPENSE item with matching product and positive base quantity |
| `receipt_posting_mismatches` | PURCHASE receipts whose transaction pointer is missing or differs from their purchase item's transaction |
| `unresolved_refund_inventory_links` | Unresolved association facts, counted by link; this is separate from mismatch categories |

Each category has `{count, items}`. `count` is the complete filtered count;
`items` contains at most the first 100 records in ascending entity ID. A count
greater than the item length means results were truncated. There is no repair
or pagination command. Every category is present, including empty
`{"count":0,"items":[]}` categories. Source-cap findings count items rather than
individual splits; all other mismatch groups count lots or movements as above.

Each finding has `code` and applicable `product_id`, `lot_id`, `movement_id`,
`purchase_item_id`, `transaction_id`, `actual_transaction_id`, `link_id` or
`return_movement_id`. Unused fields are null. Projection/receipt/cap findings
include decimal-string `expected_quantity` and `actual_quantity` (cap expected
means maximum allowed); receipt findings include `expected_count`/`actual_count`.
Detail findings include `kind`, `consumption_count`, `disposal_count` and
`adjustment_count`. Terminal findings include `expected_state`/`actual_state`;
purchase-link findings include `transaction_status`/`transaction_kind`.

A matching finance posting means a POSTED EXPENSE and the receipt's transaction
reference. Unpaid and partially paid POSTED purchases remain valid under delivered
P03 settlement rules; payment/ledger integrity remains the existing
`/finance/integrity` responsibility. No full-payment requirement is introduced.
Unresolved links use code `UNRESOLVED_REFUND_INVENTORY_LINK`; a RETURN does not
resolve them. Their presence can coexist with zero mismatches in every other
category. P04-OPEN-10/11 remain PROPOSALS; no financial refund policy is decided.

Verification: `tests/test_inventory_integrity.py` covers real purchase checkout,
deduction, cooking, return, terminal kinds, replenishment, exact receipt links,
read-only snapshots, bounded findings/counts, filters and all-six-role access.
Revision 7 prevents persisted projection/receipt/detail/cap/terminal corruption
and DRAFT-linked purchase insertion even for owner SQL. Tests preserve those
guards; clean reports and existing guard-rejection tests cover those classes.
