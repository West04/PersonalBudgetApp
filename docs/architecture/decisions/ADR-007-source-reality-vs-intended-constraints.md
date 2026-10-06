# ADR-007: Source Code Defines Current Reality; Architecture Docs Define Intended Constraints

## Context

The source evidence audit found stale dependency edges in prior architecture diagrams.

## Decision

When source and architecture docs disagree:

1. treat source code and executable tests as authoritative for current behavior;
2. treat the charter, dependency rules, accepted ADRs, and approved refactor plan as authoritative for intended constraints;
3. report the discrepancy before changing code;
4. update topology documentation in the same slice that changes architecture.

## Consequences

Agents must not silently implement a stale diagram, and must not silently rewrite intended rules to match accidental code drift.
