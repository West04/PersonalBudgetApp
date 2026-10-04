# Budget App — CSV User-Test Pack & Acceptance Guide

## Purpose

This pack is a synthetic, repeatable test dataset for exercising the budget app end-to-end without using private bank statements.

The tests are designed around the current CSV-first workflow and the documented accounting convention:

- outflow / debit / charge > 0 in the app
- inflow / income / credit < 0 in the app
- income is displayed positively in budget/reporting

Do not inspect or mix in private files under the repository's `bank_statements/` directory for these tests.

---

# Before starting

1. Start the backend, frontend, and PostgreSQL database normally.
2. Record the current account/category/transaction state so you know what data existed before the test.
3. Create synthetic accounts with names that make the results obvious:
   - `TEST - USAA Checking`
   - `TEST - USAA Savings`
   - `TEST - Discover Card`
   - `TEST - International`
4. Create enough categories for the test, for example:
   - Income
   - Housing
   - Food
   - Transportation
   - Health
   - Bills
   - Test
   - Transfer
5. Select a test month such as June 2026 before beginning the budgeting tests.

---

# Import order

## 1. Import `01_usaa_checking_june_2026.csv`

Target account: `TEST - USAA Checking`

Use the built-in **USAA** format.

Expected Preview:

- 9 rows
- 9 valid rows
- 0 parse errors
- one pending transaction
- multiple expenses
- one income transaction
- one refund

Expected app amounts:

| Description | Expected app amount |
|---|---:|
| PAYROLL - ACME | -2500.00 |
| RENT | +1400.00 |
| GROCERY MART | +125.42 |
| UTILITY COMPANY | +84.17 |
| GAS STATION | +48.30 |
| COFFEE SHOP | +6.75 |
| PHARMACY | +22.19 |
| ONLINE SUBSCRIPTION | +15.99 |
| REFUND - GROCERY MART | -35.00 |

### Test

- [ ] Preview row count is 9.
- [ ] Dates are June 1–9, 2026.
- [ ] Descriptions are preserved.
- [ ] Purchase/debit signs are normalized to positive outflows.
- [ ] Payroll/deposit is normalized to a negative inflow.
- [ ] Pending status is preserved.
- [ ] Confirm imports 9 rows.
- [ ] Confirm reports 0 skipped and 0 errors.
- [ ] Persisted rows exactly match Preview.
- [ ] Transactions appear in the Transactions page.

---

# 2. Create the first June budget

Before continuing imports, build a June 2026 budget.

- [ ] Add planned income of 2500 or another clearly documented amount.
- [ ] Add planned amounts to Housing, Food, Transportation, Health, and Bills.
- [ ] Verify `to_be_assigned = planned income - planned expenses`.
- [ ] Edit at least one planned amount.
- [ ] Verify the edited value persists.
- [ ] Navigate away and return.
- [ ] Verify the selected month remains June 2026.
- [ ] Verify the budget remains persisted.

---

# 3. Categorize the USAA transactions

Assign categories to the imported June transactions.

Suggested mapping:

| Transaction | Category |
|---|---|
| RENT | Housing |
| GROCERY MART | Food |
| UTILITY COMPANY | Housing |
| GAS STATION | Transportation |
| COFFEE SHOP | Food |
| PHARMACY | Health |
| ONLINE SUBSCRIPTION | Bills |
| REFUND - GROCERY MART | Food |
| PAYROLL - ACME | Income |

- [ ] Categorize an expense.
- [ ] Categorize income.
- [ ] Change one category.
- [ ] Verify changes persist.
- [ ] Verify category actuals update.
- [ ] Verify remaining amounts update.
- [ ] Verify income actual is presented according to the current sign convention.
- [ ] Verify the refund can make an expense actual negative if applicable.

---

# 4. Import `02_usaa_checking_transfer_out_june_2026.csv`

Target account: `TEST - USAA Checking`

Use USAA format.

Expected: one +500.00 app outflow transaction after normalization.

- [ ] Preview is correct.
- [ ] Confirm imports 1 row.
- [ ] Verify the transaction exists.

---

# 5. Import `03_usaa_savings_transfer_in_june_2026.csv`

Target account: `TEST - USAA Savings`

Use USAA format.

Expected:

- transfer inflow represented as -500.00 in the app
- savings interest represented as -4.25 in the app

- [ ] Preview is correct.
- [ ] Confirm imports 2 rows.
- [ ] Verify both transactions exist.
- [ ] Find the +500 checking outflow and -500 savings inflow as transfer candidates.
- [ ] Confirm the candidate pair.
- [ ] Verify both transactions become marked as transfers.
- [ ] Verify transfer state persists after navigation/reload.
- [ ] Verify transfer treatment in budget/dashboard matches the current characterized behavior.

Do not modify transfer-matching policy during this user test.

---

# 6. Import `04_discover_june_2026.csv`

Target account: `TEST - Discover Card`

Use built-in **Discover** format.

Expected app amounts:

| Description | Expected app amount |
|---|---:|
| GROCERY MART | +82.15 |
| RESTAURANT ONE | +46.20 |
| STREAMING SERVICE | +17.99 |
| PAYMENT THANK YOU | -300.00 |
| REFUND MERCHANT | -24.50 |

- [ ] Preview dates are June 2026.
- [ ] Positive charges become positive outflows.
- [ ] Negative payment remains negative/inflow.
- [ ] Confirm imports 5 rows.
- [ ] Verify persisted rows match Preview.
- [ ] Categorize at least two charges.
- [ ] Verify credit-card view updates.
- [ ] Check `balance_owed`.
- [ ] Check `charges_this_month`.
- [ ] Check `payments_this_month`.
- [ ] Treat the currently documented transfer/future-date semantics as characterized behavior; do not change them during this acceptance test.

---

# 7. Import the custom international file

File: `06_international_dmy_custom.csv`

Target account: `TEST - International`

First create a custom format with:

```text
name: International Test
Date column: TxDate
description column: Narrative
amount column: Value
status column: Status
date format: %d/%m/%Y
```

Use the appropriate sign convention so positive source values become positive outflows and negative source values become negative inflows for this test.

### Important date test

The first five rows are intentionally chosen to reproduce the previous incident's dangerous ambiguity if `%m/%d/%Y` is incorrectly configured.

With the correct `%d/%m/%Y`, all six rows should be in September 2026.

- [ ] Format is detected.
- [ ] Preview shows September 1, 4, 7, 10, 12, and 15.
- [ ] Confirm persists the same dates.
- [ ] No date is silently moved into another month.
- [ ] Re-uploading the file detects the saved custom format.

---

# 8. Multi-month statement test

File: `05_multi_month_usaa_aug_sep_2026.csv`

Target: `TEST - USAA Checking`

Use USAA format.

This file intentionally crosses a month boundary:

- August 28
- August 31
- September 1
- September 15
- September 30

- [ ] Preview shows all 5 dates.
- [ ] Confirm imports all 5.
- [ ] Verify all 5 persisted dates.
- [ ] Verify August 2026 view shows the two August rows.
- [ ] Verify September 2026 view shows the three September rows.
- [ ] Verify selecting a month in one page and navigating to another page preserves the selected budgeting month when that page is month-scoped.
- [ ] Verify the post-import Transactions workflow does not incorrectly hide part of the statement.

---

# 9. Duplicate import safety

File: `10_same_file_duplicate_demo_usaa.csv`

Target: any dedicated test account.

### First import

- [ ] Preview 2 valid rows.
- [ ] Confirm imports 2.

### Second import of the exact same file

- [ ] Confirm reports the rows as skipped according to the existing duplicate contract where they already exist.
- [ ] Verify no extra ledger rows appear unexpectedly.
- [ ] Record imported/skipped counts.

### Important

The current documented duplicate identity is:

```text
(account_id, date, amount, description)
```

Do not broaden or change the matching rule during this acceptance test.

---

# 10. Overlapping statement test

Use the following in order:

1. `07_overlap_statement_a_aug_sep_2026.csv`
2. `08_overlap_statement_b_sep_oct_2026.csv`

Use the same target account.

Rows `OVERLAP COMMON - 09/01` and `OVERLAP A - 09/05` appear in both statements.

Expected:

- First file imports 4 rows.
- Second file imports only the genuinely new rows under the current exact-match rule.
- The shared rows are skipped.
- No unexpected duplicates appear.

- [ ] Verify counts.
- [ ] Verify shared rows are not duplicated.
- [ ] Verify the October row is present.
- [ ] Verify month filtering still works across September/October.

---

# 11. Row-error usability

File: `09_malformed_rows_usaa.csv`

Target: dedicated test account.

Contains:

- valid row
- malformed date
- malformed amount
- valid pending row

### Preview

- [ ] Valid rows remain visible.
- [ ] Malformed rows show useful errors.
- [ ] Error count is correct.
- [ ] Valid rows retain correct dates/amounts.

### Confirm

- [ ] Confirm behavior is understandable.
- [ ] Valid rows are handled according to the current tolerant import contract.
- [ ] Invalid rows are reported.
- [ ] No silent data loss occurs.

---

# 12. Transactions page / navigation test

This specifically covers the navigation issue already discovered during acceptance.

Start on June 2026.

- [ ] Select June 2026.
- [ ] Select a specific account.
- [ ] Confirm expected transactions are visible.
- [ ] Navigate to another tab/page.
- [ ] Return to Transactions.
- [ ] Verify the selected month did not reset to the current calendar month.
- [ ] Verify the account filter behaves as intended.
- [ ] Click the sidebar Transactions link.
- [ ] Verify the month behavior matches the application's chosen shared-month design.
- [ ] Use browser back/forward and verify the month context remains coherent.

Observed:
    "Month persists as expected across all navigation. Account filter
    persists with browser back/forward, but resets when clicking sidebar
    link. Uncategorized and search filters reset on page leave (local component state)."

---

# 13. Dashboard consistency

After categorization and transfer confirmation:

- [ ] Check account balances.
- [ ] Check budget health.
- [ ] Check recent transactions.
- [ ] Compare several values against the Transactions and Budget pages.
- [ ] Verify month selection is consistent.

---

# 14. Two-month budgeting test

Use June and July 2026.

- [ ] Create/adjust June budget.
- [ ] Create/adjust July budget.
- [ ] Verify allocations are month-specific.
- [ ] Verify June transactions affect June actuals.
- [ ] Verify July transactions do not affect June actuals.
- [ ] Verify dashboard month switching.
- [ ] Verify credit-card monthly metrics.

---

# 15. Restart / persistence test

After completing the above workflows:

1. Stop backend/frontend.
2. Restart the application.
3. Verify:

- [ ] Accounts remain.
- [ ] Categories remain.
- [ ] Budgets remain.
- [ ] Transactions remain.
- [ ] Categories assigned to transactions remain.
- [ ] Transfer flags remain.
- [ ] Custom CSV format remains.
- [ ] Selected month behavior remains sensible.

---

# 16. CSV-first readiness checklist

## Import reliability

- [ ] USAA import works.
- [ ] Discover import works.
- [ ] Custom format import works.
- [ ] Preview matches Confirm/persistence.
- [ ] Date formats are correct.
- [ ] Sign conventions are correct.
- [ ] Pending status works.
- [ ] Duplicate handling is understandable.
- [ ] Overlapping statements are manageable.
- [ ] Malformed-row behavior is understandable.

## Budgeting

- [ ] Accounts work.
- [ ] Categories work.
- [ ] Budget creation/editing works.
- [ ] `to_be_assigned` is understandable.
- [ ] Actuals reconcile with transactions.
- [ ] Remaining amounts make sense.
- [ ] Transfers work.
- [ ] Dashboard values reconcile.

## UX

- [ ] Selected month survives navigation.
- [ ] Transaction filtering is understandable.
- [ ] Import results are understandable.
- [ ] Errors are actionable.
- [ ] Empty states make sense.
- [ ] Loading states make sense.
- [ ] No workflow feels unexpectedly blocked.

## Persistence

- [ ] Restart preserves data.
- [ ] No imported transactions appear to disappear.
- [ ] No unexpected duplicates appear.

---

# What to record when something goes wrong

For every failure, record:

```text
Workflow:
File:
Target account:
Selected month:
Expected result:
Actual result:
Preview count:
Confirm imported:
Confirm skipped:
Confirm errors:
Database count:
Transactions API count:
UI count:
Exact error message:
```

The most valuable debugging distinction is:

```text
Preview
  ↓
Confirm
  ↓
Database
  ↓
Transactions API
  ↓
UI
```

Identify the first point where expected data diverges.

---

# Readiness gate

When the full test pass is complete, make one explicit decision:

```text
CSV-FIRST READY FOR REAL USE
```

or:

```text
CSV-FIRST NOT READY — BLOCKERS FOUND
```

If blockers remain, fix only the highest-impact blocker, add regression coverage, rerun the affected workflow, and repeat.

---

# After CSV readiness

The next major product phase should be the frontend redesign rather than another speculative backend architecture pass.

Recommended order:

```text
CSV-first acceptance
    ↓
real budgeting cycle
    ↓
frontend redesign
    ↓
Transactions-first UX
    ↓
merchant normalization
    ↓
deterministic categorization rules
    ↓
ML category suggestions
    ↓
optional LLM assistance
```

The auto-categorizer should treat user-confirmed categories as authoritative and start with deterministic rules before introducing ML.

---

# Optional future feature candidates

These are roadmap candidates, not current acceptance requirements:

- recurring transactions / bills
- account reconciliation
- merchant/payee normalization
- transaction rules
- bulk edits
- split transactions
- richer reporting/analytics
- savings goals
- forecasting
- net worth
- investments

Do not let these features expand the current acceptance scope.

---

# Acceptance Observations & Characterized Behaviors

### 1. Credit Card Negative Balance Owed
- **Formula:** `balance_owed = starting_balance + (all-time net transactions)`
- **Accounting Sign Convention:** Outflows / charges > 0; Inflows / payments / credits < 0.
- **Why `balance_owed` was negative (`-$178.16`) in Step 6:**
  - `TEST - Discover Card` was initialized with `starting_balance = $0.00`.
  - Charges totaled `+$146.34` (`$82.15` + `$46.20` + `$17.99`).
  - Inflows totaled `-$324.50` (`-$300.00` payment + `-$24.50` refund).
  - Net: `$0.00 + $146.34 - $324.50 = -$178.16`.
- **Domain Interpretation:** A positive balance owed represents outstanding debt to the card issuer; a negative balance owed represents an overpayment / credit balance (the card issuer owes you money). If an existing debt was carried prior to importing transactions, set `starting_balance` accordingly (e.g., via the pencil edit icon ✏️ on the Credit Cards page).

### 2. Transactions Page Filter State & Navigation Lifecycle
- **Budget Month (`selectedMonth`):** Persisted globally across all month-scoped views via [`useBudgetMonth`](file:///Users/west/programming_stuff/budget_app/frontend/app/composables/useBudgetMonth.ts) (`useState('selected_budget_month')`) and synchronized to `?month=YYYY-MM`. Survives navigation across tabs and sidebar clicks.
- **Account Filter (`selectedAccount`):** Synchronized to route query `?account_id=...` in [`transactions.vue`](file:///Users/west/programming_stuff/budget_app/frontend/app/pages/transactions.vue).
  - **Browser Back / Forward:** Restores `account_id` from history as expected.
  - **Sidebar Links:** The sidebar link in [`app.vue`](file:///Users/west/programming_stuff/budget_app/frontend/app/app.vue) navigates to `/transactions?month=...` without an `account_id`, which intentionally resets the view to "All Accounts".
- **Secondary Filters (`uncategorizedOnly`, `searchQuery`, `selectedCategory`):**
  - Stored purely as local component `ref`s inside [`transactions.vue`](file:///Users/west/programming_stuff/budget_app/frontend/app/pages/transactions.vue).
  - When navigating away to another tab, the component is unmounted and destroyed; returning to the page remounts it fresh with default values (`uncategorizedOnly = false`, blank search, blank category).
  - Preserving secondary filters in the route query or session storage is noted for the post-acceptance frontend redesign phase ("Transactions-first UX").

