---
name: doc-truth-verifier
description: >-
  Rigorously verifies that existing or proposed documentation is 100% factually accurate, source-backed, and contractually correct against current implementation code, tests, and database constraints. Prevents hallucinations, over-generalizations, naming assumptions, and speculative claims.
---

# Documentation Truth Verifier

Use this skill before finalizing or committing documentation changes, when reviewing documentation PRs, or when auditing technical specs. Its mission is to enforce **zero tolerance for documentation hallucinations, assumed module names, speculative claims, and contractual inaccuracies**.

Every technical statement in repository documentation must be directly traceable to working source code or passing tests.

---

## 1. Source-of-Truth Hierarchy

When evaluating the factual truth of any documentation claim, apply this strict priority of evidence:

```text
1. Current implementation source code (backend/, frontend/app/)
2. Current automated tests & assertions (tests/)
3. Active Pydantic schemas, FastAPI route signatures, SQLAlchemy models
4. Recent git commit history (used strictly to clarify intent, not to override running code)
5. Existing documentation (never treated as authoritative; updated whenever it conflicts with code)
```

**Never modify code to make stale or inaccurate documentation true.** Always correct the documentation to reflect code reality.

---

## 2. Verification Checklists

Verify documentation against the following 8 factual dimensions:

### 1. Module Paths & Exported Symbol Verification
- **Rule:** Every referenced file path, class name, function name, and variable must exist in the actual repository tree.
- **Verification Steps:**
  - Verify Manager filenames end in the exact repository convention (e.g. `budget_summary_manager.py`, NOT `budget_summary.py`).
  - Verify every referenced function actually exists (e.g. `get_budget_summary`, `confirm_csv_import`, `get_transfer_candidates`).
  - Check for invented "convenience" modules (e.g. confirming there is no `credit_card_access.py` when credit card summary queries `account_access.py` and `transaction_access.py`).
  - Distinguish router helper functions from domain/ingestion functions (e.g. `_resolve_statement_loader` lives in `routers/upload.py`, while `get_loader` lives in `bank_statement_loader.py`).

### 2. Architecture Taxonomy & Boundary Discipline (VBD)
- **Rule:** Architectural components must be classified accurately according to Volatility-Based Decomposition.
- **Verification Steps:**
  - **Presentation:** FastAPI routers (`backend/routers/`) and Nuxt pages (`frontend/app/pages/`). Owns HTTP validation, status codes, and serialization.
  - **Manager:** Meaningful use-case workflow sequencing (`backend/managers/`). Must coordinate multiple Accessors/Engines. Never invent a Manager for simple CRUD.
  - **Engine:** Pure, deterministic business algorithms/policies (`backend/domain/`). Must have zero dependencies on SQLAlchemy, Sessions, HTTP, or external SDKs.
  - **ResourceAccess:** Concrete persistence and external API integration (`backend/access/`). Must NOT include file statement parsing.
  - **Ingestion / Parser Boundary:** Statement loaders (`backend/bank_statement_loader.py`). Adapts external bank files into domain objects (`TransactionCreate`). **Must NOT be called an Engine and must NOT be called ResourceAccess.**
  - **Resource:** Persistent external infrastructure (PostgreSQL, Plaid API, CSV upload stream).
  - **None:** Simple logic not warranting a separate layer.

### 3. Exact Mathematical & Logical Contracts
- **Rule:** Mathematical operations, set relationships, and financial conventions must be described with exact precision.
- **Verification Steps:**
  - **Set Semantics:** Verify subset relationships. If `detect_csv_format` uses `required_headers.issubset(uploaded_headers)`, document mathematically as:
    $$\text{required\_headers} \subseteq \text{uploaded\_headers}$$
    Never describe this as a "strict subset" or "proper subset" ($A \subset B$), which would falsely imply exact header matches fail or that extra columns are required.
  - **Monetary Sign Conventions:**
    - Outflows / Debits / Purchases / Charges: **Positive (`> 0`)**
    - Inflows / Credits / Deposits / Income: **Negative (`< 0`)**
    - Display/Reporting Inversion: Income inverted for user display ($\text{actual} = -1 \times \sum \text{amount}$).
  - **Zero-Based Budget Math:**
    $$\text{to\_be\_assigned} = \text{total\_income\_planned} - \text{total\_expense\_planned}$$
  - **Exact Matching Rules:** State whether comparisons are case-sensitive, whitespace-sensitive, or punctuation-sensitive. Explain exactly what helpers like `normalize_headers` do (e.g. filtering `None`/`""` rather than trimming or lowercasing).

### 4. Database Schema & Model Precision
- **Rule:** Distinguish persisted database columns from Python-derived dataclass properties.
- **Verification Steps:**
  - Check `backend/models.py` for exact table names, column names, nullability, and server defaults.
  - Verify check constraints (e.g. `amount_sign_convention IN ('positive_is_outflow', 'positive_is_inflow')`).
  - Verify unique indexes (e.g. `lower(name)` case-insensitive unique index).
  - Confirm derived properties are documented as derived, not persisted (e.g. `required_headers` on `MappedCSVFormatConfig`).
  - **Reject Hallucinated Properties:** Ensure nonexistent conceptual properties (such as `header_signature`) are completely omitted.

### 5. API Transport & Schema Contracts
- **Rule:** REST API documentation must match Pydantic schemas and FastAPI route signatures exactly.
- **Verification Steps:**
  - Verify exact endpoint path (including trailing slash rules, e.g. `/budget/` vs `/category-groups`).
  - Verify HTTP methods and success status codes (200 OK, 201 Created, 204 No Content).
  - Verify error status codes (400 Bad Request, 404 Not Found, 409 Conflict, 422 Unprocessable Entity).
  - Verify response payload structures. For example: confirm `sample_rows` in `/upload/inspect` is a positional list of lists (`sample_rows[row][column]`), **not** an array of header-keyed dictionaries.
  - Clarify when endpoints require explicit parameters vs performing auto-detection (e.g. `POST /upload/preview` and `/upload/confirm` require an explicit `format` identifier and do not auto-detect).

### 6. Frontend UI & Interaction Reality
- **Rule:** Documentation of user interfaces must reflect actual template components and state machines.
- **Verification Steps:**
  - Verify exact wizard step sequences from template source (e.g. `stepLabels = ['Upload', 'Account', 'Preview', 'Done']`).
  - Verify whether sub-workflows are rendered **inline** or in modal dialogs (e.g. the custom format mapping form is rendered inline within Step 1 when status is `unknown`, not in a modal).
  - Verify client API communication patterns (e.g. confirm all pages use `const API_BASE = '/api'` proxying through Nuxt Nitro, rather than direct client-to-backend CORS calls).

### 7. Preserved Defects vs. Unresolved Decisions
- **Rule:** Never document a bug away or turn an unresolved product debate into settled architecture.
- **Verification Steps:**
  - **Known Defects:** If code exhibits a known defect (e.g. `Transaction.description` database nullability vs Pydantic non-null validation, or `CategoryGroup` backend cascade deletion discrepancy), document it explicitly as a **Known Defect**.
  - **Unresolved Domain Decisions:** If an accounting rule is an active product dilemma (e.g. credit card `balance_owed` including transfers while `charges_this_month` excludes transfers, inclusion of future-dated transactions, or greedy transfer pairing), document it as an **Unresolved Domain Decision / Characterized Production Behavior**, not a permanent invariant.

### 8. Test Command & Baseline Hygiene
- **Rule:** Keep setup instructions resilient against immediate staleness.
- **Verification Steps:**
  - Long-lived developer documentation (`DEVELOPMENT.md`, `README.md`) must specify the test runner (`python3 -m pytest`) without embedding hardcoded test counts (e.g. `>650 tests`) that invalidate on the next test addition.
  - Point-in-time test counts belong exclusively in dated refactoring checkpoints or progress logs (e.g. `docs/TODO.md`).

---

## 3. Verification Workflow & Execution

1. **Extract Claims:** Read the document or diff and extract all technical claims (file names, symbol names, endpoints, formulas, database columns, UI steps).
2. **Trace to Source:** For each extracted claim, use codebase search (`view_file`, `run_command` with `grep`/`ls`) to find the exact source implementation.
3. **Spot-Check Citations:** Record the exact file and line number supporting the claim.
4. **Flag Divergences:** If a claim contradicts source code, record the contradiction and provide the exact source-backed correction.

---

## 4. Required Truth Verification Report

When executing this skill, produce a structured truth verification report:

```markdown
# Documentation Truth Verification Report

## 1. Scope & Source-of-Truth Baseline
- **Document(s) Verified:** <list of file paths>
- **HEAD Commit:** <commit hash>

## 2. Claim-by-Claim Verification Matrix

| Claim in Documentation | Source File & Line | Status | Notes / Correction Required |
|---|---|:---:|---|
| Module path `budget_summary_manager.py` | `backend/managers/budget_summary_manager.py:29` | Verified | Exists and exports `get_budget_summary` |
| Loader resolution helper | `backend/routers/upload.py:48` | Corrected | Router helper is `_resolve_statement_loader` |
| Format detection subset rule | `backend/bank_statement_loader.py:411` | Corrected | Uses `issubset` (⊆), not strict subset (⊂) |
| Nonexistent `header_signature` | `backend/bank_statement_loader.py:255` | Corrected | Removed claim; only `required_headers` exists |

## 3. Taxonomy & Boundary Assessment
- Confirms correct classification of Presentation, Manager, Engine, ResourceAccess, Ingestion/Parser, Resource, and None.
- Confirms zero leakage of infrastructure into pure Engines.
- Confirms `BankStatementLoader` is strictly classified as an Ingestion boundary.

## 4. Inaccuracies Found & Required Edits
Provide the exact text replacements required to make the document 100% source-accurate.

## 5. Final Verdict
State exactly one:
- **READY TO COMMIT** (All claims are 100% verified against source code).
- **CORRECTIONS REQUIRED** (One or more claims diverged from source code; edits listed above must be applied first).
```
