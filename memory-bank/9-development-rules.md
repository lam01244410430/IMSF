# Development rules
Use Python snake_case, React PascalCase, and plural snake_case for tables. Type DTOs explicitly. Use Decimal for money and quantities. Correlate structured logs by request_id and retain stable error codes.
Confirm requirement IDs, module boundaries, and migration impact before making the smallest safe change. Application use cases own transactions. Repositories cannot commit independently. Review authorization, races, retries, backward compatibility, and privacy. Verify generated work against actual behavior.
