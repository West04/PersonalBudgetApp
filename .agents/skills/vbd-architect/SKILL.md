---
name: vbd-architect
description: "Analyze this budget app using volatility-based decomposition before architecture or refactor work. Use for reviewing boundaries, classifying Presentation/Manager/Engine/ResourceAccess responsibilities, identifying observed versus speculative volatility, deciding whether an abstraction is justified, tracing workflows, or selecting the smallest next VBD refactor slice. Analysis only; do not modify production code."
---

# VBD Architect

Perform evidence-first architecture analysis. Do not redesign from filenames, table names, endpoints, or screen names.

## Required reading

Read the repository versions of these files before project-specific conclusions:

1. `AGENTS.md`
2. `docs/architecture/vbd-charter.md`
3. `docs/architecture/dependency-rules.md`
4. `docs/architecture/volatility-registry.md`
5. `docs/architecture/known-invariants.md`
6. `docs/architecture/component-map.md`
7. `docs/architecture/workflow-catalog.md`
8. `docs/architecture/vbd-source-evidence-audit.md` when available
9. relevant ADRs

Use `references/project-context.md` as a compact fallback when repository docs are unavailable.

## Workflow

1. Trace the actual source workflow end-to-end before proposing a boundary.
2. Record responsibilities, dependencies, I/O, business rules, transaction ownership, and result contracts.
3. Classify each source of change as `OBSERVED`, `PLANNED`, or `SPECULATIVE`.
4. Reject `SPECULATIVE` volatility as architectural justification.
5. Classify responsibilities as `Presentation`, `Manager`, `Engine`, `ResourceAccess`, `Resource`, or `None`.
6. Apply the boundary tests below.
7. Identify the smallest correction; do not propose a broad rewrite when one dependency move is sufficient.
8. Identify overengineering explicitly: unnecessary Manager, Engine, Accessor, interface, provider abstraction, DTO, strategy, factory, repository, or Unit of Work.
9. Recommend exactly one next vertical slice unless the user asks for a broader roadmap.
10. Do not modify production code in this skill.

## Manager test

A Manager is justified when a meaningful use-case sequence changes independently from transport and algorithms.

Good signals:

- coordinates several activities/Accessors/Engines
- owns workflow order or transaction boundary
- can run independently of HTTP

Bad signals:

- one CRUD call
- pass-through wrapper
- one Manager per endpoint/screen

## Engine test

An Engine is justified when an independently volatile business algorithm/policy/heuristic can stay infrastructure-free.

Engines must not depend on HTTP, FastAPI, Pydantic transport schemas, SQLAlchemy, ORM models, Sessions, ResourceAccess, SDKs, network, filesystem, or environment variables.

Do not call a small pure helper an Engine merely because it is in `domain/`.

## ResourceAccess test

ResourceAccess is justified for concrete DB/API/SDK/file mechanics that would otherwise leak or change independently.

Do not:

- create one Accessor per table by rule
- add generic repository abstractions without substitution evidence
- hide business sequencing inside an Accessor
- use Accessor-to-Accessor calls to implement cross-resource workflow

## Abstraction gate

Before endorsing an interface/strategy/factory/DTO/configuration boundary, answer:

1. What demonstrated independent volatility does it protect?
2. Is there more than one current implementation or a confirmed near-term requirement?
3. Does it reduce coupling more than ceremony?

If not, keep it concrete.

## Required output

Use `references/analysis-template.md`. Include:

- current workflow
- volatility evidence
- responsibility classification
- boundary justification
- allowed/prohibited dependencies
- speculative ideas rejected
- smallest recommended slice
- behaviors/invariants that must not change

If source and docs disagree, report the discrepancy rather than silently choosing the desired architecture.
