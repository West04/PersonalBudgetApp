# VBD Code-Agent Workflow Guide

This guide defines how to make changes to the Budget App with a code agent while preserving the Volatility-Based Decomposition rules established for the project.

The goal is not merely to make the code "cleaner."

The goal is:

> Change one demonstrated volatility boundary at a time, preserve observable behavior, verify the resulting dependency structure, and keep the architecture documentation synchronized with the actual code.

The normal workflow is:

```text
Choose one problem
      ↓
vbd-architect
      ↓
approve one small slice
      ↓
vbd-refactor
      ↓
tests
      ↓
vbd-reviewer
      ↓
human review
      ↓
commit
```

Do not skip directly from "I see something ugly" to "refactor it."

---

# 1. Start from a clean checkpoint

Before beginning architectural work:

```bash
git status
git log -1 --oneline
```

Prefer a clean working tree.

If unrelated changes already exist, either finish them first or make sure the agent knows they are out of scope.

Do not mix:

```text
feature development
+
bug fixes
+
architecture refactor
```

in the same change unless one genuinely requires the others.

For architecture work, create a dedicated branch if desired:

```bash
git switch -c refactor/<short-slice-name>
```

Example:

```bash
git switch -c refactor/plaid-token-exchange-vbd
```

---

# 2. Choose one concrete architectural problem

Do not start with:

> Refactor transactions to VBD.

That is too broad.

Instead choose something like:

```text
Plaid public-token exchange workflow lives in the Router.

transaction_access calls split_access and ml_model_access.

CSV preview orchestration lives in upload.py.

AccountReconciliationManager raises FastAPI HTTPException.

Rule matching is duplicated inside transaction_access.
```

The unit of work should be one **volatility boundary**, not one subsystem.

Use:

```text
docs/architecture/refactor-roadmap.md
```

to select the next slice when possible.

---

# 3. Run the architecture pass first

Use:

```text
.agents/skills/vbd-architect/
```

The architecture pass is analysis only.

Do not allow production code modifications during this phase.

A good prompt is:

```text
Use vbd-architect.

Analyze [WORKFLOW].

Before analysis:
- read AGENTS.md;
- read the vbd-architect skill;
- read the relevant architecture docs and ADRs;
- inspect the actual source and callers.

Do not modify production code.

Determine:
1. the current workflow;
2. current responsibilities;
3. dependencies;
4. transaction ownership;
5. business rules;
6. the actual volatility axis;
7. whether volatility is OBSERVED, PLANNED, or SPECULATIVE;
8. the correct VBD classification of each responsibility;
9. the smallest justified boundary correction;
10. the target dependency graph;
11. behavior that must remain unchanged;
12. files likely affected.

Explicitly reject speculative abstractions.

Finish with one recommended vertical slice.
```

---

# 4. Require an architecture preflight

Before you approve implementation, the architecture agent should give you something approximately like:

```text
Workflow:
...

Observed volatility:
...

Current responsibilities:
Presentation:
Manager:
Engine:
ResourceAccess:
Resource:

Current dependency issue:
...

Target dependency:
...

Boundary justified because:
...

Speculative alternatives rejected:
...

Behavior that must remain unchanged:
...

Recommended slice:
...
```

Do not proceed if the reasoning is basically:

> This would be cleaner.

or:

> This pattern is more scalable.

Those are not sufficient VBD justifications.

The key question is:

> What has demonstrated that this responsibility changes independently?

---

# 5. Apply the volatility test yourself

Before approving the plan, ask three questions.

## Is the volatility real?

It should be classified as:

```text
OBSERVED
```

when current code proves it through things such as:

- duplicated business rules;
- multiple implementations;
- external integration behavior;
- repeated independent changes;
- coupling across responsibilities;
- differing algorithms;
- multiple resource mechanisms.

It may be:

```text
PLANNED
```

only when an explicit requirement or roadmap item exists.

It must not justify architecture when merely:

```text
SPECULATIVE
```

Examples of speculation:

```text
Maybe we'll use Mongo someday.

Maybe we'll replace Plaid.

Maybe we'll have multiple currencies.

Maybe we'll need GraphQL.

Maybe another budgeting algorithm will exist.
```

Do not build boundaries for those unless they become real requirements.

---

# 6. Apply the component test

For every proposed component, ask what kind of responsibility it really is.

## Presentation

Good fit:

```text
HTTP request parsing
status codes
serialization
multipart handling
transport validation
```

Presentation should not own:

```text
multi-step business workflow
business calculations
transaction sequencing
SDK orchestration
database queries
```

## Manager

Good fit:

```text
meaningful use-case sequencing
multiple activities
transaction ownership
Engine + ResourceAccess coordination
```

Bad reason to create one:

```text
there is an endpoint
there is a screen
there is a database model
every Router should have a Manager
```

## Engine

Good fit:

```text
business calculation
matching algorithm
heuristic
policy
decision rule
```

An Engine must remain infrastructure-free.

No:

```text
FastAPI
HTTP
SQLAlchemy Session
ORM models
ResourceAccess
Plaid SDK
filesystem
environment variables
```

## ResourceAccess

Good fit:

```text
SQLAlchemy query behavior
Plaid SDK calls
raw HTTP integration
filesystem model storage
storage-specific aggregation
```

ResourceAccess should not become an application workflow coordinator.

Avoid:

```text
ResourceAccess -> ResourceAccess
```

when that relationship represents sequencing between resources.

## None

This is a valid and important classification.

Use ordinary code for:

```text
small helpers
simple formatting
tiny calculations
simple CRUD
```

Do not force everything into a VBD architectural component.

---

# 7. Approve only the smallest justified slice

Suppose analysis finds:

```text
transaction_access
 -> split_access
 -> ml_model_access
 -> categorization_rule_access
```

Do not respond with:

> Rewrite all transaction architecture.

Instead select one atomic correction.

For example:

```text
Move manual transaction update sequencing out of TransactionAccess,
while preserving list/get/delete behavior unchanged.
```

The principle is:

```text
one volatility boundary
       ↓
one refactor
       ↓
tests
       ↓
review
       ↓
commit
```

---

# 8. Use vbd-refactor for implementation

After approving the architecture plan, start a fresh code-agent task using:

```text
.agents/skills/vbd-refactor/
```

Do not ask it to redesign the architecture again.

Give it the approved plan.

Example:

```text
Use vbd-refactor.

Implement the approved VBD slice:

[PASTE APPROVED SLICE]

Before editing:
- read AGENTS.md;
- load vbd-refactor;
- read the relevant architecture documents and ADRs;
- inspect current tests for this workflow.

Stay strictly within this slice.

Preserve existing observable behavior.

Do not:
- introduce speculative abstractions;
- redesign adjacent workflows;
- create generic repositories or Unit of Work;
- change database schemas;
- change API contracts;
- fix unrelated bugs;
- change accounting semantics.

Run characterization tests before changes where useful.

After implementation:
- run targeted tests;
- run the broader relevant test suite;
- inspect the diff;
- update current architecture documentation if the dependency structure changed.

Finish with the required refactor report.
```

---

# 9. Require the implementation agent to show its preflight

Before code changes, it should report:

```text
Skill loaded:
vbd-refactor

Documents read:
...

Approved slice:
...

Behavior being preserved:
...

Expected files to change:
...

Files explicitly out of scope:
...

Tests protecting this behavior:
...
```

If it starts editing without doing this, stop the task.

---

# 10. Protect behavior before changing structure

Architecture refactoring should ordinarily preserve behavior.

Tests should answer:

```text
Did we move responsibility
without changing what the app does?
```

For important workflows, prefer existing characterization tests.

If behavior is insufficiently protected, adding a characterization test before moving code can be appropriate.

But do not rewrite tests merely to mirror the new implementation structure.

A good architecture refactor should make old behavioral tests continue to pass.

---

# 11. Watch transaction ownership carefully

For mutating workflows, explicitly identify:

```text
Who starts the sequence?

Who stages mutations?

Who commits?

Who rolls back?

What must be atomic?
```

Managers should generally own transaction/workflow order for meaningful multi-step use cases.

ResourceAccess may stage or flush as appropriate.

Do not move transaction boundaries accidentally while merely reorganizing functions.

Transaction changes can alter behavior even when API outputs appear unchanged.

---

# 12. Do not "clean up while you're there"

This is one of the most important rules for agent-driven refactoring.

If the agent notices:

```text
bad variable names
duplicate helpers
security issue
schema mismatch
unrelated dead code
formatting problems
another architecture smell
```

it should report them, not automatically fix them.

Keep a separate follow-up list.

This makes failures diagnosable.

Bad:

```text
VBD refactor
+ rename 20 modules
+ fix token encryption
+ fix category cascade
+ change schema types
```

Good:

```text
VBD boundary correction only
```

---

# 13. Update documentation only when architecture actually changes

After a successful slice, update current architecture documents such as:

```text
docs/architecture/component-map.md
docs/architecture/workflow-catalog.md
docs/architecture/refactor-roadmap.md
```

Do not rewrite:

```text
docs/architecture/vbd-source-evidence-audit.md
```

to make old evidence match the new system.

That audit represents a historical source snapshot.

If a durable new decision is made, consider an ADR.

Examples:

```text
"We now treat X workflow as Manager-owned."

"We deliberately retain two Plaid ResourceAccess components because
SDK and raw-HTTP protocol volatility remain independent."
```

Do not create an ADR for every renamed function.

---

# 14. Run the reviewer independently

After implementation succeeds, start a new code-agent review using:

```text
.agents/skills/vbd-reviewer/
```

Do not simply ask the implementation agent:

> Does your work look good?

Have the reviewer inspect the actual source and diff independently.

Use:

```text
Use vbd-reviewer.

Review the just-completed VBD refactor.

Read:
- AGENTS.md;
- the vbd-reviewer skill;
- relevant architecture docs;
- the approved architecture plan;
- the actual git diff;
- all changed source files;
- relevant callers and tests.

Do not modify production code.

Do not trust the implementation agent's summary.

Verify:
1. scope discipline;
2. behavior preservation;
3. dependency direction;
4. Manager/Engine/ResourceAccess classification;
5. transaction ownership;
6. no new speculative abstractions;
7. no presentation leakage;
8. no ResourceAccess orchestration leakage;
9. no unnecessary DTO or interface layers;
10. documentation consistency.

Return:
PASS

or

CHANGES REQUIRED

with concrete evidence for every issue.
```

---

# 15. Treat reviewer findings as blockers

If the reviewer says:

```text
CHANGES REQUIRED
```

do not commit yet.

Give only those findings back to the implementation agent.

Example:

```text
Use vbd-refactor.

Address only these reviewer findings:

1. ...
2. ...

Do not make any other architecture changes.

Re-run the relevant tests and provide an updated completion report.
```

Then run `vbd-reviewer` again.

Repeat until:

```text
PASS
```

---

# 16. Perform your own human review

You do not need to understand every Python line to review architecture effectively.

Check the diff for these questions:

```text
Did the agent change more files than expected?

Did business behavior change?

Did it introduce new classes/interfaces that were not in the plan?

Did a Router gain more responsibility?

Did an Engine import infrastructure?

Does ResourceAccess call another ResourceAccess?

Did a Manager start knowing about HTTP?

Did the change create DTOs that simply duplicate other types?

Did it modify unrelated code?

Did documentation change consistently?
```

If something surprises you, ask why before committing.

Unexpected architecture is a reason to investigate.

---

# 17. Inspect Git before every commit

Run:

```bash
git status
git diff --stat
git diff
```

If already staged:

```bash
git diff --cached --stat
git diff --cached
```

Make sure the diff contains only the intended slice.

Then commit.

Example:

```bash
git add ...
git commit -m "refactor plaid token exchange boundary"
```

Avoid giant commits such as:

```text
refactor architecture
```

Prefer commits that describe one boundary correction.

---

# 18. Stop after the commit

Do not let the agent automatically begin the next roadmap item.

After each slice:

```text
tests green
review PASS
docs current
commit complete
```

then stop.

Take the next slice as a fresh task.

This creates useful checkpoints and prevents architecture drift.

---

# 19. Use separate prompts for feature work

Not every change is an architecture refactor.

Suppose you want to add:

```text
ability to hide an account
```

Do not automatically invoke a full architecture redesign.

First ask:

```text
Does this feature introduce a new source of volatility,
or does it fit existing boundaries?
```

A feature prompt can say:

```text
Implement [FEATURE].

Follow AGENTS.md and existing architecture.

Use the existing boundaries unless the new requirement provides
concrete evidence that a boundary no longer fits.

Do not create new architectural components merely because a feature
is being added.
```

If the feature exposes a real boundary problem, then run `vbd-architect`.

---

# 20. Use a different process for bugs

For a normal bug:

```text
reproduce
understand cause
write/fix test
make smallest correction
verify
```

Do not turn every bug fix into a VBD exercise.

If the bug reveals that responsibility is misplaced, record an architecture follow-up separately.

---

# 21. Keep product decisions separate from architectural decisions

Some questions are about product semantics, not VBD.

For example:

```text
Should future-dated credit-card transactions count?

Should transfers count toward balance owed?

Should recurring detection require two or three occurrences?
```

These are product/domain decisions.

VBD can tell you **where that policy belongs**, but not **what the policy should be**.

Resolve product semantics intentionally before refactoring around them.

---

# 22. Red flags that should stop a refactor

Stop and reconsider if the agent proposes:

```text
IRepository<T>

IUnitOfWork

generic service layer

one Manager for every Router

one Engine for every calculation

one Accessor for every table

BankProvider interface when Plaid is the only provider

database abstraction because another DB might be used someday

large DTO hierarchy to avoid passing ordinary data

message bus/event architecture without an actual requirement
```

Ask:

> What demonstrated volatility justifies this?

If there is no concrete answer, reject it.

---

# 23. Green flags

Good VBD refactors often produce simpler dependency graphs.

For example:

Before:

```text
Router
  -> TransactionAccess
       -> SplitAccess
       -> MLModelAccess
       -> CategorizationRuleAccess
```

After:

```text
Router
  -> Manager
       -> TransactionAccess
       -> SplitAccess
       -> MLModelAccess
       -> Categorization policy
```

Another good result:

Before:

```text
Router
  -> Plaid SDK
  -> legacy CRUD
  -> db.commit()
```

After:

```text
Router
  -> Manager
       -> Plaid ResourceAccess
       -> DB ResourceAccess
       -> commit workflow
```

The goal is not more layers.

The goal is clearer ownership of independent change.

---

# 24. A short everyday workflow

Once you become comfortable with the process, most architecture changes can follow this routine:

```text
1. Pick one roadmap item.

2. Ask vbd-architect to analyze it.

3. Read the proposed volatility evidence.

4. Approve one small slice.

5. Ask vbd-refactor to implement only that slice.

6. Run tests.

7. Ask vbd-reviewer to inspect the actual diff.

8. Fix reviewer findings.

9. Inspect git diff yourself.

10. Commit.

11. Stop.
```

---

# 25. Minimal architect prompt

```text
Use vbd-architect.

Analyze [WORKFLOW/PROBLEM].

Follow AGENTS.md and the architecture docs.

Analysis only. Do not modify production code.

Identify current workflow, demonstrated volatility, VBD classifications,
dependency violations, behavior to preserve, and the smallest justified
vertical slice.

Explicitly reject speculative abstractions.
```

---

# 26. Minimal implementation prompt

```text
Use vbd-refactor.

Implement this approved VBD slice:

[SLICE]

Follow AGENTS.md and all relevant architecture docs/ADRs.

Show the required preflight before editing.

Preserve behavior.
Do not broaden scope.
Run targeted and broader tests.
Update current architecture docs if required.
Finish with the required refactor report.
```

---

# 27. Minimal reviewer prompt

```text
Use vbd-reviewer.

Independently review the completed refactor for:

[SLICE]

Read the actual diff and changed source.
Do not trust the implementation summary.
Do not modify production code.

Check VBD boundaries, dependency direction, transaction ownership,
behavior preservation, scope discipline, tests, and documentation.

Return PASS or CHANGES REQUIRED with evidence.
```

---

# 28. When you are unsure what to do next

Do not ask the code agent:

> What should I refactor next?

Instead use:

```text
Use vbd-architect.

Review docs/architecture/refactor-roadmap.md and the current source.

Recommend the next smallest VBD refactor based only on OBSERVED or
explicitly PLANNED volatility.

Do not modify code.
Do not propose speculative architecture.
```

This keeps prioritization tied to evidence.

---

# 29. The rule to remember

When evaluating any architecture suggestion, ask:

> What changes independently, and what evidence do we have?

Then:

> What is the smallest boundary that contains that change?

If those questions cannot be answered clearly, do not refactor yet.

The desired outcome is not the maximum number of VBD components.

The desired outcome is:

```text
Every demonstrated source of independent volatility
has the smallest justified boundary,

and everything else remains simple.
```