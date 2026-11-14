# Open decisions
- RESOLVED 2026-11-05 (user-confirmed, multi-agent arbiter): browser session transport, token lifetime, verification and recovery channels, role permissions, and retention. See "Pre-Phase-02 gates resolved 2026-11-05" below.
- Before Phase 03, confirm overdraft policies, currency precision, exchange rate sources, cross-currency transfer and refund rounding.
- Before Phases 04–05, confirm valuation and discount allocation, undated lots, terminal status after mixed depletion, and adjustments against lot capacity.
- Before Phases 06–07, confirm waste-rate denominator, multicurrency reporting, recipe scoring, and substitutes.
- Before release, confirm the license, backup RPO/RTO, privacy retention periods, and deployment environment.

## Pre-Phase-02 gates resolved 2026-11-05
Decided by a bounded multi-agent interrogation (proposer, challenger, two rounds, arbiter as hard stop) and confirmed by the user on 2026-11-05. User confirmations: (1) Deployment origin: same-origin. (2) ADMIN scope: limited. (3) VIEWER scope: full. (4) Retention: default. (5) Email provider: PENDING behaviour. (6) Account recovery: manual.
- Transport: default same-origin (React and FastAPI under one domain, /api proxied); cross-origin only as an explicit fallback with an origin list. Access token: Bearer Authorization header only, held in React memory only, never localStorage, sessionStorage, or a cookie. Refresh token: HttpOnly, Secure, SameSite=Lax cookie, Path /api/v1/auth/, name refresh_token; cross-origin fallback only SameSite=None; Secure together with the CSRF header and an explicit CORS allowlist. CSRF header X-CSRF-Token (session-bound, in login JSON, held in memory, rotated on refresh) required for all cookie-authenticated mutations except /refresh, which is protected by SameSite=Lax plus a strict Origin/Referer allowlist check; logout requires the CSRF header. CORS: explicit CORS_ALLOWED_ORIGINS, credentials only for listed origins, never *. No token material in URLs, logs, or error responses. JWT claims are never authority: backend re-resolves household membership (removed_at IS NULL) and session family status on every household-scoped request; objects in another household return 404.
- Token lifetime: access JWT 15 minutes; refresh token 30 days from issuance, rotated on every successful refresh; session family absolute lifetime 90 days from initial login; idle timeout 14 days with no successful refresh; effective family expiry = min(login + 90 days, last_successful_refresh + 14 days); refresh expiry = min(issuance + 30 days, family expiry). Parallel-refresh grace window: 10 seconds, idempotent retry returning the same successor token, no family revocation inside the window; reuse after 10 seconds or after a different successor was issued revokes the entire family in a committed transaction. Retry outside the window requires full login. Maximum 10 active session families per user; an 11th login revokes the oldest family by last_activity and records an auth_audit_events row.
- Verification: PENDING users may log in to a verification-only state (login, logout, resend verification, update own email address, which invalidates prior VERIFY_EMAIL challenges); they cannot create a household, join or access any household, post, accept an invitation, or call any household-scoped endpoint (backend-enforced). Invitation acceptance requires ACTIVE; invitation life 7 days. Challenge: random 32-byte opaque token, stored only as SHA-256 token_digest, purpose VERIFY_EMAIL, 24-hour expiry, single use, atomic consumption; a new challenge atomically consumes prior unconsumed VERIFY_EMAIL challenges; resend cooldown 60 seconds, maximum 5 per user per 24 hours, verification attempts rate-limited at 10/hour/IP, generic errors. Email via an EmailProvider abstraction configured only via environment/secret manager; no provider hardcoded. No provider in production: registration stays PENDING with a generic error, token never returned in an API response or log; dev-console printing only with ENV=development and DEV_EMAIL_CONSOLE=true.
- Recovery: email only in V1; no SMS, security questions, admin password override, or support backdoor in the app. Reset request returns the same generic 200 regardless of account existence or state; rate limits 5/hour/IP and 3/hour per email_key on request, confirm endpoint also rate-limited per IP. Single active RESET_PASSWORD challenge: issuing a new challenge atomically invalidates prior unconsumed ones. No challenge is created for DISABLED accounts; a successful reset does not activate a PENDING account and never reactivates a DISABLED account. Reset token: 32-byte opaque, SHA-256 digest only, 60-minute expiry, single use, atomic consumption, invalidated after 5 failed confirm attempts. New password: 12-128 characters, Argon2id via pwdlib, must differ from the current password, no mandatory character-class rules. On successful reset, atomically consume the challenge, revoke all auth_sessions and refresh_tokens for the user (all devices, all families), revoke other unconsumed reset challenges, require full re-login with no auto-login, record an auth_audit_events row, and send a notification email with no link and no token. Never email a password, token digest, session/refresh token, or auto-login link. Account recovery for a lost email account is a documented manual out-of-app runbook; its identity-proof rule must be documented before release (not a P02-01 blocker, and not an in-app bypass).
- Role permission matrix: explicit allow-list per endpoint group, deny by default, backend-enforced within the resolved household only; ordering OWNER > ADMIN > FINANCE_MANAGER = INVENTORY_MANAGER > MEMBER > VIEWER applies only as a grant ceiling for membership/role actions; single role per user per household; no self-role-change; every membership/role mutation locks the household row, runs in one transaction, and is rejected if it would leave zero active OWNERs. OWNER: invite, remove, change roles, transfer ownership, archive, promote to ADMIN/OWNER, manage settings, post/reverse finance, manage inventory, stock-deducting cooking. ADMIN (limited): invite, remove, change roles only for roles below ADMIN, manage settings, view; ADMIN may NOT post/reverse finance, manage inventory, do stock-deducting cooking, transfer ownership, archive, or promote to ADMIN/OWNER. FINANCE_MANAGER: post/reverse finance, create/edit recipes, view-only inventory/settings. INVENTORY_MANAGER: manage inventory, stock-deducting cooking, view-only finance/settings. MEMBER: DRAFT transactions only, record consumption/disposal movements (audited, lot-resolved), create/edit recipes; MEMBER may NOT create products, lots, or adjustments, and may NOT do stock-deducting cooking. VIEWER (full): view-only access to household business/financial data, no writes, no audit-log access, no member management. Finance reversal only once per original, only when prior refunds and stock effects can be resolved consistently, actor recorded in audit_logs.
- Retention (defaults, user-confirmed): audit_logs for the lifetime of the household plus 7 years after archival; auth_audit_events 2 years (730 days) from event_at; auth_sessions/refresh_tokens purged at max(expires_at, revoked_at) + 90 days, never before expiry; invitations purged at max(expires_at, final_state_at) + 90 days, with provenance (inviter, invitee email_key, role, timestamps, final state) preserved as a household-scoped audit_logs entry before deletion; auth_challenges purged at max(expires_at, consumed_at) + 30 days. Retention is global deployment configuration via environment variables, not per-household UI. Purges run only as a separate privileged job role (never the runtime role), as idempotent scheduled_jobs with lease fencing, and each purge run is recorded in system metrics/logs outside the table being purged. Retention jobs must never delete account_ledger_entries, transactions, transaction_items, transaction_payments, inventory_lots, inventory_movements, inventory_adjustments, consumption_records, disposal_records, or recipe_cooking_history. The 7-year/2-year periods are approved defaults; legal/privacy confirmation remains a pre-release check.

## P06-01 Step 2 proposal status (2026-11-13)

Lam authorized Q1–Q8 default (a) implementation; P06-OPEN-01..10 remain OPEN
until P06 closure. Step 2 implements only valuation defaults 01/03/04/05/06/08:
fixed per-lot cost, correction-netted movements, quantities-only unknown-cost
section, observed currencies without conversion, nonblocking purchase/reversal
issues, the two valuation VIEW reads and exact Decimal strings. No carried
P05 OPEN, P3-2, P04-OPEN-11/16, P02-02 leftover, P01-01 label or ADR-0005 is
re-decided. Step 3 waste and Step 4 summary/bounds are deferred.

P3 input: existing correction commands can overcompensate a linked deduction;
the proposed absolute-per-kind net model reports TIE_OUT_MISMATCH for that
retained shape. P06-OPEN-01 closure must consider signed nets versus correction
constraints. No correction write policy is changed by Step 2. Split PURCHASE
lots compare against the item's full net amount without allocation, as proposed.

## P06-01 Step 3 proposal status

P06-OPEN-02/09/10 defaults (a) are implemented as PROPOSALS under Lam's Q1–Q8
authorization: same-period received known-cost value denominator (product and
currency filters, never reason); root occurred_at for disposals/consumption and
received_at for receipts, required household timezone, local months/open ranges;
DISPOSE-only waste from recorded reasons. Expired/cooking consumption remains
consumption. Step 2 defaults 01/03/04/05/06/08 are reused. **All P06 OPEN decisions
remain OPEN until closure; implementation and tests decide no policy gate.**

P06-OPEN-07's 366-day cap and per-report 1,000-row cap are deferred explicitly to
Step 4, along with currency summary. P3 bounds input: waste returns uncapped
per-root event rows to the application in addition to the existing full-lot
totals/denominator scan; by-product pagination limits output only. Overcorrected
opposite-signed disposal roots can disagree with per-lot absolute netting and
return 200 with TIE_OUT_MISMATCH. No correction writer policy is changed.

P05 OPEN-09 remains UNRESOLVED. Other P05 OPEN items, P3-2, P04-OPEN-11/16,
P02-02 leftovers, P01-01 label and proposed ADR-0005 are not re-decided.

## P06 Step 4 PROPOSAL status

P06-OPEN-07(a) default 50/max 200, cursor pages, waste-only 366-day spans and
1,000-row query-result bound are implemented as PROPOSALS, alongside the
currency-summary GET. This supersedes the historical Step 2/3 deferrals, not
their policy status. SQL aggregates cover all scoped source rows; page fetches
return at most 201, unknown/issue identifiers first 100 with complete counts.
The bound does not truncate inputs or cap database recursion/nested aggregate
arrays. Existing finance contracts/limits remain unchanged (P05-OPEN-14 input
only). All ten P06 OPEN items remain OPEN until closure.

Step 2 P3-2 full-lot Python materialization and Step 3 P3-1 uncapped root/product
results are fixed. Step 3 P3-2 overcorrected opposite-signed roots remains a
closure input: preserve HTTP 200/TIE_OUT_MISMATCH; recommend closure explicitly
accept per-root absolute waste or separately decide signed-net/correction-writer
policy. Step 3 P3-3 actual DDL finding: disposal_records.reason_code is NOT NULL
with four-code CHECK in revision 7, and detail guards require alignment.
Recommend relying on those valid-data constraints and separately deciding any
defensive malformed-import policy; no new reason semantics are implemented.
P05 OPEN-09, all prior carried OPEN items, P01-01 and ADR-0005 stay unchanged.

## P06 Step 5 closure review status (2026-11-14, docs only)

Step 5 changes no production code, test, migration, route or DTO. It reviews
Steps 2–4 and records the closure verdicts (a)–(h) for Lam's separate closure
decision. Full evidence: [.project/p0601-step5-coder-evidence.md](../.project/p0601-step5-coder-evidence.md);
EC2 result `/tmp/p0601-step5-result.md`. The live full-suite floor is 1210
passed (plan §6 "1157" is the P05-01 floor, never the P06 floor).

**P06-OPEN-01..10 — every item implemented as a PROPOSAL, every item stays OPEN
for Lam to decide at the P06 closure:**

| Item | Implemented as (proposal) | What the closure decision needs |
|---|---|---|
| OPEN-01 Valuation method | (a) per-lot unit_cost × movement deltas per kind; ADJUST_IN negative vs adjusted_out; corrections net out per kind | Confirm (a), or choose pro-rata allocation (b) / stored snapshot (c, needs a migration). Also decides Step 2 P3-1: write-time correction constraints vs signed nets |
| OPEN-02 Waste denominator | (a) total received value of known-cost lots in the same scope | Confirm (a), or choose quantity (b) / consumed+disposed (c) / purchase cost (d) / lifetime (e) |
| OPEN-03 Unknown-cost policy | (a) quantities only, never money/zero/estimate; explicit unknown_cost section | Confirm (a), or approve estimating from the finance item (b) / zero money (c) |
| OPEN-04 Currency policy | (a) group by observed code; no conversion, no combined total, no default currency | Confirm (a), or choose conversion (b, needs a rate source) / single-currency only (c) |
| OPEN-05 Reconciliation strictness | (a) mismatches + reversed originals are report issues; read returns 200 | Confirm (a), or choose mismatch blocks the report (b) / ignore the linkage (c) |
| OPEN-06 Report surface and roles | (a) four GET routes, VIEW for all six roles | Confirm (a), or restrict the currency summary (b) / all reports (c). Also decides Step 2 P3-3 (VIEWER/MEMBER money visibility) |
| OPEN-07 Report/payload maximums | (a) default 50/max 200, cursor pages, waste 366-day cap, 1,000-row query-result bound | Confirm (a), or choose tighter (b) / looser (c). Feeds P05-OPEN-14 + P09 hardening |
| OPEN-08 Money rounding/presentation | (a) exact Decimal strings, no rounding | Confirm (a), or choose minor-unit rounding (b) / display-only half-up (c) |
| OPEN-09 Report periods/timezone | (a) occurred_at for waste/disposal, received_at for received/remaining; required household timezone; local months; open-ended ranges allowed | Confirm (a), or choose recorded_at everywhere (b) / period required (c) |
| OPEN-10 Waste definition | (a) DISPOSE movements only by recorded reason code; expired-lot and cooking consumption are not waste | Confirm (a), or include expired-lot consumption (b) / cooking consumption (c) as waste |

**Carried P3 dispositions (Step 5):** Step 2 P3-1 → OPEN-01 closure decision
above; Step 2 P3-3 → OPEN-06 closure decision above; Step 3 P3-2 → closure
accepts per-root absolute waste or separately decides signed-net /
correction-writer constraints; Step 3 P3-3 → rely on DDL-enforced NOT NULL +
four-code CHECK for valid data, defensive malformed-import handling is a
separate decision; Step 4 reviewer P3-1 → closure confirms global-unknown_cost
semantics for filtered summaries or aligns the summary with valuation/waste;
Step 4 reviewer P3-2 → closure confirms the summary unknown_cost count+IDs-only
shape or adds quantities by kind; Step 4 reviewer P3-3 → recommended
disposition is documenting the shared-aggregate contract (follow-up cleanup vs
documented summary-only use), no code change in Step 5.

**P05-OPEN-14 input as delivered:** new-surface maximums (default 50/max 200,
waste 366-day cap, 1,000-row query-result bound) plus bounded SQL-aggregate
inputs for the consumed finance reads; existing finance contract limits
unchanged. P05-OPEN-14 itself stays a release input; P09 owns hardening.

**Known limitations:** full-suite pytest exit -15 (post-summary shutdown hang
on the 1 GB host) is recorded plainly in every P06 step; the Step 5 exit code
and SIGTERM record are in the Step 5 evidence file. The Step 3 coder's first
full-suite attempt died at 84% on a Codex usage-limit hit (184,773 tokens);
that step's count rests on two complete independent re-runs.

**Handoffs:** P07 receives per-lot valuation + waste facts (read-only) plus the
unchanged P05 contracts. P08/P09 receive stable report DTOs and the decided
maximums as hardening input.

P05 OPEN-09 remains UNRESOLVED. Other P05 OPEN items, P3-2, P04-OPEN-11/16,
P02-02 leftovers, P01-01 label and proposed ADR-0005 are not re-decided.
