# REST API Reference

The backend API is built with FastAPI. Interactive OpenAPI/Swagger documentation is available at `http://localhost:12344/docs` (or `http://localhost:8000/docs` when running without Docker).

Base URLs:
- **Docker Compose host port:** `http://localhost:12344`
- **Docker container internal port:** `http://backend:8000`
- **Frontend Proxy route:** `/api/**` -> `http://backend:8000/**`

---

## Table of Contents
1. [Category Groups](#1-category-groups)
2. [Categories](#2-categories)
3. [Budgets & Planning](#3-budgets--planning)
4. [Transactions](#4-transactions)
5. [Accounts & Reconciliation](#5-accounts--reconciliation)
6. [Categorization Rules](#6-categorization-rules)
7. [Machine Learning Categorization](#7-machine-learning-categorization)
8. [Recurring Transactions](#8-recurring-transactions)
9. [Credit Cards & Transfers](#9-credit-cards--transfers)
10. [CSV Statement Upload](#10-csv-statement-upload)
11. [Summaries & Dashboard](#11-summaries--dashboard)
12. [Plaid Bank Integration](#12-plaid-bank-integration)

---

## 1. Category Groups

Manage high-level grouping containers (e.g. "Housing", "Food", "Income").

### `POST /category-groups`
Create a new category group.
- **Request Body:**
  ```json
  {
    "name": "Housing",
    "sort_order": 1
  }
  ```
- **Response (201 Created):** `CategoryGroupRead`

### `GET /category-groups`
List all category groups, eager-loading nested categories, ordered by `sort_order`.
- **Response (200 OK):** `Array<CategoryGroupWithCategories>`

### `GET /category-groups/{group_id}`
Retrieve a category group by UUID.
- **Response (200 OK):** `CategoryGroupRead`

### `PUT /category-groups/{group_id}`
Update group name or sort order.
- **Request Body:** `{"name": "New Name", "sort_order": 2}`
- **Response (200 OK):** `CategoryGroupRead`

### `DELETE /category-groups/{group_id}`
Delete a group. Cascade deletes child categories in the database.
- **Response (204 No Content)**

### `POST /category-groups/reorder`
Batch update sort orders from an ordered array of group UUIDs.
- **Request Body:**
  ```json
  {
    "order": ["uuid-1", "uuid-2", "uuid-3"]
  }
  ```
- **Response (200 OK):** `Array<CategoryGroupWithCategories>`

---

## 2. Categories

Manage individual spending, income, or transfer categories.

### `POST /categories`
Create a new category under a group.
- **Request Body:**
  ```json
  {
    "name": "Groceries",
    "group_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "sort_order": 0,
    "type": "expense",
    "is_active": true
  }
  ```
  *(type must be one of: `"income"`, `"expense"`, `"transfer"`)*
- **Response (201 Created):** `CategoryRead`

### `GET /categories`
List categories with optional group filter.
- **Query Parameters:** `group_id` (optional UUID)
- **Response (200 OK):** `Array<CategoryRead>`

### `GET /categories/{category_id}`
Retrieve single category by UUID.
- **Response (200 OK):** `CategoryRead`

### `PUT /categories/{category_id}`
Update category fields (`name`, `group_id`, `sort_order`, `type`, `is_active`).
- **Request Body:** `CategoryUpdate`
- **Response (200 OK):** `CategoryRead`

### `DELETE /categories/{category_id}`
Delete category. Cascade deletes associated budget records; nullifies category_id on linked transactions (`SET NULL`).
- **Response (204 No Content)**

### `POST /categories/reorder`
Reorder categories within a group.
- **Request Body:**
  ```json
  {
    "group_id": "group-uuid",
    "order": ["cat-uuid-1", "cat-uuid-2"]
  }
  ```
- **Response (200 OK):** `Array<CategoryRead>`

---

## 3. Budgets & Planning

Set and query planned monthly dollar allocations.

### `POST /budget/`
Create a monthly planned amount for a category.
- **Request Body:**
  ```json
  {
    "budget_month": "2026-03-01",
    "planned_amount": 450.00,
    "category_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```
  *(Note: `budget_month` must be formatted as `YYYY-MM-01`)*
- **Response (201 Created):** `BudgetRead`

### `GET /budget/`
Query budgets, optionally filtered by month or category.
- **Query Parameters:** `budget_month` (optional date `YYYY-MM-01`), `category_id` (optional UUID)
- **Response (200 OK):** `Array<BudgetRead>`

### `GET /budget/{budget_id}`
Retrieve a budget record.
- **Response (200 OK):** `BudgetRead`

### `PUT /budget/{budget_id}`
Update planned amount or month.
- **Request Body:** `{"planned_amount": 500.00}`
- **Response (200 OK):** `BudgetRead`

### `DELETE /budget/{budget_id}`
Delete a budget record.
- **Response (204 No Content)**

---

## 4. Transactions

Ledger for spending, deposits, transfers, and split category allocations.

> [!IMPORTANT]
> **Amount Convention:** Outflow (money spent) is positive (`+50.00`); Inflow (income/deposit) is negative (`-2500.00`).

### `GET /transactions/`
Search and filter transactions with server-side pagination.
- **Query Parameters:**
  - `account_id` (UUID, optional)
  - `category_id` (UUID, optional) - matches parent category or any child split allocation
  - `start_date` (`YYYY-MM-DD`, optional)
  - `end_date` (`YYYY-MM-DD`, optional)
  - `uncategorized` (`bool`, optional) - matches transactions with `category_id IS NULL AND ~has_splits`
  - `q` (`str`, optional) - case-insensitive substring search on description or merchant
  - `limit` (`int`, default: 50)
  - `offset` (`int`, default: 0)
- **Response (200 OK):** `TransactionListResponse`
  ```json
  {
    "items": [...],
    "total": 142,
    "limit": 50,
    "offset": 0
  }
  ```

### `GET /transactions/{transaction_id}`
Retrieve a single transaction with joined account and split details.
- **Response (200 OK):** `TransactionRead`

### `POST /transactions/`
Manually create a single transaction.
- **Request Body:**
  ```json
  {
    "account_id": "account-uuid",
    "category_id": "category-uuid",
    "description": "Trader Joe's",
    "merchant": "Trader Joe's",
    "amount": 78.45,
    "date": "2026-03-15",
    "pending": false
  }
  ```
- **Response (201 Created):** `TransactionRead`

### `PUT /transactions/{transaction_id}`
Update category assignment, merchant, description, transfer flag, or review status.
- **Request Body:** `TransactionUpdate`
- **Response (200 OK):** `TransactionRead`

### `PATCH /transactions/{transaction_id}/cleared`
Toggles the `is_cleared` status of a transaction during account reconciliation.
- **Request Body:** `{"is_cleared": true}`
- **Response (200 OK):** `TransactionRead`
- **Error Responses:** `400 Bad Request` if transaction is already reconciled (`is_reconciled == true`).

### `DELETE /transactions/{transaction_id}`
Delete a transaction by UUID.
- **Response (204 No Content)**
- **Error Responses:** `400 Bad Request` if transaction is reconciled.

### `GET /transactions/transfer-candidates`
Scans database for matching inter-account transfers across different accounts within a 2-day window where neither side has `is_transfer = true`.
- **Response (200 OK):** `Array<TransferCandidateResponse>`

### `POST /transactions/mark-transfers`
Marks one or more transactions with `is_transfer = true`.
- **Request Body:** `{"transaction_ids": ["txn-uuid-1", "txn-uuid-2"]}`
- **Response (204 No Content)**

### Split Transaction Endpoints

#### `GET /transactions/{transaction_id}/splits`
Retrieves child split allocations for a specific transaction.
- **Response (200 OK):** `Array<TransactionSplitRead>`

#### `PUT /transactions/{transaction_id}/splits`
Atomically replaces split allocations for a transaction:
- **Request Body:**
  ```json
  {
    "splits": [
      {"category_id": "cat-uuid-1", "amount": 50.00},
      {"category_id": "cat-uuid-2", "amount": 28.45}
    ]
  }
  ```
- **Invariant:** Sum of split amounts must exactly equal parent transaction amount (`Decimal`). Minimum 2 allocations, non-zero amounts, same sign as parent.
- **Response (200 OK):** `TransactionRead`

#### `POST /transactions/{transaction_id}/unsplit`
Converts a split transaction back to a single category transaction:
- **Request Body:** `{"category_id": "cat-uuid"}`
- **Response (200 OK):** `TransactionRead`

### ML Category Suggestion Endpoints

#### `POST /transactions/category-suggestions`
Computes ML category suggestions for a batch of transaction IDs.
- **Request Body:** `{"transaction_ids": ["uuid-1", "uuid-2"]}`
- **Response (200 OK):** `BatchCategorySuggestionsResponse`

#### `GET /transactions/{transaction_id}/category-suggestion`
Returns an ML category suggestion for a specific transaction if eligible (abstains below 0.30 operating confidence).
- **Response (200 OK):** `TransactionCategorySuggestionRead`

#### `POST /transactions/{transaction_id}/accept-suggestion`
Accepts an ML category suggestion:
- **Request Body:** `{"category_id": "cat-uuid"}`
- **Response (200 OK):** `TransactionRead` (sets `category_source = 'ml'`, increments training revision)

---

## 5. Accounts & Reconciliation

Manage financial accounts and reconcile cleared transactions against institution statement balances.

### `GET /accounts/types`
Returns supported account types and their valid subtypes.
- **Response (200 OK):**
  ```json
  {
    "depository": ["checking", "savings"],
    "credit": ["credit card"],
    "investment": ["brokerage", "ira", "401k", "other"],
    "loan": ["mortgage", "auto", "student", "personal", "other"],
    "other": ["other"]
  }
  ```

### `GET /accounts/`
List all accounts with ledger-derived current balances and reconciliation metadata.
- **Response (200 OK):** `Array<AccountRead>`

### `POST /accounts/`
Create a manual account.
- **Request Body:** `AccountCreate`
- **Response (201 Created):** `AccountRead`

### `PUT /accounts/{account_id}`
Update account metadata (`name`, `type`, `subtype`, `starting_balance`, `is_active`).
- **Response (200 OK):** `AccountRead`

### `DELETE /accounts/{account_id}`
Delete an account and its associated transactions.
- **Response (204 No Content)**

### `GET /accounts/{account_id}/reconciliation`
Returns the reconciliation workspace summary for an account, evaluating cleared transactions through `ending_date` against `ending_balance`.
- **Query Parameters:** `ending_date` (optional date), `ending_balance` (optional Decimal)
- **Response (200 OK):** `AccountReconciliationSummary`
  - `account_id`, `account_name`
  - `statement_ending_date`, `statement_ending_balance`
  - `cleared_balance`, `difference`
  - `cleared_count`, `uncleared_count`
  - `last_reconciled_date`, `last_reconciled_balance`

### `POST /accounts/{account_id}/reconciliation/complete`
Finalizes reconciliation for an account when `difference == 0.00`. Atomically locks all participating cleared transactions (`is_reconciled = true`) and updates the account's watermark.
- **Request Body:**
  ```json
  {
    "statement_ending_date": "2026-03-31",
    "statement_ending_balance": 4120.21
  }
  ```
- **Response (200 OK):** `AccountReconciliationSummary`

---

## 6. Categorization Rules

Deterministic merchant-to-category matching rules keyed by canonical merchant identity.

### `GET /rules/`
Lists all active categorization rules ordered alphabetically by normalized merchant name.
- **Response (200 OK):** `Array<CategorizationRuleRead>`

### `POST /rules/`
Creates a new categorization rule. Refuses duplicate merchants and nonexistent categories.
- **Request Body:**
  ```json
  {
    "merchant": "Starbucks",
    "category_id": "category-uuid"
  }
  ```
- **Response (201 Created):** `CategorizationRuleRead`

### `GET /rules/{rule_id}`
Retrieves a single categorization rule.
- **Response (200 OK):** `CategorizationRuleRead`

### `PUT /rules/{rule_id}`
Updates an existing categorization rule.
- **Request Body:** `CategorizationRuleUpdate`
- **Response (200 OK):** `CategorizationRuleRead`

### `DELETE /rules/{rule_id}`
Deletes a categorization rule.
- **Response (204 No Content)**

### `GET /rules/{rule_id}/preview`
Counts uncategorized transactions that would be matched by this rule retroactively.
- **Response (200 OK):** `CategorizationRulePreviewResponse` (`rule_id`, `merchant`, `category_id`, `matching_count`)

### `POST /rules/{rule_id}/apply`
Applies a categorization rule retroactively to all matching uncategorized transactions, setting `category_source = 'rule'`.
- **Response (200 OK):** `CategorizationRuleBatchApplyResponse` (`rule_id`, `applied_count`)

---

## 7. Machine Learning Categorization

Status and on-demand retraining controls for the local TF-IDF + Logistic Regression classification model.

### `GET /ml/status`
Returns current model status, sample count, active revision, operating threshold, and evaluation metrics.
- **Response (200 OK):** `MLModelStatusRead`

### `POST /ml/retrain`
Triggers local supervised retraining of the candidate model. Evaluates candidate against test split and benchmark; activates atomically if quality gates pass.
- **Query Parameters:** `force` (`bool`, default: false)
- **Response (200 OK):** `MLRetrainResponse` (`success`, `message`, `model_activated`, `status`)

---

## 8. Recurring Transactions

Pattern-detected repeating transactions across accounts.

### `GET /recurring/`
Lists recurring transaction patterns. If none detected yet, runs an initial detection pass.
- **Query Parameters:** `account_id` (optional UUID), `status` (optional string: `"detected"`, `"confirmed"`, `"dismissed"`)
- **Response (200 OK):** `Array<RecurringItemRead>`

### `POST /recurring/detect`
Scans historical posted transactions and detects genuine recurring series (weekly, biweekly, monthly, annual).
- **Query Parameters:** `account_id` (optional UUID)
- **Response (200 OK):** `Array<RecurringItemRead>`

### `GET /recurring/{item_id}`
Returns full details of a specific recurring pattern, including its member transaction history.
- **Response (200 OK):** `RecurringItemDetailRead`

### `POST /recurring/{item_id}/confirm`
Confirms a detected recurring item as an authoritative repeating pattern.
- **Response (200 OK):** `RecurringItemRead`

### `POST /recurring/{item_id}/dismiss`
Dismisses a detected recurring item from active consideration.
- **Response (200 OK):** `RecurringItemRead`

---

## 9. Credit Cards & Transfers

Endpoints for tracking revolving credit debt and matching inter-account transfers.

### `GET /credit-cards/summary`
Calculates cumulative credit debt, monthly charges, and monthly payments per credit card.
- **Query Parameter:** `month` (`YYYY-MM`, required)
- **Response (200 OK):** `CreditCardSummaryResponse`
  - `cards[].balance_owed`: `starting_balance + sum(all-time transactions)`
  - `cards[].charges_this_month`: sum of positive non-transfer transactions
  - `cards[].payments_this_month`: absolute sum of negative transactions
  - `cards[].transactions`: list of transactions for this month

### `GET /credit-cards/transfer-candidates`
Legacy alias for `GET /transactions/transfer-candidates`.
- **Response (200 OK):** `Array<TransferCandidateResponse>`

### `POST /credit-cards/mark-transfers`
Legacy alias for `POST /transactions/mark-transfers`.
- **Response (204 No Content)**

---

## 10. CSV Statement Upload

Parse, inspect, format, and import bank exports with duplicate detection.

### `POST /upload/inspect`
Inspects an uploaded CSV file without importing data or requiring a destination account:
- Reads file stream, extracts headers, and reads up to 3 sample rows.
- Runs pure header auto-detection against built-in and user-defined custom formats.
- **Response (200 OK):** `CSVInspectResponse` (`status`, `headers`, `sample_rows`, `detected_format`, `matches`)

### `GET /upload/formats`
Lists all user-defined persisted custom CSV format configurations.
- **Response (200 OK):** `Array<CSVFormatRead>`

### `POST /upload/formats`
Creates and persists a new custom CSV format definition.
- **Request Body:** `CSVFormatCreate`
- **Response (201 Created):** `CSVFormatRead`

### `POST /upload/preview`
Multipart form upload that parses a CSV file using an explicit format identifier without persisting data.
- **Form Data:** `file`, `account_id`, `format`
- **Response (200 OK):** `CSVPreviewResponse` (`total_rows`, `valid_rows`, `error_rows`, `rows[]`)

### `POST /upload/confirm`
Parses and imports the CSV into the database with duplicate prevention and non-fatal row error isolation.
- **Form Data:** `file`, `account_id`, `format`
- **Response (200 OK):** `CSVImportResult` (`imported`, `skipped`, `errors`)

---

## 11. Summaries & Dashboard

Aggregated financial metrics for budgeting and dashboard visualization.

### `GET /summary/budget`
Computes group-by-group zero-based budgeting breakdown for a specific month (incorporating child split allocations).
- **Query Parameter:** `month` (`YYYY-MM`, required)
- **Response (200 OK):** `BudgetSummaryResponse`
  - `total_income_planned`, `total_income_actual`
  - `total_expense_planned`, `total_expense_actual`
  - `to_be_assigned`: `total_income_planned - total_expense_planned`
  - `groups[]`: category groups with nested planned, actual, remaining, and `is_over_budget`

### `GET /summary/dashboard`
Consolidated view for dashboard home page.
- **Query Parameter:** `month` (`YYYY-MM`, required)
- **Response (200 OK):** `DashboardSummaryResponse`
  - Income and expense KPIs
  - Liquid cash across depository accounts and credit card debt totals
  - Actionable items (unreviewed transactions, transfer candidates)
  - Spending breakdown by category group
  - Connected accounts with balances
  - Recent transactions

---

## 12. Plaid Bank Integration

Endpoints to interface with the Plaid API.

### `POST /plaid/create_link_token`
Generates a Link token for the client Plaid Link drop-in.
- **Response (200 OK):** `{"link_token": "link-sandbox-..."}`

### `POST /plaid/exchange_public_token`
Exchanges public token for access token, stores `PlaidItem`, and initial accounts.
- **Request Body:** `{"public_token": "public-sandbox-..."}`
- **Response (200 OK):** `Array<AccountRead>`

### `POST /plaid/sync_accounts`
Fetches current balance and accounts metadata from Plaid.
- **Request Body:** `{"item_id": "uuid"}` or `{"plaid_item_id": "string"}`
- **Response (200 OK):** `{"accounts_synced": 3}`

### `POST /plaid/sync_transactions`
Uses Plaid cursor-based sync to fetch new, updated, and removed transactions.
- **Request Body:** `{"item_id": "uuid"}` or `{"plaid_item_id": "string"}`
- **Response (200 OK):**
  ```json
  {
    "message": "Transactions synced successfully",
    "added": 15,
    "modified": 2,
    "removed": 0,
    "next_cursor": "cursor_string",
    "warnings": []
  }
  ```
  *(Note: `warnings` array is populated if provider corrections conflict with reconciled transactions or cause split allocations to be deleted)*
