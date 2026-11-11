# Inventory Step 2 API

Implementation of the **P04-OPEN-01/03/04/06/07/08/09/10/11/13/14 proposals** for review. These policies remain proposals, not user-confirmed decisions. P02 authorization and P03 finance decisions remain fixed. This document describes the enabled Step 2 contracts; it does not declare P04 delivered.

All paths below use `/api/v1/households/{household_id}`. Bearer authentication requires an ACTIVE user, a live session and current membership. Reads use `household.view` (all six roles). Every mutation requires `inventory.manage` (OWNER and INVENTORY_MANAGER only). ADMIN, FINANCE_MANAGER, MEMBER and VIEWER cannot manage inventory. There is no role inheritance.

| Resource | Enabled methods and paths |
|---|---|
| Measurement units | GET `/measurement-units` |
| Explicit directional conversions | GET `/unit-conversions` |
| Product categories | POST/GET `/product-categories`; GET/PATCH `/product-categories/{category_id}`; POST `/product-categories/{category_id}/archive` |
| Products | POST/GET `/products`; GET/PATCH `/products/{product_id}`; POST `/products/{product_id}/archive` |
| Receipt lots | POST/GET `/inventory-lots`; GET/PATCH `/inventory-lots/{lot_id}`; POST `/inventory-lots/{lot_id}/archive` |
| Immutable movement history | GET `/inventory-movements`; GET `/inventory-movements/{movement_id}` |

Create returns 201; reads, patches and archives return 200. There is no DELETE, unarchive, unit administration or arbitrary movement write endpoint. Adjustments, consumption, disposal, returns, checkout, cooking and recipe routes remain absent. The only enabled stock writer creates receipts. Future lifecycle tables in migration 7 do not enable their commands. No `expiration_alerts` table is created; alerts remain P05-owned (P04-OPEN-09 proposal).

## Requests and reads

Names are trimmed, 1–200 characters. Reason text is trimmed, 1–1000 characters. Writes reject extra fields, client scope/actor IDs and projections. IDs are positive signed BIGINTs. Decimal values are JSON strings, never floats or JSON numbers; non-finite, exponent notation, overflow and excess significant scale are rejected before SQL coercion. Quantities use NUMERIC(20,6); costs/factors use NUMERIC(30,12). Offset-aware receipt instants normalize to UTC; expiry is an ISO date. No household timezone default is introduced.

- Category create/patch: `{ "name": "Dry food" }`. Archive body: `{}`. Category names are household-unique, including archived rows.
- Product create: `{ "name": "Rice", "base_unit_id": 1, "category_id": null }`. Product patch accepts name, base unit and category only; omitted fields are preserved, null category clears it. Duplicate product names are allowed; stable IDs identify products. Base unit changes conflict once any retained lot exists, including archived or depleted lots. Archived categories cannot be newly selected.
- Receipt: `{ "product_id": 1, "source_kind": "GIFT", "quantity": "500", "unit_id": 1, "received_at": "2026-11-11T10:00:00Z", "expires_on": null, "purchase_item_id": null, "cost_currency": null, "unit_cost": null, "reason": "Gift received" }`. Optional fields may be omitted. Sources are PURCHASE/GIFT/MANUAL. PURCHASE requires an existing product-linked item of an unreversed POSTED EXPENSE; GIFT/MANUAL forbid a purchase item. Purchase cost currency, if supplied, must equal the purchase currency. Cost is explicitly supplied per base unit, never derived by dividing finance totals; unknown cost remains a null pair. Cost allocation/valuation remains open for P06.
- Lot patch: `{ "expires_on": "2026-12-31", "reason": "Correct printed label" }`. Null clears expiry; omission preserves it. Receipt/source/product/cost/quantity cannot be patched. Expiry edits are audited under product/lot locks (P04-OPEN-08 proposal).
- Lot archive: `{ "reason": "Retain this stock history" }`. Product/category archive body: `{}`. Archived objects remain readable. Archived products block new receipts; no history is removed.

Lot responses include `id`, `household_id`, product/source/purchase reference, receipt time, expiry/archive, immutable `received_quantity`, projected `remaining_quantity`, optional fixed cost/currency, nullable `terminal_state` and `receipt_movement_id`. Decimal output uses strings. One lot and its unique RECEIPT commit together; the receipt delta equals the base received quantity. The sum of split PURCHASE lots cannot exceed the item's base quantity.

Movement responses expose ID/scope/lot/kind, signed decimal delta, business `occurred_at`, server `recorded_at`, retained actor/transaction/correction links and reason. Receipt commands produce only RECEIPT rows; listings retain any future supported movement history.

The global migration-seeded catalog is g/kg MASS, ml/l VOLUME, each COUNT. Conversions are explicit kg→g 1000, g→kg 0.001, l→ml 1000, ml→l 0.001. Identity conversion is allowed; no reciprocal inference, graph traversal, mass/volume or pack/density conversion exists. Base conversion must be exactly representable to six decimals. For example 0.000001 g→kg is rejected instead of rounded. Referenced meanings are frozen.

The proposed terminal labels at zero are CONSUMED, DISCARDED, RETURNED, ADJUSTED_OUT or MIXED according to all retained negative movement kinds. Positive stock clears the terminal label. Deferred DB guards verify receipt uniqueness, movement sums, chronological caps, terminal derivation and exact lifecycle detail alignment. These future-command invariants are present in frozen DDL; Step 2 exposes no deduction command.

## Pagination and isolation

Lists return `{ "items": [], "next_cursor": null }`, default 50/max 200. Opaque cursors bind household, resource and filters. Order is ascending ID; conversions use `(from_unit_id,to_unit_id)`. Product categories support `archived`; products support `category_id,archived`; lots support `product_id,source_kind,expires_from,expires_to,archived`; movements support `lot_id`. Date range bounds are inclusive. Foreign-household referenced/filter/path IDs return 404 after permission checks. Archived-household reads remain available; mutations and success replay are denied.

## Idempotency and errors

Every POST/PATCH requires `Idempotency-Key`: 1–128 visible ASCII characters without spaces. Inventory extends the decided P03 standard: household/current actor/method/normalized target route/version scope, canonical Decimal/UTC datetime/DATE payload hash, durable reservation with conflict-safe insertion, saved status/body replay and current authorization before replay. Equivalent decimal formatting replays identical response bytes; changed payload conflicts. Effects, audit, key and response commit in one transaction. Refused/failed requests leave no committed key. Retryable DB failures restart the entire use case up to three attempts.

Errors use `{ "error_code": "INVENTORY_…", "details": {}, "request_id": "…" }`. Codes are proposals under P04-OPEN-13: 401 UNAUTHENTICATED, 403 FORBIDDEN, 404 NOT_FOUND, 422 INVALID_INPUT / INVALID_IDEMPOTENCY_KEY / UNIT_CONVERSION_INVALID, 409 STATE_CONFLICT / HOUSEHOLD_ARCHIVED / IDEMPOTENCY_CONFLICT / RETRY_EXHAUSTED (each prefixed `INVENTORY_`). Details never expose SQL or credentials. Existing finance and identity error contracts retain their semantics.

## Finance compatibility and reversal evidence

New or editable DRAFT finance items may supply nullable paired `product_id` and `base_quantity`; both must be supplied together for patches, including clearing the pair. Base quantity is a positive exact decimal string. Reads expose both nullable fields. These are stock annotations only: existing finance permissions remain fixed and DRAFT edits/posting do not create inventory. Existing posted items remain unchanged; there is no backfill or commercial UPDATE.

A finance-facing `ReversalEffects.load_locked` port loads actual inventory/refund associations after original/account locks, then item/product/FEFO lot locks. The inventory adapter writes no finance rows. All receipt/link insertion paths also lock the original before products/lots; the SQL backstop rejects associations against reversed originals.

Append-only `refund_inventory_links` require a real live POSTED purchase, its item, its PURCHASE lot and retained creator. Composite FKs enforce scope and aggregate identity. Optional RETURN/payment/ledger references must belong to that aggregate; paired payment/ledger references must match the same payment/account/currency tuple. There is no public link administration, resolved flag, cash REFUND or financial settlement implementation.

Every persisted unresolved association blocks the existing finance reversal with **409 `FINANCE_UNRESOLVED_REFUND`** (fixed P03 behavior). A physical RETURN alone never resolves it. Separately, linked purchase stock blocks reversal with proposed **409 `FINANCE_STOCK_EFFECT_UNRESOLVED`** until a resolution policy is separately approved (P04-OPEN-11). No stock is automatically restored or erased. Unlinked finance-only reversals retain exact mirrors, archived-account correction and header-only unpaid reversal.

The first persisted-link HTTP evidence is `tests/test_finance_inventory_reversal.py::test_http_reversal_rejects_real_unresolved_refund_inventory_link_without_effects`, parameterized for OWNER and FINANCE_MANAGER. It commits real HTTP-created DRAFT→POSTED purchase/item/payment/ledger and PURCHASE receipt rows, inserts the link through the runtime repository, and compares original row bytes plus stock/detail/link snapshots before/after refusal. It checks zero reversal headers/mirrors/ledger/audit/committed request keys without replacing guard, loader, authorization or DB.

## Migration/runtime boundary

Frozen revision `000000000007_inventory_core.py` follows 6; revisions 1–6 are unchanged. It includes core, minimal recipe/cooking, nullable consumption/cooking and refund-link DDL so later steps implement commands without editing revision 7. `FINANCE_RUNTIME_ROLE` must explicitly identify an existing unprivileged non-owner role; absent/invalid provisioning fails closed. Unit catalogs are runtime read-only, history SELECT/INSERT-only, business UPDATE privileges column-scoped. Runtime has no history DELETE/TRUNCATE. Triggers retain history even if ordinary privileges are accidentally broadened. Repositories flush; application services commit.

Downgrade locks business/history and finance-item tables, then refuses retained inventory/recipe data or populated product annotations with SQLSTATE 55000. Empty-only downgrade removes new objects and retains revision-6 finance data. Deployment, production role changes and destructive rollback are outside this implementation authorization.
