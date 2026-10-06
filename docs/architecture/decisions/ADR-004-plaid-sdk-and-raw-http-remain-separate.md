# ADR-004: Plaid SDK and Raw Transaction-Sync HTTP Remain Separate

## Context

The application uses the official Plaid SDK for standard operations while transaction synchronization uses raw HTTP due to demonstrated cursor/SDK behavior.

## Decision

Keep the SDK access and `/transactions/sync` raw-HTTP access as separate concrete ResourceAccess boundaries while their access mechanisms have independent change pressure.

## Evidence / volatility

This split already exists because a real SDK limitation/behavior forced a different protocol implementation.

## Alternatives rejected

- generic `BankProvider` interface for hypothetical providers
- forcing all Plaid calls through one implementation merely for symmetry

## Consequences

Managers may coordinate both access mechanisms where a workflow requires them. The Accessors must not call each other to implement application sequencing.
