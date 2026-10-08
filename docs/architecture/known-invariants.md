# Known Invariants and Preserved Behavior

Structural refactors must preserve these behaviors unless the task explicitly authorizes a product/domain change.

## Accounting conventions

- Outflow/debit/charge amounts are positive.
- Inflow/income/credit amounts are negative.
- Income is inverted for budget display/reporting.
- `to_be_assigned = planned income - planned expenses`.
- Refunds may make expense actual negative and remaining exceed planned.
- Split allocations must sum exactly to the parent transaction amount.
- Split lines must obey current sign and non-zero rules.

## Current credit-card behavior

Preserve until a product decision changes it:

- `balance_owed` includes current established transfer behavior.
- `charges_this_month` excludes transfers.
- `payments_this_month` currently includes negative transfers.
- `balance_owed` currently includes future-dated transactions.

## Transfer/reconciliation behavior

- Transfer matching is currently greedy/order-dependent.
- The current matcher does not necessarily prefer the closest date.
- Account reconciliation preserves its current balanced-state and cleared-transaction semantics.

## CSV/import behavior

- Existing parser sign/date normalization must remain unchanged during architecture-only work.
- CSV duplicate detection currently uses exact `(account_id, date, amount, description)` equality.
- Preview and confirm behavior may be relocated but must remain behaviorally equivalent unless separately approved.

## Category and group behavior

- Category groups cannot be deleted while they contain categories (must be empty; returns HTTP 400 with detail "Cannot delete category group containing categories. Move or delete categories first.").
- Category deletion semantics (`DELETE /categories/{category_id}`):
  - Split references block deletion (`HTTP 400`, detail: `"Cannot delete category referenced by split allocations. Reassign or remove splits first."`, zero database mutation).
  - Transactions survive as uncategorized (`category_id` set to `NULL`, `category_source` preserved).
  - Monthly budgets are cascade-deleted (`Category.budgets` specifies `cascade="all, delete", passive_deletes=True`, `Budget.category_id` is `NOT NULL` with FK `ON DELETE CASCADE`).
  - Categorization rules are cascade-deleted (`cascade="all, delete-orphan"`, FK `ON DELETE CASCADE`).

## Known defects that must not be silently fixed

- Transaction `description` DB nullability conflicts with the API schema's non-null string expectation.
- Plaid token storage uses the current insecure placeholder/base64-style mechanism. Real encryption is a separate migration.

## Transaction behavior

Do not change commit granularity merely because code is being moved unless the current refactor explicitly targets transaction semantics. In particular, Plaid transaction sync's current per-event/final commit structure is a known behavior requiring a separate correctness decision.
