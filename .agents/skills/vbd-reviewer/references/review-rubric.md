# Review Rubric

## BLOCKING

The slice is not safe/complete to merge: behavior regression, wrong architectural direction, speculative abstraction central to the change, test failure, unreviewed schema/security/product change, or source/docs contradiction that would mislead the next refactor.

## MAJOR

The main slice mostly works but leaves or introduces meaningful VBD coupling: workflow still in wrong layer, Accessor chaining, policy duplication, infrastructure contamination, incorrect transaction owner, or unnecessary new component.

## MINOR

Naming, documentation precision, small unnecessary mapping, or limited cleanup that does not invalidate the boundary.

## OK

No material VBD or behavior-preservation issue found.

Review evidence, not aesthetics. A smaller concrete design is preferred over symmetrical layering.
