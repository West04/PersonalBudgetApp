**PERSONAL BUDGET APP**

# UI Redesign & Theming Brief

*A practical source of truth for redesigning the existing frontend without changing its functionality.*

> **Design intent**
>
> Keep the workflows and capabilities that already work. Improve information hierarchy, navigation, layout, visual polish, consistency, accessibility, and theming without turning the redesign into a feature rewrite.

## Redesign snapshot

| Aspect | Summary |
| --- | --- |
| Primary goal | Same app, same workflows, much better presentation. |
| Best first page | Dashboard, because it establishes the visual language. |
| Recommended sequence | Audit -> design direction -> one-page prototype -> review -> implementation -> repeat. |
| Theme strategy | One semantic token system powering Light, Dark, Pink, Tech, and System modes. |

## Contents

- 1. Redesign phase and goals
- 2. Redesign principles
- 3. Recommended Claude Code workflow
- 4. Visual design direction
- 5. Design system and semantic tokens
- 6. Theme system: Light, Dark, Pink, Tech, System
- 7. Financial color semantics
- 8. Page-by-page redesign order
- 9. Component and layout guidance
- 10. Accessibility and responsive behavior
- 11. Implementation guardrails
- 12. Independent review and commit workflow
- 13. Suggested Claude Code prompts
- 14. Final rollout plan

> **When to start**
>
> Begin this phase after the backend correctness work is complete and the API/domain contracts are stable. The redesign should consume those stable contracts rather than forcing backend changes.

## 1. Redesign phase and goals

This should be treated as a separate product/UI phase, not another architecture phase. The current frontend functionality is worth preserving; the redesign should focus on presentation quality and usability rather than recreating features.

- Clearer financial information hierarchy
- Cleaner navigation and stronger page structure
- Better spacing, typography, density, and visual rhythm
- More intentional use of color and status styling
- Stronger tables and data-heavy layouts
- Responsive behavior across desktop and mobile
- A reusable theme system that does not duplicate component logic

> **Core principle**
>
> Layout can change dramatically; behavior should not change accidentally. Existing actions, filters, editing flows, transfer workflows, category behavior, summaries, and forms should continue to work.

## 2. Redesign principles

### Preserve function, redesign presentation

Do not turn the redesign into a feature rewrite or backend/API migration.

### Use hierarchy before decoration

Spacing, typography, grouping, and ordering should do more work than borders, shadows, or excessive cards.

### Design for financial scanning

Users should quickly understand current position, obligations, available money, exceptions, and next actions.

### Keep dense data dense

Transactions and financial tables should remain efficient to scan; do not replace useful tables with oversized cards.

### Create one system, not page-specific art

Typography, spacing, inputs, buttons, tables, status colors, and surfaces should feel consistent across the app.

### Be visually distinctive without being flashy

Aim for polished personal-finance software, not a marketing landing page or generic SaaS dashboard.

## 3. Recommended Claude Code workflow

Claude Code is a good fit because it can inspect the existing Nuxt/Vue codebase, understand the actual components and workflows, and redesign around them rather than producing a disconnected mockup.

1. Audit the existing frontend without modifying code.
2. Define a design direction and visual language.
3. Redesign one proving-ground page - preferably Dashboard.
4. Review the result independently for hierarchy, consistency, accessibility, responsiveness, and functional preservation.
5. Commit the page only after review passes.
6. Repeat page-by-page, reusing the established design system.

> **Avoid this prompt**
>
> "Redesign my entire frontend." It encourages broad file churn, accidental behavior changes, and generic AI-dashboard styling. Prefer narrow, reviewable slices.

## 4. Visual design direction

The preferred visual character is clean, calm, trustworthy, data-focused, and professional without feeling corporate. Use strong typography, generous spacing, restrained surfaces, deliberate table styling, and limited semantic color.

- Avoid excessive gradients, glow, shadows, rounded cards, and animation.
- Avoid making every section a bordered card; let whitespace and hierarchy communicate structure.
- Use tabular numerals for financial values where practical.
- Make key financial metrics prominent, but keep supporting detail available immediately below.
- Use accent color for interaction and selection, not as a substitute for financial meaning.

```text
Page title + primary action

Key financial summary
--------------------------------

Main working area
--------------------------------

Secondary/detail information
--------------------------------
```

## 5. Design system and semantic tokens

The redesign should define a small semantic design system before page-by-page styling. Components should consume meaning-based tokens rather than hardcoded colors.

```text
--bg-page        --bg-surface       --bg-elevated
--text-primary   --text-secondary   --text-muted
--border-subtle  --border-strong
--accent-primary --accent-hover     --focus-ring
--status-success --status-warning   --status-error
--financial-debt --financial-credit --financial-neutral
--table-header   --table-hover      --input-bg   --button-primary
```

- Define typography scale and weight usage.
- Define spacing scale and page/container widths.
- Define border radii and shadow policy.
- Define button, form, table, badge, modal, empty-state, and alert treatments.
- Keep tokens semantic so themes can change visual styling without rewriting components.

## 6. Theme system: Light, Dark, Pink, Tech, System

The same components and layouts can support multiple personalities by swapping the semantic token values. Theme choice should not change workflows, metric meaning, or page structure.

| Theme | Visual direction | Guardrails |
| --- | --- | --- |
| Light | Bright neutral background, clean light surfaces, charcoal text, subtle borders, restrained accent. | High readability; avoid sterile all-white UI. |
| Dark | Deep charcoal/navy background, layered dark surfaces, readable light text, controlled contrast. | Avoid pure black everywhere and overly bright accents. |
| Pink | Warm neutral or softly tinted base, rose/pink interaction accents, softer visual personality. | Do not make every surface pink; retain professional finance feel. |
| Tech | Slate/near-black surfaces, cyan/blue accents, sharper hierarchy, slightly denser technical feel. | Avoid neon overload, glow, and cyberpunk gimmicks. |
| System | Follows operating-system light/dark preference when the user has not selected an explicit theme. | Should map only to Light/Dark, not randomly to personality themes. |

### Theme selector behavior

- Support System, Light, Dark, Pink, and Tech.
- Persist explicit user choice using the existing frontend persistence convention, or localStorage if no convention exists.
- System follows the OS light/dark preference.
- Avoid flashes of the wrong theme during initial load where practical.
- Keep dimensions and workflow layout mostly consistent across themes; personality should come primarily from tokens and restrained styling differences.

## 7. Financial color semantics

Theme accents and accounting semantics must remain separate. A pink theme does not mean debt should become pink; a tech theme does not mean every positive number becomes cyan.

```text
Theme accent      -> navigation, primary actions, selection, focus
Financial debt    -> liability / owed / overspending semantic token
Financial credit  -> credit / available / favorable semantic token
Warning           -> attention needed, not simply "negative number"
Neutral           -> informational values without positive/negative judgment
```

- Do not mechanically map positive number = green and negative number = red.
- Credit-card debt may be numerically positive while semantically unfavorable.
- Refunds should not look like errors.
- Payments should be distinguishable from charges.
- Available budget and overspending should use meaning-based styling consistently in every theme.

## 8. Page-by-page redesign order

Use one-page slices so the visual system is proven before it is applied everywhere.

### 1. Dashboard

Establish page shell, spacing, typography, metric hierarchy, summary sections, and the initial visual language.

### 2. Transactions

Stress-test dense tables, filters, search, amount styling, row actions, editing, and responsive behavior.

### 3. Budget

Validate hierarchy for planned/actual/remaining money, categories, groups, and zero-based budgeting workflows.

### 4. Accounts & Credit Cards

Unify account presentation, liabilities, balances, card metrics, and financial-state styling.

### 5. Categories

Improve management layout and forms while preserving current category behavior.

### 6. Imports / Plaid / Reconciliation

Apply the mature design system to operational workflows, reviews, and exception handling.

## 9. Component and layout guidance

### Application shell and navigation

- Clarify primary navigation and page location.
- Use a consistent content width and vertical rhythm.
- Keep page titles, primary actions, and secondary actions predictable.
- Avoid a heavy header if a lighter shell communicates hierarchy better.

### Tables

- Treat tables as a first-class part of the design system.
- Improve row density, headers, alignment, numeric alignment, hover/selected state, and responsive behavior.
- Do not replace dense financial tables with card grids.
- Use tabular numerals where possible and emphasize amounts without overwhelming the row.

### Cards and sections

- Use cards only where a bounded summary or action group benefits from a surface.
- Prefer sections and whitespace for ordinary grouping.
- Avoid every statistic becoming an isolated card.

### Forms and controls

- Create consistent inputs, selects, buttons, focus states, validation, and error presentation.
- Maintain visible labels and clear destructive-action styling.
- Keep edit flows behaviorally identical unless a separate UX change is explicitly approved.

## 10. Accessibility and responsive behavior

- Maintain adequate contrast in every theme.
- Preserve visible keyboard focus.
- Do not communicate important state by color alone.
- Ensure muted text remains readable in light, dark, pink, and tech themes.
- Keep touch targets clear on mobile.
- Check dense tables and filters at narrow widths; use deliberate responsive patterns rather than simply shrinking everything.
- Verify empty states, loading states, error states, dialogs, and forms in every theme.

> **Accessibility rule**
>
> Theming is not successful if a theme looks attractive but weakens contrast, focus visibility, data legibility, or financial-state clarity.

## 11. Implementation guardrails

- Preserve backend APIs and response shapes.
- Preserve financial calculations and domain semantics.
- Preserve routing, forms, filters, actions, and workflows.
- Reuse the existing Vue/Nuxt architecture.
- Introduce reusable UI primitives only where repeated patterns justify them.
- Do not replace the entire component stack without a concrete reason.
- Do not mix layout redesign with backend/domain refactors.
- Do not add speculative product features during visual work.

> **Recommended sequencing**
>
> Redesign the layout and shared component language first. Add the multi-theme system after the layout is stable so you are not redesigning four versions of a moving target.

## 12. Independent review and commit workflow

Use the same disciplined pattern that worked well on the backend: one UI slice, one review, one commit.

```text
Designer agent
    -> implements one page / one visual-system slice

Independent reviewer
    -> checks hierarchy
    -> consistency
    -> accessibility
    -> responsiveness
    -> preserved functionality
    -> unnecessary complexity
    -> reuse of design primitives

PASS
    -> commit
    -> next page
```

## 13. Suggested Claude Code prompts

### A. Frontend audit prompt

```text
Perform a frontend UX/layout audit only. Do not modify code.

Inspect the current Nuxt/Vue application page-by-page and report:
- navigation and app-shell structure
- information hierarchy
- visual density and spacing
- typography consistency
- repeated component patterns
- table/form usability
- responsive behavior
- accessibility issues
- page-specific visual problems
- opportunities for shared design primitives

Preserve all existing functionality. Do not propose backend/API changes.
Recommend a page-by-page redesign roadmap, starting with Dashboard.
```

### B. Visual redesign brief

```text
Redesign the frontend visual system while preserving all existing functionality,
workflows, API contracts, and page behavior.

Goals:
- clearer financial information hierarchy
- cleaner navigation
- better spacing and typography
- less visual clutter
- stronger tables and dense-data presentation
- consistent treatment of financial states
- professional personal-finance aesthetic
- responsive desktop/mobile behavior

Avoid:
- generic SaaS dashboard appearance
- excessive cards, gradients, shadows, and animations
- changing workflows without justification
- backend/API changes
```

### C. Multi-theme implementation brief

```text
Implement a semantic-token theme system with:
- System
- Light
- Dark
- Pink
- Tech

Components must consume semantic tokens rather than hardcoded per-theme colors.
Keep accounting semantics separate from theme accents.
Persist explicit user selection and follow OS light/dark in System mode.
Preserve all application behavior and backend contracts.
```

## 14. Final rollout plan

### Phase 1 - Backend completion

Finish remaining backend correctness work and reach a stable green suite.

### Phase 2 - Frontend audit

Document current UX/layout problems and repeated visual patterns without changing code.

### Phase 3 - Visual direction

Define the design language, token system, typography, spacing, and component conventions.

### Phase 4 - Dashboard prototype

Redesign one page, independently review it, and use it to establish the system.

### Phase 5 - Page-by-page rollout

Transactions -> Budget -> Accounts/Credit Cards -> Categories -> Imports/Reconciliation.

### Phase 6 - Theme system

Apply System, Light, Dark, Pink, and Tech themes through semantic tokens.

### Phase 7 - Final UI review

Check consistency, accessibility, responsive behavior, and preserved functionality across all pages/themes.

> **End state**
>
> A single stable frontend architecture and workflow set, with a stronger information hierarchy, cohesive visual system, and multiple user-selectable themes - without sacrificing the functionality you already like.
