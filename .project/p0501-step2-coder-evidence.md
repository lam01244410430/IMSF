# P05-01 Step 2 — coder evidence

Branch: `task/P05-01-lifecycle-reads`. Base/HEAD: `c22ea83ae1415149c16d3e74d4fe608be2852caf`.
All changes uncommitted. No commit, push, deployment, PR, or production credential creation.

## Scope implemented (approved plan §6 Step 2 only)

- Three additive VIEW reads: `GET /api/v1/households/{household_id}/inventory/lifecycle`,
  `GET .../expiration-alerts`, `GET .../expiration-alerts/{alert_id}` (all six roles, VIEW only).
- New `app/lifecycle/` package (domain/dto/ports/service + infrastructure models/repositories),
  `app/api/lifecycle.py`, minimal `app/main.py` + `alembic/env.py` registration.
- Additive migration `000000000008_inventory_expiry.py` (down-revision `000000000007`):
  append-only `expiration_alerts` (natural key `(household_id, lot_id, alert_kind, local_date)`,
  expiry/timezone/job provenance) + `scheduled_jobs` (INVENTORY_EXPIRY; READY/RUNNING/SUCCEEDED/FAILED;
  lease/checkpoint/result JSONB `schema_version` 1). Downgrade 8→7 refuses SQLSTATE 55000 when any
  alert/job row exists; empty-only downgrade removes revision-8 objects and preserves revision-7 history.
- NO dispatcher, claim/execution, enqueue endpoint, stock writer, email, inbox/read state,
  history deletion, ADR-0005 expansion, or P01-01 label change. All P05 choices remain PROPOSALS
  for the merge gate. Revisions 1–7 byte-identical with `c22ea83` (SHA256 verified, see below).

## Verification (coder completion — Codex hit its usage limit mid-verification)

Codex (worker) implemented the step and ran its own targeted/full checks, then stopped on
`ERROR: You've hit your usage limit ... try again at 5:53 AM` (283,283 tokens used) while a
full-suite re-run was at ~81%. The coder completed verification directly on the EC2
(no second Codex run) using the same disposable-DB driver (`/tmp/p0501-step2-run.py`).

- Targeted (4 new files, re-run by coder): **83 passed, 0 failed, 1 warning, 50.34s**,
  exit 0 — `/tmp/p0501-step2-verify-targeted.log`.
- Full suite (re-run by coder, `--health`): **1079 passed, 0 failed, 1 warning,
  1033.37s pytest** (driver total 1367.76s), exit 0 — `/tmp/p0501-step2-verify-full2.log`.
  Baseline was 996 passed; +83 new tests. P2-1 combined-race regression (10 cases) passed.
  Health on a separate fresh DB: alembic `upgrade head` exit 0, `/health` 200 `{"status":"ok"}`,
  `/health/ready` 200 `{"status":"ok"}` — see `/tmp/p0501-step2-verify-full2-persisted.json`,
  `-health-migration.log`, `-uvicorn.log`.
- Standalone migration rehearsals (outside pytest, fresh disposable DBs,
  `/tmp/p0501-step2-rehearse.py`): **15/15 checks PASS** — `/tmp/p0501-step2-rehearsal.out`,
  `.json`. Populated rev-7 (10 seeded rows + reference data) 7→8 preserves every row;
  downgrade with 1 job + 1 alert refuses with SQLSTATE 55000
  (`Refusing downgrade: retained expiry alert/job history exists`), version stays
  `000000000008`, data intact; empty head→7 downgrade removes rev-8 objects, rev-7 tables
  intact, version `000000000007`.
- Static: `git diff --check` exit 0; no `.env`; `docker ps` empty at end; OpenAPI — all 72
  existing paths and 111 schemas unchanged vs `c22ea83`, exactly 3 new GET paths
  (Codex comparison, `/tmp/p0501-step2-openapi.json`).

## Incidents during verification (all recorded, none hidden)

- Disk-full abort: the first coder full run died at 75% (`OSError: [Errno 28]`, driver exit 99)
  because the host had 227 dangling Docker volumes (16.04 GB, from earlier disposable runs).
  Only dangling volumes were pruned (`docker volume prune -f`); the one active volume was
  untouched. Disk went from 3.5 MB free to 15 GB free. The 4 concurrency ERRORs in that
  aborted run were disk-full artifacts; all pass in the clean re-run.
- A concurrent Guiyan Wave 4 verification (`npm test` + `guiyan-test-pg` container) shared the
  EC2 during verification. The coder waited for its container to stop, then ran the full suite
  while its `npm test` process was still alive; no interference was observed.
- One pre-existing test needed a fixture-only fix to cover revision 8: the rolled-back owner
  probe in `test_history_triggers_backstop_accidentally_broadened_runtime_grants` now also
  grants TRUNCATE on `expiration_alerts` (new FK dependent of `inventory_lots`). No production
  guard, grant, or 55000 assertion changed. Existing-test edits are otherwise version
  (7→8) and OpenAPI allow-list updates only.

## OPEN-04/05/08 — DDL-settled (PROPOSAL) vs deferred

- OPEN-04 settled for DDL: opaque household/job_key identity, length ≤200, non-empty content;
  kind INVENTORY_EXPIRY; frozen scope/key/kind/created_at/original run_after/payload; payload v1
  local_date/timezone. Deferred: daily key generation/format, dispatcher cadence, explicit
  enqueue timing, current-day-only scheduling, job generation policy.
- OPEN-05 settled for DDL: READY/RUNNING/SUCCEEDED/FAILED; non-negative attempts; paired
  RUNNING-only lease storage; completion/terminal consistency; immutable terminal outcomes;
  allowed UPDATE columns; history guards. Deferred: claim/reclaim/SKIP LOCKED protocol, token
  issuance, unexpired-token/DB-time effect fencing, lease duration/renewal, job-attempt budget,
  retry classification/delays, terminal failure recovery/operator command. Storage is not a
  claim/fence protocol.
- OPEN-08 settled for DDL: bounded 4096-byte JSONB objects with numeric schema_version 1;
  checkpoint optional non-negative BIGINT high_water_id/last_lot_id; result optional
  non-negative BIGINT scanned_count/warning_count/expired_count and bounded uppercase
  outcome_code. Deferred: batch size, source high-water capture, source observation/snapshot/
  isolation policy, counter/outcome meanings, checkpoint advancement, alert/checkpoint atomic
  effects, late-arrival handling, resume algorithm.
- OPEN-06 (date drift, timezone-only changes, same-day rescan/completed-day rerun, backfill,
  late-edit policy) fully deferred. OPEN-10 exact production roles/credentials/provisioning,
  source-schema USAGE, restricted household-lock helper, worker invocation/system context/
  logging, failed-job recovery remain open. No production roles were created.

## Carried items untouched

P3-2 lots `min_length`, P04-OPEN-11 resolution policy, P04-OPEN-16 archived-account
reconciliation, report/payload limits, identity/release follow-ups; P01-01 Conditionally
approved; ADR-0004 accepted; ADR-0005 proposed; P04-01 and P2-1 CLOSED.

## Evidence paths (EC2 /tmp)

- `p0501-step2-run.py` (disposable-DB driver), `p0501-step2-rehearse.py`
- `p0501-step2-verify-targeted.log`, `p0501-step2-verify-full2.log`,
  `p0501-step2-verify-full2-persisted.json`, `p0501-step2-verify-full2-health-migration.log`,
  `p0501-step2-verify-full2-uvicorn.log`, `p0501-step2-rehearsal.out`,
  `p0501-step2-rehearsal.json`, `p0501-step2-commands.jsonl`
- Codex working logs: `p0501-step2-coder.log` (283,283 tokens; ended on usage limit),
  `p0501-step2-targeted-final.log`, `p0501-step2-full-final.log` (1078 passed / 1 failed —
  the fixture-grant failure fixed before the final re-runs), `p0501-step2-review-*.log`,
  `p0501-step2-independent-review.md`, `p0501-step2-static.json`,
  `p0501-step2-frozen-migrations.diff` (0 bytes), `p0501-step2-openapi.json`
- This record: `.project/p0501-step2-coder-evidence.md`; coder result: `/tmp/p0501-step2-result.md`
