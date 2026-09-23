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
│       ├── upload.vue          # 4-step CSV bank statement import wizard
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

- When running inside Docker Compose, browser calls to `/api/...` are routed to the Nuxt Nitro server on port 3000, which forwards them over the Docker network to `http://backend:8000/...`.
- When developing locally, FastAPI's `CORSMiddleware` also allows direct requests from `http://localhost:3000` and `http://localhost:12345`.

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
