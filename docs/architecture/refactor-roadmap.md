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

**Exit criteria:** no ResourceAccess-to-ResourceAccess workflow chaining for the addressed operations; behavior unchanged.

## Slice 3 — Categorization policy authority

**Problem:** rule matching is duplicated/inlined in ResourceAccess while domain categorization functions exist.

**Target:** one authoritative pure categorization policy/activity; Managers decide when it is applied; ResourceAccess persists the selected result.

**Exit criteria:** no duplicated business rule matching in `transaction_access.py`; ingestion flows use the authoritative policy.

## Slice 4 — CSV/upload application boundary

**Problem:** upload Router owns loader resolution, format DB lookup, parser construction, inspect/preview sequencing, and redundant account validation.

**Target:** Presentation handles HTTP/upload mechanics; Manager/application/parser boundary handles format/parser/use-case sequencing.

**Exit criteria:** Router contains no application parsing loop or persisted-format-driven construction; preview/confirm behavior remains characterized and green.

## Slice 5 — Remove Presentation coupling from Managers

**Problem:** some Managers raise `HTTPException` or return Pydantic transport schemas.

**Target:** application/domain exceptions or meaningful result types; Router maps failures/results to HTTP/Pydantic.

**Guardrail:** do not create field-for-field Manager DTOs merely to remove Pydantic.

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
