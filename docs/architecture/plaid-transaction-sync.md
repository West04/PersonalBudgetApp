# Plaid Transaction Sync Architecture Specification (Slice 7)
## Status: Slice 7 Implemented & Verified

---

## 1. Overview & Conceptual Architecture

The Plaid Transaction Sync workflow (`POST /plaid/sync_transactions`) performs stateful ledger synchronization for a linked `PlaidItem`. It couples a pre-sync account balance refresh with a paginated transaction sync loop against Plaid's `/transactions/sync` endpoint, applying incoming transaction additions, modifications, and deletions to PostgreSQL, and persisting the updated cursor.

Under Volatility-Based Decomposition (VBD), this workflow decomposes into:

```text
FastAPI Plaid Router (backend/routers/plaid.py)
        ↓
PlaidTransactionSyncManager (backend/managers/plaid_transaction_sync_manager.py)
        ├── PlaidItem ResourceAccess (backend/access/plaid_item_access.py) ───────────────→ PostgreSQL
        ├── Existing token security helper (backend/security.py:decrypt_token)
        ├── Plaid Account External Access (backend/access/plaid_access.py) ────────────────→ Plaid /accounts/get
        ├── Account ResourceAccess (backend/access/account_access.py) ────────────────────→ PostgreSQL
        ├── Plaid Transaction External Access (backend/access/plaid_transaction_access.py) → raw HTTP /transactions/sync
        └── Transitional concrete persistence helper (backend/crud/transaction.py) ──────→ PostgreSQL
```

### Key Architectural Boundaries:
1. **No Engine Justified:** Transaction synchronization contains no independently volatile business rules, financial formulas, or scoring algorithms. Sign negation (`-amount`), event dispatching (`added`/`modified`/`removed`), and cursor progression are transport mappings and workflow control, not pure business policy.
2. **Dedicated Workflow Manager:** `PlaidTransactionSyncManager` coordinates the multi-step sequence across credential decoding, account balance refresh staging, cursor-based pagination, per-event transaction persistence, and final cursor commitment.
3. **No Monolithic Sync Manager:** Account Sync (`/plaid/sync_accounts`) and Transaction Sync (`/plaid/sync_transactions`) are fundamentally different operational pipelines (stateless balance refresh vs. stateful cursor pagination). They are deliberately separate vertical slices and must not be combined into a generic `PlaidSyncManager`.
4. **Decoupled from PlaidAccountSyncManager:** Although Transaction Sync refreshes balances before fetching transactions, it must **not** invoke `PlaidAccountSyncManager`. Standalone Account Sync commits immediately (`db.commit()`), whereas Transaction Sync stages updates with `db.flush()` so that balance updates roll back if transaction fetching fails.
5. **Dedicated Raw HTTP External Access (`plaid_transaction_access.py`):** Transaction sync uses raw `requests.post` calls to bypass Plaid Python SDK cursor validation bugs. It must not be merged into `plaid_access.py` (which uses the official Plaid Python SDK).
6. **Transitional Concrete Persistence Helper (`backend/crud/transaction.py`):** In Slice 7, transaction database operations are delegated to existing legacy helpers in `backend/crud/transaction.py` (`create_or_update_transaction`, `delete_transaction_by_plaid_id`). These are classified as **transitional concrete persistence helpers**, not as the final desired ResourceAccess architecture. A clean `TransactionAccess` abstraction and schema fix are deferred to a dedicated follow-up slice to prevent mixing bug fixes or broad persistence rewrites into Slice 7.
7. **Transitional Commit Ownership:** The Manager owns event sequencing and determines when each legacy helper is invoked. The legacy transaction persistence helpers continue to own their existing internal per-event commits. Therefore, Slice 7 does not yet completely move transaction-boundary ownership into the Manager; this is deliberate transitional debt.
8. **Decoupled Router Error Knowledge:** The Router imports and catches only framework-free Manager/application errors. It contains zero knowledge of ResourceAccess errors (`PlaidAccessError`, `PlaidTransactionHttpError`, `PlaidTransactionNetworkError`), requests exceptions, or Plaid SDK exceptions.

---

## 2. No Engine Justified

Creating an engine (e.g. `PlaidTransactionEngine`, `TransactionSyncEngine`, `TransactionLifecycleEngine`, `SyncEngine`) is **explicitly rejected**.

### Analysis of Candidate Responsibilities:
1. **Amount Sign Negation (`stored local amount = -raw Plaid amount`):**
   - The characterized behavior requires:
     - raw `+35.00` $\rightarrow$ stored `-35.00`
     - raw `-5.50` $\rightarrow$ stored `+5.50`
     - raw `0` $\rightarrow$ stored `0`
   - This exact formula (`-tx_data['amount']`) is preserved as characterized.
   - Negating a number is a 1-line primitive data mapping, not an independently volatile calculation engine.
2. **Event Dispatch (`added`, `modified`, `removed`):**
   - Branching on event type received from an external REST API is standard workflow control flow, which belongs squarely in the Manager.
3. **Pagination & Cursor Progression:**
   - Tracking `has_more` and updating `cursor = next_cursor` is standard transport loop orchestration.
4. **Field Mapping (`name -> description`, `date -> date`, etc.):**
   - Transport-to-schema field mapping is an integration concern, not domain calculation.

None of these operations vary independently from the Plaid sync workflow or contain domain heuristics. Introducing an Engine would represent speculative abstraction and violate VBD Principle 3.

---

## 3. Workflow Manager Justification

The `PlaidTransactionSyncManager` is justified strictly by an **observed multi-step business workflow**:

```text
validate identifier presence (item_id or plaid_item_id)
        ↓
resolve PlaidItem from persistence using item_id precedence
        ↓
decode stored access token via existing security helper
        ↓
fetch current accounts from Plaid external ResourceAccess (plaid_access)
        ↓
for each remote account:
    stage local Account record via Account ResourceAccess (account_access)
        ↓
db.flush() (balance updates staged in session, NOT committed)
        ↓
read initial cursor from PlaidItem.transactions_cursor
        ↓
while has_more:
    fetch transaction page via Plaid Transaction External Access (plaid_transaction_access)
        ↓
    advance in-memory cursor to page.next_cursor
        ↓
    for each added:
        invoke create_or_update_transaction (legacy helper executes internal db.commit())
        ↓
    for each modified:
        invoke create_or_update_transaction (legacy helper executes internal db.commit())
        ↓
    for each removed:
        invoke delete_transaction_by_plaid_id
        if row found: legacy helper deletes and executes internal db.commit()
        if row missing: no delete, NO event-level commit executed
        ↓
    repeat while page.has_more is True
        ↓
stage final in-memory cursor via PlaidItemAccess.stage_transactions_cursor(db, plaid_item.plaid_item_id, cursor) (NO commit)
        ↓
db.commit() (behavioral equivalent of legacy cursor helper commit)
        ↓
db.commit() (preserves existing final redundant commit)
        ↓
return PlaidTransactionSyncResult(message, added, modified, removed, next_cursor)
```

### Rationale:
- Coordinates five distinct boundaries: `PlaidItem` persistence, token decoding, external account fetching, external transaction pagination, and transaction persistence.
- Owns pagination loop control, cursor lifecycle, error translation, and final commit timing.
- Keeps HTTP routing and transport mechanics separate from sync coordination.

---

## 4. Presentation / Router Responsibilities

File: [`backend/routers/plaid.py`](../../backend/routers/plaid.py)

### Router Owns:
- Route registration: `@router.post("/sync_transactions", response_model=Dict[str, Any])`.
- Request body deserialization into [`schemas.PlaidSyncRequest`](../../backend/schemas.py).
- Acquiring database session via dependency injection: `db: Session = Depends(get_db)`.
- Invoking the Manager:
  ```python
  result = plaid_transaction_sync_manager.sync_plaid_transactions(
      db=db,
      item_id=payload.item_id,
      plaid_item_id=payload.plaid_item_id,
  )
  ```
- Catching **only** framework-free application exceptions from the Manager and translating them to HTTP responses:
  - `PlaidTransactionSyncMissingIdentifierError` $\rightarrow$ `HTTPException(400, detail="Must provide item_id or plaid_item_id")`
  - `PlaidTransactionSyncItemNotFoundError` $\rightarrow$ `HTTPException(404, detail="Plaid Item not found")`
  - `PlaidTransactionSyncDecryptionError` $\rightarrow$ `HTTPException(500, detail="Error decrypting access token")`
  - `PlaidTransactionSyncAccountRefreshError` $\rightarrow$ `HTTPException(status_code=exc.status_code, detail=exc.detail)`
  - `PlaidTransactionSyncHttpError` $\rightarrow$ `HTTPException(status_code=exc.status_code, detail=f"Plaid Sync Error: {exc.detail}")`
  - `PlaidTransactionSyncNetworkError` $\rightarrow$ `HTTPException(status_code=500, detail=exc.detail)`
  - Unexpected errors $\rightarrow$ `HTTPException(500, detail=str(exc))`
- Serializing `PlaidTransactionSyncResult` to the existing JSON response contract:
  ```json
  {
    "message": "Sync successful",
    "added": 5,
    "modified": 2,
    "removed": 1,
    "next_cursor": "cur_abc123"
  }
  ```

### Router Must NOT Import or Retain:
- ResourceAccess error classes (`PlaidAccessError`, `PlaidTransactionHttpError`, `PlaidTransactionNetworkError`).
- PlaidItem database queries (`db.query(models.PlaidItem)`).
- Direct Account balance queries or staging.
- Direct invocation of Plaid SDK clients or raw HTTP requests (`requests`).
- Plaid SDK exception classes (`ApiException`).
- Token decryption logic (`decrypt_token`).
- Pagination loops (`while has_more:`).
- Transaction CRUD operations or commits.

---

## 5. Request Precedence & Identifier Validation

Schema:
```python
class PlaidSyncRequest(BaseModel):
    plaid_item_id: Optional[str] = None
    item_id: Optional[UUID] = None
```

### Validation Precedence Rules:
1. **Missing Identifiers:** If neither `item_id` nor `plaid_item_id` is supplied:
   ```text
   raise PlaidTransactionSyncMissingIdentifierError("Must provide item_id or plaid_item_id")
   → HTTP 400
   ```
2. **`item_id` Precedence:** If both `item_id` and `plaid_item_id` are provided, `item_id` takes precedence. The Manager resolves the `PlaidItem` strictly by `item_id`.
3. **Item Not Found:** If the chosen identifier does not match any record in PostgreSQL:
   ```text
   raise PlaidTransactionSyncItemNotFoundError("Plaid Item not found")
   → HTTP 404
   ```
   **No Fallback:** If `item_id` is supplied but does not exist, the Manager must **not** fall back to searching by `plaid_item_id`.

---

## 6. Token Security & Credential Boundary

File: [`backend/security.py`](../../backend/security.py)

### Invariants:
- The existing Base64 placeholder implementation in `backend/security.py:decrypt_token` remains **unchanged**.
- Slice 7 does **not** introduce real cryptographic encryption; that remains a future security migration slice.

### Malformed-Token Behavior (Characterized Invariant):
`decrypt_token` catches decode exceptions internally and returns `""` (empty string).
- In the characterized application:
  ```text
  malformed token in database
          ↓
  decrypt_token returns ""
          ↓
  Manager calls Plaid external API with access_token=""
          ↓
  Plaid API returns error (e.g. HTTP 400 INVALID_ACCESS_TOKEN)
          ↓
  Plaid HTTP status and body reach client as HTTP error
  ```
- **Constraint:** The Manager must **not** add validation like `if not access_token: raise ...`. It must pass the decoded string directly to the external Accessor.

### Escaping Decrypt-Exception Behavior:
If `decrypt_token` raises an unexpected exception outward:
```text
escaping decrypt exception
        ↓
Manager raises PlaidTransactionSyncDecryptionError("Error decrypting access token")
        ↓
Router returns HTTP 500 (detail="Error decrypting access token")
```

---

## 7. Balance Refresh Coupling & Decoupled Architecture

Before syncing transactions, the workflow refreshes balances for all accounts associated with the `PlaidItem`.

### Why NOT to Compose `PlaidAccountSyncManager`:
- Standalone `PlaidAccountSyncManager.sync_plaid_accounts` executes an explicit `db.commit()` at the end of its execution.
- In `POST /plaid/sync_transactions`, account balance updates are staged with `db.flush()` and **piggybacked** onto transaction commits.
- If `/transactions/sync` fails on the very first page or during balance refresh, the database session is rolled back, leaving account balances unchanged.
- Composing `PlaidAccountSyncManager` would prematurely commit balance updates before transaction synchronization begins, violating characterized rollback behavior.

### Direct ResourceAccess Reuse & Application Error Mapping:
1. Manager calls `plaid_access.fetch_accounts_for_token(access_token)` to fetch `Sequence[PlaidAccountSnapshot]`.
   - If `plaid_access` raises `PlaidAccessError(status_code, detail)`, the Manager catches it and raises:
     ```python
     raise PlaidTransactionSyncAccountRefreshError(
         status_code=exc.status_code,
         detail=exc.detail,
     )
     ```
   - Router translates `PlaidTransactionSyncAccountRefreshError` to:
     ```text
     HTTP status_code = exc.status_code
     detail = exc.detail
     ```
   - **No Prefix:** No `"Plaid Sync Error: "` prefix applies to the account-refresh path. Characterized raw Plaid `/accounts/get` `ApiException` details (`e.status`, `e.body`) are preserved exactly.
2. Manager calls `account_access.stage_or_update_plaid_account(...)` to stage each account update in PostgreSQL.
3. Manager executes `db.flush()` to send SQL updates to PostgreSQL without committing.

### Commit Piggybacking Invariant:
- If transactions are processed (`added` > 0, `modified` > 0, or `removed` > 0 with matching row), the staged balance updates are committed along with the first transaction's internal `db.commit()`.
- If zero transaction events occur across all pages, the staged balance updates are committed along with the final cursor `db.commit()`.
- If an error occurs prior to the first commit (e.g. Plaid returns HTTP 400 on page 1), session teardown rolls back the staged balance updates.

---

## 8. Dedicated Plaid Transaction External ResourceAccess

File: `backend/access/plaid_transaction_access.py`

### Why Separate from `plaid_access.py`:
- `backend/access/plaid_access.py` encapsulates the official Plaid Python SDK (`PlaidApi`, `AccountsGetRequest`).
- Plaid's Python SDK has a known cursor validation bug when calling `/transactions/sync` (raising SDK-level validation errors when handling cursor states).
- The codebase uses raw HTTP via `requests.post` to execute `/transactions/sync`.
- To avoid polluting `plaid_access.py` with raw HTTP request code and environment resolution, transaction sync external access is placed in a dedicated module.

### Protocol Details:
- **Base URL Resolution:**
  - `PLAID_ENVIRONMENT` environment variable (`"Sandbox"`, `"Development"`, `"Production"`, defaulting to `"Sandbox"`).
  - Sandbox: `https://sandbox.plaid.com`
  - Development: `https://development.plaid.com`
  - Production: `https://production.plaid.com`
- **Endpoint:** `f"{PLAID_BASE}/transactions/sync"`
- **HTTP Method:** `POST`
- **Headers:**
  ```python
  {
      "Content-Type": "application/json",
      "PLAID-CLIENT-ID": os.getenv("PLAID_CLIENT_ID"),
      "PLAID-SECRET": os.getenv("PLAID_SECRET"),
  }
  ```
- **Payload:**
  - `access_token`: string
  - `count`: 500 (Plaid maximum per page)
  - `cursor`: included in JSON payload **only if** `cursor` is a non-empty string. If `cursor` is `None` or `""`, the `"cursor"` key is omitted from the request body.
- **Timeout:** `timeout=60` seconds.

### Data Contract & Infrastructure Exceptions:
```python
@dataclass(frozen=True)
class PlaidTransactionPage:
    added: list[dict[str, Any]]
    modified: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    next_cursor: str
    has_more: bool


class PlaidTransactionHttpError(Exception):
    """Raised when external Plaid /transactions/sync returns an HTTP error status."""
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PlaidTransactionNetworkError(Exception):
    """Raised when external Plaid /transactions/sync encounters a network/connection/timeout error."""
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def fetch_transactions_page(
    access_token: str,
    cursor: Optional[str] = None,
) -> PlaidTransactionPage:
    """Calls Plaid /transactions/sync via raw HTTP requests."""
```

### Accessor Exception Mapping Rules:
- `requests.exceptions.HTTPError` $\rightarrow$ `PlaidTransactionHttpError(status_code=e.response.status_code, detail=e.response.text)`
  - Stores raw `e.response.text` as detail. Does **not** prepend `"Plaid Sync Error: "`.
- Other request/network/timeout exceptions $\rightarrow$ `PlaidTransactionNetworkError(detail=str(exc))`
- The Accessor must **not** import Manager exceptions.

---

## 9. PlaidItem Persistence & Cursor Management

File: `backend/access/plaid_item_access.py`

### Existing Lookups Reused:
- `get_plaid_item_by_id(db, item_id)`
- `get_plaid_item_by_plaid_item_id(db, plaid_item_id)`

### Cursor Staging Operation (Stage-Only):
```python
def stage_transactions_cursor(
    db: Session,
    plaid_item_id: str,
    cursor: str,
) -> None:
    """
    Looks up PlaidItem by plaid_item_id, assigns transactions_cursor, and adds to session.
    Performs NO database commit.
    """
    plaid_item = get_plaid_item_by_plaid_item_id(db, plaid_item_id)
    if plaid_item:
        plaid_item.transactions_cursor = cursor
        db.add(plaid_item)
```

### Cursor Lifecycle & Progression Rules:
1. **Initial Cursor:** Read from `plaid_item.transactions_cursor`. If `None` or `""`, initial request omits the cursor key.
2. **In-Memory Advancement:** `cursor` is updated to `page.next_cursor` **before** event iteration begins for that page.
3. **Loop Continuation:** If `page.has_more == True`, the next page request uses `cursor = page.next_cursor`.
4. **Final Cursor Staging & Two-Stage Final Commit Sequence:**
   - After the pagination loop terminates (`has_more == False`), `stage_transactions_cursor(db, plaid_item.plaid_item_id, in_memory_cursor)` is called.
   - The Manager then executes the **two-stage final commit sequence**:
     ```python
     stage_transactions_cursor(db, plaid_item.plaid_item_id, cursor)
     db.commit()  # Behavioral equivalent of legacy cursor helper commit
     db.commit()  # Preserves existing final redundant commit
     ```
   - **Deliberate Compatibility Artifact:** The second `db.commit()` is redundant but preserved verbatim from legacy behavior (`crud_plaid.update_transactions_cursor` committed, followed by an immediate outer `db.commit()` in `sync_transactions_from_plaid`). It is documented as a compatibility artifact deliberately preserved during structural extraction, not as good design.

### Multi-Page Failure Invariant:
If page 1 succeeds and commits transactions, but page 2 fails (e.g. Plaid returns HTTP 500):
- Page 1 transactions remain committed in PostgreSQL.
- `PlaidItem.transactions_cursor` in PostgreSQL **remains at its starting value** (cursor persistence occurs only after all pages complete).
- On the next sync attempt, Plaid will re-send page 1 transactions. Because transactions are matched by `plaid_transaction_id` and updated in place, replaying page 1 events is safe and idempotent.

---

## 10. Transaction Event Processing & Commit Semantics

File: `backend/crud/transaction.py` (transitional concrete persistence helper)

### Event Processing Order:
For each page received from Plaid, events are processed in strict sequential order:
1. `added` list
2. `modified` list
3. `removed` list

### 1. `added` Events:
- Lookup existing record: `get_transaction_by_plaid_id(db, tx_data["transaction_id"])`.
- Lookup account: `get_account_by_plaid_account_id(db, tx_data["account_id"])`. If not found, raises Exception.
- **If transaction does not exist:**
  - Invert amount: `amount_for_budget = -tx_data["amount"]`.
  - Validate and stage via `TransactionCreate`:
    - `plaid_transaction_id = tx_data["transaction_id"]`
    - `account_id = db_account.id`
    - `category_id = None` (uncategorized)
    - `description = tx_data["name"]`
    - `amount = amount_for_budget`
    - `date = tx_data["date"]`
    - `datetime = tx_data.get("datetime")`
    - `pending = tx_data["pending"]`
  - Legacy helper adds to session, executes internal `db.commit()`, and refreshes model.
- **If transaction already exists (collision / re-sync):**
  - Update mutable fields: `description = tx_data["name"]`, `amount = -tx_data["amount"]`, `date = tx_data["date"]`, `datetime = tx_data.get("datetime")`, `pending = tx_data["pending"]`.
  - **Preserve user fields:** `category_id`, `is_transfer`, `account_id`, `transaction_id`.
  - Legacy helper adds to session, executes internal `db.commit()`, and refreshes model.
- Increments `added_count`.

### 2. `modified` Events:
- Lookup existing record: `get_transaction_by_plaid_id(db, tx_data["transaction_id"])`.
- **If transaction exists:**
  - Update mutable fields: `description = tx_data["name"]`, `amount = -tx_data["amount"]`, `date = tx_data["date"]`, `datetime = tx_data.get("datetime")`, `pending = tx_data["pending"]`.
  - **Preserve user fields:** `category_id`, `is_transfer`, `account_id` (even if Plaid sends a different `account_id`), `transaction_id`.
  - Legacy helper adds to session, executes internal `db.commit()`, and refreshes model.
- **If transaction does not exist locally (out-of-order modify):**
  - Fall back to creation path (same as `added`).
  - Legacy helper executes internal `db.commit()`.
- Increments `modified_count`.

### 3. `removed` Events:
- Lookup existing record: `get_transaction_by_plaid_id(db, tx_data["transaction_id"])`.
- **If found (`R_found`):**
  - `db.delete(db_transaction)`
  - Legacy helper executes internal `db.commit()`.
- **If not found (`R_missing`):**
  - No database deletion occurs.
  - **NO `db.commit()` is executed.**
- Increments `removed_count` regardless of local presence.

### Per-Event Commit Summary Table:

| Event Type | Local Match Found? | Database Action | Executes `db.commit()`? | Count Incremented? |
|---|:---:|---|:---:|:---:|
| `added` | No | Insert new `Transaction` | **Yes** (via legacy helper) | `added_count += 1` |
| `added` | Yes | Update existing `Transaction` | **Yes** (via legacy helper) | `added_count += 1` |
| `modified` | Yes | Update existing `Transaction` | **Yes** (via legacy helper) | `modified_count += 1` |
| `modified` | No | Insert new `Transaction` | **Yes** (via legacy helper) | `modified_count += 1` |
| `removed` | Yes | Delete existing `Transaction` | **Yes** (via legacy helper) | `removed_count += 1` |
| `removed` | No | No-op | **No** | `removed_count += 1` |

---

## 11. Schema Datetime Validation Resolution (Slice 8)

In [`backend/schemas.py`](../../backend/schemas.py), `TransactionCreate` and `TransactionRead` originally defined:
```python
class TransactionCreate(BaseModel):
    ...
    datetime: Optional[datetime] = None
```
Because the field name `datetime` matched the type name `datetime` within class scope, Python/Pydantic resolved `datetime` to `NoneType`, causing newly added or missing-modified Plaid transactions with non-null timestamps to fail with HTTP 500.

### Resolution in Slice 8:
- Disambiguated imported type as `DateTime` (`from datetime import date, datetime, datetime as DateTime`).
- Updated `TransactionCreate` and `TransactionRead` annotations to `datetime: Optional[DateTime] = None`.
- Pydantic now resolves the field to `Optional[datetime.datetime]`. Non-null ISO timestamps from Plaid events validate cleanly, persist to PostgreSQL `TIMESTAMP WITH TIME ZONE`, and serialize properly in reads.
- Characterization coverage was updated to freeze and verify the corrected persistence and serialization behavior.

---

## 12. Framework-Free Application Error Contract

File: `backend/managers/plaid_transaction_sync_manager.py`

The Manager contains no FastAPI or Pydantic imports:

```python
class PlaidTransactionSyncMissingIdentifierError(Exception):
    """Raised when neither item_id nor plaid_item_id is provided."""
    pass


class PlaidTransactionSyncItemNotFoundError(Exception):
    """Raised when the requested PlaidItem does not exist in persistence."""
    pass


class PlaidTransactionSyncDecryptionError(Exception):
    """Raised when token decryption raises an unexpected exception."""
    pass


class PlaidTransactionSyncAccountRefreshError(Exception):
    """Raised when external Plaid /accounts/get fails during pre-sync balance refresh."""
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PlaidTransactionSyncHttpError(Exception):
    """Raised when external raw HTTP /transactions/sync returns an HTTP error status."""
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PlaidTransactionSyncNetworkError(Exception):
    """Raised when external raw HTTP /transactions/sync encounters a network/connection/timeout error."""
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail
```

---

## 13. Manager Contract & Result

File: `backend/managers/plaid_transaction_sync_manager.py`

```python
@dataclass(frozen=True)
class PlaidTransactionSyncResult:
    message: str
    added: int
    modified: int
    removed: int
    next_cursor: str


def sync_plaid_transactions(
    db: Session,
    item_id: Optional[UUID] = None,
    plaid_item_id: Optional[str] = None,
) -> PlaidTransactionSyncResult:
    """
    Coordinates the Plaid transaction synchronization workflow:
    1. Validates presence of at least one identifier.
    2. Resolves PlaidItem using item_id precedence.
    3. Decrypts access token via security helper.
    4. Stages account balance updates:
       - Calls plaid_access.fetch_accounts_for_token(access_token).
         Catches PlaidAccessError -> raises PlaidTransactionSyncAccountRefreshError.
       - Stages account records via account_access.stage_or_update_plaid_account.
       - Executes db.flush() (staged in session, NOT committed).
    5. Reads starting cursor from PlaidItem.transactions_cursor.
    6. Executes pagination loop against PlaidTransactionAccess:
       - Calls plaid_transaction_access.fetch_transactions_page(access_token, cursor).
         Catches PlaidTransactionHttpError -> raises PlaidTransactionSyncHttpError.
         Catches PlaidTransactionNetworkError -> raises PlaidTransactionSyncNetworkError.
       - Advances in-memory cursor to page.next_cursor before event iteration.
       - Invokes legacy helpers for added, modified, and removed events.
         (Legacy helpers execute internal per-event commits as characterized).
    7. Stages final cursor via plaid_item_access.stage_transactions_cursor(db, plaid_item.plaid_item_id, cursor).
    8. Executes two-stage final commits:
       - db.commit()  # Equivalent to legacy cursor helper commit
       - db.commit()  # Redundant final commit preserved for compatibility
    9. Returns PlaidTransactionSyncResult.
    """
```

---

## 14. Volatility Classification

### Observed Volatility (Justified Boundaries):
- **Plaid Raw HTTP Protocol:** Direct REST request, timeout, count, and cursor omission $\rightarrow$ [`backend/access/plaid_transaction_access.py`](../../backend/access/plaid_transaction_access.py).
- **Workflow Sequencing:** Pagination loop, balance refresh staging, cursor progression, error translation, final commit timing $\rightarrow$ [`backend/managers/plaid_transaction_sync_manager.py`](../../backend/managers/plaid_transaction_sync_manager.py).
- **PlaidItem Relational Storage:** PostgreSQL schema and cursor staging $\rightarrow$ [`backend/access/plaid_item_access.py`](../../backend/access/plaid_item_access.py).
- **Account Relational Storage:** PostgreSQL schema and balance updates $\rightarrow$ [`backend/access/account_access.py`](../../backend/access/account_access.py).
- **Plaid External Account Access:** Official Plaid SDK for accounts/get $\rightarrow$ [`backend/access/plaid_access.py`](../../backend/access/plaid_access.py).
- **Transitional Concrete Persistence Helper:** Transitional relational transaction mutations $\rightarrow$ [`backend/crud/transaction.py`](../../backend/crud/transaction.py).
- **Credential Storage Utility:** Base64 placeholder decryption $\rightarrow$ [`backend/security.py`](../../backend/security.py).

### Speculative Volatility (Explicitly Rejected):
- Transaction domain calculation engine (`PlaidTransactionEngine`, `TransactionSyncEngine`).
- Monolithic `PlaidSyncManager` merging account and transaction sync.
- Direct composition of `PlaidAccountSyncManager` within Transaction Sync.
- Generic bank provider interfaces (`IBankProvider`).
- Automatic transaction categorization ML engines.
- Background asynchronous worker queues (Celery/Redis/Kafka).
- Generic Unit of Work or repository abstractions.

---

## 15. Dependency Rules

### Allowed:
```text
Router -> PlaidTransactionSyncManager

Manager -> PlaidItemAccess
Manager -> PlaidAccess
Manager -> AccountAccess
Manager -> PlaidTransactionAccess
Manager -> Legacy Transaction Persistence Helpers (crud/transaction.py)
Manager -> security.decrypt_token
Manager -> Session (application context)

Manager may import focused ResourceAccess errors (PlaidAccessError, PlaidTransactionHttpError, PlaidTransactionNetworkError) to translate them.
ResourceAccess -> SQLAlchemy / PostgreSQL / requests
```

### Prohibited:
```text
Router -> ResourceAccess errors (PlaidAccessError, PlaidTransactionHttpError, PlaidTransactionNetworkError)
Router -> requests
Router -> Plaid SDK exceptions

Manager -> FastAPI
Manager -> HTTPException
Manager -> requests
Manager -> Plaid SDK request/response classes

PlaidTransactionAccess -> Manager errors
PlaidAccess -> Manager errors

Transaction Sync -> PlaidAccountSyncManager (prohibited composition)
```

---

## 16. Characterization Safety Baseline

Pre-refactoring safety baseline: **197 passed, 45 warnings in 5.00s** (100% green).
Protected by [`tests/test_characterization_plaid_transactions.py`](../../tests/test_characterization_plaid_transactions.py) across 34 dedicated endpoint-level scenarios covering:
- Identifier validation errors (400) and `item_id` precedence over `plaid_item_id`;
- PlaidItem missing errors (404);
- Malformed token returning empty string to Plaid API;
- Escaping decryption exception producing HTTP 500;
- Account balance refresh staging and `db.flush()` execution;
- Balance refresh rollback on initial transaction sync failure;
- Staged balance commit piggybacking on first transaction event or final cursor;
- Cursor omission on initial sync when `cursor` is `None` or `""`;
- Cursor inclusion on subsequent requests;
- Multi-page pagination loop with count and next_cursor aggregation;
- Multi-page failure preserving starting cursor in PostgreSQL while keeping earlier page transactions committed;
- Amount sign negation (`stored = -raw`);
- Added events: new transaction insertion with per-event commit;
- Added events: existing transaction collision updating mutable fields while preserving `category_id` and `is_transfer`;
- Datetime schema validation resolution on `added` and `modified-missing` events (resolved in Slice 8);
- Modified events: existing transaction update preserving `category_id`, `is_transfer`, and `account_id`;
- Modified events: missing transaction falling back to insert;
- Removed events: found transaction deleted with `db.commit()`;
- Removed events: missing transaction no-op without `db.commit()`;
- Error detail formatting: `f"Plaid Sync Error: {e.response.text}"` from HTTP errors vs generic network errors without prefix.

---

## 17. Deferred Follow-Up Slices

1. **Transaction ResourceAccess Extraction:**
   - Extract `create_or_update_transaction` and `delete_transaction_by_plaid_id` from `backend/crud/transaction.py` into a focused `backend/access/transaction_access.py`.
   - Separate manual transaction CRUD from external Plaid transaction persistence.
   - Transition transaction commit ownership cleanly into the Manager.
2. **Schema Annotation Fix (Resolved in Slice 8):**
   - Resolved class-scope `datetime: Optional[DateTime]` name collision in `backend/schemas.py:TransactionCreate` and `TransactionRead`.
3. **Plaid Token Encryption Migration:**
   - Replace Base64 placeholder in `backend/security.py` with real cryptographic encryption (e.g. Fernet) and migrate existing tokens.
