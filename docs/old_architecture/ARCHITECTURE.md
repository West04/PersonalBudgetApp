# System Architecture

This document describes the high-level architecture, design patterns, domain logic, and component interactions of the Personal Budget App.

---

## 1. System Overview

The Personal Budget App is a full-stack personal finance application designed around the **zero-based budgeting methodology** (assign every dollar a job). It supports dual ingestion methods for financial data: automated bank syncing via **Plaid** and manual statement importing via **CSV bank exports**.

```mermaid
flowchart TD
    subgraph Client ["Client Browser"]
        UI["Nuxt 4 / Vue 3 SPA<br/>(Port 12345)"]
    end

    subgraph ReverseProxy ["Nuxt Nitro Server"]
        Proxy["Proxy Route Rules<br/>/api/** &rarr; backend:8000/**"]
    end

    subgraph Backend ["FastAPI Backend (Port 12344 / 8000)"]
        Router["Presentation Routers<br/>(backend/routers/)"]
        Mgr["Workflow Managers<br/>(backend/managers/)"]
        Engine["Domain Engines<br/>(backend/domain/)"]
        Access["ResourceAccess<br/>(backend/access/)"]
        Loader["Statement Loaders<br/>(USAA, Discover, Mapped)"]
        Lifespan["App Lifespan<br/>(Auto DDL & Default Seed)"]
    end

    subgraph Database ["PostgreSQL 18 (Port 5432)"]
        DB[(budget_app Database)]
    end

    subgraph External ["External Services"]
        PlaidAPI["Plaid API<br/>(Link, Accounts, Transactions)"]
    end

    UI -->|All /api calls| Proxy
    Proxy -->|Internal Docker network| Router
    Router --> Mgr
    Router --> Access
    Router --> Loader
    Mgr --> Engine
    Mgr --> Access
    Mgr --> Loader
    Access --> DB
    Access --> PlaidAPI
    Lifespan --> DB
```

---

## 2. Technology Stack

| Layer | Technology | Version / Details | Purpose |
|---|---|---|---|
| **Frontend Framework** | [Nuxt](https://nuxt.com/) | 4.2+ | Modern SSR/SPA framework with file-based routing and Vite |
| **UI Library** | [Vue.js](https://vuejs.org/) | 3.5+ | Composition API, `<script setup>`, reactive state |
| **Drag & Drop** | [vuedraggable](https://github.com/SortableJS/vue.draggable.next) | 4.1+ | Reordering category groups and categories |
| **Backend Framework** | [FastAPI](https://fastapi.tiangolo.com/) | 0.115+ | High-performance Python web API with OpenAPI/Swagger docs |
| **ORM / Data Layer** | [SQLAlchemy](https://www.sqlalchemy.org/) | 2.x | Relational mapping, eager loading (`selectinload`, `joinedload`) |
| **Data Validation** | [Pydantic](https://docs.pydantic.dev/) | 2.x | Schema validation, `ConfigDict(from_attributes=True)`, `condecimal` |
| **Database** | [PostgreSQL](https://www.postgresql.org/) | 18 | Relational database with UUID keys and numeric decimals |
| **Bank Sync** | [Plaid Python SDK](https://github.com/plaid/plaid-python) | Latest | Bank authentication and transaction synchronization |
| **CSV Parsing** | Python Standard Library | `csv`, `io` | Custom statement parser abstraction for bank CSVs |
| **Containerization** | [Docker Compose](https://docs.docker.com/compose/) | 3.8+ | Multi-container orchestration (backend, frontend, postgres) |

---

## 3. Core Domain Concepts & Business Rules

### 3.1 Transaction Amount Sign Convention

All transaction records follow a strict accounting sign convention across the entire database:

$$\text{Outflow (Spending / Charges / Debits)} > 0 \quad (\text{Positive})$$
$$\text{Inflow (Income / Deposits / Credits)} < 0 \quad (\text{Negative})$$

- **Purchases & Expenses:** When money leaves an account (e.g. paying \$50 for groceries), `amount = 50.00`.
- **Income & Deposits:** When money enters an account (e.g. paycheck of \$2,500), `amount = -2500.00`.
- **Credit Card Charges:** Buying an item on credit increases balance owed; `amount = 45.00`.
- **Credit Card Payments:** Money sent from checking to credit card reduces debt; appears as `amount = -150.00` on the credit card account and `amount = 150.00` on the checking account.

### 3.2 Zero-Based Budgeting (ZBB) Calculation

The core philosophy assigns every dollar of expected income to a specific category:

$$\text{To Be Assigned} = \text{Total Income Planned} - \text{Total Expense Planned}$$

- When $\text{To Be Assigned} = 0$: **"Every dollar has a job!"** The budget is balanced.
- When $\text{To Be Assigned} > 0$: Unassigned funds remain to be allocated.
- When $\text{To Be Assigned} < 0$: The user is over-budgeted.

#### Monthly Category Actuals & Remaining Math
In [`backend/routers/summaries.py`](file:///Users/west/programming_stuff/budget_app/backend/routers/summaries.py):
- **For `type == "expense"` categories:**
  - $\text{Actual} = \sum \text{Transaction.amount}$ (where amount > 0 for outflows)
  - $\text{Remaining} = \text{Planned} - \text{Actual}$
  - $\text{Is Over Budget} = \text{Actual} > \text{Planned}$
- **For `type == "income"` categories:**
  - Transactions for income are stored as negative numbers (inflow), so:
  - $\text{Actual} = -1 \times \sum \text{Transaction.amount}$
  - $\text{Remaining} = \text{Planned} - \text{Actual}$
  - $\text{Is Over Budget} = \text{Actual} < \text{Planned}$ (i.e. did not meet planned income goal)

### 3.3 Credit Card Debt & Balance Model

Credit cards require special handling because balances accumulate over time and payments cross accounts:

1. **Balance Owed Formula:**
   $$\text{Balance Owed} = \text{Starting Balance} + \sum_{\text{all-time}} \text{Transaction.amount}$$
   Since charges are positive and payments/credits are negative, the all-time net sum directly yields the current unpaid debt.
2. **Monthly Charges:**
   $$\text{Charges This Month} = \sum \text{Transaction.amount} \quad \text{where } \text{amount} > 0 \text{ and } \text{is\_transfer} = \text{False}$$
3. **Monthly Payments:**
   $$\text{Payments Received} = \left| \sum \text{Transaction.amount} \right| \quad \text{where } \text{amount} < 0$$

### 3.4 Automated Inter-Account Transfer Matching

Credit card payments or checking-to-savings transfers generate two distinct records:
1. An outflow on Account A (+X)
2. An inflow on Account B (-X)

If unaddressed, these would distort spending and income reports. The backend reconciliation engine in [`backend/domain/reconciliation.py`](file:///Users/west/programming_stuff/budget_app/backend/domain/reconciliation.py) (`detect_transfer_candidates`) provides an automated heuristic:
- Matches any unlinked inflow (`amount < 0`, `is_transfer == False`) on one account with an unlinked outflow (`amount > 0`, `is_transfer == False`) on a *different* account.
- **Criteria:** Exactly identical absolute amount and $| \text{date}_{\text{outflow}} - \text{date}_{\text{inflow}} | \le 2\text{ days}$.
- Returns pairs as candidate transfers for user review or batch approval via `POST /credit-cards/mark-transfers`.

---

## 4. Ingestion Architecture

```mermaid
flowchart LR
    subgraph BankSync ["Plaid Ingestion"]
        P1["Plaid Link UI"] -->|public_token| P2["POST /plaid/exchange_public_token"]
        P2 -->|Stores encrypted access_token| P3["PlaidItem in DB"]
        P4["POST /plaid/sync_transactions"] -->|Plaid Sync API / cursor| P5["Upsert Transactions"]
    end

    subgraph CSVIngestion ["CSV Statement Ingestion (Upload-First)"]
        C1["User selects CSV File"] --> C2["POST /upload/inspect"]
        C2 --> C3["Backend inspects headers & sample rows<br/>Auto-detects format (detected / ambiguous / unknown)"]
        C3 --> C4["Frontend Step 1: displays detection state<br/>(Optional: Save custom mapping via POST /upload/formats)"]
        C4 --> C5["User selects Target Account (Step 2) & clicks Preview"]
        C5 --> C6["POST /upload/preview"]
        C6 --> C7["_resolve_statement_loader()<br/>(USAA, Discover, or MappedStatementLoader)"]
        C7 -->|Parses & validates rows| C8["Step 3: Preview Table & Confirm Action"]
        C8 -->|User clicks Confirm / Import| C9["POST /upload/confirm"]
        C9 -->|Duplicate Check via csv_import_manager<br/>(account_id + date + amount + description)| C10["Step 4: Done (Import Results)"]
    end
```

### 4.1 Plaid Integration
- Uses Plaid Link token workflow.
- Stores access token encoded with base64 placeholder (production migration planned for cryptographic encryption via Fernet/KMS).
- Tracks `transactions_cursor` on the `PlaidItem` model for incremental synchronization.
- Maps Plaid account categories to application account types (`depository`, `credit`, `investment`, `loan`, `other`).

### 4.2 Bank Statement Loader Pattern
- Implemented as an extensible Abstract Base Class (`BankStatementLoader` in [`backend/bank_statement_loader.py`](file:///Users/west/programming_stuff/budget_app/backend/bank_statement_loader.py)). Under Volatility-Based Decomposition, this represents an ingestion/parsing boundary adapting messy external bank representations, not a pure business calculation Engine.
- Built-in concrete loaders:
  - `USAALoader`: Handles USAA CSV exports (dates: `%Y-%m-%d`, sign: negative=debit, positive=credit). Structurally requires `Date`, `Description`, `Category`, `Amount`, `Status` (where source `Category` is bank-assigned categorization, distinct from user budget categories).
  - `DiscoverLoader`: Handles Discover CSV exports (dates: `%m/%d/%Y`, sign: positive=debit, negative=credit). Structurally requires `Trans. Date`, `Description`, `Amount`, `Category`.
- Configurable parser:
  - `MappedStatementLoader`: Driven by `MappedCSVFormatConfig` to support arbitrary user-defined CSV column mappings persisted in `models.CSVFormat`.
- Loader Resolution:
  - Built-in lookup: `get_loader(format_name, account_id)` using `LOADER_REGISTRY` in [`backend/bank_statement_loader.py`](file:///Users/west/programming_stuff/budget_app/backend/bank_statement_loader.py).
  - Endpoint resolution: Router helper `_resolve_statement_loader(db, account_id, format_identifier)` in [`backend/routers/upload.py`](file:///Users/west/programming_stuff/budget_app/backend/routers/upload.py) resolves built-ins via `get_loader` or custom formats by UUID lookup via [`backend/access/csv_format_access.py`](file:///Users/west/programming_stuff/budget_app/backend/access/csv_format_access.py), constructing a `MappedStatementLoader(account_id=account_id, config=config)`.
- Header auto-detection: `detect_csv_format(headers, formats)` checks whether candidate required headers are a subset of uploaded headers ($required\_headers \subseteq uploaded\_headers$) using exact string comparison (case-sensitive, whitespace-sensitive, punctuation-sensitive; BOM handled via `utf-8-sig`), permitting extra columns and classifying files as `detected` (unique match), `ambiguous` (multiple matches), or `unknown` (no match).

---

## 5. Frontend Architecture

### 5.1 Page Layout & Navigation
The application uses a persistent sidebar defined in [`frontend/app/app.vue`](file:///Users/west/programming_stuff/budget_app/frontend/app/app.vue). The sidebar is collapsible and provides navigation to:
- **Dashboard (`/dashboard`):** Monthly financial summary, account balances, and recent transactions.
- **Categories & Budget (`/categories`):** Combined category manager and monthly budget planner with drag-and-drop reordering.
- **Transactions (`/transactions`):** Searchable, paginated transaction ledger with filters for account, category, uncategorized transactions, and inline updates.
- **Accounts (`/accounts`):** Grouped account list by category (depository, credit, loan, etc.) with balance tracking and CRUD modals.
- **Credit Cards (`/credit-cards`):** Debt tracking, monthly charge/payment breakdowns, and transfer matching review.
- **Upload (`/upload`):** Upload-first CSV statement ingestion wizard: inspects CSV files, auto-detects formats or supports custom column mappings, binds to target accounts, previews parsed rows with error reporting, and confirms deduplicated imports.
- **Settings (`/settings`):** User preferences placeholder.
- **Index (`/`):** Redirects automatically to `/dashboard`.

### 5.2 API Communication Pattern
1. **Server-Side Proxy:** Nuxt routes `/api/**` to backend via Nitro server proxy in [`frontend/nuxt.config.ts`](file:///Users/west/programming_stuff/budget_app/frontend/nuxt.config.ts). All frontend pages and components standardize on `const API_BASE = '/api'`, avoiding hardcoded backend ports or direct client-to-backend CORS dependencies.
2. **CORS:** FastAPI configures `CORSMiddleware` as a defense-in-depth fallback for direct requests during local development.
3. **Data Types Composable:** Shared account types and sub-type definitions are centralized in [`frontend/app/composables/useAccountTypes.ts`](file:///Users/west/programming_stuff/budget_app/frontend/app/composables/useAccountTypes.ts) and kept in sync with backend `ACCOUNT_SUBTYPES`.
