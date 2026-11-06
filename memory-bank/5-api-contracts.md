# Draft REST API contracts
Use /api/v1. Resolve explicit household context and enforce membership and permission. Generate OpenAPI from Pydantic DTOs. Proposed list contract uses bounded cursor pagination and stable ordering. Encode amounts and quantities as decimal strings.

| Route groups | Draft methods and contracts |
|---|---|
| /auth | POST registration, login, refresh, logout, password changes and recovery. Accept credential DTOs and return session DTOs or 204. Rate limit public operations. |
| /users /households /household-members | GET current user and households. POST creation and invitations. PATCH/DELETE membership with permission. Return user, household, or member DTOs. |
| /accounts /transactions /transaction-items /ledger | GET resources. POST account, transaction, or reversal. Accept items, payments, and an idempotency key for posting. Return transaction ID and status. Ledger queries are read-only. |
| /products /inventory /inventory-lots /inventory-movements | GET products, stock, lots, and movements. POST/PATCH products and POST explicit adjustments. Return product or stock DTOs. |
| /consumption /disposals /expiration-alerts | POST quantity, unit, reason, and idempotency key and return movement summaries. GET history and alerts. |
| /recipes /recipe-recommendations | GET recipes and recommendations. POST/PATCH recipes. Return recipe and ingredient availability details. |
| /analytics /notifications /system | GET reports, notifications, and health. PATCH notification state. Expose only minimal health status publicly. |

Use 200/201/204 on success. Error fields are error_code, details, and request_id. Use 401 for invalid authentication, 403 for insufficient permission, 404 for invisible objects, 409 for state or idempotency conflicts, 422 for invalid input, and 429 for rate limits. Clients localize stable error codes. Endpoint fields and permission matrices await phase review.
