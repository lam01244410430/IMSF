# API contracts

P03-01 implementation covers ledger posting, recorded payments, full reversal and manual reconciliation. Closure acceptance remains with Lam and the coordinator; OPEN-09/10/14 remain **PROPOSALS**, not approved gates. No commit, deployment or delivery-status transition is implied.

| Contract | Scope |
|---|---|
| [Finance posting](finance-posting.md) | Decimal strings, accounts/drafts, atomic settlement, ledger-derived balances and idempotency |
| [Finance reversals](finance-reversals.md) | Retained full mirrors, original/account locks, single reversal and rollback |
| [Inventory lifecycle](inventory-lifecycle.md) | P05 Step 2 PROPOSALS: date-bound reads and retained alert/job persistence; execution deferred |
| [Inventory](inventory.md) | P04-OPEN PROPOSAL products, receipts and lifecycle commands |
| [Checkout](checkout.md) | Step 4 P04-OPEN-02/07/08/09/11/12/13/15 PROPOSALS: FEFO deductions and atomic purchase checkout |
| [Recipes and cooking](recipes-cooking.md) | Step 5 P04-OPEN-06/07/09/12/13 PROPOSALS: retained recipe inputs, immutable snapshots and atomic FEFO cooking |
| [Finance reconciliation](finance-reconciliation.md) | Payment/ledger integrity, manual statement/cash observations, cutoff, matching and zero-tolerance closure |

The per-step contracts are retained. OPEN-07 HTTP-level refund/inventory evidence requires P04 persistence. FX, feeds/imports, automatic corrections and reopening CLOSED reconciliations are outside P03. See the [API design reference](../../memory-bank/5-api-contracts.md) for planned later modules.
