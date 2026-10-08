# VBD Component Map

This map records the currently justified architectural components. It is descriptive of intended boundaries, not a requirement that every file fit a named component.

## Presentation

FastAPI routers own HTTP parsing, validation, error/status mapping, multipart extraction, and serialization.

Direct Router -> ResourceAccess is allowed for genuinely simple CRUD. Routers must not own multi-step application workflow, database transaction orchestration for such workflows, or external SDK workflow sequencing.

## Managers

| Manager | Responsibility | Boundary assessment |
|---|---|---|
| AccountReconciliationManager | reconciliation workspace/completion sequence | justified meaningful workflow; transport coupling removed in Slice 5, raises application exceptions |
| AccountSummaryManager | account listing plus derived depository balance | currently justified; review transport-schema coupling |
| BudgetSummaryManager | category/budget/actual retrieval + budget Engine | strong reference Manager |
| CategorizationRuleManager | retroactive rule preview/apply | lightweight but has batch workflow/transaction semantics |
| CreditCardSummaryManager | credit-account retrieval + financial calculation | justified; review DTO ceremony |
| CSVImportManager | upload inspection & format detection, loader resolution, preview parsing, and dedupe/normalize/categorize/stage/commit import | strongly justified; Slices 4 and 4b implementation |
| DashboardSummaryManager | composite dashboard read workflow | justified only while composition changes independently; review screen-driven boundary and Manager-to-Manager edge |
| ManualTransactionManager | manual transaction create and update workflows (merchant override resolution, split & reconciled invariant guards, rule fallback vs manual ML revision staging, atomic persistence) | narrowly scoped workflow Manager; Slice 2d and 2e implementation |
| MLCategorizationManager | training/evaluation/artifact/metadata/inference workflows | strongly justified |
| PlaidAccountSyncManager | public-token exchange, item creation/resolution, token decode, remote account fetch, upsert, commit | strongly justified |
| PlaidTransactionSyncManager | item resolution, account refresh, paged sync, event persistence, cursor | strongly justified; transaction semantics reviewed separately |
| RecurringTransactionManager | detection/sync plus status/list operations | detection workflow justified; trivial operations need no additional abstraction |
| TransactionSplitManager | split/unsplit invariants and coordinated persistence | strongly justified |
| TransferReconciliationManager | candidate retrieval, matching Engine, enrichment | justified read workflow |

## Engines / domain policies

Strongly justified algorithm/policy boundaries:

- `budgeting.py`
- `account_reconciliation.py`
- `credit_cards.py`
- `merchant_normalization.py`
- `ml_categorization.py`
- `reconciliation.py`
- `recurring_transactions.py`
- `transaction_splits.py`

Small pure utilities are not automatically Engines:

- `accounts.py`
- `dates.py`
- parts of `categorization_rules.py`

Keep them pure; do not add interfaces merely to elevate their architectural status.

## ResourceAccess

Concrete access-mechanism boundaries with demonstrated independent volatility:

- Plaid SDK access
- raw Plaid transaction-sync HTTP access
- local ML model artifact access together with its concrete metadata lifecycle where cohesion remains justified

Database Accessors may remain concrete, but their boundaries must not be justified solely by one-table-per-module symmetry. Cross-Accessor workflow calls are migration targets.

## Transitional/legacy

`backend/crud/plaid.py` (and the legacy `backend/crud/` package) has been retired as part of Slice 1 (Plaid public-token exchange boundary migration). All Plaid persistence operations now route through `backend/access/plaid_item_access.py` and `backend/access/account_access.py`.
