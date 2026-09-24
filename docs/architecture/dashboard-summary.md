# Dashboard Summary Architecture Specification (Slice 2)

## 1. Overview & Conceptual Architecture

The Dashboard Summary workflow (`GET /summary/dashboard`) provides a composite monthly view consisting of zero-based budget metrics, active account balances, and recent transaction history.

Rather than reconstructing budget calculations or executing raw SQL queries in the route handler, the Dashboard Summary workflow is decomposed using Volatility-Based Decomposition (VBD) with direct application-level composition:

```text
FastAPI Dashboard Router
        │
        ▼
Dashboard Summary Manager
        ├── existing Budget Summary workflow (BudgetSummaryManager)
        ├── Account ResourceAccess (account_access)
        └── Transaction ResourceAccess (transaction_access)
```

The existing Budget Summary workflow remains unchanged as the reference vertical slice:

```text
Budget Summary Manager
        ├── Budget Engine (calculate_budget_summary)
        ├── Category Access (get_category_groups)
        ├── Budget Access (get_budgets_for_month)
        └── Transaction Access (get_actuals_by_category)
```

---

## 2. Layer Responsibilities & Boundaries

### 2.1. Presentation / Router ([`backend/routers/summaries.py`](../../backend/routers/summaries.py))
**Owns:**
- HTTP query parameter parsing (`month: str = Query(..., pattern=r"^\d{4}-\d{2}$")`).
- HTTP validation and error mapping (parsing `month` to `budget_month: date`; returning `HTTPException(400)` on malformed format).
- Dependency acquisition (`db: Session = Depends(get_db)`).
- Converting immutable application result objects from the Manager into Pydantic HTTP response models (`schemas.DashboardSummaryResponse`).

**Must NOT contain:**
- SQLAlchemy query construction or execution.
- Duplicated Zero-Based Budgeting aggregation or calculation.
- Dashboard workflow sequencing or orchestration.

---

### 2.2. Dashboard Summary Manager ([`backend/managers/dashboard_summary_manager.py`](../../backend/managers/dashboard_summary_manager.py))
**Owns:**
- Determining the monthly interval `[start_date, end_date)` using the shared pure month-range helper.
- Invoking the existing `BudgetSummaryManager.get_budget_summary(db, budget_month)` application workflow.
- Retrieving active account records through Account ResourceAccess (`account_access.get_active_accounts(db)`).
- Retrieving the ten recent transactions for the month through Transaction ResourceAccess (`transaction_access.get_recent_transactions_for_month(db, start_date, end_date)`).
- Computing the scalar `total_balance` across active accounts.
- Mapping persistence ORM records into clean, immutable application result dataclasses.
- Composing and returning `DashboardSummaryResult`.

**Pragmatic Coupling Decision:**
- The Manager accepts `db: Session` as an intentional pragmatic coupling (as established in Session 1, because database engine substitution is not an identified volatility axis).
- This input coupling does **not** grant permission to leak ORM records through the Manager's public output contract.

---

### 2.3. ResourceAccess ([`backend/access/`](../../backend/access/))
**Owns:**
- SQLAlchemy queries, filtering, ordering, and eager loading.
- Isolating concrete persistence retrieval from business workflows.

**Approved Operations:**
```python
# backend/access/account_access.py
def get_active_accounts(
    db: Session,
) -> Sequence[models.Account]:
    """Retrieves all active accounts ordered by name ascending."""
    ...

# backend/access/transaction_access.py
def get_recent_transactions_for_month(
    db: Session,
    start_date: date,
    end_date: date,
) -> Sequence[models.Transaction]:
    """Retrieves the 10 most recent transactions within [start_date, end_date) with account loaded."""
    ...
```

**Boundary Rules:**
- Accessors return concrete persistence ORM records (`models.Account`, `models.Transaction`) to the Manager.
- Accessors must **not** import Manager-defined types or application result structures (preventing inverted dependencies).
- Accessors own relationship loading (e.g. `joinedload(models.Transaction.account)`) to ensure all necessary data is retrieved in a single round-trip without triggering lazy loading.

---

## 3. Manager Output Contract (Pure Application Dataclasses)

The Manager's output contract is strictly decoupled from both the database ORM models and presentation Pydantic schemas.

`DashboardSummaryResult` and its nested members are plain Python dataclasses (`frozen=True`) using standard library types (`UUID`, `Decimal`, `date`, `datetime`, `Optional`):

```python
@dataclass(frozen=True)
class DashboardAccountItem:
    account_id: UUID
    name: str
    type: str
    subtype: Optional[str]
    current_balance: Decimal
    available_balance: Optional[Decimal]
    currency: str
    balance_last_updated: Optional[datetime]
    is_active: bool


@dataclass(frozen=True)
class DashboardTransactionAccountItem:
    id: UUID
    name: str
    type: str
    subtype: Optional[str]
    current_balance: Optional[Decimal]
    available_balance: Optional[Decimal]
    starting_balance: Decimal
    currency: str
    balance_last_updated: Optional[datetime]
    is_active: bool
    plaid_account_id: Optional[str]
    item_id: Optional[UUID]


@dataclass(frozen=True)
class DashboardRecentTransactionItem:
    transaction_id: UUID
    account_id: UUID
    category_id: Optional[UUID]
    description: str
    amount: Decimal
    date: date
    datetime: Optional[datetime]
    pending: bool
    is_transfer: bool
    account: Optional[DashboardTransactionAccountItem] = None


@dataclass(frozen=True)
class DashboardSummaryResult:
    budget_summary: BudgetSummaryResult
    accounts: Sequence[DashboardAccountItem]
    total_balance: Decimal
    recent_transactions: Sequence[DashboardRecentTransactionItem]
```

### Boundary Rule:
These application result structures must contain **no**:
- SQLAlchemy ORM models (`models.Account`, `models.Transaction`);
- Pydantic models (`schemas.AccountRead`, `schemas.TransactionRead`);
- FastAPI or HTTP-specific objects.

The presentation Router is responsible for converting these application values into the existing Pydantic response models.

---

## 4. Shared Pure Month-Range Helper

### Location: [`backend/domain/dates.py`](../../backend/domain/dates.py)

Month-to-interval conversion (`date -> [start_date, end_date)`) has demonstrated observed reuse across three distinct workflows:
1. Budget Summary ([`budget_summary_manager.determine_month_range`](../../backend/managers/budget_summary_manager.py#L28))
2. Dashboard Summary ([`routers/summaries.py:get_month_range`](../../backend/routers/summaries.py#L25))
3. Credit Cards ([`routers/credit_cards.py:get_month_range`](../../backend/routers/credit_cards.py#L22))

Because this is a pure calendar calculation rather than workflow sequencing, it belongs in a shared domain utility:

```python
"""Pure domain functions for date interval and period calculations."""
from datetime import date


def determine_month_range(month_date: date) -> tuple[date, date]:
    """
    Returns the half-open interval [start_date, end_date) for a given month date.
    """
    start_date = date(month_date.year, month_date.month, 1)
    if start_date.month == 12:
        end_date = date(start_date.year + 1, 1, 1)
    else:
        end_date = date(start_date.year, start_date.month + 1, 1)
    return start_date, end_date
```

**Guardrails:**
- It is **not an Engine** (it has no financial rules or heuristic volatility).
- It must **not** be wrapped into a `DateService`, `CalendarEngine`, or `TimeManager`.

### Caller Search & Public API Cleanup:
A search across the codebase for `determine_month_range` revealed:
- Production callers: **0** callers outside of `budget_summary_manager.py` itself.
- Test callers: Only `tests/test_manager_budget_summary.py` directly unit-tests the function.

**Decision:**
Because no production caller depends on `determine_month_range` living in `budget_summary_manager.py`, we do **not** preserve a compatibility re-export in the Manager. Tests testing month-range calculation will import it directly from `backend.domain.dates`. Tests must not dictate an artificial public API on a Manager.

---

## 5. Dashboard Recent-Transaction Rule (`10` Limit)

**Requirement:** The Dashboard returns the ten most recent transactions within the selected month.

**Design Rule:**
- The value `10` is an internal constant (`DASHBOARD_RECENT_TRANSACTIONS_LIMIT = 10`) encapsulated inside the Accessor query.
- It is **not** exposed as a public configurable parameter (`limit: int = 10`) on the Accessor function signature.
- No generic pagination abstractions or speculative limit parameters are introduced.

---

## 6. Explicitly Rejected Abstractions

To prevent overengineering and functional decomposition masquerading as VBD, this slice deliberately rejects:

1. **`DashboardEngine`:** Summing active account balances is simple data aggregation, not an independently volatile business algorithm. The existing `Budget Engine` is reused via `BudgetSummaryManager`.
2. **`IDashboardSummaryManager`:** No substitutability requirement exists.
3. **Generic Repositories (`IRepository<T>`):** The application relies on concrete, focused functions in `account_access.py` and `transaction_access.py`.
4. **Accessor Interfaces:** A single PostgreSQL relational store is used.
5. **Dependency Injection Containers / Command Buses:** Direct function composition (`DashboardSummaryManager` calling `BudgetSummaryManager`) is concrete and standard.
6. **Generic Widget / Dashboard Plugin Framework:** The dashboard consists of fixed cards and feeds; dynamic plugin architectures are speculative.
7. **One DTO Type Per Layer:** Clean separation is maintained by having Accessors return ORM models to the Manager, the Manager return focused application dataclasses, and the Router map to Pydantic responses.
8. **Configurable Recent-Transaction Limits:** The requirement is fixed at 10.
9. **Frontend Redesign:** Visual and UI changes are deferred until backend boundaries are stabilized.

---

## 7. Preserved Invariants & Known Exclusions

The following known defects and unresolved domain decisions remain explicitly excluded from this refactoring slice:
- **`Transaction.description` Nullability Defect:** Database allows `None`; schema expects `str`. Preserved without silent modification.
- **Category Group Cascade-Delete Defect:** Backend permits cascading group deletion. Preserved as characterized.
- **Credit-Card Transfer Semantics:** Preserved as characterized in the credit-card module.
- **Future-Dated Credit-Card Balance Semantics:** Preserved as characterized.
- **Greedy Transfer-Matching Behavior:** Preserved as characterized.
- **Plaid Token Encryption Migration:** Stored as base64 placeholder; real encryption migration is tracked separately as a security task.

---

## 8. Implementation Acceptance Invariant

> **Implementation Invariant:**
> The refactor must preserve the existing Dashboard API response JSON, ordering, values, monthly scope, account-balance behavior, and recent-transaction behavior, as protected by characterization tests.
