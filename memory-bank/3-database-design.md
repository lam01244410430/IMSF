# PostgreSQL logical design
Use BIGINT identifiers. Household-owned tables carry household_id. Parent tables expose UNIQUE(household_id, id) and children reference composite keys. Mark shared reference data explicitly. Migrations specify keys, nullability, and constraints.

| Module | Entities and relationships |
|---|---|
| Identity | users join households through household_members, unique on (household_id,user_id). roles join permissions via role_permissions. refresh_tokens belong to a user and session family. audit_logs record actor, action, and target. |
| Finance | currencies define denominations. accounts and categories are household-owned. transactions own transaction_items and transaction_payments. Payments reference accounts. account_ledger_entries reference transactions and accounts and link reversals. |
| Inventory | products reference product_categories and measurement_units. unit_conversions identify compatible dimensions. inventory_lots reference products and optionally purchase items. inventory_movements and inventory_adjustments record lot changes. |
| Lifecycle | expiration_alerts reference lots. consumption_records and disposal_records reference movements. household_settings has one row per household. |
| Recipes | recipes own recipe_ingredients and recipe_cooking_history. recipe_recommendations is proposed as a derived read model. |
| Operations | notifications reference recipients and source events. notification_preferences are unique per member and channel. scheduled_jobs track execution and retries. |

Use NUMERIC for quantities and currency-tagged amounts. Require received quantity > 0, remaining quantity between zero and received quantity, and nonnegative unit cost. Update the lot balance projection and movement in one transaction and reconcile them. Use TIMESTAMPTZ for events and DATE for expiration in the household time zone.
Candidate indexes include household-prefixed transaction date, account, product, and expiry date indexes and a partial active-lot index. Retain posted entries and inventory events under the audit policy. Retention periods await approval. Test Alembic upgrades on empty and populated databases.
See the [core ERD](../docs/diagrams/database-erd.mmd).

## Phase 01 schema reference

Use the [PostgreSQL V1 schema specification](../docs/database/schema-v1.md) as the detailed Phase 01 design reference. Preserve composite household ownership, immutable account entries, and atomic lot movements when translating the specification into migrations. The specification is proposed. Review [open decisions](15-open-questions.md) before freezing phase-specific policies. PostgreSQL migration and runtime evidence remain pending.
