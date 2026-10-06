# BudgetApp Frontend

A Vue 3 & Nuxt 4 web application implementing an EveryDollar-style zero-based budgeting interface.

---

## 🛠️ Stack & Dependencies

- **Framework:** [Nuxt 4](https://nuxt.com/) (Compatibility Date: `2025-07-15`)
- **UI & State:** [Vue 3](https://vuejs.org/) (Composition API, `<script setup>`)
- **Drag & Drop:** [`vuedraggable`](https://github.com/SortableJS/vue.draggable.next) (SortableJS wrapper for Vue 3)
- **Language:** TypeScript
- **Styling:** Centralized CSS design token system (`tokens.css`, `base.css`) providing semantic typography, colors (inflow, outflow, warnings, overpayments), spacing, and elevation.

---

## 📂 Directory Structure

```
frontend/
├── app/
│   ├── app.vue                 # Persistent layout with collapsible sidebar
│   ├── tokens.css              # Global design tokens (colors, typography, spacing, elevation)
│   ├── base.css                # Base reset and common utility classes
│   ├── components/             # Reusable design system primitives
│   │   ├── AppDialog.vue       # Accessible modal dialog with focus management and escape key handling
│   │   ├── EmptyState.vue      # Standardized empty list state presentation
│   │   ├── ErrorBanner.vue     # Dismissible error alerts
│   │   ├── FormField.vue       # Standardized form input wrappers with validation labels
│   │   ├── LoadingState.vue    # Loading indicators and skeletons
│   │   ├── MonthNavigator.vue  # Unified month selection component synchronized with query routes
│   │   └── PageHeader.vue      # Consistent page header with title, subtitle, and action slots
│   ├── composables/
│   │   ├── useAccountTypes.ts      # Standardized account types and subtypes
│   │   ├── useBudgetMonth.ts       # Unified route-synchronized budget month state (YYYY-MM)
│   │   └── useTransactionFilters.ts# Reactive, query-synchronized transaction filters
│   └── pages/
│       ├── index.vue           # Middleware redirect to /dashboard
│       ├── dashboard.vue       # Monthly financial KPI cards, liquid cash, debt totals, spending by category, Needs Attention
│       ├── categories.vue      # Merged category manager & zero-based budget planner with whole-row expansion
│       ├── transactions.vue    # Primary transaction ledger with filters, search, review, splits modal, and ML suggestions
│       ├── accounts.vue        # Account management, ledger-derived balances, overpayments, and Account Reconciliation modal
│       ├── credit-cards.vue    # Specialized credit card debt tracking and monthly charge/payment breakdowns
│       ├── upload.vue          # Upload-first 4-step CSV wizard (Upload/Inspect/Resolve, Account, Preview & Confirm, Done)
│       └── settings.vue        # Categorization Rules management (add, edit, delete, preview matches, retroactive bulk apply)
├── public/                     # Static assets (favicons, robots.txt)
├── nuxt.config.ts              # Nitro proxy configuration
├── Dockerfile                  # Multi-stage production build container
└── package.json
```

---

## 🌐 API Proxying & Backend Communication

In [`nuxt.config.ts`](file:///Users/west/programming_stuff/budget_app/frontend/nuxt.config.ts), Nuxt proxies `/api/**` calls directly to the FastAPI container:

```typescript
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  routeRules: {
    '/api/**': { proxy: 'http://backend:8000/**' }
  }
})
```

- **Consistent Frontend Contract:** All pages and components standardize on `const API_BASE = '/api'`.
- In both local development and Docker Compose, browser requests to `/api/...` are routed through the Nuxt Nitro server proxy to `http://backend:8000/...`, eliminating direct client-side dependencies on backend port numbers.
- FastAPI's `CORSMiddleware` provides a defense-in-depth fallback for direct API calls during local testing.

---

## 💻 Development Commands

```bash
# Install dependencies
npm install

# Start development server with hot-reload (http://localhost:3000)
npm run dev

# Build for production
npm run build

# Preview production build locally
npm run preview
```
