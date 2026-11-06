# ADR-0006 authentication and authorization
Status is proposed.

## Context
Browser sessions span household permissions.

## Problem
Enforce revocation and scoped authorization.

## Options
JWT only or short JWTs with revocable refresh tokens.

## Decision
Use short JWTs, refresh rotation, and backend authorization.

## Rationale
Session families support revocation and replay detection.

## Consequences
Maintain server-side session state.

## Risks
Transport and recovery policy await review.
