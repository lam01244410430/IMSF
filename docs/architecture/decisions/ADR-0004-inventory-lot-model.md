# ADR-0004 inventory lot model
Status is proposed.

## Context
Products have multiple costs and expiration dates.

## Problem
Track remaining stock and valuation.

## Options
Aggregate product stock or lot balances with movements.

## Decision
Use lot balances and traceable movements.

## Rationale
This supports FEFO and waste costing.

## Consequences
Update projection and movement in one transaction.

## Risks
Locking and adjustment bounds require validation.
