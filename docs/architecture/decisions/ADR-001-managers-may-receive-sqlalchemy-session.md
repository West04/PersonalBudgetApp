# ADR-001: Managers May Receive SQLAlchemy Session

## Context

The application uses SQLAlchemy/PostgreSQL and has no observed or confirmed requirement to substitute a different persistence engine. Managers need transaction/workflow control for multi-step use cases.

## Decision

Managers may receive a concrete SQLAlchemy `Session` and may own commit/rollback boundaries for meaningful workflows.

## Evidence / volatility

Database-engine substitution is speculative. Transaction sequencing is observed in reconciliation, CSV import, ML training, recurring detection, splits, and Plaid sync.

## Alternatives rejected

- generic Unit of Work
- repository interfaces solely to hide SQLAlchemy
- DI framework introduced for persistence abstraction

## Consequences

Managers are coupled to the current persistence session abstraction, deliberately. Engines remain fully isolated from SQLAlchemy.
