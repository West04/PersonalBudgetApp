# Plaid Account Sync Architecture Specification (Slice 6)
## Status: Slice 6 Implemented & Verified

---

## 1. Overview & Conceptual Architecture

The Plaid Account Sync workflow (`POST /plaid/sync_accounts`) synchronizes account balances and metadata from the external Plaid REST API for a single specified `PlaidItem`, reconciles them against existing local `Account` records in PostgreSQL, and commits the updates.

Under Volatility-Based Decomposition (VBD), this workflow decomposes into:

```text
FastAPI Plaid Router (backend/routers/plaid.py)
        ↓
PlaidAccountSyncManager (backend/managers/plaid_account_sync_manager.py)
        ├── PlaidItem ResourceAccess (backend/access/plaid_item_access.py) ─────→ PostgreSQL
        ├── Account ResourceAccess (backend/access/account_access.py) ───────────→ PostgreSQL
        ├── Existing token security helper (backend/security.py)
        └── Plaid External ResourceAccess (backend/access/plaid_access.py) ──────→ Plaid API
```

### Key Architectural Boundaries:
1. **No Engine:** Account synchronization contains no independently volatile financial formulas, heuristics, or scoring algorithms. Creating an engine for external-to-relational field mapping is explicitly rejected.
2. **Dedicated Workflow Manager:** `PlaidAccountSyncManager` coordinates the multi-step sequence across credential decoding, external network I/O, relational account upserting, and transaction lifecycle.
3. **No Monolithic Sync Manager:** Account Sync (`/plaid/sync_accounts`) and Transaction Sync (`/plaid/sync_transactions`) are fundamentally different operational pipelines (stateless balance refresh vs. stateful cursor pagination). They are deliberately separate vertical slices and must not be combined into a generic `PlaidSyncManager`. Plaid Transaction Sync remains **Planned / Not Yet Analyzed for Refactor**.
4. **Isolated External ResourceAccess:** Plaid SDK classes, request/response models, and `ApiException` details are completely encapsulated in `backend/access/plaid_access.py`.
5. **Decoupled Persistence Accessors:** `backend/access/account_access.py` does not import external Plaid snapshot types. The Manager mediates between external snapshots and persistence functions.
6. **Explicit Transaction Lifecycle:** The Manager explicitly coordinates `db.flush()` and `db.commit()`.

---

## 2. Workflow Manager Justification

The `PlaidAccountSyncManager` is justified strictly by an **observed multi-step business workflow**:

```text
validate identifier presence (item_id or plaid_item_id)
        ↓
resolve PlaidItem from persistence using item_id precedence
        ↓
decode stored access token via existing security helper
        ↓
fetch current accounts from Plaid external ResourceAccess
        ↓
for each remote account:
    stage/create/update local Account record via Account ResourceAccess
        ↓
explicit db.flush()
        ↓
single db.commit()
        ↓
return PlaidAccountSyncResult(accounts_updated=N)
```

### Rationale:
- Coordinates four distinct boundaries: relational persistence for `PlaidItem`, relational persistence for `Account`, credential decoding, and external Plaid REST API communication.
- Owns validation precedence, error mapping, and transaction boundary timing (`flush` $\rightarrow$ `commit`).
- The use case ("refresh balances for a linked institution") changes independently from HTTP presentation and external SDK versions.

---

## 3. Presentation / Router Responsibilities

File: [`backend/routers/plaid.py`](../../backend/routers/plaid.py)

### Router Owns:
- FastAPI route registration: `@router.post("/sync_accounts", response_model=Dict[str, Any])`.
- Request body deserialization into [`schemas.PlaidSyncRequest`](../../backend/schemas.py).
- Acquiring database session via dependency injection: `db: Session = Depends(get_db)`.
- Invoking the Manager: `plaid_account_sync_manager.sync_plaid_accounts(db, item_id=payload.item_id, plaid_item_id=payload.plaid_item_id)`.
- Catching framework-free application exceptions and translating them to HTTP responses:
  - `PlaidAccountSyncMissingIdentifierError` $\rightarrow$ `HTTPException(400, detail="Must provide item_id or plaid_item_id")`
  - `PlaidAccountSyncItemNotFoundError` $\rightarrow$ `HTTPException(404, detail="Plaid Item not found")`
  - `PlaidAccountSyncDecryptionError` $\rightarrow$ `HTTPException(500, detail="Error decrypting access token")`
  - `PlaidAccountSyncExternalApiError` $\rightarrow$ `HTTPException(status_code=exc.status_code, detail=exc.detail)`
  - Unexpected errors $\rightarrow$ `HTTPException(500, detail=str(exc))`
- Serializing `PlaidAccountSyncResult` to the existing JSON response contract:
  ```json
  {
    "status": "ok",
    "accounts_updated": 3
  }
  ```

### Router Must NOT Retain:
- PlaidItem database queries (`db.query(models.PlaidItem)`).
- Direct Account queries or staging.
- Direct invocation of Plaid SDK clients or requests (`AccountsGetRequest`, `client.accounts_get`).
- Token decryption logic (`decrypt_token`).
- Account mutation loops.
- `db.flush()` or `db.commit()` workflow orchestration.

---

## 4. Request Precedence & Identifier Validation

Schema:
```python
class PlaidSyncRequest(BaseModel):
    plaid_item_id: Optional[str] = None
    item_id: Optional[UUID] = None
```

### Validation Precedence Rules:
1. **Missing Identifiers:** If neither `item_id` nor `plaid_item_id` is supplied:
   ```text
   raise PlaidAccountSyncMissingIdentifierError("Must provide item_id or plaid_item_id")
   → HTTP 400
   ```
2. **`item_id` Precedence:** If both `item_id` and `plaid_item_id` are provided, `item_id` takes precedence. The Manager resolves the `PlaidItem` strictly by `item_id`.
3. **Item Not Found:** If the chosen identifier does not match any record in PostgreSQL:
   ```text
   raise PlaidAccountSyncItemNotFoundError("Plaid Item not found")
   → HTTP 404
   ```

---

## 5. PlaidItem ResourceAccess

File: `backend/access/plaid_item_access.py`

Focused persistence module for PostgreSQL `models.PlaidItem` queries:

```python
def get_plaid_item_by_id(
    db: Session,
    item_id: UUID,
) -> Optional[models.PlaidItem]:
    """Retrieves a PlaidItem by its primary key UUID."""
    return db.query(models.PlaidItem).filter(models.PlaidItem.id == item_id).first()


def get_plaid_item_by_plaid_item_id(
    db: Session,
    plaid_item_id: str,
) -> Optional[models.PlaidItem]:
    """Retrieves a PlaidItem by its unique Plaid item ID string."""
    return db.query(models.PlaidItem).filter(models.PlaidItem.plaid_item_id == plaid_item_id).first()
```

### Invariants:
- Exact primary-key or alternate-key lookup only.
- No hidden status filtering or automatic fallback selection.
- Generic repository patterns (`IRepository`, `find_plaid_item(filters)`) are rejected.

---

## 6. Transitional Legacy-Helper Rule

Existing Plaid database helpers in [`backend/crud/plaid.py`](../../backend/crud/plaid.py) (e.g. `sync_accounts_and_balances`, `list_accounts_by_item`, `create_plaid_item`) are currently shared with:
- Public token exchange (`POST /plaid/exchange_public_token`)
- Transaction synchronization (`POST /plaid/sync_transactions`)

Under VBD:
- Slice 6 refactors only `POST /plaid/sync_accounts`.
- The new `PlaidAccountSyncManager` uses the new focused Accessors (`plaid_item_access.py`, `account_access.py`, `plaid_access.py`).
- Legacy helpers in `crud/plaid.py` will remain intact so unmigrated workflows continue to function without disruption.
- Legacy helpers will be retired in subsequent vertical slices when their respective workflows are modernized.

---

## 7. Token Security & Credential Boundary

File: [`backend/security.py`](../../backend/security.py)

### Invariants:
- The existing Base64 placeholder implementation in `backend/security.py:decrypt_token` remains **unchanged**.
- Slice 6 does **not**:
  - introduce cryptography libraries (e.g. `cryptography.fernet`);
  - migrate existing database tokens;
  - rotate credentials;
  - redesign `PlaidItem` storage.
- Real token encryption is a planned security migration that will occur in a dedicated, isolated slice.

### Malformed-Token Behavior (Characterized Invariant):
`decrypt_token` catches decode exceptions internally and returns `""` (empty string).
- In the characterized application:
  ```text
  malformed token in database
          ↓
  decrypt_token returns ""
          ↓
  Manager calls PlaidAccess with access_token=""
          ↓
  Plaid API returns ApiException (e.g. HTTP 400 INVALID_ACCESS_TOKEN)
          ↓
  Plaid HTTP status and body reach the client
  ```
- **Constraint:** The Manager must **not** add validation like `if not access_token: raise ...`. It must pass the decoded string directly to the external Accessor.

### Escaping Decrypt-Exception Behavior:
If `decrypt_token` raises an unexpected exception outward:
```text
escaping decrypt exception
        ↓
Manager raises PlaidAccountSyncDecryptionError("Error decrypting access token")
        ↓
Router returns HTTP 500 (detail="Error decrypting access token")
        ↓
Plaid API is not called
```

---

## 8. Plaid External ResourceAccess

File: `backend/access/plaid_access.py`

This boundary encapsulates all Plaid SDK protocol interactions:

```python
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class PlaidAccountSnapshot:
    account_id: str
    name: Optional[str]
    mask: Optional[str]
    account_type: Optional[str]
    subtype: Optional[str]
    current_balance: Decimal
    available_balance: Optional[Decimal]
    currency: str


class PlaidAccessError(Exception):
    """Raised when external Plaid API communication fails."""
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def fetch_accounts_for_token(access_token: str) -> Sequence[PlaidAccountSnapshot]:
    """
    Calls Plaid /accounts/get using the provided access token.
    Translates raw SDK accounts into immutable PlaidAccountSnapshot objects.
    Translates ApiException and network errors into PlaidAccessError.
    """
```

### Invariants:
1. **SDK Encapsulation:** Owns `AccountsGetRequest`, `client.accounts_get`, Plaid configuration, and response parsing.
2. **Exception Translation:**
   - Plaid `ApiException`: Maps to `PlaidAccessError(status_code=e.status, detail=e.body)`. `e.body` is preserved as the raw string (nested JSON is not parsed).
   - Other exceptions: Maps to `PlaidAccessError(status_code=500, detail=str(exc))`.
3. **No Reverse Dependencies:** `plaid_access.py` does not import Manager exceptions or database models.
4. **No Balance Sign Inversion:** Plaid balance amounts are preserved as-is. Positive checking balances remain positive; positive credit card balances remain positive liabilities.
5. **No Currency Conversion:** `iso_currency_code` is passed through (defaulting to `"USD"` if missing). `unofficial_currency_code` is ignored.

---

## 9. Account ResourceAccess & Persistence Operations

File: [`backend/access/account_access.py`](../../backend/access/account_access.py)

To prevent coupling between persistence and external SDK models, `account_access.py` accepts explicit scalar parameters:

```python
def stage_or_update_plaid_account(
    db: Session,
    item_id: UUID,
    plaid_account_id: str,
    name: Optional[str],
    mask: Optional[str],
    account_type: Optional[str],
    subtype: Optional[str],
    current_balance: Decimal,
    available_balance: Optional[Decimal],
    currency: str,
    balance_last_updated: datetime,
) -> models.Account:
    """
    Locates an account by exact plaid_account_id:
    - If absent: stages a new models.Account record with is_active=True and ORM default starting_balance=0.00.
    - If present: updates mutable fields while preserving starting_balance, is_active, and item_id.
    Does not flush or commit.
    """
```

### Exact Identity & Matching Rule:
- Query matches strictly on:
  ```text
  models.Account.plaid_account_id == plaid_account_id
  ```
- **Not scoped by `item_id`:** If an account exists locally with the matching `plaid_account_id` but is associated with a different `item_id`, the existing account is updated in place, and its original `item_id` is preserved.

### New-Account Creation Semantics:
- `item_id = item_id`
- `plaid_account_id = plaid_account_id`
- `name = name or "Account"`
- `mask = mask`
- `type = account_type or "unknown"`
- `subtype = subtype`
- `is_active = True`
- `starting_balance`: Relies on ORM column default `default=0` (`Decimal("0.00")`). Not explicitly overridden.
- `current_balance = current_balance`
- `available_balance = available_balance`
- `currency = currency`
- `balance_last_updated = balance_last_updated`
- Staged via `db.add(db_account)`.

### Existing-Account Update Semantics & Fallback Asymmetry:
- **Mutable fields updated:** `name`, `mask`, `type`, `subtype`, `current_balance`, `available_balance`, `currency`, `balance_last_updated`.
- **Fallback asymmetries:**
  - Remote `name` falsy $\rightarrow$ **preserves** existing local `name`.
  - Remote `type` falsy $\rightarrow$ **preserves** existing local `type`.
  - Remote `mask` is `None` $\rightarrow$ **overwrites** local `mask` with `None`.
  - Remote `subtype` is `None` $\rightarrow$ **overwrites** local `subtype` with `None`.
  - Remote `available_balance` is `None` $\rightarrow$ **overwrites** local `available_balance` with `None`.
  - Missing currency $\rightarrow$ **falls back** to `"USD"`.
- Staged via `db.add(db_account)`.

### Fields Never Overwritten on Existing Accounts:
- `id` (Local primary key)
- `starting_balance` (Custom user baseline preserved)
- `is_active` (`is_active = False` remains `False`; no silent reactivation)
- `item_id` (Original PlaidItem association preserved)
- `plaid_account_id` (Identity key)

---

## 10. Timestamp & Reconciliation Semantics

1. **Per-Account Timestamps:** Each returned remote account receives a fresh `datetime.utcnow()` timestamp during its iteration/update. No request-wide synchronization timestamp policy is introduced.
2. **Missing Remote Accounts:** Local accounts belonging to the synced `item_id` that are omitted from Plaid's response are **completely untouched** (not deleted, not deactivated, balances not zeroed). Account sync operates strictly as an upsert over returned accounts.
3. **`accounts_updated` Meaning:** The returned count represents the total number of remote accounts processed from the Plaid response, regardless of whether local values were mutated or identical.

---

## 11. Transaction Lifecycle & Commit Ownership

1. **Flush Ownership:** The workflow executes an explicit `db.flush()` after staging all returned accounts.
   - If `db.flush()` fails (e.g. database constraint violation), it propagates as HTTP 500, and commit is not reached.
2. **Commit Ownership:** The Manager executes a single final `db.commit()` at the conclusion of the workflow.
   - If `db.commit()` fails, it propagates as HTTP 500, and PostgreSQL session teardown rolls back uncommitted changes.
3. **API-Before-Write Ordering:** The external Plaid API call precedes any database staging. If the external call fails, zero database modifications are staged or committed.

---

## 12. Framework-Free Application Error Contract

File: `backend/managers/plaid_account_sync_manager.py`

The Manager contains no FastAPI or Pydantic imports:

```python
class PlaidAccountSyncMissingIdentifierError(Exception):
    """Raised when neither item_id nor plaid_item_id is provided."""
    pass


class PlaidAccountSyncItemNotFoundError(Exception):
    """Raised when the requested PlaidItem does not exist in persistence."""
    pass


class PlaidAccountSyncDecryptionError(Exception):
    """Raised when token decryption raises an unexpected exception."""
    pass


class PlaidAccountSyncExternalApiError(Exception):
    """Raised when the external Plaid API call fails."""
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
```

---

## 13. Manager Contract & Result

File: `backend/managers/plaid_account_sync_manager.py`

```python
@dataclass(frozen=True)
class PlaidAccountSyncResult:
    accounts_updated: int


def sync_plaid_accounts(
    db: Session,
    item_id: Optional[UUID] = None,
    plaid_item_id: Optional[str] = None,
) -> PlaidAccountSyncResult:
    """
    Coordinates the Plaid account synchronization workflow:
    1. Validates presence of at least one identifier.
    2. Resolves PlaidItem using item_id precedence.
    3. Decrypts access token via security helper.
    4. Fetches account snapshots via Plaid External ResourceAccess.
    5. Iterates snapshots and stages/updates records via Account ResourceAccess.
    6. Flushes session via db.flush().
    7. Commits batch transaction via db.commit().
    8. Returns PlaidAccountSyncResult.
    """
```

---

## 14. Volatility Classification

### Observed Volatility (Justified Boundaries):
- **Plaid API Protocol:** External SDK objects, request headers, error models $\rightarrow$ [`backend/access/plaid_access.py`](../../backend/access/plaid_access.py).
- **Workflow Sequencing:** Use-case coordination across credentials, external API, persistence, and commit $\rightarrow$ [`backend/managers/plaid_account_sync_manager.py`](../../backend/managers/plaid_account_sync_manager.py).
- **PlaidItem Relational Storage:** PostgreSQL schema and queries for `plaid_items` $\rightarrow$ [`backend/access/plaid_item_access.py`](../../backend/access/plaid_item_access.py).
- **Account Relational Storage:** PostgreSQL schema, queries, and upsert for `accounts` $\rightarrow$ [`backend/access/account_access.py`](../../backend/access/account_access.py).
- **Credential Storage Utility:** Base64 placeholder decryption $\rightarrow$ [`backend/security.py`](../../backend/security.py).

### Speculative Volatility (Explicitly Rejected):
- Generic bank provider interfaces (`IBankProvider`, `PlaidProviderInterface`).
- Combined `PlaidSyncManager` merging account and transaction sync.
- Account reconciliation strategy interfaces.
- Automatic account deactivation policies for missing remote accounts.
- Background Celery/Redis job queues.
- Webhook ingestion framework.
- Multi-currency forex conversion engines.
- Generic Unit of Work or repository patterns.

---

## 15. Dependency Rules

### Allowed:
```text
Router -> PlaidAccountSyncManager
PlaidAccountSyncManager -> PlaidItem ResourceAccess
PlaidAccountSyncManager -> Account ResourceAccess
PlaidAccountSyncManager -> Plaid External ResourceAccess
PlaidAccountSyncManager -> security.decrypt_token
PlaidAccountSyncManager -> Session (application context)
ResourceAccess -> SQLAlchemy / PostgreSQL / Plaid SDK
```

### Prohibited:
```text
PlaidAccountSyncManager -> FastAPI
PlaidAccountSyncManager -> HTTPException
PlaidAccountSyncManager -> Plaid SDK classes (PlaidApi, AccountsGetRequest, ApiException)
Plaid External ResourceAccess -> PlaidAccountSyncManager errors
Account ResourceAccess -> PlaidAccountSnapshot
Account ResourceAccess -> Plaid SDK
```

---

## 16. Characterization Safety Baseline

Pre-refactoring safety baseline: **133 passed, 13 warnings in 3.15s** (100% green).
Protected by [`tests/test_characterization_plaid_accounts.py`](../../tests/test_characterization_plaid_accounts.py) across 20 distinct scenarios covering:
- Identifier validation errors (400) and `item_id` precedence;
- PlaidItem missing errors (404);
- Malformed token returning empty string to Plaid API;
- Escaping decryption exception producing HTTP 500;
- Plaid `ApiException` exact status code and raw body string propagation;
- Generic external exception producing HTTP 500 with `str(exc)`;
- Full new-account field persistence and fallbacks;
- No balance sign inversion;
- Existing-account updates and update fallback asymmetry;
- Invariant preservation (`starting_balance`, `is_active=False`, `item_id`, `id`);
- Identity matching by `plaid_account_id` without `item_id` scoping;
- Remote-missing accounts remaining untouched;
- `accounts_updated` counting semantics;
- API-before-write ordering;
- Explicit `flush()` and `commit()` failure propagation and rollback.
