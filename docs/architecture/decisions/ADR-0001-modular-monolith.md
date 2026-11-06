# ADR-0001 modular monolith
Status is proposed.

## Context
Modules share transactions and deployment.

## Problem
Coordinate checkout across finance and inventory.

## Options
Microservices or a modular monolith.

## Decision
Use a modular monolith and a checkout application service.

## Rationale
A shared database transaction supports atomic checkout.

## Consequences
Define ownership and dependency boundaries.

## Risks
Boundary erosion can increase coupling.
