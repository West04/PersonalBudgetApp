# BudgetApp Frontend

A Vue 3 & Nuxt 4 web application implementing an EveryDollar-style zero-based budgeting interface.

---

## 🛠️ Stack & Dependencies

- **Framework:** [Nuxt 4](https://nuxt.com/) (Compatibility Date: `2025-07-15`)
- **UI & State:** [Vue 3](https://vuejs.org/) (Composition API, `<script setup>`)
- **Drag & Drop:** [`vuedraggable`](https://github.com/SortableJS/vue.draggable.next) (SortableJS wrapper for Vue 3)
- **Language:** TypeScript
- **Styling:** Vanilla CSS design system using CSS custom properties (`--bg-color`, `--sidebar-bg`, etc.)

---

## 📂 Directory Structure

```
frontend/
├── app/
│   ├── app.vue                 # Persistent layout with collapsible sidebar
│   ├── composables/
│   │   └── useAccountTypes.ts  # Standardized account types and subtypes
│   └── pages/
│       ├── index.vue           # Middleware redirect to /dashboard
│       ├── dashboard.vue       # Monthly financial KPI cards and balance overview
│       ├── categories.vue      # Merged category manager & zero-based budget planner
│       ├── transactions.vue    # Paginated, filterable transaction ledger
│       ├── accounts.vue        # Account management & balances by account type
│       ├── credit-cards.vue    # Credit debt tracking and transfer candidate review
│       ├── upload.vue          # Upload-first 4-step CSV wizard (Upload/Inspect/Resolve, Account, Preview & Confirm, Done)
│       └── settings.vue        # Settings placeholder
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

- **Consistent Frontend Contract:** All pages and components (`dashboard.vue`, `transactions.vue`, `accounts.vue`, `categories.vue`, `credit-cards.vue`, `upload.vue`) standardize on `const API_BASE = '/api'`.
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
