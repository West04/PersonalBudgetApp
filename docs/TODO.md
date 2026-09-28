# Budget App VBD Modernization — TODO

**Current stopping point:** Slices 1–16 complete; Custom CSV Format Persistence, Header Detection, Configurable Mapped Statement Parser, Inspection API, and Upload-First Frontend Workflow complete at HEAD (`df4f6b0`).

**Verified regression state at current HEAD:**

```text
Backend:  652 passed, 27 warnings (python3 -m pytest)
Frontend: npm run build -> PASS
```

> Always rerun the full suite and treat the latest result as authoritative.

---

## Completed Slices & Milestones

- [x] **Slice 1:** Budget Summary Manager (`backend/managers/budget_summary_manager.py`)
- [x] **Slice 2:** Dashboard Summary Manager (`backend/managers/dashboard_summary_manager.py`)
- [x] **Slice 3:** Credit Card Summary Manager (`backend/managers/credit_card_summary_manager.py`)
- [x] **Slice 4:** Transfer Reconciliation Manager (`backend/managers/transfer_reconciliation_manager.py`)
- [x] **Slice 5:** CSV Import Confirmation Manager (`backend/managers/csv_import_manager.py`)
- [x] **Slice 6:** Plaid Account Sync Manager (`backend/managers/plaid_account_sync_manager.py`)
- [x] **Slice 7 & 9:** Plaid Transaction Sync Manager (`backend/managers/plaid_transaction_sync_manager.py`) & Transaction ResourceAccess
- [x] **Slice 10:** Manual Transaction CRUD ResourceAccess (`backend/access/transaction_access.py`)
- [x] **Slice 11:** Account CRUD ResourceAccess (`backend/access/account_access.py`)
- [x] **Slice 12:** Category & CategoryGroup CRUD / Reorder ResourceAccess (`backend/access/category_access.py`, retired `backend/crud/category.py`)
- [x] **Slice 13:** Budget Allocation ResourceAccess (`backend/access/budget_access.py`, retired `backend/crud/budget.py`)
- [x] **Slice 14:** Transfer Confirmation ResourceAccess (`backend/access/transaction_access.py:mark_transfers_as_reconciled`)
- [x] **Slice 15:** Plaid Link-Token Creation ResourceAccess (`backend/access/plaid_access.py:create_link_token`)
- [x] **Slice 16:** Upload Preview Account Lookup ResourceAccess (`backend/access/account_access.py:get_account_by_id`)
- [x] **Custom CSV Formats & Upload-First Ingestion:**
  - Persisted `CSVFormat` PostgreSQL Resource and `backend/access/csv_format_access.py`
  - Configurable `MappedStatementLoader` and immutable `MappedCSVFormatConfig` in `backend/bank_statement_loader.py`
  - Header auto-detection helper function (`detect_csv_format`) with exact matching rules
  - Stateless upload inspection endpoint (`POST /upload/inspect`)
  - Custom format management endpoints (`GET /upload/formats`, `POST /upload/formats`)
  - Upload-first frontend workflow in `frontend/app/pages/upload.vue` (Step 1: Upload / Inspect / Resolve $\rightarrow$ Step 2: Account $\rightarrow$ Step 3: Preview & Confirm $\rightarrow$ Step 4: Done)

---

## Priority 1 — Audit Remaining Persistence Leaks

- [ ] Audit routers and managers for direct SQLAlchemy queries or session management that belong in ResourceAccess:
  - [ ] Search for `db.query(`
  - [ ] Search for `db.add(`
  - [ ] Search for `db.delete(`
  - [ ] Search for `db.commit(`
  - [ ] Search for direct ORM construction inside routers
- [ ] Ensure any remaining raw queries are encapsulated in concrete `backend/access/` modules.

---

## Priority 2 — Backend VBD Audit & Consistency

- [ ] Verify Routers contain Presentation concerns only (HTTP validation, error mapping, serialization).
- [ ] Verify Managers exist only for meaningful multi-step orchestration.
- [ ] Verify Engines remain pure and infrastructure-free.
- [ ] Verify Accessors own concrete persistence/external-resource mechanics.
- [ ] Check for dead code or legacy compatibility wrappers (e.g. audit remaining `backend/crud/plaid.py`).
- [ ] Confirm no unnecessary Managers, Engines, repositories, or DTO layers.

- [ ] Verify Routers contain Presentation concerns only where intended.
- [ ] Verify Managers exist only for meaningful orchestration.
- [ ] Verify Engines remain pure and infrastructure-free.
- [ ] Verify Accessors own persistence/external-resource mechanics.
- [ ] Search for duplicated domain calculations.
- [ ] Search for stale legacy CRUD modules.
- [ ] Remove dead compatibility wrappers.
- [ ] Confirm no unnecessary:
  - [ ] Managers
  - [ ] Engines
  - [ ] repositories
  - [ ] DTO layers
  - [ ] Unit of Work
  - [ ] provider abstractions
- [ ] Reconcile architecture documentation with actual code.

---

## Priority 8 — Separate product / behavior decisions

These must remain separate from structural refactors.

### Transaction description mismatch

- [ ] Decide how to resolve DB-nullable vs API-non-null `Transaction.description`.
- [ ] Add targeted characterization/migration tests before changing behavior.

### CategoryGroup deletion inconsistency

Current state:

```text
Frontend blocks deleting non-empty groups.
Backend cascades deletion if the request is sent.
```

- [ ] Decide whether backend should reject non-empty deletion.
- [ ] Or decide whether frontend should permit the cascade.
- [ ] Make this a dedicated behavior/product slice.

### Credit-card semantics

- [ ] Decide whether `balance_owed` should include transfers.
- [ ] Decide whether payments should include negative transfers.
- [ ] Decide whether future-dated transactions belong in current `balance_owed`.

### Transfer matching

- [ ] Decide whether matching should remain greedy/order-dependent.
- [ ] Decide whether closest-date preference is desired.
- [ ] If changed, treat as an intentional domain-policy update.

### Plaid amount signs

- [ ] Decide whether the current Plaid amount inversion is correct for the app-wide sign convention.
- [ ] Keep any correction separate from sync architecture.

---

## Priority 9 — Plaid token security migration

Current token storage is not real encryption.

- [ ] Design actual encryption/key-management approach.
- [ ] Define configuration/key-loading strategy.
- [ ] Plan migration for already-stored Plaid tokens.
- [ ] Add migration tests.
- [ ] Verify existing-user data path.
- [ ] Verify fresh-install path.
- [ ] Keep this separate from normal Plaid sync refactors.

---

## Priority 10 — Frontend modernization

Begin after backend/API behavior is stable.

### Foundation

- [ ] Define design tokens.
- [ ] Build reusable UI primitives.
- [ ] Standardize spacing, typography, states, and responsive rules.

### Vertical slices

- [ ] Dashboard
- [ ] Budget
- [ ] Accounts
- [ ] Transactions
- [ ] Credit cards
- [ ] Transfers
- [ ] CSV import
- [ ] Plaid/settings

### UX hardening

- [ ] Loading states
- [ ] Empty states
- [ ] Error states
- [ ] Mobile/responsive behavior
- [ ] Keyboard accessibility
- [ ] Screen-reader semantics
- [ ] Reusable Vue components/composables where justified

---

## Priority 11 — Final hardening

- [ ] Run the complete PostgreSQL-backed suite.
- [ ] Add/verify E2E and smoke tests.
- [ ] Verify Docker Compose from a clean environment.
- [ ] Verify fresh database initialization.
- [ ] Verify migrations.
- [ ] Remove dead files/config.
- [ ] Reconcile README/setup instructions.
- [ ] Test a clean clone/setup.
- [ ] Perform final architecture/doc audit.

---

# Guardrails to keep using

```text
domain noun != component
CRUD != Manager
CRUD != Engine
possible future change != observed volatility
```

Workflow:

```text
preserve behavior first
-> characterize odd behavior
-> extract one justified boundary
-> run full suite
-> review
-> update docs
-> commit
-> repeat
```

For simple CRUD, prefer:

```text
Router -> Accessor -> Resource
```

Do not introduce speculative abstractions unless a real independent volatility axis is demonstrated.

---

# Resume checkpoint

When returning to the project, the current baseline is:

> **All Slices 1–16 and Custom CSV Format / Upload-First ingestion are complete and regression-verified at HEAD (`df4f6b0`). Documentation audit is complete.**

Next steps:
- Human review of the refreshed documentation.
- Select the next prioritized slice:
  - **Priority 1 & 2:** Auditing remaining persistence leaks and legacy wrappers (e.g. `backend/crud/plaid.py`).
  - **Priority 3:** Separate product/behavior decisions (Transaction description nullability, CategoryGroup cascade deletion, Credit card transfer/future-dated balance semantics).
  - **Priority 4:** Plaid token security migration (replacing base64 with cryptographic key management).

