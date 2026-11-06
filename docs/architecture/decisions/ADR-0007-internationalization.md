# ADR-0007 internationalization
Status is proposed.

## Context
The interface supports three locales.

## Problem
Translate text and format dates and amounts consistently.

## Options
Hardcoded labels or translation keys with locale formatting.

## Decision
Use react-i18next and locale formatting.

## Rationale
Business identifiers remain stable.

## Consequences
Update locale resources with each UI change.

## Risks
Missing keys and long strings affect usability.
