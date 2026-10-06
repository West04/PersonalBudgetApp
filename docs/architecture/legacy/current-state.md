> [!WARNING]
> Historical architecture document.
>
> This file is preserved for project history and does not represent the
> authoritative current VBD dependency structure.
>
> For current architecture constraints and evidence, see:
>
> - `../vbd-charter.md`
> - `../component-map.md`
> - `../dependency-rules.md`
> - `../vbd-source-evidence-audit.md`

# Current State Architecture & System Analysis


## 1. Executive Summary
The Personal Budget App is a full-stack personal finance application built on the zero-based budgeting (ZBB) methodology. It supports automated bank syncing via Plaid and manual CSV statement uploads (with automatic header detection, custom format persistence, upload-first workflow, and route-query synchronized ledger). 

Following the completion of modernizing architectural slices and product feature phases (Phases 1 through 12: Design Foundation, Budget & Categories, Dashboard, Transactions UX, Accounts Consolidation, Transaction Review & Transfers, Account Reconciliation, Merchant Normalization, Categorization Rules, ML Categorization, Recurring Transactions, and Split Transactions), this document records the authoritative architectural implementation, components, data flows, cross-feature interaction rules, and known defects/unresolved items at HEAD (`b41c3d5`).

---

## 2. Technology Stack & Infrastructure

| Layer | Technologies | Key Libraries & Specifications |
|---|---|---|
| **Backend API** | Python 3.11, FastAPI 0.115+ | Uvicorn, Pydantic v2 (`ConfigDict`, `condecimal`), `python-dotenv`, `python-multipart` |
| **ORM & Database** | SQLAlchemy 2.x, PostgreSQL 18 | `psycopg2-binary`, `UUID`, `DECIMAL(10,2)`, `DECIMAL(12,2)`, 11 models (`CategoryGroup`, `Category`, `Budget`, `Account`, `Transaction`, `PlaidItem`, `CSVFormat`, `CategorizationRule`, `MLModelMetadata`, `RecurringItem`, `TransactionSplit`) |
| **Machine Learning** | scikit-learn 1.4+, joblib | `Pipeline`, `TfidfVectorizer` (char_wb n-grams 3–5), `LogisticRegression` (balanced class weights), local atomic joblib model persistence |
| **Integrations** | Plaid Python SDK, `requests` | Direct HTTP calls to `/transactions/sync`, `csv`, `io` |
| **Security** | Python Standard Library | `base64` placeholder token encoding (cryptographic migration to Fernet/KMS pending) |
| **Frontend SPA** | Nuxt 4 (`^4.2.2`), Vue 3 (`^3.5.26`) | Composition API, `<script setup>`, Vue Router 4, `vuedraggable` (`^4.1.0`), centralized CSS design tokens |
| **Orchestration** | Docker Compose | Backend (`:12344`), Frontend (`:12345`), Postgres (`:5432`) |

---

## 3. Entry Points & Runtime Initialization

1. **Backend Lifespan Entry (`backend/main.py`):**
   - Runs `models.Base.metadata.create_all(bind=engine)` to auto-provision database tables.
   - Executes idempotent database migration functions in `backend/database.py`:
     - `migrate_review_state()`: Populates review flags.
     - `migrate_reconciliation_state()`: Adds cleared and reconciled tracking fields.
     - `migrate_merchant_state()`: Adds merchant normalization and override fields.
     - `migrate_categorization_rules()`: Adds deterministic categorization rules table.
     - `migrate_ml_state()`: Adds ML category metadata and transaction category source tracking.
     - `migrate_recurring_state()`: Adds recurring items detection table.
     - `migrate_split_state()`: Adds split transaction allocations table and Plaid reconciliation conflict columns.
   - Invokes `init_db(db)` from `backend/initial_data.py` to seed default category groups (Income, Saving, Housing, Food, Transportation).
   - Configures CORS middleware for `http://localhost:3000` and `http://localhost:12345`.
   - Registers 11 presentation routers: `accounts`, `budgets`, `categories`, `credit_cards`, `ml`, `plaid`, `recurring`, `rules`, `summaries`, `transactions`, `upload`.
2. **Frontend Root Layout (`frontend/app/app.vue`):**
   - Applies global design tokens (`frontend/app/tokens.css`, `frontend/app/base.css`).
   - Renders a collapsible sidebar navigation menu.
   - Hosts `<NuxtPage />` routed views.
   - `frontend/app/pages/index.vue` redirects root traffic to `/dashboard`.
3. **Docker Networking & Proxy Rules:**
   - Nuxt Nitro server proxies `/api/**` to `http://backend:8000/**`.
   - All frontend views communicate via `/api/**`.

---

## 4. Module Map & Responsibilities

`backend/domain/` contains pure business code. Within it:
- **Engines / Domain Policies (8):** Isolate independently volatile business algorithms, calculations, heuristics, and accounting invariants that change independently from transport and persistence.
- **Domain Utilities (3):** Contain simple supporting pure functions (depository subtraction formula, narrow canonical merchant-key helpers, date helpers) that do not justify a separate volatility boundary.

Directory membership alone does not determine VBD classification: domain noun != component, pure function != automatically Engine, and small implementation != automatically Utility. The deciding factor is independent business volatility.

```
backend/
├── main.py                     # Lifespan DDL/migrations/seeding, router mounting, CORS
├── database.py                 # Engine creation, SessionLocal factory, get_db, 7 idempotent migration helpers
├── models.py                   # 11 SQLAlchemy models
├── schemas.py                  # Pydantic v2 schemas and ACCOUNT_SUBTYPES definition
├── security.py                 # Base64 placeholder token encoding (security migration pending)
├── initial_data.py             # Default category group and category seed records
├── bank_statement_loader.py    # BankStatementLoader ABC, USAA/Discover, MappedStatementLoader, MappedCSVFormatConfig, detect_csv_format
├── access/                     # 12 Concrete PostgreSQL & external ResourceAccess modules
│   ├── account_access.py       # Account persistence, active filters, starting balances, reconciliation fields
│   ├── budget_access.py        # Monthly budget allocation queries and CRUD
│   ├── category_access.py      # Category/Group CRUD, hierarchy queries, sort_order updates
│   ├── categorization_rule_access.py # Rule CRUD, merchant key lookup dictionary, transaction queries
│   ├── csv_format_access.py    # CSVFormat persistence, uniqueness validation, mapped config converters
│   ├── ml_model_access.py      # MLModelMetadata persistence, joblib atomic model load/save/delete
│   ├── plaid_access.py         # Plaid SDK client, link-token creation, account balance queries
│   ├── plaid_item_access.py    # PlaidItem lookup and cursor persistence
│   ├── plaid_transaction_access.py # Dedicated raw HTTP /transactions/sync client
│   ├── recurring_access.py     # RecurringItem queries, upsert, status updates, stale auto-detected cleanup
│   ├── split_access.py         # TransactionSplit queries, batch creation, deletion, transaction split status
│   └── transaction_access.py   # Transaction queries, CSV deduplication, category actuals aggregation, splits
├── domain/                     # 8 Pure Calculation Engines & Domain Policies + 3 Pure Domain Utilities
│   │   # --- Pure Calculation Engines & Domain Policies (Independently Volatile) ---
│   ├── account_reconciliation.py # Cleared balance calculation, statement difference, balanced-state policy
│   ├── budgeting.py            # Zero-based budget calculations (planned, actual, to_be_assigned)
│   ├── credit_cards.py         # Credit card balance_owed, charges, payments calculations
│   ├── merchant_normalization.py # Merchant cleaning heuristics, pattern stripping, and fallback policy
│   ├── ml_categorization.py    # Feature extraction, Pipeline construction, training, quality gate evaluation
│   ├── reconciliation.py       # Inter-account transfer candidate pairing heuristic
│   ├── recurring_transactions.py # Cadence clustering, interval validation, variance filtering, next date projection
│   ├── transaction_splits.py   # Split allocation business invariants (sum exactness, minimum count, sign matching)
│   │   # --- Pure Domain Utilities & Supporting Helpers (Narrow / Stable Policy) ---
│   ├── accounts.py             # Simple depository balance subtraction formula
│   ├── categorization_rules.py # Merchant canonical key normalization helper for narrow Phase 9 model
│   └── dates.py                # Month range and UTC date calculation helpers
├── managers/                   # 13 Workflow orchestration Managers
│   ├── account_reconciliation_manager.py # Coordinates cleared balance checks and atomic reconciliation completion
│   ├── account_summary_manager.py        # Coordinates depository ledger balance and credit debt summaries
│   ├── budget_summary_manager.py         # Coordinates category, budget, transaction access, and budgeting engine
│   ├── categorization_rule_manager.py    # Coordinates rule lookup and retroactive bulk rule execution
│   ├── credit_card_summary_manager.py    # Coordinates credit accounts, transaction history, and credit card engine
│   ├── csv_import_manager.py             # Coordinates account verification, statement parsing, deduplication, commit
│   ├── dashboard_summary_manager.py      # Composes liquid cash, debt totals, spending breakdown, and action items
│   ├── ml_categorization_manager.py      # Coordinates model inference, confidence scoring, and synchronous retraining
│   ├── plaid_account_sync_manager.py     # Coordinates Plaid account balance sync and account persistence
│   ├── plaid_transaction_sync_manager.py # Coordinates cursor pagination, transaction sync, split deallocation, conflict guards
│   ├── recurring_transaction_manager.py  # Coordinates candidate transaction aggregation, recurrence engine, persistence
│   ├── transaction_split_manager.py      # Coordinates atomic transaction split allocation and unsplit restoration
│   └── transfer_reconciliation_manager.py# Coordinates unmatched candidate search and reconciliation engine
├── crud/                       # Legacy compatibility layer (retained for backward compatibility)
└── routers/                    # 11 Presentation / FastAPI route handlers
    ├── accounts.py             # Account CRUD, types, and reconciliation endpoints
    ├── budgets.py              # Budget allocation CRUD
    ├── categories.py           # Category & Group management and reordering
    ├── credit_cards.py         # CC summaries, transfer candidate search, and mark-transfers
    ├── ml.py                   # ML model status and on-demand retrain endpoints
    ├── plaid.py                # Link tokens, token exchange, account/tx sync endpoints
    ├── recurring.py            # Recurring series detection, listing, confirmation, dismissal
    ├── rules.py                # Categorization rule CRUD, preview, and retroactive apply
    ├── summaries.py            # Budget & Dashboard summary aggregations
    ├── transactions.py         # Paginated transaction ledger, filters, review, splits, cleared toggles, suggestions
    └── upload.py               # Inspect (/upload/inspect), format management, preview, confirm
```

---

## 5. Core Domain Logic & Accounting Invariants

1. **Monetary Sign Convention Invariant:**
   - Outflow / Debit / Purchase / Charge: **Positive (> 0)**
   - Inflow / Credit / Deposit / Income: **Negative (< 0)**
2. **Zero-Based Budgeting (ZBB):**
   $$\text{to\_be\_assigned} = \text{total\_income\_planned} - \text{total\_expense\_planned}$$
   - Expense Actuals: $\sum \text{allocated category actuals}$ (outflows > 0)
   - Income Actuals: $-1 \times \sum \text{allocated category actuals}$ (inflows < 0 converted to positive for display)
   - Expense Category Remaining: $\text{planned} - \text{actual}$
3. **Depository Account Balance Model:**
   - Depository (Checking / Savings / Cash) balances are derived from the transaction ledger:
     $$\text{current\_balance} = \text{starting\_balance} - \sum_{\text{all-time}} \text{Transaction.amount}$$
   - Outflows are positive in the ledger and reduce depository cash; inflows are negative and increase depository cash.
4. **Credit Card Debt Model:**
   $$\text{balance\_owed} = \text{starting\_balance} + \sum_{\text{all-time}} \text{Transaction.amount}$$
   - Charges: Sum of positive non-transfer transactions in current month.
   - Payments: Absolute sum of negative transactions in current month.
   - When cumulative payments exceed charges from a zero starting balance, `balance_owed` is negative, indicating an overpayment/credit balance.
5. **Transfer Matching Heuristic:**
   - Evaluates unlinked inflows (`amount < 0`, `is_transfer == False`) against unlinked outflows (`amount > 0`, `is_transfer == False`).
   - Pairs them if $|\text{date}_{\text{outflow}} - \text{date}_{\text{inflow}}| \le 2\text{ days}$ and $\text{account}_{\text{outflow}} \ne \text{account}_{\text{inflow}}$.
   - Approval sets `is_transfer = True` on both records.

---

## 6. Detailed Architectural Systems (Phases 7–12)

### 6.1. Account Reconciliation (Phase 7)
- **Engine / Domain Policy:** `backend/domain/account_reconciliation.py`
- **Manager:** `backend/managers/account_reconciliation_manager.py`
- **Accessors:** `backend/access/account_access.py`, `backend/access/transaction_access.py`
- **State Properties:**
  - `Transaction.is_cleared`: Boolean flag toggled as individual transactions clear the financial institution.
  - `Transaction.is_reconciled`: Boolean locking flag set when an account reconciliation is completed.
  - `Account.last_reconciled_date`: Date of the most recent completed reconciliation.
  - `Account.last_reconciled_balance`: Confirmed institution balance of the most recent reconciliation.
- **Workflow:**
  - Client retrieves current cleared balance via `GET /accounts/{id}/reconciliation`.
  - User toggles cleared transactions via `PATCH /transactions/{id}/cleared`.
  - Once the cleared balance equals the target statement balance, client calls `POST /accounts/{id}/reconciliation/complete`.
  - Atomically locks participating cleared transactions (`is_reconciled = True`) and updates the account's reconciliation watermark.
  - Reconciled transactions are protected against modifications to financial fields (`amount`, `date`, `account_id`).

### 6.2. Merchant Normalization (Phase 8)
- **Engine / Domain Policy:** `backend/domain/merchant_normalization.py`
- **Properties:**
  - `Transaction.description`: Preserves raw financial institution narrative without modification.
  - `Transaction.merchant`: Clean, normalized merchant name derived automatically.
  - `Transaction.is_merchant_overridden`: Flag indicating the user manually edited the merchant name, preventing automated recalculation.
- **Algorithm:**
  - Strips point-of-sale prefixes (`SQ *`, `TST*`, `PAYPAL *`, `SP *`, etc.).
  - Removes store IDs, phone numbers, terminal numbers, and geographical tags (`#\d+`, `STORE \d+`, `\b[A-Z]{2}\b`).
  - Generates normalized uppercase comparison key `clean_merchant_key` used for rule matching and recurring series clustering.

### 6.3. Categorization Rules Engine (Phase 9)
- **Domain Utility:** `backend/domain/categorization_rules.py`
- **Manager:** `backend/managers/categorization_rule_manager.py`
- **Accessor:** `backend/access/categorization_rule_access.py`
- **Table:** `categorization_rules` (`id`, `merchant`, `category_id`, `created_at`, `updated_at`)
- **Matching Semantics:**
  - Exact canonical merchant match: evaluated via `clean_merchant_key(merchant)` (case-insensitive, whitespace-collapsed).
  - Matches `merchant` only (does NOT match raw description; contains operators and priority sorting do NOT exist).
  - Uniqueness: Exactly one rule per canonical merchant identity (enforced by `uq_categorization_rules_merchant_canonical` unique index).
  - Display ordering: Rules are listed alphabetically by canonical merchant (`order_by(func.lower(func.trim(merchant)).asc())`).
- **Application:**
  - Evaluated synchronously during transaction staging (CSV import & Plaid sync) for transactions where `category_id IS NULL`.
  - Historical retroactive application is explicit/user-triggered via `POST /rules/{id}/apply`.
  - Split transactions are strictly excluded from retroactive rule application.

### 6.4. Machine Learning Categorization (Phase 10)
- **Engine:** `backend/domain/ml_categorization.py`
- **Manager:** `backend/managers/ml_categorization_manager.py`
- **Accessor:** `backend/access/ml_model_access.py`
- **Model Pipeline:**
  - scikit-learn `Pipeline` consisting of `TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))` and `LogisticRegression(C=2.0, class_weight='balanced')`.
  - Persisted locally to disk using `joblib` with atomic POSIX replacement (`os.replace`).
- **Precedence Hierarchy:**
  $$\text{Explicit User Category} > \text{Deterministic Rule} > \text{ML Suggestion} > \text{Uncategorized}$$
- **Operational Policies:**
  - Suggestion-only: ML provides suggestions with confidence operating scores; it **never** silently auto-categorizes transactions.
  - Threshold: Model abstains when confidence score is $< 0.30$.
  - Provenance Tracking: `Transaction.category_source` records `'manual'`, `'rule'`, `'ml'`, or `'legacy'`.
  - Supervised Training Eligibility: Only categories with `category_source IN ('manual', 'ml', 'legacy')` are eligible training signals; deterministic rules and unconfirmed predictions are strictly excluded.
  - Retraining: On-demand synchronous retraining triggered when `current_training_revision - trained_revision >= 10` (or manual call to `POST /ml/retrain`).
  - Quality Gate: Candidate models must meet minimum criteria ($\ge 10$ samples, $\ge 2$ classes, surfaced precision $\ge 50\%$, accuracy drop $\le 15$ percentage points below current model) before atomic activation.
  - Splits Exclusion: Split transactions have no single category; they never receive ML suggestions and never contribute training examples.

### 6.5. Recurring Transactions (Phase 11)
- **Engine:** `backend/domain/recurring_transactions.py`
- **Manager:** `backend/managers/recurring_transaction_manager.py`
- **Accessor:** `backend/access/recurring_access.py`
- **Table:** `recurring_items` (`id`, `account_id`, `merchant`, `direction`, `cadence`, `amount_type`, `expected_amount`, `status`, `last_date`, `next_expected_date`, `occurrence_count`, `created_at`, `updated_at`)
- **Detection Dimensions:**
  - Grouped by `(account_id, clean_merchant_key, direction)` where direction is `'outflow'` vs `'inflow'`.
  - Eligibility: Posted (`pending == False`), non-transfer (`is_transfer == False`), dated on or before today (`date <= as_of_date`), non-zero, non-blank merchant.
- **Exact Cadence Semantics & Constants:**
  - `weekly`: nominal 7 days; every interval in `[5, 9]` days; average interval in `[6.0, 8.0]` days.
  - `biweekly`: nominal 14 days; every interval in `[11, 17]` days; average interval in `[12.5, 15.5]` days.
  - `monthly`: nominal 1 calendar month; every interval in `[26, 35]` days; consecutive dates must be 1 calendar month apart (`month_diff == 1`); day difference $\le 4$ days OR both dates within 2 days of month-end (`day >= last_day - 2`).
  - `annual`: nominal 1 year; every interval in `[355, 375]` days; consecutive dates must be 12 calendar months apart (`month_diff == 12`); day difference $\le 5$ days OR both dates within 2 days of month-end.
- **Minimum Evidence:** $\ge 3$ posted occurrences (yielding at least 2 valid intervals).
- **Amount Stability:** Evaluates absolute monetary magnitudes. Classified as:
  - `fixed`: All amounts within $0.05 of the mean.
  - `variable`: Maximum-to-minimum ratio $\le 2.5$ and coefficient of variation $CV \le 0.35$.
- **Lifecycle & Status:**
  - Statuses: `detected`, `confirmed`, `dismissed`.
  - Re-detection clears stale auto-detected series while strictly preserving user `confirmed` and `dismissed` states.
  - `next_expected_date` is an informational pattern projection; it does not create transactions or alter ledger balances.

### 6.6. Split Transactions & Budget Actuals Flow (Phase 12)
- **Engine / Domain Policy:** `backend/domain/transaction_splits.py`
- **Manager:** `backend/managers/transaction_split_manager.py`
- **Accessor:** `backend/access/split_access.py`, `backend/access/transaction_access.py`
- **Table:** `transaction_splits` (`id`, `transaction_id` FK CASCADE, `category_id` FK RESTRICT, `amount`)
- **Core Domain Invariant:**
  > One parent `Transaction` remains the only financial event. `TransactionSplit` rows represent category allocation only.
- **Constraints & Rules:**
  - Split Allocation Sum Invariant: $\sum \text{split.amount} == \text{parent.amount}$ with exact Decimal precision.
  - Minimum 2 allocations; all allocation amounts must be non-zero and share the exact mathematical sign of the parent.
  - Unique constraint on `(transaction_id, category_id)`.
  - While split: `parent.category_id = NULL` and `parent.category_source = NULL`.
  - Uncategorized Semantics: A transaction is uncategorized only if `category_id IS NULL AND ~has_splits`.
- **Architectural Responsibility for Split Actuals Substitution:**
  - **ResourceAccess Responsibility (`transaction_access.get_actuals_by_category`):** Executes database queries combining:
    1. Unsplit transactions: `Transaction.category_id` + `Transaction.amount`
    2. Split allocations: `TransactionSplit.category_id` + `TransactionSplit.amount`
    into a pre-aggregated category total mapping (`dict[UUID, Decimal]`).
  - **Budget Engine Responsibility (`budgeting.py`):** Receives the pre-aggregated category actual totals from `BudgetSummaryManager` and calculates display actuals, category remaining, group totals, and `to_be_assigned`. The Budget Engine does not query or substitute transaction splits directly.
- **Balance Independence:** Splits never affect depository current balances, credit debt, reconciliation totals, or transaction count.
- **Mutual Exclusion:** Transfers and splits are mutually exclusive (`is_transfer == True` transactions cannot be split). Pending transactions cannot be split.
- **Reconciled Transactions:** Category allocations on reconciled transactions are permitted because category adjustments do not mutate financial fields (`amount`, `date`, `account_id`).

---

## 7. Cross-Feature Interaction Matrix

| Scenario / Feature | Normal Transaction | Split Transaction | Transfer Transaction | Reconciled Transaction | Pending Transaction |
|---|---|---|---|---|---|
| **Ledger Balance Calculation** | Full parent `amount` | Full parent `amount` (splits ignored) | Included in depository and debt balance | Full parent `amount` | Ledger net sums include pending records; remote Plaid balances use institution snapshot |
| **Budget Actuals** | Allocates parent `amount` to `category_id` | ResourceAccess combines child split amounts into category actuals | Included in actuals; excluded from summary totals only if category is type `transfer` | Allocated to category or child splits | Excluded from monthly budget actuals |
| **Deterministic Rules** | Applied during staging if uncategorized | **Excluded** from rule matching and retroactive batch apply | **Excluded** | Permitted via retroactive apply if `category_id IS NULL` | Applied during staging if uncategorized |
| **ML Suggestions** | Surfaced if uncategorized | **Excluded** (no suggestions, no training labels) | **Excluded** | Permitted if `category_id IS NULL` and not transfer | Excluded |
| **Recurring Detection** | Eligible if posted, non-transfer, non-zero ($\ge 3$ occurrences) | Eligible by parent `amount` & merchant | **Excluded** (`is_transfer == False`) | Eligible by parent `amount` & merchant | **Excluded** (`pending == False`) |
| **Account Reconciliation** | Cleared / Reconciled toggles | Cleared / Reconciled on parent | Cleared / Reconciled on parent | **Locked** (financial fields immutable) | Excluded from reconciliation queries |
| **Plaid Amount Update (Correction)** | Updates parent amount; flags unreviewed | **Deallocates child splits**, resets category, flags unreviewed | Updates parent amount | **Blocks financial mutation**, records conflict fields, returns warning | Updates parent amount |

---

## 8. Plaid Provider Correction Policies

During Plaid transaction synchronization (`/plaid/sync_transactions`):

1. **Non-Reconciled Transactions:**
   - If Plaid reports an updated amount for an unsplit transaction, the amount is updated and `is_reviewed` is set to `False`.
   - If Plaid reports an updated amount for a **split transaction**, the provider amount is authoritative: all child `transaction_splits` are invalidated/deleted, `parent.category_id` and `category_source` are reset to `None`, `is_reviewed` is set to `False`, and the transaction amount is updated.
2. **Reconciled Transactions (Conflict Guard):**
   - If Plaid reports an updated amount for an already-reconciled transaction (`is_reconciled == True`):
     - The financial mutation is **blocked** to protect reconciled historical integrity.
     - Reconciliation state and split allocations are strictly preserved.
     - The discrepancy is recorded on the transaction:
       - `Transaction.plaid_reconciliation_conflict_amount = new_amount`
       - `Transaction.plaid_reconciliation_conflict_at = datetime.utcnow()`
     - Sync cursor advances normally and a warning is included in the sync API response.
3. **Conflict Clearing:**
   - If a subsequent Plaid sync reports an amount matching the local reconciled amount, `plaid_reconciliation_conflict_amount` and `plaid_reconciliation_conflict_at` are reset to `None`.
   - Administrative review and reopening of reconciled provider conflicts is deferred to a future dedicated workflow.

---

## 9. Structural Modernization & Remaining Known Items

### 9.1. Addressed Through Modernization Slices
1. **Persistence Decoupled from Route Handlers:** Raw SQLAlchemy queries have been moved into 12 concrete ResourceAccess modules (`backend/access/`).
2. **Pure Business Calculations Extracted to Pure Engines:** 8 infrastructure-free calculation engines & domain policies in `backend/domain/` backed by 3 focused domain utilities.
3. **Meaningful Workflow Sequencing Isolated in Managers:** 13 focused workflow managers in `backend/managers/`.
4. **Timezone Offset Bug Resolved:** The frontend date truncation bug on `end_date` was resolved in commit `f1e2f92` by using `Date.UTC(...)` in date range helpers.
5. **Design System & Shared Components:** Shared typography, spacing, semantic colors, and dialog patterns centralized in `frontend/app/tokens.css`, `base.css`, `MonthNavigator.vue`, and `AppDialog.vue`.

### 9.2. Preserved Known Defects & Unresolved Domain Items
1. **`Transaction.description` Database/Schema Nullability Mismatch (Known Defect):**
   `models.Transaction.description` is nullable in PostgreSQL (`Text`, nullable=True), but Pydantic schemas enforce non-null `str`. Querying rows with `NULL` descriptions via standard endpoints causes serialization errors. Pinned via characterization test; preserved pending an intentional database/API migration slice.
2. **CategoryGroup Backend Deletion Cascade Inconsistency (Known Defect):**
   `backend/routers/categories.py` allows cascading deletion of category groups and child categories in the database, whereas `frontend/app/pages/categories.vue` blocks deleting non-empty groups in the UI. Preserved pending an intentional behavior decision.
3. **Credit Card `balance_owed` Includes Transfers While `charges_this_month` Excludes Them (Unresolved Domain Decision):**
   In `credit_cards.py`, `balance_owed` includes all transactions (including `is_transfer == True`), while `charges_this_month` filters out transfers. Pinned via characterization test.
4. **Credit Card `balance_owed` Includes Future-Dated Transactions (Unresolved Domain Decision):**
   All-time sum currently evaluates transactions regardless of whether `date` is in the future. Pinned via characterization test.
5. **Transfer Matching Greedy / Order-Dependent (Unresolved Domain Decision):**
   `detect_transfer_candidates` pairs transactions greedily in input list order without closest-date tie-breaking or persistent counterpart foreign keys. Pinned via characterization test.
6. **Insecure Credential Storage (Security Migration Pending):**
   `backend/security.py` uses base64 string encoding instead of authenticated symmetric encryption (Fernet/KMS). Plaid access tokens require cryptographic key migration in a dedicated security slice.
7. **Deferred Reconciled Plaid Corrections Workflow (Unresolved Follow-Up):**
   Material provider corrections to already-reconciled transactions are guarded by conflict recording fields. An explicit administrative workflow to reopen or reconcile provider conflicts remains deferred.
