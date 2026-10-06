---
name: vbd-reviewer
description: "Review a budget-app architecture or refactor diff for compliance with the project volatility-based decomposition rules. Use after a VBD refactor or when auditing proposed changes for boundary correctness, speculative abstractions, dependency direction, behavior preservation, tests, transaction ownership, documentation drift, or unnecessary layering. Review first; do not redesign unrelated code."
---

# VBD Reviewer

Review the resulting code and diff against the project's VBD charter and the approved slice.

## Required reading

Read:

1. `AGENTS.md`
2. `docs/architecture/vbd-charter.md`
3. `docs/architecture/dependency-rules.md`
4. `docs/architecture/known-invariants.md`
5. `docs/architecture/documentation-maintenance.md`
6. the approved analysis/task for the slice
7. relevant workflow/ADR
8. the diff and affected source/tests

Use `references/review-rubric.md` as the scoring guide.

## Review workflow

1. Restate the intended one-slice architecture change.
2. Inspect the actual diff and affected call graph; do not trust the implementation summary alone.
3. Confirm the volatility evidence remains `OBSERVED` or `PLANNED`.
4. Check responsibility placement and dependency direction.
5. Check that no new speculative abstraction or layer ceremony was introduced.
6. Check behavior preservation against invariants and characterization tests.
7. Check transaction ownership and ensure unrelated transaction semantics did not change.
8. Check docs for topology drift.
9. Run or inspect test results as available.
10. Classify findings as `BLOCKING`, `MAJOR`, `MINOR`, or `OK`.
11. Recommend only fixes necessary for this slice. Do not expand the scope into the next roadmap item.

## VBD checks

Flag as blocking/major when appropriate:

- business workflow remains in Presentation after the slice claims to remove it
- ResourceAccess coordinates other ResourceAccess modules as application workflow
- business policy remains duplicated in persistence code after an authority refactor
- Engine gains HTTP/ORM/Session/SDK/filesystem/environment coupling
- Manager gains FastAPI transport coupling
- new Manager is only CRUD/pass-through
- new Engine is just a tiny helper with no independent volatility
- generic repository/UoW/provider/strategy/factory is added without evidence
- field-for-field DTO layer is added solely for layering
- known accounting behavior changes unintentionally
- docs claim topology that source does not implement

Do not flag as violations solely because:

- a Manager receives SQLAlchemy Session
- a simple CRUD Router calls an Accessor directly
- a concrete Accessor returns ORM objects where no stronger boundary is justified
- small pure helpers are not Engines

## Required output

Use `references/review-template.md`.
