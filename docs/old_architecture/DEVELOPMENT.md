# Developer Guide & Workflows

This document outlines environment setup, local development, database seeding, testing, and common troubleshooting steps.

---

## 1. Prerequisites

- **Docker & Docker Compose** (Docker Desktop on macOS)
- **Python:** 3.11+ (recommended for local backend development)
- **Node.js:** 20+ (recommended for local frontend development)
- **Git**

---

## 2. Environment Configuration

Create a `.env` file in the project root directory. Example configuration:

```bash
# Database Settings
POSTGRES_HOST=db             # Use 'localhost' when running backend outside Docker
POSTGRES_PORT=5432
POSTGRES_USER=budget_user
POSTGRES_PASSWORD=budget_secret
POSTGRES_DATABASE=budget_app

# Plaid API Credentials (Optional - only needed for Plaid bank sync)
PLAID_CLIENT_ID=your_plaid_client_id
PLAID_SECRET=your_plaid_secret
PLAID_ENVIRONMENT=Sandbox     # Sandbox | Development | Production

# Plaid Token Authenticated Encryption Key (Required whenever stored Plaid items exist)
# Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
PLAID_TOKEN_ENCRYPTION_KEY=your_fernet_key
```

> [!NOTE]
> When running inside Docker Compose, `POSTGRES_HOST=db` is overridden automatically by the docker-compose service configuration.

---

## 3. Quick Start with Docker Compose (Recommended)

To start the full stack (PostgreSQL, FastAPI Backend, Nuxt Frontend):

```bash
docker-compose up --build
```

### Service URLs
| Service | Host URL | Description |
|---|---|---|
| **Frontend UI** | [http://localhost:12345](http://localhost:12345) | Nuxt web application |
| **Backend API** | [http://localhost:12344](http://localhost:12344) | FastAPI application |
| **Interactive Docs** | [http://localhost:12344/docs](http://localhost:12344/docs) | Swagger UI for testing endpoints |
| **PostgreSQL** | `localhost:5432` | Database container |

To shut down:
```bash
docker-compose down
```

---

## 4. Local Development (Without Docker)

### 4.1 Start the PostgreSQL Container Only
If you want to run the code locally with hot-reloading:

```bash
docker run --name budget-db \
  -e POSTGRES_DB=budget_app \
  -e POSTGRES_USER=budget_user \
  -e POSTGRES_PASSWORD=budget_secret \
  -p 5432:5432 \
  -d postgres:18
```

Ensure your `.env` specifies:
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=budget_user
POSTGRES_PASSWORD=budget_secret
POSTGRES_DATABASE=budget_app
```

### 4.2 Start the Backend
From the project root:

```bash
# Create and activate a Python virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Start FastAPI with hot reload
uvicorn backend.main:app --reload --port 8000
```

### 4.3 Start the Frontend
In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend will run at [http://localhost:3000](http://localhost:3000).

---

## 5. Testing & Database Seeding

The repository contains both an automated unit/integration test suite (`pytest`) and live environment smoke/seeding tools:

### 5.1 Run the Automated Test Suite (Pytest)
Executes the automated suite of unit, integration, and characterization tests covering budgeting logic, credit card calculation, transfer matching, statement loaders, CSV auto-detection, and resource access:

```bash
# Run all tests
python3 -m pytest

# Run specific test file
python3 -m pytest tests/test_unit_csv_parsing.py
```

### 5.2 Run the Smoke Test Suite
Verifies all core API endpoints against a running backend server:

```bash
# Default targets http://127.0.0.1:12344
python3 tests/smoke_test.py
```

Expected output:
```text
Waiting for server at http://127.0.0.1:12344...
Server up. Starting tests...

✅ GET /category-groups: 5 items
✅ GET /budget?budget_month=2024-01-01
✅ GET /summary/budget?month=2024-01
✅ GET /summary/dashboard (Account fields verified)
✅ GET /transactions (Paginated: 0 total)
✅ GET /transactions?uncategorized=true
✅ GET /accounts
✅ POST /plaid/create_link_token
```

### 5.3 Comprehensive Seed Script
Populates the database with realistic multi-month budgets, multiple accounts, and transactions:

```bash
# Seed realistic data
python3 tests/seed_comprehensive.py

# Optional: Wipe existing data before seeding
python3 tests/seed_comprehensive.py --clean

# Target a custom URL (e.g. local backend on port 8000)
python3 tests/seed_comprehensive.py --base-url http://localhost:8000
```

### 5.4 Plaid Sandbox Transaction Generator
If using Plaid Sandbox:
```bash
python3 tests/generate_sandbox_tx.py
```

---

## 6. Common Gotchas & Troubleshooting

1. **Trailing Slashes on Routes:**
   - FastAPI enforces exact routing: `/budget/` requires the trailing slash; `/category-groups` does not have a trailing slash. Always check [`API_REFERENCE.md`](file:///Users/west/programming_stuff/budget_app/docs/old_architecture/API_REFERENCE.md).
2. **Transaction Sign Convention:**
   - Purchases/Outflows are **positive** numbers.
   - Income/Deposits are **negative** numbers.
3. **Decimal Precision Validation:**
   - Budget planned amounts and transaction amounts are validated with `condecimal(max_digits=10, decimal_places=2)`. Values with more than 2 decimal places will trigger a 422 Unprocessable Entity error. Round numbers to 2 decimal places before sending.
4. **Dates in Requests:**
   - Budget records require `budget_month` formatted as the first day of the month: `YYYY-MM-01`.
   - Summary query parameters expect `month` as `YYYY-MM`.
   - Transactions require `date` as `YYYY-MM-DD`.
