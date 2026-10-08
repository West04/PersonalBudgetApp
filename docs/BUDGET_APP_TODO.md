# Budget App — Historical Slice 16 TODO [Archived]

> [!NOTE]
> **Historical Archive Notice:**
> This file is a preserved historical milestone document from September 2026 (Slice 16).
> For the active canonical task list, completed Phases 1–12, and current roadmap, consult:
> [`docs/TODO.md`](TODO.md) and [`docs/PRODUCT_REDESIGN_PLAN.md`](PRODUCT_REDESIGN_PLAN.md).

**Original Date:** September 26, 2026  
**Original goal:** Get the app ready for real personal use with **CSV imports first**. Plaid is optional and is no longer on the critical path.

## Current checkpoint

- [x] Slice 12 — Category + CategoryGroup CRUD/Reorder ResourceAccess
- [x] Slice 13 — Budget Allocation CRUD ResourceAccess
- [x] Slice 14 — Transfer Confirmation ResourceAccess
- [x] Slice 15 — Plaid Link-Token ResourceAccess
- [x] Priority 6 — Repository-wide persistence-leak audit
- [x] Slice 16 — Upload Preview characterization
- [x] Slice 16 — Upload Preview implementation reviewed
- [x] **Commit and close Slice 16**
- [ ] **Switch from architecture-first work to CSV-first product acceptance**

Latest known test result before Slice 16 commit:

```text
481 passed, 23 warnings
```

Last committed architecture checkpoint before Slice 16:

```text
8d09ce1 refactor: extract plaid link-token resource access
```

---

# Priority A — Close Slice 16

Target architecture:

```text
Upload Preview:
upload.py
    -> account_access.py
        -> PostgreSQL

upload.py
    -> BankStatementLoader
        -> uploaded CSV

Upload Confirm:
upload.py
    -> CSVImportManager
        -> AccountAccess
        -> TransactionAccess
        -> BankStatementLoader
```

- [x] Characterize `/upload/preview`
- [x] Reuse `account_access.get_account_by_id`
- [x] Remove direct `db.query(models.Account)` from `upload.py`
- [x] Remove `_verify_account`
- [x] Preserve Preview-before-Confirm behavior
- [x] Preserve USAA parsing behavior
- [x] Preserve Discover parsing behavior
- [x] Preserve read-only Preview semantics
- [x] Update architecture documentation
- [x] Full regression: `481 passed, 23 warnings`
- [ ] Final diff review
- [ ] Commit Slice 16
- [ ] Confirm clean working tree

Suggested commit message:

```text
refactor: route upload preview account lookup through resource access
```

---

# Priority B — CSV-First Readiness / Acceptance Pass

This is now the **main product milestone**.

Goal:

> Prove that the app is practical to use for real budgeting with CSV imports, without requiring Plaid.

## 1. CSV-only startup

- [ ] Verify backend starts without Plaid production credentials
- [ ] Verify frontend starts without Plaid configuration
- [ ] Verify non-Plaid pages work without Plaid API failures
- [ ] Identify any Plaid-only errors or UI friction
- [ ] Classify Plaid friction as blocker / annoying but usable / cosmetic

## 2. First-time account setup

- [ ] Create a USAA checking/savings account through the UI
- [ ] Create a Discover credit-card account through the UI
- [ ] Verify account type selection
- [ ] Verify `starting_balance` behavior
- [ ] Document how starting balances should be entered before the first CSV import
- [ ] Verify account data persists after restart

## 3. Category setup

- [ ] Create CategoryGroups through the UI
- [ ] Create Categories through the UI
- [ ] Edit Categories
- [ ] Reorder Categories / Groups if needed
- [ ] Verify enough category setup exists to budget a real month

## 4. First monthly budget

- [ ] Select a month
- [ ] Create budget allocations
- [ ] Edit planned amounts
- [ ] Verify income groups
- [ ] Verify expense groups
- [ ] Verify `to_be_assigned`
- [ ] Verify budget state persists after restart

## 5. USAA CSV acceptance

Use a representative non-private fixture shaped like a real USAA export.

- [ ] Preview CSV
- [ ] Verify row count
- [ ] Verify dates
- [ ] Verify descriptions
- [ ] Verify pending state
- [ ] Verify purchase sign: exported negative purchase -> positive app outflow
- [ ] Verify deposit sign: exported positive deposit -> negative app inflow
- [ ] Confirm import
- [ ] Verify persisted transactions match Preview
- [ ] Inspect transactions in the real UI

## 6. Discover CSV acceptance

Use a representative non-private Discover fixture.

- [ ] Preview CSV
- [ ] Verify dates
- [ ] Verify descriptions
- [ ] Verify charge sign: positive charge -> positive app outflow
- [ ] Verify payment sign: negative payment -> negative app inflow
- [ ] Confirm import
- [ ] Verify persisted transactions match Preview
- [ ] Inspect transactions in the real UI

## 7. Preview / Confirm consistency

For both supported formats:

- [ ] Preview date == persisted date
- [ ] Preview description == persisted description
- [ ] Preview amount == persisted amount
- [ ] Preview account == persisted account
- [ ] Investigate any Preview/Confirm mismatch before using real data

## 8. Duplicate-import safety

- [ ] Import the same CSV twice
- [ ] Verify the second import does not create duplicate ledger rows
- [ ] Record inserted/skipped counts
- [ ] Test overlapping statements
- [ ] Verify overlapping date ranges do not duplicate matching transactions

Example overlap:

```text
Statement A: June 1 - June 30
Statement B: June 20 - July 20
```

## 9. Row-error usability

Create a CSV with:

- [ ] valid rows
- [ ] malformed date
- [ ] malformed amount

Verify:

- [ ] Preview remains understandable
- [ ] invalid rows show useful errors
- [ ] valid rows remain visible
- [ ] Confirm behavior is understandable
- [ ] no silent data loss occurs

## 10. Transaction categorization

After import:

- [ ] Categorize an expense
- [ ] Categorize income
- [ ] Edit a category assignment
- [ ] Verify changes persist
- [ ] Verify imported transactions are practical to review in the UI

## 11. Transfer workflow

For transfers between owned accounts:

- [ ] Find transfer candidates
- [ ] Review candidate pairs
- [ ] Mark transfers
- [ ] Verify transfer state persists
- [ ] Confirm workflow is usable enough for CSV-imported transactions

Do not change the current matching heuristic during this acceptance pass.

## 12. Budget actuals

After categorization:

- [ ] Verify expense actuals
- [ ] Verify income actuals
- [ ] Verify category remaining amounts
- [ ] Verify group totals
- [ ] Verify `to_be_assigned`
- [ ] Compare a few values manually against imported transactions

## 13. Dashboard

- [ ] Verify account balances
- [ ] Verify budget-health values
- [ ] Verify recent transactions
- [ ] Verify values correspond to persisted CSV-imported data

## 14. Discover credit-card view

- [ ] Verify `balance_owed`
- [ ] Verify `charges_this_month`
- [ ] Verify `payments_this_month`
- [ ] Confirm the current characterized behavior is usable

Do not change transfer/future-date semantics during this pass.

## 15. Two-month usage test

Use two adjacent months.

- [ ] Separate monthly budgets work
- [ ] Transactions appear in the correct month
- [ ] Actuals remain month-scoped
- [ ] Dashboard month selection works
- [ ] Credit-card monthly metrics remain coherent
- [ ] Repeated monthly CSV imports remain manageable

## 16. Persistence / restart smoke test

After a realistic session:

- [ ] Stop backend/frontend
- [ ] Restart app
- [ ] Verify accounts remain
- [ ] Verify categories remain
- [ ] Verify budgets remain
- [ ] Verify transactions remain
- [ ] Verify category assignments remain
- [ ] Verify transfer flags remain

---

# CSV-First Readiness Gate

Do not move back to broad architecture work until this is answered:

```text
CSV-FIRST READY FOR REAL USE
```

or:

```text
CSV-FIRST NOT READY — BLOCKERS FOUND
```

If blockers are found:

- [ ] Rank them by severity
- [ ] Fix only the highest-impact blocker first
- [ ] Add a focused regression test
- [ ] Re-run the real CSV acceptance path
- [ ] Repeat until CSV-first use is practical

---

# Priority C — Use the App for Real

Once CSV readiness is green:

- [ ] Create real accounts
- [ ] Enter correct starting balances
- [ ] Create real categories
- [ ] Build first real monthly budget
- [ ] Import first real USAA CSV
- [ ] Import first real Discover CSV
- [ ] Categorize imported transactions
- [ ] Mark transfers
- [ ] Verify totals manually
- [ ] Use the app for at least one full budgeting cycle
- [ ] Record friction encountered during real use
- [ ] Prioritize improvements based on actual usage instead of speculative cleanup

---

# Priority D — Backend VBD Audit

**Deferred until CSV-first acceptance is complete.**

- [ ] Verify Routers contain only intended Presentation concerns
- [ ] Verify Managers exist only for meaningful orchestration
- [ ] Verify Engines remain pure
- [ ] Verify Accessors own persistence/external-resource mechanics
- [ ] Search for duplicated domain calculations
- [ ] Search for stale legacy CRUD modules
- [ ] Remove dead compatibility wrappers
- [ ] Reconcile architecture docs with actual code
- [ ] Confirm no unnecessary Managers / Engines / repositories / DTO layers / Unit of Work / provider abstractions

Known deferred architecture issue:

```text
POST /plaid/exchange_public_token
```

This is not required for CSV-first use.

---

# Priority E — Product / Behavior Decisions

Handle these only when they materially affect usage.

## Transaction description nullability (Resolved)

- [x] Decide whether API should allow `description = null` (Decided: No, SQL NULL prohibited)
- [x] Enforce non-null descriptions in persistence (`migrate_transaction_description_integrity` and `Text, nullable=False`)
- [x] Add migration/characterization coverage before changing behavior (`test_migration_transaction_description_integrity.py`, `test_transaction_description_contract.py`)

## CategoryGroup deletion inconsistency

Current behavior:

```text
Frontend blocks deleting non-empty groups.
Backend can cascade the deletion.
```

- [ ] Decide intended product rule
- [ ] Make a dedicated behavior slice if needed

## Credit-card semantics

- [ ] Decide whether `balance_owed` should include transfers
- [ ] Decide whether payments should include negative transfers
- [ ] Decide whether future-dated transactions should affect current `balance_owed`

## Transfer matching (Resolved)

- [x] Decide whether greedy/order-dependent matching is acceptable (Decided: No; eliminated input-order dependence)
- [x] Decide whether closest-date preference is desired (Decided: Yes; deterministic closest-first greedy matching implemented in `detect_transfer_candidates`)

## Budget Summary transfer semantics

- [ ] Decide whether transaction-level `is_transfer=True` should exclude categorized transactions from actuals

---

# Priority F — Plaid

**Deferred / optional.**

Current decision:

> Start with CSV imports. Do not make Plaid a prerequisite for using the app.

## If Plaid is revisited later

- [ ] Decide whether Plaid is still worth supporting
- [ ] Obtain appropriate production access if possible
- [ ] Characterize / modernize `exchange_public_token`
- [ ] Resolve legacy `backend/crud/plaid.py`
- [ ] Decide Plaid transaction sign semantics
- [ ] Implement real token encryption/key management
- [ ] Migrate existing stored Plaid credentials safely
- [ ] Run Plaid-specific E2E acceptance

## If Plaid is abandoned

- [ ] Decide whether to hide Plaid UI
- [ ] Decide whether to disable Plaid routes
- [ ] Remove dead Plaid-only code only after proving no CSV workflows depend on it
- [ ] Remove unused configuration/docs
- [ ] Keep removal as a separate cleanup slice

---

# Priority G — Frontend Improvements

Do these based on friction observed during real CSV use.

## Highest-value CSV-first areas

- [ ] Account setup clarity
- [ ] Starting-balance guidance
- [ ] CSV Preview UX
- [ ] CSV Confirm/result UX
- [ ] Row-error visibility
- [ ] Transaction categorization workflow
- [ ] Transfer review workflow
- [ ] Budget editing
- [ ] Dashboard clarity
- [ ] Empty states
- [ ] Loading states
- [ ] Error states
- [ ] Responsive/mobile behavior

## Broader modernization later

- [ ] Design tokens
- [ ] Reusable UI primitives
- [ ] Dashboard
- [ ] Budget
- [ ] Accounts
- [ ] Transactions
- [ ] Credit cards
- [ ] Transfers
- [ ] CSV import
- [ ] Settings
- [ ] Keyboard accessibility
- [ ] Screen-reader semantics

---

# Priority H — Final Hardening

Before calling the project fully finished:

- [ ] Complete PostgreSQL-backed suite
- [ ] Add/verify E2E tests
- [ ] Add/verify smoke tests
- [ ] Verify Docker Compose from clean environment
- [ ] Verify fresh database initialization
- [ ] Verify migrations
- [ ] Remove dead files/config
- [ ] Reconcile README/setup instructions
- [ ] Test clean clone/setup
- [ ] Perform final architecture/doc audit

---

# Working Rules

Continue using:

```text
preserve behavior first
-> characterize
-> change one justified thing
-> run focused tests
-> run full regression
-> review
-> commit
```

Architecture guardrails:

```text
domain noun != component
CRUD != Manager
CRUD != Engine
possible future change != observed volatility
```

Product guardrail:

> Do not delay real CSV use just to finish low-value architecture or Plaid work.

---

# Immediate Next Actions

1. [ ] Commit Slice 16.
2. [ ] Run the CSV-first readiness / acceptance pass.
3. [ ] Fix only real CSV-use blockers.
4. [ ] Start using representative CSV data.
5. [ ] Start using real CSV data once the acceptance gate is green.
6. [ ] Let actual usage determine the next product improvements.
