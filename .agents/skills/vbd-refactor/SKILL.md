---
name: vbd-refactor
description: "Implement one evidence-approved volatility-based decomposition refactor slice in the budget app while preserving behavior. Use after a VBD analysis has identified a concrete boundary correction, such as moving workflow sequencing out of a Router or ResourceAccess, removing infrastructure from business logic, or correcting a dependency edge. Requires tests, minimal scope, documentation updates, and no speculative abstractions."
---

# VBD Refactor

Implement exactly one bounded architecture correction. Do not continue into the next roadmap item automatically.

## Required reading

Read:

1. `AGENTS.md`
2. `docs/architecture/vbd-charter.md`
3. `docs/architecture/dependency-rules.md`
4. `docs/architecture/known-invariants.md`
5. `docs/architecture/documentation-maintenance.md`
6. the relevant workflow in `workflow-catalog.md`
7. the relevant roadmap slice/ADR
8. the approved VBD analysis for this change

Use `references/project-context.md` when repository docs are unavailable.

## Preconditions

Do not implement until these are explicit:

- current workflow
- `OBSERVED` or `PLANNED` volatility evidence
- responsibility classification
- target dependency change
- behavior that must remain unchanged
- tests that protect the workflow

If the requested change is justified only by `SPECULATIVE` volatility, stop and report that the abstraction is not justified.

## Refactor workflow

1. Inspect the exact source and tests for the selected workflow.
2. Add or strengthen characterization tests only when needed to protect current behavior.
3. Make the smallest change that corrects the approved boundary.
4. Keep business behavior unchanged unless explicitly authorized.
5. Keep Engines infrastructure-free.
6. Keep multi-step workflow sequencing in Managers rather than Presentation or ResourceAccess.
7. Allow simple Router -> Accessor CRUD to remain simple.
8. Do not replace transport coupling with duplicate DTO ceremony.
9. Do not add generic repository/UoW/provider/factory/strategy interfaces without demonstrated volatility.
10. Do not perform unrelated cleanup, renames, bug fixes, schema changes, security migrations, or product decisions.
11. Run focused tests during implementation.
12. Run the full relevant/full suite before completion.
13. Review `git diff --stat` and the full diff.
14. Update architecture docs in the same slice if topology changed.
15. Stop and hand the diff to `vbd-reviewer`.

## Transaction rule

Managers may receive SQLAlchemy Session and may own commit/rollback for meaningful workflows. Do not change transaction granularity unless transaction semantics are explicitly in scope.

Standalone simple CRUD Accessors may retain atomic commits.

## Current project state

The VBD modernization program is complete.

Established boundaries:
- Presentation -> Manager -> Engine / Accessor -> Resource.
- Simple CRUD may remain Presentation -> Accessor -> Resource.
- Managers may receive SQLAlchemy Session.
- Engines remain pure and infrastructure-free.

Resolved hardening decisions:
- Transaction.description is TEXT NOT NULL; "" represents missing description text.
- Non-empty category-group deletion is rejected.
- Category deletion preserves transactions as uncategorized, cascades budgets/rules, and split references block deletion.
- Plaid access tokens use authenticated enc:v1: Fernet encryption.
- Credit-card metrics use point-in-time balance, gross non-transfer charges, and transfer-only payments.
- Transfer matching uses deterministic closest-first greedy suggestion matching.

Do not propose additional architecture merely because another abstraction is possible.
New structural work requires observed volatility or an explicit roadmap requirement.

## Required completion report

Use `references/completion-template.md` and report:

- before -> after dependency
- files changed
- dependencies removed/introduced
- behavior changes (`NONE` unless authorized)
- tests run/results
- docs updated
- known issues intentionally untouched
- remaining concern for reviewer
