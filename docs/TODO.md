# Budget App VBD Modernization — TODO

**Current stopping point:** Slice 11 complete; Slice 12 main analysis complete; Slice 12 implementation has not started.

**Current known test baseline before the final Slice 12 correction gate:**

```text
354 passed, 23 warnings
```

> Always rerun the full suite and treat the latest result as authoritative.

---

## Priority 1 — Finish Slice 12 characterization gate

- [ ] Run/recreate **Prompt `68431`**: *Slice 12 Final Characterization Gate — Null Updates & Reorder Edges*.
- [ ] Confirm production code remains unchanged during this gate.
- [ ] Characterize `CategoryGroupUpdate` with:
  - [ ] `name = null`
  - [ ] `sort_order = null`
- [ ] Characterize `CategoryUpdate` with:
  - [ ] `name = null`
  - [ ] `group_id = null`
  - [ ] `sort_order = null`
  - [ ] `type = null`
  - [ ] `is_active = null`
- [ ] Characterize CategoryGroup reorder with:
  - [ ] empty `order`
  - [ ] duplicate IDs
- [ ] Characterize Category reorder with:
  - [ ] empty `order`
  - [ ] duplicate IDs
- [ ] Run the complete repository suite.
- [ ] Confirm the pass count increases beyond 354 and warnings remain understood.
- [ ] Review the report before allowing Slice 12 implementation.

---

## Priority 2 — Implement Slice 12

**Target architecture:**

```text
categories.py
    -> category_access.py
    -> PostgreSQL
```

- [ ] Add the required CategoryGroup CRUD/reorder operations to `backend/access/category_access.py`.
- [ ] Add the required Category CRUD/reorder operations to `backend/access/category_access.py`.
- [ ] Preserve existing `get_category_groups` behavior used by `BudgetSummaryManager`.
- [ ] Keep `CategoryAccess` free of Pydantic/FastAPI dependencies.
- [ ] Retarget all Category/CategoryGroup routes in `backend/routers/categories.py` to `CategoryAccess`.
- [ ] Preserve all characterized HTTP status/error behavior.
- [ ] Preserve explicit-null update behavior exactly as discovered in the final characterization gate.
- [ ] Preserve reorder behavior for:
  - [ ] unknown IDs
  - [ ] unlisted rows
  - [ ] cross-group Category IDs
  - [ ] empty lists
  - [ ] duplicate IDs
- [ ] Preserve CategoryGroup delete cascade behavior exactly.
- [ ] Preserve Transaction `category_id -> NULL` behavior on Category deletion.
- [ ] Preserve current Budget/category deletion behavior.
- [ ] Confirm `backend/crud/category.py` has zero remaining callers.
- [ ] Delete `backend/crud/category.py` if fully dead.
- [ ] Add focused unit tests to `tests/test_access_category.py`.
- [ ] Run full regression.
- [ ] Update `docs/architecture/volatility-map.md`.
- [ ] Review the diff.
- [ ] Commit Slice 12.

---

## Priority 3 — Budget Allocation CRUD

Expected shape:

```text
Router -> BudgetAccess -> PostgreSQL
```

- [ ] Run an analysis/characterization gate first.
- [ ] Inventory Budget CRUD routes and existing `budget_access.py` behavior.
- [ ] Freeze create/update/delete semantics.
- [ ] Preserve Budget Summary Manager and Budget Engine behavior.
- [ ] Avoid introducing a BudgetManager for simple CRUD.
- [ ] Implement only after characterization is green.
- [ ] Full regression, docs reconciliation, review, commit.

---

## Priority 4 — Transfer Confirmation

Expected shape:

```text
Router -> Accessor
```

- [ ] Characterize the current transfer-confirmation endpoint.
- [ ] Confirm it is still a simple atomic persistence mutation.
- [ ] Avoid a Manager unless real sequencing is discovered.
- [ ] Avoid an Engine unless real algorithmic volatility is discovered.
- [ ] Extract persistence if needed.
- [ ] Full regression, docs, review, commit.

---

## Priority 5 — Plaid Link-Token Creation

Expected shape:

```text
Router -> Plaid Accessor
```

- [ ] Characterize the current link-token creation endpoint.
- [ ] Preserve exact SDK request/response/error behavior.
- [ ] Keep it separate from Plaid sync Managers.
- [ ] Do not invent a generic bank-provider abstraction.
- [ ] Extract only the external-resource interaction if justified.
- [ ] Full regression, docs, review, commit.

---

## Priority 6 — Remaining persistence leaks

- [ ] Audit routers/managers for direct SQLAlchemy usage.
- [ ] Specifically revisit `backend/routers/upload.py::_verify_account`.
- [ ] Handle the upload Account lookup within the CSV/upload boundary.
- [ ] Do not mechanically move queries without checking workflow ownership.
- [ ] Re-run repository-wide searches for:
  - [ ] `db.query(`
  - [ ] `db.add(`
  - [ ] `db.delete(`
  - [ ] `db.commit(`
  - [ ] direct ORM construction inside routers

---

## Priority 7 — Backend VBD audit

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

When returning to the project, the first task is:

> **Run Prompt `68431` and finish the Slice 12 explicit-null + reorder-edge characterization gate.**

Do **not** start the Slice 12 implementation until that gate is reviewed.
