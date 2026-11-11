# API contracts

P03-01 implementation covers ledger posting, recorded payments, full reversal and manual reconciliation. Closure acceptance remains with Lam and the coordinator; OPEN-09/10/14 remain **PROPOSALS**, not approved gates. No commit, deployment or delivery-status transition is implied.

| Contract | Scope |
|---|---|
| [Finance posting](finance-posting.md) | Decimal strings, accounts/drafts, atomic settlement, ledger-derived balances and idempotency |
| [Finance reversals](finance-reversals.md) | Retained full mirrors, original/account locks, single reversal and rollback |
| [Finance reconciliation](finance-reconciliation.md) | Payment/ledger integrity, manual statement/cash observations, cutoff, matching and zero-tolerance closure |

The per-step contracts are retained. OPEN-07 HTTP-level refund/inventory evidence requires P04 persistence. FX, feeds/imports, automatic corrections and reopening CLOSED reconciliations are outside P03. See the [API design reference](../../memory-bank/5-api-contracts.md) for planned later modules.
