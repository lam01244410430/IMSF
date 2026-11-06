# ADR-0005 lifecycle state model
Status is proposed.

## Context
Freshness changes with the calendar.

## Problem
Protect terminal states from expiry evaluation.

## Options
One status or separate status dimensions.

## Decision
Persist lifecycle state and derive freshness.

## Rationale
Scheduling cannot overwrite terminal states.

## Consequences
Reads need the household date.

## Risks
Undated lots and mixed depletion await review.
