# Budget App — Canonical Product & Modernization TODO

**Last Updated:** October 6, 2026  
**Status:** Active Canonical TODO  
**Current HEAD:** `b41c3d5` (`feat: add split transaction allocations`)  
**Test Suite Baseline:** 946 passed, 28 warnings (38.50s)  
**Purpose:** Single source of truth replacing previous split TODO files. Tracks completed milestones, acceptance results, deferred product/UX decisions, and upcoming engineering phases.

---

## Issue Classification Taxonomy

To maintain architectural integrity, items in this repository are categorized under a strict taxonomy:

- **Known Defect:** Code or schema behavior believed to be incorrect relative to contracts (e.g. description nullability mismatch).
- **Unresolved Domain Decision:** Business or financial semantics intentionally left undecided pending explicit product direction (e.g. closest-date transfer matching, credit-card transfer inclusion, deferred Plaid reconciled transaction resolution).
- **Product / UX Observation:** Current implementation functions correctly and consistently with characterized behavior, but user experience, visual presentation, or placement can be refined in future redesigns.

---

## Active Roadmap

```text
Phase 0   Baseline & Characterization            ✓ COMPLETE
Phase 1   Frontend Design Foundation             ✓ COMPLETE
Phase 2   Budget / Categories Redesign           ✓ COMPLETE
Phase 3   Dashboard Redesign                     ✓ COMPLETE
Phase 4   Transactions UX Foundation             ✓ COMPLETE
Phase 5   Accounts Consolidation                 ✓ COMPLETE
Phase 6   Transaction Review & Transfers         ✓ COMPLETE
Phase 7   Account Reconciliation                 ✓ COMPLETE
Phase 8   Merchant Normalization                 ✓ COMPLETE
Phase 9   Categorization Rules                   ✓ COMPLETE
Phase 10  ML Categorization                      ✓ COMPLETE
Phase 11  Recurring Transactions                 ✓ COMPLETE
Phase 12  Split Transactions                     ✓ COMPLETE
    ↓
Phase 13  Financial Depth [Candidate Roadmap]    ACTIVE CANDIDATE
```

---

# Current Checkpoint

## Completed Milestones & Architectural Slices

- [x] **VBD Architectural Slices 1–16:** Pure engine extractions, manager orchestration, accessor boundaries, and regression safety.
- [x] **Orchestration Managers (13 total):**
  - `account_reconciliation_manager.py` (cleared balances, reconciliation completion)
  - `account_summary_manager.py` (depository ledger balance, credit debt, overpayments)
  - `budget_summary_manager.py` (planned vs actual, category actuals aggregation)
  - `categorization_rule_manager.py` (rule creation, listing, preview, retroactive batch apply)
  - `credit_card_summary_manager.py` (debt owed, monthly charges, payments)
  - `csv_import_manager.py` (upload inspection, format mapping, deduplication)
  - `dashboard_summary_manager.py` (liquid cash, credit debt, category spending, alerts)
  - `ml_categorization_manager.py` (confidence-scored suggestions, synchronous retraining)
  - `plaid_account_sync_manager.py` (Plaid item linking and account syncing)
  - `plaid_transaction_sync_manager.py` (transaction cursor syncing, conflict recording)
  - `recurring_transaction_manager.py` (series detection, user confirmation/dismissal)
  - `transaction_split_manager.py` (atomic split allocation and unsplit restoration)
  - `transfer_reconciliation_manager.py` (inter-account transfer candidate discovery)
- [x] **Pure Business Engines & Domain Policies (8 total):**
  - `account_reconciliation.py` (cleared balance arithmetic, statement difference, balanced-state policy)
  - `budgeting.py` (zero-based math, category remaining/assigned calculations)
  - `credit_cards.py` (balance owed, overpayment state, monthly charge/payment totals)
  - `merchant_normalization.py` (merchant cleaning heuristics, pattern stripping, fallback policy)
  - `ml_categorization.py` (TF-IDF + LogisticRegression pipeline, operating thresholds, retraining quality gates)
  - `reconciliation.py` (inter-account transfer candidate pairing heuristic)
  - `recurring_transactions.py` (cadence clustering, variance filtering, next occurrence projection)
  - `transaction_splits.py` (split allocation business invariants: sum exactness, sign matching, minimum count)
- [x] **Pure Domain Utilities (3 total):**
  - `accounts.py` (depository ledger-derived balance formula: starting_balance - sum(amounts))
  - `categorization_rules.py` (canonical merchant string normalization and lookup helper for narrow Phase 9 model)
  - `dates.py` (month boundaries, UTC date conversions)
- [x] **Concrete ResourceAccess (12 total):**
  - `account_access.py`, `budget_access.py`, `categorization_rule_access.py`, `category_access.py`, `csv_format_access.py`, `ml_model_access.py`, `plaid_access.py`, `plaid_item_access.py`, `plaid_transaction_access.py`, `recurring_access.py`, `split_access.py`, `transaction_access.py`.
- [x] **Timezone Offset Bug Resolved:** Frontend timezone date truncation bug on `end_date` resolved in commit `f1e2f92` using `Date.UTC(...)`.

---

# Milestone 1 — CSV-First Product Acceptance (Completed)

## Acceptance Gate: CSV-FIRST READY FOR REAL USE (Achieved)

- Manual CSV upload, inspection, preview, and confirmation.
- Built-in format parsing (USAA, Discover) and custom format handling (configurable date/amount/header mappings).
- Account creation, category creation, and zero-based budget assignment (`to_be_assigned`).
- Transaction ledger viewing, filtering, and manual category assignment.
- Inter-account transfer discovery and confirmation.
- Multi-month statement imports and date boundary preservation.
- Exact-match deduplication `(account_id, date, amount, description)`.
- Row-level error handling on malformed rows without data loss.

---

# Milestone 2 — Real-Use Validation & Modernization (Completed)

All foundation and core budgeting capabilities have been implemented and regression tested through Phase 12.

- [x] **Phase 1: Frontend Design Foundation**
  - Visual design tokens in `frontend/app/tokens.css` (semantic colors, spacing, typography).
  - Reusable components: `MonthNavigator.vue`, `AppDialog.vue`, feedback banners.
  - Route-synchronized month state across views.
- [x] **Phase 2: Budget & Categories Redesign**
  - Zero-based budgeting assignment (`to_be_assigned == total_income - total_expense`).
  - Row expansion, category inline editing, drag-and-drop category/group reordering.
- [x] **Phase 3: Dashboard Redesign**
  - Liquid cash and total credit debt cards with overpayment handling.
  - Spending by category breakdown with progress bars.
  - Actionable "Needs Attention" cards (unreviewed transactions, transfer candidates).
- [x] **Phase 4: Transactions UX Foundation**
  - Fast inline category assignment, account/category/date filters, search input.
  - Route query persistence for active filters (`useTransactionFilters.ts`).
- [x] **Phase 5: Accounts & Credit Cards Consolidation**
  - Depository current balances derived strictly from transaction ledger (`accounts.py`).
  - Credit card accounts represented with `balance_owed`, debt badges, and overpayment indicators.
  - Starting balances treated as setup/accounting metadata.
- [x] **Phase 6: Transaction Review & Transfers**
  - Explicit review tracking (`is_reviewed`).
  - First-class transfer review modal and pairing workflow directly in Transactions workspace.
- [x] **Phase 7: Account Reconciliation**
  - First-class reconciliation workflow (`/accounts/{id}/reconciliation`, `/accounts/{id}/reconciliation/complete`).
  - Transaction cleared state (`is_cleared`) and reconciled locking (`is_reconciled`).
  - Reconciliation history tracking (`last_reconciled_date`, `last_reconciled_balance`).
- [x] **Phase 8: Merchant Normalization**
  - Raw narrative preserved in `description`.
  - Normalized merchant derived in `merchant` with `clean_merchant_key`.
  - Manual override support with `is_merchant_overridden` flag.
- [x] **Phase 9: Categorization Rules**
  - Deterministic merchant-to-category rules (`categorization_rules` table) keyed by canonical `LOWER(TRIM(merchant))`.
  - Single rule per merchant, alphabetized listing, preview matches, and explicit retroactive batch application.
  - Automatically applied during staging to uncategorized rows (`category_id IS NULL`), strictly excluding split transactions.
- [x] **Phase 10: ML Categorization Suggestions**
  - Scikit-learn pipeline (character n-gram TF-IDF + Logistic Regression).
  - Suggestion-only workflow (abstains below 0.30 operating confidence score).
  - Strict supervised provenance: explicit user/ml/legacy categories eligible; rules excluded.
  - Synchronous on-demand retraining with candidate validation and quality gates.
- [x] **Phase 11: Recurring Transactions**
  - Automated detection of recurring series by `(account_id, clean_merchant_key, direction)`.
  - Cadences: weekly (5–9d, avg 6–8d), biweekly (11–17d, avg 12.5–15.5d), monthly (month_diff=1, 26–35d, <=4d or month-end), annual (month_diff=12, 355–375d, <=5d or month-end).
  - Minimum 3 occurrences (2 valid intervals), fixed ($0.05) or variable (CV <= 0.35) amounts.
  - Persistence in `recurring_items` with statuses: `detected`, `confirmed`, `dismissed`.
  - Informational `expected_next_date` projection without mutating ledger balances.
- [x] **Phase 12: Split Transactions**
  - Parent transaction remains the sole financial event; `TransactionSplit` allocates categories.
  - Schema: `transaction_splits` (`transaction_id`, `category_id`, `amount`).
  - Invariant: split amounts sum exactly to parent transaction amount.
  - While split: `parent.category_id = NULL` and `parent.category_source = NULL`.
  - Budget actuals substitution: `transaction_access.get_actuals_by_category` (ResourceAccess) aggregates unsplit parent amounts and child split amounts into category actuals; the Budget Engine receives already-aggregated category totals.
  - Plaid correction policies: non-reconciled splits are deallocated/deleted on provider amount change; reconciled transactions block financial mutation and log conflict fields (`plaid_reconciliation_conflict_amount`, `plaid_reconciliation_conflict_at`).

---

# Milestone 3 — Candidate Phase 13: Financial Depth (Active Roadmap)

Future enhancements to be evaluated based on real-world personal budgeting usage:

- [ ] **Savings Goals & Sinking Funds:** Target balances, monthly contribution targets, and goal progress tracking.
- [ ] **Orthogonal Transaction Tags:** Cross-category labeling for vacation, tax-deductible items, projects, or shared expenses.
- [ ] **Net Worth Tracking:** Aggregation of depository liquid assets minus credit debt over time with historical charting.
- [ ] **Reporting & Analytics:** Category breakdown charts, multi-month spending trends, and cash flow analysis.
- [ ] **Cash Flow Forecasting:** Project future cash position using confirmed recurring transactions and monthly budget targets.

---

# Deferred Product & Domain Decisions

These are documented decisions intentionally kept separate from architectural refactoring:

### Transaction description nullability
- **Classification:** Resolved defect
- **Status:** Completed
- `models.Transaction.description` is non-null in PostgreSQL (`Text`, nullable=False) and schemas enforce non-null `str`. Fixed via `migrate_transaction_description_integrity`, `TransactionUpdate` validator, and Plaid ingestion normalization. Canonical representation for missing narrative is `""`.

### CategoryGroup deletion cascade inconsistency
- **Classification:** Known defect / behavior inconsistency
- **Status:** Preserved pending product decision
- Backend allows cascading deletion of category groups in database, while frontend blocks deleting non-empty groups in UI.

### Credit-card transfer & future-date semantics
- **Classification:** Unresolved domain decision
- **Status:** Preserved characterized behavior
- `balance_owed` includes transfers, while `charges_this_month` excludes transfers. Future-dated transactions are currently evaluated in `balance_owed`. Negative balance owed represents credit/overpayment balance.

### Transfer matching heuristic
- **Classification:** Unresolved domain decision
- **Status:** Preserved characterized behavior
- `detect_transfer_candidates` pairs transactions greedily in database retrieval sequence (tolerance $\le 2$ days) without closest-date tie-breaking or persistent counterpart foreign key.

### Budget Summary transfer exclusion
- **Classification:** Unresolved domain decision
- **Status:** Preserved characterized behavior
- `get_actuals_by_category` does not filter out transaction-level `is_transfer = True`; high-level exclusion relies on the category being configured as type `transfer`.

### Deferred Reconciled Plaid Corrections
- **Classification:** Unresolved domain decision / follow-up workflow
- **Status:** Preserved characterized guard
- Material provider corrections to already-reconciled transactions are blocked from mutating reconciled financial history. The conflict is recorded in `plaid_reconciliation_conflict_amount` and `plaid_reconciliation_conflict_at`, and a warning is returned in the sync response. An explicit administrative workflow to review and resolve reconciled provider conflicts is deferred future work.

---

# Stored Plaid Token Security Migration (Deferred Security Debt)

- **Classification:** Deferred security migration
- **Status:** Preserved placeholder implementation
- `backend/security.py` currently uses base64 encoding as an obfuscation placeholder for access tokens (`ENCRYPTION_KEY` dummy).
- Production deployment requires migrating to authenticated symmetric encryption (e.g., cryptography `Fernet` or AWS/GCP KMS envelope encryption).

---

# Core Architectural Principles & Guardrails

- `domain noun != component`
- `CRUD != Manager`
- `CRUD != Engine`
- `possible future change != observed volatility`
- Standard workflow: `Presentation -> Manager -> Engine / Accessor -> Resource`
- Simple CRUD: `Presentation -> Accessor -> Resource`
- CSV parsing remains an ingestion/parser boundary, not a business Engine.
- Do not introduce speculative abstractions (UnitOfWork, generic repository interfaces, DI containers) without demonstrated independent volatility.
