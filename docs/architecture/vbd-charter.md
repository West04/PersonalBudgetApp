# VBD Architecture Charter

## Purpose

Refactor and evolve the budget app using the volatility-based decomposition principles from *Righting Software*. The goal is not visual layer symmetry. The goal is to isolate responsibilities that demonstrably change independently while keeping everything else concrete and simple.

## Governing rule

> Every independently volatile responsibility gets the smallest justified boundary. Code without demonstrated boundary value remains ordinary code.

Architecture is based on observed or confirmed volatility, not on database tables, REST endpoints, frontend screens, domain nouns, or folder symmetry.

## Evidence classes

Every proposed architectural boundary must be justified as one of:

- **OBSERVED** — current code, multiple implementations, duplicated policy, external integration pressure, or existing coupling demonstrates independent change.
- **PLANNED** — explicitly present in the confirmed roadmap.
- **SPECULATIVE** — merely plausible future change.

**SPECULATIVE volatility does not justify a new architectural boundary.**

## Responsibility classifications

### Presentation / Host
Owns transport-specific concerns:

- HTTP parsing and validation
- multipart/request extraction
- status-code and HTTP error mapping
- authentication/transport concerns if introduced
- Pydantic request/response serialization

Presentation must not own meaningful business workflow sequencing.

### Manager
Owns the sequence of a meaningful business use case when that sequence changes independently from transport and algorithms.

Good signals:

- coordinates several activities, Accessors, or Engines
- owns workflow order or transaction boundaries
- can be invoked independently of HTTP

Bad signals:

- one CRUD call
- pass-through wrapper
- one Manager per endpoint or screen by convention

### Engine
Owns an independently volatile business algorithm, policy, calculation, heuristic, or decision that can remain infrastructure-free.

Good signals:

- accounting calculation policy
- matching/detection heuristic
- duplicated deterministic business rules
- ML policy/evaluation logic

Bad signals:

- simple formatting
- one arithmetic helper with no independent volatility
- CRUD
- one Engine per pure function

### ResourceAccess / Accessor
Owns concrete interaction with a database, API, SDK, filesystem, or other resource when those mechanics would otherwise leak or change independently.

Good signals:

- SQLAlchemy queries and storage-specific aggregation
- external SDK or HTTP protocol details
- filesystem artifact operations

Bad signals:

- generic repository interfaces with no substitution need
- one Accessor per table by default
- hidden business sequencing across Accessors

### Resource
The external or persistent capability itself, such as PostgreSQL, Plaid, uploaded bytes, or local model artifact storage.

### None
Plain code that does not justify a special architectural boundary. This is a valid and preferred classification when no independent volatility is demonstrated.

## Dependency target

Preferred direction:

```text
Presentation -> Manager -> Engine and/or ResourceAccess -> Resource
Presentation -> ResourceAccess -> Resource   # only for genuinely simple CRUD
```

The reference pattern is not mandatory for every endpoint.

## Project-specific principles

- Managers may receive a concrete SQLAlchemy `Session`.
- Do not introduce Unit of Work, generic repositories, or DI solely to hide SQLAlchemy.
- External Plaid SDK access and raw `/transactions/sync` HTTP access are currently separate because actual integration behavior differs.
- CSV parser specialization is justified by actual bank-format/sign/date differences.
- Pure domain code must remain infrastructure-free.
- One architectural concern per refactor slice.
- Preserve observable behavior during structural refactors unless the task explicitly authorizes a behavior change.

## Definition of VBD success for this project

The project is considered consistently VBD-aligned when all currently demonstrated volatility is isolated behind justified boundaries, dependency direction follows this charter, business sequencing is not hidden in Presentation or ResourceAccess, and no speculative abstraction has been introduced to create architectural symmetry.
