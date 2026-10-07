# CSV Confirmation & Deduplication Architecture Specification (Slice 5 - Implemented & Verified)

## 1. Overview & Conceptual Architecture

The CSV Confirmation & Deduplication workflow (`POST /upload/confirm`) parses uploaded bank statement CSV files (supporting built-in USAA and Discover formats as well as user-defined custom formats via `MappedStatementLoader`), verifies target account validity, detects exact duplicate transactions against existing records, stages non-duplicate transactions, and commits them in a single batch transaction.

Under Volatility-Based Decomposition (VBD), this workflow decomposes into:

```text
FastAPI Upload Router (backend/routers/upload.py)
        ↓ resolves format ("usaa" | "discover" | <custom_uuid>) via _resolve_statement_loader
        ├── CSV Format ResourceAccess (backend/access/csv_format_access.py) ────────→ PostgreSQL
        ↓ passes resolved BankStatementLoader instance
CSV Import Manager (backend/managers/csv_import_manager.py)
        ├── Account ResourceAccess (backend/access/account_access.py) ─────────────→ PostgreSQL
        ├── Transaction ResourceAccess (backend/access/transaction_access.py) ─────→ PostgreSQL
        └── BankStatementLoader boundary (backend/bank_statement_loader.py)
                ├── USAALoader
                ├── DiscoverLoader
                └── MappedStatementLoader (configurable custom formats)
```

### Key Architectural Boundaries:
1. **No New Engine:** Deduplication is a concrete persistence-backed existence lookup, not an independently volatile calculation or business policy. An engine is explicitly rejected.
2. **StatementLoader Boundary Preserved:** The `BankStatementLoader` hierarchy in [`backend/bank_statement_loader.py`](../../backend/bank_statement_loader.py) remains authoritative for file parsing, header mapping, bank date formats, and sign normalization. Dynamic custom formats are parsed through `MappedStatementLoader` driven by immutable `MappedCSVFormatConfig`.
3. **Account & Transaction ResourceAccess:** Direct SQLAlchemy queries in the router are moved behind focused, concrete ResourceAccess operations.
4. **Single Transaction Boundary:** The Manager owns the workflow sequencing and the single final `db.commit()`.

---

## 2. Manager Justification

The `CSVImportManager` is justified strictly by an **observed multi-step business workflow**:

```text
verify destination account exists (Account ResourceAccess)
        ↓
parse raw bytes into valid transactions and non-fatal row errors via loader.load_records_tolerant (BankStatementLoader)
        ↓
for each valid transaction:
    check exact duplicate existence (Transaction ResourceAccess)
    if duplicate:
        skipped += 1
    else:
        stage new Transaction (Transaction ResourceAccess)
        imported += 1
    catch existing per-row exceptions and record formatted error
        ↓
commit batch transaction (single db.commit())
        ↓
return CSVImportSummary(imported, skipped, errors)
```

### Rationale:
- This workflow coordinates multiple distinct boundaries: Account ResourceAccess, the StatementLoader parser, Transaction ResourceAccess, per-row error isolation, and database transaction commit.
- The use case ("confirm and import statement") changes independently from HTTP multipart transport handling (FastAPI `UploadFile`, `Form(...)`) and from file-format-specific CSV schemas.
- A Manager is justified because of this meaningful orchestration sequence, **not** because every endpoint requires a Manager.

---

## 3. Transport vs. Application Sequencing Clarification

In the legacy router, execution was interleaved with transport operations:
```text
account lookup → UploadFile read → loader resolution → parse
```

In the implemented VBD architecture:
- The **Router** owns transport I/O:
  ```python
  raw_bytes = await file.read()
  await file.seek(0)
  ```
- The Router verifies account existence and resolves the format identifier to a concrete `BankStatementLoader` instance (USAA, Discover, or `MappedStatementLoader`).
- The **Manager** executes the application validation sequence:
  ```text
  account lookup → statement parsing (tolerant) → duplicate check & staging loop → commit
  ```

### Invariant Application Validation Precedence:
The application validation precedence is strictly:
$$\text{Account Existence (404)} \longrightarrow \text{Format Validity (400 / 404)} \longrightarrow \text{Statement Parsing (422)}$$

- Nonexistent account + unknown format $\rightarrow$ Account error (HTTP 404).
- Nonexistent account + malformed CSV $\rightarrow$ Account error (HTTP 404).
- Valid account + unknown format $\rightarrow$ Format error (HTTP 400 for bad string, HTTP 404 for unknown custom UUID).
- Valid account + malformed CSV headers $\rightarrow$ Parse error (HTTP 422).

Reading `UploadFile` bytes prior to Manager invocation is a transport extraction step and does not alter this domain validation precedence.

---

## 4. Presentation / Router Responsibilities

File: [`backend/routers/upload.py`](../../backend/routers/upload.py)

### Router Owns:
- FastAPI endpoint registration: `@router.post("/confirm", response_model=schemas.CSVImportResult)`.
- Multipart form parameter extraction: `file: UploadFile = File(...)`, `account_id: UUID = Form(...)`, `format: str = Form(...)`.
- Resolving the loader via `_resolve_statement_loader(db, account_id, format)`:
  - `"usaa"` or `"discover"` $\rightarrow$ built-in loader from `LOADER_REGISTRY`;
  - custom UUID $\rightarrow$ fetches `CSVFormat` via `csv_format_access.get_custom_format_by_id`, builds `MappedCSVFormatConfig`, returns `MappedStatementLoader`;
  - invalid string $\rightarrow$ `HTTPException(400, detail="Unknown format...")`;
  - unknown UUID $\rightarrow$ `HTTPException(404, detail="Format <uuid> not found")`.
- Reading `UploadFile` stream into `raw_bytes: bytes`.
- Acquiring database session via dependency injection: `db: Session = Depends(get_db)`.
- Invoking the Manager: `csv_import_manager.confirm_csv_import(db=db, raw_bytes=raw, loader=loader)`.
- Catching framework-free application exceptions and mapping them to HTTP status codes:
  - `CSVImportAccountNotFoundError` $\rightarrow$ `HTTPException(404, detail=str(exc))`
  - `CSVImportParseError` $\rightarrow$ `HTTPException(422, detail=str(exc))`
- Mapping `CSVImportSummary` to [`schemas.CSVImportResult`](../../backend/schemas.py).
- Returning HTTP 200 OK.

### Router Must NOT Retain:
- Transaction duplicate queries (`db.query(models.Transaction)`).
- Direct instantiation of `models.Transaction`.
- Transaction staging loops.
- `db.commit()` workflow orchestration.
- CSV parsing internals.

---

## 5. Framework-Free Application Error Contract

File: `backend/managers/csv_import_manager.py`

The Manager contains **no FastAPI imports** and raises zero `HTTPException`s. It defines application error classes:

```python
class CSVImportAccountNotFoundError(Exception):
    """Raised when the target account cannot be found in persistence."""


class CSVImportUnknownFormatError(Exception):
    """Raised when the requested format string is not in the loader registry (legacy/compatibility)."""


class CSVImportParseError(Exception):
    """Raised when the statement loader fails to parse the CSV bytes."""
```

### Exact Message Preservation:
1. **Missing Account:**
   ```python
   raise CSVImportAccountNotFoundError(f"Account {account_id} not found")
   ```
2. **Invalid Statement / Missing Columns:**
   ```python
   try:
       parsed = loader.load_records_tolerant(raw_bytes)
   except ValueError as exc:
       raise CSVImportParseError(str(exc)) from exc
   ```

The Router maps `str(exc)` directly into `detail`, preserving exact existing error strings without leaking parser types into presentation.

---

## 6. Manager Contract

File: `backend/managers/csv_import_manager.py`

### Function Signature:
```python
def confirm_csv_import(
    db: Session,
    raw_bytes: bytes,
    loader: BankStatementLoader,
) -> CSVImportSummary:
    """
    Coordinates the CSV confirmation and import workflow:
    1. Verifies destination account exists via get_account_by_id(db, loader.account_id).
    2. Parses CSV bytes into normalized transactions via loader.load_records_tolerant.
    3. Iterates parsed transactions:
       - Checks duplicate existence via csv_import_transaction_exists.
       - If duplicate, increments skipped counter.
       - If new, stages transaction via stage_csv_import_transaction and increments imported.
       - Catches per-row exceptions and formats row error strings.
    4. Commits the transaction batch via db.commit().
    5. Returns CSVImportSummary.
    """
```

### Rules & Invariants:
- Accepts `db: Session` as application context under established VBD pragmatic coupling.
- Accepts `raw_bytes: bytes` (does not import `UploadFile`).
- Accepts `loader: BankStatementLoader` resolved by the router.
- Exposes no ORM models or Pydantic schemas.

---

## 7. Manager Result Contract

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class CSVImportSummary:
    imported: int
    skipped: int
    errors: tuple[str, ...]
```

- Minimal, immutable dataclass.
- Decoupled from Pydantic and HTTP transport.
- Directly mapped by Router:
  ```python
  return schemas.CSVImportResult(
      imported=summary.imported,
      skipped=summary.skipped,
      errors=list(summary.errors),
  )
  ```

---

## 8. Account ResourceAccess

File: [`backend/access/account_access.py`](../../backend/access/account_access.py)

```python
def get_account_by_id(
    db: Session,
    account_id: UUID,
) -> Optional[models.Account]:
    """
    Retrieves an Account by primary key without active-status filtering.
    """
    return db.query(models.Account).filter(models.Account.id == account_id).first()
```

### Invariants:
- Filters strictly by primary key: `models.Account.id == account_id`.
- **No `is_active` filter:** Inactive accounts currently accept CSV imports.
- **No `type` filter:** All account types (`depository`, `credit`, etc.) are permitted.

---

## 9. Transaction ResourceAccess

File: [`backend/access/transaction_access.py`](../../backend/access/transaction_access.py)

Concrete, CSV-specific persistence operations:

```python
def csv_import_transaction_exists(
    db: Session,
    account_id: UUID,
    transaction_date: date,
    amount: Decimal,
    description: str,
) -> bool:
    """
    Checks if an identical transaction exists for the given account.
    Matches exact account_id, date, amount, and description (case-sensitive).
    """
    return (
        db.query(models.Transaction)
        .filter(
            models.Transaction.account_id == account_id,
            models.Transaction.date == transaction_date,
            models.Transaction.amount == amount,
            models.Transaction.description == description,
        )
        .first()
    ) is not None


def stage_csv_import_transaction(
    db: Session,
    account_id: UUID,
    transaction_date: date,
    amount: Decimal,
    description: str,
    pending: bool = False,
    category_id: Optional[UUID] = None,
    category_source: Optional[str] = None,
    transaction_datetime: Optional[datetime] = None,
    merchant: Optional[str] = None,
) -> models.Transaction:
    """
    Instantiates and stages a new manual CSV import Transaction in the session.
    Explicitly sets plaid_transaction_id = None.
    If merchant is omitted, normalizes merchant from description.
    Sets is_merchant_overridden = False.
    Does not flush or commit.
    """
    from ..domain.merchant_normalization import normalize_merchant

    resolved_merchant = merchant if merchant is not None else normalize_merchant(description)

    txn = models.Transaction(
        account_id=account_id,
        category_id=category_id,
        category_source=category_source,
        description=description,
        merchant=resolved_merchant,
        is_merchant_overridden=False,
        amount=amount,
        date=transaction_date,
        datetime=transaction_datetime,
        pending=pending,
        plaid_transaction_id=None,
    )
    db.add(txn)
    return txn
```

### Invariants:
- Staging calls `db.add(txn)`.
- It does **not** flush and does **not** commit.
- `plaid_transaction_id` is explicitly set to `None`.
- `is_transfer` defaults to `False` via ORM model column default.
- `category_id` and `category_source` are persisted exactly as passed; `TransactionAccess` performs zero provenance or categorization inference.

---

## 10. Exact Duplicate Identity Semantics

A transaction is considered an exact duplicate if and only if an existing record in PostgreSQL matches:

```text
account_id == incoming.account_id
AND date == incoming.date
AND amount == incoming.amount
AND description == incoming.description
```

### Operational Rules:
1. **Account Scoping:** Duplicate checking is strictly scoped to `account_id`. The same date, amount, and description on a different account is **not** a duplicate.
2. **Date:** Exact `datetime.date` equality.
3. **Amount:** Exact `Decimal` equality (`DECIMAL(10, 2)`).
4. **Description:** Exact **case-sensitive** text equality in PostgreSQL (`models.Transaction.description == description`).
5. **Ignored Fields:** `category_id`, `pending`, `is_transfer`, `datetime`, and `plaid_transaction_id` are not evaluated.
6. **No Whitespace Alteration:** `csv_import_transaction_exists` performs no internal whitespace stripping or regex normalization.

---

## 11. Same-Request Duplicate Behavior (Preserved Invariant)

### Characterized Behavior:
If two identical rows appear in the same CSV file and neither existed in PostgreSQL prior to the request:
- **Both rows are imported** (`imported == 2, skipped == 0`).
- Both records exist in the database afterward.

### Root Cause:
1. `SessionLocal` runs with `autoflush=False`.
2. `stage_csv_import_transaction` calls `db.add()`, but does **not** flush.
3. `csv_import_transaction_exists` queries PostgreSQL directly, which does not see uncommitted, unflushed objects in `Session.new`.
4. `models.Transaction` has no composite unique constraint on `(account_id, date, amount, description)`.

### Refactoring Constraint:
This is characterized behavior and an explicit structural invariant. The refactor must not introduce:
- an in-memory `seen` set;
- per-row `db.flush()`;
- database unique constraints;
- `INSERT ... ON CONFLICT`.

---

## 12. Deduplication Is NOT an Engine

Creating a `DeduplicationEngine` or `TransactionMatchingEngine` is **firmly rejected**:
- Deduplication is a concrete single-table database query (`csv_import_transaction_exists`).
- There are no algorithmic computations, heuristics, or strategy choices.
- It directly depends on PostgreSQL persistence state (pure engines must not touch DB).
- Extracting a 4-field equality check into an Engine represents overengineering.

---

## 13. StatementLoader Remains the Parser Boundary

The existing parser hierarchy in [`backend/bank_statement_loader.py`](../../backend/bank_statement_loader.py) remains authoritative and unchanged:
- `BankStatementLoader` (ABC)
- `USAALoader` (handles USAA headers, date format `%Y-%m-%d`, and negates amounts so purchases are positive)
- `DiscoverLoader` (handles Discover headers, date format `%m/%d/%Y`, and preserves positive charges)
- `MappedStatementLoader` (configurable parser implementation driven by `MappedCSVFormatConfig`)
- `LOADER_REGISTRY` & `get_loader` (built-in loader registry)

The router resolves the loader instance via `_resolve_statement_loader` and passes it to `confirm_csv_import`, where the Manager coordinates tolerant statement parsing via `loader.load_records_tolerant(raw_bytes)`. No parser logic is moved into the Manager.

---

## 14. Preview Remains a Separate Workflow

`POST /upload/preview` is **outside this slice**:
- Preview is a stateless, read-only endpoint returning unpersisted `schemas.CSVPreviewResponse` rows.
- Confirmation reparses raw bytes independently and executes the persistence workflow.
- Preview and Confirmation must **not** be unified into a single monolithic Manager.

---

## 15. Per-Row Exception Scope & Error Formatting

Inside the transaction processing loop:
```python
for txn in transactions:
    try:
        if csv_import_transaction_exists(db, ...):
            skipped += 1
            continue
        stage_csv_import_transaction(db, ...)
        imported += 1
    except Exception as exc:
        errors.append(f"Row {txn.date} '{txn.description}': {exc}")
```

### Invariants:
1. **Try/Catch Scope:** Encloses duplicate check, ORM creation, and staging.
2. **Error String Format:** Exactly `f"Row {txn.date} '{txn.description}': {exc}"`.
3. **Loop Continuation:** A row exception does not halt the workflow; subsequent rows continue processing.
4. **Commit Eligibility:** Successfully staged rows before and after a failed row remain eligible for the final commit.
5. **Tolerant Parsing & Non-Fatal Row Errors:** Statements are parsed via `loader.load_records_tolerant(raw_bytes)`. Missing required columns fail the whole request with HTTP 422 (`CSVImportParseError`). Malformed rows during parsing (invalid dates, invalid decimal amounts, ragged rows) are captured non-fatally and recorded in `errors`, while valid rows proceed to the duplicate check and staging loop.

---

## 16. Commit Ownership & Commit-Failure Semantics

- **Commit Owner:** `CSVImportManager` executes a single final `db.commit()`.
- **Commit Failure:**
  - Located outside the per-row `try/except`.
  - A database commit failure propagates as an unhandled request exception (HTTP 500).
  - The request fails; it does **not** return HTTP 200 with an entry in `errors`.
  - PostgreSQL rolls back all staged transactions during session teardown (`get_db()`).
  - No partial persistence occurs.
- No `try/except` around `db.commit()` or retry logic is introduced.

---

## 17. Imported Counter Semantics

`imported += 1` increments immediately after `stage_csv_import_transaction` succeeds in staging the row. Because the endpoint returns HTTP 200 only after `db.commit()` succeeds, this reflects the total count of successfully committed new transactions.

---

## 18. Persistence Execution Shape

For $N$ parsed transactions resulting in $K$ duplicates and $M$ new transactions ($M = N - K$):

- **SELECT Operations:**
  - $1$ Account lookup (`SELECT accounts WHERE id = :id LIMIT 1`)
  - $N$ duplicate-existence lookups (`SELECT transactions WHERE ... LIMIT 1`)
- **Staging:**
  - $M$ `db.add()` calls staging records in memory
- **Flush / Write Operations:**
  - $M$ staged `INSERT` statements executed when `db.commit()` flushes the session
- **Transaction Completion:**
  - $1$ final `COMMIT`

*VBD Rule:* The $N+1$ query pattern is preserved without premature query batching or bulk insert optimizations.

---

## 19. Public HTTP Response Contract

Preserves [`schemas.CSVImportResult`](../../backend/schemas.py):
```python
class CSVImportResult(BaseModel):
    imported: int
    skipped: int
    errors: List[str]
```
Returns HTTP 200 OK for:
- normal imports;
- all rows skipped as duplicates;
- empty/header-only files (`imported=0, skipped=0, errors=[]`);
- imports with non-fatal row errors.

---

## 20. Characterization Safety Baseline

Pre-refactor safety baseline: **95 passed in 1.99s** (100% green).
Protected by [`tests/test_characterization_csv_import.py`](../../tests/test_characterization_csv_import.py) and [`tests/test_characterization_workflows.py`](../../tests/test_characterization_workflows.py):
1. Initial upload creates transactions (`imported=3, skipped=0`).
2. Exact re-upload skips all records (`imported=0, skipped=3`).
3. Partial overlap imports only new records.
4. Missing account returns HTTP 404 with exact detail.
5. Inactive accounts can receive CSV imports.
6. Unknown format returns HTTP 400 with exact detail.
7. Malformed CSV / missing columns returns HTTP 422 with parser detail.
8. Validation precedence: 404 > 400 > 422.
9. Intra-request identical rows both imported (`imported=2, skipped=0`).
10. Cross-account duplicate isolation (identical transaction on different account not skipped).
11. Description case sensitivity (`"GROCERY"` vs `"grocery"` treated as distinct).
12. Header-only CSV imports cleanly with zero counts.
13. Discover format end-to-end normalization, date parsing, and sign preservation.
14. Zero-amount transaction import.

---

## 21. Volatility Classification & Rejected Abstractions

### Observed Volatility:
- **Bank CSV Formats:** Isolated behind `BankStatementLoader`.
- **Confirmation Workflow Sequencing:** Isolated behind `CSVImportManager`.
- **SQLAlchemy Persistence Mechanics:** Isolated behind Account and Transaction ResourceAccess.

### Explicitly Rejected Abstractions:
- `DeduplicationEngine` or `TransactionMatchingEngine`.
- Strategy / scoring interfaces for duplicate matching.
- Fuzzy or hash-based deduplication.
- Configurable dedupe tolerance or policies.
- Generic ingestion framework combining CSV and Plaid.
- Dedicated hardcoded Python parser classes for hypothetical banks (arbitrary CSV variations are handled as configuration data via `MappedCSVFormatConfig` and `CSVFormat` records).
- Generic repositories or Unit of Work.
- Eager batch query or `ON CONFLICT` optimization.

---

## 22. Dependency Rules

### Allowed:
```text
Router -> CSVImportManager
CSVImportManager -> Account ResourceAccess
CSVImportManager -> Transaction ResourceAccess
CSVImportManager -> BankStatementLoader
CSVImportManager -> Session (as application context)
ResourceAccess -> SQLAlchemy / PostgreSQL
```

### Prohibited:
```text
CSVImportManager -> FastAPI
CSVImportManager -> HTTPException
CSVImportManager -> UploadFile
CSVImportManager -> Pydantic response schemas
BankStatementLoader -> SQLAlchemy
BankStatementLoader -> FastAPI
ResourceAccess -> CSVImportSummary
```
