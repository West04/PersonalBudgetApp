# Transfer Candidate Search Architecture Specification (Slice 4)

## 1. Overview & Conceptual Architecture

The Transfer Candidate Search workflow (`GET /credit-cards/transfer-candidates`) identifies opposing transactions across different accounts that likely represent inter-account transfers (credit card payments, checking-to-savings transfers, etc.).

Rather than executing raw database queries, orchestrating domain input conversion, invoking matching heuristics, and performing lazy relationship enrichment inside the FastAPI router, the Transfer Candidate Search workflow is decomposed using Volatility-Based Decomposition (VBD):

```text
FastAPI Credit Card Router (backend/routers/credit_cards.py)
          ↓
Transfer Reconciliation Manager (backend/managers/transfer_reconciliation_manager.py)
     ├── Transaction ResourceAccess (backend/access/transaction_access.py) ──→ PostgreSQL
     └── Existing Reconciliation Engine (backend/domain/reconciliation.py)
```

### Key Architectural Boundaries:
1. **PostgreSQL is reached only through Transaction ResourceAccess.**
2. **Transaction ResourceAccess owns candidate queries and lazy relationship resolution.** When account metadata is needed for a matched transaction, Transaction ResourceAccess resolves the relationship via `get_account_for_transaction(transaction)`.
3. **Account ResourceAccess is NOT a direct dependency of this workflow.**
4. **The pure Reconciliation Engine remains authoritative for pair matching.** It is reused without modification.

---

## 2. Manager Justification

The `TransferReconciliationManager` is justified strictly by an **observed multi-step business workflow**:

```text
get unmatched inflows (Transaction ResourceAccess)
        ↓
get unmatched outflows (Transaction ResourceAccess)
        ↓
map ORM transaction scalar fields -> ReconciliationTransaction
        ↓
invoke existing Reconciliation Engine (detect_transfer_candidates)
        ↓
correlate matched IDs back to Transaction ORM records
        ↓
for matched transactions only:
    Transaction ResourceAccess resolves transaction.account (get_account_for_transaction)
        ↓
map Account ORM records -> immutable application values
        ↓
return Sequence[TransferCandidateItem]
```

### Rationale:
- This workflow coordinates multiple distinct concerns: persistence query execution, domain input translation, pure heuristic evaluation, ID-based correlation, and relationship traversal.
- The use case ("find transfer candidates") changes independently from HTTP presentation (FastAPI, query handling, Pydantic schemas) and from the matching heuristic itself (the pure Engine).
- A Manager is justified because of this meaningful orchestration sequence, **not** because "every endpoint needs a Manager."

---

## 3. Presentation / Router Responsibility

File: [`backend/routers/credit_cards.py`](../../backend/routers/credit_cards.py)

### Router Owns:
- FastAPI endpoint registration: `@router.get("/transfer-candidates", response_model=List[schemas.TransferCandidate])`.
- Dependency injection of the database session: `db: Session = Depends(get_db)`.
- Invoking the Manager: `transfer_reconciliation_manager.get_transfer_candidates(db)`.
- Mapping immutable application result items into Pydantic HTTP response models:
  - [`schemas.TransferCandidate`](../../backend/schemas.py);
  - [`schemas.CreditCardTransactionRead`](../../backend/schemas.py);
  - [`schemas.TransactionRead`](../../backend/schemas.py);
  - nested [`schemas.AccountRead`](../../backend/schemas.py).
- HTTP response serialization (HTTP 200 OK).

### Router Must NOT Retain:
- SQLAlchemy candidate queries or filtering.
- In-memory transaction ID indexing or correlation.
- `ReconciliationTransaction` construction.
- Direct invocation of the Reconciliation Engine.
- Pair matching or tie-breaking logic.

---

## 4. ResourceAccess Responsibility

File: [`backend/access/transaction_access.py`](../../backend/access/transaction_access.py)

ResourceAccess owns concrete persistence queries for retrieving candidate transactions.

### Approved Operations:

```python
def get_unmatched_inflow_transactions(
    db: Session,
) -> Sequence[models.Transaction]:
    """
    Retrieves all unmatched negative transactions (amount < 0, is_transfer == False)
    across all accounts, preserving current query shape and introducing no explicit ordering.
    """


def get_unmatched_outflow_transactions(
    db: Session,
) -> Sequence[models.Transaction]:
    """
    Retrieves all unmatched positive transactions (amount > 0, is_transfer == False)
    across all accounts, preserving current query shape and introducing no explicit ordering.
    """


def get_account_for_transaction(
    transaction: models.Transaction,
) -> Optional[models.Account]:
    """
    Resolves the Account relationship associated with a Transaction.

    Accessing transaction.account may trigger SQLAlchemy lazy loading.
    Relationship loading remains a concrete persistence concern owned by
    Transaction ResourceAccess.
    """
    return transaction.account
```

### Inflow Query Semantics:
```python
db.query(models.Transaction)
.join(models.Account, models.Account.id == models.Transaction.account_id)
.filter(
    models.Transaction.amount < 0,
    models.Transaction.is_transfer == False,
)
.all()
```

### Outflow Query Semantics:
```python
db.query(models.Transaction)
.join(models.Account, models.Account.id == models.Transaction.account_id)
.filter(
    models.Transaction.amount > 0,
    models.Transaction.is_transfer == False,
)
.all()
```

### Critical Ordering Rule:
Both queries have **NO `ORDER BY` clause**.
PostgreSQL row order is therefore **unspecified**.
- The Accessor preserves the existing query shape and introduces no explicit ordering.
- The Accessor does **not** guarantee "storage order," "insertion order," or "chronological order."
- The Manager and Engine must consume the returned sequence without sorting it.

### Account Join Preservation:
The existing `join(models.Account, ...)` is retained during this structural slice to avoid intentionally changing the current SQLAlchemy query shape in an order-sensitive workflow. Retaining this join does not guarantee an identical PostgreSQL query execution plan or row order, but avoids speculative query rewrites during structural refactoring.

### Account Relationship Resolution:
- `transaction.account` is not merely an in-memory attribute; in SQLAlchemy it performs resource access by issuing a lazy SQL query if the relationship is not already cached in the Session identity map.
- Placing this traversal behind `transaction_access.get_account_for_transaction(transaction)` keeps storage-triggering behavior strictly inside Transaction ResourceAccess while preserving existing lazy-loading persistence execution.
- No `Session` argument is added because SQLAlchemy ORM models attached to an active Session resolve relationships via internal session binding.
- Account ResourceAccess is not introduced; Account is not queried independently.
- No `joinedload`, `selectinload`, or `contains_eager` is introduced.

---

## 5. Candidate-Set Selection vs. Pair Matching

The workflow explicitly separates candidate scoping from pair matching:

| Responsibility | Owning Component | Logic & Invariants |
|---|---|---|
| **Candidate-Set Selection** | **Transaction ResourceAccess** | Selects candidate persistence records from PostgreSQL:<br/>• Inflows: `amount < 0 AND is_transfer == False`<br/>• Outflows: `amount > 0 AND is_transfer == False` |
| **Pair Matching** | **Reconciliation Engine** | Authoritative matching algorithm:<br/>• Equal absolute amounts: `\|inflow.amount\| == \|outflow.amount\|`<br/>• Opposite signs: `inflow.amount < 0`, `outflow.amount > 0`<br/>• Different accounts: `inflow.account_id != outflow.account_id`<br/>• Date proximity: `\|outflow.date - inflow.date\| <= 2` days<br/>• Greedy first eligible match per inflow<br/>• Single-use outflows: matched outflows cannot be reused |

Pairing rules must not be moved into SQL or the Manager; candidate scoping rules remain in ResourceAccess.

---

## 6. Existing Reconciliation Engine Remains Authoritative

File: [`backend/domain/reconciliation.py`](../../backend/domain/reconciliation.py)

The pure domain Engine and its data structures remain completely unchanged:

```python
@dataclass(frozen=True)
class ReconciliationTransaction:
    transaction_id: UUID
    account_id: UUID
    amount: Decimal
    date: date
    is_transfer: bool = False


@dataclass(frozen=True)
class MatchedTransferCandidate:
    inflow: ReconciliationTransaction
    outflow: ReconciliationTransaction


def detect_transfer_candidates(
    inflows: Sequence[ReconciliationTransaction],
    outflows: Sequence[ReconciliationTransaction],
) -> list[MatchedTransferCandidate]:
```

### Engine Invariants:
- Pure Python calculation with zero dependencies on SQLAlchemy, Sessions, FastAPI, or Pydantic.
- No `payload: Any` field (infrastructure leakage previously removed).
- No configurable `max_days_difference` argument (internal named constant `MAX_TRANSFER_DAYS_DIFFERENCE = 2`).
- Do not create another Engine, strategy/scoring interfaces, closest-date policies, or configurable tolerances.

---

## 7. Ordering as an Implementation Invariant

Because the Reconciliation Engine's matching heuristic is greedy and input-order dependent, the ordering sequence is an implementation invariant:

```text
Database returns an unspecified row sequence (no SQL ORDER BY)
        ↓
Accessor returns sequence unchanged (no sorting)
        ↓
Manager maps to domain inputs in the same sequence
        ↓
Engine consumes sequence unchanged
        ↓
Greedy matching result depends on that sequence
```

### Non-Negotiable Structural Invariants:
- **No SQL `ORDER BY`** in candidate queries.
- **No Python sorting** in Accessors, Manager, or Router (Engine owns matching policy).
- Matching policy is owned strictly by the pure Reconciliation Engine (`backend/domain/reconciliation.py`).

Transfer candidate matching is deterministic closest-first greedy matching:
- **Eligibility**: exact opposite amount, different accounts, $\pm 2$ calendar days, not already transfer, no splits.
- **Selection**: smallest date distance first (`0` > `1` > `2`); stable dates and transaction IDs break ties; each transaction appears in at most one suggestion.
- **Order-invariance**: Input and database ordering do not affect results.
- **Suggestion-only**: Matching is suggestion-only until explicit user confirmation via `POST /credit-cards/mark-transfers`.

---

## 8. Lazy Account Loading is Intentionally Preserved

The current implementation issues lazy Account SELECT queries when relationship data is traversed.
Under the revised architecture:
- Direct relationship traversal from the Manager is eliminated.
- The Manager delegates account resolution to `transaction_access.get_account_for_transaction(txn)` only for matched transactions where account metadata is required.
- Accessing `get_account_for_transaction(txn)` triggers the lazy Account SELECT if the `Account` instance is not already cached in SQLAlchemy's Session identity map.
- Eager loading is not introduced; accounts are resolved on-demand only for matched pairs.
- Do not introduce `joinedload`, `selectinload`, `contains_eager`, bulk account retrieval, or an Account ResourceAccess dependency for this workflow.
- Execution query shape remains approximately:
  ```text
  2 base Transaction queries
  +
  lazy Account SELECTs for matched transactions as account relationships are resolved via Transaction ResourceAccess
  ```
- The exact number of lazy Account queries varies because SQLAlchemy's Session identity map reuses already-loaded `Account` instances when multiple matched transactions belong to the same account.
- Eager loading remains a **possible future implementation optimization**, not an architectural volatility driver.

---

## 9. Manager Contract

File: `backend/managers/transfer_reconciliation_manager.py`

### Function Signature:
```python
def get_transfer_candidates(
    db: Session,
) -> Sequence[TransferCandidateItem]:
    """
    Coordinates the transfer candidate search workflow:
    1. Retrieves unmatched inflows via Transaction ResourceAccess.
    2. Retrieves unmatched outflows via Transaction ResourceAccess.
    3. Maps scalar transaction records to ReconciliationTransaction domain models, preserving query order.
    4. Invokes the pure Reconciliation Engine (detect_transfer_candidates).
    5. Correlates matched candidate IDs back to persistence records.
    6. For matched transactions only, resolves accounts via Transaction ResourceAccess (get_account_for_transaction).
    7. Maps Account ORM records to immutable application values.
    8. Constructs and returns immutable Sequence[TransferCandidateItem].
    """
```

### Architectural Contract:
- **No Result Wrapper:** There is deliberately no top-level result wrapper (`TransferCandidatesResult`) because the HTTP endpoint returns a flat `List[schemas.TransferCandidate]` with no metadata.
- **Pragmatic Coupling:** The Manager accepts `db: Session` as application context under the established pragmatic coupling decision (Session 1 & Checkpoint 1).
- **ORM Handling Rules:**
  - The Manager receives ORM records from ResourceAccess.
  - The Manager reads already-materialized scalar ORM fields needed for mapping (`transaction_id`, `account_id`, `amount`, `date`, `is_transfer`, `description`, `category_id`, `plaid_transaction_id`, `datetime`, `pending`).
  - The Manager must **NOT** directly traverse relationships that may issue database I/O.
  - For matched transactions, the Manager delegates account resolution to `transaction_access.get_account_for_transaction(txn)`.
- **No Leaks:** The Manager must not expose ORM models, Pydantic schemas, FastAPI objects, or HTTP concepts.

---

## 10. Approved Application Result Structures

The Manager's output contract uses minimal, immutable dataclasses:

```python
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID


@dataclass(frozen=True)
class TransferInflowSideItem:
    transaction_id: UUID
    description: str
    amount: Decimal
    date: date
    is_transfer: bool
    category_id: Optional[UUID] = None


@dataclass(frozen=True)
class TransferOutflowAccountItem:
    id: UUID
    name: str
    type: str
    subtype: Optional[str]
    current_balance: Decimal
    available_balance: Optional[Decimal]
    starting_balance: Decimal
    currency: str
    balance_last_updated: Optional[datetime]
    is_active: bool
    mask: Optional[str] = None
    plaid_account_id: Optional[str] = None
    item_id: Optional[UUID] = None


@dataclass(frozen=True)
class TransferOutflowSideItem:
    transaction_id: UUID
    account_id: UUID
    description: str
    amount: Decimal
    date: date
    is_transfer: bool
    category_id: Optional[UUID] = None
    plaid_transaction_id: Optional[str] = None
    datetime: Optional[datetime] = None
    pending: bool = False
    account: Optional[TransferOutflowAccountItem] = None


@dataclass(frozen=True)
class TransferCandidateItem:
    inflow_side: TransferInflowSideItem
    inflow_account_name: str
    outflow_side: TransferOutflowSideItem
    outflow_account_name: str
```

---

## 11. Presentation-Only Pydantic Defaults

### Finding: `Account.status`
- The SQLAlchemy ORM model `models.Account` **does not have a `status` column**.
- The value `status = "connected"` in the HTTP response originates **exclusively** from the Pydantic schema default in [`schemas.AccountRead`](../../backend/schemas.py):
  ```python
  class AccountRead(BaseModel):
      ...
      status: str = "connected"
  ```

### Boundary Rule:
- `TransferOutflowAccountItem` does **not** contain a `status` field.
- The default value remains strictly in the Presentation / Pydantic schema layer.
- No synthetic `"connected"` value is injected into the Manager.

---

## 12. Exact Response Asymmetry

The existing public HTTP contract is intentionally asymmetric between the inflow and outflow sides:

### Inflow Side (`schemas.CreditCardTransactionRead`):
- `transaction_id`: `UUID`
- `description`: `str`
- `amount`: `Decimal`
- `date`: `date`
- `is_transfer`: `bool`
- `category_id`: `Optional[UUID]`
*(No `account_id`, `account`, `pending`, `datetime`, or `plaid_transaction_id`)*

### Outflow Side (`schemas.TransactionRead`):
- `transaction_id`: `UUID`
- `plaid_transaction_id`: `Optional[str]`
- `account_id`: `UUID`
- `category_id`: `Optional[UUID]`
- `description`: `str`
- `amount`: `Decimal`
- `date`: `date`
- `datetime`: `Optional[datetime]`
- `pending`: `bool`
- `is_transfer`: `bool`
- `account`: `Optional[schemas.AccountRead]` *(fully populated nested account object)*

### Top-Level Fields:
- `inflow_account_name`: `str`
- `outflow_account_name`: `str`

The structural refactor must preserve this exact public contract without attempting to normalize or redesign the response shape.

---

## 13. Preserved Defects and Unresolved Behaviors

The following domain and implementation characteristics are preserved or resolved:
1. **Unspecified query ordering:** No `ORDER BY` in candidate persistence queries; Engine owns deterministic ranking.
2. **Deterministic closest-first greedy matching:** Engine ranks eligible pairs by date distance, dates, and IDs; closest date strictly wins. (Resolved Checkpoint #7).
3. **2-day matching threshold:** Fixed constant `MAX_TRANSFER_DAYS_DIFFERENCE = 2`.
4. **Single-use pairing:** Inflows and outflows are claimed at most once.
5. **Transaction description nullability:** Resolved defect (database enforces NOT NULL, schema requires non-null string).
6. **Category-group deletion behavior:** Resolved defect (deleting a non-empty category group is rejected with HTTP 400).

---

## 14. Transfer Confirmation Remains Separate

The mutation endpoint:
```text
POST /credit-cards/mark-transfers
```
is **not** part of `TransferReconciliationManager`.

### Rationale:
- It is a simple atomic boolean mutation (`Transaction.is_transfer = True`).
- It has no workflow sequencing or algorithmic volatility.
- It remains classified as:
  ```text
  Router -> Accessor
  ```
- Candidate search and transfer confirmation must **not** be unified into a generic reconciliation service.

---

## 15. Explicitly Rejected Abstractions

The following abstractions have been evaluated and rejected as overengineering:
- `ITransferReconciliationManager` (no alternate manager implementations).
- `RelationshipLoader`, `ORMResolver`, or separate `AccountService`.
- Generic Transaction repository (`IRepository<Transaction>`).
- Generic Candidate repository (`ICandidateRepository`).
- Generic `ReconciliationService` (combining search, confirmation, and import).
- Strategy / scoring interfaces for candidate pairing.
- Configurable date tolerance (`max_days_difference`).
- DTO-per-layer hierarchies.
- Unit of Work pattern.
- Dependency injection container.
- Eager-loading optimization during this structural slice.
- Query ordering or tie-breaking fixes during this structural slice.

---

## 16. Characterization Safety Baseline

The characterization safety net in [`tests/test_characterization_transfers.py`](../../tests/test_characterization_transfers.py) protects:
- Empty database behavior (HTTP 200 + `[]`).
- Non-qualifying transactions (> 2 days, same account, already marked transfers).
- Solitary unmatched transaction isolation (unmatched inflows and outflows excluded).
- Full response contract (all inflow and outflow fields, nested `account`, Pydantic defaults).
- Account enrichment names matching respective transactions.
- Category UUID and None pass-through.
- Verbatim description pass-through on both sides.
- One-to-one matching when multiple transactions qualify without assuming a specific DB-order winner.

### Characterization Test Suite Baseline:
```text
76 passed
```
All 76 tests must remain green before and after the structural refactor of Slice 4.

---

## 17. Implementation & Verification Summary

- **Implementation Date:** 2026-09-24
- **Status:** Implemented & Verified
- **Test Suite Results:** 84 passed (76 existing characterization baseline + 3 new access tests + 5 new manager tests)
- **Delivered Components:**
  - ResourceAccess: `get_unmatched_inflow_transactions`, `get_unmatched_outflow_transactions`, and `get_account_for_transaction` added to [`backend/access/transaction_access.py`](../../backend/access/transaction_access.py).
  - Domain Engine: Pure [`detect_transfer_candidates`](../../backend/domain/reconciliation.py) preserved unchanged.
  - Workflow Manager: [`backend/managers/transfer_reconciliation_manager.py`](../../backend/managers/transfer_reconciliation_manager.py) introduced with immutable items (`TransferInflowSideItem`, `TransferOutflowAccountItem`, `TransferOutflowSideItem`, `TransferCandidateItem`) returning `Sequence[TransferCandidateItem]`.
  - Presentation / Router: [`backend/routers/credit_cards.py`](../../backend/routers/credit_cards.py) simplified to delegate candidate retrieval to Manager and map to `schemas.TransferCandidate`.
  - Focused Tests: [`tests/test_access_transfers.py`](../../tests/test_access_transfers.py) and [`tests/test_manager_transfer_reconciliation.py`](../../tests/test_manager_transfer_reconciliation.py).
- **Invariants Verified:**
  - No `ORDER BY` or Python sorting introduced.
  - Lazy relationship loading preserved strictly inside Transaction ResourceAccess (`get_account_for_transaction` called only for matched transactions).
  - Pure Reconciliation Engine untouched.
  - Public HTTP API response contract and asymmetry preserved verbatim.

