# ADR-005: Preserve the CSV Parser Boundary

## Context

Bank statement formats vary in headers, date formats, sign conventions, and configurable mappings. Multiple concrete parsers/configurations are in active use.

## Decision

Keep bank statement parsing as a specialized pure-ish ingestion boundary separate from FastAPI Presentation and database persistence.

## Evidence / volatility

USAA, Discover, and mapped/custom formats demonstrate current representation volatility.

## Consequences

Presentation may extract uploaded bytes but should not own persisted-format-driven parser construction or row-by-row application workflow. Managers/application code coordinate parser use.
