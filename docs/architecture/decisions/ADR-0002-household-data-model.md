# ADR-0002 household data model
Status is proposed.

## Context
Users can join multiple households.

## Problem
Prevent reads and writes across ownership boundaries.

## Options
Application filters alone or filters with composite constraints.

## Decision
Combine membership authorization and composite foreign keys.

## Rationale
Defense at both layers limits cross-household access.

## Consequences
Child tables carry household_id.

## Risks
Missing query filters can still expose data.
