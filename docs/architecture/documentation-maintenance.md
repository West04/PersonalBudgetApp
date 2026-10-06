# Architecture Documentation Maintenance Policy

## Purpose

This document defines how architecture and VBD documentation for the Budget App must be maintained as the codebase changes.

The purpose is to prevent three common failures:

1. documentation drifting away from the actual source code;
2. historical evidence being rewritten to match newer architecture;
3. code agents updating implementation without updating the documentation that describes it.

Architecture documentation is part of the architecture.

A refactor is not complete when the code compiles or the tests pass. If the change affects a documented architectural boundary, workflow, invariant, volatility classification, or architectural decision, the relevant current-state documentation must be reviewed and updated in the same change.

---

# 1. Documentation Authority Model

The repository uses the following authority hierarchy.

## Level 1 — Source code

The actual source code is authoritative for:

- current runtime behavior;
- current dependency relationships;
- current call paths;
- current transaction behavior;
- current resource interactions;
- current imports and framework dependencies.

Documentation must never be used to claim that the code currently behaves differently from what the source demonstrates.

If documentation and source disagree:

1. report the discrepancy;
2. determine whether the source or the intended architecture should change;
3. do not silently rewrite one to match the other.

---

## Level 2 — Source evidence audits

Example:

```text
docs/architecture/vbd-source-evidence-audit.md
```

Source-evidence audits are historical snapshots of the source tree at a particular repository state.

They are authoritative for:

> What was observed in the source code when that audit was performed?

They are **not** living current-state documents.

Do not modify an old audit merely because the code changed later.

When a new full audit is required, create a new audit or clearly version the existing audit process according to the rules in this document.

---

## Level 3 — VBD charter

```text
docs/architecture/vbd-charter.md
```

The charter defines the architectural principles the repository intends to follow.

It answers questions such as:

- what VBD means in this project;
- how volatility is used to justify boundaries;
- what classifications exist;
- what principles take precedence.

The charter should change rarely.

---

## Level 4 — Dependency rules

```text
docs/architecture/dependency-rules.md
```

This document defines which dependency directions are allowed, discouraged, or prohibited.

It is authoritative for intended dependency constraints.

Examples include:

```text
Presentation -> Manager
Presentation -> ResourceAccess for simple CRUD
Manager -> Engine
Manager -> ResourceAccess
ResourceAccess -> Resource
```

and prohibited relationships such as infrastructure dependencies from Engines.

---

## Level 5 — Current architecture documentation

Examples:

```text
docs/architecture/component-map.md
docs/architecture/workflow-catalog.md
docs/architecture/known-invariants.md
docs/architecture/volatility-registry.md
docs/architecture/refactor-roadmap.md
```

These documents describe the intended current state of the application.

Unlike historical audits, these documents are expected to change as the architecture changes.

---

## Level 6 — Architecture Decision Records

```text
docs/architecture/decisions/
```

ADRs explain durable architectural decisions and why they were made.

They answer:

> Why did we choose this architecture?

They should not be rewritten merely because later work supersedes them.

If a decision changes, supersede the old ADR with a new ADR rather than erasing the historical reasoning.

---

## Level 7 — Historical architecture documentation

```text
docs/architecture/legacy/
```

These files are retained for historical context.

They are not authoritative for the current architecture.

Every document in this directory that could reasonably be mistaken for current documentation should contain a visible historical warning.

---

# 2. Core Maintenance Rule

Any change that alters a documented architectural fact must review the documentation describing that fact.

The required rule is:

```text
architecture change
        ↓
review affected current-state documentation
        ↓
update affected documentation
        ↓
review documentation against actual source
        ↓
commit code and documentation together
```

Do not intentionally leave current-state documentation incorrect with the expectation that it will be fixed later.

---

# 3. Documentation Is Changed by Evidence, Not Tidiness

Do not update architecture documentation merely to make the repository look more symmetrical.

Documentation should reflect demonstrated architecture.

Examples of valid reasons to update documentation:

- a Manager takes ownership of a workflow;
- an Engine is introduced for observed business-policy volatility;
- an Accessor boundary changes;
- a dependency is removed;
- transaction ownership changes;
- a resource interaction changes mechanism;
- a workflow sequence changes;
- an invariant changes intentionally;
- observed volatility is discovered;
- planned volatility becomes implemented;
- a durable architecture decision is made.

Examples that do not by themselves justify architectural documentation changes:

- renaming a local variable;
- formatting;
- moving a private helper without changing responsibility;
- reorganizing tests;
- minor internal implementation changes that preserve architectural ownership.

---

# 4. Required Review Matrix

Use this table whenever a change is made.

| Change | Required documentation review |
|---|---|
| New Manager | `component-map.md`, `workflow-catalog.md`, `volatility-registry.md` |
| Manager removed or merged | `component-map.md`, `workflow-catalog.md`, `refactor-roadmap.md` |
| Manager responsibility changes | `component-map.md`, `workflow-catalog.md` |
| New Engine | `component-map.md`, `volatility-registry.md`, relevant workflow docs |
| Engine algorithm changes without boundary change | relevant workflow/invariant docs |
| Engine removed | `component-map.md`, `workflow-catalog.md`, `volatility-registry.md` |
| New ResourceAccess boundary | `component-map.md`, `workflow-catalog.md`, `volatility-registry.md` |
| ResourceAccess responsibility changes | `component-map.md`, relevant workflow docs |
| Resource mechanism changes | `component-map.md`, `volatility-registry.md`, possibly ADR |
| Dependency direction changes | `component-map.md`, `dependency-rules.md` if the rule itself changes |
| Workflow sequence changes | `workflow-catalog.md` and relevant workflow-specific document |
| Transaction ownership changes | `workflow-catalog.md`, possibly ADR |
| Business invariant changes | `known-invariants.md` |
| New observed volatility | `volatility-registry.md` |
| Planned volatility implemented | `volatility-registry.md`, `component-map.md` if boundaries change |
| Speculative idea becomes planned | `volatility-registry.md` |
| Speculative idea rejected | usually no change unless rejection is durable enough for an ADR |
| Durable architecture decision | new ADR |
| Existing ADR superseded | new ADR that references the old ADR |
| Refactor slice completed | `refactor-roadmap.md` |
| Current-state architecture document found stale | correct it in the same change |
| Historical document found stale | do not rewrite history; move/mark as historical if necessary |
| Full source audit performed | create/update audit snapshot according to the audit policy below |

---

# 5. VBD Charter Maintenance

File:

```text
docs/architecture/vbd-charter.md
```

The charter should be stable.

Update it only when the project changes its architectural principles.

Do not modify the charter simply because:

- a new Manager is added;
- a new workflow exists;
- a particular refactor is completed;
- a component is renamed.

Valid reasons to change the charter include:

- changing the project's definition of a Manager;
- changing the project's accepted dependency model;
- changing how volatility evidence is classified;
- changing the fundamental abstraction policy.

Changes to the charter should receive deliberate human review.

---

# 6. Volatility Registry Maintenance

File:

```text
docs/architecture/volatility-registry.md
```

The volatility registry records evidence for architectural boundaries.

Every entry must be classified as:

```text
OBSERVED
PLANNED
SPECULATIVE
```

## OBSERVED

Use when current evidence demonstrates independent change.

Examples:

- multiple current implementations;
- duplicated business rules;
- external APIs changing independently;
- differing algorithms;
- resource mechanisms requiring separate handling;
- current coupling that demonstrates unrelated responsibilities changing together.

## PLANNED

Use only when an explicit confirmed requirement exists.

A vague possibility is not PLANNED.

## SPECULATIVE

Use when the idea is merely possible.

SPECULATIVE volatility must not justify a new abstraction.

---

## When volatility changes classification

If:

```text
SPECULATIVE -> PLANNED
```

update the registry when the requirement becomes explicit.

If:

```text
PLANNED -> OBSERVED
```

update the registry when implementation or actual behavior provides evidence.

Do not rewrite history to pretend the evidence existed earlier.

If useful, record the transition in the entry.

---

# 7. Component Map Maintenance

File:

```text
docs/architecture/component-map.md
```

The component map should describe architectural components that currently exist or are the currently approved target of an active refactor.

For each component, keep the following information current where applicable:

```text
Name
Classification
Responsibility
Volatility evidence
Public operations
Allowed dependencies
Prohibited dependencies
Resources accessed
Why the boundary exists
```

Do not add hypothetical future components.

A component belongs in the map because its boundary is justified by observed or explicitly planned volatility.

Do not create entries simply for symmetry.

---

# 8. Workflow Catalog Maintenance

File:

```text
docs/architecture/workflow-catalog.md
```

Document meaningful application workflows.

Examples include:

- CSV import confirmation;
- Plaid token exchange;
- Plaid account synchronization;
- Plaid transaction synchronization;
- reconciliation;
- transaction splitting;
- recurring transaction detection;
- ML retraining.

For each meaningful workflow, maintain:

```text
Trigger
Owning Manager, if justified
Sequence
Engines
ResourceAccess dependencies
Transaction owner
Commit point
Failure behavior
Output
```

Do not document every trivial CRUD endpoint as a workflow.

The workflow catalog is for meaningful application sequences.

---

# 9. Known Invariants Maintenance

File:

```text
docs/architecture/known-invariants.md
```

This file protects behavior during structural work.

Update it when a product or accounting rule intentionally changes.

Examples:

```text
Outflow/debit/charge > 0
Inflow/income/credit < 0
```

If an invariant is under product discussion, clearly label it as unresolved rather than silently changing it.

Architecture refactors must not change documented invariants unless the task explicitly includes a product behavior change.

---

# 10. Refactor Roadmap Maintenance

File:

```text
docs/architecture/refactor-roadmap.md
```

The roadmap should show the next known architecture work without turning speculative ideas into commitments.

After completing a slice:

- mark the slice complete;
- record the commit if useful;
- update dependencies or sequencing if the completed work changes later priorities;
- identify the next smallest justified slice.

Do not automatically add every discovered smell to the active roadmap.

A roadmap item should have evidence.

---

# 11. ADR Maintenance

Directory:

```text
docs/architecture/decisions/
```

Create an ADR when the project makes a durable decision whose reasoning future developers or agents need to understand.

Examples:

- allowing Managers to receive SQLAlchemy Session;
- rejecting generic Repository/Unit of Work;
- allowing direct Router-to-Accessor simple CRUD;
- retaining separate Plaid SDK and raw HTTP access;
- retaining a parser boundary;
- rejecting speculative provider abstraction.

Do not create ADRs for:

- minor renames;
- implementation details;
- one-off helper movement;
- obvious local code cleanup.

---

## ADRs are append-only historical records

Do not rewrite an accepted ADR to pretend that a later decision was always the original decision.

If a decision changes:

1. preserve the original ADR;
2. create a new ADR;
3. mark the old ADR as superseded if appropriate;
4. link the new ADR to the old one;
5. explain what new evidence caused the change.

Example:

```text
ADR-008 supersedes ADR-004
```

The historical reasoning remains valuable.

---

# 12. Source Evidence Audit Maintenance

Source audits are snapshots.

An audit must identify at least:

```text
repository commit / HEAD
audit date
scope
major findings
```

Do not edit an older audit's findings after code changes.

If another comprehensive audit is performed, prefer one of these approaches:

```text
vbd-source-evidence-audit-2026-10-06.md
vbd-source-evidence-audit-2027-01-15.md
```

or maintain:

```text
docs/architecture/audits/
```

with dated snapshots.

If the existing audit filename remains canonical, preserve its historical metadata and create a new dated audit instead of replacing evidence silently.

---

# 13. Legacy Documentation Maintenance

Directory:

```text
docs/architecture/legacy/
```

Move a document here when:

- it previously claimed to represent the current architecture;
- the source and current architecture docs have superseded it;
- it still has historical value.

Do not move a useful workflow or product document to `legacy/` merely because it is old.

Historical documents should contain a warning such as:

```markdown
> [!WARNING]
> Historical architecture document.
>
> This document is retained for project history and does not represent
> the authoritative current architecture.
```

Where possible, link to the corresponding current documents.

---

# 14. Documentation Maintenance During a VBD Refactor

Every VBD refactor must include a documentation review.

The normal sequence is:

```text
1. vbd-architect analyzes current source.

2. A single refactor slice is approved.

3. vbd-refactor changes implementation.

4. Tests verify behavior.

5. Current architecture documentation is reviewed.

6. Affected current-state documents are updated.

7. vbd-reviewer compares:
      source
      diff
      architecture docs
      ADRs
      tests

8. Documentation inconsistencies are treated as review findings.

9. Only after review passes is the slice committed.
```

Documentation maintenance is part of the slice, not a later cleanup task.

---

# 15. Required Documentation Check Before Commit

Before an architecture-changing commit, answer:

```text
Did component ownership change?

Did workflow sequencing change?

Did dependency direction change?

Did transaction ownership change?

Did an Engine policy change?

Did resource interaction change?

Was a new source of volatility discovered?

Did a volatility classification change?

Did a business invariant change?

Was a durable architectural decision made?

Was a roadmap slice completed?

Did any existing current-state documentation become false?
```

For every YES answer, identify which document was reviewed and whether it required an update.

---

# 16. Code Agent Requirements

Any code agent performing architecture work must read:

```text
AGENTS.md
docs/architecture/vbd-charter.md
docs/architecture/dependency-rules.md
docs/architecture/documentation-maintenance.md
```

and all task-relevant architecture documents.

The code agent must not assume documentation is correct without checking the current source.

The agent must distinguish:

```text
source reality
```

from:

```text
intended architecture
```

If they conflict, the agent must report the conflict.

---

# 17. Required Code Agent Documentation Report

Every architecture-changing task should end with:

```markdown
## Documentation Review

### Documents reviewed
- ...

### Documents updated
- ...

### Documents reviewed but unchanged
- ...

### New ADRs
- ...

### Volatility registry changes
- ...

### Workflow catalog changes
- ...

### Component map changes
- ...

### Invariant changes
NONE

or list them explicitly.

### Historical documents modified
NONE

or explain why.

### Documentation/source discrepancies remaining
NONE

or list them explicitly.
```

A report of:

```text
Documentation updated
```

without naming the files is insufficient.

---

# 18. Reviewer Requirements

The VBD reviewer must treat stale documentation as an architecture review failure when the documentation claims to describe the current state.

The reviewer must inspect:

```text
source
git diff
component-map.md
workflow-catalog.md
dependency-rules.md
volatility-registry.md
known-invariants.md
relevant ADRs
documentation-maintenance.md
```

as applicable.

The reviewer should return:

```text
CHANGES REQUIRED
```

when:

- code changes a documented architecture boundary but current docs remain stale;
- documentation claims dependencies that no longer exist;
- documentation omits newly introduced architectural components;
- a new abstraction lacks volatility evidence;
- a durable decision changed without appropriate ADR treatment;
- historical evidence was rewritten incorrectly.

---

# 19. Automated Documentation Checks

If repository-local documentation verification skills exist, use them as additional checks.

Examples may include:

```text
.agents/skills/doc-staleness-checker/
.agents/skills/doc-truth-verifier/
```

When available, follow each skill's own `SKILL.md`.

These checks supplement human and VBD review.

They do not override source inspection.

---

# 20. Documentation Review Frequency

Documentation should primarily be maintained event-by-event rather than through occasional large cleanup efforts.

Required:

```text
Every architecture-changing refactor
-> documentation review
```

Recommended:

```text
Before major new feature work
-> check relevant architecture docs

After several completed VBD slices
-> run a broader documentation/source consistency review

Before declaring the VBD migration complete
-> perform a new full source-evidence audit
```

The preferred strategy is continuous maintenance rather than periodic repair.

---

# 21. New Feature Documentation Rule

A new feature does not automatically require new architecture documentation.

First determine whether the feature:

```text
fits an existing volatility boundary
```

or:

```text
introduces new independent volatility
```

If it fits existing boundaries, update only the relevant workflow/product documentation.

If it demonstrates new volatility:

1. add evidence to `volatility-registry.md`;
2. determine whether an architectural boundary is justified;
3. update `component-map.md` if a boundary changes;
4. update `workflow-catalog.md` if sequencing changes;
5. create an ADR only if a durable decision warrants one.

---

# 22. Bug Fix Documentation Rule

A normal bug fix does not automatically require architecture documentation changes.

Update architecture documentation only if the bug fix changes or reveals:

- component responsibility;
- dependency direction;
- transaction ownership;
- business invariant;
- resource boundary;
- volatility evidence.

If a bug reveals an architecture problem but fixing that architecture is out of scope:

1. fix only the bug if appropriate;
2. record the architecture issue separately;
3. do not silently broaden the bug fix into a structural refactor.

---

# 23. Product Decisions vs Architecture Decisions

Architecture documentation must not silently decide unresolved product semantics.

Examples:

```text
Should future-dated transactions count toward balance owed?

Should transfers count toward a particular metric?

How should competing transfer candidates be prioritized?
```

These are product/domain decisions.

VBD determines where the policy should live.

It does not determine what the policy should be.

Document unresolved product questions explicitly and avoid encoding accidental behavior as intentional architecture.

---

# 24. Documentation Anti-Patterns

Do not:

- rewrite historical audits to match current code;
- keep two competing documents that both claim to describe current architecture;
- document hypothetical components;
- create ADRs for trivial changes;
- silently change volatility classifications;
- copy code structure directly into docs without explaining responsibility;
- make diagrams authoritative when source contradicts them;
- leave current-state docs stale after a known architectural change;
- treat generated documentation as correct without source verification;
- use documentation cleanup as an excuse for unrelated refactoring.

---

# 25. Definition of Done for Architecture Documentation

An architecture-changing refactor is documentation-complete only when all of the following are true:

```text
[ ] Source code reflects the approved slice.

[ ] Tests verify preserved behavior.

[ ] component-map.md reflects current component ownership.

[ ] workflow-catalog.md reflects current meaningful sequences.

[ ] volatility-registry.md reflects any new volatility evidence.

[ ] dependency-rules.md remains accurate.

[ ] known-invariants.md remains accurate.

[ ] refactor-roadmap.md reflects slice completion where applicable.

[ ] ADRs reflect any durable new decision.

[ ] Historical audits were not rewritten incorrectly.

[ ] Legacy documents are clearly marked historical.

[ ] No current-state documentation contradicts the source.

[ ] VBD reviewer has checked documentation consistency.

[ ] Documentation and implementation are committed together.
```

---

# 26. Responsibility for Documentation

The person or code agent making an architecture change is responsible for reviewing the documentation affected by that change.

Do not rely on a later "documentation cleanup."

The reviewer is responsible for checking that this review occurred.

The human maintainer retains final responsibility for approving architectural decisions and determining whether unresolved semantic questions require product decisions rather than structural changes.

---

# 27. Guiding Principle

Documentation should answer two different questions without confusing them:

```text
What does the system actually do?
```

and:

```text
What architectural rules do we intend the system to follow?
```

Source evidence and historical audits answer the first question.

The VBD charter, dependency rules, component map, workflow catalog, volatility registry, invariants, and ADRs govern the second.

When reality and intent differ, preserve the evidence, report the difference, and resolve it deliberately.

Do not rewrite history.

Do not document speculation as architecture.

Keep the current architecture documents synchronized with the code after every architectural slice.