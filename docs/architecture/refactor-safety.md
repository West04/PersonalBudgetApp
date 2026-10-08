# Refactoring Safety Map & Test Inventory

## 1. Overview & Strategy

Prior to architectural decomposition and throughout Phases 1–12, comprehensive characterization harnesses and automated regression suites were established to protect core accounting rules and behavior. The regression harness is implemented using **`pytest`**, SQLite in-memory fixtures for rapid regression checking, and direct domain test fixtures:
- Core business invariants (zero-based budgeting, depository ledger balance, credit card debt, account reconciliation, merchant normalization, categorization rules, ML category suggestions, recurring transaction clustering, and split transaction allocations) are protected by automated tests in `tests/`.
- All major workflows have corresponding unit, manager, and characterization tests verifying HTTP status codes, schema contracts, and boundary conditions.
- The automated regression suite currently passes **946 tests** (with 28 warnings in ~31.9 seconds) via:
  ```bash
  python3 -m pytest
  ```

---

## 2. Test Coverage & Safety Matrix

The following matrix documents the key system behaviors characterized and protected by automated tests across all 12 feature phases:

| # | Major Behavior | Relevant Source Files | Implemented Protection | Coverage Confidence | Characterized Invariants & Behavior |
|---|---|---|---|:---:|---|
| **1** | **Monetary Sign Convention** | `models.py`, `bank_statement_loader.py`, `access/transaction_access.py`, `domain/budgeting.py` | `test_decimal.py`, `test_characterization_zbb.py`, `test_unit_csv_parsing.py` | **High** | • Outflows (Purchases, Debits, Charges) > 0<br/>• Inflows (Deposits, Credits, Income) < 0<br/>• Income displayed positively in budget & dashboard reports. |
| **2** | **Manual Transaction CRUD** | `routers/transactions.py`, `schemas.py`, `access/transaction_access.py` | `test_characterization_transactions.py`, `test_access_transaction.py` | **High** | • Valid transaction creation with UUID<br/>• Nullable category_id<br/>• Decimal precision (`condecimal(10,2)`). |
| **3** | **CSV Statement Parsing** | `bank_statement_loader.py` | `test_unit_csv_parsing.py`, `test_unit_mapped_csv_parsing.py` | **High** | • USAA negates raw amount (credit/debit normalization)<br/>• Discover preserves raw charge amount<br/>• Configurable mapped formats handle custom dates and sign conventions<br/>• Tolerant parser records non-fatal row errors. |
| **4** | **CSV Transaction Confirmation & Deduplication** | `managers/csv_import_manager.py`, `access/transaction_access.py` | `test_characterization_csv_import.py`, `test_manager_csv_import.py`, `test_access_csv_import.py` | **High** | • Duplicate matching rule: exact `(account_id, date, amount, description)`<br/>• Duplicates are silently skipped without throwing 400/500 errors<br/>• Valid rows are inserted atomically. |
| **5** | **Plaid Synchronization & Conflict Guards** | `managers/plaid_*_sync_manager.py`, `access/plaid_*_access.py` | `test_characterization_plaid_*.py`, `test_manager_plaid_*.py` | **High** | • Plaid amounts inverted: `amount = -tx_data['amount']`<br/>• Idempotent upsert based on `plaid_transaction_id`<br/>• Cursor updated upon page exhaustion<br/>• Provider amount corrections deallocate child splits and reset category on non-reconciled transactions<br/>• Reconciled transactions block provider mutations and record conflict fields. |
| **6** | **Zero-Based Budget (ZBB) Calculation** | `domain/budgeting.py`, `managers/budget_summary_manager.py`, `access/transaction_access.py` | `test_domain_budgeting.py`, `test_characterization_zbb.py`, `test_manager_budget_summary.py` | **High** | • $\text{to\_be\_assigned} = \text{total\_income\_planned} - \text{total\_expense\_planned}$<br/>• Income actuals inverted (`actual = -raw_actual`)<br/>• Transfers excluded from income/expense totals when category is type transfer<br/>• `transaction_access.get_actuals_by_category` aggregates unsplit transactions and child split amounts into category actuals before Budget Engine evaluation. |
| **7** | **Dashboard Summary Calculation** | `managers/dashboard_summary_manager.py` | `test_manager_dashboard_summary.py`, `test_access_dashboard_summary.py` | **High** | • Planned, actual, and `to_be_assigned` match `get_budget_summary` output identically<br/>• Liquid cash = sum of active depository ledger balances<br/>• Total credit debt = sum of active credit card `balance_owed`. |
| **8** | **Category Budget Remaining Calculations** | `domain/budgeting.py`, `routers/budgets.py` | `test_domain_budgeting.py`, `test_characterization_budgets.py` | **High** | • Expense: $\text{remaining} = \text{planned} - \text{actual}$; $\text{is\_over\_budget} = \text{remaining} < 0$<br/>• Income: $\text{remaining} = \text{planned} - \text{actual}$; $\text{is\_over\_budget} = \text{False}$. |
| **9** | **Transfer Candidate Matching** | `domain/reconciliation.py`, `managers/transfer_reconciliation_manager.py` | `test_domain_reconciliation.py`, `test_characterization_transfers.py`, `test_manager_transfer_reconciliation.py` | **High** | • Requires opposite signs: one positive (outflow), one negative (inflow)<br/>• Absolute amounts must match exactly<br/>• Accounts must differ<br/>• $|date_{outflow} - date_{inflow}| \le 2\text{ days}$<br/>• Neither transaction has `is_transfer == True`. |
| **10** | **Transfer Confirmation & Review** | `routers/credit_cards.py`, `routers/transactions.py`, `access/transaction_access.py` | `test_characterization_transfers.py`, `test_access_transfers.py`, `test_characterization_review.py` | **High** | • Sets `Transaction.is_transfer = True`<br/>• Bulk atomic update in PostgreSQL<br/>• Distinct `is_reviewed` tracking on all transactions. |
| **11** | **Credit Card Metrics & Overpayments** | `domain/credit_cards.py`, `managers/credit_card_summary_manager.py` | `test_domain_credit_cards.py`, `test_characterization_credit_cards.py`, `test_manager_credit_card_summary.py` | **High** | • $\text{balance\_owed} = \text{starting\_balance} + \sum_{\text{all-time}} \text{amount}$<br/>• Charges: sum of positive, non-transfer transactions in month<br/>• Payments: absolute sum of negative transactions in month<br/>• Negative `balance_owed` handled cleanly as overpayment/credit. |
| **12** | **Category & Group Reordering** | `access/category_access.py`, `routers/categories.py` | `test_characterization_categories.py`, `test_access_category.py` | **High** | • Sequential 0-indexed `sort_order`<br/>• Category reordering preserves parent `group_id`<br/>• Preserves characterized handling of nulls, duplicates, and unlisted IDs. |
| **13** | **Depository Current Balance** | `domain/accounts.py`, `managers/account_summary_manager.py` | `test_domain_accounts.py`, `test_manager_account_summary.py`, `test_characterization_depository_balances.py` | **High** | • $\text{current\_balance} = \text{starting\_balance} - \sum_{\text{all-time}} \text{amount}$<br/>• Outflows reduce cash; inflows increase cash. |
| **14** | **Account Reconciliation** | `domain/account_reconciliation.py`, `managers/account_reconciliation_manager.py` | `test_domain_account_reconciliation.py`, `test_manager_account_reconciliation.py`, `test_characterization_account_reconciliation.py` | **High** | • Tracks `is_cleared` toggles<br/>• Verifies cleared balance equals target statement balance<br/>• Atomically sets `is_reconciled = True`<br/>• Protects reconciled transactions against modifications to financial fields (`amount`, `date`, `account_id`). |
| **15** | **Merchant Normalization** | `domain/merchant_normalization.py` | `test_domain_merchant_normalization.py`, `test_characterization_merchant_normalization.py` | **High** | • Preserves raw narrative in `description`<br/>• Derives normalized `merchant` and `clean_merchant_key`<br/>• Strips POS prefixes, store IDs, state codes<br/>• Manual user override sets `is_merchant_overridden = True`. |
| **16** | **Categorization Rules** | `domain/categorization_rules.py`, `managers/categorization_rule_manager.py` | `test_domain_categorization_rules.py`, `test_manager_categorization_rule.py`, `test_characterization_categorization_rules.py` | **High** | • Canonical merchant key matching (`clean_merchant_key(merchant)` &rarr; `category_id`)<br/>• Single rule per canonical merchant (unique index)<br/>• Alphabetical display ordering by merchant<br/>• Retroactive batch execution updates uncategorized transactions (excluding splits) and sets `category_source = 'rule'`. |
| **17** | **ML Categorization Suggestions** | `domain/ml_categorization.py`, `managers/ml_categorization_manager.py`, `access/ml_model_access.py` | `test_domain_ml_categorization.py`, `test_manager_ml_categorization.py`, `test_characterization_ml.py` | **High** | • Character n-gram TF-IDF + Logistic Regression pipeline<br/>• Suggestion-only workflow; abstains below 0.30 confidence threshold<br/>• Strict provenance: only `manual`, `ml`, and `legacy` eligible for retraining; rules excluded<br/>• Quality gates enforce candidate accuracy and minimum sample counts before atomic POSIX replacement. |
| **18** | **Recurring Transactions** | `domain/recurring_transactions.py`, `managers/recurring_transaction_manager.py`, `access/recurring_access.py` | `test_domain_recurring_transactions.py`, `test_manager_recurring_transaction.py`, `test_characterization_recurring.py` | **High** | • Groups posted, non-transfer, non-zero transactions by `(account_id, clean_merchant_key, direction)`<br/>• Cadences: weekly (5–9d, avg 6–8), biweekly (11–17d, avg 12.5–15.5), monthly (26–35d, 1mo diff, day diff $\le 4$ or month-end), annual (355–375d, 12mo diff, day diff $\le 5$ or month-end)<br/>• Filters fixed ($0.05) or variable ($CV \le 0.35$) amounts<br/>• Upserts `recurring_items` table with `detected`, `confirmed`, `dismissed` statuses<br/>• Computes informational `next_expected_date` without mutating ledger balances. |
| **19** | **Split Transaction Allocations** | `domain/transaction_splits.py`, `managers/transaction_split_manager.py`, `access/split_access.py`, `access/transaction_access.py` | `test_domain_transaction_splits.py`, `test_manager_transaction_split.py`, `test_characterization_splits.py` | **High** | • One parent transaction remains sole financial event; child splits allocate categories<br/>• Exact sum invariant ($\sum \text{split.amount} == \text{parent.amount}$)<br/>• Min 2 allocations, non-zero amounts, same sign as parent<br/>• While split: `parent.category_id = NULL` and `parent.category_source = NULL`<br/>• Category actuals substitution performed by `transaction_access.get_actuals_by_category` (ResourceAccess)<br/>• Mutual exclusion with transfers and pending transactions<br/>• Reconciled category allocation permitted without mutating financial fields. |

---

## 3. Characterization Test Harness

The test suite runs via:
```bash
python3 -m pytest
```
Key harness components:
- **`pytest`**: Test runner with parameterized test fixtures.
- **In-Memory SQLite**: Fast isolated test database via `conftest.py` with zero persistence pollution.
- **FastAPI `TestClient` (`httpx`)**: Synchronous route endpoint tests without spinning up network servers.
- **Pure Domain Unit Tests**: Direct execution of domain calculation functions (`Decimal`, `date`) without touching database tables.

---

## 4. Known Behaviors & Domain Decisions Discovered During Characterization

The following behaviors and invariants were discovered during characterization testing and code auditing:

### 1. `Transaction.description` Database/Schema Nullability Mismatch (Resolved Defect)
- **Previous Behavior:** The SQLAlchemy model `Transaction.description` (`backend/models.py`) was defined as `Column(Text)` which was nullable in PostgreSQL, while Pydantic schemas (`TransactionCreate`, `TransactionRead`, etc. in `backend/schemas.py`) defined `description: str` as required / non-nullable. Creating a transaction with `description: None` via `POST /transactions/` yielded 422, but direct ORM/SQL inserts could store `NULL` and cause `ResponseValidationError` (HTTP 500) on read endpoints.
- **Resolution:**
  1. Backfilled legacy NULL rows to empty string `""` and enforced PostgreSQL `NOT NULL` on `transactions.description` via startup migration `migrate_transaction_description_integrity`.
  2. Updated SQLAlchemy model to `description = Column(Text, nullable=False)`.
  3. Added Pydantic `@field_validator("description")` to `TransactionUpdate` to reject explicit `null` with HTTP 422 while preserving omission and empty string `""`.
  4. Plaid synchronization normalizes provider `None` names to `""` at the staging boundary.
  5. The authoritative invariant is enforced: `Transaction.description` is always a non-null string; empty string `""` is the canonical representation when no description text exists; SQL `NULL` is prohibited.
- **Status:** **Resolved Defect**.

### 2. Backend Category-Group Deletion Blocks Non-Empty Groups (Resolved Defect)
- **Previous Behavior:** The route `DELETE /category-groups/{group_id}` (`backend/routers/categories.py`) permitted deleting category groups with child categories, triggering cascading deletion of child categories, nullifying transactions and budgets, and deleting categorization rules (or crashing on split transactions).
- **Resolution:** Backend enforces that a category group may be deleted only when it contains zero categories. If child categories exist, `category_access.delete_category_group` raises `ValueError`, which `routers/categories.py` maps to `HTTP 400 Bad Request` with detail `"Cannot delete category group containing categories. Move or delete categories first."`, preserving all category, transaction, budget, rule, and split data without mutation.
- **Status:** **Resolved Defect**. Aligned backend contract with existing frontend pre-delete guard.

### 3. Credit Card `balance_owed` Includes Transfers While `charges_this_month` Excludes Them (Unresolved Domain/Product Decision)
- **Current Behavior:** In `backend/domain/credit_cards.py`, `balance_owed` is computed as `starting_balance + sum(all-time transaction amounts)`, which includes transactions flagged with `is_transfer == True`. Concurrently, `charges_this_month` sums only positive transactions where `is_transfer == False`, explicitly excluding transfers.
- **Consequence:** Transfers affect the total outstanding debt balance on the card, but are excluded from the current month's spending charges metric.
- **Status:** Treated as an **Unresolved Domain/Product Decision**. Behavior is preserved as characterized.

### 4. Credit Card `balance_owed` Includes Future-Dated Transactions (Unresolved Domain Decision)
- **Current Behavior:** All-time sum currently evaluates transactions regardless of whether `date` is in the future.
- **Status:** Treated as an **Unresolved Domain Decision**. Behavior is preserved as characterized.

### 5. Transfer Matching Deterministic Closest-First Policy (Resolved Domain Decision)
- **Previous Behavior:** `detect_transfer_candidates` paired transactions greedily in input list order without closest-date tie-breaking or stable ordering.
- **Resolution:** Implemented deterministic closest-first greedy suggestion matching in `detect_transfer_candidates`. Eligible candidate pairs are ranked by smallest date distance first (`0` > `1` > `2`), followed by stable dates and transaction IDs breaking ties. Closest date distance strictly wins, input/database ordering dependence is eliminated, and each transaction appears in at most one suggestion.
- **Status:** **Resolved Domain Decision**.

### 6. Insecure Credential Storage (Deferred Security Debt)
- **Current Behavior:** `backend/security.py` uses base64 string encoding instead of authenticated symmetric encryption (Fernet/KMS). Plaid access tokens require cryptographic key migration in a dedicated security slice.
- **Status:** Treated as **Deferred Security Debt**. Behavior is preserved as characterized.

### 7. Deferred Reconciled Plaid Corrections Workflow (Unresolved Follow-Up)
- **Current Behavior:** Material provider corrections to already-reconciled transactions are blocked from mutating reconciled financial history, recording discrepancies in `plaid_reconciliation_conflict_amount` and `plaid_reconciliation_conflict_at`. An administrative workflow to reopen or resolve provider conflicts is deferred.
- **Status:** Treated as an **Unresolved Domain Decision / Follow-Up**. Behavior is preserved as characterized.

### 8. Resolved Defect: Frontend Timezone Date Offset on Month End
- **Previous Behavior:** In `frontend/app/pages/transactions.vue`, `end_date` computation using local midnight converted to UTC shifted the date back by one calendar day in positive UTC offset timezones, truncating end-of-month transactions.
- **Resolution:** Resolved in commit `f1e2f92` using `Date.UTC(...)` across frontend date range calculations.

### 9. Resolved Defect: Category Deletion Budget Cascade and Non-Null Integrity
- **Previous Behavior:** When deleting a category, SQLAlchemy ORM nullified `Budget.category_id` before deletion because `Category.budgets` omitted `cascade="all, delete", passive_deletes=True` and `Budget.category_id` was nullable. This bypassed database `ON DELETE CASCADE`, leaving orphaned budget rows with `category_id = NULL` that caused `GET /budget/` and `GET /budget/{id}` to crash with `fastapi.exceptions.ResponseValidationError` (HTTP 500).
- **Resolution:** Configured `Category.budgets` relationship with `cascade="all, delete", passive_deletes=True`, set `Budget.category_id` to `nullable=False`, added idempotent migration `migrate_budget_category_integrity` to purge orphaned rows and enforce PostgreSQL `NOT NULL`, and verified downstream API and budget summary integrity.

