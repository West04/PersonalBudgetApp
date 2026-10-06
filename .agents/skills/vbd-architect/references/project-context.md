# Budget App Project Context

Reference architecture: Presentation/FastAPI -> meaningful Manager -> Engine and/or concrete ResourceAccess -> resource. Direct Presentation -> ResourceAccess is allowed for simple CRUD.

Managers may receive SQLAlchemy Session. Do not add Unit of Work or generic repositories solely to hide SQLAlchemy.

Strong observed Engine/policy areas: budgeting, account reconciliation, credit-card calculations, merchant normalization, ML categorization, transfer matching, recurring detection, split validation.

Observed integration volatility: CSV parser formats/sign/date behavior; Plaid SDK access; separate raw Plaid transaction-sync HTTP caused by demonstrated SDK/cursor behavior; PostgreSQL-specific queries/aggregation.

Known structural hotspots from source audit:

- live Plaid public-token exchange workflow remains in Router and legacy `crud/plaid.py`
- upload Router owns loader/format/preview/inspect sequencing
- Accessor-to-Accessor workflow coupling exists, especially in `transaction_access.py`
- categorization matching is duplicated inside ResourceAccess
- some Managers know FastAPI/Pydantic transport concepts
- some Manager DTOs duplicate ORM/Pydantic fields
- exactly one current Manager-to-Manager edge was observed: DashboardSummaryManager -> BudgetSummaryManager

Explicitly speculative until requirements change: alternate DB engines, alternative bank providers, multi-currency, GraphQL/gRPC, generic message bus, generic rule DSL, multi-user auth/tenancy, OFX/QIF.
