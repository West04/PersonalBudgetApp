# Volatility Registry

This registry records which sources of change currently justify architecture. Update it only when source evidence or the confirmed roadmap changes.

| Responsibility | Class | Evidence | Current/desired boundary |
|---|---|---|---|
| Zero-based budget calculations | OBSERVED | Multiple accounting calculations and reporting rules used by budget/dashboard workflows | Budget Engine |
| Account reconciliation calculation | OBSERVED | Cleared balance, difference, balanced-state rules | Reconciliation Engine |
| Transfer candidate matching | OBSERVED | Matching heuristic across accounts, amount and date window | Reconciliation Engine |
| Credit-card calculations | OBSERVED | Balance owed, monthly charges/payments, transfer behavior | Credit-card Engine |
| Merchant normalization | OBSERVED | Multiple regex/cleanup heuristics and multiple ingestion callers | Domain policy/Engine |
| ML categorization | OBSERVED | Training, baseline, activation gates, inference thresholds | ML Engine + Manager + concrete storage access |
| Recurring detection | OBSERVED | Cadence ranges, stability thresholds, projection heuristics | Recurring Engine |
| Transaction split validation | OBSERVED | exact-sum, sign, non-zero, minimum-line invariants | Split Engine |
| CSV statement parsing | OBSERVED | USAA, Discover, mapped formats; date/sign differences | Parser boundary |
| User-defined CSV formats | OBSERVED | persisted format configuration and mappings | Concrete CSV format access + parser config |
| Plaid account/link access | OBSERVED | official Plaid SDK integration | Plaid SDK ResourceAccess |
| Plaid transaction-sync protocol | OBSERVED | raw HTTP exists because SDK cursor behavior proved problematic | Dedicated raw-HTTP ResourceAccess |
| PostgreSQL persistence | OBSERVED | SQLAlchemy ORM, joins, aggregation, transactional persistence | Concrete ResourceAccess |
| Dashboard composition | OBSERVED | composite read model used by dashboard and changes separately from core calculations | Review as application composition; keep only if sequence boundary remains justified |
| Account summaries | OBSERVED | manual depository balance derivation differs from stored/provider balances | Manager/use-case + domain helper as currently justified |
| Categorization rule matching | OBSERVED | same policy needed in CSV, Plaid, and ML-related flows; matching duplicated in ResourceAccess | One authoritative domain policy/activity |
| Alternative bank aggregators | SPECULATIVE | only Plaid exists; no confirmed roadmap requirement | No provider interface |
| Alternative database engines | SPECULATIVE | no confirmed substitution requirement | No DB port/repository abstraction |
| Multi-currency/FX | SPECULATIVE | no confirmed requirement | No currency architecture |
| Generic rule DSL | SPECULATIVE | current rules are exact canonical merchant -> category | No generic rule engine |
| GraphQL/gRPC | SPECULATIVE | FastAPI HTTP API is the only host | No transport abstraction |
| Multi-user/auth tenancy | SPECULATIVE | personal single-user app | No tenancy/auth architecture until planned |
| OFX/QIF import | SPECULATIVE | no confirmed requirement | No import-provider framework |

## Rule for changes

Before creating an interface, base class, strategy, factory, configurable provider, DTO layer, Manager, Engine, or new Accessor boundary, add or update a registry entry and cite concrete evidence. A `SPECULATIVE` row cannot be used as architectural justification.
