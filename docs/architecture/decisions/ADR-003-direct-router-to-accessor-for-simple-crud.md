# ADR-003: Direct Router-to-Accessor Is Allowed for Simple CRUD

## Context

Not every endpoint contains independently volatile sequencing. Creating a Manager for every endpoint would be functional/layer decomposition rather than VBD.

## Decision

Allow `Presentation -> ResourceAccess` for genuinely simple CRUD or atomic access operations.

## Test

A direct path is acceptable when there is no meaningful multi-activity workflow, business algorithm, cross-resource sequencing, or transaction choreography that changes independently.

## Consequences

Do not create CRUD Managers merely to satisfy a layering diagram. Revisit the decision if the operation gains real sequencing behavior.
