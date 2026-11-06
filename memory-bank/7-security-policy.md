# Security policy
- Propose Argon2id via pwdlib and short-lived JWTs. Verify signature, algorithm, issuer, audience, and expiration. Rotate hashed refresh tokens and revoke the session family on replay. Browser transport, lifetime, and recovery channels await approval.
- Validate household membership and permission on each request. Use composite ownership keys, parameterized queries, validated inputs, and least-privilege database roles.
- Allow explicit CORS origins. Protect cookie flows against CSRF. Apply output encoding and CSP against XSS. Rate limit sensitive endpoints. Audit permission, finance, and inventory actions and redact secrets.
- Inject secrets through the environment or a secret manager. Test cross-household reads and writes, excessive privilege, removed members, token replay, error leakage, and races.
