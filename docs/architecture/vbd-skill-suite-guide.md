# VBD Skill Suite Guide

This suite contains three complementary skills for the budget-app modernization process.

## 1. VBD Architect
Use before changing code.

Purpose:
- distinguish observed/planned volatility from speculative volatility
- classify responsibilities as Presentation, Manager, Engine, Accessor/ResourceAccess, Resource, or None
- decide whether a boundary is actually justified
- reject unnecessary interfaces, Managers, Engines, DTOs, and configuration
- recommend the smallest next vertical slice

Typical request:
> Analyze this workflow using VBD and tell me whether it needs a Manager, Engine, Accessor, or should remain simple.

## 2. VBD Refactor
Use when implementing an approved architectural slice.

Purpose:
- preserve behavior
- require characterization tests first when safety is weak
- change one volatility boundary at a time
- prevent unrelated cleanup or product changes
- run the full test suite and stop for review

Typical request:
> Extract the approved transfer ResourceAccess boundary using the VBD refactor process.

## 3. VBD Reviewer
Use after an agent proposes or completes a change.

Purpose:
- review boundary correctness
- detect infrastructure leakage into Engines
- detect Manager/DTO/interface/configuration overengineering
- verify regression protection and scope discipline
- decide whether the slice is ready to commit

Typical request:
> Review this agent output using the VBD reviewer and tell me what should be cleaned up before I commit.

## Recommended workflow

```text
VBD Architect
    ↓
approve one boundary
    ↓
VBD Refactor
    ↓
full tests
    ↓
VBD Reviewer
    ↓
commit
    ↓
repeat
```

All three skills include the current budget-app context: completed Engines/Manager/Accessors, core financial invariants, known defects, unresolved product decisions, rejected speculative requirements, the Plaid encryption migration warning, and the accepted SQLAlchemy Session coupling.
