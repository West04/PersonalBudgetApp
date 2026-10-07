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
resolve/receive statement parser
-> verify destination account
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

**Architecture boundary:** `CSVImportManager` determines categorization using domain helper `match_merchant_rule` before delegating to `transaction_access.stage_csv_import_transaction`. ResourceAccess performs atomic staging without evaluating rules or calling other Accessors.

**Migration concern:** loader resolution and a redundant account check currently live in Presentation.

## CSV inspect/preview — migration target

Current Presentation performs format sniffing, custom-format retrieval, loader selection/construction, row parsing, and error aggregation. Move application/parser sequencing out of the Router while leaving HTTP file extraction and response mapping in Presentation.

## Account reconciliation

```text
load account
-> validate supported account type
-> load unreconciled transactions
-> compute reconciliation state in Engine
-> on completion validate balanced state
-> mark participating transactions reconciled
-> update account reconciliation watermark
-> commit/rollback
-> return refreshed result
```

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
