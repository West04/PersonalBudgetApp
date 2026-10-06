# ADR-002: No Generic Repository or Unit of Work

## Context

The project is a personal budget application with one concrete persistence technology and storage-specific queries/aggregations.

## Decision

Do not introduce `Repository<T>`, generic persistence ports, or a Unit of Work without a new observed/planned volatility requirement.

## Evidence / volatility

Current volatility is in concrete query/resource mechanics and business workflows, not persistence-engine substitution.

## Alternatives rejected

Generic repository/UoW patterns added for architectural symmetry or testability alone.

## Consequences

Accessors stay concrete. Tests should characterize concrete behavior rather than requiring speculative interfaces.
