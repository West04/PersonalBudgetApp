# VBD Refactor Roadmap

This roadmap is structural. It does not replace the product roadmap. Perform one slice at a time, run the full suite, review, and commit before continuing.

## Slice 1 — Plaid public-token exchange boundary [COMPLETED]

**Problem:** meaningful workflow, SDK construction, legacy CRUD, and commit exist in Presentation.

**Target:** Router -> Plaid Manager (`PlaidAccountSyncManager.exchange_public_token`) -> concrete Plaid/persistence ResourceAccess (`plaid_access`, `plaid_item_access`, `account_access`).

**Behavior preserved:** public token exchange, Plaid item semantics, two-commit sequencing, orphan item persistence on downstream failure, account synchronization, response/error contract.

**Exit criteria met:**
- no live `crud/plaid.py` dependency (file and package retired);
- Router owns no workflow commit or Plaid SDK orchestration;
- Characterization suite (6 tests) and full test suite (952 tests) green;
- Architecture documentation updated (`component-map.md`, `workflow-catalog.md`, `dependency-rules.md`, `refactor-roadmap.md`).

**Follow-up (Slice 1b):** Atomicity refactor to collapse the two-commit sequence into a single atomic transaction.

## Slice 2 — Transaction ResourceAccess cross-dependencies

**Problem:** `transaction_access.py` coordinates split, categorization-rule, and ML metadata Accessors.

**Target:** identify each hidden use-case sequence and move sequencing to existing justified Managers or the smallest new Manager boundary proven necessary. Keep atomic persistence operations concrete.

### Slice 2a — CSV import categorization rule decoupling [COMPLETED]
- Decoupled `stage_csv_import_transaction` from `categorization_rule_access` and removed inlined rule-matching logic.
- `CSVImportManager` now authoritatively resolves categorization rules via pure domain helper `match_merchant_rule(merchant, rules_lookup)` and passes resolved scalars `category_id` and `category_source` to `stage_csv_import_transaction`.
- Exit criteria met: zero cross-accessor calls between `stage_csv_import_transaction` and `categorization_rule_access`; `rules_lookup` removed from `stage_csv_import_transaction`; characterization suite and full test suite (953 tests) green.

### Slice 2b — Plaid sync categorization rule decoupling [COMPLETED]
- Decoupled `stage_or_update_plaid_transaction` from `categorization_rule_access` and removed inlined rule-matching logic.
- `PlaidTransactionSyncManager._process_upsert_event` now authoritatively resolves categorization rules via pure domain helpers `is_eligible_for_rule` and `match_merchant_rule(effective_merchant, rules_lookup)` with inline effective merchant selection (`existing_tx.merchant` if overridden else `normalized_merchant`).
- Introduced `_EXISTING_TRANSACTION_NOT_PROVIDED` sentinel in `transaction_access.py` to distinguish known-absent (`existing_transaction=None`) from omitted parameter, guaranteeing exactly one lookup per event while preserving 100% backwards compatibility for legacy/direct callers.
- Exit criteria met: zero cross-accessor calls between `stage_or_update_plaid_transaction` and `categorization_rule_access`; `rules_lookup` removed from `stage_or_update_plaid_transaction`; characterization suite and full test suite (956 tests) green.

### Slice 2c — Plaid sync split invalidation decoupling [COMPLETED]
- Decoupled `stage_or_update_plaid_transaction` from `split_access` and removed split invalidation orchestration from `transaction_access.py`.
- `PlaidTransactionSyncManager._process_upsert_event` now authoritatively coordinates the ledger-first split invalidation workflow:
  1. Computes `amount_changed` and evaluates reconciliation conflict gate first.
  2. If not a reconciliation conflict, checks split existence via `split_access.transaction_has_splits(db, existing_tx.transaction_id)`.
  3. If split and amount changed: deletes splits via `split_access.stage_delete_splits(db, existing_tx.transaction_id)`, invalidates ORM collection via `db.expire(existing_tx, ["splits"])`, and resets parent state (`category_id=None`, `category_source=None`, `is_reviewed=False`).
  4. Suppresses rule categorization for transactions known to be split during the event.
  5. Stages entity update via `stage_or_update_plaid_transaction` and commits the transaction boundary.
- Reconciliation conflict ownership remained authoritative inside `transaction_access.stage_or_update_plaid_transaction` (guaranteeing zero split deletions before conflict rejection, staging markers, and raising `PlaidReconciliationConflictError`).
- Exit criteria met: zero cross-accessor calls between `stage_or_update_plaid_transaction` and `split_access`; characterization suite (21 tests in `test_plaid_split_conflict.py`) and full test suite (966 tests) green.

### Slice 2d — Manual transaction create decoupling [COMPLETED]
- Decoupled manual transaction creation from `transaction_access.py` into a new narrowly scoped `ManualTransactionManager.create_transaction`.
- `ManualTransactionManager.create_transaction` authoritatively coordinates:
  1. Resolving merchant identity (stripping explicit merchant and setting `is_merchant_overridden=True`, or normalizing description via domain `normalize_merchant` and setting `is_merchant_overridden=False`).
  2. Resolving category precedence: explicit category assigns `category_source="manual"` and stages ML revision bump via `ml_model_access.increment_training_revision`; otherwise evaluates merchant rule fallback via `categorization_rule_access.get_rule_by_merchant` (setting `category_source="rule"` without ML revision bump); otherwise unassigned.
  3. Staging entity via `transaction_access.stage_manual_transaction` with zero cross-accessor dependencies and no commit/refresh.
  4. Owning the atomic single-commit and refresh transaction boundary.
- Replaced `transaction_access.create_manual_transaction` with pure `stage_manual_transaction` (db.add only, zero cross-accessor calls, zero commit/refresh).
- Permanently deleted `create_manual_transaction` with zero `ResourceAccess -> Manager` backward compatibility wrappers.
- Migrated all test callers (unit characterization tests moved to `ManualTransactionManager`, fixture callers updated to `stage_manual_transaction` + commit).
- Exit criteria met: zero cross-accessor calls from `stage_manual_transaction`; `POST /transactions/` routed to `ManualTransactionManager`; characterization suite (7 unit tests in `test_manager_manual_transaction.py`, 85 targeted tests) and full test suite (981 tests) green.

### Slice 2e — Manual transaction update decoupling [COMPLETED]
- Decoupled manual transaction update workflow from `transaction_access.py` into `ManualTransactionManager.update_transaction`.
- `ManualTransactionManager.update_transaction` authoritatively coordinates:
  1. Transaction lookup via `transaction_access.get_transaction_by_id`, returning `None` immediately if missing.
  2. Split detection via `split_access.transaction_has_splits`.
  3. Split mutation guards strictly in precedence order: rejecting amount modification, direct category assignment, and transfer conversion (`is_transfer=True`).
  4. Reconciled financial-field guards: rejecting changes to `amount`, `date`, or `account_id` when `is_reconciled=True`, while permitting unchanged values.
  5. Merchant override and description normalization preserving existing precedence and timing.
  6. Category mutation and ML revision bump: explicit category assigns `category_source="manual"` and flushes ML revision increment before subsequent assignments; same category leaves ML revision unchanged; explicit `None` clears category and source without rule fallback.
  7. Generic field assignments for remaining supplied fields.
  8. Rule fallback for uncategorized non-split transactions where category was not in payload.
  9. Owning single atomic commit and refresh boundary.
- Permanently deleted `transaction_access.update_manual_transaction` with zero `ResourceAccess -> Manager` backward compatibility wrappers.
- Completely eliminated all remaining imports of `ml_model_access` and `categorization_rule_access` from `transaction_access.py`.
- Migrated all 18 test call sites across 5 test files to `ManualTransactionManager.update_transaction`.
- Exit criteria met: zero cross-accessor calls from update workflow in `transaction_access.py`; `PUT /transactions/{transaction_id}` routed to `ManualTransactionManager`; characterization suite (17 tests in `test_manager_manual_transaction.py`, 87 targeted tests) and full test suite green.

## Slice 3 — Categorization policy authority [COMPLETED]

**Problem:** rule matching is duplicated/inlined in ResourceAccess while domain categorization functions exist.

**Target:** one authoritative pure categorization policy/activity; Managers decide when it is applied; ResourceAccess persists the selected result.

**Exit criteria met:**
- zero duplicated business rule matching in `transaction_access.py`;
- ingestion and mutation workflows (`CSVImportManager`, `PlaidTransactionSyncManager`, `ManualTransactionManager`) authoritatively decide categorization rules via pure domain helpers;
- `transaction_access.py` persists selected scalars with zero cross-accessor dependencies; full test suite green.

## Slice 4 — CSV/upload application boundary [COMPLETED]

**Problem:** upload Router owned loader resolution, format DB lookup, parser construction, inspect/preview sequencing, and redundant account validation.

**Target:** Presentation handles HTTP/upload mechanics; `CSVImportManager` owns format resolution, account verification, preview sequencing, and confirm import workflow.

**Exit criteria met:**
- Router contains zero database lookups, zero loader strategy construction, zero byte decoding, and zero row parsing loops;
- `CSVImportManager` authoritatively coordinates destination account validation, format identifier resolution (built-ins vs custom UUID via `csv_format_access`), statement loader construction, and preview row parsing / error aggregation;
- Application exceptions (`CSVImportAccountNotFoundError`, `CSVImportUnknownFormatError`, `CSVImportFormatNotFoundError`, `CSVImportParseError`) mapped in Router to existing HTTP status codes (400, 404, 422);
- Characterization suite (109 tests across preview, confirm, format resolution, and categorization) and full test suite (971 tests) green.

### Slice 4b — Move CSV Inspection Workflow out of Presentation [COMPLETED]
- Decoupled CSV inspection and format auto-detection from `backend/routers/upload.py::inspect_csv` into `CSVImportManager.inspect_csv_upload`.
- `CSVImportManager.inspect_csv_upload` authoritatively coordinates:
  1. Raw byte decoding via `utf-8-sig` (preserving BOM stripping and raising plain application exception `CSVInspectError` on `UnicodeDecodeError`).
  2. Emptiness and whitespace validation, raising `CSVInspectError("CSV file is empty or contains no header row")`.
  3. Header and sample row parsing via `io.StringIO` and `csv.reader`, validating non-empty headers and collecting up to 3 bounded sample rows positionally without dictionary key-collision loss or padding.
  4. Candidate assembly: combining `BUILTIN_FORMAT_MATCHES` (`USAA`, `Discover`) followed by persisted custom formats from `csv_format_access.list_custom_formats(db)` converted via `csv_format_access.csv_format_to_match_definition`.
  5. Format detection via pure domain `detect_csv_format(headers=headers, formats=candidates)`.
  6. Direct construction and return of `schemas.CSVInspectResponse` without duplicate DTO ceremony.
- Presentation boundary in `backend/routers/upload.py` pruned of `csv`, `io`, `BUILTIN_FORMAT_MATCHES`, and `detect_csv_format`. Router retains only multipart stream reading (`_read_upload`), delegation to `inspect_csv_upload`, and mapping `CSVInspectError` to HTTP 422 Unprocessable Entity.
- Preserved zero-account, zero-loader-resolution, and zero-database-mutation invariants.
- Exit criteria met: zero CSV parsing or format detection logic in `backend/routers/upload.py`; characterization suite (35 tests in `test_manager_csv_import.py`, 21 tests in `test_integration_csv_inspect.py`, 133 focused CSV tests) and full test suite (1,005 tests) green.

## Slice 5 — Remove Presentation coupling from Managers [COMPLETED]

**Problem:** some Managers raise `HTTPException` or return Pydantic transport schemas.

**Target:** application/domain exceptions or meaningful result types; Router maps failures/results to HTTP/Pydantic.

**Guardrail:** do not create field-for-field Manager DTOs merely to remove Pydantic.

### Slice 5a — Remove FastAPI coupling from AccountReconciliationManager [COMPLETED]
- Removed `fastapi.HTTPException` and `fastapi.status` dependencies from `backend/managers/account_reconciliation_manager.py`.
- Introduced plain, localized application exceptions: `AccountNotFoundError`, `UnsupportedAccountTypeError`, and `UnbalancedReconciliationError`.
- Updated `backend/routers/accounts.py` (`get_account_reconciliation` and `complete_account_reconciliation`) to catch application exceptions and map them to HTTP 404/400 preserving exact detail strings and status codes.
- Preserved Pydantic return models (`schemas.AccountReconciliationSummary`, `schemas.ReconciliationTransactionRead`) per guardrail against duplicate DTO ceremony.
- Preserved exact reconciliation domain math, baseline derivation, transaction filtering, and atomic single-commit completion semantics.
- Exit criteria met: zero `fastapi` references across all managers in `backend/managers/`; full test suite green.

## Slice 6 — Manager topology review [COMPLETED]

Audited the summary family and the single `DashboardSummaryManager -> BudgetSummaryManager` call. Confirmed that all 13 managers orchestrate demonstrated multi-step workflows. No manager-merging or artificial splitting is warranted.

## Slice 7 — DTO/contract cleanup [COMPLETED]

Audited data transfer boundaries. Redundant DTO layers were rejected per ADR-002 and VBD principles; meaningful calculation results (`CreditCardSummaryResult`, `TransferCandidateItem`, `CSVInspectResponse`) are retained.

## Slice 8 — Documentation and architecture conformance [COMPLETED]

All architecture documentation, known invariants, and safety matrices synchronized with actual repository source and test suite. Stopping condition reached.

## Per-slice required record

For each slice, record:

- current workflow and dependencies
- volatility evidence
- classification of each moved responsibility
- exact intended dependency change
- behavior explicitly preserved
- tests run
- files changed
- docs/ADRs changed
- unresolved issues intentionally left untouched
