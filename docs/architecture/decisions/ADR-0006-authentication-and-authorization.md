# ADR-0006 authentication and authorization

Status is accepted.

## Context

Browser sessions span household permissions. Identity covers registration,
email verification, login, refresh rotation, logout, household membership
and RBAC, and password reset — delivered in P02-02 Steps 2-5 and verified
2026-11-09 (273 tests, branch task/P02-02-password-reset, HEAD 123bdd9).

## Problem

Enforce revocation and scoped authorization.

## Options

JWT only or short JWTs with revocable refresh tokens.

## Decision

Use short JWTs, refresh rotation, and backend authorization.

- Access token: JWT, HS256, 15 minutes, Bearer, memory-only on the client.
  Issuer and audience are mandatory; the app fails closed at startup
  without them.
- Refresh token: HttpOnly, Secure, SameSite=Lax cookie under /api/v1/auth/,
  30-day lifetime, rotation on every refresh, 10-second grace window,
  90-day family cap, 14-day idle expiry, at most 10 families per user.
  Replay of a consumed refresh token revokes its whole family.
- Refresh successor during the grace window: the exact successor and CSRF
  token are stored encrypted with Fernet under a separate env key
  (REFRESH_GRACE_KEY); ciphertext is cleared when the grace expires.
  Startup fails closed if the key is missing, equals JWT_SECRET, or is not
  a valid Fernet key. [Gate note: this encrypted-successor design is a
  manager proposal implemented as described; the gate confirms it or
  replaces it with digest-only successor tracking — see open decision 2.]
- CSRF protection on cookie-authenticated endpoints except /refresh.
- Registration is PENDING / verification-only: a PENDING user may verify
  email but may not use household features, and refresh requires ACTIVE on
  both the normal and the grace path, so a PENDING user must log in again
  after the 15-minute access token expires. [Gate note: whether PENDING may
  refresh is open decision 3.]
- Email verification: 24-hour, single-use token.
- Password reset (recovery Option A, user-confirmed): in-app email reset
  stays; manual out-of-app recovery is only for lost-email access; no
  backdoor, no SMS, no security question, no admin override. Reset request
  always returns a generic 200. Token is 32-byte opaque, SHA-256 digest
  only, 60 minutes, single-use, invalidated after 5 failed confirms;
  success revokes ALL sessions/families and sends a token-free
  notification email. Reset never activates PENDING and never reactivates
  DISABLED.
- Login rate limits as implemented: 10/hour/IP + 5/hour/email_key, with a
  dummy Argon2id hash for unknown accounts (equal-cost). Password-reset
  request: 5/hour/IP + 3/hour/email_key; confirm shares the 5/hour/IP
  bucket. [Gate note: both sets of limits are manager proposals
  implemented as described; the gate confirms the values or sets different
  ones — see open decision 1.]
- Authorization: allow-list role/permission matrix, deny-by-default.
  ADMIN is limited (membership below ADMIN + settings + view only, and may
  view the audit log); ADMIN may patch household locale/timezone settings
  only, not name or currency. [Gate note: ADMIN name/currency is open
  decision 5.] Ownership transfer is OWNER-only, with the last-OWNER
  invariant; a sole OWNER may not change email before transferring
  ownership. Household invitations: 7 days, ACTIVE-required, via the
  EmailProvider abstraction; with no provider an invitation is created but
  not emailed and no token is returned.
- Email change requires only a valid Bearer token for the owner today; no
  password re-authentication and no confirmation of the old address.
  [Gate note: re-auth on email change is open decision 4.]

## Rationale

Session families support revocation and replay detection. Short-lived
access tokens bound to a mandatory issuer/audience limit the damage of a
stolen token; server-side refresh families with rotation, a 10-second
grace window and family-wide revocation on replay make theft detectable
and recoverable; PENDING verification-only and the last-OWNER invariant
keep unverified and sole-owner accounts from escaping their limits.

## Consequences

Maintain server-side session state. Login, refresh, logout and password
reset all depend on the auth_sessions / refresh_tokens / auth_challenges /
auth_rate_limits tables and on the REFRESH_GRACE_KEY and JWT secrets being
configured; the app fails closed without them.

## Risks

- Transport and proxy trust: rate limits use the transport peer IP, so
  behind a proxy all users share one IP unless trusted proxy headers are
  configured. Settle proxy trust at deployment.
- Email delivery is best-effort: reset/verification/invitation mail goes
  through BackgroundTasks with no durable queue and no production provider
  is configured, so users receive no mail without one.
- Response timing has not been benchmarked; only status/body
  anti-enumeration is tested.
- Household settings defaults are not set (new households get values =
  {}); currency/locale/timezone/warning_days defaults are open decision 6.
- CI is local-only so far; the candidate remote workflow file was never
  run (open decision 7). Member reactivation exists only via accepting a
  new invitation (open decision 8).
