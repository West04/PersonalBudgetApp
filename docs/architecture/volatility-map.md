# Volatility Map & Decomposition Strategy

## 1. Overview & Core Principles

Rather than organizing the codebase mechanically around functional entities ("budgets", "categories", "transactions") or layering every endpoint identically, this architecture decomposes the system along **observed, independent axes of volatility**.

### Architectural Invariants:
1. **Volatility-Driven Boundaries:** Components exist only to protect against demonstrated, independent reasons to change.
2. **Workflow Managers:** A Manager is justified strictly when there is meaningful orchestration or sequencing across multiple activities.
3. **Calculation Engines:** An Engine is justified strictly when there is an independently volatile business algorithm, heuristic, or calculation rule that can be expressed as a pure, infrastructure-free function.
4. **ResourceAccess / Accessors:** Accessors own concrete interaction with PostgreSQL tables or external APIs (querying, filtering, eager loading, persistence). They replace generic repository patterns.
5. **No Mechanical Layering:** Simple CRUD operations do **not** receive Managers or Engines. They follow a direct `Router -> Accessor` design.
6. **No Domain-Noun Architecture:** Domain entities (Account, Category, Budget, Transaction) do not automatically become architecture layers (`AccountManager`, `CategoryEngine`, etc.).

---

## 2. Volatility Analysis Matrix

The following matrix documents only **observed volatility** and **confirmed roadmap items**.

| System Responsibility | What Changes Independently? | Volatility Rate | Observed Evidence in Codebase | Justified Architecture Boundary |
|---|---|:---:|---|---|
| **Bank Statement Parsing** | Bank export headers, date formats, transaction sign conventions | **Medium-High** | USAA and Discover CSV formats have opposite sign conventions and different column headers | **Ingestion Parser / StatementLoader** (`backend/bank_statement_loader.py`) |
| **Plaid API Integration** | External API endpoints, cursor-based sync protocol, credential decryption | **High** | Plaid API cursor typing quirk requiring raw HTTP requests; token storage security | **External ResourceAccess** (`plaid_access.py` / SDK client for `/accounts/get` + `plaid_transaction_access.py` / raw HTTP for `/transactions/sync`) |
| **Zero-Based Budget (ZBB) Math** | Sign inversions, category remaining, group totals, `to_be_assigned` | **Medium** | Financial math was previously copy-pasted across `get_budget_summary` and `get_dashboard_summary` | **Pure Domain Engine** (`backend/domain/budgeting.py`) |
| **Transfer Reconciliation Matching** | Pairing heuristics: exact absolute amount, opposing signs, different accounts, $\le 2$ days | **Medium-High** | Heuristic matching was trapped inside `routers/credit_cards.py` | **Pure Domain Engine** (`backend/domain/reconciliation.py`) |
| **Credit Card Financial Metrics** | Calculating starting balance, `balance_owed`, monthly charges, monthly payments | **Medium** | Card balance calculations were trapped inside route handlers | **Pure Domain Engine** (`backend/domain/credit_cards.py`) |
| **Budget Summary Orchestration** | Sequencing period determination, category fetching, budget allocations, actuals aggregation | **Medium** | Coordinates 3 accessors and the Budget Engine | **Workflow Manager** (`backend/managers/budget_summary_manager.py`) |
| **Dashboard Summary Orchestration** | Composing budget health, active account balances snapshot, and 10 recent transactions | **Medium** | Assembles 3 disparate data concerns into a unified view | **Workflow Manager** (`backend/managers/dashboard_summary_manager.py`) |
| **Relational Data Persistence** | SQLAlchemy query syntax, eager loading, session transactions | **Low-Medium** | Raw SQL queries scattered across route handlers | **Concrete ResourceAccess / Accessors** (`backend/access/`) |
| **API Transport & Validation** | FastAPI path/query parsing, HTTP status codes, Pydantic response models | **Medium** | Route parameter validation and response serialization | **Presentation / Router Layer** (`backend/routers/`) |
| **Client UI Views** | Visual layout, component hierarchy, responsive styling | **High** | Frontend views in Nuxt 4 / Vue 3 SPA | **Client Presentation Layer** (`frontend/app/pages/`) |

---

## 3. Explicitly Rejected & Speculative Drivers

The following items are **speculative** and must **not** be used to justify architectural layers, interfaces, or configuration parameters:

| Speculative Concept | Why Rejected as an Architectural Driver |
|---|---|
| **Alternative Bank Aggregators (MX, Teller)** | The application currently integrates exclusively with Plaid. Introducing an `IBankProvider` interface is premature generalization. |
| **Hypothetical CSV Layouts (Chase, BoA, OFX/QIF)** | Only USAA and Discover statements are currently supported. Adding generic bank format parsers before real formats are needed adds dead code. |
| **Fuzzy Duplicate Matching / Hash Deduplication** | Current deduplication is an exact 4-tuple match `(account_id, date, amount, description)`. Algorithmic scoring engines are overengineering. |
| **Merchant-Keyword / Split-Transfer Matching** | Inter-account transfers currently use deterministic 1-to-1 pairing within 2 days. Heuristic pipeline frameworks are rejected. |
| **Statement Cycles, APR Tracking, Minimum Payments** | Credit card accounting strictly tracks all-time net transactions and monthly charges/payments. Liability forecasting engines are speculative. |
| **Nested Subcategories / Icon / Color Metadata** | Categories form a flat 2-level hierarchy (`CategoryGroup -> Category`). Tree structures and metadata engines are rejected. |
| **Multi-Currency Ledgers / Forex Rates** | All accounts and calculations strictly operate in fixed-point USD decimals. Currency conversion engines are speculative. |
| **Custom / Bi-Weekly Budget Periods** | Zero-based budgeting operates on standard calendar months. Configurable calendar engines are rejected. |
| **Multi-User / JWT Authentication Infrastructure** | The system currently operates as a personal budget application without multi-tenant authentication boundaries. |
| **Alternative Persistence Engines (MongoDB, DynamoDB)** | The application fundamentally relies on relational guarantees, foreign keys, and ACID transactions. Database abstraction layers are rejected. |

---

## 4. System Architecture & Component Interactions

```mermaid
flowchart TD
    subgraph Presentation ["Presentation Layer (FastAPI Routers)"]
        RouterSummary["summaries.py<br/>(/summary/budget, /summary/dashboard)"]
        RouterCC["credit_cards.py<br/>(/credit-cards/summary, candidates)"]
        RouterTx["transactions.py<br/>(Slice 10 Implemented & Verified)"]
        RouterAcct["accounts.py<br/>(Slice 11 Implemented & Verified)"]
        RouterCat["categories.py<br/>(Slice 12 Implemented & Verified)"]
        RouterBudget["budgets.py<br/>(Slice 13 Implemented & Verified)"]
        RouterUpload["upload.py<br/>(/upload/preview, /upload/confirm)"]
        RouterPlaid["plaid.py<br/>(/plaid/sync_accounts, sync_transactions)"]
    end

    subgraph Managers ["Workflow Managers (Sequencing Volatility)"]
        BudgetSummaryMgr["BudgetSummaryManager<br/>(Reference Vertical Slice)"]
        DashSummaryMgr["DashboardSummaryManager<br/>(Slice 2 Implemented & Verified)"]
        CCSummaryMgr["CreditCardSummaryManager<br/>(Slice 3 Implemented & Verified)"]
        ReconcileMgr["TransferReconciliationManager<br/>(Slice 4 Implemented & Verified)"]
        CSVImportMgr["CSVImportManager<br/>(Slice 5 Implemented & Verified)"]
        PlaidAccountSyncMgr["PlaidAccountSyncManager<br/>(Slice 6 Implemented & Verified)"]
        PlaidTxSyncMgr["PlaidTransactionSyncManager<br/>(Slice 7 & Slice 9 Implemented & Verified)"]
    end

    subgraph Engines ["Domain Calculation Engines (Pure Business Rules)"]
        ZBBEngine["Budget Engine<br/>(calculate_budget_summary)"]
        CCEngine["Credit Card Engine<br/>(calculate_credit_card_state)"]
        ReconcileEngine["Reconciliation Engine<br/>(detect_transfer_candidates)"]
    end

    subgraph Accessors ["ResourceAccess (Concrete Persistence & API Access)"]
        BudgetAcc["budget_access.py"]
        CatAcc["category_access.py"]
        TxAcc["transaction_access.py"]
        AcctAcc["account_access.py"]
        PlaidItemAcc["plaid_item_access.py"]
        PlaidAcc["plaid_access.py / SDK Client"]
        PlaidTxAcc["plaid_transaction_access.py<br/>(raw /transactions/sync)"]
        CSVLoader["bank_statement_loader.py (USAA, Discover)"]
    end

    subgraph Resources ["External & Storage Resources"]
        DB[(PostgreSQL)]
        PlaidAPI["Plaid API"]
        CSVFile["CSV Upload Stream"]
    end

    %% Router to Manager
    RouterSummary --> BudgetSummaryMgr
    RouterSummary --> DashSummaryMgr
    RouterCC --> CCSummaryMgr
    RouterCC --> ReconcileMgr
    RouterUpload --> CSVImportMgr
    RouterPlaid --> PlaidAccountSyncMgr
    RouterPlaid --> PlaidTxSyncMgr

    %% Implemented CRUD directly to Accessors
    RouterTx --> TxAcc
    RouterAcct --> AcctAcc
    RouterCat --> CatAcc
    RouterBudget --> BudgetAcc

    %% Manager internal wiring
    BudgetSummaryMgr --> ZBBEngine
    BudgetSummaryMgr --> CatAcc
    BudgetSummaryMgr --> BudgetAcc
    BudgetSummaryMgr --> TxAcc

    DashSummaryMgr --> BudgetSummaryMgr
    DashSummaryMgr --> AcctAcc
    DashSummaryMgr --> TxAcc

    CCSummaryMgr --> CCEngine
    CCSummaryMgr --> AcctAcc
    CCSummaryMgr --> TxAcc

    ReconcileMgr --> ReconcileEngine
    ReconcileMgr --> TxAcc

    CSVImportMgr --> CSVLoader
    CSVImportMgr --> AcctAcc
    CSVImportMgr --> TxAcc

    PlaidAccountSyncMgr --> PlaidAcc
    PlaidAccountSyncMgr --> PlaidItemAcc
    PlaidAccountSyncMgr --> AcctAcc

    PlaidTxSyncMgr --> PlaidItemAcc
    PlaidTxSyncMgr --> PlaidAcc
    PlaidTxSyncMgr --> AcctAcc
    PlaidTxSyncMgr --> PlaidTxAcc
    PlaidTxSyncMgr --> TxAcc

    %% Accessors to Resources
    BudgetAcc --> DB
    CatAcc --> DB
    TxAcc --> DB
    AcctAcc --> DB
    PlaidItemAcc --> DB
    PlaidAcc --> PlaidAPI
    PlaidTxAcc --> PlaidAPI
    CSVLoader --> CSVFile
```

### Key Structural Invariants:
1. **Not Every Endpoint Uses Every Layer:** Direct `Router -> Accessor` is the standard, terminal pattern for CRUD.
2. **Direct Manager Composition:** `DashboardSummaryManager` reuses `BudgetSummaryManager` directly to obtain zero-based budget metrics, eliminating calculation and query duplication.
3. **Engines Remain Pure:** Calculation Engines have zero dependencies on SQLAlchemy, FastAPI, or Pydantic.
4. **Accessors Own Query Mechanics:** Accessors encapsulate filtering, ordering, and eager loading, preventing lazy-loading bugs.

---

## 5. Ingestion Architecture: CSV vs. Plaid Disentanglement

Although both ingestion pipelines persist transactions to PostgreSQL, their operational characteristics and volatility axes are fundamentally different. They must **not** be unified into a generic transaction ingestion framework.

### 5.1. CSV Statement Ingestion Pipeline
- **Input Resource:** Stateless file stream (`UploadFile`).
- **Processing Model:** Batch parsing via `BankStatementLoader` hierarchy (USAA, Discover).
- **Identity Model:** No stable external transaction IDs.
- **Deduplication Policy:** Exact 4-field tuple match `(account_id, date, amount, description)`.
- **Event Lifecycle:** Two user-facing operations: Preview and Confirm. Confirm reparses the raw upload independently and does not consume Preview state. Insert-only; duplicate rows are skipped; no deletion or modification events.
- **Error Model:** Preview reports row-level parsing issues; Confirm fails whole-statement parsing with 422 before persistence, while persistence-loop row errors are accumulated non-fatally.

### 5.2. Plaid Account Sync Pipeline (Slice 6 Implemented & Verified)
- **Input Resource:** External Plaid REST API (`/accounts/get`).
- **Processing Model:** Explicitly stateless, single API fetch. No cursor, no pagination loop.
- **Identity Model:** Single specified `PlaidItem` resolved by `item_id` (precedence) or `plaid_item_id`. Account identity matched strictly by `Account.plaid_account_id == remote.account_id` (not scoped by `item_id`).
- **Persistence & Update Policy:** Upsert over returned accounts. Staged and updated in PostgreSQL; preserves custom user edits (`starting_balance`, inactive status `is_active=False`, `item_id`, `id`). Accounts omitted from the Plaid response are untouched.
- **Event Lifecycle:** Balance and metadata refresh for a linked institution. Stages records, performs explicit `db.flush()`, single final `db.commit()`, and returns `accounts_updated`.
- **Security Dependency:** Decrypts stored access token via `security.decrypt_token`. Passes decoded token directly to external ResourceAccess.

### 5.3. Plaid Transaction Sync Pipeline (Slice 7 & Slice 9 Implemented & Verified)
- **Input Resource:** External Plaid REST API (`/transactions/sync` via raw HTTP requests library to bypass Plaid Python SDK cursor validation issues).
- **Processing Model:** Stateful cursor-based pagination loop (`has_more` paging), coupled with pre-sync account balance refresh staged with `db.flush()` (commit piggybacking).
- **Identity Model:** Exact, stable external IDs (`plaid_transaction_id`).
- **Deduplication Policy:** Upsert on external ID match (`plaid_transaction_id`).
- **Event Lifecycle:** Continuous ledger synchronization. Supports transaction additions (insert or update), modifications (in-place update preserving user fields `category_id` and `is_transfer`), and removals (deletion by external ID if present, commit-on-found); persists latest sync cursor after pagination loop completes.
- **VBD Architecture:** Coordinates `plaid_item_access.py`, `security.decrypt_token`, `plaid_access.py` (for account balance snapshots), `account_access.py`, `plaid_transaction_access.py` (dedicated raw HTTP /transactions/sync client), and `transaction_access.py` (PostgreSQL transaction persistence). Manager owns event-level commits. Documented in [plaid-transaction-sync.md](plaid-transaction-sync.md).

---

## 6. Anti-Patterns & Overengineering to Avoid

1. **Generic Repository Interfaces (`IRepository<T>`):**
   Introducing generic repository abstractions, specification patterns, or Unit of Work frameworks for PostgreSQL is unnecessary boilerplate. Concrete Python functions in focused access modules (`account_access.py`, `transaction_access.py`) are preferred.
2. **Manager-per-Domain-Entity Antipattern:**
   Creating `AccountManager`, `CategoryManager`, or `BudgetManager` for basic CRUD operations adds zero architectural value. A Manager is justified strictly by workflow sequencing.
3. **Engine-per-Feature Antipattern:**
   Inventing pseudo-engines (e.g. `DashboardEngine`, `TransferConfirmationEngine`, `ReorderingEngine`) for simple sums, index increments, or boolean updates is overengineering.
4. **DTO Layer Proliferation:**
   Do not introduce parallel DTO types for every layer. Accessors return ORM persistence records to Managers; Managers map records into clean, immutable application dataclasses; Routers serialize application dataclasses to Pydantic responses.
5. **Microservices / Distributed Message Brokers:**
   Deploying Kafka, RabbitMQ, or Celery for a personal budgeting application would introduce substantial operational overhead without benefit.

---

## 7. Remaining Workflows Classification & Architectural Decisions

Following the reference vertical slice (Budget Summary) and the completed Dashboard Summary slice, the remaining application workflows are classified based on observed volatility:

### 7.1. Classification Summary Matrix

| Workflow | Manager? | Engine? | Accessor? | Target Pattern | Rationale |
|---|:---:|:---:|:---:|---|---|
| **Dashboard Summary** | **Yes** | **Reuse Budget Engine** | **Yes** | `Router -> Manager -> (BudgetSummaryManager + Accessors)` | Composes existing Budget Summary workflow, active accounts, and 10 recent transactions (Slice 2 Implemented & Verified; see [dashboard-summary.md](dashboard-summary.md)). |
| **Credit-Card Summary** | **Yes** | **Reuse CC Engine** | **Yes** | `Router -> Manager -> (CreditCardEngine + Accessors)` | Coordinates active credit accounts, historical ledger queries, calculation engine execution, and monthly display selection (Slice 3 Implemented & Verified; see [credit-card-summary.md](credit-card-summary.md)). |
| **Transfer Candidate Search** | **Yes** | **Reuse Reconciliation Engine** | **Yes** | `Router -> Manager -> (ReconciliationEngine + Accessor)` | Coordinates candidate-set retrieval, domain input mapping, pure Engine matching, match-to-record correlation, and response enrichment (Slice 4 Implemented & Verified; see [transfer-candidate-search.md](transfer-candidate-search.md)). |
| **CSV Confirmation & Deduplication** | **Yes** | **No Standalone Engine** | **Yes** | `Router -> CSVImportManager -> (AccountAccess + TransactionAccess + StatementLoader)` | Coordinates account verification, loader parsing, exact duplicate checking, batch insert, and commit (Slice 5 Implemented & Verified; see [csv-import-confirmation.md](csv-import-confirmation.md)). |
| **Plaid Account Sync** | **Yes** | **No Engine** | **Yes** | `Router -> PlaidAccountSyncManager -> (PlaidItemAccess + AccountAccess + PlaidAccess)` | External API call, credential decryption, and account/balance persistence (Slice 6 Implemented & Verified; see [plaid-account-sync.md](plaid-account-sync.md)). |
| **Plaid Transaction Sync** | **Yes** | **No Engine** | **Yes** | `Router -> PlaidTransactionSyncManager -> (PlaidItemAccess + PlaidAccess + AccountAccess + PlaidTransactionAccess + TransactionAccess)` | Coordinates balance refresh flush, cursor pagination loop, added/modified/removed processing, event-level commits, and cursor persistence (Slice 7 & Slice 9 Implemented & Verified; see [plaid-transaction-sync.md](plaid-transaction-sync.md)). |
| **Transfer Confirmation** | **No** | **No Engine** | **Yes** | `Router -> Accessor` | Single atomic boolean mutation (`is_transfer = True`). |
| **Manual Transaction CRUD** | **No** | **No Engine** | **Yes** | `Router -> TransactionAccess` | Standard entity CRUD and query filtering (Slice 10 Implemented & Verified). Retired legacy `crud/transaction.py`. |
| **Account CRUD** | **No** | **No Engine** | **Yes** | `Router -> AccountAccess` | Standard entity CRUD (Slice 11 Implemented & Verified). Raw queries moved to `account_access.py`. |
| **Category & Group CRUD** | **No** | **No Engine** | **Yes** | `Router -> CategoryAccess` | Standard entity CRUD (Slice 12 Implemented & Verified). Retired legacy `crud/category.py`. |
| **Category & Group Reorder** | **No** | **No Engine** | **Yes** | `Router -> CategoryAccess` | Applies payload-index sort_order updates while preserving characterized handling of unknown, unlisted, cross-group, empty, and duplicate IDs (Slice 12 Implemented & Verified). |
| **Budget Allocation CRUD** | **No** | **No Engine** | **Yes** | `Router -> BudgetAccess` | Standard monthly allocation entity CRUD (Slice 13 Implemented & Verified). Concrete persistence moved to `budget_access.py`. |
| **Plaid Link-Token Creation** | **No** | **No Engine** | **Yes** | `Router -> Plaid Accessor` | Single external SDK call. |

### 7.2. Category 1: Manager + Existing Engine
- **Credit-Card Summary (Slice 3 Implemented & Verified):** Uses `CreditCardSummaryManager` orchestrating active credit accounts, historical transactions, calculation engine execution, and monthly display selection, reusing the existing, pure [`calculate_credit_card_state`](backend/domain/credit_cards.py). Documented in [credit-card-summary.md](credit-card-summary.md).

- **Transfer Candidate Search (Slice 4 Implemented & Verified):** Uses `TransferReconciliationManager` orchestrating candidate-set retrieval, domain input mapping, pure Engine matching, match-to-record correlation, and response enrichment, reusing the existing, pure [`detect_transfer_candidates`](backend/domain/reconciliation.py). Documented in [transfer-candidate-search.md](transfer-candidate-search.md).

### 7.3. Category 2: Manager Likely Justified, No Engine
- **CSV Confirmation & Deduplication (Slice 5 Implemented & Verified):** Multi-step pipeline (verify account $\rightarrow$ parse statement $\rightarrow$ deduplicate $\rightarrow$ batch stage $\rightarrow$ commit), reusing the existing BankStatementLoader boundary without a new Engine. Documented in [csv-import-confirmation.md](csv-import-confirmation.md).
- **Plaid Account Sync (Slice 6 Implemented & Verified):** Multi-step pipeline (validate identifiers $\rightarrow$ lookup PlaidItem $\rightarrow$ decrypt token $\rightarrow$ fetch accounts $\rightarrow$ stage/update local accounts $\rightarrow$ flush $\rightarrow$ commit), coordinating external Plaid SDK access, credential decoding, and account persistence without a standalone Engine. Documented in [plaid-account-sync.md](plaid-account-sync.md).
- **Plaid Transaction Sync (Slice 7 & Slice 9 Implemented & Verified):** Multi-step pipeline (validate identifiers $\rightarrow$ lookup PlaidItem $\rightarrow$ decrypt token $\rightarrow$ stage balance refresh $\rightarrow$ flush $\rightarrow$ paginated cursor loop $\rightarrow$ event-level commits $\rightarrow$ persist final cursor $\rightarrow$ commit cursor), coordinating raw HTTP Plaid transaction sync, external account fetching, account persistence, and transaction resource access without an Engine. Documented in [plaid-transaction-sync.md](plaid-transaction-sync.md).

### 7.4. Category 3: No Manager and No Engine Currently Justified
Direct **`Router -> Accessor`** is the terminal and correct VBD design for:
- Transfer confirmation (`POST /credit-cards/mark-transfers`)
- Manual transaction CRUD (`backend/routers/transactions.py -> backend/access/transaction_access.py`; Slice 10 Implemented & Verified)
- Account CRUD (`backend/routers/accounts.py -> backend/access/account_access.py`; Slice 11 Implemented & Verified)
- Category and CategoryGroup CRUD (`backend/routers/categories.py -> backend/access/category_access.py`; Slice 12 Implemented & Verified)
- Category and CategoryGroup reordering (`/category-groups/reorder`, `/categories/reorder -> backend/access/category_access.py`; Slice 12 Implemented & Verified)
- Budget allocation CRUD (`backend/routers/budgets.py -> backend/access/budget_access.py`; Slice 13 Implemented & Verified)
- Plaid link-token creation (`POST /plaid/create_link_token`)

> [!NOTE]
> **Shared ResourceAccess for Multiple Callers:**
> Notice that `budget_access.py` supports multiple callers:
> - `BudgetSummaryManager -> BudgetAccess` (monthly summary retrieval via `get_budgets_for_month`)
> - `Budget CRUD Router -> BudgetAccess` (manual allocation CRUD via `create_budget`, `list_budgets`, etc.)
> Both need concrete PostgreSQL Budget persistence and query behavior. Sharing the concrete Accessor does not imply their workflows should be merged; Budget Summary maintains its workflow Manager and calculation Engine, while Budget CRUD terminates directly at the Accessor.

> [!IMPORTANT]
> **Deliberate VBD Architecture:**
> The absence of a Manager or Engine for simple workflows is an intentional VBD decision, not incomplete architecture. Introducing Managers or Engines into these simple CRUD workflows would represent functional decomposition masquerading as VBD and create meaningless passthrough boilerplate.

---

## 8. Preserved Exclusions & Unresolved Domain Items

The following items remain intentionally excluded from structural refactoring and must not be modified silently:
1. `Transaction.description` database/schema nullability mismatch (Known Defect).
2. Category-group cascade deletion backend inconsistency (Known Defect).
3. Credit-card transfer inclusion in `balance_owed` vs exclusion from `charges_this_month` (Unresolved Domain Decision).
4. Credit-card inclusion of future-dated transactions in current `balance_owed` (Unresolved Domain Decision).
5. Transfer-matching greedy matching on unspecified PostgreSQL row sequence without closest-date tie-breaking (Unresolved Domain Decision).
6. Plaid token base64 storage upgrade to real cryptographic encryption (Security Migration).
