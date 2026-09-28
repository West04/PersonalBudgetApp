# Refactoring Safety Map & Test Inventory

## 1. Overview & Strategy

Prior to architectural decomposition, safety nets were established to protect core accounting rules and behavior. The characterization harness was implemented using **`pytest`**, SQLite in-memory fixtures for rapid regression checking, and direct domain test fixtures:
- Core business invariants (such as zero-based budget calculations, credit card debt aggregation, transfer pairing heuristics, and CSV deduplication) are now covered by automated regression tests in `tests/`.
- All major workflows have corresponding characterization and integration tests verifying error handling, HTTP status codes, and edge-case contracts.
- The automated regression suite is executed with `python3 -m pytest`.

---

## 2. Test Coverage & Safety Matrix

The following matrix documents the key system behaviors characterized and protected by automated tests:

| # | Major Behavior | Relevant Source Files | Implemented Protection | Coverage Confidence | Characterized Invariants & Behavior |
|---|---|---|---|:---:|---|
| **1** | **Monetary Sign Convention** | `models.py`, `bank_statement_loader.py`, `access/transaction_access.py`, `domain/budgeting.py` | `test_decimal.py`, `test_characterization_zbb.py`, `test_unit_csv_parsing.py` | **High** | • Outflows (Purchases, Debits, Charges) > 0<br/>• Inflows (Deposits, Credits, Income) < 0<br/>• Income displayed positively in budget & dashboard reports. |
| **2** | **Manual Transaction CRUD** | `routers/transactions.py`, `schemas.py`, `access/transaction_access.py` | `test_characterization_transactions.py`, `test_access_transaction.py` | **High** | • Valid transaction creation with UUID<br/>• Nullable category_id<br/>• Decimal precision (`condecimal(10,2)`). |
| **3** | **CSV Statement Parsing** | `bank_statement_loader.py` | `test_unit_csv_parsing.py`, `test_unit_mapped_csv_parsing.py` | **High** | • USAA negates raw amount (credit/debit normalization)<br/>• Discover preserves raw charge amount<br/>• Configurable mapped formats handle custom dates and sign conventions<br/>• Tolerant parser records non-fatal row errors. |
| **4** | **CSV Transaction Confirmation & Deduplication** | `managers/csv_import_manager.py`, `access/transaction_access.py` | `test_characterization_csv_import.py`, `test_manager_csv_import.py`, `test_access_csv_import.py` | **High** | • Duplicate matching rule: exact `(account_id, date, amount, description)`<br/>• Duplicates are silently skipped without throwing 400/500 errors<br/>• Valid rows are inserted atomically. |
| **5** | **Plaid Synchronization** | `managers/plaid_*_sync_manager.py`, `access/plaid_*_access.py` | `test_characterization_plaid_*.py`, `test_manager_plaid_*.py` | **High** | • Plaid amounts inverted: `amount = -tx_data['amount']`<br/>• Idempotent upsert based on `plaid_transaction_id`<br/>• Cursor updated upon page exhaustion. |
| **6** | **Zero-Based Budget (ZBB) Calculation** | `domain/budgeting.py`, `managers/budget_summary_manager.py` | `test_domain_budgeting.py`, `test_characterization_zbb.py`, `test_manager_budget_summary.py` | **High** | • $\text{to\_be\_assigned} = \text{total\_income\_planned} - \text{total\_expense\_planned}$<br/>• Income actuals inverted (`actual = -raw_actual`)<br/>• Transfers excluded from income/expense totals. |
| **7** | **Dashboard Summary Calculation** | `managers/dashboard_summary_manager.py` | `test_manager_dashboard_summary.py`, `test_access_dashboard_summary.py` | **High** | • Planned, actual, and `to_be_assigned` match `get_budget_summary` output identically<br/>• Total balance = sum of active `account.current_balance`. |
| **8** | **Category Budget Remaining Calculations** | `domain/budgeting.py`, `routers/budgets.py` | `test_domain_budgeting.py`, `test_characterization_budgets.py` | **High** | • Expense: $\text{remaining} = \text{planned} - \text{actual}$; $\text{is\_over\_budget} = \text{remaining} < 0$<br/>• Income: $\text{remaining} = \text{planned} - \text{actual}$; $\text{is\_over\_budget} = \text{False}$. |
| **9** | **Transfer Candidate Matching** | `domain/reconciliation.py`, `managers/transfer_reconciliation_manager.py` | `test_domain_reconciliation.py`, `test_characterization_transfers.py`, `test_manager_transfer_reconciliation.py` | **High** | • Requires opposite signs: one positive (outflow), one negative (inflow)<br/>• Absolute amounts must match exactly<br/>• Accounts must differ<br/>• $|date_{outflow} - date_{inflow}| \le 2\text{ days}$<br/>• Neither transaction has `is_transfer == True`. |
| **10** | **Transfer Confirmation** | `routers/credit_cards.py`, `access/transaction_access.py` | `test_characterization_transfers.py`, `test_access_transfers.py` | **High** | • Sets `Transaction.is_transfer = True`<br/>• Bulk atomic update in PostgreSQL. |
| **11** | **Credit Card Balance & Metric Calculations** | `domain/credit_cards.py`, `managers/credit_card_summary_manager.py` | `test_domain_credit_cards.py`, `test_characterization_credit_cards.py`, `test_manager_credit_card_summary.py` | **High** | • $\text{balance\_owed} = \text{starting\_balance} + \sum_{\text{all-time}} \text{amount}$<br/>• Charges: sum of positive, non-transfer transactions in month<br/>• Payments: absolute sum of negative transactions in month. |
| **12** | **Category & Group Reordering** | `access/category_access.py`, `routers/categories.py` | `test_characterization_categories.py`, `test_access_category.py` | **High** | • Sequential 0-indexed `sort_order`<br/>• Category reordering preserves parent `group_id`<br/>• Preserves characterized handling of nulls, duplicates, and unlisted IDs. |

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

