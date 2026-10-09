# Frontend Design Foundation

Reference for the UI redesign slices that follow `budget_app_ui_redesign_brief.md`.
Direction: **Instrument** (precise, compact, tool-like) with Ledger restraint
(few surfaces, minimal shadow, hierarchy before decoration).

This slice set up tokens, typography roles, financial semantics, the app shell and
a Money primitive. Page content has not been redesigned yet.

## Tokens (`frontend/app/assets/css/tokens.css`)

Three layers:

1. **Semantic tokens**: `--bg-*`, `--text-*`, `--border-*`, `--accent-*`, `--focus-*`,
   `--status-*`, `--financial-*`, `--table-*`, `--input-*`, `--button-*`, `--nav-*`,
   `--overlay-scrim`. New code uses only these. Future themes (Light, Dark, Pink,
   Tech, System) replace these values and nothing else.
2. **Scales**: spacing, radius, type roles, layout widths.
3. **Legacy aliases**: `--color-*`, `--bg-color`, `--text-color`, and the rest. Legacy
   `--color-*` names continue to resolve through compatibility aliases; their values now
   map to the new foundational palette. Some values changed on purpose for contrast
   (muted and light text, borders, success/warning/error), so unmigrated pages look
   slightly different but keep their structure. Remove each alias once no page uses it.

Contrast floor: `--text-muted` is the lightest token allowed for readable text
(≥ 5.3:1 on page and surface). `--text-disabled` is only for disabled controls.

## Financial semantics

Accounting meaning is kept separate from the accent and status colors:

| Token | Meaning |
| --- | --- |
| `--financial-neutral` | informational amounts |
| `--financial-outflow` | spending (neutral ink: spending is normal) |
| `--financial-inflow` | money arriving (income, refunds, deposits) |
| `--financial-debt` | liability owed |
| `--financial-credit` | balance in the user's favor |
| `--financial-available` | money left to spend or assign |
| `--financial-overspent` | spent beyond plan / over-assigned |

The caller decides which meaning applies. Never choose one from the sign of a number:
credit-card debt is positive but unfavorable, and a refund is an inflow, not an
error.

Credit-card balances use one presentation everywhere (Dashboard, Accounts, Credit
Cards): the `formatCardBalance` figure in `neutral` tone when owed or `credit` tone
when in credit, with the word "owed" / "credit" set beneath it; zero has no word.
Debt is not shown in an alarm color.

## Money primitive

`<Money :amount="value" tone="debt" sign="never" />`
(`components/Money.vue`, `utils/money.ts`)

- Formats only. It does no calculation, no credit-card logic and no inference from the sign.
- `tone` is one of the financial meanings above (default `neutral`).
- `sign`: `auto` (same output as `formatCurrency`), `never`, `always` (`+`/`-`, zero
  unsigned).
- Uses tabular figures in the body font, not monospace.
- The `.money--{tone}` classes can be used directly when a component would be
  overkill.

Pages adopt it during their own redesign slices.

## Typography

One system sans family. Roles are exposed as tokens and classes:
`--font-display`, `--font-body`, `--font-numeric`; `.type-title`, `.type-heading`,
`.type-subheading`, `.type-meta`, `.type-label`, `.type-metric`, `.num`.
Labels use sentence case. `.font-mono` is legacy; new numeric work uses `.num`.

## Surfaces

- The page background is the primary surface. Ordinary sections are not cards.
- `.surface-card` is for genuinely bounded content: 1px border, `--radius-md`, no shadow.
- `--shadow-modal` is reserved for dialogs and the mobile navigation drawer.

## Focus

A global `:focus-visible` draws a solid 2px outline in `--focus-ring` on every focusable
element. Form controls enforce it with `!important`, because several pages set
`outline: none` on inputs.

## Shell and layout

| Width | Navigation |
| --- | --- |
| ≥ 1024px | 232px rail. The user can collapse it to a 64px icon rail; the choice is saved in the `nav_collapsed` cookie so the server renders it correctly. |
| 768–1023px | 64px icon rail, always. |
| ≤ 767px | 52px top bar and a navigation drawer: modal, focus-trapped, closes on Escape (document-level listener while open), scrim click or route change; main content is `inert` while it is open. Under `prefers-reduced-motion` transitions are cut to `0s` globally and removed from the drawer, so focus moves into it immediately (a tiny non-zero duration would create `visibility` transitions on every element). |

On the icon rail, labels are visually hidden but stay in the DOM, so links keep their
accessible names. The active route is shown by a tint, a leading bar and font weight,
plus `aria-current`.

Page containers (opt-in per page slice): `.page-container` (1200px),
`.page-container--wide` (1520px, dense tables), `.page-container--narrow`
(880px, forms and wizards). The shell itself adds no padding.

## Known issues deferred to page slices

- ~~Budget group header crushes the group name at ~700px content width~~ (fixed in the Budget slice:
  the ledger uses fixed numeric tracks and stacked/compact/full container-query tiers).
- Hydration mismatch warnings on Dashboard/Transactions `server: false` loading
  states (pre-existing).
- Undefined custom properties referenced by pages: `--color-primary-bg`,
  `--color-surface-subtle`, `--font-mono`, `--font-weight-normal` (pre-existing).
- The calendar emoji in `MonthNavigator` and the warning emoji in `ErrorBanner`.
  Page-local hardcoded colors are gone: Credit Cards and Accounts (Accounts/Credit
  Cards slice), Transactions (its own slice) and Import plus the reconcile dialog
  (Import/Reconciliation slice). Import keeps its existing four-step sequence
  (File, Account, Preview, Done); its preview table and the reconcile dialog's
  transaction table restack with explicit ARIA roles below 560px / 480px.
