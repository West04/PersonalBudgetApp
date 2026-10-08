# Budget App Refactor Context

## Current architecture status
- structural VBD program complete;
- established boundaries are stable: Presentation -> Manager -> Engine / Accessor -> Resource;
- previously targeted hotspots (Plaid token exchange, transaction_access coupling, CSV upload sequencing, Manager transport coupling) are resolved;
- no known high-value boundary violation is open;
- prefer no architectural change unless new observed volatility appears.

## Resolved hardening invariants
- Transaction.description is TEXT NOT NULL; "" represents missing narrative.
- Non-empty category groups cannot be deleted (HTTP 400).
- Category deletion cascade preserves transactions as uncategorized, deletes budgets and rules, and blocks on split references.
- Plaid access tokens use authenticated enc:v1: Fernet encryption.
- Credit-card metrics use point-in-time balance_owed up to effective cutoff, gross positive non-transfer charges, and negative transfer payments.
- Transfer candidate matching is deterministic closest-first greedy suggestion matching.

## Future / non-blocking backlog
- Candidate Phase 13: Financial Depth (Savings Goals, Transaction Tags, Net Worth Tracking, Reporting & Analytics, Cash Flow Forecasting).
- Administrative UI workflow for reconciled Plaid corrections.
- Query batching optimizations if future profiling justifies it.

## Explicitly rejected speculative drivers
- alternate DB engines, Unit of Work / generic repositories solely to hide SQLAlchemy Session.
- hypothetical bank-provider abstractions or multi-currency.
- generic message buses or rule DSLs.
- GraphQL/gRPC or speculative auth/tenancy architecture.
- one Manager per endpoint or field-for-field DTO layers solely for layering.
