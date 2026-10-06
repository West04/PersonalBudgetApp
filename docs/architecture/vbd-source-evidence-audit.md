# Volatility-Based Decomposition (VBD) Source-Code Evidence Audit

```text
Repository HEAD: 8f1381b5253de3431e17d752c11d8670966013bf
Audit date: 2026-10-06
Production files modified: NONE
Tests modified: NONE
```

---

## Executive Summary & Scope

This report provides an exhaustive, source-code-authoritative architectural audit of the `budget_app` repository evaluated against the Volatility-Based Decomposition (VBD) model from *Righting Software* (Juval Löwy).

The audit is strictly **fact-based and analytical**:
- No production code has been modified.
- No test files have been modified.
- No refactoring or abstraction has been introduced.
- Stated intent in existing architecture documentation has been compared against running code, but the Python implementation at HEAD (`8f1381b5253de3431e17d752c11d8670966013bf`) is treated as the sole authoritative source of truth.
- All dependencies, call sites, transaction boundaries, and data representations are cited with exact file paths, line numbers, and symbol names.

---

## 1. Actual Dependency Graph

An exhaustive AST and call-site trace of production Python code across `backend/routers/`, `backend/managers/`, `backend/domain/`, `backend/access/`, `backend/crud/`, and foundational modules establishes the following actual dependency graph.

### 1.1 Dependency Group Breakdown

| Caller | Callee | Mechanism | Why Caller Uses It | Source Evidence |
|---|---|---|---|---|
| **Router -> Manager** | `accounts.py` -> `account_summary_manager.py` | Synchronous function call | Delegate accounts listing with ledger balance derivation | `backend/routers/accounts.py:25` calls `account_summary_manager.get_accounts_summary(db)` |
| **Router -> Manager** | `accounts.py` -> `account_reconciliation_manager.py` | Synchronous function call | Delegate reconciliation workspace summary and completion | `backend/routers/accounts.py:75,93` calls `get_reconciliation_summary`, `complete_reconciliation` |
| **Router -> Manager** | `credit_cards.py` -> `credit_card_summary_manager.py` | Synchronous function call | Delegate monthly credit card spending & balance owed computation | `backend/routers/credit_cards.py:33` calls `get_credit_card_summary(db, budget_month)` |
| **Router -> Manager** | `credit_cards.py` -> `transfer_reconciliation_manager.py` | Synchronous function call | Delegate transfer candidate pairing search | `backend/routers/credit_cards.py:73` calls `get_transfer_candidates(db)` |
| **Router -> Manager** | `ml.py` -> `ml_categorization_manager.py` | Synchronous function call | Delegate model status query and manual retraining workflow | `backend/routers/ml.py:26,39` calls `get_ml_status`, `retrain_model` |
| **Router -> Manager** | `plaid.py` -> `plaid_account_sync_manager.py` | Synchronous function call | Delegate Plaid account balance refresh orchestration | `backend/routers/plaid.py:72` calls `sync_plaid_accounts(db, ...)` |
| **Router -> Manager** | `plaid.py` -> `plaid_transaction_sync_manager.py` | Synchronous function call | Delegate cursor-based transaction sync orchestration | `backend/routers/plaid.py:99` calls `sync_plaid_transactions(db, ...)` |
| **Router -> Manager** | `recurring.py` -> `recurring_transaction_manager.py` | Synchronous function call | Delegate detection, listing, confirmation, dismissal | `backend/routers/recurring.py:32,49,64,84,104` calls all 5 manager entrypoints |
| **Router -> Manager** | `rules.py` -> `categorization_rule_manager.py` | Synchronous function call | Delegate rule impact preview and retroactive batch execution | `backend/routers/rules.py:126,151` calls `preview_rule_matches`, `apply_rule_to_uncategorized` |
| **Router -> Manager** | `summaries.py` -> `budget_summary_manager.py` | Synchronous function call | Delegate monthly zero-based budget summary calculation | `backend/routers/summaries.py:25` calls `get_budget_summary(db, budget_month)` |
| **Router -> Manager** | `summaries.py` -> `dashboard_summary_manager.py` | Synchronous function call | Delegate composite dashboard summary aggregation | `backend/routers/summaries.py:72` calls `get_dashboard_summary(db, budget_month)` |
| **Router -> Manager** | `transactions.py` -> `transfer_reconciliation_manager.py` | Synchronous function call | Delegate transfer candidate pairing search | `backend/routers/transactions.py:76` calls `get_transfer_candidates(db)` |
| **Router -> Manager** | `transactions.py` -> `ml_categorization_manager.py` | Synchronous function call | Delegate batch and single transaction suggestion inference and acceptance | `backend/routers/transactions.py:280,296,322` calls `batch_predict_suggestions`, `predict_category_for_transaction`, `accept_suggestion` |
| **Router -> Manager** | `transactions.py` -> `transaction_split_manager.py` | Synchronous function call | Delegate split retrieval, replacement, and unsplit workflows | `backend/routers/transactions.py:350,368,397` calls `get_transaction_splits`, `create_or_replace_split`, `unsplit_transaction` |
| **Router -> Manager** | `upload.py` -> `csv_import_manager.py` | Synchronous function call | Delegate batch CSV statement import, deduplication, and commit | `backend/routers/upload.py:317` calls `confirm_csv_import(db, raw, loader)` |
| **Router -> Accessor** | `accounts.py` -> `account_access.py` | Synchronous function call | Direct CRUD for manual accounts (create, update, delete) | `backend/routers/accounts.py:31,45,57` calls `create_manual_account`, `update_manual_account`, `delete_account` |
| **Router -> Accessor** | `budgets.py` -> `budget_access.py` | Synchronous function call | Direct CRUD for monthly category budget assignments | `backend/routers/budgets.py:27,47,63,73,83` calls all budget access CRUD functions |
| **Router -> Accessor** | `categories.py` -> `category_access.py` | Synchronous function call | Direct CRUD & reordering for category groups and categories | `backend/routers/categories.py:26,46,62,72,83,101,133,153,169,179,190,208` |
| **Router -> Accessor** | `credit_cards.py` -> `transaction_access.py` | Synchronous function call | Approve transfer pair by setting `is_transfer = True` | `backend/routers/credit_cards.py:128` calls `mark_transactions_as_transfers` |
| **Router -> Accessor** | `plaid.py` -> `plaid_access.py` | Synchronous function call | Create Plaid Link token for frontend Link flow | `backend/routers/plaid.py:34` calls `create_link_token()` |
| **Router -> Accessor** | `rules.py` -> `categorization_rule_access.py` | Synchronous function call | Direct CRUD for deterministic categorization rules | `backend/routers/rules.py:33,52,70,84,95` calls `get_rules`, `create_rule`, `get_rule_by_id`, `update_rule`, `delete_rule` |
| **Router -> Accessor** | `transactions.py` -> `transaction_access.py` | Synchronous function call | Direct transaction ledger queries, manual CRUD, cleared toggle, transfer marking | `backend/routers/transactions.py:51,132,148,166,193,223,252` |
| **Router -> Accessor** | `upload.py` -> `account_access.py` | Synchronous function call | Target account existence validation in preview and confirm routes | `backend/routers/upload.py:233,305` calls `get_account_by_id(db, account_id)` |
| **Router -> Accessor** | `upload.py` -> `csv_format_access.py` | Synchronous function call | Custom format CRUD, format lookup during loader resolution, format inspection | `backend/routers/upload.py:68,75,92,109,185,187` |
| **Router -> Domain / Engine / Utility** | `upload.py` -> `bank_statement_loader.py` | Synchronous function call & class instantiation | CSV format sniffing (`detect_csv_format`), built-in loader retrieval (`get_loader`), `MappedStatementLoader` instantiation | `backend/routers/upload.py:57,76,190,192` |
| **Router -> crud (Legacy)** | `plaid.py` -> `crud/plaid.py` | Synchronous function call | Direct invocation of legacy Plaid Item creation, account syncing, and account listing in token exchange | `backend/routers/plaid.py:47,49,52,60` |
| **Router -> External SDK / Resource** | `plaid.py` -> Plaid Python SDK | Direct SDK client & model construction | Constructs `ApiClient`, `PlaidApi`, `ItemPublicTokenExchangeRequest` | `backend/routers/plaid.py:27,42` |
| **Router -> Database Directly** | `plaid.py` -> SQLAlchemy Session | Direct session method call | Invokes `db.commit()` directly after legacy `crud_plaid.sync_accounts_and_balances` | `backend/routers/plaid.py:59` calls `db.commit()` |
| **Manager -> Manager** | `dashboard_summary_manager.py` -> `budget_summary_manager.py` | Synchronous function call | Reuses full Budget Summary workflow calculation | `backend/managers/dashboard_summary_manager.py:25,98` calls `get_budget_summary(db, budget_month)` |
| **Manager -> Engine / Domain** | `account_reconciliation_manager.py` -> `domain/account_reconciliation.py` | Synchronous function call | Compute cleared balance, statement difference, balanced state | `backend/managers/account_reconciliation_manager.py:26,88` |
| **Manager -> Engine / Domain** | `account_summary_manager.py` -> `domain/accounts.py` | Synchronous function call | Pure depository balance subtraction ($starting - net$) | `backend/managers/account_summary_manager.py:21,51` calls `calculate_depository_balance` |
| **Manager -> Engine / Domain** | `budget_summary_manager.py` -> `domain/budgeting.py` | Synchronous function call | Pure zero-based budgeting calculation engine | `backend/managers/budget_summary_manager.py:22,69` calls `calculate_budget_summary` |
| **Manager -> Engine / Domain** | `budget_summary_manager.py` -> `domain/dates.py` | Synchronous function call | Calendar month boundary interval calculation | `backend/managers/budget_summary_manager.py:24,40` calls `determine_month_range` |
| **Manager -> Engine / Domain** | `categorization_rule_manager.py` -> `domain/categorization_rules.py` | Synchronous function call | Canonical merchant string normalization for rule lookup | `backend/managers/categorization_rule_manager.py:17,34,58` calls `clean_merchant_key` |
| **Manager -> Engine / Domain** | `credit_card_summary_manager.py` -> `domain/credit_cards.py` | Synchronous function call | Pure credit card debt, charges, and payments calculation | `backend/managers/credit_card_summary_manager.py:29,91` calls `calculate_credit_card_state` |
| **Manager -> Engine / Domain** | `credit_card_summary_manager.py` -> `domain/dates.py` | Synchronous function call | Calendar month boundary interval calculation | `backend/managers/credit_card_summary_manager.py:31,73` calls `determine_month_range` |
| **Manager -> Engine / Domain** | `csv_import_manager.py` -> `domain/merchant_normalization.py` | Synchronous function call | Clean POS prefixes and store IDs before staging | `backend/managers/csv_import_manager.py:19,93` calls `normalize_merchant` |
| **Manager -> Engine / Domain** | `dashboard_summary_manager.py` -> `domain/dates.py` | Synchronous function call | Calendar month boundary interval calculation | `backend/managers/dashboard_summary_manager.py:24,95` calls `determine_month_range` |
| **Manager -> Engine / Domain** | `ml_categorization_manager.py` -> `domain/categorization_rules.py` | Synchronous function call | Clean merchant key for baseline lookup | `backend/managers/ml_categorization_manager.py:35` calls `clean_merchant_key` |
| **Manager -> Engine / Domain** | `ml_categorization_manager.py` -> `domain/ml_categorization.py` | Synchronous function call | Feature building, pipeline creation, classifier evaluation, activation gating, prediction | `backend/managers/ml_categorization_manager.py:44-48,123,173,191,209,307,419` |
| **Manager -> Engine / Domain** | `plaid_transaction_sync_manager.py` -> `domain/merchant_normalization.py` | Synchronous function call | Clean POS prefixes and combine with provider counterparties | `backend/managers/plaid_transaction_sync_manager.py:24,105` calls `normalize_merchant` |
| **Manager -> Engine / Domain** | `recurring_transaction_manager.py` -> `domain/categorization_rules.py` | Synchronous function call | Canonical merchant key for series identity clustering | `backend/managers/recurring_transaction_manager.py:19,96,124,181` calls `clean_merchant_key` |
| **Manager -> Engine / Domain** | `recurring_transaction_manager.py` -> `domain/recurring_transactions.py` | Synchronous function call | Cadence clustering, interval validation, stability check | `backend/managers/recurring_transaction_manager.py:23,90` calls `detect_recurring_series` |
| **Manager -> Engine / Domain** | `transaction_split_manager.py` -> `domain/transaction_splits.py` | Synchronous function call | Exact allocation sum invariant, minimum 2 allocations, non-zero sign check | `backend/managers/transaction_split_manager.py:26,97` calls `validate_split_allocations` |
| **Manager -> Engine / Domain** | `transfer_reconciliation_manager.py` -> `domain/reconciliation.py` | Synchronous function call | Inter-account transfer pairing heuristic ($\le 2$ days, opposite sign) | `backend/managers/transfer_reconciliation_manager.py:29,126` calls `detect_transfer_candidates` |
| **Manager -> Accessor** | 13 Managers -> 12 Accessors | Synchronous function call | Managers coordinate concrete persistence and external API calls through Accessors (detailed in Section 2) | Documented per-manager in Section 2 |
| **Manager -> Ingestion Loader Boundary** | `csv_import_manager.py` -> `bank_statement_loader.py` | Synchronous method call | Invokes `loader.load_records_tolerant(raw_bytes)` | `backend/managers/csv_import_manager.py:47,69` |
| **Manager -> Security Helper** | `plaid_account_sync_manager.py`, `plaid_transaction_sync_manager.py` -> `security.py` | Synchronous function call | Decrypt base64-encoded Plaid access token | `plaid_account_sync_manager.py:15,78`, `plaid_transaction_sync_manager.py:25,172` calls `decrypt_token` |
| **Manager -> crud (Legacy)** | NONE | None | No Manager imports or calls any function from `backend/crud/` | Verified: 0 calls across all 13 managers |
| **Manager -> External SDK Directly** | NONE | None | External network interaction is isolated in `plaid_access.py` and `plaid_transaction_access.py` | Verified: 0 SDK imports in managers |
| **Engine / Domain -> Manager** | NONE | None | Engines have zero knowledge of Managers | Verified: 0 imports |
| **Engine / Domain -> Accessor** | NONE | None | Engines have zero knowledge of Accessors | Verified: 0 imports |
| **Engine / Domain -> ORM / Models** | NONE | None | Engines have zero knowledge of SQLAlchemy models | Verified: 0 imports |
| **Engine / Domain -> FastAPI / Pydantic** | NONE | None | Engines have zero knowledge of FastAPI or Pydantic | Verified: 0 imports |
| **Engine / Domain -> External SDK / Env** | NONE | None | No environment variables, network calls, or filesystem access | Verified: pure python only (except `numpy`/`sklearn` in `ml_categorization.py`) |
| **Accessor -> Manager** | NONE | None | No Accessor imports or calls any Manager | Verified: 0 imports |
| **Accessor -> Engine / Domain** | `transaction_access.py` -> `domain/merchant_normalization.py`, `domain/categorization_rules.py` | Synchronous function call | Normalizes merchant and cleans merchant key during row creation/staging | `backend/access/transaction_access.py:10,11,185,235,316,383,526,629` |
| **Accessor -> Accessor** | `category_access.py` -> `split_access.py` | Synchronous function call | Validates category has no splits before deletion (`count_splits_by_category`) | `backend/access/category_access.py:186-187` |
| **Accessor -> Accessor** | `transaction_access.py` -> `split_access.py` | Synchronous function call | Checks if transaction has splits (`transaction_has_splits`), deletes splits on update (`stage_delete_splits`) | `backend/access/transaction_access.py:359-365,593-594,699` |
| **Accessor -> Accessor** | `transaction_access.py` -> `categorization_rule_access.py` | Synchronous function call | Fallback rule lookup when `rules_lookup` mapping is not passed (`get_rule_by_merchant`) | `backend/access/transaction_access.py:240-241,320-321,387-388,542-543,649-650` |
| **Accessor -> Accessor** | `transaction_access.py` -> `ml_model_access.py` | Synchronous function call | Bumps ML training revision on manual category assignment (`increment_training_revision`) | `backend/access/transaction_access.py:539-540,637-638` |
| **Accessor -> ORM / Models** | 10 Database Accessors -> `models.py` | Declarative queries and model instantiation | Encapsulates all SQLAlchemy queries and table mutations | Verified across all DB accessors |
| **crud -> Callers** | `crud/plaid.py` -> `backend/routers/plaid.py` | Synchronous function call | Router endpoint `exchange_public_token` calls 4 legacy CRUD functions | `backend/routers/plaid.py:47,49,52,60` |

---

## 2. Manager Audit

This section audits each of the 13 modules in `backend/managers/`.

### 2.1 AccountReconciliationManager (`backend/managers/account_reconciliation_manager.py`)

#### Identity
- **Module Name:** `account_reconciliation_manager.py`
- **Public Entry Functions:**
  - `get_reconciliation_summary(db: Session, account_id: UUID, statement_ending_date: date, statement_ending_balance: Decimal) -> schemas.AccountReconciliationSummary`
  - `complete_reconciliation(db: Session, account_id: UUID, statement_ending_date: date, statement_ending_balance: Decimal) -> schemas.AccountReconciliationSummary`
- **Production Callers:**
  - `backend/routers/accounts.py:75` (calls `get_reconciliation_summary` via `GET /accounts/{account_id}/reconciliation`)
  - `backend/routers/accounts.py:93` (calls `complete_reconciliation` via `POST /accounts/{account_id}/reconciliation/complete`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.account_reconciliation.compute_reconciliation_state` (calls `calculate_cleared_balance`, `calculate_reconciliation_difference`, `is_reconciliation_balanced`)
- **Accessors Called:**
  - `access.account_access.get_account_by_id`
  - `access.account_access.update_account_reconciliation_metadata`
  - `access.transaction_access.get_unreconciled_transactions_for_account`
  - `access.transaction_access.mark_transactions_as_reconciled`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `accounts` and `transactions` via Accessors.
- **Direct Infrastructure/Transport Coupling:**
  - Directly imports `fastapi.HTTPException` and `fastapi.status` (`account_reconciliation_manager.py:19`).
  - Raises `HTTPException(404, "Account not found")` at line 48.
  - Raises `HTTPException(400, "Account reconciliation is currently supported for depository accounts only...")` at line 54.
  - Raises `HTTPException(400, "Cannot complete reconciliation: statement ending balance does not match cleared balance...")` at line 153.
  - Directly imports and returns Pydantic presentation schema `schemas.AccountReconciliationSummary` (`account_reconciliation_manager.py:22,37,111,135`).

#### Workflow
1. **`get_reconciliation_summary`:**
   ```text
   validate account existence (account_access.get_account_by_id)
   -> validate depository type (raise HTTPException 400 if non-depository)
   -> resolve baseline balance (last_reconciled_balance or starting_balance)
   -> load unreconciled transactions (transaction_access.get_unreconciled_transactions_for_account)
   -> map to domain input models (ReconciliationTx)
   -> invoke pure engine (domain.account_reconciliation.compute_reconciliation_state)
   -> assemble schemas.ReconciliationTransactionRead items
   -> return schemas.AccountReconciliationSummary
   ```
2. **`complete_reconciliation`:**
   ```text
   invoke get_reconciliation_summary
   -> validate is_balanced (raise HTTPException 400 if difference != 0.00)
   -> filter cleared transaction IDs
   -> stage transaction reconciliation (transaction_access.mark_transactions_as_reconciled -> db.flush())
   -> stage account reconciliation watermark (account_access.update_account_reconciliation_metadata -> db.flush())
   -> commit transaction (db.commit()) or rollback on exception (db.rollback())
   -> re-invoke get_reconciliation_summary to return refreshed summary state
   ```

#### Transaction Ownership
- `account_reconciliation_manager.py` explicitly owns the commit boundary for completion:
  - Calls `db.commit()` at line 183.
  - Calls `db.rollback()` at line 185.
- Called Accessors:
  - `transaction_access.mark_transactions_as_reconciled` executes `db.flush()` at line 817.
  - `account_access.update_account_reconciliation_metadata` executes `db.flush()` at line 237.
  - Neither Accessor calls `db.commit()`.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: combines account validation, transaction filtering, financial reconciliation computation, transaction state transition, account watermark update, and atomic batch commit.
- **Coordinates more than one Accessor?** Yes: `account_access` and `transaction_access`.
- **Invokes an Engine?** Yes: `compute_reconciliation_state` in `domain/account_reconciliation.py`.
- **Merely performs one query/mutation plus mapping?** No.
- **Could current public operation be described as simple CRUD?** No.
- **Exists primarily to produce a particular screen/API response?** Yes: directly powers the Reconciliation modal/screen (`GET /accounts/{id}/reconciliation`).
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.2 AccountSummaryManager (`backend/managers/account_summary_manager.py`)

#### Identity
- **Module Name:** `account_summary_manager.py`
- **Public Entry Functions:**
  - `get_accounts_summary(db: Session) -> Sequence[schemas.AccountRead]`
- **Production Callers:**
  - `backend/routers/accounts.py:25` (via `GET /accounts/`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.accounts.calculate_depository_balance`
- **Accessors Called:**
  - `access.account_access.get_all_accounts_ordered`
  - `access.transaction_access.get_transaction_net_by_account`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `accounts` and `transactions` via Accessors.
- **Direct Infrastructure/Transport Coupling:** Returns `Sequence[schemas.AccountRead]` (Pydantic schema).

#### Workflow
```text
load all accounts ordered by type ascending, name ascending (account_access.get_all_accounts_ordered)
-> identify manual depository accounts (plaid_account_id is None and type == 'depository')
-> aggregate historical transaction net amounts (transaction_access.get_transaction_net_by_account)
-> for each account:
    validate into schemas.AccountRead
    if manual depository:
        derive authoritative balance via domain.accounts.calculate_depository_balance(starting_balance, net_tx)
        copy schema with updated current_balance
-> return list[schemas.AccountRead]
```

#### Transaction Ownership
- Zero database transaction operations: 0 `add`, 0 `flush`, 0 `commit`, 0 `rollback`, 0 `refresh`.
- Read-only query aggregation workflow.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: fetches accounts, identifies depository manual subset, aggregates transaction net totals, and applies ledger balance formula.
- **Coordinates more than one Accessor?** Yes: `account_access` and `transaction_access`.
- **Invokes an Engine?** Invokes `domain.accounts.calculate_depository_balance` (a 1-line formula: $starting - net$).
- **Merely performs one query/mutation plus mapping?** No: performs two coordinated queries across two tables and joins their results in Python.
- **Could current public operation be described as simple CRUD?** No (because of ledger-derived balance calculation).
- **Exists primarily to produce a particular screen/API response?** Yes: powers the Accounts screen list view (`GET /accounts/`).
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No (specifically, `DashboardSummaryManager` does NOT call it).

---

### 2.3 BudgetSummaryManager (`backend/managers/budget_summary_manager.py`)

#### Identity
- **Module Name:** `budget_summary_manager.py`
- **Public Entry Functions:**
  - `get_budget_summary(db: Session, budget_month: date) -> BudgetSummaryResult`
- **Production Callers:**
  - `backend/routers/summaries.py:25` (via `GET /summary/budget`)
  - `backend/managers/dashboard_summary_manager.py:98` (via `get_dashboard_summary`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.dates.determine_month_range`
  - `domain.budgeting.calculate_budget_summary`
- **Accessors Called:**
  - `access.category_access.get_category_groups`
  - `access.budget_access.get_budgets_for_month`
  - `access.transaction_access.get_actuals_by_category`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `category_groups`, `categories`, `budgets`, `transactions`, `transaction_splits` (via `get_actuals_by_category`).

#### Workflow
```text
determine half-open calendar month interval [start_date, end_date) via domain.dates.determine_month_range
-> retrieve category groups with nested categories (category_access.get_category_groups)
-> retrieve budget allocations for month (budget_access.get_budgets_for_month)
-> retrieve transaction actuals aggregated by category including splits (transaction_access.get_actuals_by_category)
-> assemble domain inputs (GroupBudgetInput, CategoryBudgetInput)
-> invoke pure Zero-Based Budgeting Engine (domain.budgeting.calculate_budget_summary)
-> return domain BudgetSummaryResult
```

#### Transaction Ownership
- Zero database transaction operations: 0 `add`, 0 `flush`, 0 `commit`, 0 `rollback`, 0 `refresh`.
- Read-only composite query orchestration.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: determines date range, queries three separate persistence stores, maps records into hierarchical domain inputs, and executes zero-based budget calculations.
- **Coordinates more than one Accessor?** Yes: 3 Accessors (`category_access`, `budget_access`, `transaction_access`).
- **Invokes an Engine?** Yes: authoritative `calculate_budget_summary` in `domain/budgeting.py`.
- **Merely performs one query/mutation plus mapping?** No.
- **Could current public operation be described as simple CRUD?** No.
- **Exists primarily to produce a particular screen/API response?** Yes: powers the Budget screen (`GET /summary/budget`) and supplies budget metrics to the Dashboard.
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** Yes: called by `DashboardSummaryManager.get_dashboard_summary`.

---

### 2.4 CategorizationRuleManager (`backend/managers/categorization_rule_manager.py`)

#### Identity
- **Module Name:** `categorization_rule_manager.py`
- **Public Entry Functions:**
  - `preview_rule_matches(db: Session, rule_id: UUID) -> int`
  - `apply_rule_to_uncategorized(db: Session, rule_id: UUID) -> int`
- **Production Callers:**
  - `backend/routers/rules.py:126` (via `GET /rules/{rule_id}/preview`)
  - `backend/routers/rules.py:151` (via `POST /rules/{rule_id}/apply`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.categorization_rules.clean_merchant_key`
- **Accessors Called:**
  - `access.categorization_rule_access.get_rule_by_id`
  - `access.transaction_access.count_uncategorized_transactions_by_merchant_key`
  - `access.transaction_access.apply_category_to_uncategorized_by_merchant_key`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `categorization_rules` and `transactions`.

#### Workflow
1. **`preview_rule_matches`:**
   ```text
   load rule by ID (categorization_rule_access.get_rule_by_id)
   -> raise CategorizationRuleNotFoundError if missing
   -> clean rule merchant string (domain.categorization_rules.clean_merchant_key)
   -> count matching uncategorized transactions (transaction_access.count_uncategorized_transactions_by_merchant_key)
   -> return integer count
   ```
2. **`apply_rule_to_uncategorized`:**
   ```text
   load rule by ID (categorization_rule_access.get_rule_by_id)
   -> raise CategorizationRuleNotFoundError if missing
   -> clean rule merchant string (domain.categorization_rules.clean_merchant_key)
   -> update matching uncategorized rows (transaction_access.apply_category_to_uncategorized_by_merchant_key -> db.flush())
   -> commit batch transaction (db.commit()) or rollback on exception (db.rollback())
   -> return count of updated rows
   ```

#### Transaction Ownership
- `apply_rule_to_uncategorized` owns the commit boundary:
  - Calls `db.commit()` at line 68.
  - Calls `db.rollback()` at line 71.
- Called Accessor: `transaction_access.apply_category_to_uncategorized_by_merchant_key` executes `db.flush()` at line 873 without committing.
- `preview_rule_matches` has zero transaction operations (read-only).

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Narrow scope: verifies rule, cleans key, and executes batch update + commit.
- **Coordinates more than one Accessor?** Yes: `categorization_rule_access` and `transaction_access`.
- **Invokes an Engine?** Invokes only `domain.categorization_rules.clean_merchant_key` (string cleaning helper). Does NOT invoke `match_merchant_rule` or any complex calculation engine.
- **Merely performs one query/mutation plus mapping?** Nearly: loads 1 rule, then runs 1 query/update on transactions, then commits.
- **Could current public operation be described as simple CRUD?** No, it is a batch retroactive update, but it is very lightweight orchestration.
- **Exists primarily to produce a particular screen/API response?** Yes: powers the rule preview button and retroactive apply button on the Rules page.
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.5 CreditCardSummaryManager (`backend/managers/credit_card_summary_manager.py`)

#### Identity
- **Module Name:** `credit_card_summary_manager.py`
- **Public Entry Functions:**
  - `get_credit_card_summary(db: Session, budget_month: date) -> CreditCardSummaryResult`
- **Production Callers:**
  - `backend/routers/credit_cards.py:33` (via `GET /credit-cards/summary`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.dates.determine_month_range`
  - `domain.credit_cards.calculate_credit_card_state`
- **Accessors Called:**
  - `access.account_access.get_active_credit_accounts`
  - `access.transaction_access.get_transactions_for_account`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `accounts` and `transactions`.
- **Manager-Defined DTOs:**
  - `CreditCardMonthlyTransactionItem`
  - `CreditCardAccountSummaryItem`
  - `CreditCardSummaryResult`

#### Workflow
```text
determine half-open month interval [start_date, end_date) via domain.dates.determine_month_range
-> retrieve active credit accounts ordered by name ascending (account_access.get_active_credit_accounts)
-> for each credit account:
    load all historical transactions ordered by date descending (transaction_access.get_transactions_for_account)
    map to domain models (domain.credit_cards.CreditCardTransaction)
    invoke pure engine (domain.credit_cards.calculate_credit_card_state)
    filter current month transactions in [start_date, end_date)
    map monthly transactions to CreditCardMonthlyTransactionItem dataclasses
    assemble CreditCardAccountSummaryItem dataclass
-> assemble and return CreditCardSummaryResult(cards=cards)
```

#### Transaction Ownership
- Zero database transaction operations: 0 `add`, 0 `flush`, 0 `commit`, 0 `rollback`, 0 `refresh`.
- Read-only composite query orchestration.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: determines date range, queries active cards, fetches complete transaction histories per card, invokes pure financial calculations, filters display rows, and maps into application dataclasses.
- **Coordinates more than one Accessor?** Yes: `account_access` and `transaction_access`.
- **Invokes an Engine?** Yes: `calculate_credit_card_state` in `domain/credit_cards.py`.
- **Merely performs one query/mutation plus mapping?** No: coordinates $N+1$ queries across two tables and executes financial calculations.
- **Could current public operation be described as simple CRUD?** No.
- **Exists primarily to produce a particular screen/API response?** Yes: powers the Credit Cards overview screen (`GET /credit-cards/summary`).
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.6 CSVImportManager (`backend/managers/csv_import_manager.py`)

#### Identity
- **Module Name:** `csv_import_manager.py`
- **Public Entry Functions:**
  - `confirm_csv_import(db: Session, raw_bytes: bytes, loader: BankStatementLoader) -> CSVImportSummary`
- **Production Callers:**
  - `backend/routers/upload.py:317` (via `POST /upload/confirm`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.merchant_normalization.normalize_merchant`
- **Accessors Called:**
  - `access.account_access.get_account_by_id`
  - `access.categorization_rule_access.get_rules_lookup_dict`
  - `access.transaction_access.csv_import_transaction_exists`
  - `access.transaction_access.stage_csv_import_transaction`
- **Ingestion / Parser Boundary:**
  - `BankStatementLoader.load_records_tolerant(raw_bytes)`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** Target account, statement bytes stream, categorization rules, transactions table.
- **Manager-Defined DTOs / Exceptions:**
  - `CSVImportSummary`
  - `CSVImportAccountNotFoundError`
  - `CSVImportUnknownFormatError`
  - `CSVImportParseError`

#### Workflow
```text
verify destination account exists via account_access.get_account_by_id (redundant second check)
-> raise CSVImportAccountNotFoundError if missing
-> parse CSV bytes via loader.load_records_tolerant (BankStatementLoader)
-> catch ValueError and raise CSVImportParseError
-> fetch rules lookup dictionary via categorization_rule_access.get_rules_lookup_dict
-> loop valid parsed transactions:
    check duplicate via transaction_access.csv_import_transaction_exists(account_id, date, amount, description)
    if duplicate:
        skipped += 1
        continue
    normalize merchant via domain.merchant_normalization.normalize_merchant
    stage transaction via transaction_access.stage_csv_import_transaction (inlines rule matching)
    imported += 1
    catch per-row exceptions and append to errors list
-> commit entire batch via db.commit()
-> return CSVImportSummary(imported, skipped, errors)
```

#### Transaction Ownership
- Owns the single batch commit boundary:
  - Calls `db.commit()` at line 113.
- Called Accessor: `transaction_access.stage_csv_import_transaction` executes `db.add(txn)` without commit or flush.
- Note: There is NO `db.rollback()` in `confirm_csv_import` if `db.commit()` fails.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: account verification, tolerant CSV parsing, duplicate checking, merchant normalization, inline rule matching, transaction staging, per-row error isolation, and batch commit.
- **Coordinates more than one Accessor?** Yes: 3 Accessors (`account_access`, `categorization_rule_access`, `transaction_access`).
- **Invokes an Engine?** Invokes `domain.merchant_normalization.normalize_merchant`.
- **Merely performs one query/mutation plus mapping?** No.
- **Could current public operation be described as simple CRUD?** No.
- **Exists primarily to produce a particular screen/API response?** Exists to orchestrate the import commit workflow (`POST /upload/confirm`).
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.7 DashboardSummaryManager (`backend/managers/dashboard_summary_manager.py`)

#### Identity
- **Module Name:** `dashboard_summary_manager.py`
- **Public Entry Functions:**
  - `get_dashboard_summary(db: Session, budget_month: date) -> DashboardSummaryResult`
- **Production Callers:**
  - `backend/routers/summaries.py:72` (via `GET /summary/dashboard`)
- **Other Managers Called:**
  - `managers.budget_summary_manager.get_budget_summary`
- **Engines / Domain Functions Called:**
  - `domain.dates.determine_month_range`
- **Accessors Called:**
  - `access.account_access.get_active_accounts`
  - `access.transaction_access.get_recent_transactions_for_month`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `accounts`, `transactions`, plus all tables touched by `budget_summary_manager`.
- **Manager-Defined DTOs:**
  - `DashboardAccountItem`
  - `DashboardTransactionAccountItem`
  - `DashboardRecentTransactionItem`
  - `DashboardSummaryResult`

#### Workflow
```text
determine month interval [start_date, end_date) via domain.dates.determine_month_range
-> invoke BudgetSummaryManager.get_budget_summary(db, budget_month)
-> retrieve active accounts via account_access.get_active_accounts
-> retrieve 10 recent transactions for month via transaction_access.get_recent_transactions_for_month
-> iterate raw accounts:
    sum current_balance into total_balance
    map into DashboardAccountItem dataclass
-> iterate raw transactions:
    map account relationship to DashboardTransactionAccountItem dataclass
    map transaction to DashboardRecentTransactionItem dataclass
-> assemble and return DashboardSummaryResult(budget_summary, accounts, total_balance, recent_transactions)
```

#### Transaction Ownership
- Zero database transaction operations: 0 `add`, 0 `flush`, 0 `commit`, 0 `rollback`, 0 `refresh`.
- Read-only composite aggregation workflow.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: coordinates another Manager workflow (`BudgetSummaryManager`), active account balance aggregation, and recent transaction history retrieval.
- **Coordinates more than one Accessor?** Coordinates 2 Accessors directly (`account_access`, `transaction_access`), and 3 Accessors indirectly via `BudgetSummaryManager`.
- **Invokes an Engine?** Directly invokes only `domain.dates.determine_month_range`. The Zero-Based Budgeting Engine is invoked indirectly via `BudgetSummaryManager`.
- **Merely performs one query/mutation plus mapping?** No.
- **Could current public operation be described as simple CRUD?** No.
- **Exists primarily to produce a particular screen/API response?** Yes: exclusively powers the main Dashboard page (`GET /summary/dashboard`).
- **Calls another Manager synchronously?** Yes: calls `BudgetSummaryManager`.
- **Is called by another Manager synchronously?** No.

---

### 2.8 MLCategorizationManager (`backend/managers/ml_categorization_manager.py`)

#### Identity
- **Module Name:** `ml_categorization_manager.py`
- **Public Entry Functions:**
  - `get_ml_status(db: Session) -> schemas.MLModelStatusRead`
  - `retrain_model(db: Session, force: bool = False) -> tuple[bool, str, bool, schemas.MLModelStatusRead]`
  - `ensure_model_freshness(db: Session) -> None`
  - `predict_category_for_transaction(db: Session, transaction_id: UUID) -> Optional[schemas.CategorySuggestionRead]`
  - `batch_predict_suggestions(db: Session, transaction_ids: Sequence[UUID]) -> list[schemas.CategorySuggestionRead]`
  - `accept_suggestion(db: Session, transaction_id: UUID, category_id: UUID) -> models.Transaction`
- **Production Callers:**
  - `backend/routers/ml.py:26` (calls `get_ml_status`)
  - `backend/routers/ml.py:39` (calls `retrain_model`)
  - `backend/routers/transactions.py:280` (calls `batch_predict_suggestions`)
  - `backend/routers/transactions.py:296` (calls `predict_category_for_transaction`)
  - `backend/routers/transactions.py:322` (calls `accept_suggestion`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.categorization_rules.clean_merchant_key`
  - `domain.ml_categorization` functions and classes (`build_feature_text`, `create_ml_pipeline`, `evaluate_classifier`, `should_activate_candidate`, `predict_suggestion`, `MerchantFrequencyBaseline`)
- **Accessors Called:**
  - `access.category_access.get_category_by_id`
  - `access.categorization_rule_access.get_rules_lookup_dict`
  - `access.ml_model_access.get_model_metadata`, `artifact_exists`, `get_ml_training_examples`, `save_candidate_model`, `activate_candidate_model`, `cleanup_temp_candidate`, `update_model_metadata_after_training`, `load_active_model`, `increment_training_revision`
  - `access.split_access.transaction_has_splits`
  - `access.transaction_access.get_transaction_by_id`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `transactions`, `ml_model_metadata`, `categories`, `categorization_rules`, and filesystem `.joblib` model artifact storage via `ml_model_access`.

#### Workflow
1. **`retrain_model`:**
   ```text
   load metadata and eligible supervised training examples (ml_model_access)
   -> validate data sufficiency (>= 10 examples, >= 2 categories)
   -> extract feature texts and labels
   -> train/test split (stratified if viable)
   -> fit TF-IDF + LogisticRegression candidate pipeline on training split
   -> fit MerchantFrequencyBaseline on training split
   -> evaluate candidate on test split via domain.ml_categorization.evaluate_classifier
   -> evaluate safety gates via domain.ml_categorization.should_activate_candidate
   -> if gates pass (or force=True):
       fit final pipeline on all examples
       serialize to temp file (ml_model_access.save_candidate_model)
       atomically replace active model (ml_model_access.activate_candidate_model)
       update metadata record (ml_model_access.update_model_metadata_after_training -> db.flush())
       commit transaction (db.commit())
   -> catch Exception:
       rollback database (db.rollback())
       delete temp file (ml_model_access.cleanup_temp_candidate)
       return failure status
   ```
2. **`predict_category_for_transaction` & `batch_predict_suggestions`:**
   ```text
   ensure model freshness (trigger auto-retrain if revision delta >= 10)
   -> load active pipeline from joblib artifact
   -> load rules lookup dictionary
   -> for each transaction:
       verify eligible (exists, not transfer, not split, category_id is NULL)
       check deterministic rules first (precedence: manual > rule > ML)
       if no rule match:
           build feature text (build_feature_text)
           predict via domain.ml_categorization.predict_suggestion
           if confidence >= threshold (0.60):
               assemble suggestion
   -> return suggestions
   ```
3. **`accept_suggestion`:**
   ```text
   load transaction and verify category exists
   -> update tx.category_id = category_id, tx.category_source = 'ml'
   -> increment training revision (ml_model_access.increment_training_revision -> db.flush())
   -> db.add(tx)
   -> db.commit()
   -> db.refresh(tx)
   -> return tx
   ```

#### Transaction Ownership
- Multiple commit/rollback boundaries within the Manager:
  - In `retrain_model`: `db.add(meta)` + `db.commit()` at lines 119-120; `db.add(meta)` + `db.commit()` at lines 204-205; `db.commit()` at line 231; `db.rollback()` at line 241.
  - In `accept_suggestion`: `db.add(tx)` at line 501; `db.commit()` at line 502; `db.refresh(tx)` at line 503.
- Called Accessors: `ml_model_access.update_model_metadata_after_training` and `increment_training_revision` execute `db.flush()` without committing.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: coordinates data extraction, ML training/evaluation, filesystem artifact replacement, metadata updates, precedence evaluation (rule before ML), suggestion inference, and label acceptance.
- **Coordinates more than one Accessor?** Yes: 5 Accessors (`category_access`, `categorization_rule_access`, `ml_model_access`, `split_access`, `transaction_access`).
- **Invokes an Engine?** Yes: comprehensive invocation of `domain/ml_categorization.py`.
- **Merely performs one query/mutation plus mapping?** No.
- **Could current public operation be described as simple CRUD?** No.
- **Exists primarily to produce a particular screen/API response?** Coordinates multiple distinct use cases: status, retraining, single/batch prediction, and acceptance.
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.9 PlaidAccountSyncManager (`backend/managers/plaid_account_sync_manager.py`)

#### Identity
- **Module Name:** `plaid_account_sync_manager.py`
- **Public Entry Functions:**
  - `sync_plaid_accounts(db: Session, item_id: Optional[UUID] = None, plaid_item_id: Optional[str] = None) -> PlaidAccountSyncResult`
- **Production Callers:**
  - `backend/routers/plaid.py:72` (via `POST /plaid/sync_accounts`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:** None.
- **Accessors Called:**
  - `access.plaid_item_access.get_plaid_item_by_id`
  - `access.plaid_item_access.get_plaid_item_by_plaid_item_id`
  - `access.plaid_access.fetch_accounts_for_token`
  - `access.account_access.stage_or_update_plaid_account`
- **Security Helper:**
  - `security.decrypt_token`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** Remote Plaid `/accounts/get` API (via `plaid_access`), local PostgreSQL `plaid_items` and `accounts` tables.
- **Manager-Defined DTOs / Exceptions:**
  - `PlaidAccountSyncResult`
  - `PlaidAccountSyncMissingIdentifierError`
  - `PlaidAccountSyncItemNotFoundError`
  - `PlaidAccountSyncDecryptionError`
  - `PlaidAccountSyncExternalApiError`

#### Workflow
```text
validate identifier presence (item_id or plaid_item_id)
-> resolve PlaidItem from persistence (plaid_item_access)
-> decrypt stored access token (security.decrypt_token)
-> fetch remote account snapshots from Plaid API (plaid_access.fetch_accounts_for_token)
-> loop snapshots:
    stage/update account in database (account_access.stage_or_update_plaid_account)
-> flush session (db.flush())
-> commit transaction (db.commit())
-> return PlaidAccountSyncResult(accounts_updated)
```

#### Transaction Ownership
- Owns the single transaction commit boundary:
  - Calls `db.flush()` at line 107.
  - Calls `db.commit()` at line 108.
- Called Accessors: `account_access.stage_or_update_plaid_account` executes `db.add(db_account)` without flush or commit.
- Note: There is NO `db.rollback()` if flush or commit fails.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: identifier resolution, token decryption, external Plaid API fetch, relational account upsert staging, and database commit.
- **Coordinates more than one Accessor?** Yes: 2 Accessors (`plaid_item_access`, `plaid_access`, plus `account_access` = 3 Accessors).
- **Invokes an Engine?** No.
- **Merely performs one query/mutation plus mapping?** No: coordinates external API fetch and relational upsert.
- **Could current public operation be described as simple CRUD?** No.
- **Exists primarily to produce a particular screen/API response?** Exists to orchestrate the account balance refresh workflow (`POST /plaid/sync_accounts`).
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.10 PlaidTransactionSyncManager (`backend/managers/plaid_transaction_sync_manager.py`)

#### Identity
- **Module Name:** `plaid_transaction_sync_manager.py`
- **Public Entry Functions:**
  - `sync_plaid_transactions(db: Session, item_id: Optional[UUID] = None, plaid_item_id: Optional[str] = None) -> PlaidTransactionSyncResult`
- **Private Helper Functions:**
  - `_process_upsert_event(db: Session, tx_data: dict, rules_lookup: Optional[dict]) -> Optional[str]`
- **Production Callers:**
  - `backend/routers/plaid.py:99` (via `POST /plaid/sync_transactions`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.merchant_normalization.normalize_merchant`
- **Accessors Called:**
  - `access.plaid_item_access.get_plaid_item_by_id`
  - `access.plaid_item_access.get_plaid_item_by_plaid_item_id`
  - `access.plaid_item_access.stage_transactions_cursor`
  - `access.plaid_access.fetch_accounts_for_token`
  - `access.account_access.stage_or_update_plaid_account`
  - `access.account_access.get_account_by_plaid_account_id`
  - `access.categorization_rule_access.get_rules_lookup_dict`
  - `access.plaid_transaction_access.fetch_transactions_page`
  - `access.transaction_access.stage_or_update_plaid_transaction`
  - `access.transaction_access.stage_delete_transaction_by_plaid_id`
- **Security Helper:**
  - `security.decrypt_token`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** Remote Plaid `/accounts/get` (SDK), remote Plaid `/transactions/sync` (raw HTTP), local PostgreSQL `plaid_items`, `accounts`, `transactions`, `categorization_rules`.
- **Manager-Defined DTOs / Exceptions:**
  - `PlaidTransactionSyncResult`
  - `PlaidTransactionSyncMissingIdentifierError`
  - `PlaidTransactionSyncItemNotFoundError`
  - `PlaidTransactionSyncDecryptionError`
  - `PlaidTransactionSyncAccountRefreshError`
  - `PlaidTransactionSyncHttpError`
  - `PlaidTransactionSyncNetworkError`

#### Workflow
```text
validate identifier presence (item_id or plaid_item_id)
-> resolve PlaidItem from persistence (plaid_item_access)
-> decrypt stored access token (security.decrypt_token)
-> pre-sync account balance refresh:
    fetch snapshots from Plaid API (plaid_access.fetch_accounts_for_token)
    stage account updates (account_access.stage_or_update_plaid_account)
    execute db.flush() (staged in session, NOT committed)
-> load rules lookup dictionary (categorization_rule_access.get_rules_lookup_dict)
-> read starting cursor from plaid_item.transactions_cursor
-> execute pagination loop against Plaid raw HTTP (plaid_transaction_access.fetch_transactions_page):
    advance cursor to page.next_cursor
    for each added event:
        _process_upsert_event:
            resolve account via account_access.get_account_by_plaid_account_id
            normalize merchant via domain.merchant_normalization.normalize_merchant
            stage transaction via transaction_access.stage_or_update_plaid_transaction (inlines rule matching)
            execute db.commit()  # per-row commit!
    for each modified event:
        _process_upsert_event -> execute db.commit()  # per-row commit!
    for each removed event:
        stage deletion via transaction_access.stage_delete_transaction_by_plaid_id
        if record found:
            execute db.commit()  # per-row commit!
-> stage final cursor via plaid_item_access.stage_transactions_cursor
-> execute db.commit()  # final cursor commit (legacy helper equivalent)
-> execute db.commit()  # redundant final commit (compatibility artifact)
-> return PlaidTransactionSyncResult
```

#### Transaction Ownership
- Unusual, non-atomic commit structure:
  - Account balances staged with `db.flush()` at line 199.
  - Per-event commits: `db.commit()` on every added/modified event at line 123 (and line 126 on conflict).
  - Per-event commits: `db.commit()` on every removed event at line 250.
  - Final cursor commit: `db.commit()` at line 259.
  - Redundant final commit: `db.commit()` at line 261.
- Total commits during a sync: $1 + N_{	ext{added}} + N_{	ext{modified}} + N_{	ext{removed}} + 2$.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: identifier resolution, token decryption, pre-sync account balance refresh, pagination loop over raw HTTP, per-event upsert and deletion staging, merchant normalization, inline rule matching, cursor tracking, and multi-stage commit ownership.
- **Coordinates more than one Accessor?** Yes: coordinates 6 Accessors (`plaid_item_access`, `plaid_access`, `account_access`, `categorization_rule_access`, `plaid_transaction_access`, `transaction_access`).
- **Invokes an Engine?** Invokes `domain.merchant_normalization.normalize_merchant`.
- **Merely performs one query/mutation plus mapping?** No.
- **Could current public operation be described as simple CRUD?** No.
- **Exists primarily to produce a particular screen/API response?** Orchestrates the transaction synchronization workflow (`POST /plaid/sync_transactions`).
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.11 RecurringTransactionManager (`backend/managers/recurring_transaction_manager.py`)

#### Identity
- **Module Name:** `recurring_transaction_manager.py`
- **Public Entry Functions:**
  - `detect_and_sync_recurring_items(db: Session, account_id: Optional[UUID] = None) -> list[schemas.RecurringItemRead]`
  - `list_recurring_items(db: Session, account_id: Optional[UUID] = None) -> list[schemas.RecurringItemRead]`
  - `get_recurring_item_detail(db: Session, item_id: UUID) -> Optional[schemas.RecurringItemDetailRead]`
  - `confirm_recurring_item(db: Session, item_id: UUID) -> Optional[schemas.RecurringItemRead]`
  - `dismiss_recurring_item(db: Session, item_id: UUID) -> Optional[schemas.RecurringItemRead]`
- **Production Callers:**
  - `backend/routers/recurring.py:32,49,64,84,104` (via `GET /recurring/`, `POST /recurring/detect`, `GET /recurring/{id}`, `POST /recurring/{id}/confirm`, `POST /recurring/{id}/dismiss`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.categorization_rules.clean_merchant_key`
  - `domain.recurring_transactions.detect_recurring_series`
- **Accessors Called:**
  - `access.recurring_access.stage_upsert_detected_series`, `remove_stale_detected_items`, `list_recurring_items`, `get_recurring_item_by_id`, `set_recurring_item_status`
  - `access.transaction_access.get_eligible_transactions_for_recurrence`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `recurring_items`, `transactions`, `accounts`.
- **Direct Infrastructure/Transport Coupling:** Returns Pydantic schemas (`schemas.RecurringItemRead`, `schemas.RecurringItemDetailRead`).

#### Workflow
1. **`detect_and_sync_recurring_items`:**
   ```text
   load eligible historical transactions (transaction_access.get_eligible_transactions_for_recurrence)
   -> map to domain inputs (RecurrenceTransactionInput)
   -> invoke pure Recurrence Engine (domain.recurring_transactions.detect_recurring_series)
   -> build series identity map using clean_merchant_key
   -> stage upsert detected series (recurring_access.stage_upsert_detected_series -> db.flush())
   -> remove stale auto-detected series (recurring_access.remove_stale_detected_items -> db.flush())
   -> commit batch transaction (db.commit()) or rollback on exception (db.rollback())
   -> load persisted items and assemble schemas.RecurringItemRead with transaction IDs
   -> return list of schemas
   ```
2. **`confirm_recurring_item` / `dismiss_recurring_item`:**
   ```text
   update status via recurring_access.set_recurring_item_status (db.flush())
   -> commit transaction (db.commit()) or rollback on exception (db.rollback())
   -> map and return updated schema
   ```

#### Transaction Ownership
- Owns commit boundaries across mutative operations:
  - In `detect_and_sync_recurring_items`: `db.commit()` at line 114; `db.rollback()` at line 116.
  - In `confirm_recurring_item`: `db.commit()` at line 223; `db.rollback()` at line 226.
  - In `dismiss_recurring_item`: `db.commit()` at line 242; `db.rollback()` at line 245.
- Called Accessor: `recurring_access` methods execute `db.flush()` without committing.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** `detect_and_sync_recurring_items` coordinates eligible transaction extraction, heuristic cadence detection, persistence synchronization, stale item cleanup, and batch commit. In contrast, `confirm_recurring_item` and `dismiss_recurring_item` are simple 1-line status updates plus commit.
- **Coordinates more than one Accessor?** Yes: `transaction_access` and `recurring_access`.
- **Invokes an Engine?** Yes: `detect_recurring_series` in `domain/recurring_transactions.py`.
- **Merely performs one query/mutation plus mapping?** For `confirm`, `dismiss`, and `list`: yes, essentially CRUD. For `detect_and_sync`: no.
- **Could current public operation be described as simple CRUD?** 3 out of 5 entry functions (`list`, `confirm`, `dismiss`) are simple CRUD / status toggles.
- **Exists primarily to produce a particular screen/API response?** Exists as the dedicated manager for the Recurring Transactions page.
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.12 TransactionSplitManager (`backend/managers/transaction_split_manager.py`)

#### Identity
- **Module Name:** `transaction_split_manager.py`
- **Public Entry Functions:**
  - `get_transaction_splits(db: Session, transaction_id: UUID) -> Sequence[models.TransactionSplit]`
  - `create_or_replace_split(db: Session, transaction_id: UUID, allocations: Sequence[schemas.TransactionSplitLine]) -> models.Transaction`
  - `unsplit_transaction(db: Session, transaction_id: UUID, target_category_id: Optional[UUID] = None) -> models.Transaction`
- **Production Callers:**
  - `backend/routers/transactions.py:350` (via `GET /transactions/{id}/splits`)
  - `backend/routers/transactions.py:368` (via `PUT /transactions/{id}/splits`)
  - `backend/routers/transactions.py:397` (via `POST /transactions/{id}/unsplit`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.transaction_splits.validate_split_allocations`
- **Accessors Called:**
  - `access.category_access.get_category_by_id`
  - `access.ml_model_access.increment_training_revision`
  - `access.split_access.get_splits_for_transaction`, `transaction_has_splits`, `stage_replace_splits`, `stage_delete_splits`
  - `access.transaction_access.get_transaction_by_id`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `transactions`, `transaction_splits`, `categories`, `ml_model_metadata`.
- **Manager-Defined Exceptions:**
  - `TransactionNotFoundError`
  - `SplitValidationError`
  - `SplitTransactionPendingError`
  - `SplitTransactionTransferError`

#### Workflow
1. **`create_or_replace_split`:**
   ```text
   verify transaction existence and eligibility (not pending, not transfer)
   -> validate allocations against domain invariants (domain.transaction_splits.validate_split_allocations)
   -> verify each target category exists in persistence (category_access.get_category_by_id)
   -> clear parent category (tx.category_id = None, tx.category_source = None, db.add(tx))
   -> bump ML training revision if parent had human label (ml_model_access.increment_training_revision -> db.flush())
   -> replace split allocations (split_access.stage_replace_splits -> db.flush())
   -> expire relationships (db.expire(tx, ['splits']))
   -> commit transaction (db.commit())
   -> refresh instance (db.refresh(tx))
   -> return tx ORM instance
   ```
2. **`unsplit_transaction`:**
   ```text
   verify transaction existence and target category validity
   -> verify transaction currently has splits (split_access.transaction_has_splits)
   -> delete split allocations (split_access.stage_delete_splits -> db.flush())
   -> restore parent category (target_category_id, category_source='manual' if provided)
   -> bump ML training revision if assigned explicit category
   -> expire relationships (db.expire(tx, ['splits']))
   -> db.add(tx)
   -> commit transaction (db.commit())
   -> refresh instance (db.refresh(tx))
   -> return tx ORM instance
   ```
3. **`get_transaction_splits`:**
   ```text
   verify transaction existence (transaction_access.get_transaction_by_id)
   -> load splits (split_access.get_splits_for_transaction)
   -> return Sequence[models.TransactionSplit]
   ```

#### Transaction Ownership
- Owns the commit/rollback boundary:
  - In `create_or_replace_split`: `db.commit()` at line 131; `db.refresh(tx)` at line 132; `db.rollback()` at line 135.
  - In `unsplit_transaction`: `db.commit()` at line 179; `db.refresh(tx)` at line 180; `db.rollback()` at line 183.
- Called Accessors: `split_access` and `ml_model_access` execute `db.flush()` without committing.
- Leaks ORM instances: returns `models.Transaction` and `models.TransactionSplit` directly.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** `create_or_replace_split` and `unsplit_transaction` coordinate parent eligibility checks, allocation invariant validation, category existence, split staging, parent category mutation, ML training revision synchronization, and atomic commit. `get_transaction_splits` is a simple existence check + query.
- **Coordinates more than one Accessor?** Yes: 4 Accessors (`category_access`, `ml_model_access`, `split_access`, `transaction_access`).
- **Invokes an Engine?** Yes: `validate_split_allocations` in `domain/transaction_splits.py`.
- **Merely performs one query/mutation plus mapping?** No (for mutation operations). Yes (for `get_transaction_splits`).
- **Could current public operation be described as simple CRUD?** `get_transaction_splits` could be described as simple CRUD; the mutations cannot.
- **Exists primarily to produce a particular screen/API response?** Exists to orchestrate the Split Transaction modal workflows.
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.13 TransferReconciliationManager (`backend/managers/transfer_reconciliation_manager.py`)

#### Identity
- **Module Name:** `transfer_reconciliation_manager.py`
- **Public Entry Functions:**
  - `get_transfer_candidates(db: Session) -> Sequence[TransferCandidateItem]`
- **Production Callers:**
  - `backend/routers/credit_cards.py:73` (via `GET /credit-cards/transfer-candidates`)
  - `backend/routers/transactions.py:76` (via `GET /transactions/transfer-candidates`)
- **Other Managers Called:** None.
- **Engines / Domain Functions Called:**
  - `domain.reconciliation.detect_transfer_candidates`
- **Accessors Called:**
  - `access.transaction_access.get_unmatched_inflow_transactions`
  - `access.transaction_access.get_unmatched_outflow_transactions`
  - `access.transaction_access.get_account_for_transaction`
- **Legacy `crud` Functions Called:** None.
- **Resources Accessed:** PostgreSQL tables `transactions` and `accounts`.
- **Manager-Defined DTOs:**
  - `TransferInflowSideItem`
  - `TransferOutflowAccountItem`
  - `TransferOutflowSideItem`
  - `TransferCandidateItem`

#### Workflow
```text
load unmatched inflows via transaction_access.get_unmatched_inflow_transactions
-> load unmatched outflows via transaction_access.get_unmatched_outflow_transactions
-> index transactions by ID for correlation
-> map to domain models (domain.reconciliation.ReconciliationTransaction)
-> invoke pure Reconciliation Engine (domain.reconciliation.detect_transfer_candidates)
-> for each paired candidate:
    resolve account relationships via transaction_access.get_account_for_transaction
    map outflow account to TransferOutflowAccountItem
    map inflow side to TransferInflowSideItem
    map outflow side to TransferOutflowSideItem
    assemble TransferCandidateItem
-> return list of TransferCandidateItem dataclasses
```

#### Transaction Ownership
- Zero database transaction operations: 0 `add`, 0 `flush`, 0 `commit`, 0 `rollback`, 0 `refresh`.
- Read-only candidate pairing search workflow.

#### Boundary Assessment Evidence
- **Coordinates more than one meaningful activity?** Yes: loads candidate pools from two queries, maps to domain models, executes heuristic pairing engine, resolves account relationships for matched pairs, and maps to application dataclasses.
- **Coordinates more than one Accessor?** Calls only 1 Accessor module (`transaction_access`), but uses 3 distinct functions in it.
- **Invokes an Engine?** Yes: `detect_transfer_candidates` in `domain/reconciliation.py`.
- **Merely performs one query/mutation plus mapping?** No: coordinates two distinct queries, invokes heuristic pairing, and enriches results.
- **Could current public operation be described as simple CRUD?** No.
- **Exists primarily to produce a particular screen/API response?** Powers the transfer candidates banner and drawer on both the Transactions and Credit Cards screens.
- **Calls another Manager synchronously?** No.
- **Is called by another Manager synchronously?** No.

---

### 2.14 Use-Case Family Comparison

#### Summary Managers Family
Comparison of:
- `BudgetSummaryManager`
- `DashboardSummaryManager`
- `AccountSummaryManager`
- `CreditCardSummaryManager`

| Attribute | `BudgetSummaryManager` | `DashboardSummaryManager` | `AccountSummaryManager` | `CreditCardSummaryManager` |
|---|---|---|---|---|
| **Accessors Shared** | `category_access`, `budget_access`, `transaction_access` | `account_access`, `transaction_access` | `account_access`, `transaction_access` | `account_access`, `transaction_access` |
| **Domain Logic Shared** | `determine_month_range`, `calculate_budget_summary` | `determine_month_range`, reuses `BudgetSummaryManager` | `calculate_depository_balance` | `determine_month_range`, `calculate_credit_card_state` |
| **Calls Other Manager?** | No | **Yes (`BudgetSummaryManager`)** | No | No |
| **Called By Other Manager?** | **Yes (by `DashboardSummaryManager`)** | No | No | No |
| **Data Overlap** | Queries category groups, monthly budgets, and actuals | Queries active accounts and recent transactions; reuses budget summary | Queries all accounts and aggregates depository net transactions | Queries active credit cards and full transaction history per card |
| **Accounting Rules Divergence** | Authoritative ZBB planned, actual, to_be_assigned | Computes scalar `total_balance` by directly summing stored `current_balance` on active accounts (does **not** derive balances from ledger) | Calculates authoritative depository balances from ledger: $starting - net$ | Calculates authoritative credit card balance owed from ledger: $starting + net$ |
| **Divided By** | Calculation domain + endpoint | View / screen composition (`/dashboard`) | View / screen listing (`/accounts/`) | View / screen overview (`/credit-cards/summary`) |

**Key Finding:** `DashboardSummaryManager` does **not** call `AccountSummaryManager`. As a result, there is an observable calculation divergence: `AccountSummaryManager` recalculates depository cash balances from historical transactions ($starting\_balance - net\_transactions$), whereas `DashboardSummaryManager` simply sums the stored `acc.current_balance` column across active accounts.

---

#### Rule & Ingestion Managers Family
Comparison of:
- `CategorizationRuleManager`
- `CSVImportManager`
- `PlaidTransactionSyncManager`

Specifically evaluating automatic rule application during statement ingestion and bank sync:

1. **Does `CSVImportManager` call `CategorizationRuleManager`?**
   - **NO.** `CSVImportManager` does not import or call `CategorizationRuleManager`.
2. **Does `PlaidTransactionSyncManager` call `CategorizationRuleManager`?**
   - **NO.** `PlaidTransactionSyncManager` does not import or call `CategorizationRuleManager`.
3. **If yes, which Manager function is called and what does that function actually do?**
   - **N/A.** Neither sync manager calls `CategorizationRuleManager`.
4. **How is automatic categorization actually invoked during ingestion/sync?**
   - Both `CSVImportManager` (`csv_import_manager.py:74`) and `PlaidTransactionSyncManager` (`plaid_transaction_sync_manager.py:201`) call `categorization_rule_access.get_rules_lookup_dict(db)` directly.
   - The resulting dictionary mapping `clean_merchant_key -> category_id` is passed into `transaction_access.stage_csv_import_transaction` and `transaction_access.stage_or_update_plaid_transaction`.
   - The actual rule evaluation logic is embedded directly inside `backend/access/transaction_access.py` (lines 234–237, 314–317, 381–384):
     ```python
     if rules_lookup is not None:
         clean_key = clean_merchant_key(resolved_merchant)
         if clean_key and clean_key in rules_lookup:
             assigned_category_id = rules_lookup[clean_key]
             category_source = "rule"
     ```
   - `CategorizationRuleManager` exists solely for **retroactive batch application** (`preview_rule_matches` and `apply_rule_to_uncategorized`) on existing database rows.
5. **Could that called operation be described independently of the rule-management use case?**
   - Yes: retrieving the active rule lookup dictionary is a pure Accessor query (`categorization_rule_access.get_rules_lookup_dict`), and matching canonical payee names is a pure domain dictionary lookup.
---

## 3. Explicit Manager-to-Manager Call Audit

A search across the entire backend reveals exactly **one** production Manager-to-Manager dependency:

| Caller Manager | Called Manager | Function | Synchronous? | Return Value Used? | Shared DB Session? | Purpose |
|---|---|---|---|---|---|---|
| `dashboard_summary_manager.py` | `budget_summary_manager.py` | `get_budget_summary(db, budget_month)` | Yes | Yes (embedded into `DashboardSummaryResult.budget_summary`) | Yes (passes caller's `db: Session`) | Reuses complete ZBB calculation workflow for dashboard display |

### Confirmation of Documented Relationships

The repository's architecture documentation (notably `docs/architecture/volatility-map.md` lines 179–208) contains explicit diagram edges linking managers. Comparing those claims against production Python code produces the following findings:

| Documented Relationship | Claimed Mechanism | Current Code Reality | Status | Concrete Source Evidence |
|---|---|---|---|---|
| `DashboardSummaryManager -> BudgetSummaryManager` | Synchronous workflow composition | Present | **PRESENT** | `backend/managers/dashboard_summary_manager.py:25` imports `from . import budget_summary_manager`; line 98 calls `budget_summary = budget_summary_manager.get_budget_summary(db, budget_month)` |
| `DashboardSummaryManager -> AccountSummaryManager` | Synchronous workflow composition | Absent | **ABSENT** | `dashboard_summary_manager.py` does **not** import `account_summary_manager`. It bypasses it, importing `get_active_accounts` directly from `access.account_access:21` and reading `acc.current_balance` directly. |
| `CSVImportManager -> CategorizationRuleManager` | Synchronous rule evaluation | Absent | **ABSENT** | `csv_import_manager.py` does **not** import `categorization_rule_manager`. It calls `categorization_rule_access.get_rules_lookup_dict(db)` directly at line 74 and delegates inline rule matching to `transaction_access.stage_csv_import_transaction`. |
| `PlaidTransactionSyncManager -> CategorizationRuleManager` | Synchronous rule evaluation | Absent | **ABSENT** | `plaid_transaction_sync_manager.py` does **not** import `categorization_rule_manager`. It calls `categorization_rule_access.get_rules_lookup_dict(db)` directly at line 201 and delegates inline rule matching to `transaction_access.stage_or_update_plaid_transaction`. |

---

## 4. ResourceAccess Audit

This section audits each of the 12 concrete resource access modules in `backend/access/`.

### 4.1 Module-by-Module Production Specifications

#### 1. `account_access.py`
- **Public Production Functions:**
  - `get_account_by_id(db, account_id) -> Optional[models.Account]` (Callers: `upload.py:233,305`, `account_reconciliation_manager.py:46`, `csv_import_manager.py:63`)
  - `get_active_accounts(db) -> Sequence[models.Account]` (Callers: `dashboard_summary_manager.py:101`)
  - `get_active_credit_accounts(db) -> Sequence[models.Account]` (Callers: `credit_card_summary_manager.py:75`)
  - `get_account_by_plaid_account_id(db, plaid_account_id) -> Optional[models.Account]` (Callers: `plaid_transaction_sync_manager.py:87`)
  - `stage_or_update_plaid_account(db, item_id, plaid_account_id, ...) -> models.Account` (Callers: `plaid_account_sync_manager.py:92`, `plaid_transaction_sync_manager.py:185`)
  - `get_all_accounts_ordered(db) -> Sequence[models.Account]` (Callers: `account_summary_manager.py:32`)
  - `create_manual_account(db, name, account_type, ...) -> models.Account` (Callers: `accounts.py:31`)
  - `update_manual_account(db, account_id, update_data) -> Optional[models.Account]` (Callers: `accounts.py:45`)
  - `delete_account(db, account_id) -> bool` (Callers: `accounts.py:57`)
  - `update_account_reconciliation_metadata(db, account_id, last_reconciled_date, last_reconciled_balance) -> Optional[models.Account]` (Callers: `account_reconciliation_manager.py:177`)
- **Resource Accessed:** PostgreSQL table `accounts`.
- **Operations:** Both retrieval and mutation.
- **Transaction Operations:**
  - `db.commit()` in `create_manual_account` (line 165), `update_manual_account` (line 199), `delete_account` (line 218).
  - `db.refresh()` in `create_manual_account` (line 166), `update_manual_account` (line 200).
  - `db.flush()` in `update_account_reconciliation_metadata` (line 237).
  - Staging functions (`stage_or_update_plaid_account`) execute `db.add()` only.
- **Accepts ORM Objects?** No.
- **Returns ORM Objects?** Yes (`models.Account`).
- **Accepts Pydantic Models?** No (`update_manual_account` accepts `dict`).
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Resource/entity-oriented (`models.Account`).

#### 2. `budget_access.py`
- **Public Production Functions:**
  - `get_budgets_for_month(db, month_date) -> Sequence[models.Budget]` (Callers: `budget_summary_manager.py:44`)
  - `get_budget_by_id(db, budget_id) -> Optional[models.Budget]` (Callers: `budgets.py:63`)
  - `list_budgets(db) -> Sequence[models.Budget]` (Callers: `budgets.py:47`)
  - `create_budget(db, category_id, month, planned_amount) -> models.Budget` (Callers: `budgets.py:27`)
  - `update_budget(db, budget_id, planned_amount) -> Optional[models.Budget]` (Callers: `budgets.py:73`)
  - `delete_budget(db, budget_id) -> bool` (Callers: `budgets.py:83`)
- **Resource Accessed:** PostgreSQL table `budgets`.
- **Operations:** Both retrieval and mutation.
- **Transaction Operations:**
  - `db.commit()` in `create_budget` (line 63), `update_budget` (line 85), `delete_budget` (line 103).
  - `db.refresh()` in `create_budget` (line 64), `update_budget` (line 86).
- **Accepts ORM Objects?** No.
- **Returns ORM Objects?** Yes (`models.Budget`).
- **Accepts Pydantic Models?** No.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Resource/entity-oriented (`models.Budget`).

#### 3. `categorization_rule_access.py`
- **Public Production Functions:**
  - `get_rules(db) -> Sequence[models.CategorizationRule]` (Callers: `rules.py:33`)
  - `get_rule_by_id(db, rule_id) -> Optional[models.CategorizationRule]` (Callers: `rules.py:70,123`, `categorization_rule_manager.py:30,54`)
  - `get_rule_by_merchant(db, merchant) -> Optional[models.CategorizationRule]` (Callers: `transaction_access.py:241,321,388,543,650`)
  - `get_rules_lookup_dict(db) -> dict[str, UUID]` (Callers: `csv_import_manager.py:74`, `plaid_transaction_sync_manager.py:201`, `ml_categorization_manager.py:284,395`)
  - `create_rule(db, merchant, category_id) -> models.CategorizationRule` (Callers: `rules.py:52`)
  - `update_rule(db, rule_id, update_data) -> Optional[models.CategorizationRule]` (Callers: `rules.py:84`)
  - `delete_rule(db, rule_id) -> bool` (Callers: `rules.py:95`)
- **Resource Accessed:** PostgreSQL table `categorization_rules`.
- **Operations:** Both retrieval and mutation.
- **Transaction Operations:**
  - `db.commit()` in `create_rule` (line 112), `update_rule` (line 150), `delete_rule` (line 170).
  - `db.refresh()` in `create_rule` (line 113), `update_rule` (line 151).
- **Accepts ORM Objects?** No.
- **Returns ORM Objects?** Yes (`models.CategorizationRule`). `get_rules_lookup_dict` returns a pure primitive mapping `dict[str, UUID]`.
- **Accepts Pydantic Models?** No.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Resource/entity-oriented (`models.CategorizationRule`).

#### 4. `category_access.py`
- **Public Production Functions:**
  - CategoryGroup CRUD: `get_category_groups`, `get_category_group_by_id`, `create_category_group`, `update_category_group`, `delete_category_group`, `reorder_category_groups`
  - Category CRUD: `get_category_by_id`, `list_categories`, `create_category`, `update_category`, `delete_category`, `reorder_categories`
- **Production Callers:** `routers/categories.py` (all endpoints), `budget_summary_manager.py:43`, `ml_categorization_manager.py:493`, `transaction_split_manager.py:106,159`.
- **Resource Accessed:** PostgreSQL tables `category_groups` and `categories`.
- **Operations:** Both retrieval and mutation.
- **Transaction Operations:**
  - `db.commit()` in `create_category_group` (line 48), `update_category_group` (line 71), `delete_category_group` (line 85), `reorder_category_groups` (line 104), `create_category` (line 149), `update_category` (line 172), `delete_category` (line 191), `reorder_categories` (line 211).
  - `db.refresh()` on created/updated entities.
- **Accepts ORM Objects?** No.
- **Returns ORM Objects?** Yes (`models.CategoryGroup`, `models.Category`).
- **Accepts Pydantic Models?** `reorder_category_groups` accepts `schemas.ReorderCategoryGroupsRequest`; `reorder_categories` accepts `schemas.ReorderCategoriesRequest`.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** **Yes:** dynamically imports `split_access` inside `delete_category` (line 186) and calls `split_access.count_splits_by_category(db, category_id)`.
- **Observed Cohesion:** Resource/entity-oriented (category tree entities `CategoryGroup` and `Category`).

#### 5. `csv_format_access.py`
- **Public Production Functions:**
  - `get_custom_format_by_id(db, format_id) -> Optional[models.CSVFormat]` (Callers: `upload.py:68`)
  - `get_custom_format_by_name(db, name) -> Optional[models.CSVFormat]`
  - `list_custom_formats(db) -> Sequence[models.CSVFormat]` (Callers: `upload.py:92,185`)
  - `create_custom_format(db, format_data: schemas.CSVFormatCreate) -> models.CSVFormat` (Callers: `upload.py:109`)
  - `csv_format_to_mapped_config(csv_format: models.CSVFormat) -> MappedCSVFormatConfig` (Callers: `upload.py:75`)
  - `csv_format_to_match_definition(csv_format: models.CSVFormat) -> CSVFormatMatchDefinition` (Callers: `upload.py:187`)
- **Resource Accessed:** PostgreSQL table `csv_formats`.
- **Operations:** Both retrieval and mutation.
- **Transaction Operations:**
  - In `create_custom_format`: `db.commit()` at line 167; `db.rollback()` at line 169; `db.refresh()` at line 174.
- **Accepts ORM Objects?** Yes: `csv_format_to_mapped_config` and `csv_format_to_match_definition` accept `models.CSVFormat`.
- **Returns ORM Objects?** Yes (`models.CSVFormat`), and domain loader configurations (`MappedCSVFormatConfig`, `CSVFormatMatchDefinition`).
- **Accepts Pydantic Models?** Yes: `create_custom_format` accepts `schemas.CSVFormatCreate`.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Mixed: entity-oriented (`models.CSVFormat`) + parser-adapter converter (`csv_format_to_mapped_config`).

#### 6. `ml_model_access.py`
- **Public Production Functions:**
  - Storage paths & checks: `get_model_storage_dir`, `get_active_model_path`, `get_temp_candidate_path`, `artifact_exists`, `get_model_artifact_size_bytes`
  - Joblib file operations: `load_active_model`, `save_candidate_model`, `activate_candidate_model`, `cleanup_temp_candidate`
  - PostgreSQL queries & mutations: `get_ml_training_examples`, `get_model_metadata`, `increment_training_revision`, `update_model_metadata_after_training`
- **Production Callers:** `ml_categorization_manager.py` (all functions), `transaction_access.py:540,638`, `transaction_split_manager.py:122,172`.
- **Resource Accessed:** Dual resource: PostgreSQL table `ml_model_metadata` AND filesystem disk artifact directory (`backend/data/models/`).
- **Operations:** Both retrieval and mutation.
- **Transaction Operations:**
  - Database calls execute `db.flush()` only (lines 184, 197, 227). Zero `db.commit()` calls in this accessor.
  - Disk operations execute atomic file replace via `temp_path.replace(active_path)`.
- **Accepts ORM Objects?** No.
- **Returns ORM Objects?** `get_model_metadata` returns `models.MLModelMetadata`. `get_ml_training_examples` returns domain dataclasses `MLTrainingExample`.
- **Accepts Pydantic Models?** No.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Access-mechanism-oriented / composite resource (unifies PostgreSQL metadata state and atomic disk artifact lifecycle for local machine learning).

#### 7. `plaid_access.py`
- **Public Production Functions:**
  - `fetch_accounts_for_token(access_token: str) -> Sequence[PlaidAccountSnapshot]` (Callers: `plaid_account_sync_manager.py:83`, `plaid_transaction_sync_manager.py:177`)
  - `create_link_token() -> str` (Callers: `plaid.py:34`)
- **Resource Accessed:** Remote external Plaid API (`/accounts/get`, `/link/token/create`).
- **Access Mechanism:** Official Plaid Python SDK (`plaid.api.plaid_api.PlaidApi`).
- **Operations:** External API retrieval and token creation.
- **Transaction Operations:** Zero database interaction.
- **Accepts ORM Objects?** No.
- **Returns ORM Objects?** No (returns pure frozen dataclass `PlaidAccountSnapshot` or `str`).
- **Accepts Pydantic Models?** No.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Access-mechanism-oriented (encapsulates Plaid Python SDK integration).

#### 8. `plaid_item_access.py`
- **Public Production Functions:**
  - `get_plaid_item_by_id(db, item_id: UUID) -> Optional[models.PlaidItem]` (Callers: `plaid_account_sync_manager.py:68`, `plaid_transaction_sync_manager.py:162`)
  - `get_plaid_item_by_plaid_item_id(db, plaid_item_id: str) -> Optional[models.PlaidItem]` (Callers: `plaid_account_sync_manager.py:70`, `plaid_transaction_sync_manager.py:164`)
  - `stage_transactions_cursor(db, plaid_item_id: str, cursor: str) -> None` (Callers: `plaid_transaction_sync_manager.py:253`)
- **Resource Accessed:** PostgreSQL table `plaid_items`.
- **Operations:** Retrieval and staging mutation.
- **Transaction Operations:** Executes `db.add(plaid_item)` in `stage_transactions_cursor` (line 52). Zero `commit`, zero `flush`.
- **Accepts ORM Objects?** No.
- **Returns ORM Objects?** Yes (`models.PlaidItem`).
- **Accepts Pydantic Models?** No.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Resource/entity-oriented (`models.PlaidItem`).

#### 9. `plaid_transaction_access.py`
- **Public Production Functions:**
  - `fetch_transactions_page(access_token: str, cursor: Optional[str] = None) -> PlaidTransactionPage` (Callers: `plaid_transaction_sync_manager.py:213`)
- **Resource Accessed:** Remote external Plaid API endpoint `/transactions/sync`.
- **Access Mechanism:** Raw HTTP `requests.post` (intentionally bypasses official Python SDK to avoid SDK cursor validation bugs).
- **Operations:** External API pagination retrieval.
- **Transaction Operations:** Zero database interaction.
- **Accepts ORM Objects?** No.
- **Returns ORM Objects?** No (returns frozen dataclass `PlaidTransactionPage`).
- **Accepts Pydantic Models?** No.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Access-mechanism-oriented (encapsulates raw HTTP protocol and error mapping for Plaid transactions sync).

#### 10. `recurring_access.py`
- **Public Production Functions:**
  - `list_recurring_items(db, account_id) -> Sequence[models.RecurringItem]` (Callers: `recurring_transaction_manager.py:120`, `recurring.py:32`)
  - `get_recurring_item_by_id(db, item_id) -> Optional[models.RecurringItem]` (Callers: `recurring_transaction_manager.py:173`)
  - `find_recurring_item_by_identity(db, account_id, merchant, direction, cadence) -> Optional[models.RecurringItem]`
  - `stage_upsert_detected_series(db, series) -> models.RecurringItem` (Callers: `recurring_transaction_manager.py:104`)
  - `set_recurring_item_status(db, item_id, status) -> Optional[models.RecurringItem]` (Callers: `recurring_transaction_manager.py:220,239`)
  - `delete_recurring_item(db, item_id) -> bool`
  - `remove_stale_detected_items(db, active_identity_keys, account_id) -> int` (Callers: `recurring_transaction_manager.py:107`)
- **Resource Accessed:** PostgreSQL table `recurring_items`.
- **Operations:** Both retrieval and mutation.
- **Transaction Operations:** All staging/mutation operations execute `db.flush()` (lines 118, 134, 152, 167, 194). Zero `db.commit()` calls.
- **Accepts ORM Objects?** No (accepts domain dataclass `DetectedRecurringSeries` in `stage_upsert_detected_series`).
- **Returns ORM Objects?** Yes (`models.RecurringItem`).
- **Accepts Pydantic Models?** No.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Resource/entity-oriented (`models.RecurringItem`).

#### 11. `split_access.py`
- **Public Production Functions:**
  - `get_splits_for_transaction(db, transaction_id) -> Sequence[models.TransactionSplit]` (Callers: `transaction_split_manager.py:62`)
  - `get_splits_for_transactions(db, transaction_ids) -> dict[UUID, list[models.TransactionSplit]]`
  - `transaction_has_splits(db, transaction_id) -> bool` (Callers: `transaction_access.py:360,594`, `ml_categorization_manager.py:292,403`, `transaction_split_manager.py:163`)
  - `count_splits_by_category(db, category_id) -> int` (Callers: `category_access.py:187`)
  - `stage_replace_splits(db, transaction_id, allocations) -> list[models.TransactionSplit]` (Callers: `transaction_split_manager.py:124`)
  - `stage_delete_splits(db, transaction_id) -> int` (Callers: `transaction_access.py:365`, `transaction_split_manager.py:167`)
- **Resource Accessed:** PostgreSQL table `transaction_splits`.
- **Operations:** Both retrieval and mutation.
- **Transaction Operations:** Executes `db.flush()` only (lines 104, 117, 139). Zero `db.commit()` calls.
- **Accepts ORM Objects?** No.
- **Returns ORM Objects?** Yes (`models.TransactionSplit`).
- **Accepts Pydantic Models?** No.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** No.
- **Observed Cohesion:** Resource/entity-oriented (`models.TransactionSplit`).

#### 12. `transaction_access.py`
- **Public Production Functions (23 functions across 908 lines):**
  - Aggregation queries: `get_actuals_by_category`, `get_transaction_net_by_account`
  - List & filter queries: `get_recent_transactions_for_month`, `get_transactions_for_account`, `get_unmatched_inflow_transactions`, `get_unmatched_outflow_transactions`, `list_transactions`, `get_unreconciled_transactions_for_account`, `get_eligible_transactions_for_recurrence`, `count_uncategorized_transactions_by_merchant_key`
  - Record lookups: `get_transaction_by_id`, `get_transaction_by_plaid_id`, `get_account_for_transaction`
  - Staging mutations (for managers): `csv_import_transaction_exists`, `stage_csv_import_transaction`, `stage_or_update_plaid_transaction`, `stage_delete_transaction_by_plaid_id`, `mark_transactions_as_reconciled`, `apply_category_to_uncategorized_by_merchant_key`
  - Standalone CRUD mutations: `create_manual_transaction`, `update_manual_transaction`, `delete_manual_transaction`, `mark_transactions_as_transfers`, `set_transaction_cleared`
- **Resource Accessed:** PostgreSQL table `transactions`.
- **Operations:** Retrieval, staging, and standalone CRUD mutations.
- **Transaction Operations:**
  - `db.commit()` in standalone CRUD: `create_manual_transaction` (line 563), `update_manual_transaction` (line 656), `delete_manual_transaction` (line 680), `mark_transactions_as_transfers` (line 711), `set_transaction_cleared` (line 781).
  - `db.flush()` in manager-staged operations: `mark_transactions_as_reconciled` (line 817), `apply_category_to_uncategorized_by_merchant_key` (line 873).
  - Staging functions execute `db.add()` or `db.delete()` without flush or commit.
- **Accepts ORM Objects?** Yes: `get_account_for_transaction(transaction: models.Transaction) -> Optional[models.Account]`.
- **Returns ORM Objects?** Yes (`models.Transaction`).
- **Accepts Pydantic Models?** No.
- **Imports Manager Types?** No.
- **Calls Another Accessor?** **Yes:** dynamically imports `split_access`, `ml_model_access`, and `categorization_rule_access` across 7 separate function bodies.
- **Observed Cohesion:** Mixed / broad repository: covers core table persistence, historical aggregations, embedded rule evaluations, split cleanup, and ML revision tracking.

---

### 4.2 Observed Cohesion Classification

| Accessor Module | Observed Cohesion | Evidence |
|---|---|---|
| `account_access.py` | **resource/entity-oriented** | All 10 functions operate strictly on `models.Account` persistence and balance attributes. |
| `budget_access.py` | **resource/entity-oriented** | All 6 functions operate strictly on `models.Budget` persistence rows. |
| `categorization_rule_access.py` | **resource/entity-oriented** | All 7 functions operate strictly on `models.CategorizationRule` persistence rows. |
| `category_access.py` | **resource/entity-oriented** | All 12 functions operate on the category hierarchy (`CategoryGroup` and `Category`). |
| `csv_format_access.py` | **mixed** | Encapsulates both `models.CSVFormat` database CRUD and domain loader configuration mapping. |
| `ml_model_access.py` | **access-mechanism-oriented** | Encapsulates dual-storage access (PostgreSQL table + local filesystem `.joblib` model file). |
| `plaid_access.py` | **access-mechanism-oriented** | Encapsulates the official Plaid Python SDK client and protocol models. |
| `plaid_item_access.py` | **resource/entity-oriented** | All 3 functions operate strictly on `models.PlaidItem` rows in PostgreSQL. |
| `plaid_transaction_access.py` | **access-mechanism-oriented** | Encapsulates raw HTTP communication with Plaid `/transactions/sync`. |
| `recurring_access.py` | **resource/entity-oriented** | All 7 functions operate strictly on `models.RecurringItem` persistence rows. |
| `split_access.py` | **resource/entity-oriented** | All 6 functions operate strictly on `models.TransactionSplit` persistence rows. |
| `transaction_access.py` | **mixed** | Mega-accessor (908 lines) spanning transaction queries, staging, CRUD commits, and cross-accessor calls. |

---

### 4.3 Plaid Access Modules Comparison

Why do `plaid_access.py`, `plaid_transaction_access.py`, and `plaid_item_access.py` exist separately?

| Module | Underlying Resource | Access Mechanism | Concrete Reason for Separate Existence |
|---|---|---|---|
| `plaid_item_access.py` | Local PostgreSQL `plaid_items` table | SQLAlchemy ORM `Session.query(models.PlaidItem)` | Manages local database persistence of Plaid credentials, item metadata, and sync cursors. Does **not** touch external network. |
| `plaid_access.py` | Remote Plaid API (`/accounts/get`, `/link/token/create`) | Plaid Python SDK (`plaid.api.plaid_api.PlaidApi`) | Encapsulates standard SDK client initialization, link-token creation, and accounts balance retrieval. |
| `plaid_transaction_access.py` | Remote Plaid API (`/transactions/sync`) | Direct raw HTTP `requests.post` | **SDK defect isolation:** The official Plaid Python SDK exhibited cursor validation bugs on `/transactions/sync`. A dedicated raw HTTP accessor was implemented to isolate this external protocol failure without destabilizing the SDK-based account fetch. |

**Conclusion:** The Plaid access modules represent **demonstrated access-mechanism volatility**, not mechanical entity splitting.

---

### 4.4 Evolution Pattern: Entity vs. Volatility

Did the repository evolve toward:
$$	ext{one persistence model/table} \longrightarrow 	ext{one Accessor module}$$
or distinct access volatility?

**Observed Evidence:**
1. **7 out of 10 database accessors** map 1:1 to single database tables:
   - `account_access.py` &rarr; `accounts`
   - `budget_access.py` &rarr; `budgets`
   - `categorization_rule_access.py` &rarr; `categorization_rules`
   - `csv_format_access.py` &rarr; `csv_formats`
   - `plaid_item_access.py` &rarr; `plaid_items`
   - `recurring_access.py` &rarr; `recurring_items`
   - `split_access.py` &rarr; `transaction_splits`
2. **`category_access.py`** unifies two tables (`category_groups` and `categories`) because of tight parent-child relational hierarchy.
3. **`ml_model_access.py`** breaks the 1:1 table model by unifying database metadata with filesystem model artifacts.
4. **`transaction_access.py`** operates on `transactions`, but acts as a broad repository handling general queries, staging, and cross-entity side effects.
5. **External Plaid access** (`plaid_access.py` vs `plaid_transaction_access.py`) is divided strictly by external access mechanism.

**Verdict:** The relational persistence layer has largely evolved toward **one table &rarr; one Accessor module** (entity-oriented CRUD), while external API and machine learning layers reflect genuine **access-mechanism volatility**.

---

## 5. Legacy `crud/` Audit

### 5.1 Remaining Functions in `backend/crud/plaid.py`

| Legacy Function | Production Callers | Test-Only Callers | Equivalent Accessor? | Still Required in Production? | Status |
|---|---|---|---|---|---|
| `create_plaid_item` | `backend/routers/plaid.py:49` | `test_characterization_plaid_accounts.py`, `test_access_account.py`, `test_characterization_accounts.py` | None exists in `plaid_item_access.py` | **Yes** (called by `exchange_public_token`) | **live** |
| `get_plaid_item_by_plaid_item_id` | `backend/routers/plaid.py:47` | None | `plaid_item_access.get_plaid_item_by_plaid_item_id` | **Yes** (called by `exchange_public_token`, but exact duplicate exists in `plaid_item_access`) | **live** |
| `get_plaid_item_by_id` | **None** | None | `plaid_item_access.get_plaid_item_by_id` | **No** (superseded by `plaid_item_access`) | **apparently dead** |
| `update_transactions_cursor` | **None** | None | `plaid_item_access.stage_transactions_cursor` | **No** (superseded by `plaid_item_access`) | **apparently dead** |
| `get_account_by_plaid_account_id` | Called internally within `crud_plaid.sync_accounts_and_balances` (line 90) | `test_access_account.py` | `account_access.get_account_by_plaid_account_id` | Required only by internal `sync_accounts_and_balances` | **live (internal only)** |
| `list_accounts_by_item` | `backend/routers/plaid.py:60` | None | None exists in `account_access.py` | **Yes** (called by `exchange_public_token`) | **live** |
| `create_account` | **None** | None | `account_access.create_manual_account` | **No** (never called in prod or tests) | **apparently dead** |
| `sync_accounts_and_balances` | `backend/routers/plaid.py:52` | `test_characterization_plaid_accounts.py` (referenced in docstrings) | `plaid_account_sync_manager.sync_plaid_accounts` | **Yes** (called by `exchange_public_token`) | **live** |

### 5.2 Live Production Call Graph for `backend/crud/plaid.py`

In current production code, `backend/crud/plaid.py` is invoked exclusively by a single route handler:

```text
HTTP POST /plaid/exchange_public_token (backend/routers/plaid.py)
        │
        ├── line 47: crud_plaid.get_plaid_item_by_plaid_item_id(db, plaid_item_id)
        │
        ├── line 49: crud_plaid.create_plaid_item(db=db, plaid_item_id=plaid_item_id, access_token=access_token)
        │
        ├── line 52: crud_plaid.sync_accounts_and_balances(db=db, client=client, access_token=access_token, item_id=db_item.id)
        │       │
        │       └── line 90 (internal): crud_plaid.get_account_by_plaid_account_id(db, data["account_id"])
        │       └── line 120: db.flush()
        │
        ├── line 59: db.commit()  <-- Direct commit inside presentation router!
        │
        └── line 60: crud_plaid.list_accounts_by_item(db, db_item.id)
```

### 5.3 Conclusions
- **`backend/crud/` is NOT dead code.** It hosts 4 live production functions executing during bank account linking.
- **Duplicate implementations exist:** `get_plaid_item_by_plaid_item_id` and `sync_accounts_and_balances` duplicate capabilities that now exist in `plaid_item_access` and `plaid_account_sync_manager`.
- Three functions (`get_plaid_item_by_id`, `update_transactions_cursor`, `create_account`) are **apparently dead** in production.
---

## 6. CSV / Upload Workflow Deep Dive

### 6.1 Independent Traces for Upload Endpoints

#### 1. `POST /upload/inspect`
```text
HTTP Request (file: UploadFile)
  ↓
backend/routers/upload.py:inspect_csv
  ├── 1. Read bytes: await _read_upload(file)
  ├── 2. Decode text: raw.decode("utf-8-sig") (raises 422 if invalid or empty)
  ├── 3. Parse headers: reader = csv.reader(io.StringIO(text)); next(reader)
  ├── 4. Collect sample rows: up to 3 non-empty rows as positional lists of strings
  ├── 5. Query custom formats: csv_format_access.list_custom_formats(db)
  ├── 6. Convert custom formats: csv_format_access.csv_format_to_match_definition(cf)
  ├── 7. Combine candidates: BUILTIN_FORMAT_MATCHES + custom_candidates
  ├── 8. Detect format: bank_statement_loader.detect_csv_format(headers, candidates)
  └── 9. Return schemas.CSVInspectResponse(headers, sample_rows, status, detected_format, matches)
```
*Note:* This entire workflow is orchestrated directly inside `backend/routers/upload.py`. No Manager is called.

#### 2. `GET /upload/formats`
```text
HTTP Request
  ↓
backend/routers/upload.py:list_formats
  └── csv_format_access.list_custom_formats(db)  --> PostgreSQL
  └── Return list[schemas.CSVFormatRead]
```
*Note:* Direct Router -> Accessor CRUD.

#### 3. `POST /upload/formats`
```text
HTTP Request (payload: schemas.CSVFormatCreate)
  ↓
backend/routers/upload.py:create_format
  ├── csv_format_access.create_custom_format(db=db, format_data=payload)
  │     ├── validate configuration uniqueness & name conflicts
  │     ├── models.CSVFormat(...) -> db.add() -> db.commit() -> db.refresh()
  │     └── on conflict: db.rollback() -> raise CSVFormatNameConflictError
  └── Return schemas.CSVFormatRead
```
*Note:* Direct Router -> Accessor CRUD with internal Accessor commit.

#### 4. `POST /upload/preview`
```text
HTTP Request (file: UploadFile, account_id: UUID, format: str)
  ↓
backend/routers/upload.py:preview_csv
  ├── 1. Check account existence: account_access.get_account_by_id(db, account_id) (raises 404 if missing)
  ├── 2. Resolve loader: _resolve_statement_loader(db, account_id, format)
  │        ├── if format in LOADER_REGISTRY: get_loader(format, account_id)
  │        └── else format UUID:
  │              csv_format_access.get_custom_format_by_id(db, format_uuid) (raises 404 if missing)
  │              config = csv_format_access.csv_format_to_mapped_config(custom_format)
  │              return MappedStatementLoader(account_id, config)
  ├── 3. Read bytes: await _read_upload(file)
  ├── 4. Decode text: raw.decode("utf-8-sig") with latin-1 fallback
  ├── 5. Row-by-row parse loop:
  │        reader = csv.DictReader(io.StringIO(text))
  │        for i, raw_row in enumerate(reader, start=1):
  │            try:
  │                normalized = loader.normalize_row(raw_row)
  │                txn = loader.transform_row(normalized)
  │                rows.append(schemas.CSVTransactionRow(...))
  │            except Exception as exc:
  │                rows.append(schemas.CSVTransactionRow(row_number=i, parse_error=str(exc)))
  └── 6. Return schemas.CSVPreviewResponse(rows, total_rows, valid_rows, error_rows)
```
*Note:* This preview orchestration lives entirely in `backend/routers/upload.py`. It does **not** call `CSVImportManager` or `loader.load_records_tolerant`.

#### 5. `POST /upload/confirm`
```text
HTTP Request (file: UploadFile, account_id: UUID, format: str)
  ↓
backend/routers/upload.py:confirm_csv
  ├── 1. Router checks account: account_access.get_account_by_id(db, account_id) (raises 404)
  ├── 2. Router resolves loader: _resolve_statement_loader(db, account_id, format)
  ├── 3. Router reads bytes: await _read_upload(file)
  ├── 4. Router invokes Manager: csv_import_manager.confirm_csv_import(db, raw, loader)
  │        ├── 4a. Manager re-checks account: account_access.get_account_by_id(db, loader.account_id)
  │        ├── 4b. Manager parses bytes: loader.load_records_tolerant(raw_bytes)
  │        ├── 4c. Manager fetches rules dict: categorization_rule_access.get_rules_lookup_dict(db)
  │        ├── 4d. Loop parsed.valid_transactions:
  │        │        ├── Duplicate check: transaction_access.csv_import_transaction_exists(...)
  │        │        ├── if duplicate: skipped += 1
  │        │        └── else:
  │        │              merchant = domain.merchant_normalization.normalize_merchant(txn.description)
  │        │              transaction_access.stage_csv_import_transaction(..., merchant=merchant, rules_lookup=rules_lookup)
  │        │              imported += 1
  │        ├── 4e. Commit: db.commit()
  │        └── 4f. Return CSVImportSummary(imported, skipped, errors)
  └── 5. Router serializes and returns schemas.CSVImportResult
```

---

### 6.2 Precise Responsibilities for `POST /upload/confirm`

| # | Question | Exact Source-Code Answer | Source Location |
|---|---|---|---|
| 1 | Where is the account existence check performed? | Performed in **both** the Router and the Manager. | `routers/upload.py:305` and `managers/csv_import_manager.py:63` |
| 2 | Is it performed more than once? | **YES. Exactly twice.** First in the Router handler, then immediately again in the Manager. | `upload.py:305` -> `get_account_by_id`; `csv_import_manager.py:63` -> `get_account_by_id` |
| 3 | Where is the format identifier resolved? | Inside `backend/routers/upload.py` helper `_resolve_statement_loader`. | `backend/routers/upload.py:48-76` |
| 4 | Who queries `CSVFormat`? | Helper `_resolve_statement_loader` in `backend/routers/upload.py`. | `backend/routers/upload.py:68` calls `csv_format_access.get_custom_format_by_id` |
| 5 | Who constructs `MappedCSVFormatConfig`? | `csv_format_access.csv_format_to_mapped_config`, invoked by router helper `_resolve_statement_loader`. | `backend/routers/upload.py:75` and `backend/access/csv_format_access.py:179` |
| 6 | Who constructs `MappedStatementLoader`? | Router helper `_resolve_statement_loader` in `backend/routers/upload.py`. | `backend/routers/upload.py:76` |
| 7 | Who reads the uploaded bytes? | The Router handler `confirm_csv` via helper `_read_upload`. | `backend/routers/upload.py:42,314` |
| 8 | Who invokes the parser? | `CSVImportManager.confirm_csv_import`. | `backend/managers/csv_import_manager.py:69` (`loader.load_records_tolerant(raw_bytes)`) |
| 9 | Who performs duplicate lookup? | `CSVImportManager.confirm_csv_import` calls `transaction_access.csv_import_transaction_exists`. | `backend/managers/csv_import_manager.py:83` |
| 10 | Who stages transactions? | `CSVImportManager.confirm_csv_import` calls `transaction_access.stage_csv_import_transaction`. | `backend/managers/csv_import_manager.py:94` |
| 11 | Who applies merchant normalization? | `CSVImportManager.confirm_csv_import` calls `domain.merchant_normalization.normalize_merchant`. | `backend/managers/csv_import_manager.py:93` |
| 12 | Who applies categorization rules? | Orchestrated by `CSVImportManager` (fetching `rules_lookup` dict), but the **matching logic is embedded inside `transaction_access.stage_csv_import_transaction`**. | `csv_import_manager.py:74` and `access/transaction_access.py:234-238` |
| 13 | Who commits? | `CSVImportManager.confirm_csv_import` calls `db.commit()`. | `backend/managers/csv_import_manager.py:113` |
| 14 | Which responsibilities live in Router? | 1. Account existence validation (1st check)<br>2. Format identifier resolution<br>3. Custom format DB lookup (`csv_format_access`)<br>4. Construction of `MappedStatementLoader`<br>5. Upload byte extraction (`_read_upload`)<br>6. HTTP exception mapping (`CSVImportAccountNotFoundError` &rarr; 404, `CSVImportParseError` &rarr; 422)<br>7. Pydantic response model construction (`schemas.CSVImportResult`) | `backend/routers/upload.py:48-76,305,312,314,323,328,333` |
| 15 | Which live in Manager? | 1. Account existence validation (2nd redundant check)<br>2. Parser invocation (`loader.load_records_tolerant`)<br>3. Exception translation (`ValueError` &rarr; `CSVImportParseError`)<br>4. Rules dictionary acquisition (`categorization_rule_access.get_rules_lookup_dict`)<br>5. Loop coordination over parsed rows<br>6. Calling duplicate existence check<br>7. Invoking merchant normalization<br>8. Invoking transaction staging<br>9. Per-row error aggregation<br>10. Batch database commit (`db.commit()`)<br>11. Result dataclass construction (`CSVImportSummary`) | `backend/managers/csv_import_manager.py:62-119` |
| 16 | Which live in Accessors? | 1. `account_access.get_account_by_id`: ORM query for `models.Account`<br>2. `csv_format_access.get_custom_format_by_id`: ORM query for `models.CSVFormat`<br>3. `csv_format_access.csv_format_to_mapped_config`: ORM entity &rarr; domain config dataclass<br>4. `categorization_rule_access.get_rules_lookup_dict`: query rules and build canonical key map<br>5. `transaction_access.csv_import_transaction_exists`: 4-tuple duplicate query<br>6. `transaction_access.stage_csv_import_transaction`: inline rule match, create `models.Transaction`, `db.add()` | `backend/access/account_access.py`, `backend/access/csv_format_access.py`, `backend/access/categorization_rule_access.py`, `backend/access/transaction_access.py` |
| 17 | Which live in parser boundary? | 1. File byte decoding with encoding fallbacks<br>2. Header extraction and normalization<br>3. Row normalization and field transformation<br>4. Date parsing across bank-specific format masks<br>5. Sign convention normalization<br>6. Tolerant error collection (`TolerantParseResult`) | `backend/bank_statement_loader.py` (`BankStatementLoader`, `MappedStatementLoader`, `USAALoader`, `DiscoverLoader`) |

---

## 7. Engine / Domain Audit

An exhaustive inspection of all 11 modules in `backend/domain/` establishes their operational contracts and infrastructure isolation.

### 7.1 Infrastructure Contamination Check

Every file in `backend/domain/` was tested against imports, parameters, and references to:
- `FastAPI`, `HTTPException`
- Pydantic schema types
- SQLAlchemy `Session`, declarative models, `models.*`
- `access.*`, `managers.*`, `crud.*`
- `requests`, Plaid SDK
- Filesystem paths, `open()`, `os.environ`, `getenv`

**Result:** **ZERO infrastructure contamination.**
All 11 modules in `backend/domain/` are 100% pure Python. They operate exclusively on standard library primitives (`Decimal`, `date`, `datetime`, `UUID`, `str`, `int`, `Sequence`, `Optional`) and domain-defined dataclasses. (Module `ml_categorization.py` imports `numpy` and `scikit-learn`, which are pure computational libraries).

---

### 7.2 Module Profiles

| Module | Public Functions / Classes | Callers | Inputs / Outputs | Business Rules / Calculations | Classification |
|---|---|---|---|---|---|
| `account_reconciliation.py` | `ReconciliationTx`, `ReconciliationCalculation`, `calculate_cleared_balance`, `calculate_reconciliation_difference`, `is_reconciliation_balanced`, `compute_reconciliation_state` | `account_reconciliation_manager.py:26,88` | Inputs: prior balance, statement date, ending balance, `list[ReconciliationTx]`. Output: `ReconciliationCalculation`. | Cleared balance calculation: $prior + \sum 	ext{cleared outflows} + \sum 	ext{cleared inflows}$. Difference: $ending - cleared$. Balanced predicate: $|difference| == 0.00$. | **algorithm/policy** |
| `accounts.py` | `calculate_depository_balance` | `account_summary_manager.py:21,51` | Inputs: `starting_balance: Decimal`, `net_transactions: Decimal`. Output: `Decimal`. | Single arithmetic formula: $starting\_balance - net\_transactions$. Contains no branching, heuristics, or loops. | **small pure utility** |
| `budgeting.py` | `CategoryBudgetInput`, `GroupBudgetInput`, `CategoryBudgetResult`, `GroupBudgetResult`, `BudgetSummaryResult`, `calculate_actual`, `calculate_remaining`, `calculate_is_over_budget`, `calculate_to_be_assigned`, `calculate_category_summary`, `calculate_group_summary`, `calculate_budget_summary` | `budget_summary_manager.py:22,69`, `dashboard_summary_manager.py:23` | Inputs: hierarchical `list[GroupBudgetInput]`. Output: hierarchical `BudgetSummaryResult`. | Zero-based budgeting invariants: display sign inversion on income ($	ext{actual} = -1 	imes 	ext{raw}$), remaining calculation ($	ext{planned} - 	ext{actual}$ for expense, $	ext{actual} - 	ext{planned}$ for income), over-budget thresholds, $	ext{to\_be\_assigned} = 	ext{income planned} - 	ext{expense planned}$. | **algorithm/policy** |
| `categorization_rules.py` | `clean_merchant_key`, `is_eligible_for_rule`, `match_merchant_rule` | `clean_merchant_key` called by: `csv_import_manager`, `plaid_transaction_sync_manager`, `recurring_transaction_manager`, `ml_categorization_manager`, `transaction_access`. (`is_eligible_for_rule` and `match_merchant_rule` have **zero** production callers). | Inputs: `merchant: Optional[str]`. Output: `Optional[str]`. | Strips whitespace, converts to uppercase, removes punctuation (`[.,'"#\-_/\\]`). | **small pure utility** |
| `credit_cards.py` | `CreditCardTransaction`, `CreditCardState`, `calculate_credit_card_state` | `credit_card_summary_manager.py:29,91` | Inputs: `starting_balance: Optional[Decimal]`, `transactions: Sequence[CreditCardTransaction]`, `period_start: date`, `period_end: date`. Output: `CreditCardState`. | All-time cumulative balance owed formula: $starting\_balance + \sum 	ext{amount}$. Monthly charges: sum of positive non-transfer transactions in period. Monthly payments: absolute sum of negative transactions in period. Overpayment handling. | **algorithm/policy** |
| `dates.py` | `determine_month_range` | `budget_summary_manager:24`, `credit_card_summary_manager:31`, `dashboard_summary_manager:24` | Inputs: `month_date: date`. Output: `tuple[date, date]`. | Half-open calendar month interval $[start, end)$ with December-to-January year rollover handling. | **small pure utility** |
| `merchant_normalization.py` | `clean_casing`, `normalize_merchant` | `csv_import_manager:19`, `plaid_transaction_sync_manager:24`, `transaction_access:10,185,526,629` | Inputs: `raw_description: str`, `provider_merchant: Optional[str]`. Output: `str`. | Regular expression heuristics: strips POS prefixes (`SQ *`, `TST*`, `PAYPAL *`, `SP *`, etc.), removes store/terminal IDs (`#\d+`, `STORE \d+`), strips US state abbreviations, title-cases clean tokens, falls back to raw description. | **algorithm/policy** |
| `ml_categorization.py` | `MLEvaluationMetrics`, `MLSuggestion`, `MerchantFrequencyBaseline`, `build_feature_text`, `create_ml_pipeline`, `evaluate_classifier`, `should_activate_candidate`, `predict_suggestion` | `ml_categorization_manager.py` | Inputs: feature strings, labels, candidate pipelines. Output: metrics, predictions, activation boolean. | Character n-gram TF-IDF vectorization (3-5), balanced class weight Logistic Regression, stratified train/test split, frequency baseline evaluation, safety gate thresholds (accuracy $\ge$ baseline, macro F1 $\ge 0.50$, coverage $\ge 0.80$, regression degradation gate $\le 5\%$). | **algorithm/policy** |
| `reconciliation.py` | `ReconciliationTransaction`, `MatchedTransferCandidate`, `detect_transfer_candidates` | `transfer_reconciliation_manager.py:29,126` | Inputs: `inflows: Sequence[ReconciliationTransaction]`, `outflows: Sequence[ReconciliationTransaction]`. Output: `list[MatchedTransferCandidate]`. | Inter-account transfer pairing heuristic: pairs unmatched inflow (`< 0`) and outflow (`> 0`) if $|amount_{	ext{inflow}}| == amount_{	ext{outflow}}$, accounts differ, and $|date_{	ext{outflow}} - date_{	ext{inflow}}| \le 2	ext{ days}$. Greedy single-pair allocation. | **algorithm/policy** |
| `recurring_transactions.py` | `RecurrenceTransactionInput`, `DetectedRecurringSeries`, `detect_cadence`, `evaluate_amount_stability`, `detect_recurring_series`, date projection helpers | `recurring_transaction_manager.py:23,90` | Inputs: `list[RecurrenceTransactionInput]`. Output: `list[DetectedRecurringSeries]`. | Cadence interval detection (weekly: 6–8 days; biweekly: 13–15 days; monthly: 27–32 days; annual: 360–370 days); minimum 3 occurrences for weekly/biweekly, minimum 2 for monthly/annual; amount stability variance filtering ($\le 20\%$ deviation); next expected date calculation. | **algorithm/policy** |
| `transaction_splits.py` | `SplitAllocationInput`, `SplitValidationResult`, `calculate_remaining_amount`, `validate_split_allocations` | `transaction_split_manager.py:26,97` | Inputs: `parent_amount: Decimal`, `allocations: Sequence[SplitAllocationInput]`. Output: `SplitValidationResult`. | Accounting invariants: minimum 2 split lines; non-zero line amounts; allocation signs must match parent sign (cannot mix inflows and outflows); sum of allocation amounts must equal parent amount exactly ($\sum amounts == parent$). | **algorithm/policy** |

---

## 8. DTO / Result-Type Audit

Every custom class defined inside `backend/managers/` was audited against corresponding ORM models and Pydantic schemas.

### 8.1 Manager-Defined DTOs Inventory

| Manager Type | Defined In | ORM Equivalent | Pydantic Equivalent | Unique Business Semantics? | Mostly Mapping Boundary? |
|---|---|---|---|---|---|
| `CreditCardMonthlyTransactionItem` | `credit_card_summary_manager.py:34` | `models.Transaction` | `schemas.CreditCardTransactionRead` | No. Fields (`transaction_id, description, amount, date, is_transfer, category_id`) are a direct subset of Transaction. | **Mostly mapping boundary** |
| `CreditCardAccountSummaryItem` | `credit_card_summary_manager.py:44` | None (composite) | `schemas.CreditCardAccountSummary` | Partial: bundles account identity, calculated `CreditCardState`, and monthly transaction items. | **Mostly mapping boundary** |
| `CreditCardSummaryResult` | `credit_card_summary_manager.py:52` | None | `schemas.CreditCardSummaryResponse` | No: simple tuple wrapper `(cards: Sequence[CreditCardAccountSummaryItem])`. | **Mostly mapping boundary** |
| `CSVImportSummary` | `csv_import_manager.py:22` | None | `schemas.CSVImportResult` | **Yes:** represents atomic batch import execution statistics: `(imported: int, skipped: int, errors: tuple[str, ...])`. | Boundary protection |
| `DashboardAccountItem` | `dashboard_summary_manager.py:30` | `models.Account` | `schemas.DashboardAccountSummary` / `schemas.AccountRead` | No. 9 fields (`account_id, name, type, subtype, current_balance, available_balance, currency, balance_last_updated, is_active`) duplicate `models.Account`. | **Mostly mapping boundary** |
| `DashboardTransactionAccountItem` | `dashboard_summary_manager.py:43` | `models.Account` | `schemas.AccountRead` | No. 12 fields duplicate `models.Account`. | **Mostly mapping boundary** |
| `DashboardRecentTransactionItem` | `dashboard_summary_manager.py:59` | `models.Transaction` | `schemas.TransactionDetailRead` | No. 10 fields duplicate `models.Transaction` plus nested account reference. | **Mostly mapping boundary** |
| `DashboardSummaryResult` | `dashboard_summary_manager.py:73` | None | `schemas.DashboardSummaryResponse` | Partial: composite structure binding `BudgetSummaryResult`, accounts, scalar `total_balance`, and recent transactions. | Composite application result |
| `PlaidAccountSyncResult` | `plaid_account_sync_manager.py:18` | None | `dict` / `schemas.PlaidSyncRequest` | No: single field `accounts_updated: int`. | Minimal wrapper |
| `PlaidTransactionSyncResult` | `plaid_transaction_sync_manager.py:30` | None | `dict` | **Yes:** represents multi-stage sync statistics: `(message, added, modified, removed, next_cursor, warnings)`. | Boundary protection |
| `TransferInflowSideItem` | `transfer_reconciliation_manager.py:33` | `models.Transaction` | `schemas.TransferInflowSideRead` | No. 6 fields duplicate Transaction. | **Mostly mapping boundary** |
| `TransferOutflowAccountItem` | `transfer_reconciliation_manager.py:43` | `models.Account` | `schemas.AccountRead` | No. 12 fields duplicate Account. | **Mostly mapping boundary** |
| `TransferOutflowSideItem` | `transfer_reconciliation_manager.py:60` | `models.Transaction` | `schemas.TransactionDetailRead` | No. 11 fields duplicate Transaction. | **Mostly mapping boundary** |
| `TransferCandidateItem` | `transfer_reconciliation_manager.py:75` | None | `schemas.TransferCandidateRead` | Partial: pairs inflow and outflow transaction sides with resolved account names. | Composite application result |

### 8.2 Boundary Evaluation of Summary DTOs

In `DashboardSummaryManager`, `CreditCardSummaryManager`, and `TransferReconciliationManager`, the Manager reads ORM models from Accessors, maps them into Manager-defined `@dataclass(frozen=True)` types, and passes them to the Router. The Router immediately unpacks those exact fields into Pydantic response models:

```text
ORM model (models.Account)
        ↓
Manager DTO (DashboardAccountItem)      <-- Field-for-field intermediate clone
        ↓
Pydantic Schema (DashboardAccountSummary)
```

**Finding:** These types do not encapsulate independent business invariants. They act as **near field-for-field intermediate DTOs inserted solely between ORM and Pydantic**. In contrast, `AccountSummaryManager` bypasses this layer and returns Pydantic `schemas.AccountRead` directly, while `BudgetSummaryManager` returns domain-defined calculation results (`BudgetSummaryResult`).
---

## 9. Presentation-Layer Leakage Audit

FastAPI routers were inspected across all 11 files in `backend/routers/`. Direct `Router -> Accessor` CRUD endpoints (e.g. `budgets.py`, `categories.py`, `rules.py`) are classified as simple transport adapters and are **not** considered violations.

The following table records all routes exhibiting architectural leakage (orchestration sequencing, business logic, external SDK calls, direct database transactions, or resource construction):

### 9.1 Flagged Presentation Routes

| Router File / Route | Flagged Operations | Actual Responsibility / Behavior |
|---|---|---|
| `backend/routers/plaid.py`<br>`POST /plaid/exchange_public_token` | `crud_plaid.*`<br>`db.commit()`<br>Plaid SDK calls | **Full application workflow orchestration inside presentation layer:**<br>1. Directly instantiates Plaid SDK client.<br>2. Exchanges public token for access token.<br>3. Calls legacy `crud_plaid.get_plaid_item_by_plaid_item_id`.<br>4. Calls legacy `crud_plaid.create_plaid_item`.<br>5. Calls legacy `crud_plaid.sync_accounts_and_balances`.<br>6. **Executes `db.commit()` directly inside route handler** (line 59).<br>7. Calls legacy `crud_plaid.list_accounts_by_item`. |
| `backend/routers/upload.py`<br>`_resolve_statement_loader` | Resource construction<br>Accessor invocation | **Dynamic parser selection & construction logic in router helper:**<br>1. Inspects format identifier string.<br>2. Queries LOADER_REGISTRY.<br>3. Queries `csv_format_access.get_custom_format_by_id`.<br>4. Converts ORM model to `MappedCSVFormatConfig`.<br>5. Instantiates concrete `MappedStatementLoader` instance. |
| `backend/routers/upload.py`<br>`POST /upload/inspect` | File decoding<br>CSV sniffing<br>Domain detection | **Ingestion candidate aggregation & sniffing in router:**<br>1. Reads bytes, decodes UTF-8 with BOM.<br>2. Iterates CSV reader, extracts header and up to 3 sample rows.<br>3. Queries `csv_format_access.list_custom_formats(db)`.<br>4. Assembles candidate list and invokes `detect_csv_format`. |
| `backend/routers/upload.py`<br>`POST /upload/preview` | File parsing loop<br>Error capture | **Complete CSV preview parsing loop in router:**<br>1. Validates account existence.<br>2. Resolves loader.<br>3. Reads and decodes file bytes.<br>4. Runs row-by-row parse loop via `csv.DictReader`.<br>5. Calls `loader.normalize_row` and `loader.transform_row`.<br>6. Isolates per-row exceptions into `schemas.CSVTransactionRow`.<br>*(Bypasses `CSVImportManager` completely).* |
| `backend/routers/upload.py`<br>`POST /upload/confirm` | Redundant query | **Redundant persistence query:**<br>Executes `account_access.get_account_by_id` at line 305 before invoking `csv_import_manager.confirm_csv_import`, which immediately re-executes the exact same query at line 63. |
| `backend/routers/summaries.py`<br>`GET /summary/dashboard` | Verbose re-mapping | **Redundant intermediate DTO unpack:**<br>Receives `DashboardSummaryResult` from manager, unpacks its 4 member dataclasses field-for-field, and reconstructs `schemas.DashboardSummaryResponse`. |
| `backend/routers/credit_cards.py`<br>`GET /credit-cards/summary` | Verbose re-mapping | **Redundant intermediate DTO unpack:**<br>Receives `CreditCardSummaryResult` from manager, unpacks 3 member dataclasses field-for-field, and reconstructs `schemas.CreditCardSummaryResponse`. |

---

## 10. Commit / Transaction Boundary Audit

Every occurrence of `.commit(`, `.flush(`, `.rollback(`, and `.refresh(` across production backend Python was verified.

### 10.1 Production Database Transaction Operations Inventory

| File Path / Symbol | Line # | Operation | Workflow | Why / When It Occurs |
|---|---|---|---|---|
| `backend/routers/plaid.py:exchange_public_token` | 59 | `commit()` | Plaid Public Token Exchange | Direct transaction commit inside route handler after legacy `sync_accounts_and_balances`. |
| `backend/managers/account_reconciliation_manager.py:complete_reconciliation` | 183 | `commit()` | Account Reconciliation Completion | Commits transaction locking participating cleared transactions and updating account metadata. |
| `backend/managers/account_reconciliation_manager.py:complete_reconciliation` | 185 | `rollback()` | Account Reconciliation Completion | Rolls back transaction on unexpected failure during completion. |
| `backend/managers/categorization_rule_manager.py:apply_rule_to_uncategorized` | 68 | `commit()` | Retroactive Rule Apply | Commits batch update of uncategorized transactions to target category. |
| `backend/managers/categorization_rule_manager.py:apply_rule_to_uncategorized` | 71 | `rollback()` | Retroactive Rule Apply | Rolls back batch update on failure. |
| `backend/managers/csv_import_manager.py:confirm_csv_import` | 113 | `commit()` | CSV Statement Import | Single batch commit of all non-duplicate imported transactions. |
| `backend/managers/ml_categorization_manager.py:retrain_model` | 120 | `commit()` | ML Model Training (Data Insufficient) | Commits updated status message when training data is below minimum threshold. |
| `backend/managers/ml_categorization_manager.py:retrain_model` | 205 | `commit()` | ML Model Training (Gate Failed) | Commits updated status message when candidate fails safety gates. |
| `backend/managers/ml_categorization_manager.py:retrain_model` | 231 | `commit()` | ML Model Training (Activated) | Commits updated model metadata after atomic artifact activation. |
| `backend/managers/ml_categorization_manager.py:retrain_model` | 241 | `rollback()` | ML Model Training | Rolls back session on unexpected exception during training. |
| `backend/managers/ml_categorization_manager.py:accept_suggestion` | 502 | `commit()` | Accept ML Suggestion | Commits transaction category update and training revision increment. |
| `backend/managers/ml_categorization_manager.py:accept_suggestion` | 503 | `refresh()` | Accept ML Suggestion | Refreshes mutated transaction instance. |
| `backend/managers/plaid_account_sync_manager.py:sync_plaid_accounts` | 107 | `flush()` | Plaid Account Balance Sync | Flushes staged account upserts before commit. |
| `backend/managers/plaid_account_sync_manager.py:sync_plaid_accounts` | 108 | `commit()` | Plaid Account Balance Sync | Commits refreshed account balances. |
| `backend/managers/plaid_transaction_sync_manager.py:_process_upsert_event` | 123 | `commit()` | Plaid Transaction Sync (Added/Modified) | **Per-row commit:** commits after each individual added or modified transaction event. |
| `backend/managers/plaid_transaction_sync_manager.py:_process_upsert_event` | 126 | `commit()` | Plaid Transaction Sync (Conflict) | Commits after conflict handling when reconciled transaction cannot be updated. |
| `backend/managers/plaid_transaction_sync_manager.py:sync_plaid_transactions` | 199 | `flush()` | Plaid Transaction Sync (Pre-Sync Balance) | Flushes account balance updates staged prior to pagination loop. |
| `backend/managers/plaid_transaction_sync_manager.py:sync_plaid_transactions` | 250 | `commit()` | Plaid Transaction Sync (Removed) | **Per-row commit:** commits after each individual deleted transaction event. |
| `backend/managers/plaid_transaction_sync_manager.py:sync_plaid_transactions` | 259 | `commit()` | Plaid Transaction Sync (Final Cursor) | Commits final cursor update staged in `plaid_items`. |
| `backend/managers/plaid_transaction_sync_manager.py:sync_plaid_transactions` | 261 | `commit()` | Plaid Transaction Sync (Compatibility) | **Redundant second final commit:** compatibility artifact preserved from legacy crud. |
| `backend/managers/recurring_transaction_manager.py:detect_and_sync_recurring_items` | 114 | `commit()` | Recurring Series Detection | Commits batch upsert of detected recurring series and stale series cleanup. |
| `backend/managers/recurring_transaction_manager.py:detect_and_sync_recurring_items` | 116 | `rollback()` | Recurring Series Detection | Rolls back session on detection sync failure. |
| `backend/managers/recurring_transaction_manager.py:confirm_recurring_item` | 223 | `commit()` | Confirm Recurring Item | Commits status update to 'confirmed'. |
| `backend/managers/recurring_transaction_manager.py:confirm_recurring_item` | 226 | `rollback()` | Confirm Recurring Item | Rolls back on status update failure. |
| `backend/managers/recurring_transaction_manager.py:dismiss_recurring_item` | 242 | `commit()` | Dismiss Recurring Item | Commits status update to 'dismissed'. |
| `backend/managers/recurring_transaction_manager.py:dismiss_recurring_item` | 245 | `rollback()` | Dismiss Recurring Item | Rolls back on status update failure. |
| `backend/managers/transaction_split_manager.py:create_or_replace_split` | 131 | `commit()` | Split Transaction Replacement | Commits cleared parent category, bumped ML revision, and replaced split lines. |
| `backend/managers/transaction_split_manager.py:create_or_replace_split` | 132 | `refresh()` | Split Transaction Replacement | Refreshes parent transaction instance. |
| `backend/managers/transaction_split_manager.py:create_or_replace_split` | 135 | `rollback()` | Split Transaction Replacement | Rolls back on split validation or database failure. |
| `backend/managers/transaction_split_manager.py:unsplit_transaction` | 179 | `commit()` | Unsplit Transaction | Commits deleted split lines, restored parent category, and bumped ML revision. |
| `backend/managers/transaction_split_manager.py:unsplit_transaction` | 180 | `refresh()` | Unsplit Transaction | Refreshes parent transaction instance. |
| `backend/managers/transaction_split_manager.py:unsplit_transaction` | 183 | `rollback()` | Unsplit Transaction | Rolls back on unsplit failure. |
| `backend/access/account_access.py:create_manual_account` | 165 | `commit()` | Account Standalone CRUD | Commits new manual account. |
| `backend/access/account_access.py:create_manual_account` | 166 | `refresh()` | Account Standalone CRUD | Refreshes new account instance. |
| `backend/access/account_access.py:update_manual_account` | 199 | `commit()` | Account Standalone CRUD | Commits updated account. |
| `backend/access/account_access.py:update_manual_account` | 200 | `refresh()` | Account Standalone CRUD | Refreshes updated account instance. |
| `backend/access/account_access.py:delete_account` | 218 | `commit()` | Account Standalone CRUD | Commits deleted account. |
| `backend/access/account_access.py:update_account_reconciliation_metadata` | 237 | `flush()` | Account Reconciliation | Flushes updated reconciliation watermark (managed by `AccountReconciliationManager`). |
| `backend/access/budget_access.py:create_budget` | 63 | `commit()` | Budget Standalone CRUD | Commits new monthly budget allocation. |
| `backend/access/budget_access.py:create_budget` | 64 | `refresh()` | Budget Standalone CRUD | Refreshes new budget instance. |
| `backend/access/budget_access.py:update_budget` | 85 | `commit()` | Budget Standalone CRUD | Commits updated planned amount. |
| `backend/access/budget_access.py:update_budget` | 86 | `refresh()` | Budget Standalone CRUD | Refreshes updated budget instance. |
| `backend/access/budget_access.py:delete_budget` | 103 | `commit()` | Budget Standalone CRUD | Commits deleted budget. |
| `backend/access/categorization_rule_access.py:create_rule` | 112 | `commit()` | Rule Standalone CRUD | Commits new categorization rule. |
| `backend/access/categorization_rule_access.py:create_rule` | 113 | `refresh()` | Rule Standalone CRUD | Refreshes new rule instance. |
| `backend/access/categorization_rule_access.py:update_rule` | 150 | `commit()` | Rule Standalone CRUD | Commits updated rule. |
| `backend/access/categorization_rule_access.py:update_rule` | 151 | `refresh()` | Rule Standalone CRUD | Refreshes updated rule instance. |
| `backend/access/categorization_rule_access.py:delete_rule` | 170 | `commit()` | Rule Standalone CRUD | Commits deleted rule. |
| `backend/access/category_access.py:create_category_group` | 48 | `commit()` | Category Group Standalone CRUD | Commits new category group. |
| `backend/access/category_access.py:update_category_group` | 71 | `commit()` | Category Group Standalone CRUD | Commits updated category group. |
| `backend/access/category_access.py:delete_category_group` | 85 | `commit()` | Category Group Standalone CRUD | Commits deleted category group. |
| `backend/access/category_access.py:reorder_category_groups` | 104 | `commit()` | Category Group Standalone CRUD | Commits reordered groups. |
| `backend/access/category_access.py:create_category` | 149 | `commit()` | Category Standalone CRUD | Commits new category. |
| `backend/access/category_access.py:update_category` | 172 | `commit()` | Category Standalone CRUD | Commits updated category. |
| `backend/access/category_access.py:delete_category` | 191 | `commit()` | Category Standalone CRUD | Commits deleted category. |
| `backend/access/category_access.py:reorder_categories` | 211 | `commit()` | Category Standalone CRUD | Commits reordered categories. |
| `backend/access/csv_format_access.py:create_custom_format` | 167 | `commit()` | Custom Format Standalone CRUD | Commits new custom format. |
| `backend/access/csv_format_access.py:create_custom_format` | 169 | `rollback()` | Custom Format Standalone CRUD | Rolls back on configuration conflict. |
| `backend/access/csv_format_access.py:create_custom_format` | 174 | `refresh()` | Custom Format Standalone CRUD | Refreshes new format instance. |
| `backend/access/ml_model_access.py:increment_training_revision` | 184 | `flush()` | ML Metadata Update | Flushes incremented revision counter. |
| `backend/access/ml_model_access.py:update_model_metadata_after_training` | 197, 227 | `flush()` | ML Metadata Update | Flushes updated model evaluation metrics. |
| `backend/access/recurring_access.py:stage_upsert_detected_series` | 118, 134, 152 | `flush()` | Recurring Series Staging | Flushes staged recurring item updates. |
| `backend/access/recurring_access.py:set_recurring_item_status` | 167 | `flush()` | Recurring Item Status | Flushes status update. |
| `backend/access/recurring_access.py:remove_stale_detected_items` | 194 | `flush()` | Recurring Stale Cleanup | Flushes deleted stale items. |
| `backend/access/split_access.py:stage_replace_splits` | 104, 117 | `flush()` | Split Staging | Flushes deleted and inserted split lines. |
| `backend/access/split_access.py:stage_delete_splits` | 139 | `flush()` | Split Deletion | Flushes deleted split lines. |
| `backend/access/transaction_access.py:create_manual_transaction` | 563 | `commit()` | Transaction Standalone CRUD | Commits new manual transaction. |
| `backend/access/transaction_access.py:create_manual_transaction` | 564 | `refresh()` | Transaction Standalone CRUD | Refreshes new transaction instance. |
| `backend/access/transaction_access.py:update_manual_transaction` | 656 | `commit()` | Transaction Standalone CRUD | Commits updated transaction. |
| `backend/access/transaction_access.py:update_manual_transaction` | 657 | `refresh()` | Transaction Standalone CRUD | Refreshes updated transaction instance. |
| `backend/access/transaction_access.py:delete_manual_transaction` | 680 | `commit()` | Transaction Standalone CRUD | Commits deleted transaction. |
| `backend/access/transaction_access.py:mark_transactions_as_transfers` | 711 | `commit()` | Transfer Approval Standalone CRUD | Commits `is_transfer = True` on transaction pair. |
| `backend/access/transaction_access.py:set_transaction_cleared` | 781 | `commit()` | Cleared Toggle Standalone CRUD | Commits toggled `is_cleared` flag. |
| `backend/access/transaction_access.py:mark_transactions_as_reconciled` | 817 | `flush()` | Account Reconciliation | Flushes locked reconciled transactions. |
| `backend/access/transaction_access.py:apply_category_to_uncategorized_by_merchant_key` | 873 | `flush()` | Retroactive Rule Apply | Flushes categorized rows. |
| `backend/crud/plaid.py:create_plaid_item` | 22 | `commit()` | Legacy Plaid Item Creation | Commits new Plaid item record. |
| `backend/crud/plaid.py:update_transactions_cursor` | 40 | `commit()` | Legacy Cursor Update | Commits updated cursor. |
| `backend/crud/plaid.py:create_account` | 65 | `commit()` | Legacy Account Creation | Commits created account. |
| `backend/crud/plaid.py:sync_accounts_and_balances` | 120 | `flush()` | Legacy Account Balance Sync | Flushes upserted accounts. |

---

### 10.2 Analysis of Transaction Ownership

Transaction boundary ownership across the codebase is **MIXED**:

1. **Multi-Step Workflows Orchestrated by Managers:**
   - Commit ownership is consistently held by the Manager:
     - `AccountReconciliationManager`: owns `commit()` (line 183) and `rollback()` (line 185). Accessors only flush.
     - `CategorizationRuleManager`: owns `commit()` (line 68) and `rollback()` (line 71). Accessors only flush.
     - `CSVImportManager`: owns `commit()` (line 113). Accessors only `add()`.
     - `MLCategorizationManager`: owns `commit()` and `rollback()` across training and acceptance. Accessors only flush.
     - `RecurringTransactionManager`: owns `commit()` and `rollback()`. Accessors only flush.
     - `TransactionSplitManager`: owns `commit()` and `rollback()`. Accessors only flush.
2. **Plaid Transaction Sync (Anomalous Structure):**
   - In `PlaidTransactionSyncManager`, commits are **NOT atomic for the whole sync**.
   - Line 199 flushes account balance updates.
   - Lines 123, 126, and 250 execute **per-row commits** on every added, modified, or removed event.
   - Lines 259 and 261 execute **two consecutive final commits**.
   - If a network error occurs mid-page, all events processed prior to the failure remain committed in the database, while the cursor update at the end has not yet executed.
3. **Standalone CRUD Inside Accessors:**
   - Standalone CRUD operations (`create`, `update`, `delete`) in `account_access`, `budget_access`, `categorization_rule_access`, `category_access`, `csv_format_access`, and `transaction_access` execute `db.commit()` inside the Accessor.
4. **Presentation Router Commits:**
   - In `backend/routers/plaid.py:59`, `exchange_public_token` executes `db.commit()` directly in the router handler.
---

## 11. Current Code vs. Architecture Docs Discrepancies

Comparing actual Python implementation source code against the documentation under `docs/architecture/` produces the following discrepancy analysis.

### 11.1 Discrepancy Verification Table

| Documented Claim | Document Reference | Current Source Reality | Match? | Source Code Evidence |
|---|---|---|:---:|---|
| **`DashSummaryMgr --> AcctSummaryMgr`** | `volatility-map.md:180` | `dashboard_summary_manager.py` does **not** call `account_summary_manager`. It calls `account_access.get_active_accounts` directly and reads stored `acc.current_balance`. | **NO** | `backend/managers/dashboard_summary_manager.py:21,101,108-110`. Does not import `account_summary_manager`. |
| **`CSVImportMgr --> RulesMgr`** | `volatility-map.md:201` | `csv_import_manager.py` does **not** call `categorization_rule_manager`. It calls `categorization_rule_access.get_rules_lookup_dict` directly and passes the dict to `transaction_access`. | **NO** | `backend/managers/csv_import_manager.py:17,74`. Does not import `categorization_rule_manager`. |
| **`PlaidTxSyncMgr --> RulesMgr`** | `volatility-map.md:208` | `plaid_transaction_sync_manager.py` does **not** call `categorization_rule_manager`. It calls `categorization_rule_access.get_rules_lookup_dict` directly and passes the dict to `transaction_access`. | **NO** | `backend/managers/plaid_transaction_sync_manager.py:18,201`. Does not import `categorization_rule_manager`. |
| **`PlaidTxSyncMgr --> SplitAcc`** | `volatility-map.md:209` | `plaid_transaction_sync_manager.py` does **not** import or call `split_access`. Split deallocation occurs via dynamic internal import inside `transaction_access.stage_or_update_plaid_transaction`. | **NO** | `backend/managers/plaid_transaction_sync_manager.py:16-23`. Dynamic call lives in `backend/access/transaction_access.py:359-365`. |
| **`RouterTx --> ReconcileMgr`** | Missing from `volatility-map.md` Mermaid diagram | `transactions.py` calls `transfer_reconciliation_manager.get_transfer_candidates(db)` directly. | **NO (Omission in Doc)** | `backend/routers/transactions.py:76` calls `transfer_reconciliation_manager.get_transfer_candidates(db)`. |
| **Legacy `crud/` is merely backward-compatible legacy** | `current-state.md:108` | Legacy `backend/crud/plaid.py` is actively executed by live production route handler `exchange_public_token`. | **NO** | `backend/routers/plaid.py:47,49,52,60` directly calls 4 functions in `backend/crud/plaid.py`. |
| **Managers strictly own database commits** | `volatility-map.md:9,41`, `refactor-safety.md` | Commit ownership is mixed. 6 Accessor modules execute `db.commit()` in standalone CRUD, and `backend/routers/plaid.py:59` commits directly in the route handler. | **NO** | `backend/access/account_access.py:165`, `budget_access.py:63`, `categorization_rule_access.py:112`, `category_access.py:48`, `csv_format_access.py:167`, `transaction_access.py:563,711`, `routers/plaid.py:59`. |
| **Number of Managers = 13** | `current-state.md:94-107`, `volatility-map.md:85-99` | Exactly 13 manager modules exist in `backend/managers/`. | **MATCH** | All 13 modules verified present and functional. |
| **Number of Domain Modules = 11** | `current-state.md:80-93`, `volatility-map.md:101-116` | Exactly 11 pure modules exist in `backend/domain/` (8 engines + 3 utilities). | **MATCH** | All 11 modules verified pure and functional. |
| **Number of Accessors = 12** | `current-state.md:67-79`, `volatility-map.md:122-135` | Exactly 12 access modules exist in `backend/access/`. | **MATCH** | All 12 modules verified present. |
| **`DashboardSummaryManager -> BudgetSummaryManager`** | `dashboard-summary.md:14`, `volatility-map.md:179` | `dashboard_summary_manager.py` imports and invokes `budget_summary_manager.get_budget_summary`. | **MATCH** | `backend/managers/dashboard_summary_manager.py:25,98`. |
| **Redundant Account Check in CSV Confirm** | `csv-import-confirmation.md:68-79` | Document explicitly notes that account is verified in both Router and Manager. Code matches. | **MATCH** | `backend/routers/upload.py:305` and `backend/managers/csv_import_manager.py:63`. |

---

## 12. Evidence-Based Volatility Inventory

Evaluating each system responsibility against the strict definitions of **OBSERVED** (proven by current code, multiple implementations, or integration pain), **PLANNED** (confirmed in active roadmap/TODO), and **SPECULATIVE** (hypothetical future flexibility).

### 12.1 Volatility Inventory Table

| System Responsibility | Volatility Classification | Concrete Codebase Evidence |
|---|:---:|---|
| **Budget Calculations** | **OBSERVED** | Zero-based budgeting rules, display sign inversion on income ($	ext{actual} = -1 	imes 	ext{raw}$), remaining calculations, and over-budget thresholds are encapsulated in `domain/budgeting.py` and reused across budget and dashboard screens. |
| **Dashboard Composition** | **OBSERVED** | Composite screen view combining budget health, liquid account balances, and recent transaction history. Changes independently from calculation algorithms. |
| **Account Summaries** | **OBSERVED** | Three distinct balance derivation policies in active code: ledger-derived balance for manual depository accounts ($starting - net$), remote snapshot balance for Plaid accounts, and stored balance for non-depository accounts. |
| **Credit-Card Summaries** | **OBSERVED** | Authoritative credit debt policy: all-time cumulative net transactions ($starting + net$), current-month non-transfer charges, current-month payments, and overpayment handling in `domain/credit_cards.py`. |
| **Account Reconciliation** | **OBSERVED** | Two-state reconciliation workflow: cleared balance calculation, statement difference, balanced state invariant ($|difference| == 0.00$), and locking participating cleared transactions (`is_reconciled = True`). |
| **Transfer Matching** | **OBSERVED** | 1-to-1 heuristic pairing of unlinked opposite-signed transactions of identical absolute amount within 2 days across differing accounts in `domain/reconciliation.py`. |
| **CSV Statement Parsing** | **OBSERVED** | Multiple concrete parser subclasses actively maintained: `USAALoader` (positive is inflow), `DiscoverLoader` (negative is inflow), and `MappedStatementLoader` (configurable masks and sign conventions). |
| **CSV Custom Formats** | **OBSERVED** | Database persistence entity `models.CSVFormat`, unique constraint indexes, custom configuration converter, and user-defined mappings in `access/csv_format_access.py`. |
| **Plaid Account Access** | **OBSERVED** | Remote API integration using official Plaid Python SDK client for link token creation and balance refresh. |
| **Plaid Transaction Sync Access** | **OBSERVED** | Dedicated raw HTTP `requests.post` integration implemented in `plaid_transaction_access.py` to bypass demonstrated cursor typing bugs in the official Plaid Python SDK. |
| **Merchant Normalization** | **OBSERVED** | Regular expression heuristics stripping point-of-sale aggregator prefixes (`SQ *`, `TST*`, `PAYPAL *`), store identifiers, phone numbers, and state codes in `domain/merchant_normalization.py`. |
| **Categorization Rules** | **OBSERVED** | Exact canonical payee key normalization (`clean_merchant_key`), unique index constraint on canonical merchant, dictionary-based fast matching during ingestion, and retroactive batch execution. |
| **ML Categorization** | **OBSERVED** | Local machine learning pipeline: TF-IDF character n-gram vectorization, balanced Logistic Regression, frequency baseline, safety gate evaluation, atomic disk file replacement, and confidence thresholding. |
| **Recurring Detection** | **OBSERVED** | Heuristic interval clustering over historical transactions for weekly, biweekly, monthly, and annual cadences, stability variance filtering, and date projection in `domain/recurring_transactions.py`. |
| **Split Allocation** | **OBSERVED** | Accounting invariants: parent amount exact sum invariant ($\sum allocations == parent$), minimum 2 lines, non-zero line amounts, and uniform sign matching in `domain/transaction_splits.py`. |
| **Database Persistence** | **OBSERVED** | PostgreSQL 18 with SQLAlchemy 2.x ORM, declarative models, and 7 idempotent schema migration functions in `backend/database.py`. |
| **HTTP / API Transport** | **OBSERVED** | 11 FastAPI presentation routers handling query parsing, multipart file uploads, HTTP status codes (200, 201, 204, 400, 404, 409, 422, 500), and Pydantic v2 serialization. |
| **Frontend Presentation** | **OBSERVED** | Nuxt 4 / Vue 3 Composition API SPA with centralized design tokens (`tokens.css`), responsive layouts, interactive dialogs, and route query synchronization. |
| **Alternative Bank Aggregators (MX, Teller, Finicity)** | **SPECULATIVE** | Only Plaid is implemented. No secondary aggregator exists or is on the confirmed roadmap. Generic bank provider interfaces are speculative. |
| **Hardcoded Bank Classes for Hypothetical Layouts (Chase, BoA)** | **SPECULATIVE** | Handled generically by `MappedCSVFormatConfig`. Hardcoded parser classes for other banks do not exist and are speculative. |
| **Fuzzy Duplicate Matching / Hash Scoring** | **SPECULATIVE** | Ingestion uses exact 4-tuple equality `(account_id, date, amount, description)`. Algorithmic fuzzy duplicate matching is speculative. |
| **Complex Rule Condition Trees / Priority DSL** | **SPECULATIVE** | Rules are strictly 1:1 exact canonical merchant &rarr; category_id. Condition trees, contains/regex operators, and priority weighting are speculative. |
| **Multi-Currency Ledgers / Forex Rates** | **SPECULATIVE** | All accounts and calculations operate strictly in fixed-point USD decimals. Multi-currency ledgers are speculative. |
| **Multi-User / JWT Authentication Infrastructure** | **SPECULATIVE** | The app is single-user personal finance software without user tenants or authentication middleware. Multi-tenancy is speculative. |
| **Alternative Persistence Engines (MongoDB, DynamoDB)** | **SPECULATIVE** | Relational integrity, ACID transactions, and foreign key cascades are fundamental to the domain. Storage engine abstraction is speculative. |
---

## 13. Questions the Final Report Must Answer

### Managers
1. **Are any Managers simple pass-through wrappers?**
   - None of the 13 Managers are purely 1-line pass-through wrappers across all their entrypoints. However, several specific manager operations exhibit near-trivial pass-through or simple CRUD characteristics:
     - `recurring_transaction_manager.confirm_recurring_item` and `dismiss_recurring_item` simply call `recurring_access.set_recurring_item_status` and commit.
     - `recurring_transaction_manager.list_recurring_items` simply calls `recurring_access.list_recurring_items` and maps to schemas.
     - `transaction_split_manager.get_transaction_splits` simply verifies transaction existence and calls `split_access.get_splits_for_transaction`.
     - `categorization_rule_manager.preview_rule_matches` loads 1 rule and counts matching uncategorized rows.

2. **Are any Managers primarily named after screens/endpoints rather than independently changing workflow sequences?**
   - **YES.** Four managers are named directly after user-facing screens and HTTP endpoints:
     - `BudgetSummaryManager` &rarr; powers `/summary/budget` (Budget screen).
     - `DashboardSummaryManager` &rarr; powers `/summary/dashboard` (Dashboard screen).
     - `AccountSummaryManager` &rarr; powers `/accounts/` (Accounts screen).
     - `CreditCardSummaryManager` &rarr; powers `/credit-cards/summary` (Credit Cards screen).

3. **Which Managers call other Managers?**
   - Exactly **one** Manager calls another Manager in current production code:
     - `DashboardSummaryManager` calls `BudgetSummaryManager.get_budget_summary` (`backend/managers/dashboard_summary_manager.py:98`).
   - No other Manager-to-Manager call exists.

4. **Which Managers appear to form one related family of use cases?**
   - **Screen Summary Family:** `BudgetSummaryManager`, `DashboardSummaryManager`, `AccountSummaryManager`, `CreditCardSummaryManager`. (Read-only data retrieval and calculation orchestration for specific UI screens).
   - **Payee Categorization Family:** `CategorizationRuleManager`, `MLCategorizationManager` (plus inline rule application during ingestion).
   - **Bank Sync & Statement Ingestion Family:** `CSVImportManager`, `PlaidAccountSyncManager`, `PlaidTransactionSyncManager`.

5. **Are there clear duplicated orchestration sequences among Managers?**
   - **YES:**
     - *Token Decryption & Item Resolution:* `PlaidAccountSyncManager` (lines 67–80) and `PlaidTransactionSyncManager` (lines 161–174) execute the exact same sequence to resolve `PlaidItem` and decrypt stored access tokens.
     - *Pre-Sync Account Staging:* `PlaidTransactionSyncManager` (lines 184–199) duplicates the snapshot iteration and `account_access.stage_or_update_plaid_account` staging loop of `PlaidAccountSyncManager`.
     - *Month Range Calculation:* `BudgetSummaryManager`, `DashboardSummaryManager`, and `CreditCardSummaryManager` duplicate `start_date, end_date = determine_month_range(budget_month)`.
     - *Categorization Rule Dictionary Staging:* `CSVImportManager` (line 74) and `PlaidTransactionSyncManager` (line 201) both load `rules_lookup = categorization_rule_access.get_rules_lookup_dict(db)` and pass it into `transaction_access`.

---

### Engines
6. **Do any Engines/domain modules depend on infrastructure?**
   - **NO.** All 11 files in `backend/domain/` are 100% pure Python with zero imports or references to FastAPI, HTTPException, Pydantic, SQLAlchemy Session, ORM models, accessors, managers, external SDKs, filesystem paths, or environment variables. (Only `numpy`/`scikit-learn` in `ml_categorization.py`).

7. **Do any domain modules appear to be tiny utilities currently presented as architectural components?**
   - **YES:**
     - `backend/domain/accounts.py` is a 34-line file containing a single 1-line formula: `calculate_depository_balance` ($starting - net$).
     - `backend/domain/dates.py` is a 20-line file containing a single helper: `determine_month_range`.
     - `backend/domain/categorization_rules.py` contains 3 functions, 2 of which have zero production callers, leaving only `clean_merchant_key(merchant)` (which strips whitespace, converts to uppercase, and removes punctuation).

8. **Is any volatile business policy duplicated outside its authoritative Engine/domain module?**
   - **YES:**
     - `domain.categorization_rules.match_merchant_rule` exists to evaluate whether a transaction merchant matches an active rule. However, it has **zero callers** in production. Instead, `transaction_access.py` manually inlines the rule-matching check (`clean_key = clean_merchant_key(merchant); if clean_key and clean_key in rules_lookup: ...`) across 3 separate places (lines 235, 316, 383).
     - Depository cash balance derivation is implemented in `AccountSummaryManager` via `calculate_depository_balance`, but `DashboardSummaryManager` bypasses this policy and sums stored `current_balance` directly.

---

### ResourceAccess
9. **Are Accessors divided primarily by entity/table, by access mechanism, or by cohesive atomic operations?**
   - **Entity/Table (7 of 10 database accessors):** `account_access`, `budget_access`, `categorization_rule_access`, `csv_format_access`, `plaid_item_access`, `recurring_access`, and `split_access` map 1:1 to single database tables.
   - **Access Mechanism:** `plaid_access.py` (Plaid SDK), `plaid_transaction_access.py` (raw HTTP requests), and `ml_model_access.py` (PostgreSQL metadata + filesystem joblib artifacts).
   - **Mixed Mega-Repository:** `transaction_access.py` (908 lines) covers table queries, batch staging, standalone CRUD commits, split deletion, and ML revision tracking.

10. **Are there Accessor-to-Accessor calls?**
    - **YES.** Multiple cross-accessor dependencies exist via internal dynamic imports:
      - `backend/access/category_access.py:186` &rarr; calls `split_access.count_splits_by_category`.
      - `backend/access/transaction_access.py:360,594,699` &rarr; calls `split_access.transaction_has_splits` and `stage_delete_splits`.
      - `backend/access/transaction_access.py:241,321,388,543,650` &rarr; calls `categorization_rule_access.get_rule_by_merchant`.
      - `backend/access/transaction_access.py:540,638` &rarr; calls `ml_model_access.increment_training_revision`.

11. **Are there SQLAlchemy queries still outside Accessors, excluding intentionally accepted cases?**
    - **NO.** Within application workflows, all SQLAlchemy queries are contained inside `backend/access/` and `backend/crud/plaid.py`. The only queries outside those directories are:
      - `backend/initial_data.py`: Category group seeding during FastAPI lifespan startup.
      - `backend/database.py`: 7 idempotent schema migration functions executing raw DDL/DML via `conn.execute()`.

---

### Presentation
12. **Which Routers contain application sequencing?**
    - `backend/routers/plaid.py` in `exchange_public_token`: calls `crud_plaid.get_plaid_item_by_plaid_item_id` &rarr; `crud_plaid.create_plaid_item` &rarr; `crud_plaid.sync_accounts_and_balances` &rarr; `db.commit()` &rarr; `crud_plaid.list_accounts_by_item`.
    - `backend/routers/upload.py` in `preview_csv`: runs file decoding, `csv.DictReader` initialization, row-by-row normalization and transformation loops, and error aggregation.
    - `backend/routers/upload.py` in `inspect_csv`: runs file decoding, sample row sniffing, custom format candidate retrieval, and candidate format auto-detection.

13. **Which Routers contain resource-selection/resource-construction logic?**
    - `backend/routers/upload.py` in helper `_resolve_statement_loader`: inspects string formats, queries `csv_format_access`, converts configuration models, and constructs `MappedStatementLoader` instances.
    - `backend/routers/plaid.py`: directly instantiates Plaid SDK `Configuration`, `ApiClient`, and `PlaidApi`.

14. **Does the upload Router currently do more than transport concerns?**
    - **YES.** As detailed in Section 6 and questions 12–13, `upload.py` performs redundant account existence validation, executes loader selection and construction, runs the entire preview parse loop, and performs CSV header sniffing and auto-detection.

---

### Legacy Code
15. **What live production responsibilities remain under `backend/crud/`?**
    - In `backend/crud/plaid.py`:
      - `create_plaid_item` (called by `routers/plaid.py:49`)
      - `get_plaid_item_by_plaid_item_id` (called by `routers/plaid.py:47`)
      - `sync_accounts_and_balances` (called by `routers/plaid.py:52`)
      - `list_accounts_by_item` (called by `routers/plaid.py:60`)
    - All 4 participate in the live public token exchange workflow during bank account linking.

16. **Can any remaining `crud` module currently be proven dead?**
    - `backend/crud/plaid.py` as a whole is **NOT dead** (4 functions are live in production).
    - However, 3 specific functions within it have **zero** production callers:
      - `get_plaid_item_by_id` (superseded by `plaid_item_access`)
      - `update_transactions_cursor` (superseded by `plaid_item_access`)
      - `create_account` (dead code)

---

### Contracts
17. **Which Manager result DTOs protect a genuine boundary?**
    - `domain.budgeting.BudgetSummaryResult`: protects pure zero-based budgeting calculation structures.
    - `domain.account_reconciliation.ReconciliationCalculation`: protects cleared balance reconciliation math.
    - `csv_import_manager.CSVImportSummary`: protects batch import statistics `(imported, skipped, errors)`.
    - `plaid_transaction_sync_manager.PlaidTransactionSyncResult`: protects multi-stage sync counters and cursor state.

18. **Which Manager result DTOs mostly duplicate ORM/Pydantic structures?**
    - `DashboardAccountItem`, `DashboardTransactionAccountItem`, `DashboardRecentTransactionItem` in `dashboard_summary_manager.py`: field-for-field duplicates of `models.Account`, `models.Transaction`, `schemas.AccountRead`, and `schemas.TransactionDetailRead`.
    - `CreditCardMonthlyTransactionItem` and `CreditCardAccountSummaryItem` in `credit_card_summary_manager.py`: duplicates of `models.Transaction`, `schemas.CreditCardTransactionRead`, and `schemas.CreditCardAccountSummary`.
    - `TransferInflowSideItem`, `TransferOutflowAccountItem`, and `TransferOutflowSideItem` in `transfer_reconciliation_manager.py`: duplicates of `models.Transaction`, `models.Account`, and presentation schemas.

---

### Transactions
19. **Who currently owns commit/rollback boundaries for each multi-step workflow?**
    - **CSV Import:** `CSVImportManager.confirm_csv_import` owns `db.commit()` (line 113).
    - **Plaid Account Sync:** `PlaidAccountSyncManager.sync_plaid_accounts` owns `db.flush()` (line 107) and `db.commit()` (line 108).
    - **Plaid Transaction Sync:** `PlaidTransactionSyncManager` owns commits, but uses **per-row commits** in the pagination loop (lines 123, 126, 250) followed by **two final commits** (lines 259, 261).
    - **Account Reconciliation:** `AccountReconciliationManager.complete_reconciliation` owns `db.commit()` (line 183) and `db.rollback()` (line 185).
    - **Transaction Splitting:** `TransactionSplitManager` owns `db.commit()`, `db.refresh()`, and `db.rollback()` in `create_or_replace_split` (lines 131–135) and `unsplit_transaction` (lines 179–183).
    - **Retroactive Rule Apply:** `CategorizationRuleManager.apply_rule_to_uncategorized` owns `db.commit()` (line 68) and `db.rollback()` (line 71).
    - **Recurring Detection:** `RecurringTransactionManager.detect_and_sync_recurring_items` owns `db.commit()` (line 114) and `db.rollback()` (line 116).
    - **Plaid Public Token Exchange:** Route handler `backend/routers/plaid.py:exchange_public_token` owns `db.commit()` (line 59).

20. **Are any commits hidden inside ResourceAccess functions?**
    - **YES.** Standalone CRUD operations inside 6 Accessor modules execute `db.commit()` directly:
      - `account_access.py` (lines 165, 199, 218)
      - `budget_access.py` (lines 63, 85, 103)
      - `categorization_rule_access.py` (lines 112, 150, 170)
      - `category_access.py` (lines 48, 71, 85, 104, 149, 172, 191, 211)
      - `csv_format_access.py` (line 167)
      - `transaction_access.py` (lines 563, 656, 680, 711, 781)

---

## 14. Potential VBD Review Hotspots

This section synthesizes findings into cautious architectural review hotspots tied strictly to source-code evidence.

### Hotspot 1: Live Production Execution in Legacy `backend/crud/plaid.py`
- **Classification:** `HIGH-CONFIDENCE FACT`
- **Evidence:** `backend/routers/plaid.py:47,49,52,60` directly invokes 4 functions from `backend/crud/plaid.py` during `POST /plaid/exchange_public_token`, and executes `db.commit()` directly inside the router handler at line 59.
- **Architectural Implication:** Token exchange was never migrated to the VBD layer structure. It bypasses `plaid_account_sync_manager` and `plaid_item_access`, maintaining an active production dependency on the legacy CRUD module.

### Hotspot 2: Non-Atomic Per-Row Commits in `PlaidTransactionSyncManager`
- **Classification:** `HIGH-CONFIDENCE FACT`
- **Evidence:** `backend/managers/plaid_transaction_sync_manager.py` calls `db.commit()` inside `_process_upsert_event` for each individual added/modified event (lines 123, 126) and removed event (line 250), followed by two back-to-back final commits at lines 259 and 261.
- **Architectural Implication:** If a network failure occurs midway through pagination, previously processed transaction rows remain committed in PostgreSQL, but the cursor update at line 259 has not executed. On the subsequent sync, Plaid re-sends the same transactions. Furthermore, the double commit at lines 259 and 261 is an uncurated compatibility artifact from legacy code.

### Hotspot 3: Discrepancy Between Documented and Actual Manager Wiring
- **Classification:** `HIGH-CONFIDENCE FACT`
- **Evidence:**
  - `volatility-map.md:180` claims `DashSummaryMgr --> AcctSummaryMgr`. Current code does **not** make this call (`dashboard_summary_manager.py:21,101`).
  - `volatility-map.md:201` claims `CSVImportMgr --> RulesMgr`. Current code does **not** make this call (`csv_import_manager.py:17,74`).
  - `volatility-map.md:208` claims `PlaidTxSyncMgr --> RulesMgr`. Current code does **not** make this call (`plaid_transaction_sync_manager.py:18,201`).
- **Architectural Implication:** The architecture diagrams in `volatility-map.md` depict inter-manager coupling that does not exist in running code. The real code decouples ingestion from `CategorizationRuleManager` by fetching lookup tables directly via Accessors.

### Hotspot 4: Application Sequencing Trapped in Upload Router
- **Classification:** `HIGH-CONFIDENCE FACT`
- **Evidence:** `backend/routers/upload.py` implements the complete CSV preview parsing loop in `preview_csv` (lines 244–276), format auto-detection in `inspect_csv` (lines 141–208), and loader resolution in `_resolve_statement_loader` (lines 48–76).
- **Architectural Implication:** `preview_csv` duplicates the row-by-row parsing logic of `BankStatementLoader.load_records_tolerant`, while `_resolve_statement_loader` performs dynamic class instantiation and database lookups inside the presentation layer.

### Hotspot 5: Redundant Intermediate DTO Boundaries in Summary Managers
- **Classification:** `LIKELY HOTSPOT`
- **Evidence:** `DashboardSummaryManager`, `CreditCardSummaryManager`, and `TransferReconciliationManager` define custom `@dataclass(frozen=True)` structures (`DashboardAccountItem`, `CreditCardMonthlyTransactionItem`, `TransferInflowSideItem`, etc.) whose fields duplicate ORM models and are immediately re-mapped by route handlers into Pydantic response models.
- **Architectural Implication:** Unless external presentation models change independently from these internal dataclasses, this represents an extra intermediate mapping boundary that increases ceremony without providing volatility isolation.

### Hotspot 6: Mega-Accessor Cohesion in `transaction_access.py`
- **Classification:** `LIKELY HOTSPOT`
- **Evidence:** `backend/access/transaction_access.py` is 908 lines long and contains 23 public functions. It dynamically imports and calls `split_access`, `ml_model_access`, and `categorization_rule_access` across 7 functions, and inlines rule-matching logic.
- **Architectural Implication:** While other accessors are tightly cohesive around single entities or access mechanisms, `transaction_access.py` has absorbed orchestration side-effects and cross-accessor dependencies.

### Hotspot 7: Fast-Path / Narrow Domain Modules
- **Classification:** `INSUFFICIENT EVIDENCE`
- **Evidence:** `backend/domain/accounts.py` ($starting - net$), `backend/domain/dates.py` (`determine_month_range`), and `backend/domain/categorization_rules.py` (`clean_merchant_key`) are tiny functions classified in documentation as "Domain Utilities".
- **Architectural Implication:** While isolating pure functions is good practice, whether these small helpers justify separate files depends on team preferences regarding module granularity vs. package sprawl.

---

## 15. Verification

1. **Production Code Changes:** NONE.
2. **Test Changes:** NONE.
3. **Repository Cleanliness Check:**
   - Command: `git diff --stat`
   - Output:
     ```text
     docs/architecture/vbd-source-evidence-audit.md | [new file]
     ```
   - Only `docs/architecture/vbd-source-evidence-audit.md` has been created.
