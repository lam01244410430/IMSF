# Checkout API — Step 4 PROPOSAL

All Step 4 contracts below are **PROPOSALS** pending Lam's merge gate. Existing
identity grants and delivered finance behavior are unchanged. Let `H` denote
`/api/v1/households/{household_id}`. Writes forbid extra fields and require an
`Idempotency-Key`. Quantities, amounts and costs are decimal strings.

| PROPOSAL | Endpoint | Permission | Response |
|---|---|---|---|
| P04-OPEN-02/05/07/13 | POST `H/checkout/deductions` | `inventory.manage`: OWNER, INVENTORY_MANAGER | 201 `StockCommandResponse` |
| P04-OPEN-07/13/15 | POST `H/checkout/purchases` | `inventory.manage` AND `finance.post`: OWNER only | 201 `PurchaseCheckoutResponse` |

## Stock deduction — P04-OPEN-02/05/08/12/13 PROPOSAL

```json
{
  "items": [{"product_id": 1, "quantity": "4", "unit_id": 1}],
  "reason_code": "CHECKOUT",
  "reason": "Household stock checkout"
}
```

`items` contains 1–100 demand lines (P04-OPEN-13 PROPOSAL). Each demand converts
exactly to the product's base unit; duplicate products aggregate before selection.
P04-OPEN-05 PROPOSAL permits only `CHECKOUT` here. The service resolves one local
date per whole transaction attempt, using the existing settings JSONB
`values["timezone"]` and Python `ZoneInfo`. Missing, empty or invalid IANA zones
return 422 `INVENTORY_TIMEZONE_REQUIRED` (P04-OPEN-12 PROPOSAL). Settings remain
`{}` by default; this command never writes settings or assumes a timezone.

P04-OPEN-02/08 PROPOSAL selects only the household's matching, unarchived products
and lots with positive stock and expiry absent or on/after that local date.
Expiry day is eligible; yesterday is excluded. Lots sort by `expires_on NULLS
LAST, received_at, id` within ascending product ID. There is no expired override.
Archived products return 409 `INVENTORY_STATE_CONFLICT`; archived lots are
excluded, so insufficient eligible stock returns 409 `INVENTORY_STOCK_SHORTAGE`.

P04-OPEN-07 PROPOSAL retains the identity lock prefix and purchase
original/account/item prefix where required, then ascending products and FEFO
lots, refreshed after waiting. No `SKIP LOCKED`. If a newly discovered purchase
source was not in the acquired prefix, the attempt refuses with 409
`INVENTORY_STATE_CONFLICT`, avoiding locks in reverse order. Every product must
be fully allocated before any movement is written. A shortage rolls back all
projections, movements, details, audits and the provisional key.

The existing single writer appends one negative CONSUME and one consumption
record per allocated lot. `StockCommandResponse` lists movement/detail IDs and
`allocations: [{product_id,lot_id,base_quantity,remaining_quantity}]`. Other ID
lists are empty. This command creates no finance rows or receipts.

## Purchase checkout — P04-OPEN-07/13/15 PROPOSAL

```json
{
  "transaction_id": 1,
  "payments": [],
  "lots": [{
    "item_id": 1,
    "quantity": "5",
    "unit_id": 1,
    "received_at": "2026-11-11T10:00:00Z",
    "expires_on": "2027-01-01",
    "cost_currency": "USD",
    "unit_cost": "0.123456789012"
  }]
}
```

The existing transaction must be a DRAFT EXPENSE. Product items already carry
paired `product_id`/`base_quantity`; the server derives product and PURCHASE
source from each scoped item. Each product item's split lots must sum **exactly**
to its base quantity; omission, shortage or excess returns 409
`INVENTORY_STATE_CONFLICT`. Unknown/foreign/wrong-transaction item IDs return
404. Non-product lines stay finance-only; a finance-only EXPENSE may use `lots: []`.

`payments` uses existing `PaymentCreate` validation. Unpaid and partial finance
settlement remain allowed. The existing settlement engine posts the transaction,
exact payments and entries, and finance audit. The coordinator acquires all
referenced item locks ascending, all product locks ascending, then lot locks;
`receive_in_uow` creates PURCHASE lots/receipts with transaction IDs. It never
consumes existing stock. Ordinary finance posting remains stock-neutral.

P04-OPEN-15 PROPOSAL stores supplied fixed **base-unit** cost in the purchase
currency, or a null cost/currency pair. Both fields must be present together;
cost must be nonnegative. No division, discount allocation or residual policy.
`received_at` requires an explicit offset. Expiry is a DATE.

P04-OPEN-07 PROPOSAL exposes `LedgerService.post_in_uow(context, household_id,
transaction_id, TransactionPost)` on the same SQLAlchemy session. It reuses the
public settlement core without a nested `_command`, reservation or commit.
One outer transaction and key cover posting, receipts, audits and response:
a failure after payment/first receipt restores DRAFT and all prior state.

The response is `{transaction: <existing TransactionResponse>, lot_ids,
receipt_movement_ids}`. Existing finance errors retain their `FINANCE_*` codes,
including P3-1's decided 409 `FINANCE_CONFLICT` for an archived annotated product.

## Command guarantees — P04-OPEN-13 PROPOSAL

Keys are 1–128 visible ASCII characters without spaces, scoped to household,
actor, method/route/target and `:v1`. Canonical SHA-256 input includes Decimal,
UTC instants and DATE expiry. Identical requests replay the saved status/body
byte-for-byte; a changed payload returns 409 `INVENTORY_IDEMPOTENCY_CONFLICT`.
Both current permissions are checked before purchase replay. Revoked sessions,
removed members, disabled/PENDING users and archived-household writes are denied.
Three whole-use-case attempts handle transient PostgreSQL states; exhaustion
returns 409 `INVENTORY_RETRY_EXHAUSTED` with no committed effects/key.

Errors use `{error_code,details,request_id}` with redacted details. Inventory
validation is 422 `INVENTORY_INVALID_INPUT` or
`INVENTORY_UNIT_CONVERSION_INVALID`; permission failures are 403, scoped misses
404. Saved responses describe historical outcomes, not current stock.

## Scope and reversal gate — P04-OPEN-09/11 PROPOSAL

Checkout composes the existing finance and stock writers. Cooking is documented
in [recipes and cooking](recipes-cooking.md); expiration alerts/jobs remain
P05-owned. No migration, DELETE, REFUND, cash execution or FX is added.
P04-OPEN-11 remains a PROPOSAL: the existing Step 2/3 stock-effect reversal refusal
and persisted unresolved-refund guard are unchanged; checkout does not resolve
stock effects. The mandatory persisted OPEN-07 HTTP regression remains required.

## Verification traceability

- `tests/test_inventory_checkout.py`: stock/finance separation, split/full receipts,
  partial/unpaid settlement, post-flush rollback and same-key recovery.
- `tests/test_inventory_fefo.py`: order/ties, expiry day, midnight/DST, settings.
- `tests/test_inventory_concurrency.py`: independent-connection winners and locks.
- `tests/test_inventory_authorization.py`: six-role matrices and denied replays.
- `tests/test_inventory_idempotency.py`: replay, DATE, retries and concurrent keys.
- `tests/test_finance_inventory_reversal.py`: retained persisted OPEN-07 refusal.
