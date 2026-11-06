# Risk register
| Risk | Impact | Control | Owner |
|---|---|---|---|
| Python 3.14 dependency compatibility | Build blocked | Install and test on target platforms | Phase 02 engineering |
| Cross-household references | Data exposure | Backend authorization, composite keys, negative tests | Security and database |
| Duplicate posting and excessive deductions | Incorrect balances | Idempotency, locks, transactions, race tests | Finance and inventory |
| Pending valuation, rounding, and terminal status policies | Reporting errors | Review before relevant phases | Product owner |
