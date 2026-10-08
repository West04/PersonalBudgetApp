# Budget App Project Context

Reference architecture: Presentation/FastAPI -> meaningful Manager -> Engine and/or concrete ResourceAccess -> resource. Direct Presentation -> ResourceAccess is allowed for simple CRUD.

Managers may receive SQLAlchemy Session. Do not add Unit of Work or generic repositories solely to hide SQLAlchemy.

Strong observed Engine/policy areas: budgeting, account reconciliation, credit-card calculations, merchant normalization, ML categorization, transfer matching, recurring detection, split validation.

Observed integration volatility: CSV parser formats/sign/date behavior; Plaid SDK access; separate raw Plaid transaction-sync HTTP caused by demonstrated SDK/cursor behavior; PostgreSQL-specific queries/aggregation.

Current architecture status:
- structural VBD program complete;
- established boundaries are stable: Presentation -> Manager -> Engine / Accessor -> Resource;
- previously identified structural hotspots (Plaid public token workflow, upload sequencing, transaction_access cross-calls, categorization policy authority, and Manager transport coupling) have all been resolved;
- no known high-value boundary violation is open;
- prefer no architectural change unless new observed volatility appears.

Resolved hardening decisions:
- Transaction.description is TEXT NOT NULL; "" represents missing text.
- Non-empty category-group deletion is rejected with HTTP 400.
- Category deletion preserves transactions as uncategorized, cascades budgets and rules, and blocks on splits.
- Plaid access tokens use authenticated enc:v1: Fernet encryption.
- Credit-card metrics enforce point-in-time balance, gross charges, transfer-only payments, and effective cutoff.
- Transfer candidate matching uses deterministic closest-first greedy suggestion matching.

Future / non-blocking items:
- Candidate Phase 13: Financial Depth (Savings Goals, Tags, Net Worth, Reporting, Forecasting).
- Administrative UI for reconciled Plaid corrections.
- Query batching optimizations if future profiling justifies it.

Explicitly speculative until requirements change: alternate DB engines, alternative bank providers, multi-currency, GraphQL/gRPC, generic message bus, generic rule DSL, multi-user auth/tenancy, OFX/QIF.
