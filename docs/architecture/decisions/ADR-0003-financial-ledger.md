# ADR-0003 financial ledger
Status is proposed.

## Context
Balances and corrections must be traceable.

## Problem
Preserve auditability during posting and correction.

## Options
Mutable balances, immutable ledger, or full double-entry.

## Decision
Use immutable account entries and reversals.

## Rationale
Entries can be reconciled and correction history preserved.

## Consequences
Posting must be atomic and idempotent.

## Risks
Currency and refund policies await review.
