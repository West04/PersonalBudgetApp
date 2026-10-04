# Budget App Product Redesign & Development Plan

**Status:** Planning baseline  
**Phase:** CSV-first acceptance complete → real-use-informed redesign  
**Purpose:** Define the product direction, frontend responsibilities, future financial capabilities, sequencing, and acceptance requirements before implementation begins.

---

# 1. Executive Summary

The budget application has reached an important milestone:

```text
Backend modernization       Complete enough for current product work
CSV-first workflow          Complete
CSV acceptance testing      Complete
Major acceptance defects    Fixed
Real-use evaluation         Complete
Frontend/product redesign   Next major phase
```

The application currently works, but real use has exposed a more important question than correctness:

> How should the application organize financial information and workflows so that it is efficient, understandable, and pleasant to use repeatedly?

The next phase should therefore **not** be a broad backend refactor or a collection of isolated UI tweaks.

The plan is to redesign the application around the user's financial jobs:

```text
Dashboard
"What should I know right now?"

Budget
"What am I planning to do with my money?"

Transactions
"What happened, and what needs my attention?"

Accounts
"Where is my money and debt, and can I trust the balances?"

Upload
"How does transaction data enter the system?"

Settings
"How is the application configured?"
```

Future functionality such as transfer review, transaction rules, merchant normalization, recurring transactions, reconciliation, and ML categorization should extend these workflows rather than creating unrelated screens.

A future Reports/Insights area may be added when reporting functionality becomes substantial enough to justify a dedicated destination.

---

# 2. Product Principles

These principles should guide future product decisions.

## P-001 — Organize by user job, not backend entity

The frontend should not mirror the backend class or table structure.

Avoid navigation such as:

```text
Accounts
Credit Cards
Transfers
Categories
```

merely because those concepts exist in the domain.

Prefer:

```text
Budget
Transactions
Accounts
```

where related domain concepts are presented within the workflow where the user needs them.

---

## P-002 — Preserve workflows that already work

The redesign is not a rewrite for its own sake.

Real-use feedback indicates:

```text
Transactions     fundamentally good
Upload           good
Budget/Categories useful but interaction needs improvement
Dashboard        information hierarchy needs reconsideration
Accounts         concept needs improvement
Credit Cards     responsibility appears misplaced
Dialogs/forms    broadly inconsistent
Month selector   broadly poor
```

Successful workflows should be refined rather than replaced.

---

## P-003 — Repeated actions deserve the strongest UX attention

A screen used every week deserves more optimization than a setup screen used once.

Priority should therefore favor:

1. Transaction review
2. Categorization
3. Budget review
4. Account reconciliation
5. Import
6. Reporting
7. Administrative setup

---

## P-004 — Financial automation must remain understandable

Rules, transfer detection, recurring matching, and ML categorization should not silently alter financial data without understandable behavior.

Future automation should favor:

```text
prediction
→ preview/review
→ acceptance
→ feedback
```

over opaque automatic mutation.

---

## P-005 — Correctness before intelligence

ML categorization should not be introduced until:

- transaction data is trustworthy;
- merchant/payee normalization exists;
- user categorization history is reliable;
- deterministic rules exist;
- review/correction workflows exist.

---

## P-006 — Avoid speculative architecture

Do not introduce abstractions solely because a future feature might need them.

Continue following the VBD principles already established:

```text
domain noun != component
CRUD != Manager
CRUD != Engine
possible future change != observed volatility
```

---

# 3. Current Product Baseline

The following behaviors should be treated as the stable baseline unless explicitly changed by a future requirement.

## 3.1 CSV workflow

The CSV-first workflow has passed user acceptance.

The system currently supports:

- CSV format configuration;
- upload and preview;
- transaction persistence;
- multiple account imports;
- custom date formats;
- date-only financial dates;
- month-aware navigation;
- imported historical transactions.

CSV import should remain a supported first-class ingestion path even if Plaid or another automated source becomes more important later.

---

## 3.2 Shared budgeting month

Month-scoped views share a selected budgeting month.

The month:

- persists when navigating among relevant pages;
- is represented in route state;
- survives navigation through non-month-scoped pages;
- must represent a calendar month independent of timezone.

This behavior should be preserved.

Only the visual presentation of the month selector should be redesigned.

---

## 3.3 Date-only financial values

Financial calendar dates such as:

```text
2026-06-09
```

must always display as June 9 regardless of browser timezone.

Date-only values must not be treated like timestamp instants.

True timestamps remain a separate concept.

---

# 4. Target Information Architecture

## 4.1 Primary navigation

Target primary navigation:

```text
Dashboard

Budget

Transactions

Accounts

Upload

────────────

Settings
```

### NAV-001

Credit Cards should no longer be assumed to require a primary navigation destination.

Credit-card accounts should normally be represented within Accounts.

The existing Credit Cards screen should remain until its useful functionality has been deliberately migrated or replaced.

Do not simply delete it during early redesign work.

---

## 4.2 Potential future navigation

Do not add these items yet:

```text
Reports / Insights
Recurring
Rules
Goals
Transfers
```

They should become primary navigation destinations only if their workflows become substantial enough to justify one.

---

# 5. Shared Frontend Design Requirements

Before major page-specific redesign, establish a small shared visual and interaction system.

## UX-001 — Consistent page header

Month-aware pages should use a consistent structure:

```text
Page Title                              ‹ June 2026 ›
────────────────────────────────────────────────────
```

The exact design may change, but placement and behavior should remain consistent.

---

## UX-002 — Shared Month Navigator

Create one reusable month navigation component.

Requirements:

- previous month action;
- current selected month;
- next month action;
- optional month/year picker;
- keyboard accessibility;
- consistent appearance;
- backed by the existing shared month state;
- no duplicated month logic in individual pages.

The month selector should not resemble a raw HTML date/month input if that produces poor or inconsistent presentation.

---

## UX-003 — Shared dialog system

Current account/category/edit dialogs are perceived as disorganized and inconsistent.

Create reusable primitives for:

```text
Dialog
DialogHeader
DialogBody
DialogFooter

FormField
TextInput
SelectInput
CurrencyInput
ValidationMessage

PrimaryButton
SecondaryButton
DangerButton
```

Dialogs should have consistent:

- spacing;
- title placement;
- close affordance;
- labels;
- error behavior;
- Cancel/Save placement;
- destructive action treatment;
- keyboard behavior;
- focus management.

---

## UX-004 — Avoid decorative emoji as information architecture

Account type and financial state should primarily be communicated through:

- text;
- typography;
- grouping;
- restrained icons where useful.

Do not rely on emoji to communicate account type or financial meaning.

---

## UX-005 — Responsive layout

All redesigned screens should remain usable on narrower displays.

Tables may adapt into reduced-column or stacked views, but financial values and primary actions must remain accessible.

---

## UX-006 — Accessibility

At minimum:

- keyboard-operable controls;
- visible focus states;
- properly associated labels;
- semantic buttons rather than clickable generic containers;
- accessible dialog focus handling;
- color not used as the only state signal.

---

# 6. Dashboard Requirements

## Product responsibility

The Dashboard answers:

> What should I know about my finances right now?

It should not become a dumping ground for every financial metric.

---

## DASH-001 — Financial position

The dashboard should prominently expose useful balance information.

Potential structure:

```text
Cash Available
$12,480

Credit Card Debt
$842

Net Position
$11,638
```

Exact terminology should be validated against account sign semantics.

---

## DASH-002 — Spending by category/group

Current spending by category/group should remain prominent because real use showed it to be valuable.

The dashboard should make it easy to identify:

- amount spent;
- budgeted amount where relevant;
- categories approaching budget;
- categories over budget.

---

## DASH-003 — Needs attention

The dashboard should eventually be capable of surfacing actionable items such as:

```text
3 transactions need review
2 potential transfers
Dining is over budget
1 recurring bill appears missing
```

Do not implement these until the underlying workflows exist.

Design the page so such a section can be added naturally later.

---

## DASH-004 — Planned vs actual summary

The existing planned-vs-actual total income/expense metrics should be reconsidered.

Do not preserve them merely because they currently exist.

They may be:

- removed;
- visually de-emphasized;
- moved to future Reports/Insights.

The deciding question is whether they provide information beyond Spending by Group and category-level budgeting.

---

## DASH-005 — Recent activity

Recent transactions may remain if they provide quick context.

The Dashboard should not replace Transactions as the working transaction interface.

---

# 7. Budget / Categories Requirements

## Product responsibility

The Budget page answers:

> How have I allocated money, and how am I performing against those allocations?

Category management belongs here where it directly supports budgeting.

---

## BUD-001 — Preserve category/group structure

Maintain the current conceptual hierarchy:

```text
Group
    Category
    Category
    Category
```

Do not flatten the structure merely for visual simplicity.

---

## BUD-002 — Entire group row toggles expansion

The expand/collapse target should not be limited to a small arrow.

Clicking the reasonable non-interactive area of a group row should expand/collapse it.

Interactive child controls must not accidentally toggle the row.

---

## BUD-003 — Clear creation actions

Creation should visibly distinguish:

```text
+ Add Group
+ Add Category
```

Avoid generic dialogs whose purpose is not obvious.

---

## BUD-004 — Improved editing

Category/group editing should use the shared dialog/form system or a justified inline-editing workflow.

Editing should not feel materially different from editing an account.

---

## BUD-005 — Consistent month placement

The Budget page must use the same Month Navigator and placement as the other month-scoped pages.

---

## BUD-006 — Future goals/targets

The Budget architecture should allow future category targets or savings goals without requiring a rewrite.

Examples:

```text
Emergency Fund
$8,200 / $15,000

Vacation
$1,400 / $3,500
```

Do not implement goals during the initial redesign.

---

# 8. Transactions Requirements

## Product responsibility

Transactions becomes the central operational workspace.

It answers:

> What happened to my money, and what needs review or correction?

---

## TXN-001 — Preserve existing successful workflow

Do not unnecessarily replace the current transaction table.

Preserve useful behavior including:

- month filtering;
- account filtering;
- search;
- category filtering;
- transaction editing;
- historical browsing.

---

## TXN-002 — Persist working filters

Current secondary filters are destroyed when the page unmounts.

The redesign should define session-level persistence for useful transaction filters.

Candidates include:

```text
Account
Search
Category
Uncategorized-only
Review state
Transaction type
```

Exact persistence semantics should be specified before implementation.

Requirements:

- navigating temporarily to another page should not unexpectedly destroy the user's working view;
- explicit navigation to a clean Transactions destination should still offer an understandable way to reset filters.

---

## TXN-003 — Transaction review state

Introduce a future explicit review concept:

```text
Needs Review
Reviewed
```

Imported or automatically modified transactions may enter Needs Review according to future policy.

This becomes the foundation for automation.

The UI should eventually support:

```text
All
Needs Review
Uncategorized
Potential Transfers
```

Do not overload `category IS NULL` as a permanent substitute for review state.

---

## TXN-004 — Transfer workflow

Transfer candidate discovery and confirmation should move conceptually into Transactions.

Future flow:

```text
Potential match

Checking     -$300   Sep 15
Credit Card +$300   Sep 16

[Confirm Transfer]
[Not a Match]
```

Transfer reconciliation should remain a distinct backend workflow rather than becoming a CreditCard-specific feature.

Other budgeting applications similarly model transfers as transaction/account relationships rather than ordinary spending categories.

---

## TXN-005 — Bulk actions

Future Transactions should support multi-selection where it materially reduces repetitive work.

Potential bulk operations:

- categorize;
- mark reviewed;
- mark/confirm transfer;
- add tag;
- apply merchant;
- delete where safe.

Bulk actions should not be added indiscriminately.

---

# 9. Accounts Requirements

## Product responsibility

Accounts answers:

> Where is my money or debt, and can I trust the application's representation of the account?

---

## ACC-001 — Account summary

The primary account summary should emphasize:

```text
Name
Account type
Current balance
```

Example:

```text
USAA Checking
Checking
$4,281.42
```

For a credit card:

```text
Discover
Credit Card
$842.16 owed
```

---

## ACC-002 — Group accounts meaningfully

Potential grouping:

```text
Cash / Depository
    Checking
    Savings

Credit
    Credit Cards

Later:
    Loans
    Investments
    Other Assets
```

Do not implement unsupported account types simply to match competitors.

Actual similarly treats checking and credit-card accounts as part of the broader account model rather than requiring a completely separate credit-card concept.

---

## ACC-003 — Starting balance becomes setup metadata

Starting balance remains financially important but should not occupy prominent everyday account presentation.

Move it to an account setup/editing context such as:

```text
Balance Setup
Starting Balance
```

Provide explanatory text describing what it represents.

Do not change the underlying balance formula as part of this UI change.

---

## ACC-004 — Account detail

Eventually, selecting an account should expose:

```text
Account name/type
Current balance

Recent transactions

Relevant account actions
```

For credit cards, account-specific information may additionally include:

- balance owed;
- credit balance state;
- future credit limit/utilization if supported.

Do not fabricate unsupported card attributes.

---

## ACC-005 — Credit cards are accounts

Target design assumption:

> A credit card is an Account with credit-specific behavior, not a separate top-level product area.

Before removing the current Credit Cards page:

1. inventory every useful function currently on it;
2. determine where each responsibility belongs;
3. migrate useful functionality;
4. verify no workflow is lost;
5. only then remove it from primary navigation.

---

## ACC-006 — Negative credit-card balance presentation

Current accounting can legitimately produce:

```text
balance_owed < 0
```

which represents an overpayment/credit under the current characterized behavior.

The frontend should eventually distinguish:

```text
$842.16 owed
```

from:

```text
$178.16 credit
```

rather than displaying:

```text
-$178.16 owed
```

Do not change the balance calculation without a separate domain decision.

---

# 10. Account Reconciliation

Reconciliation should be promoted from a distant feature to a meaningful Account workflow.

Other ledger-oriented budgeting applications make reconciliation part of ensuring the application's account agrees with the financial institution.

## REC-001 — Cleared state

Future transaction/account models should support the concept of transactions being:

```text
uncleared
cleared
```

as distinct from:

```text
reviewed
```

These are not the same property.

---

## REC-002 — Reconciled state

Accounts should eventually track reconciliation status/history.

Potential account presentation:

```text
Current Balance
$4,283.12

Cleared
$4,120.21

Uncleared
$162.91

Last reconciled
Sep 30, 2026

[Reconcile]
```

---

## REC-003 — Reconciliation workflow

The user should be able to:

1. enter/confirm a real institution balance;
2. compare it with the application;
3. identify unmatched/uncleared transactions;
4. resolve discrepancies;
5. confirm reconciliation.

This should be designed separately before implementation.

---

# 11. Merchant / Payee Normalization

Merchant normalization should become a first-class data concept before ML categorization.

## MER-001 — Preserve raw description

Never destroy the original imported financial description.

Example:

```text
Raw description:
SQ *STARBUCKS 019283 CA
```

---

## MER-002 — Normalized merchant/payee

Allow the transaction to additionally resolve to:

```text
Merchant:
Starbucks
```

Rules and automation can operate on this cleaner concept.

---

## MER-003 — Reusable identity

Multiple raw variants should be able to resolve to the same merchant:

```text
STARBUCKS #123
SQ *STARBUCKS 0192
STARBUCKS STORE 440

→ Starbucks
```

---

# 12. Rules System

Rules should be implemented before ML categorization.

Competitor systems demonstrate the value of deterministic transaction processing and merchant cleanup before more advanced intelligence.

## RULE-001 — Conditions and actions

Potential rule:

```text
WHEN
merchant = Starbucks

THEN
category = Coffee
```

Future conditions may include:

- merchant;
- raw description;
- account;
- amount range;
- transaction type.

Do not build every possible rule condition initially.

---

## RULE-002 — Rule preview

Before applying a rule retroactively, display what it matches.

Example:

```text
This rule matches 14 transactions.

Sep 18   COSTCO #1032      $82.13
Sep 02   COSTCO WHSE       $97.48
...

[Future transactions only]

[Apply to 14 existing transactions and future transactions]
```

---

## RULE-003 — Deterministic precedence

Rule ordering/conflict semantics must be explicit.

Do not allow unpredictable outcomes when multiple rules modify the same property.

---

# 13. Transaction Type — Domain Investigation Required

Before implementing deeper transfer/income automation, investigate whether transactions need an explicit semantic type.

Candidate:

```text
EXPENSE / REGULAR
INCOME
TRANSFER
```

Competitor systems such as Copilot explicitly distinguish income, internal transfers, and regular transactions, with transfers excluded from spending categorization.

## DOMAIN-001 — Do not implement yet

This is not an approved schema migration.

Investigate:

- current sign semantics;
- category semantics;
- income categories;
- transfer reconciliation;
- refunds;
- credit-card payments;
- reporting behavior;
- budget calculations.

Determine whether an explicit type reduces ambiguity or merely duplicates existing information.

Produce a separate domain decision before changing persistence.

---

# 14. Recurring / Scheduled Transactions

Recurring functionality should follow the foundational transaction work.

Lunch Money and similar products use recurring items not only for display but to match expected activity and support projected finances.

## RECUR-001 — Recurring definition

Future recurring entries should support:

- merchant/payee;
- expected amount or range;
- cadence;
- next expected date;
- optional start/end;
- active/inactive status.

---

## RECUR-002 — Matching

Imported transactions should eventually be matchable to expected recurring items.

Example:

```text
Expected
Netflix
Oct 8
$15.99

Imported
NETFLIX.COM
Oct 8
$15.99

→ matched
```

---

## RECUR-003 — Status

Potential statuses:

```text
Upcoming
Matched/Paid
Late/Missing
Skipped
```

Exact semantics require a dedicated design.

---

# 15. Split Transactions

Future transactions should support splitting one financial event across multiple categories.

Example:

```text
Costco                         $247.82

Groceries                      $142.30
Household                       $67.42
Clothing                        $38.10
```

Requirements should eventually include:

- child amounts sum exactly to transaction amount;
- editing remains auditable;
- budget calculations use split allocations correctly;
- original transaction identity remains intact.

This feature should not precede merchant/rules/review foundations.

---

# 16. ML Categorization

ML should enhance the Transactions workflow rather than become its own page.

Copilot's current categorization model also uses prior reviewed behavior and allows user corrections to improve future predictions, which supports the review-feedback architecture proposed here.

## ML-001 — Inputs

Potential model features:

```text
normalized merchant
raw description text
account
amount
direction/sign
day/date context
historical user categories
```

Only use features proven useful through experimentation.

---

## ML-002 — Baseline first

Create deterministic baselines before sophisticated models.

Suggested progression:

```text
merchant historical majority
        ↓
rules
        ↓
TF-IDF / linear classifier baseline
        ↓
more advanced model only if justified
```

---

## ML-003 — Metrics

Evaluate at minimum:

```text
Top-1 accuracy
Top-3 accuracy
Per-category precision
Per-category recall
Coverage
Confidence calibration
```

---

## ML-004 — Abstention

The model must be allowed to say:

```text
I am not confident enough.
```

Example:

```text
confidence >= approved threshold
    → suggest category

confidence < threshold
    → Needs Review
```

Do not optimize solely for forcing a prediction onto every transaction.

---

## ML-005 — Feedback loop

User corrections should become future learning data.

Maintain enough provenance to distinguish:

```text
user-selected
rule-selected
ML-suggested
ML-suggestion accepted
ML-suggestion corrected
```

Exact persistence design should be determined when the ML project begins.

---

# 17. Upload Requirements

Real-use feedback indicates Upload is currently successful.

## UP-001

Preserve the existing core workflow.

Do not redesign behavior solely to achieve visual novelty.

---

## UP-002

Bring Upload into the shared visual system:

- typography;
- buttons;
- dialogs;
- spacing;
- error presentation;
- page header.

---

## UP-003

Future automation should not hide import review.

CSV remains useful because it gives users explicit control over what enters the system.

---

# 18. Reports / Insights — Future Phase

Do not overload Dashboard with historical analytics.

A future Reports/Insights area may eventually answer:

```text
How has spending changed?
What are my largest merchants?
How is my net worth changing?
What is my savings rate?
What categories are trending upward?
```

Dedicated analytics products commonly provide flexible filtering by accounts, categories, merchants/payees, and other dimensions rather than forcing every report into the main dashboard.

Potential future capabilities:

- spending trends;
- category history;
- merchant analysis;
- income/expense trends;
- net worth;
- savings rate;
- custom date ranges;
- CSV export;
- saved report filters.

Build this only after the underlying transaction/account data is mature.

---

# 19. Tags — Later Feature

Tags should remain distinct from categories.

Example:

```text
Transaction:
Restaurant

Category:
Dining

Tags:
Hawaii
Vacation
```

Tags answer cross-category questions without damaging the budgeting taxonomy.

Do not prioritize this ahead of review state, reconciliation, rules, recurring items, or splits.

---

# 20. Design System / Component Strategy

The redesign should introduce reusable components only where repetition is demonstrated.

Likely justified shared components:

```text
PageHeader
MonthNavigator

AppDialog
FormField

Button variants
Input
Select
CurrencyInput

AccountSummary
EmptyState
ErrorState
LoadingState
```

Avoid prematurely creating a large internal component framework.

Build components as repeated design patterns emerge.

---

# 21. Implementation Roadmap

## Phase 0 — Close current baseline

Goal:

Formally freeze the stable CSV-first product baseline.

Tasks:

- complete documentation updates;
- record acceptance findings;
- ensure clean test suite;
- establish baseline commit/tag if useful;
- preserve known deferred decisions.

Exit condition:

```text
CSV-first baseline documented and reproducible.
```

---

# Phase 1 — Frontend design foundation

Goal:

Fix systemic inconsistencies before rebuilding individual pages.

Deliver:

- typography system;
- spacing conventions;
- button styles;
- form controls;
- dialog system;
- page headers;
- Month Navigator;
- loading/error/empty states.

Avoid changing page responsibilities during this phase.

Exit condition:

Shared primitives are proven in at least one real screen and do not exist merely as speculative abstractions.

---

# Phase 2 — Budget / Categories redesign

Why first:

The concept works, and its friction is well understood.

Deliver:

- shared month header;
- whole-row expand/collapse;
- improved group creation;
- improved category creation;
- standardized editing dialogs/forms;
- visual cleanup.

Preserve business behavior.

Exit condition:

Routine budget/category management no longer feels cumbersome.

---

# Phase 3 — Dashboard redesign

Deliver:

- cash/account overview;
- credit debt summary if semantics support it;
- spending-by-group/category;
- categories needing attention;
- optional recent activity;
- remove/de-emphasize redundant planned-vs-actual summaries.

Exit condition:

Dashboard communicates information the user actually finds useful within seconds.

---

# Phase 4 — Transactions UX foundation

Deliver:

- visual alignment with redesign;
- filter persistence;
- improved filter controls;
- transaction detail/edit interaction;
- architecture ready for review state;
- architecture ready for transfers and bulk actions.

Do not implement ML yet.

Exit condition:

Transactions remains at least as effective as the current workflow and provides a clean platform for automation.

---

# Phase 5 — Accounts consolidation

Deliver:

- redesigned Accounts screen;
- no emoji-driven account identification;
- useful account grouping;
- name/type/current balance emphasis;
- starting balance moved to setup/editing;
- credit-card accounts integrated;
- credit-card negative balance displayed appropriately;
- account detail experience.

Inventory/migrate useful Credit Cards functionality before removing that page.

Exit condition:

A user does not need a separate page simply to understand a credit-card account.

---

# Phase 6 — Transaction review + transfer workflow

Deliver:

- Needs Review / Reviewed;
- transfer candidate presentation;
- transfer confirmation/rejection;
- move transfer discovery away from Credit Cards;
- begin multi-select/bulk review if justified.

Exit condition:

The user has a clear transaction inbox/work queue.

---

# Phase 7 — Account reconciliation

Deliver:

- cleared/uncleared transaction concept;
- cleared/uncleared balances;
- reconciliation workflow;
- last-reconciled state.

Exit condition:

The user can verify the application's account ledger against the institution.

---

# Phase 8 — Merchant normalization

Deliver:

- raw description preservation;
- normalized merchant/payee;
- manual merchant correction;
- reuse normalized merchant identity.

Exit condition:

Repeated merchant variants no longer require repeated manual interpretation.

---

# Phase 9 — Rules

Deliver:

- initial rule conditions;
- deterministic actions;
- preview;
- future-only vs retroactive application;
- rule ordering/conflict semantics.

Exit condition:

Common repetitive categorization/cleanup can be automated without ML.

---

# Phase 10 — ML categorization

Deliver:

- dataset extraction;
- baseline;
- training/evaluation pipeline;
- confidence calibration;
- transaction category suggestions;
- abstention;
- correction feedback.

Exit condition:

ML demonstrably improves on deterministic baselines without creating unacceptable silent errors.

---

# Phase 11 — Recurring items

Deliver:

- recurring definition;
- expected schedule;
- imported transaction matching;
- upcoming/missing status.

Exit condition:

Recurring obligations can be tracked without manual monthly reconstruction.

---

# Phase 12 — Split transactions

Deliver:

- split editing;
- multiple category allocation;
- budget integration;
- correct reporting.

---

# Phase 13 — Financial depth

Prioritize based on actual usage:

```text
Goals
Tags
Net worth
Reports / Insights
Forecasting
```

Do not commit to implementing all of them.

---

# 22. Mandatory Domain Decisions Before Relevant Implementation

Some issues require deliberate decisions rather than incidental frontend changes.

## DD-001 — Transaction semantic type

Determine whether explicit:

```text
Income
Expense/Regular
Transfer
```

is justified.

---

## DD-002 — Credit-card balance semantics

Document:

- starting balance meaning;
- current balance formula;
- future-dated transaction behavior;
- credit/overpayment semantics.

---

## DD-003 — Transfer semantics

Define:

- eligible account combinations;
- amount matching rules;
- date tolerance;
- ambiguous matches;
- one-to-many possibilities;
- credit-card payment treatment;
- effects on budgeting/reporting.

Do not silently preserve a greedy/order-dependent algorithm forever if real use exposes ambiguity.

---

## DD-004 — Review semantics

Define what causes a transaction to become or remain:

```text
Needs Review
Reviewed
```

Examples requiring policy:

- manually entered;
- CSV imported;
- rule-categorized;
- ML-categorized;
- transfer matched;
- edited after review.

---

## DD-005 — Reconciliation semantics

Define:

```text
cleared
reconciled
reviewed
```

as separate concepts where appropriate.

---

# 23. Testing Strategy

Each vertical slice should follow:

```text
characterize current behavior
        ↓
implement focused change
        ↓
focused tests
        ↓
frontend build
        ↓
full backend regression
        ↓
browser/user-flow verification
        ↓
review
        ↓
commit
```

Do not accumulate an entire redesign into one giant change.

---

# 24. UX Acceptance Testing

After each redesigned workflow, test the actual task rather than only screenshots.

Examples:

### Budget

```text
Create group
Create category
Expand/collapse
Assign budget
Change month
Edit category
```

### Transactions

```text
Filter account
Search
Change category
Leave page
Return
Confirm filters behave as designed
```

### Accounts

```text
Understand account balance
Edit account
Understand starting balance
Open credit card
Interpret credit balance
```

### Dialogs

```text
Open
Cancel
Save
Validation error
Keyboard navigation
Escape/close
```

---

# 25. Non-Goals for the Initial Redesign

Do not bundle these into the first frontend redesign:

- investment portfolio tracking;
- cryptocurrency;
- multi-currency architecture;
- family/multi-user collaboration;
- tax preparation;
- advanced forecasting engine;
- financial advice;
- full mobile-native application;
- complete reporting suite;
- LLM categorization;
- speculative provider abstraction.

They can be revisited if real requirements emerge.

---

# 26. Product Success Criteria

The redesign succeeds if the user can answer these questions quickly.

## Dashboard

```text
How much money do I have?
How much credit-card debt do I have?
Where am I spending money?
What needs my attention?
```

## Budget

```text
What did I plan?
How much have I used?
Which categories need adjustment?
```

## Transactions

```text
What happened?
What needs review?
What category does it belong to?
Is this a transfer?
```

## Accounts

```text
What accounts do I have?
What are their balances?
Can I trust those balances?
```

## Upload

```text
What am I importing?
Where will it go?
Did it import correctly?
```

If a screen cannot clearly answer its assigned questions, its design should be reconsidered.

---

# 27. Prioritization Summary

## Must do next

```text
1. Finalize planning documentation
2. Frontend design foundation
3. Budget/Categories redesign
4. Dashboard redesign
5. Transactions UX foundation
6. Accounts/Credit Cards consolidation
```

## High-value next capabilities

```text
7. Transaction review state
8. Transfer review
9. Account reconciliation
10. Merchant normalization
11. Rules
```

## Intelligence

```text
12. ML categorization
```

## Mature budgeting features

```text
13. Recurring transactions
14. Split transactions
15. Goals
16. Tags
17. Net worth
18. Reports / analytics
19. Forecasting
```

The order beyond the foundation should remain responsive to actual use.

---

# 28. Decision Register

### Accepted direction

- CSV-first workflow remains supported.
- Redesign is driven by real-use friction.
- Transactions is the primary transaction-management workspace.
- Accounts should represent credit cards as accounts.
- Transfer review belongs with Transactions rather than being owned by Credit Cards.
- Starting balance should become setup/accounting metadata rather than primary account information.
- Dashboard should emphasize balances, category spending, and actionable information.
- Month navigation needs one consistent component.
- Dialogs/forms need a shared interaction pattern.
- Deterministic automation should precede ML.
- ML should support confidence and abstention.
- Reconciliation should become an Account workflow.

### Proposed direction requiring prototype validation

- Remove Credit Cards from primary navigation after its useful responsibilities are migrated.
- De-emphasize/remove planned-vs-actual total cards from Dashboard.
- Persist secondary transaction filters for the working session.
- Add Dashboard "Needs Attention" as supporting features become available.

### Domain investigation required

- explicit Transaction type;
- transfer matching semantics;
- credit-card balance/future-date semantics;
- review-state semantics;
- reconciliation state semantics.

### Intentionally later

- recurring items;
- transaction splits;
- tags;
- savings goals;
- net worth;
- reports;
- forecasting.

---

# 29. Guiding Product Architecture

The target application should eventually feel like:

```text
                       BUDGET APP
                           │
          ┌────────────────┼────────────────┐
          │                │                │
       Planning         Activity         Position
          │                │                │
        Budget         Transactions       Accounts
                           │                │
                    Review / Rules      Reconcile
                    Transfers           Balances
                    Categorize          Debt
                    ML Suggestions
          │                │                │
          └────────────────┼────────────────┘
                           │
                       Dashboard
                  useful current summary

                           │
                         Upload
                      data ingestion

                           │
                    Future Insights
                   historical analysis
```

The purpose of the redesign is not merely to make this application prettier.

The purpose is to create a stable product structure in which future capabilities—automation, recurring transactions, reconciliation, reporting, and ML categorization—have obvious homes and can be added without repeatedly reorganizing the application.