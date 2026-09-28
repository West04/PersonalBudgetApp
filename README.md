# Personal Budget App 💰

A full-stack, zero-based personal budgeting web application built with **FastAPI**, **Nuxt 4**, **Vue 3**, **SQLAlchemy**, and **PostgreSQL**.

Inspired by EveryDollar and YNAB, this application gives every dollar a job. It supports automated bank syncing via **Plaid** as well as offline statement importing via **bank CSV exports** (USAA, Discover, extensible).

---

## 🌟 Key Features

- **Zero-Based Budgeting:** Balance your monthly budget so that $\text{Income Planned} - \text{Expenses Planned} = 0$ ("Every dollar has a job!").
- **Unified Categories & Budget Planner:** Reorder categories and groups using drag-and-drop (`vuedraggable`), inspect planned vs. actual numbers, and edit monthly budgets inline.
- **Credit Card Engine:** Track rolling credit debt (`balance_owed = starting_balance + all-time net transactions`), monitor monthly charges and payments, and review transactions.
- **Automated Transfer Matching:** Heuristic engine detects inter-account transfers (e.g. credit card payments, checking &rarr; savings transfers) within a 2-day window across accounts.
- **Statement CSV Upload Wizard:** Upload-first workflow with automatic header detection, custom bank format mapping & persistence, row-level preview, validation, and exact duplicate detection (supporting USAA, Discover, and custom user-defined formats).
- **Automated Bank Sync (Plaid):** Link financial institutions to automatically sync accounts, balances, and transactions.
- **Interactive Dashboard:** High-level monthly overview showing income, spending, group distributions, account balances, and recent activity.
- **Transaction Ledger:** Paginated transaction ledger with real-time text search, account filtering, category assignment, and uncategorized quick-filters.

---

## 🏗️ Architecture & Tech Stack

```mermaid
flowchart LR
    Browser["Client Browser<br/>(Port 12345)"]
    Nuxt["Nuxt 4 / Vue 3<br/>Frontend & Proxy"]
    FastAPI["FastAPI 0.115<br/>Python 3.11 Backend<br/>(Port 12344)"]
    Postgres[(PostgreSQL 18<br/>Database)]
    Plaid["Plaid API"]

    Browser --> Nuxt
    Nuxt -->|/api/** proxy| FastAPI
    FastAPI --> Postgres
    FastAPI --> Plaid
```

- **Frontend:** Nuxt 4, Vue 3 (Composition API), TypeScript, VueDraggable, custom CSS variables.
- **Backend:** FastAPI, Python 3.11, SQLAlchemy 2.x, Pydantic v2, python-multipart. Organized using Volatility-Based Decomposition (VBD) into Presentation routers, workflow Managers, pure calculation Engines, and concrete ResourceAccess modules.
- **Database:** PostgreSQL 18 with UUID primary keys and exact fixed-point decimals (`DECIMAL(10,2)` / `DECIMAL(12,2)`).
- **Deployment:** Docker & Docker Compose.

---

## 🚀 Quick Start (Docker Compose)

The fastest way to launch the entire stack is with Docker Compose:

### 1. Configure Environment
Ensure you have a `.env` file in the root directory:
```bash
POSTGRES_PORT=5432
POSTGRES_USER=budget_user
POSTGRES_PASSWORD=budget_secret
POSTGRES_DATABASE=budget_app

# Plaid API (Optional - required only for live bank sync)
PLAID_CLIENT_ID=your_plaid_client_id
PLAID_SECRET=your_plaid_secret
PLAID_ENVIRONMENT=Sandbox
```

### 2. Launch Stack
```bash
docker-compose up --build
```

### 3. Access Services
- **Web App:** [http://localhost:12345](http://localhost:12345)
- **FastAPI Documentation:** [http://localhost:12344/docs](http://localhost:12344/docs)
- **Database:** `localhost:5432`

---

## 💻 Local Development (Without Docker)

### Backend Setup
```bash
# 1. Start a local Postgres instance or container
docker run --name budget-db -e POSTGRES_DB=budget_app -e POSTGRES_USER=budget_user -e POSTGRES_PASSWORD=budget_secret -p 5432:5432 -d postgres:18

# 2. Virtual environment & dependencies
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 3. Start backend API
uvicorn backend.main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
# Frontend runs on http://localhost:3000
```

---

## 🧪 Testing & Data Seeding

Run the automated backend test suite:
```bash
# Run all unit, integration, and characterization tests
python3 -m pytest
```

Run smoke tests against a running backend:
```bash
python3 tests/smoke_test.py
```

Verify the frontend production build:
```bash
cd frontend && npm run build
```

Populate the database with realistic multi-month test data:
```bash
# Seed demo categories, accounts, budgets, and transactions
python3 tests/seed_comprehensive.py

# Or wipe and re-seed clean:
python3 tests/seed_comprehensive.py --clean
```

---

## 📁 Repository Structure

```
├── backend/
│   ├── main.py                     # FastAPI entry point & CORS configuration
│   ├── models.py                   # SQLAlchemy ORM models (UUID PKs, decimals, CSVFormat)
│   ├── schemas.py                  # Pydantic v2 request/response schemas
│   ├── database.py                 # DB engine and session factory
│   ├── initial_data.py             # Default category groups and categories
│   ├── bank_statement_loader.py    # BankStatementLoader ABC, USAA/Discover, Mapped loader, detection
│   ├── security.py                 # Plaid token encoding placeholder (base64)
│   ├── access/                     # Concrete PostgreSQL & external ResourceAccess modules
│   │   ├── account_access.py
│   │   ├── budget_access.py
│   │   ├── category_access.py
│   │   ├── csv_format_access.py
│   │   ├── plaid_access.py
│   │   ├── plaid_item_access.py
│   │   ├── plaid_transaction_access.py
│   │   └── transaction_access.py
│   ├── domain/                     # Pure, infrastructure-free business calculation Engines
│   │   ├── budgeting.py            # Zero-based budgeting calculations
│   │   ├── credit_cards.py         # Credit card balance and metric calculations
│   │   ├── dates.py                # Month range and date helpers
│   │   └── reconciliation.py       # Transfer candidate matching heuristic
│   ├── managers/                   # Workflow orchestration Managers
│   │   ├── budget_summary_manager.py
│   │   ├── credit_card_summary_manager.py
│   │   ├── csv_import_manager.py
│   │   ├── dashboard_summary_manager.py
│   │   ├── plaid_account_sync_manager.py
│   │   ├── plaid_transaction_sync_manager.py
│   │   └── transfer_reconciliation_manager.py
│   └── routers/                    # FastAPI route handlers (Presentation)
│       ├── accounts.py
│       ├── budgets.py
│       ├── categories.py
│       ├── credit_cards.py
│       ├── plaid.py
│       ├── summaries.py
│       ├── transactions.py
│       └── upload.py               # Inspect, format management, preview, confirm
├── frontend/
│   ├── app/
│   │   ├── app.vue                 # Persistent sidebar & root layout
│   │   ├── composables/            # useAccountTypes composable
│   │   └── pages/
│   │       ├── dashboard.vue       # KPI cards, accounts, recent transactions
│   │       ├── categories.vue      # Merged category admin & monthly budget planner
│   │       ├── transactions.vue    # Searchable, filterable transaction ledger
│   │       ├── accounts.vue        # Account management & balances
│   │       ├── credit-cards.vue    # Credit debt, payments, transfer review
│   │       ├── upload.vue          # Upload-first CSV inspection, format detection, preview & import
│   │       └── settings.vue        # Settings placeholder
│   ├── nuxt.config.ts              # Nuxt configuration & /api/** proxy
│   └── package.json
├── docs/                           # Documentation
│   ├── TODO.md                     # Modernization task tracking & known decisions
│   ├── architecture/               # Volatility-Based Decomposition specs & guides
│   │   ├── current-state.md        # Architecture overview & component map
│   │   ├── volatility-map.md       # Decomposition strategy & boundary matrix
│   │   ├── csv-import-confirmation.md # CSV import confirmation workflow spec
│   │   ├── credit-card-summary.md  # Credit card summary workflow spec
│   │   ├── dashboard-summary.md    # Dashboard summary workflow spec
│   │   ├── plaid-account-sync.md   # Plaid account sync workflow spec
│   │   ├── plaid-transaction-sync.md # Plaid transaction sync workflow spec
│   │   ├── transfer-candidate-search.md # Transfer candidate search workflow spec
│   │   ├── refactor-safety.md      # Characterization test safety & invariants
│   │   └── vbd-skill-suite-guide.md # VBD skill suite guide
│   └── old_architecture/           # Foundational guides & domain reference
│       ├── ARCHITECTURE.md         # System design, domain math, accounting rules
│       ├── API_REFERENCE.md        # REST endpoint reference & schemas
│       ├── DATA_MODEL.md           # PostgreSQL schemas, ERD, and constraints
│       ├── CSV_IMPORT_GUIDE.md     # Statement parser & custom format guide
│       └── DEVELOPMENT.md          # Local setup, seeding, and troubleshooting
├── tests/                          # Automated pytest suite & seed utilities
├── docker-compose.yml              # Multi-container orchestration
└── README.md
```

---

## 📖 Deep-Dive Documentation

For detailed guides, please refer to the `docs/` folder:
- [Architecture & Accounting Logic](docs/old_architecture/ARCHITECTURE.md)
- [REST API Reference](docs/old_architecture/API_REFERENCE.md)
- [Database Schema & ERD](docs/old_architecture/DATA_MODEL.md)
- [CSV Statement Import Guide](docs/old_architecture/CSV_IMPORT_GUIDE.md)
- [Developer Guide & Troubleshooting](docs/old_architecture/DEVELOPMENT.md)
- [VBD Volatility Map](docs/architecture/volatility-map.md)
- [Current State Architecture](docs/architecture/current-state.md)