# Refactoring Safety Map & Test Inventory

## 1. Overview & Strategy

Before executing any architectural refactoring, we must establish **safety nets**. A code audit reveals that the current test directory (`tests/`) contains zero unit tests:
- Existing test scripts (`smoke_test.py`, `repro_budget_issue.py`, `test_decimal.py`) are manual integration scripts requiring a live backend server running on `http://127.0.0.1:12344`.
- They primarily check HTTP status codes (`200 OK`) and JSON key presence rather than mathematical correctness, edge cases, sign inversions, or boundary conditions.
- Core business invariants (such as zero-based budget calculations, transfer pairing heuristics, and CSV deduplication) currently have **zero automated regression protection**.

The prerequisite to refactoring is writing **Characterization Tests** (using `pytest` and an isolated test environment) that pin down the exact behavior of the existing system before any code is moved or rewritten.

---

## 2. Test Coverage & Safety Matrix

| # | Major Behavior | Relevant Source Files | Existing Tests | Coverage Confidence | Characterization Tests Needed Before Refactoring | Important Invariants to Protect |
|---|---|---|---|:---:|---|---|
| **1** | **Monetary Sign Convention** | `models.py`, `bank_statement_loader.py`, `crud/plaid.py`, `routers/summaries.py` | None | **None** | Unit tests asserting sign conversions across all ingestion sources: USAA inverts debits to positive; Discover preserves positive charges; Plaid inverts negative debits; summaries invert negative income actuals to positive. | • Outflows (Purchases, Debits, Charges) > 0<br/>• Inflows (Deposits, Credits, Income) < 0<br/>• Income displayed positively in budget & dashboard reports. |
| **2** | **Manual Transaction Creation** | `routers/transactions.py`, `schemas.py`, `models.py` | `smoke_test.py` (reads list only) | **Low** | Test `POST /transactions/` creating a standalone record: test valid decimal amounts, positive vs negative amounts, null category ID, and null Plaid transaction ID. | • Creates valid transaction with generated UUID<br/>• Nullable category_id<br/>• Correct decimal precision (`condecimal(10,2)`). |
| **3** | **CSV Statement Parsing** | `bank_statement_loader.py`, `routers/upload.py` | `bank_statement_loader.py:main()` (manual CLI with hardcoded local paths) | **None** | In-memory unit tests using synthetic CSV text for `USAALoader` and `DiscoverLoader`: test header normalization, date parsing (`%Y-%m-%d` vs `%m/%d/%Y`), amount sign conversion, and missing column errors. | • USAA negates raw amount (credit/debit normalization)<br/>• Discover preserves raw charge amount<br/>• Unparseable rows raise or record parse errors. |
| **4** | **CSV Transaction Confirmation & Deduplication** | `routers/upload.py` (`_is_duplicate`, `confirm_csv`), `models.py` | None | **None** | Test importing a batch of transactions into an account; re-import the exact same batch and verify 100% of rows are marked `skipped` and zero new rows are inserted; import with 1 modified amount and verify 1 inserted, rest skipped. | • Duplicate matching rule: identical `(account_id, date, amount, description)`<br/>• Duplicates are silently skipped without throwing 400/500 errors<br/>• Valid rows are inserted atomically. |
| **5** | **Plaid Synchronization** | `crud/plaid.py`, `routers/plaid.py`, `crud/transaction.py` | `smoke_test.py` (asserts 404 on dummy item) | **Low** | Unit tests mocking Plaid API response: verify added transactions are inserted with inverted amounts; verify modified transactions update existing records by `plaid_transaction_id`; verify removed transactions delete records; verify `transactions_cursor` updates. | • Plaid amounts inverted: `amount = -tx_data['amount']`<br/>• Idempotent upsert based on `plaid_transaction_id`<br/>• Cursor updated upon page exhaustion. |
| **6** | **Zero-Based Budget (ZBB) Calculation** | `routers/summaries.py` (`get_budget_summary`) | `smoke_test.py` (status code 200 check) | **None** | Pure unit tests with synthetic category groups, budgets, and transactions: verify `total_income_planned`, `total_income_actual`, `total_expense_planned`, `total_expense_actual`, and `to_be_assigned`. | • $\text{to\_be\_assigned} = \text{total\_income\_planned} - \text{total\_expense\_planned}$<br/>• Income actuals inverted (`actual = -raw_actual`)<br/>• Transfers excluded from income/expense totals. |
| **7** | **Dashboard Summary Calculation** | `routers/summaries.py` (`get_dashboard_summary`) | `smoke_test.py` (verifies key presence) | **Low** | Test comparing dashboard metrics against budget summary metrics for the exact same dataset: verify planned/actual totals and `to_be_assigned` match identically; verify account balance sum. | • Planned, actual, and `to_be_assigned` must match `get_budget_summary` output identically<br/>• Total balance = sum of active `account.current_balance`. |
| **8** | **Category Budget Remaining Calculations** | `routers/summaries.py`, `routers/budgets.py` | None | **None** | Test remaining math: expense category with zero spent (`remaining == planned`); expense category partially spent; over-spent category (`is_over_budget == True`, `remaining < 0`); income category under-earned vs over-earned. | • Expense: $\text{remaining} = \text{planned} - \text{actual}$; $\text{is\_over\_budget} = \text{remaining} < 0$<br/>• Income: $\text{remaining} = \text{planned} - \text{actual}$; $\text{is\_over\_budget} = \text{False}$. |
| **9** | **Transfer Candidate Matching** | `routers/credit_cards.py` (`get_transfer_candidates`) | None | **None** | Test matching algorithm: identical amounts on same date across different accounts; 1-day difference (match); 2-day difference (match); 3-day difference (no match); same account (no match); already marked transfer (no match). | • Requires opposite signs: one positive (outflow), one negative (inflow)<br/>• Absolute amounts must match exactly<br/>• Accounts must differ<br/>• $|date_{outflow} - date_{inflow}| \le 2\text{ days}$<br/>• Neither transaction has `is_transfer == True`. |
| **10** | **Transfer Confirmation** | `routers/credit_cards.py` (`mark_transfers`), `routers/summaries.py` | None | **None** | Test submitting a pair of transaction IDs to `POST /credit-cards/mark-transfers`: verify both records now have `is_transfer = True`; verify they are immediately excluded from ZBB monthly actuals. | • Sets `Transaction.is_transfer = True`<br/>• Both sides neutralized in subsequent budget summary calculations. |
| **11** | **Credit Card Balance & Metric Calculations** | `routers/credit_cards.py` (`get_credit_card_summary`) | None | **None** | Test with credit card account having `starting_balance`, historical transactions from past months, and current month transactions: verify `balance_owed`, `charges_this_month`, and `payments_this_month`. | • $\text{balance\_owed} = \text{starting\_balance} + \sum_{\text{all-time}} \text{amount}$<br/>• Charges: sum of positive, non-transfer transactions in month<br/>• Payments: absolute sum of negative transactions in month. |
| **12** | **Category & Group Reordering** | `crud/category.py`, `routers/categories.py` | None | **None** | Test `POST /category-groups/reorder` and `POST /categories/reorder`: submit arbitrary permutation of UUIDs; verify sequential `sort_order` (0, 1, 2, ...) is updated in database and returned in correct order. | • Sequential 0-indexed `sort_order`<br/>• Category reordering preserves parent `group_id`<br/>• All existing items retained. |

---

## 3. Recommended Characterization Test Harness

To ensure rapid test execution and complete isolation without relying on Docker or live network ports, characterization tests should be implemented using:
- **`pytest`**: Test runner with parameterized test cases.
- **In-Memory SQLite (or dedicated local PostgreSQL test DB)**: Allows instant spinning up of tables via `models.Base.metadata.create_all()` with zero persistence pollution.
- **FastAPI `TestClient` (`httpx`)**: Tests route endpoints synchronously without spinning up Uvicorn.
- **Pure Domain Fixtures**: Tests calculation functions directly with plain Python objects (`Decimal`, `date`) without touching database tables.

### Phased Characterization Plan
1. **Phase 1: Pure Domain Tests**
   - Write tests for ZBB math (`to_be_assigned`, sign inversion, remaining).
   - Write tests for Credit Card debt calculation.
   - Write tests for Transfer matching heuristics.
   - Write tests for CSV parser row transformations.
2. **Phase 2: Database & Workflow Characterization Tests**
   - Write tests for CSV import duplicate skipping.
   - Write tests for manual transaction creation and updates.
   - Write tests for transfer marking.
   - Write tests for category and group reordering.
3. **Phase 3: Refactoring Execution**
   - Refactor modules one at a time, running the characterization test suite after every change to guarantee zero behavioral regressions.

---

## 4. Known Behaviors & Domain Decisions Discovered During Characterization

The following behaviors and invariants were discovered during characterization testing and code auditing:

### 1. `Transaction.description` Database/Schema Nullability Mismatch (Known Defect)
- **Current Behavior:** The SQLAlchemy model `Transaction.description` (`backend/models.py`) is defined as `Column(Text)` which is nullable in the database. In contrast, Pydantic schemas (`TransactionCreate`, `TransactionRead`, etc. in `backend/schemas.py`) define `description: str` as required / non-nullable.
- **Consequence:** Creating a transaction with `description: None` via `POST /transactions/` yields `422 Unprocessable Entity`. If a transaction with `description = None` exists in the database (e.g. from raw SQL or third-party sync), any endpoint attempting to serialize it via `TransactionRead` (e.g., `GET /transactions/` or `GET /summary/dashboard` via `recent_transactions`) raises a Pydantic `ValidationError` resulting in an HTTP `500 Internal Server Error`.
- **Status:** Treated as a **Known Defect**. Production behavior is preserved without modification during initial refactoring; pinned via explicit characterization test.

### 2. Backend Category-Group Deletion Allows Cascade Deletion (Known Defect)
- **Current Behavior:** In `backend/models.py`, `Category.group_id` specifies `ForeignKey("category_groups.category_group_id", ondelete="CASCADE")` and `CategoryGroup.categories` specifies `cascade="all, delete-orphan"`. The route `DELETE /category-groups/{group_id}` (`backend/routers/categories.py`) deletes the group, triggering cascading deletion of all member categories (and SQLAlchemy nulls out `category_id` on any associated budgets).
- **Consequence:** Although the frontend UI (`frontend/app/pages/categories.vue`) explicitly disables or prohibits deleting non-empty category groups to protect user data, the backend API permits cascade deletion without restriction.
- **Status:** Treated as a **Known Defect**. Production behavior is preserved without modification during initial refactoring; pinned via explicit characterization test.

### 3. Credit Card `balance_owed` Includes Transfers While `charges_this_month` Excludes Them (Unresolved Domain/Product Decision)
- **Current Behavior:** In `backend/routers/credit_cards.py` (`get_credit_card_summary`), `balance_owed` is computed as `starting_balance + sum(all-time transaction amounts)`, which includes transactions flagged with `is_transfer == True` (e.g., balance transfers or credit card payoff transfer legs). Concurrently, `charges_this_month` sums only positive transactions where `is_transfer == False`, explicitly excluding transfers.
- **Consequence:** Transfers affect the total outstanding debt balance on the card, but are excluded from the current month's spending charges metric.
- **Status:** Treated as an **Unresolved Domain/Product Decision** (rather than a bug). Behavior is preserved as intended until domain alignment is reached; pinned via characterization test in `test_characterization_credit_cards.py`.

