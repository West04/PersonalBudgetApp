# Workflow Catalog

Document meaningful use-case sequences here. Do not add entries for trivial CRUD simply to make the catalog complete.

## Plaid public-token exchange

**Trigger:** `POST /plaid/exchange_public_token`

**Manager:** `PlaidAccountSyncManager.exchange_public_token`

```text
exchange public token via plaid_access
-> lookup or create PlaidItem via plaid_item_access
-> if new item created: Commit #1
-> fetch remote account snapshots via plaid_access
-> stage/update local accounts via account_access
-> Commit #2
-> return staged Account instances to Router for schema serialization
```

**Architecture boundary:** Router retains HTTP extraction, 422 validation, and response serialization only. Manager owns SDK coordination, multi-step staging, and two-commit transaction sequencing.

**Behavior constraint:** preserves token exchange, item creation/resolution, account sync, orphan item persistence on downstream failure, returned linked-account behavior, and existing error semantics. Slice 1b will address transaction atomicity.


## Plaid account sync

**Manager:** `PlaidAccountSyncManager`

```text
resolve Plaid item
-> decode stored access token
-> fetch remote account snapshots
-> stage/update local accounts
-> flush/commit
-> return sync result
```

## Plaid transaction sync

**Manager:** `PlaidTransactionSyncManager`

```text
resolve Plaid item
-> decode token
-> refresh/stage account snapshots
-> load categorization lookup
-> page /transactions/sync
-> process added/modified/removed events:
     lookup existing transaction (single event read)
     determine amount_changed
     reconciliation-conflict guard (blocks split deletion on reconciled mismatch)
     split existence check via split_access (when not in reconciliation conflict)
     if split and amount changed:
       stage split deletion via split_access
       expire ORM relationship collection (db.expire)
       reset parent state (category_id=None, category_source=None, is_reviewed=False)
     if not split:
       select effective merchant (overridden vs normalized)
       evaluate categorization rule via domain helpers (if eligible)
     stage transaction via transaction_access with explicit scalars & lookup state
     Manager db.commit() per event (or records/commits reconciliation warning)
-> persist cursor
-> finish current commit sequence
-> return sync result
```

**Architecture boundary:** `PlaidTransactionSyncManager` coordinates reconciliation conflict checking, split existence checking and invalidation via `split_access`, and categorization rule matching before delegating to `transaction_access.stage_or_update_plaid_transaction`. ResourceAccess performs entity staging without evaluating rules or calling other Accessors (`split_access` or `categorization_rule_access`).

Transaction granularity is a separate correctness concern; do not alter it during unrelated decomposition work.

## CSV import confirmation
 
**Manager:** `CSVImportManager`

```text
verify destination account
-> resolve statement loader (built-in registry vs custom format via csv_format_access)
-> parse tolerant records
-> load categorization inputs
-> for each valid row:
     detect duplicate
     normalize merchant
     determine categorization
     stage transaction
     collect row error if needed
-> commit batch
-> return import summary
```

**Architecture boundary:** Router handles multipart form extraction, invokes `CSVImportManager.confirm_csv_import`, and serializes the summary. `CSVImportManager` authoritatively validates account existence, resolves loader strategies, parses records, applies categorization rules via domain `match_merchant_rule`, and stages via `transaction_access.stage_csv_import_transaction`.

## CSV preview

**Manager:** `CSVImportManager.preview_csv_import`

```text
verify destination account
-> resolve statement loader (built-in registry vs custom format via csv_format_access)
-> decode raw bytes (utf-8-sig with latin-1 fallback)
-> iterate rows with 1-based indexing
-> normalize and transform row via loader
-> collect row errors non-fatally
-> return CSVPreviewSummary without database mutation
```

**Architecture boundary:** Router retains HTTP multipart upload handling, invokes `CSVImportManager.preview_csv_import`, and maps domain exceptions (`CSVImportAccountNotFoundError`, `CSVImportUnknownFormatError`, `CSVImportFormatNotFoundError`) to HTTP responses (404, 400). All parsing logic, loader resolution, and row error aggregation live inside `CSVImportManager`.

## Account reconciliation

**Trigger:** `GET /accounts/{id}/reconciliation`, `POST /accounts/{id}/reconciliation/complete`

**Manager:** `AccountReconciliationManager`

```text
load account via account_access
-> validate supported depository account type
-> load unreconciled transactions via transaction_access
-> compute reconciliation state in Engine (domain/account_reconciliation.py)
-> on completion validate balanced state (difference == 0.00)
-> mark participating cleared transactions reconciled via transaction_access
-> update account reconciliation watermark via account_access
-> commit single atomic transaction (or rollback on failure)
-> return refreshed summary result
```

**Architecture boundary:** Router retains HTTP parameter extraction and response serialization, catching application exceptions (`AccountNotFoundError` -> 404, `UnsupportedAccountTypeError` -> 400, `UnbalancedReconciliationError` -> 400) and translating them to HTTP responses. `AccountReconciliationManager` coordinates the workflow and atomic transaction boundary without depending on FastAPI or transport exceptions. Pure domain engine `compute_reconciliation_state` performs cleared balance and difference calculations.

## Transaction split / unsplit

```text
load/validate parent transaction
-> validate split allocation business invariants
-> verify target categories
-> coordinate split persistence and parent category state
-> update ML training revision when required
-> commit/rollback
```

## Recurring detection and synchronization

```text
load eligible transaction history
-> map to pure detection inputs
-> detect recurring series in Engine
-> persist detected series
-> remove stale auto-detected items
-> commit/rollback
-> return current persisted view
```

Simple list/confirm/dismiss operations do not by themselves justify additional Managers.

## ML retraining

```text
load metadata/training examples
-> validate data sufficiency
-> train candidate + baseline
-> evaluate candidate
-> apply activation policy
-> if activated, write/replace artifact
-> update metadata
-> commit/rollback and cleanup
```

## Retroactive categorization-rule application

```text
load rule
-> derive canonical merchant key
-> preview count OR update matching uncategorized transactions
-> commit/rollback for mutation
```

Rule-matching policy used during ingestion must have one authoritative business implementation rather than copies inside ResourceAccess.

## Manual transaction creation

**Trigger:** `POST /transactions/`

**Manager:** `ManualTransactionManager.create_transaction`

```text
resolve merchant identity:
  if explicit nonblank merchant: stripped merchant, is_merchant_overridden=True
  else: normalized merchant via domain normalize_merchant, is_merchant_overridden=False
-> resolve category and ML revision:
     if explicit category provided:
       assign category_id, category_source="manual", increment ML training revision via ml_model_access
     else if merchant present:
       lookup rule via categorization_rule_access.get_rule_by_merchant
       if rule matched: assign rule category_id, category_source="rule", no ML revision bump
       else: category_id=None, category_source=None, no ML revision bump
     else:
       category_id=None, category_source=None, no ML revision bump
-> stage transaction via transaction_access.stage_manual_transaction (pure db.add, zero cross-accessor dependencies)
-> commit single transaction boundary (committing Transaction and ML revision increment if staged)
-> refresh transaction
-> return transaction to Router for schema serialization
```

**Architecture boundary:** Router retains HTTP parsing, request validation, and serialization. `ManualTransactionManager` coordinates merchant resolution, categorization precedence, ML revision staging, and transaction boundary ownership. `transaction_access.stage_manual_transaction` remains pure persistence with zero cross-accessor calls and zero commits.

## Manual transaction update

**Trigger:** `PUT /transactions/{transaction_id}`

**Manager:** `ManualTransactionManager.update_transaction`

```text
load transaction via transaction_access.get_transaction_by_id
-> if missing: return None immediately (Presentation maps to 404)
-> check split allocations via split_access.transaction_has_splits
-> if split, evaluate split guards strictly in order:
     if amount changed: raise ValueError("Cannot modify amount of a split transaction...")
     if category_id present in payload: raise ValueError("Cannot directly assign a category to a split transaction...")
     if is_transfer is True: raise ValueError("Cannot mark a split transaction as a transfer.")
-> if reconciled, evaluate financial guards:
     prohibit changes to amount, date, or account_id (supplying identical existing value permitted)
-> resolve merchant and description:
     if merchant provided: stripped merchant, is_merchant_overridden=True (or reset to False if blank/None)
     elif description provided and not overridden: renormalize merchant
-> resolve category mutation and ML revision:
     if category_id in payload:
       if new category != old category:
         if new category is not None:
           assign category_id, category_source="manual", increment ML revision via ml_model_access (flushed to session)
         else:
           clear category_id and category_source
-> apply generic field assignments for remaining payload fields
-> if uncategorized, non-split, category not in payload, and merchant present:
     lookup rule via categorization_rule_access.get_rule_by_merchant
     if matched: assign rule category_id, category_source="rule" (no ML revision bump)
-> stage transaction via db.add
-> commit single transaction boundary (committing Transaction and ML revision increment if staged)
-> refresh transaction
-> return transaction to Router for schema serialization
```

**Architecture boundary:** Router retains HTTP parameter parsing, request validation, and status code mapping (ValueError -> 400, None -> 404). `ManualTransactionManager` coordinates split guards, reconciliation guards, merchant resolution, category resolution, rule fallback, and transaction boundary ownership. `transaction_access` contains zero cross-accessor calls and zero business guard logic.

