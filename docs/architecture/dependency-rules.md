# VBD Dependency Rules

These rules are intended to be enforceable by humans and code agents.

## Allowed by default

| Caller | Callee | Rule |
|---|---|---|
| Presentation | Manager | Preferred for meaningful use cases |
| Presentation | ResourceAccess | Allowed for genuinely simple CRUD or atomic access |
| Manager | Engine | Allowed |
| Manager | ResourceAccess | Allowed |
| Manager | small pure helper/value | Allowed when it does not create a fake component |
| ResourceAccess | Resource | Required purpose of ResourceAccess |
| Engine | pure domain values/helpers | Allowed |

## Prohibited by default

- `Engine -> Manager`
- `Engine -> ResourceAccess`
- `Engine -> SQLAlchemy/ORM/Session`
- `Engine -> FastAPI/Pydantic transport schemas`
- `Engine -> external SDK/HTTP/filesystem/environment`
- `ResourceAccess -> Manager`
- `ResourceAccess -> ResourceAccess` when it represents cross-resource sequencing
- `ResourceAccess -> business Engine` to decide business behavior during persistence
- `Manager -> FastAPI.HTTPException`
- `Manager -> HTTP status codes`
- `Presentation -> raw SQLAlchemy queries`
- `Presentation -> database commit/rollback` for a multi-step business workflow
- `Presentation -> external SDK workflow orchestration`

## Clarifications

### ResourceAccess-to-ResourceAccess

A helper call is not automatically forbidden merely because two modules live under `access/`; the architectural test is responsibility. If one ResourceAccess invokes another because a business operation spans multiple resources, move that sequencing to a Manager or redesign the atomic ResourceAccess operation. Do not hide a workflow behind dynamic imports.

### Commits

For multi-step workflows, the Manager should normally own commit/rollback boundaries. A standalone CRUD Accessor may commit when the operation is intentionally an atomic Router -> Accessor path. Do not create a Manager solely to centralize every commit.

### Presentation schemas

Managers should not depend on FastAPI transport errors. Pydantic response models should also remain at Presentation unless a type has genuine application/domain semantics. Do not replace every Pydantic type with a duplicate Manager DTO.

### Manager-to-Manager calls

Do not ban these mechanically. Treat them as a review trigger. Prefer a Manager to coordinate Engines and ResourceAccess directly when two Managers are merely endpoint/screen subdivisions. Preserve a Manager-to-Manager call only when the called Manager is itself a stable reusable use-case boundary and the composition does not create cyclic or screen-driven decomposition.

## Current known violations to remove incrementally

The source evidence audit originally reported:

- live workflow orchestration in `backend/routers/plaid.py::exchange_public_token` (RESOLVED in Slice 1: delegated to `PlaidAccountSyncManager.exchange_public_token`)
- upload preview/loader sequencing in `backend/routers/upload.py` (RESOLVED in Slice 4: delegated to `CSVImportManager`)
- Accessor-to-Accessor calls involving `transaction_access.py`, `split_access.py`, `categorization_rule_access.py`, `ml_model_access.py`, and `category_access.py` (RESOLVED for transaction_access in Slice 2: Slice 2a removed `categorization_rule_access` from CSV import; Slice 2b removed `categorization_rule_access` from Plaid sync; Slice 2c removed `split_access` from Plaid sync; Slice 2d removed `categorization_rule_access` and `ml_model_access` from manual create; and Slice 2e removed `split_access`, `ml_model_access`, and `categorization_rule_access` from manual update via `ManualTransactionManager.update_transaction`)
- categorization matching logic duplicated in `transaction_access.py` (PARTIALLY RESOLVED in Slice 2a: CSV import inlined matching replaced by domain `match_merchant_rule` in `CSVImportManager`; and Slice 2b: Plaid sync inlined matching replaced by domain `match_merchant_rule` in `PlaidTransactionSyncManager`)
- FastAPI/Pydantic coupling in some Managers (PARTIALLY RESOLVED in Slice 5: FastAPI HTTPException and status coupling removed from AccountReconciliationManager; plain application exceptions mapped in accounts Router)
- one current Manager-to-Manager call: `DashboardSummaryManager -> BudgetSummaryManager`

Treat the audit as evidence, not as an instruction to rewrite all of these at once.
