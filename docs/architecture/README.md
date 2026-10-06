# Architecture Documentation

This directory contains the authoritative architecture specifications and controls for the Personal Budget App, decomposed along demonstrated axes of volatility following *Righting Software* (Juval Löwy).

## Authority Hierarchy

When evaluating system behavior and architecture, resolve discrepancies using this explicit hierarchy:

1. **Actual source code**  
   Authoritative for current runtime behavior.
2. **[vbd-source-evidence-audit.md](vbd-source-evidence-audit.md)**  
   Authoritative evidence snapshot of the audited source.
3. **[vbd-charter.md](vbd-charter.md)**  
   Authoritative VBD principles for this repository.
4. **[dependency-rules.md](dependency-rules.md)**  
   Authoritative dependency constraints.
5. **[component-map.md](component-map.md)** + **[workflow-catalog.md](workflow-catalog.md)**  
   Authoritative intended current decomposition.
6. **[decisions/](decisions/)** (ADRs)  
   Authoritative record of deliberate architecture decisions.
7. **[legacy/](legacy/)**  
   Historical context only.

---

## Core Architecture Documents

- **[vbd-charter.md](vbd-charter.md)** — Governing principles, evidence classes (OBSERVED, PLANNED, SPECULATIVE), layer definitions, and project-specific rules.
- **[volatility-registry.md](volatility-registry.md)** — Register of demonstrated and confirmed axes of volatility.
- **[component-map.md](component-map.md)** — Catalog of intended components (Presentation, Managers, Engines, ResourceAccess).
- **[dependency-rules.md](dependency-rules.md)** — Strict dependency direction rules and prohibited coupling patterns.
- **[workflow-catalog.md](workflow-catalog.md)** — Mapping of application workflows to their orchestrators, engines, and accessors.
- **[known-invariants.md](known-invariants.md)** — Immutable financial invariants, domain rules, and preserved defect baselines.
- **[refactor-roadmap.md](refactor-roadmap.md)** — Ordered sequence of prioritized architecture refactor slices.
- **[refactor-task-template.md](refactor-task-template.md)** — Pre-implementation task template required before each slice.
- **[review-checklist.md](review-checklist.md)** — Post-implementation review checklist to verify behavioral and structural boundaries.
- **[vbd-source-evidence-audit.md](vbd-source-evidence-audit.md)** — Source code evidence audit baseline.
- **[decisions/](decisions/)** — Architectural Decision Records (ADRs):
  - [ADR-001: Managers May Receive SQLAlchemy Session](decisions/ADR-001-managers-may-receive-sqlalchemy-session.md)
  - [ADR-002: No Generic Repository or Unit of Work](decisions/ADR-002-no-generic-repository-or-unit-of-work.md)
  - [ADR-003: Direct Router to Accessor for Simple CRUD](decisions/ADR-003-direct-router-to-accessor-for-simple-crud.md)
  - [ADR-004: Plaid SDK and Raw HTTP Remain Separate](decisions/ADR-004-plaid-sdk-and-raw-http-remain-separate.md)
  - [ADR-005: CSV Parser Boundary](decisions/ADR-005-csv-parser-boundary.md)
  - [ADR-006: No Speculative Provider Abstraction](decisions/ADR-006-no-speculative-provider-abstraction.md)
  - [ADR-007: Source Reality vs Intended Constraints](decisions/ADR-007-source-reality-vs-intended-constraints.md)
- **[legacy/](legacy/)** — Historical architecture documents preserved for project history:
  - [legacy/current-state.md](legacy/current-state.md)
  - [legacy/volatility-map.md](legacy/volatility-map.md)

---

## Workflow Specifications & Safety

- **[refactor-safety.md](refactor-safety.md)** — Refactoring protocols, test coverage requirements, and characterization rules.
- **[vbd-skill-suite-guide.md](vbd-skill-suite-guide.md)** — Guide to the three VBD repo-local skills (`vbd-architect`, `vbd-refactor`, `vbd-reviewer`).
- **Workflow Specs:**
  - [credit-card-summary.md](credit-card-summary.md)
  - [csv-import-confirmation.md](csv-import-confirmation.md)
  - [dashboard-summary.md](dashboard-summary.md)
  - [plaid-account-sync.md](plaid-account-sync.md)
  - [plaid-transaction-sync.md](plaid-transaction-sync.md)
  - [transfer-candidate-search.md](transfer-candidate-search.md)

---

## Required Refactor Workflow

1. Use `vbd-architect` before making architectural changes (analysis-only; classifies volatility and justifies boundaries).
2. Approve or select exactly one bounded refactor slice.
3. Use `vbd-refactor` to implement that slice without modifying unrelated behavior.
4. Run the full test suite.
5. Use `vbd-reviewer` to inspect the diff, dependencies, docs, and test evidence.
6. Commit only that slice.

---

## Architectural Priority Order

Refactor slices are addressed in this priority order based on the source evidence audit:

1. Move the live Plaid public-token exchange workflow out of the Router and retire the active legacy CRUD path.
2. Remove ResourceAccess-to-ResourceAccess workflow coupling, beginning with `transaction_access.py`.
3. Make categorization rule evaluation authoritative outside ResourceAccess.
4. Move CSV inspection/preview/loader orchestration out of the upload Router.
5. Remove FastAPI/Pydantic presentation coupling from Managers where it is not justified.
6. Re-evaluate Manager topology after boundary leaks are corrected.
7. Remove redundant DTO boundaries only when they lack independent semantics.

Do not combine these slices into a single rewrite.
