# Current State Architecture & System Analysis

## 1. Executive Summary
The Personal Budget App is a full-stack personal finance application built on the zero-based budgeting (ZBB) methodology. It supports automated bank syncing via Plaid and manual CSV statement uploads. This document documents the existing architectural implementation, components, data flows, and structural issues identified during reverse engineering.

---

## 2. Technology Stack & Infrastructure

| Layer | Technologies | Key Libraries & Specifications |
|---|---|---|
| **Backend API** | Python 3.11/3.12, FastAPI 0.115+ | Uvicorn, Pydantic v2 (`ConfigDict`, `condecimal`), `python-dotenv` |
| **ORM & Database** | SQLAlchemy 2.x, PostgreSQL 18 | `psycopg2-binary`, `UUID`, `DECIMAL(10,2)`, `DECIMAL(12,2)` |
| **Integrations** | Plaid Python SDK, `requests` | Direct HTTP calls to `/transactions/sync`, `csv`, `io` |
| **Security** | Python Standard Library | `base64` placeholder token encoding |
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
   - Inconsistency: `dashboard.vue` and `transactions.vue` bypass the proxy and target `http://localhost:12344` directly, whereas `credit-cards.vue`, `upload.vue`, `accounts.vue`, and `categories.vue` consume `/api/**`.

---

## 4. Module Map & Responsibilities

```
backend/
├── main.py                     # App creation, lifespan DDL/seeding, router mounting
├── database.py                 # Engine creation, SessionLocal factory, get_db dependency
├── models.py                   # 6 SQLAlchemy models in a single monolithic file
├── schemas.py                  # Pydantic schemas and ACCOUNT_SUBTYPES definition
├── security.py                 # Base64 encode/decode masquerading as encryption
├── initial_data.py             # Default category group and category seed records
├── bank_statement_loader.py    # BankStatementLoader ABC, USAALoader, DiscoverLoader
├── crud/
│   ├── budget.py               # Budget model queries
│   ├── category.py             # Category & CategoryGroup queries and reordering
│   ├── plaid.py                # PlaidItem and Account sync queries
│   └── transaction.py          # Transaction listing, update, and Plaid sync helpers
└── routers/
    ├── accounts.py             # Account CRUD (bypasses crud layer, raw DB queries)
    ├── budgets.py              # Budget CRUD endpoints
    ├── categories.py           # Category & Group management and reordering
    ├── credit_cards.py         # CC balances, monthly metrics, transfer matching heuristic
    ├── plaid.py                # Link tokens, token exchange, account/tx sync endpoints
    ├── summaries.py            # Budget & Dashboard summary aggregations (ZBB calculations)
    ├── transactions.py         # Paginated transaction ledger and category assignment
    └── upload.py               # Multipart CSV preview and confirm endpoints
```

---

## 5. Core Domain Logic & Accounting Rules

1. **Monetary Sign Convention Invariant:**
   - Outflow / Debit / Purchase / Charge: **Positive (> 0)**
   - Inflow / Credit / Deposit / Income: **Negative (< 0)**
2. **Zero-Based Budgeting (ZBB):**
   $$\text{to\_be\_assigned} = \text{total\_income\_planned} - \text{total\_expense\_planned}$$
   - Expense Actuals: $\sum \text{Transaction.amount}$ (outflows > 0)
   - Income Actuals: $-1 \times \sum \text{Transaction.amount}$ (inflows < 0 converted to positive)
   - Expense Category Remaining: $\text{planned} - \text{actual}$
3. **Credit Card Debt Model:**
   $$\text{balance\_owed} = \text{starting\_balance} + \sum_{\text{all-time}} \text{Transaction.amount}$$
   - Charges: Sum of positive non-transfer transactions in current month.
   - Payments: Absolute sum of negative transactions in current month.
4. **Transfer Matching Heuristic:**
   - Evaluates all unlinked inflows (`amount < 0`, `is_transfer == False`) against unlinked outflows (`amount > 0`, `is_transfer == False`).
   - Pairs them if $|\text{date}_{\text{outflow}} - \text{date}_{\text{inflow}}| \le 2\text{ days}$ and $\text{account}_{\text{outflow}} \ne \text{account}_{\text{inflow}}$.
   - User approval sets `is_transfer = True` on both records, excluding them from spending calculations.

---

## 6. Identified Architectural Problems

1. **Tight Coupling to Persistence in Route Handlers:**
   `backend/routers/summaries.py`, `backend/routers/credit_cards.py`, and `backend/routers/accounts.py` directly construct and execute complex SQLAlchemy queries and manage session transactions inside HTTP route handlers.
2. **Duplicated Business Logic:**
   - `get_month_range()` is copy-pasted between `summaries.py` and `credit_cards.py`.
   - ZBB actuals aggregation and planned calculations are duplicated between `get_budget_summary()` and `get_dashboard_summary()`.
   - Transaction persistence and duplicate prevention logic is duplicated across `upload.py`, `transactions.py`, and `crud/transaction.py`.
   - Account types and subtypes are duplicated between `backend/schemas.py` and `frontend/app/composables/useAccountTypes.ts`.
3. **Domain Logic Trapped in Presentation Layer:**
   The transfer matching heuristic is a multi-account reconciliation algorithm, yet it is trapped inside `routers/credit_cards.py`.
4. **Circular Internal Dependencies:**
   `backend/crud/transaction.py` imports from `backend/crud/plaid.py`, while `backend/crud/plaid.py` imports from `backend/crud/transaction.py`.
5. **Insecure Credential Storage:**
   `backend/security.py` uses base64 string encoding instead of encryption, leaving Plaid access tokens vulnerable in plaintext equivalent storage.
