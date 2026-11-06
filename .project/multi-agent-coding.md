# Multi-agent coding group

Status: set up 2026-11-05. No code, migration, CI change, commit, push, or deployment is started by this document.

## Purpose

This document defines how a coding group coordinated in Muse works on this repository, which runs on the Windows PC named lampro. It complements AGENTS.md, which remains the repository operating rules. Repository files are written in English. Communication with the user is in Vietnamese.

## Coordinator and executor

- Coordinator: Peter in Muse. The coordinator splits work, assigns agents, collects diffs and test evidence, runs the merge gate, and reports to the user. The coordinator does not silently merge, commit, push, or deploy.
- Executor: Codex CLI on lampro, reached from Muse over SSH through Tailscale. Verified 2026-11-05: Codex CLI 0.166.0, logged in using ChatGPT. Known limitation from the same date: the Codex on-PC exec runner timed out twice. Keep executor tasks small, use one retry with a longer timeout, and report a timeout as a timeout, never as success.
- Muse subagents are the working agents in Muse. When one needs to run code on lampro, it uses the SSH scripts kept in the Muse workspace, the lampro user lamvi, and the quoted project path. It never invents a different host, user, or path.

## Source of truth, in order

1. AGENTS.md and applicable nested instructions.
2. .project/task-board.md: only a task whose status the user has approved may be started. A task marked Awaiting approval or Planned is not started by any agent.
3. docs/database/schema-v1.md as a design reference only. Per the P01-01 conditional approval on 2026-11-05, schema-v1 is not a frozen contract, the ERD is not an authoritative diagram, and API contracts, DTOs, permission matrix, and provisional policies are not frozen. An agent that needs one of those items must raise it as an open decision, never invent it as final.
4. .project/decision-log.md, .project/traceability-matrix.md, and the memory-bank open questions.
## Roles

Each role maps to an existing skill under .agents/skills. An agent loads the skill for its role before it starts, and it stays inside that role.

- Architect: system-architect. Plans the smallest safe change, checks the contract and open-decision gates, and splits a task only when every part stays testable.
- Backend coder: fastapi-engineer, with database-engineer for schema and migration work. Keeps controllers thin, uses API, application, and domain layers, and puts data access in infrastructure repositories.
- Frontend coder: react-engineer, with i18n-accessibility for locales and keyboard paths.
- Domain checker: finance-domain, inventory-lifecycle, or recipe-engine, depending on the task. Checks money, lot, movement, and recipe rules against the domain model, not against a guess.
- Tester: test-engineer. Writes and runs unit, integration, and security tests independently of the coder. Test evidence is a result, not a claim.
- Reviewer: code-reviewer, with security-engineer for authorization and security-sensitive changes. Reviews independently and returns feedback. The reviewer does not edit the code in the same step; the coder applies the fix and the tester re-runs the tests.
- DevOps and docs: devops-release for toolchain, Compose, and CI, and documentation-engineer for repository documentation updates.
- Coordinator: Muse. Assigns one agent per task, sequences agents that would touch the same file, and owns the merge gate.
## Task lifecycle

1. Gate: the user approves the task. No agent starts an unapproved task.
2. Plan: the architect confirms the task board acceptance criteria, the contract, the files the task may touch, and the tests that will prove it. Unresolved contract items become open decisions, not silent assumptions.
3. Code: one coder works on one task. The coder implements only that task, runs the relevant tests, and returns a diff summary.
4. Test: the tester runs the tests independently and reports pass or fail with evidence. A failed test returns to the coder with the failure, not to the reviewer.
5. Review: the reviewer checks correctness, household authorization, Decimal money handling, idempotency, concurrency, rollback, and security, and returns a pass or a concrete fix list.
6. Report: the coordinator reports files changed, diff summary, test evidence, acceptance criteria checked, and anything not done, and updates task board, build log, traceability, status, and handoff for the completed step only.
7. Merge gate: only the user approves a commit, a push, a deployment, a destructive migration, or an architecture change. No agent performs any of those on its own.

## Branch and file rules

- One task, one branch, one coder at a time. Branch name: task/<task-id>-<short-slug>, for example task/P02-01-toolchain.
- Two agents never edit the same file in parallel. If two tasks touch the same file, the coordinator sequences them: the first task merges only after user approval, then the second task starts.
- A coder never edits files outside its assigned task, and never rewrites another agent's branch.
- Git gate, checked 2026-11-05: this repository has no commits yet on master, and all files are untracked. Per-task branches therefore have no base commit yet. Do not invent a base commit. P02-01 is the initial-commit task, and its first commit requires separate user approval. After that commit exists, later tasks branch from master.
## Return contract for every agent

Every agent result must include, in this order: task ID and role; files changed, with a short diff summary; tests run and their results, with the exact commands or steps used; task board acceptance criteria checked, one by one; open decisions and anything deliberately not done; risks or follow-up tasks, if any. No fabricated test evidence, no invented data, no invented source, and no claim that a step passed when it was skipped or timed out.

## Domain and safety rules

These repeat AGENTS.md because every coder, tester, and reviewer must enforce them: enforce household authorization and composite ownership constraints, with no cross-household access; use Decimal for money; reverse posted entries to correct them, do not edit posted history in place; record movements for inventory changes; wrap critical writes in application transactions and verify idempotency, concurrency, and rollback; no hardcoded secrets, no fabricated data or evidence.

## How to invoke the group

- In Muse chat, the user says: Run <task-id> with the coding group. The coordinator then runs the lifecycle above for that task only.
- The saved Muse workflow for this group is named lampro-coding-group. It runs the same lifecycle: plan, implement, verify, review. Launching it does not approve a commit, a push, or a deployment; those still need separate user approval.
- A workflow launch, a subagent run, and a Codex run are preparation and implementation only. The user decision at the merge gate is a separate step.

## What is not set up and not started

- No code, migration, Compose file, or CI change is started by this setup.
- P02-01 (toolchain, minimal service, Compose, Alembic, CI) delivered 2026-11-05, initial commit 14a903b on task/P02-01-toolchain (CI steps verified locally; remote CI pending). P02-02 remains Planned.
- The P01-01 conditions remain open: resolve the pre-Phase-02 open-decision gates, sync the ERD with the schema or mark it orientation-only, expand ADR rationale, and add DTOs and a permission matrix or defer them to a specific P02 task.