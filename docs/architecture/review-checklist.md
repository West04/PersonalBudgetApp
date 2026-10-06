# VBD Post-Refactor Review Checklist

## Boundary correctness

- [ ] The change is justified by OBSERVED or PLANNED volatility.
- [ ] No new abstraction is justified only by hypothetical future change.
- [ ] Presentation owns transport rather than business sequencing.
- [ ] Manager owns meaningful workflow sequencing where required.
- [ ] Engine remains infrastructure-free.
- [ ] ResourceAccess contains resource mechanics rather than business workflow.
- [ ] No new ResourceAccess-to-ResourceAccess workflow chain was introduced.
- [ ] Simple CRUD was not wrapped in a Manager without evidence.

## Coupling/contract quality

- [ ] No FastAPI HTTP concepts were introduced into Manager/Engine logic.
- [ ] No ORM/Session/SDK/filesystem dependency entered an Engine.
- [ ] No field-for-field DTO layer was added without independent semantics.
- [ ] No generic repository/UoW/provider interface was added without demonstrated substitution volatility.

## Behavioral safety

- [ ] Accounting invariants preserved.
- [ ] Known defects were not silently fixed.
- [ ] Product/domain decisions were not changed accidentally.
- [ ] Transaction semantics were not changed unless in scope.
- [ ] API behavior was preserved unless explicitly authorized.

## Verification

- [ ] Characterization/relevant tests pass.
- [ ] Full suite passes.
- [ ] `git diff --stat` reviewed.
- [ ] Full diff reviewed.
- [ ] architecture docs reflect the resulting source reality.
