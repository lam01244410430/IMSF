# ADR-0008 recipe ranking
Status is proposed.

## Context
Recommendations must be reproducible and explainable.

## Problem
Rank available recipes and prioritize stock nearing expiry.

## Options
External model or deterministic ranking.

## Decision
Score coverage, quantity, urgency, and missing ingredients.

## Rationale
Identical inputs reproduce the ranking.

## Consequences
Simulate FEFO and exclude expired lots.

## Risks
Substitution rules and weights await review.
