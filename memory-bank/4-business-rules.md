# Business rules
- Derive balances from posted account entries. Correct entries using reversals or adjustments. Track both transfer sides and link refunds to original transactions. Support partial payments and reconciliation.
- Checkout validates household, permission, account, currency, items, and totals. Write transaction, items, payments, ledger entries, applicable lots, and inbound movements in one transaction. Replay of the same idempotency key and payload returns the same result. A different payload conflicts.
- Bills may have zero inventory impact. Gifts may enter inventory without purchases. Record lot, reason, actor, and movement for deductions. Prevent negative stock.
- Track ACTIVE, CONSUMED, and DISCARDED separately from freshness. Support partial consumption and disposal. Preserve mixed histories in events. Terminal status for mixed depletion awaits review.
- Value waste at the original lot cost and group by currency. Keep it separate from cash expenditure.
- Enforce OWNER, ADMIN, FINANCE_MANAGER, INVENTORY_MANAGER, MEMBER, and VIEWER permissions in the backend. Audit membership changes and sensitive actions.
