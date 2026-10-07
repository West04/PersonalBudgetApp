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

### Remaining in Slice 2 / Slice 3:
- Manual transaction creation/update policy concerns (unresolved future slices; no generic TransactionManager).

## Slice 3 — Categorization policy authority

**Problem:** rule matching is duplicated/inlined in ResourceAccess while domain categorization functions exist.

**Target:** one authoritative pure categorization policy/activity; Managers decide when it is applied; ResourceAccess persists the selected result.

**Exit criteria:** no duplicated business rule matching in `transaction_access.py`; ingestion flows use the authoritative policy.

## Slice 4 — CSV/upload application boundary [COMPLETED]

**Problem:** upload Router owned loader resolution, format DB lookup, parser construction, inspect/preview sequencing, and redundant account validation.

**Target:** Presentation handles HTTP/upload mechanics; `CSVImportManager` owns format resolution, account verification, preview sequencing, and confirm import workflow.

**Exit criteria met:**
- Router contains zero database lookups, zero loader strategy construction, zero byte decoding, and zero row parsing loops;
- `CSVImportManager` authoritatively coordinates destination account validation, format identifier resolution (built-ins vs custom UUID via `csv_format_access`), statement loader construction, and preview row parsing / error aggregation;
- Application exceptions (`CSVImportAccountNotFoundError`, `CSVImportUnknownFormatError`, `CSVImportFormatNotFoundError`, `CSVImportParseError`) mapped in Router to existing HTTP status codes (400, 404, 422);
- Characterization suite (109 tests across preview, confirm, format resolution, and categorization) and full test suite (971 tests) green.

## Slice 5 — Remove Presentation coupling from Managers

**Problem:** some Managers raise `HTTPException` or return Pydantic transport schemas.

**Target:** application/domain exceptions or meaningful result types; Router maps failures/results to HTTP/Pydantic.

**Guardrail:** do not create field-for-field Manager DTOs merely to remove Pydantic.

### Slice 5a — Remove FastAPI coupling from AccountReconciliationManager [COMPLETED]
- Removed `fastapi.HTTPException` and `fastapi.status` dependencies from `backend/managers/account_reconciliation_manager.py`.
- Introduced plain, localized application exceptions: `AccountNotFoundError`, `UnsupportedAccountTypeError`, and `UnbalancedReconciliationError`.
- Updated `backend/routers/accounts.py` (`get_account_reconciliation` and `complete_account_reconciliation`) to catch application exceptions and map them to HTTP 404/400 preserving exact detail strings and status codes.
- Preserved Pydantic return models (`schemas.AccountReconciliationSummary`, `schemas.ReconciliationTransactionRead`) per guardrail against duplicate DTO ceremony.
- Preserved exact reconciliation domain math, baseline derivation, transaction filtering, and atomic single-commit completion semantics.
- Exit criteria met: zero `fastapi` references in `account_reconciliation_manager.py`; Manager unit tests assert application exceptions; integration suite asserts exact HTTP contract; full test suite (974 tests) green.

## Slice 6 — Manager topology review

Re-evaluate the summary family and the single `DashboardSummaryManager -> BudgetSummaryManager` call after boundary leaks are fixed. Merge or retain Managers only based on demonstrated sequencing volatility, not a target count.

## Slice 7 — DTO/contract cleanup

Remove intermediate DTOs that duplicate ORM/Pydantic representations and protect no independent semantics. Retain meaningful results such as budget calculation results, import summaries, sync results, and other types with domain/application meaning.

## Slice 8 — Documentation and architecture conformance

Regenerate/verify the source dependency graph, reconcile `component-map.md` and `workflow-catalog.md`, and archive superseded architecture statements. Current source behavior and intended constraints must no longer contradict silently.

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
