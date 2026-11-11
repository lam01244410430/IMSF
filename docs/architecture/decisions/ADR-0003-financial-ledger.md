# ADR-0003 financial ledger

Status is accepted.

## Context

Finance covers accounts, INCOME/EXPENSE categories, DRAFT transactions,
posting INCOME/EXPENSE/TRANSFER same-currency + OPENING, partial settlement,
a single immutable full reversal, and ledger↔payment reconciliation with
manual statement/cash comparison — delivered in P03-01 Steps 2–5 and verified
2026-11-11 (692 tests on a fresh disposable DB, branch
task/P03-01-reconciliation, HEAD 8859d05; closure verification numbers in the
closure README). Inventory (P04+), recipes/cooking, FEFO, cash refunds, FX /
multi-currency conversion, bank import/gateway, purge jobs, UPDATE of posted
data, and balance caches are OUT of P03-01 by approved scope.

## Decision

- **Immutable ledger, no stored balance.** Balances are the sum of signed
  ledger entries by account and currency (NUMERIC(20,6)). Runtime has
  INSERT/SELECT only on `account_ledger_entries`; UPDATE/DELETE/TRUNCATE are
  refused by DB grants and by the `finance_reject_history_change` trigger
  (verified: SQLSTATE 42501 under the runtime role).
- **Money is Decimal ↔ NUMERIC(20,6), string DTOs, never float.**
  (OPEN-01, decided Step 2 gate 2026-11-11.) Reject float/NaN/infinity/
  overflow and excess precision before touching the DB; never round user
  money; no HALF_EVEN boundary exists in P03-01 (no FX).
- **Small explicit currency catalog; same-currency only.**
  (OPEN-02, decided Step 2 gate; OPEN-03, FX deferred by approved scope
  2026-11-10.) Seeded currencies: VND(0), JPY(0), USD(2), EUR(2), BHD(3).
  Every account/payment/transaction carries an explicit `currency_code`;
  cross-currency legs, rates, and converted reporting are deferred, not
  implemented. The `exchange_rate` column exists but the
  `ck_payments_same_currency` check enforces `amount = transaction_amount
  AND exchange_rate IS NULL`.
- **Household currency stays unset until chosen.** (OPEN-04, decided Step 2
  gate.) Household settings remain `{}`; no currency/locale/timezone default
  is invented. OWNER-only patch of the `currency` key keeps identity behavior.
- **Payments are settled bookkeeping records.** (OPEN-05, decided Step 3
  gate.) `method_code` nullable (CASH/BANK_TRANSFER/CARD/OTHER),
  `external_reference` ≤ 200 characters and not a dedupe key,
  `transaction_amount` may be omitted (defaults to `amount`); exchange-rate
  or unequal-amount input is rejected; `settled_at` is optional and must be
  offset-aware. No PAN, no gateway pending/failed states.
- **DRAFT ownership.** (OPEN-06, decided Step 2 gate.) MEMBER creates/edits
  only their own DRAFT; OWNER/FINANCE_MANAGER may edit household drafts; all
  six roles may view. Lines may be edited/added, never removed; there is no
  DELETE endpoint for transactions, items, payments, or ledger history.
- **Cash refunds are deferred.** (OPEN-07, decided Step 3 gate; HTTP-level
  evidence deferred to P04.) REFUND input is rejected. A full reversal is
  blocked by any unresolved prior refund (`require_full_reversal_eligible`,
  guard-level + wiring-level verified); an HTTP-level test with real
  refund/inventory persistence must be added in P04.
- **Single immutable full reversal.** (OPEN-08, decided Step 4 gate.) Each
  original settled payment/entry gets exactly one mirror
  (`reverses_payment_id` / `reverses_entry_id`, IN↔OUT, no recomputation, no
  new rounding), enforced by partial unique indexes
  (`uq_transactions_reversal`, `uq_payments_reversal`, `uq_ledger_reversal`).
  Header-only reversal is allowed for a posted unpaid bill (no zero ledger
  row). No reversal of a REVERSAL, no partial reversal. Reason (1–1000
  chars), actor, original, and mirror IDs are mandatory; the original row is
  byte-identical after reversal.
- **Reconciliation is ledger↔payment integrity plus manual comparison.**
  (OPEN-09, decided Step 5 gate.) The book balance comes from the ledger;
  the statement/cash count is an external comparison, never permission to
  overwrite books. `expected_closing = prior CLOSED statement +
  sum(active matched)`; close only on exact difference 0 + no internal
  integrity defects + no CUTOFF_STALE + explicit outstanding acknowledgment.
  Withdrawn matches are retained, never deleted. No auto-correction, no
  reopening of CLOSED sessions. Cutoff is the ledger high-water ID under the
  account lock; backdated `occurred_at` and reversals never rewrite a closed
  session; multi-currency is never pooled.
- **Finance permissions map into `finance.post`.** (OPEN-10, decided Step 2
  gate for accounts/categories and Step 5 gate for reconciliation.)
  Account/category/reconciliation mutations and cutoff refresh require
  `finance.post` (OWNER, FINANCE_MANAGER); reads require `household.view`.
  ADMIN is never given posting via rank. P02 role grants are unchanged.
- **Overdraft, opening, transfer, backdate.** (OPEN-11, decided Step 3 gate
  and Step 4 gate.) Negative balances are allowed in initial non-credit
  accounts, no fees/limits. TRANSFER is exactly two full opposite legs
  against distinct accounts in the transaction currency. OPENING is once,
  before the account's first ledger entry. Archive blocks new postings/
  settlements but allows an otherwise-valid audited reversal on an archived
  account; an archived household still blocks writes. Posting time controls
  ledger/reconciliation order; `occurred_at` is business history only.
- **Catalog validation is future-only.** (OPEN-12, decided Step 2 gate.)
  The settings key and response shape are preserved; catalog validation
  applies to future currency patches only, with explicit reporting of already
  stored unsupported values rather than destructive backfill. Settings
  changes never re-currency historical finance rows.
- **Separate runtime/migrator privileges.** (OPEN-13, decided Step 2 gate.)
  Non-owner runtime credentials, explicit finance grants, no ledger/audit
  mutation and no DDL/TRUNCATE privileges, DB guards, and raw runtime SQL
  tests. The operator provisions disposable databases/roles without hardcoded
  secrets; no production grant changes in P03-01.
- **Idempotency and error envelope.** (OPEN-14, decided Step 3 gate and
  Step 5 gate.) `Idempotency-Key` is required on every finance POST/PATCH
  (1–128 visible ASCII; wrong/missing → 422), scoped by
  household/actor/method/route/target/version, with a canonical hash of
  Decimal/currency/path/body, saved success response, and current-permission
  recheck before replay. Three whole-use-case attempts on transient DB
  failures; exhausted → 409 `FINANCE_RETRY_EXHAUSTED`, key reusable.
  Finance errors use stable `FINANCE_*` codes + request ID; identity
  response bodies are unchanged.
- **P02 auth/security leftovers are preserved, not re-decided.**
  (OPEN-15/16, decided as preserved by approved scope 2026-11-10.) No
  finance-specific authentication bypass or token lifecycle change. Finance
  always requires ACTIVE + live session + membership. The underlying P02
  open decisions (login limits, encrypted refresh successor, PENDING refresh,
  email-change re-auth, proxy trust, email provider, ADMIN name/currency,
  member reactivation, remote CI, manual lost-email identity-proof runbook)
  remain open as identity/deployment follow-ups; they are NOT decided by
  P03-01.
- **Documentation of approved DDL/policy.** (OPEN-17, decided as a
  documentation action at this closure.) Approved finance policies and DDL
  deviations are recorded in this ADR and in the schema-v1 finance note
  (Part 2 below). The ERD is NOT rewritten in P03-01 and remains an
  orientation diagram; P01-01 remains Conditionally approved.

## Rationale

Decimal strings end float error at the boundary; the DB enforces what the
service promises (same-currency check, one-payment/one-entry, one reversal,
single-OPEN session) so a service bug cannot silently corrupt the ledger.
Reversals mirror instead of editing, so the original stays byte-identical and
the audit trail is complete. Reconciliation compares against an external
observation without ever overwriting books, and closes only on an exact
match, so a discrepancy cannot be hidden by rounding or by an automatic
correction. Idempotency keys make retries safe on an unreliable network
without inventing a second write path.

## Consequences

- Posting, settlement, reversal, and reconciliation are atomic units of work
  under transaction/account locks (ascending ID order); a failure midway
  rolls back all mirrors and audit rows.
- Money, currency, and permission rules are enforced in both the service and
  the DB (checks, partial unique indexes, triggers, grants); the DB is the
  backstop when the service is bypassed.
- Finance reads are ledger-derived; there is no balance cache to go stale.
- P04 must add the HTTP-level OPEN-07 test with real refund/inventory
  persistence, and must decide P3-2 (archived account opening a new
  reconciliation session).

## Risks

- P3-2 UNDECIDED: an archived account can currently open a new
  reconciliation session/match (no `archived_at` check, no test). Lam has
  not answered whether to block it like settlement or allow it to close the
  books. This is the only reviewer-raised item needing a Lam decision; it
  does not block the merge, but it must be decided before release.
- Report/payload limits (OPEN-14) are a release follow-up: no `max_length`
  on payments lists, no pagination on GET payments, unbounded scans in
  `integrity()` / `_report`.
- Migration silent no-op pattern (revisions 5 and 6): if
  `FINANCE_RUNTIME_ROLE` is unset, Alembic still records the revision as
  applied while grants stay unchanged. Handle in production provisioning.
- A CLOSED session report still returns `close_eligible=true` while the
  close endpoint returns 409 — cosmetic inconsistency, fix before release.
- The `PROPOSAL` markers in app/finance code and docs/api/*.md are now
  historical labels: the items they mark were decided at the gates listed
  above. Updating the markers is a follow-up, not a closure blocker.

## Gate notes

- Scope approved by Lam 2026-11-10: finance core IN, inventory/FX/refunds/
  bank import/purge/UPDATE-of-posted/balance-cache OUT.
- Step 2 gate approved 2026-11-11 (commit 4c18423): OPEN-01/02/04/06/10/
  12/13 decided as implemented.
- Step 3 gate approved 2026-11-11 (commit 3208052): OPEN-05/07/11/14
  decided as implemented.
- Step 4 gate approved 2026-11-11 (commit d0648cc): OPEN-08/11 decided as
  implemented.
- Step 5 gate approved 2026-11-11 (commit 8859d05): OPEN-09/10/14 decided
  as implemented.
- OPEN-03 (FX defer) decided by the approved scope itself (same-currency
  only, no rate).
- OPEN-15/16 decided as preserved by the approved scope (no P02 behavior
  change in P03-01).
- OPEN-17 decided as this documentation action at closure.
- P01-01 remains Conditionally approved: this ADR is still "proposed" until
  Lam approves this draft; the ERD still omits the implemented identity
  tables and the finance tables as implemented.

---
