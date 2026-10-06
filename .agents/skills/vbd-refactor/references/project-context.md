# Budget App Refactor Context

Priority order unless the user selects another evidenced slice:

1. Plaid public-token exchange Router/legacy path.
2. ResourceAccess-to-ResourceAccess coupling centered on transaction access.
3. Categorization policy authority outside ResourceAccess.
4. CSV/upload application sequencing.
5. Presentation coupling in Managers.
6. Manager topology review.
7. Redundant DTO cleanup.

One slice means one architectural concern. A slice may touch several files if needed to move one responsibility safely.

Preserve accounting sign conventions, ZBB equations, CSV semantics, split invariants, current API behavior, known defects, and transaction semantics unless the task explicitly changes one of them.

Do not create generic Repository/UoW, alternate DB ports, hypothetical bank-provider abstractions, generic rule engines, one Manager per endpoint, one Engine per helper, or field-for-field DTO layers.
