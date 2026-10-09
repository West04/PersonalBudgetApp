# Correctness Backlog

**Status:** Canonical. Single source of truth for confirmed correctness, reliability,
accessibility and product-semantic issues remaining after the backend modernization and
the frontend redesign.
**Verified against:** `e312824` (`add frontend themes`), 2026-10-09.
**Line numbers** refer to that commit and will drift; search for the quoted identifiers.

Future roadmap features (Savings Goals, Tags, Net Worth, Reporting, Cash Flow
Forecasting) live in [`docs/TODO.md`](TODO.md) under "Milestone 3" and are out of scope here.

---

## Program state and guardrails

```text
Backend/VBD modernization:            COMPLETE
Correctness/security hardening:       COMPLETE
Frontend redesign:                    COMPLETE
```

New implementation work comes only from confirmed defects, explicit product requirements,
accessibility issues or planned features. Nothing in this backlog reopens a completed
program.

### Frontend redesign freeze

The frontend redesign is complete.

Correctness fixes may change presentation only when required to represent the corrected
state accurately.

Do not perform opportunistic visual cleanup, restyling, theme changes, or component
extraction while fixing backlog items.

### Backend / VBD guardrail

The backend architecture modernization is complete. For fixes:

- use the existing Manager / Engine / Accessor boundaries (`AGENTS.md`, `docs/architecture/`);
- do not introduce speculative repositories, Unit of Work, DI, event buses or new layers;
- make a structural change only when a confirmed defect demonstrates a real boundary problem.

Do not turn correctness fixes into modernization work.

### One defect per implementation slice

```text
For correctness implementation:

analysis
→ characterize/reproduce
→ add or identify regression coverage
→ implement smallest fix
→ run focused tests
→ run maintained suite
→ independent review
→ PASS
→ commit
→ /clear
```

Default to **one defect per slice**. Combine defects only if they share the same root
cause and the same safe change boundary.

Note: several `tests/test_frontend_*.py` source-contract tests pin the exact current
template/script text of defective code (for example the Finish button `:disabled`
expression, `alert(\`Import failed:` count, `candidates.splice(idx, 1)`). A fix slice
must update those assertions deliberately, not delete them.

---

## Priority model

| Priority | Meaning |
| --- | --- |
| P1 | UI state can disagree with persisted/server state, materially wrong financial/date behavior, or a consequential duplicate operation |
| P2 | Confirmed correctness or failure-state bug with meaningful user impact, lower immediate risk |
| P3 | Confirmed non-critical correctness/accessibility/SSR issue |
| PRODUCT | Internally consistent behavior; desired semantics need a decision |
| UX | Non-critical workflow/accessibility issue |
| DOCS | Documentation or housekeeping only |

---

## Summary

| ID | Priority | Area | Issue | Status | Next action |
| --- | --- | --- | --- | --- | --- |
| COR-001 | P1 | Reconciliation | Clear All shows every row cleared after a PATCH failure | Confirmed | Analyze then fix |
| COR-002 | P2 | Reconciliation | Finish Reconciliation can be enabled when the summary failed to load | Confirmed | Analyze then fix |
| COR-003 | P2 | Credit Cards | Transfer Confirm has no in-progress lock; index-based removal can hide the wrong candidate | Confirmed | Analyze then fix |
| COR-004 | P2 | Reconciliation | Default statement ending date is the UTC date, not the local date | Confirmed | Analyze then fix |
| COR-005 | P2 | Import | Confirm has no re-entrancy guard; backend duplicate check is not concurrency-safe | Confirmed | Analyze then fix |
| COR-006 | P2 | Accounts | Card-summary load failure silently falls back to stored `current_balance` | Confirmed | Analyze then fix |
| COR-007 | P2 | Import | Account-list load failure is not represented (empty/stray options, unhandled rejection) | Confirmed | Analyze then fix |
| COR-008 | P3 | Settings | `/category-groups` load failure leaves rule category selects silently empty | Confirmed | Analyze then fix |
| COR-009 | P3 | Accounts | Card-summary month computed in UTC | Confirmed | Analyze then fix |
| COR-010 | P3 | Credit Cards | Failed month change keeps previous month's data (accurately labelled) | Confirmed | Defer |
| COR-011 | P3 | Settings | "Last trained" hydration mismatch from `toLocaleString()` | Confirmed | Analyze then fix |
| COR-012 | P3 | Dashboard, Transactions | Hydration mismatch warnings on `server: false` loading states | Needs focused investigation | Focused analysis only |
| PROD-001 | PRODUCT | Dashboard | Income groups appear under "Spending by group" with spending language | Product decision required | Product decision required |
| PROD-002 | PRODUCT | Budget | Group totals sum income/expense/transfer categories together | Product decision required | Product decision required |
| PROD-003 | PRODUCT | Accounts | Inactive credit cards always show stored `current_balance`, not `balance_owed` | Product decision required | Product decision required |
| UX-001 | UX | Budget | Drag reorder has no keyboard alternative | Confirmed | Accessibility design decision required |
| UX-002 | UX | Budget | Planned input loses focus to the document on Enter/Escape | Confirmed | Accessibility design decision required |
| UX-003 | UX | Transactions | Merchant edit does not return focus to the edit trigger | Confirmed | Analyze then fix |
| UX-004 | UX | Transactions | Recurring tabs lack arrow-key tab navigation | Confirmed | Accessibility design decision required |
| UX-005 | UX | Import | Import failure uses native `alert()` | Confirmed | Defer |
| UX-006 | UX | Budget, Accounts | Destructive deletes use native `confirm()` | Confirmed | Defer |
| UX-007 | UX | Settings | Success/retrain feedback renders at page top, can be off-screen on mobile | Confirmed | Defer |
| DOC-001 | DOCS | Docs | `frontend_design_foundation.md` has stale pre-redesign statements | Confirmed | Documentation cleanup |
| DOC-002 | DOCS | Docs | `AGENTS.md` omits `themes.css` and `useTheme.ts` | Confirmed | Documentation cleanup |
| DOC-003 | DOCS | Docs | `AGENTS.md` required reading points at git-ignored files | Confirmed | Documentation cleanup |

---

## Recommended execution order

1. **COR-001** — persisted/UI cleared-state mismatch (only P1).
2. **COR-002** — reconciliation action enabled on unknown state (same dialog, separate root cause; separate slice).
3. **COR-003** — Credit Cards transfer list can diverge from server state.
4. **COR-004** — wrong default date persisted as `last_reconciled_date`.
5. **COR-005** — duplicate import window.
6. **COR-006**, **COR-007** — failed loads presented as valid data.
7. **COR-008**, **COR-009**, **COR-010** — lower-impact failure/date states.
8. **COR-011**, then **COR-012** analysis — hydration.
9. **UX-001 … UX-004** — accessibility debt (each needs an interaction decision first).
10. **PROD-001 … PROD-003** — whenever the product owner decides; not blocking.
11. **UX-005 … UX-007** — native dialogs and feedback placement.
12. **DOC-001 … DOC-003** — housekeeping; can be done in one docs slice.

---

## Confirmed correctness items

### COR-001 — Reconciliation Clear All can show rows cleared after a PATCH failure

Priority: P1
Area: Accounts → Reconcile dialog (`frontend/app/pages/accounts.vue`)
Classification: CONFIRMED DEFECT (pre-existing; untouched by the redesign)
Status: Confirmed

Observed behavior:
`toggleClearAll` (≈ line 759) loops over rows whose `is_cleared` differs from the target,
sets `tx.is_cleared = targetStatus` optimistically, then sends one
`PATCH /transactions/{id}/cleared` per row sequentially. A failed PATCH is only
`console.warn`-ed: the row is not rolled back and `reconcileError` is not set. There is
also no in-progress lock, so the user can toggle rows or press Finish while the loop runs.
Single-row `toggleTxCleared` does roll back and report errors; Clear All does not.

Expected behavior:
After Clear All, each row's displayed cleared state matches the server, and any failure is
reported to the user.

Evidence / reproduction:
Open Reconcile on an account with several unreconciled transactions; make one PATCH fail
(stop the backend mid-loop, or force a 4xx/5xx for one id). All checkboxes show cleared,
the cleared balance/difference are computed from the wrong set, and no error is shown.
Finish may then be enabled; the backend (`complete_reconciliation` in
`backend/managers/account_reconciliation_manager.py`) recomputes from persisted state and
rejects with "Cannot complete reconciliation: statement ending balance … does not match
cleared balance", so wrong persistence is prevented, but the dialog keeps showing the
false cleared state until it is reopened.

Risk:
UI disagrees with persisted state in a financial workflow; user cannot tell which rows
actually cleared. Server-side guard limits the damage to confusion and a rejected Finish.

Scope guard:
Fix Clear All state consistency and failure reporting only.
Do not redesign the reconciliation dialog.
Do not change reconciliation arithmetic or the backend completion guard.
Do not batch the PATCH endpoint or add new backend endpoints unless analysis proves it necessary.
Do not touch COR-002 in the same slice.

Existing test coverage:
Source-contract only: `tests/test_frontend_reconciliation.py` (`toggleClearAll` and
"Clear All" exist), `tests/test_frontend_import_redesign.py` (`@click="toggleClearAll"`).
No regression test of failure behavior.

Recommended next step:
Analyze then fix

---

### COR-002 — Finish Reconciliation can be enabled when the summary failed to load

Priority: P2
Area: Accounts → Reconcile dialog (`frontend/app/pages/accounts.vue`)
Classification: CONFIRMED DEFECT
Status: Confirmed

Observed behavior:
Finish is disabled by `!isBalanced || completingReconcile || reconcileLoading`
(≈ line 364). When `reconcileSummary` is `null` (load failed), `calculatedClearedBalance`
returns `0`, so `differenceAmount = endingBalance - 0`. With a statement balance of `0`
(the default is the account's `current_balance`, so a zero-balance account qualifies),
`isBalanced` is true and Finish is enabled while the dialog shows the values as
"Not available".
Variant: if the first load succeeds and a later reload fails (changing the ending date
calls `loadReconciliation`), `reconcileSummary` is not cleared, so the previous date's
transactions and difference stay on screen and drive the enable rule.

Expected behavior:
Finish is only available when the reconciliation state for the current inputs is known.

Evidence / reproduction:
Open Reconcile with the backend's `/accounts/{id}/reconciliation` failing and the
statement balance at `0`: the error banner shows, figures read "Not available", Finish is
enabled. The redesign deliberately changed only the presentation
(`test_reconciliation_load_error_is_not_empty_or_zero`) and preserved the enable rule.
Backend `complete_reconciliation` recomputes and rejects unbalanced completions, so an
unbalanced reconciliation cannot be persisted; a completion the server considers balanced
can be committed without the user having seen the transactions.

Risk:
Action enabled on unknown state. Backend guard prevents persisting an unbalanced
reconciliation, which is why this is P2 rather than P1.

Scope guard:
Fix the enable rule / stale-summary handling only.
Do not redesign the dialog or change reconciliation arithmetic.
Do not change the backend guard.
Do not combine with COR-001 (different root cause).

Existing test coverage:
Source-contract tests pin the current expression:
`tests/test_frontend_import_redesign.py` asserts
`:disabled="!isBalanced || completingReconcile || reconcileLoading"`;
`tests/test_frontend_reconciliation.py` checks `:disabled="!isBalanced`. Backend guard is
covered by `tests/test_manager_account_reconciliation.py` /
`tests/test_integration_account_reconciliation.py`. No frontend regression test for the
failure state.

Recommended next step:
Analyze then fix

---

### COR-003 — Credit Cards transfer Confirm has no lock; index-based removal can hide the wrong candidate

Priority: P2
Area: Credit Cards → Potential transfers (`frontend/app/pages/credit-cards.vue`)
Classification: CONFIRMED DEFECT
Status: Confirmed

Observed behavior:
`confirmTransfer(pair, idx)` (≈ line 332) has no in-progress flag and the Confirm button
has no `:disabled`. After the POST it runs `candidates.value.splice(idx, 1)` using the
index captured at click time. Two activations before the first completes (same row
twice, or two different rows) each splice by a stale index, so a different, unconfirmed
candidate disappears from the list while a confirmed one can stay visible.
Transactions' equivalent flow has a `confirmingPair` guard (`transactions.vue` ≈ line 904).

Expected behavior:
One submission per pair at a time, and the list removes exactly the pair that was confirmed.

Evidence / reproduction:
`POST /credit-cards/mark-transfers` → `transaction_access.mark_transactions_as_transfers`
is an idempotent bulk `is_transfer = True`, so a duplicate request causes no persisted
damage. The defect is the client list diverging from server state: an unconfirmed
candidate is hidden (until "Find transfer matches" is run again).

Risk:
User believes a suggestion was handled when it was only hidden; it is not a duplicate
financial write. P2, not P1, because persisted state stays correct.

Scope guard:
Fix the Credit Cards confirm lock and candidate removal only.
Do not change the transfer-matching heuristic or the backend endpoint.
Do not refactor Credit Cards and Transactions into a shared component.
Do not change Dismiss behavior unless the same root cause requires it.

Existing test coverage:
Source-contract only: `tests/test_frontend_accounts_cards_redesign.py` asserts
`@click="confirmTransfer(pair, idx)"` and `@click="candidates.splice(idx, 1)"`.
Backend marking covered by `tests/test_characterization_transfers.py`.

Recommended next step:
Analyze then fix

---

### COR-004 — Reconciliation default ending date uses the UTC date

Priority: P2
Area: Accounts → Reconcile dialog (`frontend/app/pages/accounts.vue`)
Classification: CONFIRMED DEFECT (pre-existing)
Status: Confirmed

Observed behavior:
`reconcileForm.endingDate` is initialised with `new Date().toISOString().slice(0, 10)`
(≈ lines 660 and 671). West of UTC in the evening this is tomorrow's date; east of UTC
early in the day it is yesterday's.

Expected behavior:
The default is the user's local calendar date.

Evidence / reproduction:
With a US timezone after ~17:00–20:00 local, open Reconcile: the date shows tomorrow.
If the user accepts it, `complete_reconciliation` persists it as
`account.last_reconciled_date`, shown on Accounts as "Last reconciled …". Eligibility is
`date <= statement_ending_date` over unreconciled transactions, so no transaction is lost,
but a wrong date is persisted and transactions dated tomorrow would be included.
A local helper already exists for months (`getLocalMonthString` in
`composables/useBudgetMonth.ts`).

Risk:
Wrong persisted reconciliation date with a plausible default the user is unlikely to check.

Scope guard:
Fix the default date only.
Do not change backend date handling or reconciliation eligibility.
Do not sweep every date call in the app; COR-009 is a separate slice.

Existing test coverage:
No direct coverage (`tests/test_frontend_import_redesign.py` only pins the
`v-model="reconcileForm.endingDate"` binding).

Recommended next step:
Analyze then fix

---

### COR-005 — Import confirm has no re-entrancy guard; duplicate check is not concurrency-safe

Priority: P2
Area: Import (`frontend/app/pages/upload.vue`), CSV import backend
Classification: CONFIRMED DEFECT
Status: Confirmed

Observed behavior:
`runImport` (≈ line 1273) sets `importing = true` but never returns early when
`importing` is already true. The button is disabled via `:disabled="… || importing"`,
which only takes effect after Vue re-renders, so two calls that start before that render
(programmatic, assistive tech, or a second tab) both POST `/upload/confirm`.
Backend duplicate detection is check-then-insert (`csv_import_transaction_exists` in
`backend/access/transaction_access.py`, used by `csv_import_manager`); there is no
database unique constraint on `(account_id, date, amount, description)`, so two
concurrent requests can both see "not existing" and both insert.

Expected behavior:
One import per confirmation; concurrent duplicates are not persisted.

Evidence / reproduction:
An ordinary double-click is normally blocked once the button disables. Reproduce by
invoking the confirm handler twice in the same tick, or by submitting the same file from
two tabs at the same moment. Sequential re-imports are correctly skipped as duplicates.

Risk:
Duplicate transactions would distort balances and budget actuals. Reachability through
the normal UI is low, which keeps this at P2.

Scope guard:
Fix duplicate-submission risk only.
Analysis must decide whether the frontend guard alone is sufficient or whether the
backend needs a concurrency-safe check; do not add a DB constraint without checking
existing data and `known-invariants.md` (legitimate identical rows may exist).
Do not redesign the Import wizard. Do not change UX-005 (alert) in the same slice.

Existing test coverage:
Source-contract: `tests/test_frontend_import_redesign.py` pins
`:disabled="preview.valid_rows === 0 || importing"`. Sequential dedupe covered by
`tests/test_manager_csv_import.py` / `tests/test_characterization_csv_import.py`.
No concurrency test.

Recommended next step:
Analyze then fix

---

### COR-006 — Accounts card-summary failure silently falls back to stored `current_balance`

Priority: P2
Area: Accounts (`frontend/app/pages/accounts.vue`)
Classification: CONFIRMED DEFECT (failure-state)
Status: Confirmed

Observed behavior:
`fetchAccounts` (≈ line 437) loads `/credit-cards/summary` with a `.catch` that only
`console.warn`s and returns `null`. `getAccountBalance` then shows
`formatCardBalance(account.current_balance)` for every credit card, with no indication
that the authoritative figure is missing.

Expected behavior:
When `balance_owed` is unavailable, the page does not present a different figure as if it
were the card balance.

Evidence / reproduction:
For non-Plaid credit cards `current_balance` is the stored value set at account creation
(Accounts sends `current_balance: startingBalance`; `account_summary_manager` keeps the
stored balance for non-depository accounts, and CSV import does not update it). So on
summary failure a manual card shows its opening balance instead of its ledger-derived
`balance_owed`. Force `/credit-cards/summary` to fail and reload Accounts: card balances
change with no visible error.

Risk:
Materially wrong debt figure shown without warning on failure. P2 because it only occurs
when the summary request fails.

Scope guard:
Fix failure representation for active credit cards only.
Do not decide inactive-card semantics here (PROD-003).
Do not change backend balance policy or `formatCardBalance`.

Existing test coverage:
No direct coverage of the fallback.

Recommended next step:
Analyze then fix

---

### COR-007 — Import account-list load failure is not represented

Priority: P2
Area: Import step 2 (`frontend/app/pages/upload.vue`)
Classification: CONFIRMED DEFECT
Status: Confirmed

Observed behavior:
`fetchAccounts` (≈ line 926) uses raw `fetch` with `try/finally` and no `catch` and no
`res.ok` check:
- HTTP error: `accounts.value = await res.json()` assigns the error body (e.g.
  `{ detail: … }`); `v-for="acct in accounts"` iterates the object and renders stray
  options with empty names;
- network error: the rejection escapes `onMounted` as an unhandled error;
- in both cases the select shows only "Select an account" / "Create new account…", with
  no message that loading failed.

Expected behavior:
A failed load is shown as a failure with a way to recover, not as an empty or malformed list.

Evidence / reproduction:
Stop the backend (network error) or make `/accounts/` return 500, then go to Import step 2.

Risk:
User may create a duplicate account believing none exist, or pick a malformed option.

Scope guard:
Fix account-load failure handling on Import only.
Do not migrate the page from `fetch` to `$fetch` wholesale.
Do not redesign step 2.

Existing test coverage:
No direct coverage.

Recommended next step:
Analyze then fix

---

### COR-008 — Settings category-group load failure leaves rule selects silently empty

Priority: P3
Area: Settings → Categorization rules (`frontend/app/pages/settings.vue`)
Classification: CONFIRMED DEFECT (failure-state)
Status: Confirmed

Observed behavior:
`const { data: categoryGroups } = await useFetch(…/category-groups)` (≈ line 459) ignores
`error`. On failure the Add/Edit Rule category `<select>` has only
"Select a category...", and `getCategoryGroupName` returns `''` for rule rows.

Expected behavior:
The user is told categories failed to load.

Evidence / reproduction:
Make `/category-groups` fail and open Add Rule.

Risk:
Rule creation/editing is blocked without explanation. No wrong data is written, and the
rules workflow is secondary to budgeting, so P3.

Scope guard:
Surface the load failure only.
Do not restructure Settings data loading or rule dialogs.

Existing test coverage:
Source-contract: `tests/test_frontend_settings_redesign.py` pins the `useFetch` call text.
No failure coverage.

Recommended next step:
Analyze then fix

---

### COR-009 — Accounts card-summary month computed in UTC

Priority: P3
Area: Accounts (`frontend/app/pages/accounts.vue`)
Classification: CONFIRMED DEFECT (low impact)
Status: Confirmed

Observed behavior:
`const currentMonth = new Date().toISOString().slice(0, 7)` (≈ line 441) can name the
next month (west of UTC, evening of the last day) or the previous month (east of UTC,
early on the 1st).

Expected behavior:
The local month, as elsewhere (`getLocalMonthString`).

Evidence / reproduction:
Accounts only uses `balance_owed` from the response. The backend cutoff is
`min(month_end, today + 1)` (`determine_effective_cutoff` in `backend/domain/dates.py`),
so a next-month request gives the same cutoff as the correct month. The only divergence
is the previous-month case (east of UTC, a few hours on the 1st): transactions dated that
day are excluded from `balance_owed`.

Risk:
Narrow window, small effect. Downgraded from the seed's P1/P2 after verifying the
backend cutoff.

Scope guard:
Replace the month derivation only.
Do not change backend cutoff semantics. Not combined with COR-004 (different value,
different consumer).

Existing test coverage:
No direct coverage.

Recommended next step:
Analyze then fix

---

### COR-010 — Credit Cards failed month change keeps previous month's data

Priority: P3
Area: Credit Cards (`frontend/app/pages/credit-cards.vue`)
Classification: CONFIRMED UX/RELIABILITY ISSUE
Status: Confirmed

Observed behavior:
`fetchSummary` does not clear `summary` on error, so the previous month's cards remain
while MonthNavigator shows the new month and an ErrorBanner shows the error.

Expected behavior:
Data is never presented as belonging to a month it does not.

Evidence / reproduction:
The redesign added `monthLabel = formatMonthDisplay(summary.value?.month ?? selectedMonth.value)`
(≈ line 299), used in "Balances through {monthLabel}" and "Transactions in {monthLabel}",
so stale data is labelled with its real month. Mismatch remains between the navigator
and the content heading.

Risk:
Low: the data is accurately labelled and an error is shown. Downgraded from P2.

Scope guard:
If addressed, change failure-state representation only. Do not redesign MonthNavigator.

Existing test coverage:
Source-contract: `tests/test_frontend_accounts_cards_redesign.py` asserts the
`monthLabel` expression.

Recommended next step:
Defer

---

### COR-011 — Settings "Last trained" hydration mismatch

Priority: P3
Area: Settings → ML (`frontend/app/pages/settings.vue`)
Classification: CONFIRMED DEFECT (SSR, pre-existing)
Status: Confirmed

Observed behavior:
`formatTrainedDate` (≈ line 506) returns `new Date(d).toLocaleString()`. `/ml/status` is
fetched with SSR-enabled `useFetch`, so the server renders in its locale/timezone and the
browser re-renders in the user's, producing a hydration mismatch and possibly a
different displayed time.

Expected behavior:
Server and client render the same string.

Evidence / reproduction:
Run with the Nuxt server in a different timezone/locale from the browser (e.g. Docker
UTC vs local) and load Settings with a trained model; check the console.

Risk:
Console warning and a timestamp that can change after hydration. No data impact.

Scope guard:
Fix this formatter only. Do not change other date utilities or `utils/formatDate.ts`.

Existing test coverage:
No direct coverage.

Recommended next step:
Analyze then fix

---

### COR-012 — Dashboard / Transactions hydration mismatch warnings

Priority: P3 (provisional)
Area: `frontend/app/pages/dashboard.vue`, `frontend/app/pages/transactions.vue`
Classification: CONFIRMED UX/RELIABILITY ISSUE (cause unconfirmed)
Status: Needs focused investigation

Observed behavior:
Hydration mismatch warnings were repeatedly observed on these pages during redesign
reviews and are listed as pre-existing in `docs/frontend_design_foundation.md`
("Hydration mismatch warnings on Dashboard/Transactions `server: false` loading states").

Expected behavior:
No hydration mismatches.

Evidence / reproduction:
Both pages fetch primary data with `useFetch(…, { server: false })`
(`dashboard.vue` ≈ line 311–319; `transactions.vue` ≈ line 1109–1111) and branch the
template on `pending` (`dashboard.vue`: `<LoadingState v-if="pending && !dashboardData">`).
The suspected cause is the server and the first client render disagreeing about the
loading branch. This is not confirmed; no reproduction was recorded for this backlog.

Risk:
Console noise; possible flash of incorrect content. Unknown until diagnosed.

Scope guard:
Diagnose first. Do not convert pages to SSR data fetching or restructure loading states
as part of the investigation.

Existing test coverage:
No direct coverage.

Recommended next step:
Focused analysis only

---

## Product decisions

### PROD-001 — Income groups appear under Dashboard "Spending by group"

Priority: PRODUCT
Area: Dashboard (`frontend/app/pages/dashboard.vue`), `/summary/dashboard`
Classification: PRODUCT DECISION REQUIRED (pre-existing)
Status: Product decision required

Observed behavior:
`/summary/dashboard` returns every budget group (`backend/routers/summaries.py`, from
`budget_summary.groups`). Income categories' actuals are inverted to positive
(`calculate_actual` in `backend/domain/budgeting.py`), so an income group renders as
"Spent $X of $Y planned" with Over / Unbudgeted / remaining states.

Expected behavior:
To be decided.

Evidence / reproduction:
Seed data with an Income group; open Dashboard.

Decisions required:
- Should income groups appear in this section at all?
- If yes, should section/row wording distinguish income from expense activity?
- Is backend grouping authoritative, or should presentation filter it?

Risk:
Misleading wording; numbers themselves are consistent with the Budget page.

Scope guard:
Do not change until decided. Any change is limited to the decided semantics.

Existing test coverage:
`tests/test_frontend_dashboard_redesign.py`, `tests/test_frontend_dashboard_math.py`
cover the section; nothing characterizes income-group handling specifically.

Recommended next step:
Product decision required

---

### PROD-002 — Budget group totals mix category types

Priority: PRODUCT
Area: Budget (`frontend/app/pages/categories.vue`), `backend/domain/budgeting.py`
Classification: PRODUCT DECISION REQUIRED
Status: Product decision required

Observed behavior:
`calculate_group_summary` sums planned/actual/remaining over all categories regardless of
`income` / `expense` / `transfer` type. The redesign labels such groups "mixed" and keeps
an ambiguous Remaining neutral, preserving the arithmetic.

Expected behavior:
To be decided.

Decision required:
Whether group totals for mixed-type groups should be split by type, restricted to one
type, hidden, or kept as-is; and whether groups should be allowed to mix types at all.

Risk:
Group totals in mixed groups are not meaningful sums. Top-level `to_be_assigned` is unaffected.

Scope guard:
No change to group arithmetic without a decision. Do not alter zero-based totals.

Existing test coverage:
`tests/test_domain_budgeting.py`, `tests/test_frontend_categories_redesign.py`
(group total helpers).

Recommended next step:
Product decision required

---

### PROD-003 — Inactive credit cards show stored `current_balance` on Accounts

Priority: PRODUCT
Area: Accounts (`frontend/app/pages/accounts.vue`), `account_access` active-card query
Classification: PRODUCT DECISION REQUIRED
Status: Product decision required

Observed behavior:
`/credit-cards/summary` only includes active cards (`Account.is_active == True` in
`backend/access/account_access.py` ≈ line 47). Inactive credit cards therefore always use
the `current_balance` fallback, which for manual cards is the stored opening value, not
the ledger-derived `balance_owed`.

Expected behavior:
To be decided.

Decision required:
What balance should an inactive card show: ledger-derived `balance_owed`, the stored
value, or none?

Risk:
An inactive manual card with history can show a figure unrelated to its ledger.

Scope guard:
Decide semantics first. Do not change the summary endpoint's active-only filter as a side
effect of COR-006.

Existing test coverage:
No direct coverage of inactive-card display.

Recommended next step:
Product decision required

---

## UX and accessibility

### UX-001 — Budget drag reorder has no keyboard alternative

Priority: UX
Area: Budget (`frontend/app/pages/categories.vue`)
Classification: CONFIRMED ACCESSIBILITY ISSUE
Status: Confirmed

Observed behavior:
Group and category reordering is `vuedraggable` with handles that are `tabindex="-1"`
(≈ lines 109–114, 233). There is no keyboard or menu path to reorder.

Expected behavior:
Reordering is possible without a pointer.

Evidence / reproduction:
Tab through the Budget page: handles are skipped; no other reorder control exists.

Risk:
Keyboard and assistive-technology users cannot reorder.

Scope guard:
Needs an interaction decision first. Do not replace vuedraggable or restyle the ledger.

Existing test coverage:
`tests/test_frontend_categories_redesign.py` covers drag handles; no keyboard coverage.

Recommended next step:
Accessibility design decision required

---

### UX-002 — Budget planned input loses focus on Enter/Escape

Priority: UX
Area: Budget (`frontend/app/pages/categories.vue`)
Classification: CONFIRMED ACCESSIBILITY ISSUE (pre-existing)
Status: Confirmed

Observed behavior:
Enter calls `($event.target).blur()`; Escape calls `revertPlannedAmount`, which also
`blur()`s (≈ lines 262–263, 1107). Focus moves to `<body>`, so keyboard users lose their
place.

Expected behavior:
Focus remains somewhere sensible after commit/cancel.

Evidence / reproduction:
Tab to a planned input, type, press Enter or Escape, then Tab.

Risk:
Keyboard navigation restarts from the top of the document.

Scope guard:
Do not change the save path (`onPlannedAmountChange`) or the input's visual design.

Existing test coverage:
Source-contract: `tests/test_frontend_budget_redesign.py` pins the Escape handler.

Recommended next step:
Accessibility design decision required

---

### UX-003 — Transactions merchant edit does not return focus to the trigger

Priority: UX
Area: Transactions (`frontend/app/pages/transactions.vue`)
Classification: CONFIRMED ACCESSIBILITY ISSUE (pre-existing)
Status: Confirmed

Observed behavior:
`cancelEditingMerchant` and a successful `saveMerchant` (≈ lines 1193–1216) set
`editingMerchantId = null`; the input unmounts and focus is lost. (Focus entering the
input was fixed during the redesign.)

Expected behavior:
Focus returns to the row's merchant edit trigger.

Evidence / reproduction:
Edit a merchant with the keyboard, press Esc or save, then Tab.

Risk:
Keyboard users lose their position in a long ledger.

Scope guard:
Focus management only. Do not change the merchant save contract.

Existing test coverage:
Source-contract: `tests/test_frontend_merchant_normalization.py`.

Recommended next step:
Analyze then fix

---

### UX-004 — Recurring tabs lack arrow-key navigation

Priority: UX
Area: Transactions → Recurring panel (`frontend/app/pages/transactions.vue`)
Classification: CONFIRMED ACCESSIBILITY ISSUE
Status: Confirmed

Observed behavior:
`role="tablist"` / `role="tab"` buttons (≈ lines 132–150) use `aria-selected` but have no
arrow-key handling and no roving `tabindex`; every tab is a Tab stop.

Expected behavior:
WAI-ARIA tabs pattern, or roles that match the actual interaction.

Risk:
Roles promise a keyboard model that is not implemented.

Scope guard:
Do not change the recurring panel's architecture or data flow.

Existing test coverage:
`tests/test_frontend_recurring.py` covers panel presence; no tab keyboard coverage.

Recommended next step:
Accessibility design decision required

---

### UX-005 — Import failure uses native `alert()`

Priority: UX
Area: Import (`frontend/app/pages/upload.vue`)
Classification: CONFIRMED UX/RELIABILITY ISSUE
Status: Confirmed

Observed behavior:
`runImport` shows `alert(\`Import failed: …\`)` on non-OK response and on exception
(≈ lines 1289, 1295). A non-JSON error body makes `res.json()` throw, so the alert shows a
JSON parse message instead of the server error.

Expected behavior:
In-page error consistent with the rest of the app.

Risk:
Blocking dialog; no correctness impact on persisted data.

Scope guard:
Replace the feedback mechanism only; do not redesign the preview step. Not combined with COR-005.

Existing test coverage:
Source-contract: `tests/test_frontend_import_redesign.py` asserts
`SCRIPT.count("alert(\`Import failed:") == 2`.

Recommended next step:
Defer

---

### UX-006 — Destructive deletes use native `confirm()`

Priority: UX
Area: Budget (`categories.vue` ≈ lines 893, 1055), Accounts (`accounts.vue` ≈ line 616)
Classification: CONFIRMED UX/RELIABILITY ISSUE
Status: Confirmed

Observed behavior:
Group, category and account deletion use `window.confirm`. Settings already uses an
in-app dialog (`tests/test_frontend_settings_redesign.py` forbids `confirm(`).

Expected behavior:
Consistent in-app confirmation.

Risk:
Visual/interaction inconsistency only.

Scope guard:
Do not change delete semantics or backend guards.

Existing test coverage:
No direct coverage for Budget/Accounts.

Recommended next step:
Defer

---

### UX-007 — Settings feedback can be off-screen on mobile

Priority: UX
Area: Settings (`frontend/app/pages/settings.vue`)
Classification: CONFIRMED UX/RELIABILITY ISSUE
Status: Confirmed

Observed behavior:
`successMessage` (rule create/update/delete/apply, retrain) renders in a banner at the top
of the page (≈ line 16). Actions further down a narrow viewport do not scroll it into view.
It has `role="status"`, so screen readers announce it.

Expected behavior:
Feedback visible near the action.

Risk:
Sighted mobile users may miss confirmation. No workflow failure.

Scope guard:
Feedback placement only.

Existing test coverage:
`tests/test_frontend_settings_redesign.py` covers `successMessage`.

Recommended next step:
Defer

---

## Documentation and housekeeping

### DOC-001 — `frontend_design_foundation.md` has stale pre-redesign statements

Priority: DOCS
Area: `docs/frontend_design_foundation.md`
Classification: DOCUMENTATION/HOUSEKEEPING
Status: Confirmed

Observed behavior:
Still says "Page content has not been redesigned yet" and "Pages adopt it during their own
redesign slices". "Known issues deferred to page slices" lists undefined custom properties
(`--color-primary-bg`, `--color-surface-subtle`, `--font-mono`, `--font-weight-normal`)
that no page or component references any more.

Expected behavior:
Doc reflects the completed redesign; open items point here.

Scope guard:
Edit stale statements only; do not rewrite the design doc.

Existing test coverage:
Not applicable.

Recommended next step:
Documentation cleanup

---

### DOC-002 — `AGENTS.md` omits themes

Priority: DOCS
Area: `AGENTS.md`
Classification: DOCUMENTATION/HOUSEKEEPING
Status: Confirmed

Observed behavior:
Project structure lists `tokens.css` and `base.css` but not `assets/css/themes.css`, and
the composables list omits `useTheme.ts`.

Scope guard:
Add the missing entries only.

Existing test coverage:
Not applicable.

Recommended next step:
Documentation cleanup

---

### DOC-003 — `AGENTS.md` required reading points at git-ignored files

Priority: DOCS
Area: `AGENTS.md`
Classification: DOCUMENTATION/HOUSEKEEPING
Status: Confirmed

Observed behavior:
"Read first" item 11 and the structure tree reference `docs/checkpoints/number_1.md` and
`docs/session_handoffs/session_1.md`. Both directories are git-ignored (`.gitignore`
"Private Docs"), so fresh clones and remote agents do not have them.

Scope guard:
Mark them optional/local or remove them from required reading; do not restructure the
architecture reading list otherwise.

Existing test coverage:
Not applicable.

Recommended next step:
Documentation cleanup

---

## Non-blocking polish

These do not justify reopening the completed redesign program. They are recorded so they
are not rediscovered; none is scheduled.

- **Dashboard seven-digit Cash value** can cross a divider at some medium widths
  (reported in redesign review; not re-measured for this backlog).
- **Wording**: Dashboard uses "Unbudgeted" / "No budget" (`dashboard.vue` ≈ lines 197–198);
  Budget uses "Unplanned" / "No plan" (`categories.vue` ≈ lines 1176–1188).
- **Income sign display**: Budget shows income activity as an unsigned inflow-toned amount;
  Transactions shows inflows as `+$X` (`transactions.vue` ≈ line 565).
- **Emoji icons**: 📅 in `components/MonthNavigator.vue`, ⚠️ in `components/ErrorBanner.vue`
  (both `aria-hidden`).

---

## Excluded or reclassified seed items

- **Accounts card-summary UTC month** — kept, but downgraded to P3 (COR-009): backend
  cutoff `min(month_end, today + 1)` makes the next-month case harmless.
- **Credit Cards failed month change** — kept at P3 / Defer (COR-010): data is labelled
  with its real month.
- **Credit Cards transfer double-submit** — kept (COR-003), reframed: the server call is
  idempotent; the defect is the stale-index list removal.
- **Reconciliation Finish after load failure** — kept at P2 (COR-002), not P1: the backend
  rejects unbalanced completion.
- **Settings category-group load failure** — P3 (COR-008): blocks a secondary workflow,
  writes nothing wrong.
- **Accounts card-summary fallback** — split into a failure-state defect (COR-006) and an
  inactive-card product decision (PROD-003).
- No seed item was found already fixed.
