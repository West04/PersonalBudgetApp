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
5. [Accounts](#5-accounts)
6. [Credit Cards & Transfers](#6-credit-cards--transfers)
7. [CSV Statement Upload](#7-csv-statement-upload)
8. [Summaries & Dashboard](#8-summaries--dashboard)
9. [Plaid Bank Integration](#9-plaid-bank-integration)

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
- **Response (201 Created):** [`CategoryGroupRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L16-L22)

### `GET /category-groups`
List all category groups, eager-loading nested categories, ordered by `sort_order`.
- **Response (200 OK):** `Array<CategoryGroupWithCategories>`

### `GET /category-groups/{group_id}`
Retrieve a category group by UUID.
- **Response (200 OK):** [`CategoryGroupRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L16-L22)

### `PUT /category-groups/{group_id}`
Update group name or sort order.
- **Request Body:** `{"name": "New Name", "sort_order": 2}`
- **Response (200 OK):** [`CategoryGroupRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L16-L22)

### `DELETE /category-groups/{group_id}`
Delete a group and cascade delete child categories.
- **Response (204 No Content)**

### `POST /category-groups/reorder`
Batch update sort orders from an ordered array of group UUIDs.
- **Request Body:**
  ```json
  {
    "order": ["uuid-1", "uuid-2", "uuid-3"]
  }
  ```
- **Response (200 OK):** `{"status": "ok", "updated": 3}`

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
- **Response (201 Created):** [`CategoryRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L42-L52)

### `GET /categories`
List categories with optional group filter.
- **Query Parameters:** `group_id` (optional UUID)
- **Response (200 OK):** `Array<CategoryRead>`

### `GET /categories/{category_id}`
Retrieve single category by UUID.
- **Response (200 OK):** [`CategoryRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L42-L52)

### `PUT /categories/{category_id}`
Update category fields (name, group_id, sort_order, type, is_active).
- **Request Body:** Partial [`CategoryUpdate`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L54-L60)
- **Response (200 OK):** [`CategoryRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L42-L52)

### `DELETE /categories/{category_id}`
Delete category. Cascade deletes associated budget records; un-sets category_id on linked transactions (`SET NULL`).
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
- **Response (200 OK):** `{"status": "ok", "updated": 2}`

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
- **Response (201 Created):** [`BudgetRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L185-L192)

### `GET /budget/`
Query budgets, optionally filtered by month or category.
- **Query Parameters:** `budget_month` (optional date `YYYY-MM-01`), `category_id` (optional UUID)
- **Response (200 OK):** `Array<BudgetRead>`

### `GET /budget/{budget_id}`
Retrieve a budget record.
- **Response (200 OK):** [`BudgetRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L185-L192)

### `PUT /budget/{budget_id}`
Update planned amount or month.
- **Request Body:** `{"planned_amount": 500.00}`
- **Response (200 OK):** [`BudgetRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L185-L192)

### `DELETE /budget/{budget_id}`
Delete a budget record.
- **Response (204 No Content)**

---

## 4. Transactions

Ledger for spending, deposits, and transfers.

> [!IMPORTANT]
> **Amount Convention:** Outflow (money spent) is positive (`+50.00`); Inflow (income/deposit) is negative (`-2500.00`).

### `GET /transactions/`
Search and filter transactions with server-side pagination.
- **Query Parameters:**
  - `account_id` (UUID, optional)
  - `category_id` (UUID, optional)
  - `start_date` (`YYYY-MM-DD`, optional)
  - `end_date` (`YYYY-MM-DD`, optional)
  - `uncategorized` (`bool`, optional) - filter transactions with `category_id IS NULL`
  - `q` (`str`, optional) - case-insensitive substring search on description
  - `limit` (`int`, default: 50)
  - `offset` (`int`, default: 0)
- **Response (200 OK):** [`TransactionListResponse`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L165-L170)
  ```json
  {
    "items": [...],
    "total": 142,
    "limit": 50,
    "offset": 0
  }
  ```

### `GET /transactions/{transaction_id}`
Retrieve a single transaction with joined account details.
- **Response (200 OK):** [`TransactionRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L145-L159)

### `POST /transactions/`
Manually create a single transaction.
- **Request Body:**
  ```json
  {
    "account_id": "account-uuid",
    "category_id": "category-uuid",
    "description": "Trader Joe's",
    "amount": 78.45,
    "date": "2026-03-15",
    "pending": false
  }
  ```
- **Response (201 Created):** [`TransactionRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L145-L159)

### `PUT /transactions/{transaction_id}`
Update category assignment, description, or transfer flag.
- **Request Body:**
  ```json
  {
    "category_id": "category-uuid",
    "description": "Trader Joe's (Grocery)",
    "is_transfer": false
  }
  ```
- **Response (200 OK):** [`TransactionRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L145-L159)

### `DELETE /transactions/{transaction_id}`
Delete a transaction by UUID.
- **Response (200 OK):** Deleted transaction object

---

## 5. Accounts

Manage financial accounts (checking, savings, credit cards, loans).

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
List all accounts.
- **Response (200 OK):** `Array<AccountRead>`

### `POST /accounts/`
Create a manual account.
- **Request Body:**
  ```json
  {
    "name": "USAA Checking",
    "type": "depository",
    "subtype": "checking",
    "starting_balance": 1500.00,
    "current_balance": 1500.00,
    "currency": "USD",
    "is_active": true
  }
  ```
- **Response (201 Created):** [`AccountRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L90-L115)

### `PUT /accounts/{account_id}`
Update account metadata (name, type, subtype, starting_balance, current_balance, is_active).
- **Response (200 OK):** [`AccountRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L90-L115)

### `DELETE /accounts/{account_id}`
Delete an account and its associated transactions.
- **Response (204 No Content)**

---

## 6. Credit Cards & Transfers

Dedicated endpoints for tracking revolving credit debt and matching inter-account transfers.

### `GET /credit-cards/summary`
Calculates cumulative credit debt and monthly activity per credit card.
- **Query Parameter:** `month` (`YYYY-MM`, required)
- **Response (200 OK):** [`CreditCardSummaryResponse`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L277-L280)
  - `cards[].balance_owed`: `starting_balance + sum(all-time transactions)`
  - `cards[].charges_this_month`: sum of positive non-transfer transactions
  - `cards[].payments_this_month`: absolute sum of negative transactions
  - `cards[].transactions`: list of transactions for this month

### `GET /credit-cards/transfer-candidates`
Scans database for matching inter-account transfers across different accounts within a 2-day window where neither side has `is_transfer = true`.
- **Response (200 OK):** `Array<TransferCandidate>`
  - `inflow_side`: negative transaction (money received)
  - `outflow_side`: positive transaction (money paid out)
  - Account names for both sides

### `POST /credit-cards/mark-transfers`
Marks one or more transactions with `is_transfer = true`.
- **Request Body:**
  ```json
  {
    "transaction_ids": ["txn-uuid-1", "txn-uuid-2"]
  }
  ```
- **Response (204 No Content)**

---

## 7. CSV Statement Upload

Parse, inspect, format, and import bank exports with duplicate detection.

### `POST /upload/inspect`
Inspects an uploaded CSV file without importing data or requiring a destination account:
- Reads file stream and decodes using UTF-8 BOM (`utf-8-sig`).
- Extracts CSV headers and up to 3 bounded sample rows of raw source values as positional lists (`sample_rows[row][column]` corresponds to `headers[column]`).
- Loads persisted custom format configurations and combines with built-in format candidates (`usaa`, `discover`).
- Runs pure header auto-detection against all candidates.
- **Form Data:**
  - `file`: CSV file binary (`UploadFile`)
- **Response (200 OK):** [`CSVInspectResponse`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L437-L443)
  ```json
  {
    "headers": ["Date", "Description", "Amount", "Category", "Status"],
    "sample_rows": [
      ["2026-05-01", "Grocery Store", "45.20", "Food", "posted"],
      ["2026-05-03", "Gas Station", "30.00", "Transportation", "posted"]
    ],
    "status": "detected",
    "detected_format": {
      "identifier": "usaa",
      "name": "USAA"
    },
    "matches": [
      {
        "identifier": "usaa",
        "name": "USAA"
      }
    ]
  }
  ```
  - `status`: `"unknown"` (0 matches), `"detected"` (exactly 1 match), or `"ambiguous"` (2+ matches).
  - `detected_format`: Populated only when `status == "detected"`.
  - `sample_rows`: Positional string arrays (NOT objects keyed by header names). Preserves duplicate header columns, long rows, and short rows.
- **Error Responses:**
  - `422 Unprocessable Entity`: File cannot be decoded as UTF-8, file is empty, or header row is missing/invalid.

### `GET /upload/formats`
Lists all user-defined persisted custom CSV format configurations, ordered by name case-insensitively ascending. Excludes built-in formats (USAA and Discover are code constants).
- **Response (200 OK):** `Array<CSVFormatRead>` ([`CSVFormatRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L413-L426))
  ```json
  [
    {
      "id": "e5c1505b-801b-4f99-9ea2-349f485dbba6",
      "name": "My Credit Union",
      "date_column": "Posting Date",
      "description_column": "Details",
      "amount_column": "Amount",
      "status_column": "Type",
      "date_format": "%m/%d/%Y",
      "amount_sign_convention": "positive_is_outflow",
      "status_posted_value": "posted",
      "created_at": "2026-09-27T18:00:00Z"
    }
  ]
  ```

### `POST /upload/formats`
Creates and persists a new custom CSV format definition.
- **Request Body (JSON):** [`CSVFormatCreate`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L359-L411)
  ```json
  {
    "name": "My Credit Union",
    "date_column": "Posting Date",
    "description_column": "Details",
    "amount_column": "Amount",
    "status_column": "Type",
    "date_format": "%m/%d/%Y",
    "amount_sign_convention": "positive_is_outflow",
    "status_posted_value": "posted"
  }
  ```
  - `name`: Unique name (case-insensitive check, cannot collide with reserved names `"usaa"` or `"discover"`).
  - `date_column`, `description_column`, `amount_column`: Source column names (must be mutually distinct).
  - `status_column`: Optional source column distinguishing posted vs pending items.
  - `date_format`: Python `datetime.strptime` pattern (e.g. `%Y-%m-%d`, `%m/%d/%Y`).
  - `amount_sign_convention`: `"positive_is_outflow"` (charges positive) or `"positive_is_inflow"` (deposits positive, charges negative).
  - `status_posted_value`: Value indicating a posted transaction. If `status_column` is absent (`null`), `status_posted_value` is canonicalized to `null`. If `status_column` is present and token is omitted/blank, defaults to `"posted"`. If a custom token is supplied, it is trimmed and lowercased (e.g. `"  CLEARED  "` becomes `"cleared"`).
- **Response (201 Created):** [`CSVFormatRead`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L413-L426)
- **Error Responses:**
  - `400 Bad Request`: Non-distinct column mappings or invalid parameters.
  - `409 Conflict`: Name collides with built-in or existing format, or an identical semantic configuration already exists.

### `POST /upload/preview`
Multipart form upload that parses a CSV file using an explicit format identifier and returns row-by-row previews without persisting data.
- **Form Data:**
  - `file`: CSV file binary (`UploadFile`)
  - `account_id`: Destination account UUID
  - `format`: Explicit format identifier (`"usaa"`, `"discover"`, or a custom `CSVFormat` UUID). *Note: Preview does not perform auto-detection; format must be specified.*
- **Response (200 OK):** [`CSVPreviewResponse`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L339-L345)
  - `total_rows`: Total rows read
  - `valid_rows`: Number of successfully parsed transaction rows
  - `error_rows`: Number of rows that encountered parsing errors
  - `rows[]`: Array of [`CSVTransactionRow`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L328-L336) (`row_number`, `transaction_date`, `description`, `amount`, `pending`, `parse_error`)
- **Error Responses:**
  - `400 Bad Request`: Unknown built-in format identifier string.
  - `404 Not Found`: Target account or custom format UUID not found in database.

### `POST /upload/confirm`
Parses and imports the CSV into the database with duplicate prevention and non-fatal row error isolation.
- **Form Data:**
  - `file`: CSV file binary (`UploadFile`)
  - `account_id`: Destination account UUID
  - `format`: Explicit format identifier (`"usaa"`, `"discover"`, or a custom `CSVFormat` UUID). *Note: Confirm does not perform auto-detection; format must be specified.*
- **Response (200 OK):** [`CSVImportResult`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L347-L352)
  - `imported`: Count of inserted and committed rows
  - `skipped`: Count of duplicate rows skipped (`account_id + date + amount + description` match)
  - `errors`: List of non-fatal row warnings logged during parsing or staging
- **Error Responses:**
  - `400 Bad Request`: Unknown format string.
  - `404 Not Found`: Target account or custom format UUID not found.
  - `422 Unprocessable Entity`: Whole-file parse failure (missing required header columns).

---

## 8. Summaries & Dashboard

Aggregated financial metrics for budgeting and dashboard visualization.

### `GET /summary/budget`
Computes group-by-group zero-based budgeting breakdown for a specific month.
- **Query Parameter:** `month` (`YYYY-MM`, required)
- **Response (200 OK):** [`BudgetSummaryResponse`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L214-L222)
  - `total_income_planned`, `total_income_actual`
  - `total_expense_planned`, `total_expense_actual`
  - `to_be_assigned`: `total_income_planned - total_expense_planned`
  - `groups[]`: category groups with nested planned, actual, remaining, and `is_over_budget`

### `GET /summary/dashboard`
Consolidated view for dashboard home page.
- **Query Parameter:** `month` (`YYYY-MM`, required)
- **Response (200 OK):** [`DashboardSummaryResponse`](file:///Users/west/programming_stuff/budget_app/backend/schemas.py#L242-L253)
  - Income and expense KPIs (planned vs actual)
  - Total balance across active depository accounts
  - Group stats for high-level charts
  - List of connected accounts with balances
  - Latest recent transactions

---

## 9. Plaid Bank Integration

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
- **Response (200 OK):** `{"synced": 15}`
