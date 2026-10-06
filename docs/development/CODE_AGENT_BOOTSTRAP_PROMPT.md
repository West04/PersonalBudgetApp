# Code Agent Bootstrap Prompt

Use this prompt when the code agent cannot automatically discover `AGENTS.md` or the `.agents/skills/` directory.

---

You are refactoring this personal budget application to follow the volatility-based decomposition (VBD) principles described in *Righting Software* as closely as the current evidence justifies.

Before changing production code, read in this order:

1. `AGENTS.md`
2. `docs/architecture/vbd-charter.md`
3. `docs/architecture/dependency-rules.md`
4. `docs/architecture/volatility-registry.md`
5. `docs/architecture/known-invariants.md`
6. `docs/architecture/component-map.md`
7. `docs/architecture/workflow-catalog.md`
8. `docs/architecture/refactor-roadmap.md`
9. `docs/architecture/vbd-source-evidence-audit.md`
10. relevant ADRs under `docs/architecture/decisions/`

For architecture work, follow the three-stage process:

- Analyze with `.agents/skills/vbd-architect/SKILL.md`.
- Implement exactly one approved slice with `.agents/skills/vbd-refactor/SKILL.md`.
- Review the resulting diff with `.agents/skills/vbd-reviewer/SKILL.md`.

Non-negotiable rules:

- Base boundaries on OBSERVED or explicitly PLANNED volatility only.
- SPECULATIVE volatility cannot justify a new abstraction.
- Manager = meaningful use-case sequencing.
- Engine = independently volatile pure business algorithm/policy.
- ResourceAccess = concrete DB/API/file/SDK interaction.
- Presentation = transport concerns.
- `None` is a valid classification; not every function needs a component.
- Do not create one Manager per endpoint, one Engine per pure function, or one Accessor per table by rule.
- Do not introduce generic repository, Unit of Work, DI, provider interfaces, strategy/factory layers, or DTOs without demonstrated independent volatility.
- Engines must remain infrastructure-free.
- ResourceAccess must not hide business sequencing or call other ResourceAccess modules to implement a workflow.
- Managers may receive SQLAlchemy Session.
- Direct Router -> Accessor is allowed for genuinely simple CRUD.
- Do not change known accounting behavior, product decisions, security migration, DB schema, or API contracts during a structural refactor unless explicitly in scope.
- One volatility boundary -> one refactor -> tests -> review -> commit.

Before implementation, produce the pre-refactor analysis required by `docs/architecture/refactor-task-template.md`. Do not modify production code until the current workflow, volatility evidence, target dependency, preserved behavior, and tests are explicit.

After implementation, run relevant tests and the full suite, inspect `git diff --stat` and the full diff, update architecture docs if topology changed, and report any source/docs discrepancy instead of hiding it.
---
