# Budget App VBD Development Instructions

This repository is being modernized using volatility-based decomposition (VBD). Do not spread layers mechanically.

Before architectural analysis, reference:
- Skill: [vbd-architect](file:///Users/west/programming_stuff/budget_app/.agents/skills/vbd-architect/SKILL.md)
- Context: [docs/architecture/](file:///Users/west/programming_stuff/budget_app/docs/architecture/) (especially [current-state.md](file:///Users/west/programming_stuff/budget_app/docs/architecture/current-state.md) and [volatility-map.md](file:///Users/west/programming_stuff/budget_app/docs/architecture/volatility-map.md))

Before implementing an approved architectural slice, reference:
- Skill: [vbd-refactor](file:///Users/west/programming_stuff/budget_app/.agents/skills/vbd-refactor/SKILL.md)
- Safety & Context: [refactor-safety.md](file:///Users/west/programming_stuff/budget_app/docs/architecture/refactor-safety.md)

Before reviewing a completed slice, reference:
- Skill: [vbd-reviewer](file:///Users/west/programming_stuff/budget_app/.agents/skills/vbd-reviewer/SKILL.md)
- Context & Invariants: [docs/architecture/](file:///Users/west/programming_stuff/budget_app/docs/architecture/) and [checkpoint 1](file:///Users/west/programming_stuff/budget_app/docs/checkpoints/number_1.md)

For historical reasoning and decisions, reference:
- Session Handoff: [session_1.md](file:///Users/west/programming_stuff/budget_app/docs/session_handoffs/session_1.md)
- Modernization Checkpoint: [number_1.md](file:///Users/west/programming_stuff/budget_app/docs/checkpoints/number_1.md)

## Non-negotiable rules

1. Base architecture on observed or confirmed volatility, not plausible future features.
2. Manager = meaningful workflow sequencing.
3. Engine = independently volatile business algorithm/policy.
4. Accessor/ResourceAccess = concrete DB/API/file access.
5. Presentation = HTTP validation/errors/serialization.
6. Not every endpoint needs every layer.
7. Domain entities do not automatically become architectural components.
8. Prefer concrete functions/modules over interfaces and frameworks.
9. Characterize current behavior before structural extraction.
10. One volatility boundary -> one refactor -> full tests -> review -> commit.
11. Do not mix known bug fixes, product decisions, security migrations, or unrelated cleanup into structural refactors.
12. Stop after the requested slice; do not continue into the next architectural step automatically.
