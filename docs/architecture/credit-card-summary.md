# Credit-Card Summary Architecture Specification (Slice 3)

## 1. Overview & Conceptual Architecture

The Credit-Card Summary workflow (`GET /credit-cards/summary`) provides a per-account breakdown of credit card debts, monthly charges, monthly payments, and monthly transaction activity.

Rather than executing raw database queries, orchestrating multi-entity data loading, and mapping calculations inside the FastAPI route handler, the Credit-Card Summary workflow is decomposed using Volatility-Based Decomposition (VBD):

```text
FastAPI Credit Card Router (backend/routers/credit_cards.py)
          ↓
Credit Card Summary Manager (backend/managers/credit_card_summary_manager.py)
     ├── Shared Date Helper (backend/domain/dates.py)
     ├── Credit Card Engine (backend/domain/credit_cards.py)
     ├── Account Access (backend/access/account_access.py) ──────────→ PostgreSQL
     └── Transaction Access (backend/access/transaction_access.py) ──→ PostgreSQL
```


### Authoritative Calculation Component
The authoritative business calculation remains:

```python
backend.domain.credit_cards.calculate_credit_card_state(...)
```

The Manager must directly invoke this existing Engine rather than duplicating or wrapping its formulas.

---

## 2. Layer Responsibilities & Boundaries

### 2.1. Presentation / Router ([`backend/routers/credit_cards.py`](../../backend/routers/credit_cards.py))
**Owns:**
- HTTP query parameter validation (`month: str = Query(..., pattern=r"^\d{4}-\d{2}$")`).
- Parsing `month: str` into `budget_month: date` via standard ISO conversion.
- HTTP error mapping: converting invalid calendar months (e.g. `2026-13`) into `HTTPException(400, detail="Invalid month format. Use YYYY-MM")`.
- Database session acquisition (`db: Session = Depends(get_db)`).
- Calling the Manager: `credit_card_summary_manager.get_credit_card_summary(db, budget_month)`.
- Converting immutable application dataclasses returned by the Manager into Pydantic HTTP response models:
  - [`schemas.CreditCardSummaryResponse`](../../backend/schemas.py);
  - [`schemas.CreditCardAccountSummary`](../../backend/schemas.py);
  - [`schemas.CreditCardTransactionRead`](../../backend/schemas.py).

**Must NOT retain:**
- SQLAlchemy query construction or execution.
- Per-card transaction retrieval orchestration.
- Mapping ORM transaction instances into Engine inputs.
- Financial metric calculation logic (`balance_owed`, `charges_this_month`, `payments_this_month`).

---

### 2.2. Credit Card Summary Manager (`backend/managers/credit_card_summary_manager.py`)
**Owns:**
- Resolving `[start_date, end_date)` via the shared domain date utility [`backend.domain.dates.determine_month_range`](../../backend/domain/dates.py).
- Loading active credit accounts through Account ResourceAccess (`account_access.get_active_credit_accounts(db)`).
- Loading all historical transactions for each account through Transaction ResourceAccess (`transaction_access.get_transactions_for_account(db, account.id)`).
- Mapping persistence ORM records to pure [`CreditCardTransaction`](../../backend/domain/credit_cards.py) domain models.
- Invoking [`calculate_credit_card_state(...)`](../../backend/domain/credit_cards.py) once per active credit account.
- Selecting transactions that fall within `start_date <= tx.date < end_date` for monthly display.
- Mapping persistence records into immutable application result structures.
- Assembling and returning `CreditCardSummaryResult`.

**Pragmatic Coupling Decision:**
- The Manager accepts `db: Session` under the project's established pragmatic coupling decision (Session 1 & Checkpoint 1: database engine substitution is not an identified axis of volatility).
- This input coupling does **not** grant permission to leak ORM models, Pydantic schemas, or FastAPI types through the Manager's public output signature.

---

### 2.3. ResourceAccess ([`backend/access/`](../../backend/access/))
**Owns:**
- Concrete SQLAlchemy queries, filtering, ordering, and session execution.
- Isolating concrete database mechanics from business workflows.

**Approved Operations:**

1. **Account Access ([`backend/access/account_access.py`](../../backend/access/account_access.py)):**
   ```python
   def get_active_credit_accounts(
       db: Session,
   ) -> Sequence[models.Account]:
       """
       Retrieves all active credit accounts ordered by name ascending.
       """
   ```
   *Behavior:* Filters strictly by `models.Account.type == "credit"` and `models.Account.is_active == True`. Ordered by `models.Account.name.asc()`. No secondary ordering.

2. **Transaction Access ([`backend/access/transaction_access.py`](../../backend/access/transaction_access.py)):**
   ```python
   def get_transactions_for_account(
       db: Session,
       account_id: UUID,
   ) -> Sequence[models.Transaction]:
       """
       Retrieves all historical transactions for a specific account ordered by date descending.
       """
   ```
   *Behavior:* Filters by `models.Transaction.account_id == account_id`. Ordered by `models.Transaction.date.desc()`. No secondary ordering.

**Boundary Rules:**
- Accessors return concrete persistence ORM records (`models.Account`, `models.Transaction`) to the Manager.
- Accessors must **not** import Manager result types.

---

## 3. Approved Manager Output Contract (Pure Application Dataclasses)

The Manager's public result contract is strictly decoupled from ORM models and presentation schemas:

```python
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from ..domain.credit_cards import CreditCardState


@dataclass(frozen=True)
class CreditCardMonthlyTransactionItem:
    transaction_id: UUID
    description: str
    amount: Decimal
    date: date
    is_transfer: bool
    category_id: Optional[UUID] = None


@dataclass(frozen=True)
class CreditCardAccountSummaryItem:
    account_id: UUID
    account_name: str
    state: CreditCardState
    transactions: Sequence[CreditCardMonthlyTransactionItem]


@dataclass(frozen=True)
class CreditCardSummaryResult:
    cards: Sequence[CreditCardAccountSummaryItem]
```

### Rationale:
- Reusing `state: CreditCardState` directly from [`backend.domain.credit_cards`](../../backend/domain/credit_cards.py) is approved because it is already an immutable, pure domain result. Duplicating its fields into another DTO would add boilerplate without reducing coupling.
- The Manager's result contains no ORM models, Pydantic schemas, or FastAPI types. The presentation router unpacks `card.state.starting_balance`, `card.state.balance_owed`, etc. when constructing [`schemas.CreditCardAccountSummary`](../../backend/schemas.py).

---

## 4. Shared Pure Month-Range Helper

Reuses the established domain helper in [`backend/domain/dates.py`](../../backend/domain/dates.py):

```python
def determine_month_range(month_date: date) -> tuple[date, date]:
    """
    Returns the half-open interval [start_date, end_date) for a given month date.
    Normalizes start_date to the first day of the month.
    Handles December-to-January year rollover correctly.
    """
```

### Boundary & Lifecycle:
- Semantics match the Credit-Card route's previous calendar interval logic exactly (`[YYYY-MM-01, next_month-01)`).
- The presentation router validates the string and parses it to `budget_month: date`. The Manager passes `budget_month` to `determine_month_range`.
- The previous private `get_month_range` helper in `routers/credit_cards.py` was removed during Slice 3 implementation. The summary workflow now reuses `backend.domain.dates.determine_month_range`.
- No new calendar or date abstractions are introduced.

---

## 5. Explicit N+1 Persistence Query Decision

During this structural slice, persistence execution intentionally remains:

```text
1 active-credit-account query
+
1 transaction-history query per active credit account
```

### Rationale:
- **Architectural Discipline:** The primary goal of this vertical slice is to isolate workflow orchestration and ResourceAccess boundaries while preserving existing persistence behavior.
- **Optimization Decoupling:** Query batching is an optimization concern, not an architectural boundary justification. Mixing query batching into this structural slice would conflate performance tuning with architectural refactoring.
- The N+1 query pattern is not described as desirable, nor is it justified by speculative speed claims. Rather, it is preserved intentionally to isolate variables during refactoring.
- A future batched transaction query (e.g. `Transaction.account_id.in_(account_ids)`) remains a candidate optimization only if measured profiling later warrants it.

---

## 6. Implementation Invariants & Preserved Behaviors

The refactoring slice must preserve all characterized existing behaviors exactly:

### 6.1. Credit-Card Calculation Semantics (Resolved Product Contract)
- `balance_owed` is calculated as `starting_balance + sum(tx.amount for tx in transactions if tx.date < cutoff_exclusive)`.
- Transactions with `is_transfer == True` **remain included** in `balance_owed` (card-payment transfers reduce debt, positive transfers increase debt).
- Merchant refunds/credits (`amount < 0, is_transfer == False`) reduce `balance_owed`.
- Positive transactions with `is_transfer == True` **remain excluded** from `charges_this_month` (not a purchase charge).
- `charges_this_month` reflects gross positive non-transfer charges in `[period_start, cutoff_exclusive)`. Merchant refunds do not reduce this metric.
- `payments_this_month` includes **only negative transfer payments** (`amount < 0 and is_transfer == True`) in `[period_start, cutoff_exclusive)`. Merchant refunds and non-transfer credits are strictly excluded.
- Future-dated transactions (`tx.date >= cutoff_exclusive`) are **strictly excluded** from point-in-time `balance_owed` and monthly activity.

### 6.2. Persistence Field Handling
- `account.starting_balance` is passed directly to the Engine (which normalizes it to Decimal).
- `account.current_balance` is **not used** by the credit card summary workflow.
- `transaction.description` is passed through directly from persistence to schema (enforced as non-null string in persistence and schema).
- `transaction.category_id` passes through as `UUID` or `None`.
- `transaction.amount`, `date`, and `is_transfer` are passed through directly.

### 6.3. Ordering Semantics
- Active credit accounts are ordered by `name ASC` with **no secondary sort**.
- Account transactions are ordered by `date DESC` with **no secondary sort**.
- Monthly display filtering iterates in memory preserving the `date DESC` order.

### 6.4. Empty State Semantics
- An active card with zero transactions returns `balance_owed = starting_balance`, `charges_this_month = 0.00`, `payments_this_month = 0.00`, and `transactions = []`.
- When no active credit accounts exist, the endpoint returns `{"month": "YYYY-MM", "cards": []}` with HTTP 200.

### 6.5. HTTP Presentation Semantics
- Regex-invalid `month` parameter (e.g. `month="bad"`) returns FastAPI validation failure (`HTTP 422`).
- Regex-valid but calendar-invalid `month` parameter (e.g. `month="2026-13"`) returns `HTTP 400` with `{"detail": "Invalid month format. Use YYYY-MM"}`.

---

## 7. Existing Engine Remains Authoritative

The existing domain engine in [`backend/domain/credit_cards.py`](../../backend/domain/credit_cards.py):

```python
calculate_credit_card_state(
    starting_balance: Decimal,
    transactions: Sequence[CreditCardTransaction],
    period_start: date,
    period_end: date,
    cutoff_exclusive: Optional[date] = None,
) -> CreditCardState
```

remains the sole authoritative calculation component. It owns:
- starting-balance conversion;
- `balance_owed` (point-in-time through cutoff);
- `charges_this_month` (gross charges in period through cutoff);
- `payments_this_month` (transfer payments in period through cutoff).


The Manager must not duplicate, wrap, or re-implement any of these calculations.

---

## 8. Explicitly Rejected Abstractions & Non-Goals

To maintain strict VBD discipline and avoid overengineering, the following are deliberately rejected:

1. **`ICreditCardManager`:** No substitutability requirement exists; a single concrete manager module is used.
2. **`CreditCardCalculator` / Duplicate Engine:** The existing domain engine already satisfies all requirements.
3. **Generic Repository Abstractions:** Generic `IRepository<T>` patterns are rejected in favor of focused, concrete Accessor functions in `account_access.py` and `transaction_access.py`.
4. **Arbitrary Query Filtering Parameters:** We do not generalize `get_active_accounts(type=...)`; focused concrete operations are preferred.
5. **Statement-Cycle / Billing-Period Modeling:** The product currently tracks calendar months and all-time balances; statement cycle abstractions are speculative.
6. **APR / Minimum Payment / Financing Engines:** Not part of current application requirements.
7. **Batched Transaction Queries:** Deferred to keep this structural slice focused on boundary extraction.
8. **Unit of Work / Dependency Injection Containers:** Pragmatic session coupling is preserved.
9. **UI / Frontend Changes:** Nuxt views remain untouched.
10. **Adjacent Workflows:** `GET /credit-cards/transfer-candidates` and `POST /credit-cards/mark-transfers` remain untouched in `routers/credit_cards.py`.

---

## 9. Characterization Safety Net

Before any production code refactoring, characterization tests in [`tests/test_characterization_credit_cards.py`](../../tests/test_characterization_credit_cards.py) explicitly verify:

- Multiple active credit cards;
- Alphabetical card ordering (`name ASC`);
- Transaction and balance isolation between credit cards;
- Active card with zero transactions;
- Empty credit card list when no active cards exist;
- Monthly display transaction ordering (`date DESC`);
- Exact response field contract and types;
- Handling of populated UUID and `None` for `category_id`;
- Calendar-invalid month format returning HTTP 400;
- Regex-invalid month format returning HTTP 422.

Baseline test suite status before production refactoring: **65 passed**.

---

## 10. Implementation & Verification Status

- **Status:** Slice 3 Implemented & Verified
- **Baseline suite:** 65 passed
- **Post-refactor suite:** 71 passed
- **Production files added:**
  - `backend/managers/credit_card_summary_manager.py`
- **Production files modified:**
  - `backend/access/account_access.py` (added `get_active_credit_accounts`)
  - `backend/access/transaction_access.py` (added `get_transactions_for_account`)
  - `backend/managers/__init__.py` (re-exported `credit_card_summary_manager` types and entrypoint)
  - `backend/routers/credit_cards.py` (delegated `/summary` route to `credit_card_summary_manager`, removed private `get_month_range` duplicate)
- **Test files added:**
  - `tests/test_access_credit_cards.py` (verified `get_active_credit_accounts` and `get_transactions_for_account`)
  - `tests/test_manager_credit_card_summary.py` (verified pure orchestration, engine delegation, isolation, ordering, and data mapping)
- **Architecture Invariants Verified:**
  1. Router contains zero SQLAlchemy queries for `/summary`.
  2. Router contains zero Engine invocations.
  3. Manager contains zero FastAPI or Pydantic imports.
  4. Manager performs zero SQL query construction.
  5. Accessors do not import Manager types.
  6. ORM entities do not cross Manager -> Router boundary.
  7. Existing Engine `calculate_credit_card_state` remains authoritative and unchanged.
  8. 1 + N query behavior is preserved.
  9. Ordering semantics (`name ASC`, `date DESC`) are strictly preserved.
  10. Adjacent workflows (`transfer-candidates`, `mark-transfers`) remain untouched.

