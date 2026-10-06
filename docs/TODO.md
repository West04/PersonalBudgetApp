# Budget App — Canonical Product & Modernization TODO

**Last Updated:** October 3, 2026  
**Status:** Active Canonical TODO  
**Purpose:** Single source of truth replacing previous split TODO files. Tracks completed milestones, acceptance results, deferred product/UX decisions, and upcoming engineering phases.

---

## Issue Classification Taxonomy

To maintain architectural integrity, items in this repository are categorized under a strict taxonomy:

- **Known Defect:** Code or schema behavior believed to be incorrect relative to contracts (e.g. description nullability mismatch).
- **Unresolved Domain Decision:** Business or financial semantics intentionally left undecided pending explicit product direction (e.g. closest-date transfer matching, credit-card transfer inclusion).
- **Product / UX Observation:** Current implementation functions correctly and consistently with characterized behavior, but user experience, visual presentation, or placement can be refined in future redesigns.

---

## Active Roadmap

```text
CSV-first acceptance
    ✓ COMPLETE

CSV-first real use
    ↓
Frontend redesign
    ↓
Transactions-first UX
    ↓
Categorization automation
```

---

## Current Phase — Product / Frontend Redesign

Detailed plan:
[`docs/PRODUCT_REDESIGN_PLAN.md`](PRODUCT_REDESIGN_PLAN.md)

Real-use findings and competitor pattern research have been incorporated into the redesign plan.

Next implementation phases:
1. **Frontend design foundation:** shared tokens, typography, buttons, dialogs, MonthNavigator, feedback states.
2. **Budget/Categories redesign:** whole-row expansion, distinct creation flows, improved editing, month navigation.
3. **Dashboard redesign:** account overview, spending by group/category, actionable cards, reconsidering planned-vs-actual totals.
4. **Transactions UX foundation:** filter persistence, inline editing, preparing for review/transfer/bulk workflows.
5. **Accounts/Credit Cards consolidation:** credit cards represented as accounts, starting balance moved to setup metadata, overpayment styling.

---

# Current Checkpoint

## Completed Milestones

- [x] **VBD Architectural Slices 1–16:** Slices complete and regression verified.
- [x] **Orchestration Managers:** Budget summary, dashboard summary, credit-card summary, transfer reconciliation, CSV import confirmation, and Plaid sync managers where multi-step coordination was justified.
- [x] **Pure Business Engines:** Infrastructure-free domain engines for zero-based budgeting math, credit-card state calculation, date range evaluation, and transfer candidate detection.
- [x] **Concrete ResourceAccess:** Clean persistence boundaries for Accounts, Budgets, Categories, Transactions, CSV Formats, and Plaid.
- [x] **CSV Ingestion Pipeline:** Upload-first inspection (`/upload/inspect`), custom format management (`/upload/formats`), configurable mapped CSV parser (`MappedStatementLoader`), and automated format detection.
- [x] **Timezone & Navigation Fixes:** UTC-safe transaction date calculation and route-synchronized month state across views.

---

# Milestone 1 — CSV-First Product Acceptance (Completed)

## Acceptance Gate: CSV-FIRST READY FOR REAL USE (Achieved)

### Acceptance Summary
- **Outcome:** The user completed the end-to-end acceptance pass using the synthetic user-test pack (`bank_statements/budget_app_user_test_guide.md`).
- **Core Workflows Verified:**
  - Manual CSV upload, inspection, preview, and confirmation.
  - Built-in format parsing (USAA, Discover) and custom format handling (international `%d/%m/%Y`).
  - Account creation, category creation, and zero-based budget assignment (`to_be_assigned`).
  - Transaction ledger viewing, filtering, and manual category assignment.
  - Automated transfer candidate discovery and confirmation.
  - Multi-month statement imports and date boundary preservation.
  - Exact-match deduplication and partial-overlap import safety.
  - Row-level error handling on malformed rows without data loss.
  - Persistent month selection across app-wide navigation.
- **Blockers:** Zero blocking CSV, import, or data-integrity issues remained.
- **Deferred Findings:** Two UX/product observations were identified during testing and deferred to the upcoming frontend redesign phase (see below). Future improvements should be prioritized from these observations and real personal usage.

---

# Milestone 2 — Real-Use Validation

Once real personal budgeting commences:

- [ ] Enter real accounts and accurate starting balances.
- [ ] Establish initial real monthly budget.
- [ ] Import real bank and credit-card statements.
- [ ] Categorize transactions and confirm transfers.
- [ ] Use the application through at least one full monthly budgeting cycle.
- [ ] Log real-world friction and usability notes to inform the frontend redesign.

---

# Milestone 3 — Frontend Redesign (Transactions-First UX)

Begin the complete UI modernization around the proven, reliable backend workflows.

## Design Foundation
- [ ] Define visual design tokens:
  - [ ] Typography scale
  - [ ] Spacing & layout grids
  - [ ] Semantic colors (inflow, outflow, warnings, overpayments)
  - [ ] Border radii & elevation
  - [ ] Responsive breakpoints
- [ ] Establish standard UI states: loading skeletons, empty states, error banners, and success confirmations.
- [ ] Build reusable UI primitives only where justified by repeated patterns.

## Vertical Slices in Priority Order

### 1. Transactions & Transfers (Primary Redesign Target)
Surfacing transaction review and categorization as a first-class workflow:
- [ ] Fast inline category editing.
- [ ] Advanced filter controls (account, category, date range, uncategorized toggle).
- [ ] Full-text search over descriptions and payees.
- [ ] **Transfer review placement (from Acceptance Finding 2):** Surface inter-account transfer candidate discovery, side-by-side pair review, and confirmation directly within transaction workflows rather than restricting discovery to the credit-cards page.
- [ ] Filter state preservation across navigation (route query synchronization for secondary filters).
- [ ] Clear transfer and pending badges.
- [ ] Bulk selection and actions.
- [ ] Explored future affordances: notes, tags, split transactions, suggestion badges.

### 2. Credit Cards View
- [ ] **Negative balance presentation (from Acceptance Finding 1):** Explicitly present negative `balance_owed` as an "Overpayment / Credit Balance" to prevent user confusion with outstanding debt owed.
- [ ] Clear display of starting balance, monthly charges, and monthly payments.
- [ ] Inline editing of starting balances.

### 3. Budget View
- [ ] Rapid planned amount entry.
- [ ] Clear visual separation between income and expense groups.
- [ ] Progress bars and remaining balance health indicators.
- [ ] Prominent zero-based `to_be_assigned` indicator.

### 4. Dashboard
- [ ] High-level budget health indicators.
- [ ] Depository and credit account balance summaries.
- [ ] Recent transactions feed.

### 5. Accounts & Categories
- [ ] Starting balance guidance during account creation.
- [ ] Intuitive drag-and-drop category and group reordering.
- [ ] Safe deletion protections.

### 6. CSV Upload & Import
- [ ] Polished drag-and-drop upload zone.
- [ ] Detailed format detection and sample preview table.
- [ ] Clear import confirmation summary (imported count, duplicate skips, row errors).

---

# Milestone 4 — Transaction Automation & Auto-Categorization

Build incrementally on top of the redesigned Transactions interface:

### Phase A — Data Foundation
- [ ] Treat user-confirmed category assignments as authoritative ground truth.
- [ ] Establish normalized merchant / payee data model.
- [ ] Retain raw bank narrative alongside normalized payee.

### Phase B — Deterministic Rules Engine
- [ ] Exact merchant-to-category matching.
- [ ] Configurable user rules (e.g. IF description CONTAINS 'TRADER JOE' THEN Groceries).
- [ ] Preview rule applications prior to bulk execution.
- [ ] Override and correction recording.

### Phase C — ML Category Suggestions
- [ ] Train lightweight baseline model on user-confirmed categorization history.
- [ ] Present probabilistic suggestions with confidence scores; do not mutate records without user review.
- [ ] Feed user overrides back into training signals.

### Phase D — Optional LLM Assistance
- [ ] Evaluate LLM extraction for ambiguous or unstructured narratives only where deterministic rules and ML abstain.
- [ ] Financial data privacy and strict user confirmation safeguards.

---

# Milestone 5 — Mature Budgeting Features (Candidate Roadmap)

Optional features to consider based on actual personal budgeting needs:

- **Account Reconciliation:** Distinct from transfer reconciliation; mark cleared/uncleared transactions against bank statements.
- **Recurring Transactions & Bills:** Scheduled income and bill tracking.
- **Reporting & Analytics:** Category breakdown charts, cash flow graphs, income vs. expense trends.
- **Savings Goals & Targets:** Sinking funds and progress targets.

---

# Deferred Product & Domain Decisions

These are documented decisions intentionally kept separate from architectural refactoring:

### Credit-card negative balance presentation
- **Classification:** Product / UX observation (NOT a calculation defect)
- **Status:** Deferred product/UX decision
- **Observed during CSV-first acceptance:**
  On the Discover test account, `balance_owed` displayed as `-$178.16`.
  - Starting balance: `$0.00`
  - Charges (positive outflows): `+$82.15` + `+$46.20` + `+$17.99` = `+$146.34`
  - Inflows (negative payments & refunds): `-$300.00` + `-$24.50` = `-$324.50`
  - Net: `$0.00 + $146.34 - $324.50 = -$178.16`
- **Context & Characterized Behavior:**
  The calculation is mathematically and internally consistent with the characterized credit-card debt model:
  $$\text{balance\_owed} = \text{starting\_balance} + \sum_{\text{all-time}} \text{Transaction.amount}$$
  When cumulative payments and credits exceed charges from a zero starting balance, `balance_owed` is negative.
- **Deferred Presentation Direction:**
  Positive `balance_owed` indicates debt owed to the card issuer. Negative `balance_owed` indicates a credit balance / overpayment. Surfacing this status with intuitive visual styling and labeling (e.g. "Credit Balance / Overpaid: $178.16") will be resolved during the credit-cards view redesign. Formula remains unchanged.

### Transfer review placement
- **Classification:** Product / UX architecture observation (NOT an architecture defect)
- **Status:** Deferred frontend UX decision
- **Observed during CSV-first acceptance:**
  The "Find Transfer Matches" discovery button and review panel are currently located on the Credit Cards page (`/credit-cards`). However, inter-account transfers conceptually apply across all account types (e.g. Checking &rarr; Savings, Savings &rarr; Checking, Checking &rarr; Credit Card). In Step 5 of acceptance, a checking-to-savings transfer pair was reviewed and confirmed from the credit-card page.
- **Context & Architecture Integrity:**
  The backend architecture already correctly decouples this workflow: `TransferReconciliationManager` and the pure engine `detect_transfer_candidates` operate agnostically across all account pairs, not just credit cards. The existing backend implementation is preserved.
- **Deferred UX Direction:**
  Surfacing transfer candidate discovery, review, and approval will be elevated to the redesigned Transactions view as a first-class workflow.

### Transaction description nullability
- **Classification:** Known defect
- **Status:** Preserved pending migration slice
- `models.Transaction.description` is nullable in PostgreSQL, while Pydantic schemas enforce non-null `str`. Requires a dedicated characterization and migration slice.

### CategoryGroup deletion cascade inconsistency
- **Classification:** Known defect / behavior inconsistency
- **Status:** Preserved pending product decision
- Backend allows cascading deletion of category groups, while frontend blocks deleting non-empty groups.

### Credit-card transfer & future-date semantics
- **Classification:** Unresolved domain decision
- **Status:** Preserved characterized behavior
- `balance_owed` includes transfers, while `charges_this_month` excludes transfers. Future-dated transactions are currently evaluated in `balance_owed`.

### Transfer matching heuristic
- **Classification:** Unresolved domain decision
- **Status:** Preserved characterized behavior
- `detect_transfer_candidates` pairs transactions greedily in database retrieval sequence without closest-date tie-breaking.

### Budget Summary transfer exclusion
- **Classification:** Unresolved domain decision
- **Status:** Preserved characterized behavior
- `get_actuals_by_category` does not filter out transaction-level `is_transfer = True`; high-level exclusion relies on the category being configured as type `transfer`.

### Reconciled Plaid Corrections
- **Classification:** Unresolved domain decision / follow-up
- **Status:** Preserved characterized guard
- Material provider corrections to already-reconciled transactions are currently blocked from mutating reconciled financial history. A future explicit workflow must define how reconciliation history is reopened or adjusted.

---

# Deferred Backend & Plaid Cleanup

Do not perform speculative cleanup until driven by real product requirements:

- **Backend VBD Consistency Audit:** Verify presentation purity in routers, check for legacy compatibility wrappers, ensure Accessors encapsulate all persistence mechanics.
- **Plaid Strategy Decision:**
  - If Plaid is retained: migrate token storage from base64 encoding to real cryptographic key management (Fernet/KMS), resolve legacy `backend/crud/plaid.py`, and complete Plaid-specific acceptance.
  - If Plaid is retired: cleanly disable Plaid UI and routes, verify CSV independence, and remove Plaid-only code in a dedicated cleanup slice.

---

# Core Architectural Principles & Guardrails

- `domain noun != component`
- `CRUD != Manager`
- `CRUD != Engine`
- `possible future change != observed volatility`
- Standard workflow: `Presentation -> Manager -> Engine / Accessor -> Resource`
- Simple CRUD: `Presentation -> Accessor -> Resource`
- CSV parsing remains an ingestion/parser boundary, not a business Engine.
- Do not introduce speculative abstractions without demonstrated independent volatility.
