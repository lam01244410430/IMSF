# Architecture baseline
The strict TypeScript React client calls a FastAPI modular monolith backed by PostgreSQL 16+. Background scheduling shares the application codebase and uses the database for coordination. Docker Compose supports local development.
The API validates inputs and maps authentication context and responses. Application services authorize and own transactions. The domain maintains business rules. Infrastructure implements async SQLAlchemy repositories and external adapters.
Identity supplies membership and permissions. Checkout coordinates finance and inventory through application interfaces. Lifecycle calls inventory commands. Analytics and recipes use read-only contracts. Avoid cyclic dependencies and direct writes to another module's tables.
Validate Python 3.14 dependencies on target platforms before locking. Propose an ADR for incompatibilities.
