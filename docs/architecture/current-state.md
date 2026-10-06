# Current State Architecture & System Analysis

## 1. Executive Summary
The Personal Budget App is a full-stack personal finance application built on the zero-based budgeting (ZBB) methodology. It supports automated bank syncing via Plaid and manual CSV statement uploads (with automatic header detection, custom format persistence, upload-first workflow, and route-query synchronized ledger). This document records the current architectural implementation, components, data flows, and known defects/unresolved items at HEAD (`5f4e4e5`).

---

## 2. Technology Stack & Infrastructure

| Layer | Technologies | Key Libraries & Specifications |
|---|---|---|
| **Backend API** | Python 3.11, FastAPI 0.115+ | Uvicorn, Pydantic v2 (`ConfigDict`, `condecimal`), `python-dotenv`, `python-multipart` |
| **ORM & Database** | SQLAlchemy 2.x, PostgreSQL 18 | `psycopg2-binary`, `UUID`, `DECIMAL(10,2)`, `DECIMAL(12,2)`, 7 models (`CategoryGroup`, `Category`, `Budget`, `Account`, `Transaction`, `PlaidItem`, `CSVFormat`) |
| **Integrations** | Plaid Python SDK, `requests` | Direct HTTP calls to `/transactions/sync`, `csv`, `io` |
| **Security** | Python Standard Library | `base64` placeholder token encoding (security migration pending) |
| **Frontend SPA** | Nuxt 4 (`^4.2.2`), Vue 3 (`^3.5.26`) | Composition API, `<script setup>`, Vue Router 4, `vuedraggable` (`^4.1.0`) |
| **Orchestration** | Docker Compose | Backend (`:12344`), Frontend (`:12345`), Postgres (`:5432`) |

---

## 3. Entry Points & Runtime Initialization

1. **Backend Lifespan Entry (`backend/main.py`):**
   - Runs `models.Base.metadata.create_all(bind=engine)` to auto-provision database tables.
   - Invokes `init_db(db)` from `backend/initial_data.py` to seed default category groups (Income, Saving, Housing, Food, Transportation).
   - Configures CORS middleware for `http://localhost:3000` and `http://localhost:12345`.
   - Registers 8 routers: `categories`, `budgets`, `transactions`, `plaid`, `summaries`, `accounts`, `upload`, `credit_cards`.
2. **Frontend Root Layout (`frontend/app/app.vue`):**
   - Renders a collapsible sidebar navigation menu.
   - Hosts `<NuxtPage />` routed views.
   - `frontend/app/pages/index.vue` redirects root traffic to `/dashboard`.
3. **Docker Networking & Proxy Rules:**
   - Nuxt's Nitro server proxies `/api/**` to `http://backend:8000/**`.
   - All frontend views (`dashboard.vue`, `transactions.vue`, `credit-cards.vue`, `upload.vue`, `accounts.vue`, `categories.vue`) consistently communicate via `/api/**`.

---

## 4. Module Map & Responsibilities

```
backend/
├── main.py                     # App creation, lifespan DDL/seeding, router mounting
├── database.py                 # Engine creation, SessionLocal factory, get_db dependency
├── models.py                   # 7 SQLAlchemy models (CategoryGroup, Category, Budget, Account, Transaction, PlaidItem, CSVFormat)
├── schemas.py                  # Pydantic v2 schemas and ACCOUNT_SUBTYPES definition
├── security.py                 # Base64 placeholder token encoding (security migration pending)
├── initial_data.py             # Default category group and category seed records
├── bank_statement_loader.py    # BankStatementLoader ABC, USAA/Discover, MappedStatementLoader, MappedCSVFormatConfig, detect_csv_format
├── access/                     # Concrete PostgreSQL & external ResourceAccess
│   ├── account_access.py       # Account persistence, active filters, starting balances
│   ├── budget_access.py        # Monthly budget allocation queries and CRUD
│   ├── category_access.py      # Category/Group CRUD, hierarchy queries, sort_order updates
│   ├── csv_format_access.py    # CSVFormat persistence, uniqueness validation, mapped config converters
│   ├── plaid_access.py         # Plaid SDK client, link-token creation, account balance queries
│   ├── plaid_item_access.py    # PlaidItem lookup and cursor persistence
│   ├── plaid_transaction_access.py # Dedicated raw HTTP /transactions/sync client
│   └── transaction_access.py   # Transaction queries, CSV duplicate detection, staging, transfer flags
├── domain/                     # Pure business calculation Engines (no DB, no FastAPI)
│   ├── budgeting.py            # Zero-based budget calculations (planned, actual, to_be_assigned)
│   ├── credit_cards.py         # Credit card balance_owed, charges, payments calculations
│   ├── dates.py                # Month range determination helpers
│   └── reconciliation.py       # Transfer candidate matching heuristic
├── managers/                   # Workflow orchestration Managers
│   ├── budget_summary_manager.py     # Coordinates category, budget, transaction access and budgeting engine
│   ├── credit_card_summary_manager.py # Coordinates credit accounts (account_access), transaction history (transaction_access), and credit card engine
│   ├── csv_import_manager.py         # Coordinates account verification, statement parsing, deduplication, batch commit
│   ├── dashboard_summary_manager.py  # Composes budget summary, account balances, and recent activity
│   ├── plaid_account_sync_manager.py # Coordinates Plaid account balance sync and account persistence
│   ├── plaid_transaction_sync_manager.py # Coordinates cursor pagination, transaction sync, event commits
│   └── transfer_reconciliation_manager.py # Coordinates unmatched candidate search and reconciliation engine
├── crud/
│   └── plaid.py                # Legacy Plaid CRUD (pending final deprecation audit)
└── routers/                    # Presentation / FastAPI route handlers
    ├── accounts.py             # Account CRUD (routes to account_access)
    ├── budgets.py              # Budget allocation CRUD (routes to budget_access)
    ├── categories.py           # Category & Group management and reordering (routes to category_access)
    ├── credit_cards.py         # CC summaries, transfer candidate search, and mark-transfers
    ├── plaid.py                # Link tokens, token exchange, account/tx sync endpoints
    ├── summaries.py            # Budget & Dashboard summary aggregations
    ├── transactions.py         # Paginated transaction ledger and category assignment (routes to transaction_access)
    └── upload.py               # Inspect (/upload/inspect), format management (/upload/formats), preview, confirm
```

---

## 5. Core Domain Logic & Accounting Rules

1. **Monetary Sign Convention Invariant:**
   - Outflow / Debit / Purchase / Charge: **Positive (> 0)**
   - Inflow / Credit / Deposit / Income: **Negative (< 0)**
2. **Zero-Based Budgeting (ZBB):**
   $$\text{to\_be\_assigned} = \text{total\_income\_planned} - \text{total\_expense\_planned}$$
   - Expense Actuals: $\sum \text{Transaction.amount}$ (outflows > 0)
   - Income Actuals: $-1 \times \sum \text{Transaction.amount}$ (inflows < 0 converted to positive for display)
   - Expense Category Remaining: $\text{planned} - \text{actual}$
3. **Credit Card Debt Model:**
   $$\text{balance\_owed} = \text{starting\_balance} + \sum_{\text{all-time}} \text{Transaction.amount}$$
   - Charges: Sum of positive non-transfer transactions in current month.
   - Payments: Absolute sum of negative transactions in current month.
   - Note on Sign Convention: When cumulative payments and credits exceed charges from a $0.00 baseline, `balance_owed` calculates as negative. Surfacing negative balances as an overpayment / credit balance vs. outstanding debt is a deferred presentation decision, not a calculation defect; the underlying calculation is preserved.
4. **Transfer Matching Heuristic:**
   - Evaluates unlinked inflows (`amount < 0`, `is_transfer == False`) against unlinked outflows (`amount > 0`, `is_transfer == False`).
   - Pairs them if $|\text{date}_{\text{outflow}} - \text{date}_{\text{inflow}}| \le 2\text{ days}$ and $\text{account}_{\text{outflow}} \ne \text{account}_{\text{inflow}}$.
   - Approval sets `is_transfer = True` on both records, excluding them from spending calculations.

---

## 6. Structural Modernization & Remaining Known Items

### 6.1. Addressed Through VBD Decomposition
1. **Persistence Decoupled from Route Handlers:** Raw SQLAlchemy queries have been moved from routers into focused, concrete ResourceAccess modules (`backend/access/`). Simple CRUD routes terminate directly at ResourceAccess without unnecessary Managers.
2. **Business Calculations Extracted to Pure Engines:** Zero-based budgeting formulas, credit card balance calculations, and transfer candidate matching heuristics live in pure, infrastructure-free functions in `backend/domain/`.
3. **Meaningful Workflow Sequencing Isolated in Managers:** Multi-step pipelines (summaries, statement import confirmation, Plaid account and transaction syncing) are orchestrated by focused Managers in `backend/managers/`.
4. **Ingestion & Custom CSV Formats Separated:** CSV statement interpretation is isolated behind the ingestion/parser boundary (`BankStatementLoader` and `MappedStatementLoader`), custom format configurations are persisted in `CSVFormat` via `csv_format_access`, and detection is performed by a simple deterministic ingestion helper (`detect_csv_format`).
5. **Proxy Consistency:** All frontend pages use `/api/**` via the Nuxt Nitro proxy.

### 6.2. Preserved Known Defects & Unresolved Domain Items
1. **`Transaction.description` Database/Schema Nullability Mismatch (Known Defect):**
   `models.Transaction.description` is nullable in PostgreSQL, but Pydantic schemas enforce non-null `str`. Querying rows with `NULL` descriptions via standard endpoints causes serialization errors. Pinned via characterization test; preserved pending an intentional database/API migration slice.
2. **CategoryGroup Backend Deletion Cascade Inconsistency (Known Defect):**
   `backend/routers/categories.py` allows cascading deletion of category groups and child categories, whereas `frontend/app/pages/categories.vue` blocks deleting non-empty groups. Preserved pending an intentional behavior decision.
3. **Credit Card `balance_owed` Includes Transfers While `charges_this_month` Excludes Them (Unresolved Domain Decision):**
   In `credit_cards.py`, `balance_owed` includes all transactions (including `is_transfer == True`), while `charges_this_month` filters out transfers. Pinned via characterization test.
4. **Credit Card `balance_owed` Includes Future-Dated Transactions (Unresolved Domain Decision):**
   All-time sum currently evaluates transactions regardless of whether `date` is in the future. Pinned via characterization test.
5. **Transfer Matching Greedy / Order-Dependent (Unresolved Domain Decision):**
   `detect_transfer_candidates` pairs transactions greedily in input list order without closest-date tie-breaking. Pinned via characterization test.
6. **Insecure Credential Storage (Security Migration Pending):**
   `backend/security.py` uses base64 string encoding instead of real cryptographic encryption. Plaid access tokens require migration to Fernet/KMS key management in a dedicated security slice.
7. **Frontend Timezone Offset in Transaction Range End Date (`end_date` Calculation):**
   In `frontend/app/pages/transactions.vue`, `end_date` is computed as `new Date(Number(year), Number(month), 0).toISOString().slice(0, 10)`. Converting local midnight of the month's final day to UTC shifts the date back by one calendar day in positive UTC offset timezones (e.g. `2026-09-29` instead of `2026-09-30`), truncating end-of-month transactions. Preserved pending a focused frontend date utility fix.
8. **Reconciled Plaid Corrections (Unresolved Follow-Up):**
   Material provider corrections to already-reconciled transactions are currently blocked from mutating reconciled financial history. A future explicit workflow must define how reconciliation history is reopened or adjusted.

