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

## Credit-card accounting contract (resolved)

- `balance_owed`: Point-in-time liability (`starting_balance + sum(tx.amount for tx in transactions if tx.date < cutoff_exclusive)`). Includes purchases, merchant refunds, and transfers (card payment transfers reduce balance; positive transfers increase balance). Strictly excludes future-dated activity beyond effective cutoff.
- `charges_this_month`: Gross positive non-transfer charges (`period_start <= tx.date < cutoff_exclusive`, `amount > 0`, `is_transfer == False`). Merchant refunds do not reduce this metric. Card payments and transfers out are excluded.
- `payments_this_month`: Negative transfer payments only (`period_start <= tx.date < cutoff_exclusive`, `amount < 0`, `is_transfer == True`). Merchant refunds, statement credits, and other negative non-transfer transactions are excluded.


## Reconciliation behavior

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

## Plaid token security invariants

- Plaid access tokens are stored using authenticated encryption.
- Stored current format is `enc:v1:<Fernet ciphertext>`.
- Legacy Base64 storage is prohibited after migration.
- `PLAID_TOKEN_ENCRYPTION_KEY` is required whenever stored Plaid items exist.

## Transaction description invariant

- `Transaction.description` is always a non-null string (`TEXT NOT NULL`).
- Empty string `""` is the canonical representation when no description text exists.
- SQL `NULL` is prohibited at the database, ORM, and schema layers.

## Transfer matching invariant

Transfer candidate matching is deterministic closest-first greedy suggestion matching (`detect_transfer_candidates`).

Eligibility:
- exact opposite absolute amount;
- different accounts;
- within ±2 calendar days;
- neither already marked transfer;
- split transactions excluded upstream.

Selection:
- closest date first (0-day > 1-day > 2-day);
- deterministic date and transaction UUID tie-breaking;
- each transaction appears in at most one suggestion;
- input/database ordering cannot affect results.

Persistence:
- suggestion-only until explicit user confirmation via `POST /credit-cards/mark-transfers` or `POST /transactions/mark-transfers`.

## Known defects that must not be silently fixed

- None currently active. All previously identified defects and domain ambiguities have been resolved.

## Transaction behavior

Do not change commit granularity merely because code is being moved unless the current refactor explicitly targets transaction semantics. In particular, Plaid transaction sync's current per-event/final commit structure is a known behavior requiring a separate correctness decision.

