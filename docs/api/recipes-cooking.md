# Recipes and cooking — Step 5

All Step 5 contracts and policies below implement **PROPOSALS** P04-OPEN-06,
P04-OPEN-07, P04-OPEN-09, P04-OPEN-12 and P04-OPEN-13. Implementation and passing
tests do not decide these gates. P05 retains expiry jobs/notifications and P07
retains recipe matching, ranking and substitutions; their dependencies do not change.

All routes use `/api/v1/households/{household_id}`. Authentication requires an
ACTIVE user, current membership and a live Bearer session. Household and referenced
object IDs are scoped after checking permission: forbidden current members receive
403; foreign/missing objects receive 404. Archived households retain reads and
reject new writes and replays. No identity permission grants have changed.

| Method and suffix | Input | Success | Permission |
|---|---|---|---|
| POST `/recipes` | RecipeCreate | 201 RecipeResponse | RECIPE_EDIT |
| GET `/recipes` | limit, cursor, optional archived | 200 RecipePage | VIEW |
| GET `/recipes/{recipe_id}` | — | 200 RecipeResponse | VIEW |
| PATCH `/recipes/{recipe_id}` | RecipePatch | 200 RecipeResponse | RECIPE_EDIT |
| POST `/recipes/{recipe_id}/ingredients` | IngredientCreate | 201 IngredientResponse | RECIPE_EDIT |
| PATCH `/recipes/{recipe_id}/ingredients/{ingredient_id}` | IngredientPatch | 200 IngredientResponse | RECIPE_EDIT |
| POST `/recipes/{recipe_id}/archive` | `{}` | 200 RecipeResponse | RECIPE_EDIT |
| POST `/recipes/{recipe_id}/cook` | CookingCreate | 201 CookingResponse | COOK |
| GET `/recipe-cooking-history` | limit, cursor | 200 CookingHistoryPage | VIEW |
| GET `/recipe-cooking-history/{history_id}` | — | 200 CookingHistoryResponse | VIEW |

| Role | VIEW | RECIPE_EDIT | COOK |
|---|---|---|---|
| OWNER | Yes | Yes | Yes |
| ADMIN | Yes | No | No |
| FINANCE_MANAGER | Yes | Yes | No |
| INVENTORY_MANAGER | Yes | No | Yes |
| MEMBER | Yes | Yes | No |
| VIEWER | Yes | No | No |

RECIPE_EDIT is exactly OWNER/FINANCE_MANAGER/MEMBER. COOK is exactly
OWNER/INVENTORY_MANAGER. Rank and recipe editing never imply cooking permission.
There are no DELETE routes or direct history mutations. Ingredient rows are
retained: add/patch only, with fixed line numbers and recipe ownership.

## Inputs and responses — PROPOSAL OPEN-06/13

Write DTOs reject unknown fields and client household/actor/snapshot overrides.
IDs are positive BIGINTs. All quantities and servings are finite positive decimal
strings fitting NUMERIC(20,6); floats, excess scale and overflow are rejected.
Names are trimmed, 1–200 characters. Instructions are nullable, at most 10000
characters. Recipe creation requires 1–100 ingredients with distinct positive
32-bit line numbers; later additions cannot exceed 100 retained ingredients.

```json
{
  "name": "Rice bowl",
  "servings": "2",
  "instructions": "Steam gently.",
  "ingredients": [
    {"line_no": 1, "product_id": 42, "quantity": "100", "unit_id": 1, "essential": true}
  ]
}
```

The IDs above are illustrative references, not guaranteed catalog or household IDs.
RecipePatch admits only name/servings/instructions. Omitted fields retain values;
only instructions can be explicitly cleared to null. IngredientPatch admits only
product_id/quantity/unit_id/essential; supplied fields cannot be null. Creation,
addition and ingredient patch validate scoped products and exact explicit unit
conversion under product locks. Archived products cannot be newly assigned.
Archived recipes remain readable and reject further editing and cooking.
Adding an ingredient with an existing recipe line number returns 409
INVENTORY_STATE_CONFLICT, preserving the recipe, history and command key state.

RecipeResponse includes id, household_id, name, servings, instructions, archived_at,
created_by_member_id and ingredients ordered by line_no/id. IngredientResponse
includes id, household_id, recipe_id, line_no, product_id, quantity, unit_id and
essential. CookingCreate contains only `{"servings":"2"}`. CookingResponse contains
history_id, recipe_id, servings, consumption_record_ids and allocations
(product_id, lot_id, base_quantity, remaining_quantity). Quantities are strings.
CookingHistoryResponse includes id, household_id, recipe_id, cooked_at, servings,
actor_member_id, recipe_snapshot and linked consumption_record_ids.

Pages use `{items,next_cursor}`, ascending ID, default limit 50, maximum 200.
Cursors are bound to household, resource and filters. Recipe pages include active
and archived recipes unless the archived boolean filter is supplied. History
reads always use the saved snapshot, including after recipe archive or edits.

## Atomic cooking and immutable snapshot — PROPOSAL OPEN-06/07/09

One transaction locks and re-reads the recipe, then its ingredients, before the
existing inventory purchase-original/account/item prefix, ascending product IDs,
and eligible lots in FEFO order. Edits use the same parent recipe lock. Rows are
refreshed after waiting; no SKIP LOCKED is used. Existing household serialization
is preserved. Cooking calls the shared `InventoryService.deduct_in_uow` seam,
shared FEFO allocator and single stock writer; no second deduction engine exists.

Every ingredient is scaled by requested servings / recipe servings using Decimal,
with multiplication before division for exact base-unit conversion. Input-unit
scaling may require more than six decimal places if base demand remains exact.
Inexact six-decimal base demands and absent/incompatible conversions are rejected;
base demand is never silently rounded. The snapshot
requested_quantity is display-only and may repeat at the calculation context
precision; only the exact base-demand computation traps Inexact. Duplicate
products are aggregated before FEFO so a lot cannot be allocated twice for duplicate ingredient lines. Every listed
ingredient is required, including essential=false. No optional shortage omission
or implicit substitution is allowed.

The server resolves one household local date per transaction attempt, reading
`household_settings.values["timezone"]` and validating it with ZoneInfo. Missing
or invalid timezone returns 422 INVENTORY_TIMEZONE_REQUIRED. Settings are never
written or defaulted to UTC. Scoped recipe and products are checked before timezone
resolution. Eligible lots have positive remaining stock, active product/lot, and
no expiry or expiry >= the resolved local date. FEFO sorts expiry NULLS LAST,
received_at, id, within ascending products.

The JSONB snapshot has schema_version=1, recipe (executed id/name/servings/instructions),
requested servings, ingredient IDs/line numbers/products/input and base units,
original/requested/base quantities, essential flags, conversion factors, local_date,
timezone, and actual allocation product/lot/movement IDs and base quantities.
Movement IDs are reserved from the existing identity sequence after successful
allocation planning. The complete history is INSERTed before linked consumption
details, satisfying immediate FKs without updating append-only history. Rolled-back
attempts may leave sequence gaps; they leave no business rows.

Each lot movement receives exactly one consumption record with server-only reason
COOKING and cooking_history_id. The revision-7 deferred integrity trigger checks
snapshot allocations against actual movements and consumption at commit. No new
migration is required. Recipe edits never rewrite snapshots or recorded consumption.
Shortages, failures during later ingredient writes and final response failures
roll back history, movements, details, projections, audits and provisional keys
across the whole command. Cooking has no finance posting/payment effects.

## Idempotency and errors — PROPOSAL OPEN-13

Every POST/PATCH requires Idempotency-Key: 1–128 visible ASCII characters excluding
spaces. The existing P03 protocol scopes keys by household, actor, method,
normalized route/target and version; hashes canonical payloads; reserves with
INSERT ON CONFLICT; and commits reservation, effects, audits and response together.
Same key/body replays the byte-identical saved response. Changed payload returns
409 INVENTORY_IDEMPOTENCY_CONFLICT. Current permission, membership, user/session
and household state are checked before replay. Three whole-command attempts handle
transient database failures; exhaustion returns 409 INVENTORY_RETRY_EXHAUSTED.
A failed attempt retains no key and can be safely retried.

Errors use `{error_code,details,request_id}`, without echoing inputs or SQL:
401 INVENTORY_UNAUTHENTICATED; 403 INVENTORY_FORBIDDEN;
404 INVENTORY_NOT_FOUND; 409 INVENTORY_STOCK_SHORTAGE,
INVENTORY_STATE_CONFLICT, INVENTORY_IDEMPOTENCY_CONFLICT or
INVENTORY_RETRY_EXHAUSTED; 422 INVENTORY_INVALID_INPUT,
INVENTORY_UNIT_CONVERSION_INVALID, INVENTORY_TIMEZONE_REQUIRED or
INVENTORY_INVALID_IDEMPOTENCY_KEY. Archived household writes retain the existing
409 INVENTORY_HOUSEHOLD_ARCHIVED behavior. Missing keys are DTO validation errors.

## Traceability and verification

`tests/test_inventory_cooking.py` covers immutable snapshot bytes after recipe and
ingredient edits, joins history/consumption/movement, duplicate aggregation, FEFO,
exact scaling, all-ingredient rollback, injected late failure, recipe locking,
archive, timezone, scoped references, input caps and pagination.
`tests/test_inventory_authorization.py` covers exact route roles and current-access
rechecks. `tests/test_inventory_idempotency.py` covers recipe mutations, byte replay,
conflicts, invalid keys, concurrent cooking and three whole-command retry attempts.
Step 5 execution counts, exact commands, build evidence, status and handoff are in
`/tmp/p0401-step5-result.md`, the requested executor artifact; coordinator records
are deliberately untouched.
