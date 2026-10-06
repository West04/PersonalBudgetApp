# Budget App Developer Cheat Sheet

Personal budgeting application featuring zero-based budgeting, Plaid bank synchronization, and manual CSV statement import.

## Tech Stack

- **Backend:** FastAPI (Python 3.11), SQLAlchemy 2.x, PostgreSQL 18, Pydantic v2
- **Frontend:** Nuxt 4, Vue 3 (Composition API), TypeScript, VueDraggable
- **External:** Plaid SDK for bank linking & transaction synchronization
- **Infrastructure:** Docker Compose

## Quick Start

### Docker (Recommended)
```bash
docker-compose up --build
# Frontend: http://localhost:12345
# Backend API: http://localhost:12344
# Swagger Docs: http://localhost:12344/docs
```

### Local Development

Backend:
```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Frontend:
```bash
cd frontend
npm install
npm run dev  # http://localhost:3000
```

## Project Structure

```
backend/
├── main.py                   # FastAPI app entry point with lifespan hooks
├── models.py                 # SQLAlchemy ORM models (11 models)
├── schemas.py                # Pydantic request/response schemas
├── database.py               # DB session management & idempotent migration helpers
├── initial_data.py           # Default categories initialization
├── bank_statement_loader.py  # BankStatementLoader ABC (USAA, Discover, Mapped)
├── security.py               # Token encryption placeholder (base64)
├── routers/                  # 11 API endpoints (accounts, budgets, categories,
│                             # credit_cards, ml, plaid, recurring, rules, summaries, transactions, upload)
├── managers/                 # 13 workflow orchestration managers
├── domain/                   # 11 pure business calculation engines
├── access/                   # 12 concrete resource access modules
└── crud/                     # Legacy data access layer

frontend/
├── app/
│   ├── app.vue               # Root layout with collapsible sidebar
│   ├── tokens.css            # Centralized CSS design tokens
│   ├── base.css              # Base stylesheet
│   ├── components/           # Reusable UI primitives (AppDialog, MonthNavigator, etc.)
│   ├── composables/          # useBudgetMonth.ts, useTransactionFilters.ts, useAccountTypes.ts
│   └── pages/                # File-based routing (dashboard, categories,
│                             # transactions, accounts, credit-cards, upload, settings)
├── nuxt.config.ts            # Nuxt config with API proxy
└── package.json

docs/                         # In-depth architectural & API documentation
├── architecture/             # Canonical Volatility-Based Decomposition specs & ADRs
│   ├── decisions/            # Architectural Decision Records (ADR-001 through ADR-007)
│   └── legacy/               # Historical architecture docs superseded by source audit
├── development/              # Developer guides & agent fallback prompts
├── checkpoints/              # Modernization checkpoints (number_1.md)
├── session_handoffs/         # Multi-session handoff logs
├── PRODUCT_REDESIGN_PLAN.md  # Product redesign strategy & completed phases
├── TODO.md                   # Canonical TODO and active roadmap
└── old_architecture/         # Foundational guides (ARCHITECTURE, API_REFERENCE,
                              # DATA_MODEL, CSV_IMPORT_GUIDE, DEVELOPMENT)
```

## Key Commands

```bash
# Run smoke tests
python3 tests/smoke_test.py

# Seed database with realistic multi-month data
python3 tests/seed_comprehensive.py
# Wipe and clean re-seed
python3 tests/seed_comprehensive.py --clean

# Frontend build
cd frontend && npm run build
```

## Core Domain & Accounting Rules

1. **Transaction Amounts:**
   - Outflow (Charges, Purchases, Debits) = **Positive** (`+50.00`)
   - Inflow (Income, Deposits, Credits) = **Negative** (`-2500.00`)
2. **Zero-Based Budgeting:**
   - `to_be_assigned = total_income_planned - total_expense_planned`
   - Goal: `to_be_assigned == 0.00` ("Every dollar has a job!")
3. **Credit Cards:**
   - `balance_owed = starting_balance + (all-time net transactions)`
   - Transfer matcher links matching positive/negative pairs across accounts within 2 days.
4. **CSV Ingestion:**
   - Subclasses in `bank_statement_loader.py` normalize dates and invert signs to match convention.
   - Prevents duplicate rows matching `(account_id, date, amount, description)`.

## API Conventions

- All primary keys are UUIDs (`uuid.uuid4()`).
- Monies use `condecimal(max_digits=10, decimal_places=2)`.
- Backend lifespan automatically invokes `models.Base.metadata.create_all()` and seeds default categories.
- Frontend `/api/**` route proxy maps to backend port 8000.

## Volatility-Based Decomposition (VBD) Operating Contract

This section is mandatory guidance for architecture and refactoring work. It replaces older architecture shortcuts with an evidence-first VBD process based on *Righting Software* (Juval Löwy).

### Core Volatility Axiom

```text
Architecture follows demonstrated volatility,
not nouns, endpoints, screens, or database tables.

Before architecture changes:
- inspect the actual workflow;
- identify the volatility;
- classify it OBSERVED / PLANNED / SPECULATIVE;
- classify responsibilities;
- justify the boundary.

SPECULATIVE volatility cannot justify a new abstraction.

One volatility boundary -> one refactor -> tests -> review -> commit.
```

### Read first for architecture work

1. `docs/architecture/README.md` (Authority hierarchy and document index)
2. `docs/architecture/vbd-charter.md` (Authoritative VBD charter)
3. `docs/architecture/dependency-rules.md` (Authoritative dependency constraints)
4. `docs/architecture/volatility-registry.md`
5. `docs/architecture/known-invariants.md`
6. `docs/architecture/component-map.md`
7. `docs/architecture/workflow-catalog.md`
8. `docs/architecture/refactor-roadmap.md`
9. `docs/architecture/vbd-source-evidence-audit.md` (Authoritative source snapshot)
10. Relevant ADRs under `docs/architecture/decisions/`
11. Supporting context: `docs/architecture/refactor-safety.md`, `docs/checkpoints/number_1.md`, and `docs/session_handoffs/session_1.md`.
12. Fallback prompt for agents without automatic discovery: `docs/development/CODE_AGENT_BOOTSTRAP_PROMPT.md`.

If documentation and source disagree, source/tests define current behavior while accepted architecture docs define intended constraints. Report the discrepancy before changing code.

### Required skill sequence

Architectural work must use the three repository-local VBD skills located under `.agents/skills/`:

1. **Pre-analysis:** Use `.agents/skills/vbd-architect/SKILL.md` before changing code. Analyzes workflow, classifies volatility, and justifies boundaries without touching code.
2. **Implementation:** Use `.agents/skills/vbd-refactor/SKILL.md` for exactly one approved slice. Strictly preserves behavior, requires characterization tests, and runs the test suite.
3. **Post-review:** Use `.agents/skills/vbd-reviewer/SKILL.md` before considering the slice complete. Reviews diff against VBD principles, dependency rules, and behavior preservation.

Do not skip directly to implementation because a target structure appears obvious.

### VBD definitions

- **Presentation/Host** — HTTP parsing, transport validation, status/error mapping, serialization.
- **Manager** — meaningful sequence/orchestration of a business use case.
- **Engine** — independently volatile, infrastructure-free business algorithm/policy/heuristic/calculation.
- **ResourceAccess/Accessor** — concrete database/API/SDK/file interaction.
- **Resource** — PostgreSQL, Plaid, uploaded/file data, model artifact storage, etc.
- **None** — ordinary code that does not justify a special boundary.

### Evidence rule

Classify every proposed source of volatility:

- `OBSERVED`: proven by current code, multiple implementations, duplicated rules, external change pressure, or coupling.
- `PLANNED`: explicit confirmed roadmap requirement.
- `SPECULATIVE`: plausible only.

**Do not create architectural abstractions for SPECULATIVE volatility.**

### Manager rules

Create or preserve a Manager only when a meaningful sequence changes independently from transport and algorithms.

Good evidence:
- coordinates several Accessors/Engines/activities
- owns workflow order or transaction boundary
- use case exists independently of HTTP

Bad reasons:
- one endpoint exists
- one frontend screen exists
- one domain noun exists
- one CRUD call exists
- architectural symmetry would look cleaner

A Manager may accept a concrete SQLAlchemy `Session`.

Managers must not raise FastAPI `HTTPException` or own HTTP status codes in the intended architecture. Map application failures in Presentation.

### Engine rules

An Engine must remain infrastructure-free.

Do not introduce into an Engine:
- FastAPI / HTTP concepts
- Pydantic transport schemas
- SQLAlchemy Session or ORM models
- ResourceAccess
- Plaid/external SDKs or network calls
- filesystem or environment access

Do not create one Engine per pure helper. Small pure utilities may remain ordinary domain functions.

### ResourceAccess rules

ResourceAccess exists to contain concrete resource mechanics.

Do not:
- create one Accessor per table merely by convention
- add generic `Repository<T>` or persistence ports without demonstrated substitution volatility
- hide business decisions inside persistence functions
- call another ResourceAccess module to implement cross-resource business sequencing

If an operation requires multiple resources or business-side effects, determine whether the sequence belongs in an existing Manager, a justified Manager operation, or one genuinely atomic ResourceAccess operation.

Standalone simple CRUD Accessors may own their atomic commit. Multi-step Manager workflows should normally own their transaction boundary.

### Presentation rules

Presentation may call an Accessor directly for genuinely simple CRUD.

Presentation must not own:
- multi-step business workflow sequencing
- external SDK workflow construction
- business algorithms
- database commit/rollback for a multi-step use case
- persisted-state-driven parser strategy construction when it is part of an application workflow

### Abstraction gate

Before adding an interface, abstract base class, strategy, factory, adapter layer, repository, Unit of Work, provider abstraction, configurable implementation, or DTO layer, answer all three:

1. What demonstrated independent volatility does this protect?
2. Is there more than one implementation now or a confirmed near-term requirement?
3. Does it reduce coupling more than the ceremony it adds?

If the answers are weak, keep the code concrete.

Explicitly rejected without new evidence:
- generic repositories / Unit of Work
- alternate DB-engine ports
- generic bank-provider interface for hypothetical providers
- generic message bus
- generic rule DSL/engine
- GraphQL/gRPC abstraction
- speculative auth/tenancy architecture
- multi-currency architecture
- one Manager per endpoint
- one Engine per function
- DTOs inserted solely to satisfy layering

### Behavior preservation

Read `docs/architecture/known-invariants.md` before structural work.

Do not silently change accounting semantics, CSV behavior, split invariants, known defects, Plaid token security, transaction semantics, or API contracts unless the selected slice explicitly authorizes it.

Architecture refactors are behavior-preserving by default.

### Refactor protocol

Use one volatility boundary per slice.

Before implementation, fill the substance of `docs/architecture/refactor-task-template.md`:
- current workflow
- responsibilities/dependencies
- OBSERVED/PLANNED volatility evidence
- classification of moved responsibilities
- current dependency problem
- target dependency
- speculative alternatives rejected
- behavior preserved
- tests that protect the workflow
- expected files changed

Then:
1. characterize current behavior if coverage is insufficient;
2. make the smallest structural change that corrects the boundary;
3. do not clean up unrelated code;
4. run focused tests while iterating;
5. run the full relevant/full suite before completion;
6. inspect `git diff --stat` and full diff;
7. update component/workflow/dependency docs if topology changed;
8. run the VBD review skill;
9. stop after the requested slice.

### Current priority order

Unless the task explicitly chooses another evidenced slice:
1. Plaid public-token exchange Presentation/legacy boundary.
2. ResourceAccess-to-ResourceAccess coupling centered on `transaction_access.py`.
3. Authoritative categorization policy outside ResourceAccess.
4. CSV/upload Presentation orchestration.
5. FastAPI/Pydantic coupling in Managers.
6. Manager topology review.
7. Redundant DTO cleanup.

Do not bundle these together.

### Documentation discipline

When architecture changes, update the relevant docs in the same slice. Do not rewrite the source evidence audit merely to make a refactor look compliant; create a new evidence checkpoint when needed.

Any change affecting architecture, workflow ownership, dependency direction, volatility classification, transaction ownership, or business invariants must follow `docs/architecture/documentation-maintenance.md`, and affected current-state documentation must be updated in the same change.

### Completion report

Every architecture slice must end with:
- architecture change: before -> after
- dependencies removed/introduced
- behavior changes: `NONE` or explicit list
- tests run and results
- files changed
- docs updated
- known issues intentionally untouched
- remaining VBD concern, if any
