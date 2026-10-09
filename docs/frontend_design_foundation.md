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
   `--overlay-scrim`. New code uses only these. The `:root` values are the Light
   theme; `themes.css` overrides them for the other themes (see Themes below).
2. **Scales**: spacing, radius, type roles, layout widths.
3. **Legacy aliases**: `--color-*`, `--bg-color`, `--text-color`, and the rest. Legacy
   `--color-*` names continue to resolve through compatibility aliases; their values now
   map to the new foundational palette. Some values changed on purpose for contrast
   (muted and light text, borders, success/warning/error), so unmigrated pages look
   slightly different but keep their structure. Remove each alias once no page uses it.

Contrast floor: `--text-muted` is the lightest token allowed for readable text
(≥ 5.3:1 on page and surface). `--text-disabled` is only for disabled controls.

## Themes (`frontend/app/assets/css/themes.css`)

| Preference | Rendering |
| --- | --- |
| `system` (default) | Light, or the Dark palette when `prefers-color-scheme: dark` |
| `light` | the `:root` baseline in `tokens.css` |
| `dark` | layered charcoal; surfaces get lighter as they rise (page < surface < elevated) |
| `pink` | Light structure on a faintly warm neutral, berry-rose accent |
| `tech` | deep blue-slate, crisper borders, cyan accent |

- **Contract:** the values are exactly `system`, `light`, `dark`, `pink`, `tech`
  (`utils/theme.ts`). Anything else (missing, old or hand-edited) falls back to `system`.
- **Persistence:** the `theme` cookie (one year, `SameSite=Lax`), the same convention
  as `nav_collapsed`. No cookie is written until the user picks a theme. There is no
  backend setting.
- **Rendering:** `useTheme()` seeds shared state from the sanitized cookie; `app.vue`
  renders it as `<html data-theme="...">` through `useHead`. The server sends the
  attribute and the stylesheets in `<head>`, so the first paint already uses the right
  theme, with or without JavaScript, and hydration sees the same value.
- **System** is resolved in CSS by a `prefers-color-scheme: dark` block that repeats
  the Dark tokens (a test keeps the two identical). It follows OS changes live, with
  no reload and no JavaScript. System only ever maps to Light or Dark.
- Each theme sets `color-scheme`, so native selects, date and file inputs, checkboxes
  and scrollbars match. `html { accent-color }` makes native checkboxes and radios use
  the theme accent.
- **Themes change color tokens only.** Spacing, radius, type and layout tokens are
  shared, so switching themes never changes geometry. Switching is immediate, with no
  palette animation.
- Pages and components never branch on the theme. They consume semantic tokens.
- The selector lives in Settings, under Appearance: a native radio group, applied
  immediately.

### Accent vs meaning

The accent (`--accent-*`, `--focus-*`, active navigation, primary buttons, selection)
is the only thing that carries a theme's personality. Financial and status tokens never
reference it and keep their meaning in every theme: favorable (inflow, credit,
available) is green, overspent and error are red, warning is amber, info is blue, and
outflow and ordinary card debt are neutral ink. Pink inherits Light's financial and
status values unchanged, so overspending is red, not pink. Tech's green is kept clearly
green, so it never reads as the cyan accent. Danger buttons use `--button-danger` and
`--button-danger-text`, never the accent. Tests check that the accent hue stays at
least 30° away from every financial and status hue, and that each theme meets the
contrast floor (AA text, 3:1 focus rings and control edges).

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
- The calendar emoji in `MonthNavigator` and the warning emoji in `ErrorBanner`
  (the banner's last hardcoded hover color now uses `--status-error-border`).
  Page-local hardcoded colors are gone: Credit Cards and Accounts (Accounts/Credit
  Cards slice), Transactions (its own slice) and Import plus the reconcile dialog
  (Import/Reconciliation slice). Import keeps its existing four-step sequence
  (File, Account, Preview, Done); its preview table and the reconcile dialog's
  transaction table restack with explicit ARIA roles below 560px / 480px.
