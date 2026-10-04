<template>
  <div class="transactions-page">
    <!-- Header -->
    <PageHeader
      title="Transactions"
      subtitle="Browse and categorize bank transactions"
    >
      <template #controls>
        <MonthNavigator />
      </template>
    </PageHeader>

    <!-- Error Banner -->
    <ErrorBanner
      v-if="displayError"
      :error="displayError"
      @dismiss="clearErrors"
    />

    <!-- Filters Section -->
    <div class="filters-card card" aria-label="Transaction filters">
      <div class="filters-grid">
        <!-- Search Filter -->
        <div class="filter-group">
          <label for="tx-search-input">Search</label>
          <div class="search-input-wrapper">
            <input
              id="tx-search-input"
              type="text"
              v-model="searchQuery"
              placeholder="Search description..."
              class="filter-input"
              aria-label="Search transaction description"
            />
            <button
              v-if="searchQuery"
              type="button"
              class="search-clear-btn"
              @click="searchQuery = ''"
              aria-label="Clear search input"
              title="Clear search"
            >
              ✕
            </button>
          </div>
        </div>

        <!-- Account Filter (Route-backed) -->
        <div class="filter-group">
          <label for="tx-account-select">Account</label>
          <select
            id="tx-account-select"
            v-model="selectedAccount"
            class="filter-input"
            aria-label="Filter by account"
          >
            <option value="">All Accounts</option>
            <option
              v-for="acc in accounts"
              :key="acc.account_id"
              :value="acc.account_id"
            >
              {{ acc.name }}
            </option>
          </select>
        </div>

        <!-- Category Filter -->
        <div class="filter-group">
          <label for="tx-category-select">Category</label>
          <select
            id="tx-category-select"
            v-model="selectedCategory"
            class="filter-input"
            aria-label="Filter by category"
          >
            <option value="">All Categories</option>
            <optgroup
              v-for="group in categoryGroups"
              :key="group.category_group_id"
              :label="group.name"
            >
              <option
                v-for="cat in group.categories"
                :key="cat.category_id"
                :value="cat.category_id"
              >
                {{ cat.name }}
              </option>
            </optgroup>
          </select>
        </div>
      </div>

      <!-- Filters Meta Row: Uncategorized toggle, active indicators, and reset -->
      <div class="filters-meta-row">
        <div class="filter-meta-left">
          <label class="checkbox-label" for="tx-uncategorized-checkbox">
            <input
              type="checkbox"
              id="tx-uncategorized-checkbox"
              v-model="uncategorizedOnly"
              class="filter-checkbox"
            />
            <span>Uncategorized Only</span>
          </label>
        </div>

        <div class="filter-meta-right">
          <span class="filter-summary-text" aria-live="polite">
            {{ transactionCountLabel }}
            <template v-if="filterSummaryParts.length > 0">
              · <span class="summary-chips">{{ filterSummaryParts.join(' · ') }}</span>
            </template>
          </span>

          <button
            type="button"
            class="btn-clear-filters"
            :disabled="!hasActiveSecondaryFilters"
            @click="clearSecondaryFilters"
            aria-label="Clear active secondary filters"
          >
            Clear filters
          </button>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="pending && !transactionsData"
      message="Loading transactions..."
    />

    <!-- Transactions Table Container -->
    <div v-else class="transactions-container">
      <div class="card table-card">
        <div class="table-responsive">
          <table class="transactions-table" aria-label="Transactions ledger">
            <thead>
              <tr>
                <th scope="col" class="date-col">Date</th>
                <th scope="col" class="desc-col">Description</th>
                <th scope="col" class="account-col">Account</th>
                <th scope="col" class="category-col">Category</th>
                <th scope="col" class="amount-col">Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="tx in transactionsData?.items"
                :key="tx.transaction_id"
              >
                <td class="date-cell font-mono">{{ formatDate(tx.date) }}</td>
                <td class="desc-cell">
                  <div class="desc-text" :title="tx.description">{{ tx.description }}</div>
                </td>
                <td class="account-cell">
                  <span class="account-tag">{{ tx.account?.name || 'Unknown' }}</span>
                </td>
                <td class="category-cell">
                  <select
                    :value="tx.category_id || ''"
                    @change="updateTransactionCategory(tx.transaction_id, ($event.target as HTMLSelectElement).value)"
                    class="category-select"
                    :class="{ 'uncategorized': !tx.category_id }"
                    :disabled="updatingId === tx.transaction_id"
                    aria-label="Assign category"
                  >
                    <option value="">Uncategorized</option>
                    <optgroup
                      v-for="group in categoryGroups"
                      :key="group.category_group_id"
                      :label="group.name"
                    >
                      <option
                        v-for="cat in group.categories"
                        :key="cat.category_id"
                        :value="cat.category_id"
                      >
                        {{ cat.name }}
                      </option>
                    </optgroup>
                  </select>
                </td>
                <td
                  class="amount-cell font-mono"
                  :class="{ 'inflow': tx.amount < 0 }"
                >
                  {{ tx.amount < 0 ? '+' : '' }}{{ formatCurrency(Math.abs(Number(tx.amount))) }}
                </td>
              </tr>
              <tr v-if="transactionsData?.items.length === 0">
                <td colspan="5" class="empty-row">
                  No transactions found matching current filters.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div class="pagination" v-if="transactionsData?.total > limit">
          <button
            type="button"
            :disabled="offset === 0"
            @click="offset = Math.max(0, offset - limit)"
            class="page-btn"
            aria-label="Previous page"
          >
            Previous
          </button>
          <span class="page-info">
            Showing {{ offset + 1 }} - {{ Math.min(offset + limit, transactionsData.total) }} of {{ transactionsData.total }}
          </span>
          <button
            type="button"
            :disabled="offset + limit >= transactionsData.total"
            @click="offset += limit"
            class="page-btn"
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBudgetMonth } from '~/composables/useBudgetMonth'
import { useTransactionFilters } from '~/composables/useTransactionFilters'
import { formatDateOnly } from '~/utils/formatDate'
import { buildTransactionQuery } from '~/utils/transactionQuery'

const API_BASE = '/api'

const route = useRoute()
const router = useRouter()
const { selectedMonth } = useBudgetMonth()

// Session-persisted secondary filters
const {
  searchQuery,
  selectedCategory,
  uncategorizedOnly,
  offset,
  hasActiveSecondaryFilters,
  clearSecondaryFilters,
} = useTransactionFilters()

const limit = ref(50)

// Route-backed Account Filter
const getRouteAccountId = () => {
  return typeof route.query.account_id === 'string' && route.query.account_id
    ? route.query.account_id
    : ''
}

const selectedAccount = ref(getRouteAccountId())

// Route query -> selectedAccount
watch(
  () => route.query.account_id,
  (newAccount) => {
    const accountId = typeof newAccount === 'string' ? newAccount : ''
    if (selectedAccount.value !== accountId) {
      selectedAccount.value = accountId
    }
  }
)

// selectedAccount -> Route query
watch(selectedAccount, (newAcc) => {
  const currentQueryAcc = typeof route.query.account_id === 'string' ? route.query.account_id : ''
  if (newAcc !== currentQueryAcc) {
    const nextQuery: Record<string, string> = { ...route.query, month: selectedMonth.value }
    if (newAcc) {
      nextQuery.account_id = newAcc
    } else {
      delete nextQuery.account_id
    }
    router.replace({ query: nextQuery })
  }
})

// Metadata fetching
const { data: accounts } = await useFetch<any[]>(`${API_BASE}/accounts/`)
const { data: categoryGroups } = await useFetch<any[]>(`${API_BASE}/category-groups`)

// Computed Query Parameters using pure builder
const queryParams = computed(() => {
  return buildTransactionQuery({
    month: selectedMonth.value,
    accountId: selectedAccount.value,
    categoryId: selectedCategory.value,
    search: searchQuery.value,
    uncategorized: uncategorizedOnly.value,
    limit: limit.value,
    offset: offset.value,
  })
})

const {
  data: transactionsData,
  pending,
  error: fetchError,
  refresh,
} = await useFetch<any>(`${API_BASE}/transactions/`, {
  query: queryParams,
  server: false,
})

// Reset offset to 0 when any filter or month changes
watch(
  [searchQuery, selectedAccount, selectedCategory, uncategorizedOnly, selectedMonth],
  () => {
    offset.value = 0
  }
)

// Active filter summary text
const filterSummaryParts = computed(() => {
  const parts: string[] = []
  if (selectedAccount.value) {
    const acc = accounts.value?.find((a: any) => a.account_id === selectedAccount.value)
    if (acc) parts.push(acc.name)
  }
  if (selectedCategory.value) {
    let catName = ''
    for (const group of categoryGroups.value || []) {
      const c = group.categories?.find((cat: any) => cat.category_id === selectedCategory.value)
      if (c) {
        catName = c.name
        break
      }
    }
    if (catName) parts.push(catName)
  }
  if (searchQuery.value.trim()) {
    parts.push(`"${searchQuery.value.trim()}"`)
  }
  if (uncategorizedOnly.value) {
    parts.push('Uncategorized')
  }
  return parts
})

const transactionCountLabel = computed(() => {
  const count = transactionsData.value?.total ?? 0
  return `${count} ${count === 1 ? 'transaction' : 'transactions'}`
})

// Inline Category Editing
const updateError = ref<string | null>(null)
const updatingId = ref<string | null>(null)

const updateTransactionCategory = async (transactionId: string, categoryId: string) => {
  updateError.value = null
  updatingId.value = transactionId
  try {
    const response = await fetch(`${API_BASE}/transactions/${transactionId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category_id: categoryId || null }),
    })

    if (!response.ok) throw new Error('Failed to update category')

    if (transactionsData.value?.items) {
      const item = transactionsData.value.items.find((t: any) => t.transaction_id === transactionId)
      if (item) {
        item.category_id = categoryId || null
      }
    }

    await refresh()
  } catch (err: any) {
    updateError.value = err.message || 'Failed to update category. Please try again.'
    console.error(err)
  } finally {
    updatingId.value = null
  }
}

// Helpers
const formatCurrency = (amount: number | string, currency = 'USD') => {
  const val = Number(amount)
  if (isNaN(val)) return '$0.00'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val)
}

const formatDate = (dateStr: string) => formatDateOnly(dateStr, { includeYear: true })

const displayError = computed(() => {
  if (updateError.value) return updateError.value
  if (fetchError.value) return fetchError.value.message || 'Failed to load transactions.'
  return null
})

const clearErrors = () => {
  updateError.value = null
}
</script>

<style scoped>
.transactions-page {
  padding: var(--space-lg);
  max-width: var(--page-max-width);
  margin: 0 auto;
}

.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

/* Filters Card */
.filters-card {
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-md);
  align-items: flex-end;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.filter-group label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-clear-btn {
  position: absolute;
  right: 8px;
  background: transparent;
  border: none;
  color: var(--color-text-light);
  cursor: pointer;
  padding: 4px;
  font-size: 0.75rem;
  line-height: 1;
  border-radius: var(--radius-xs);
}

.search-clear-btn:hover {
  color: var(--color-text);
}

.filter-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-surface);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  box-sizing: border-box;
}

.filter-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus);
}

/* Filters Meta Row */
.filters-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-sm);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--color-border-subtle);
}

.filter-meta-left {
  display: flex;
  align-items: center;
}

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text);
  user-select: none;
}

.filter-checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
  cursor: pointer;
}

.filter-meta-right {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.filter-summary-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.summary-chips {
  color: var(--color-text);
  font-weight: var(--font-weight-medium);
}

.btn-clear-filters {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-clear-filters:hover:not(:disabled) {
  background: var(--color-surface-hover);
  color: var(--color-text);
  border-color: var(--color-border-hover);
}

.btn-clear-filters:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.btn-clear-filters:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Table Card & Responsive Wrapper */
.table-card {
  overflow: hidden;
}

.table-responsive {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.transactions-table {
  width: 100%;
  min-width: 640px;
  border-collapse: collapse;
  text-align: left;
}

.transactions-table th {
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.transactions-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
  font-size: var(--font-size-base);
  color: var(--color-text);
}

.transactions-table tr:last-child td {
  border-bottom: none;
}

.transactions-table tbody tr:hover td {
  background-color: #fafbfc;
}

.date-col {
  width: 110px;
}

.date-cell {
  color: var(--color-text-muted);
  white-space: nowrap;
  font-size: var(--font-size-sm);
}

.desc-col {
  min-width: 200px;
}

.desc-cell {
  max-width: 320px;
}

.desc-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: var(--font-weight-medium);
}

.account-col {
  width: 140px;
}

.account-tag {
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border-subtle);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.category-col {
  width: 220px;
}

.category-select {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  width: 100%;
  max-width: 210px;
  background: var(--color-surface);
  color: var(--color-text);
  transition: border-color 0.15s ease;
  font-family: inherit;
}

.category-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-focus);
}

.category-select.uncategorized {
  border-color: var(--color-danger-border);
  background-color: var(--color-danger-bg);
  color: var(--color-danger-hover);
  font-weight: var(--font-weight-medium);
}

.amount-col {
  text-align: right;
  width: 120px;
}

.amount-cell {
  text-align: right;
  font-weight: var(--font-weight-semibold);
}

.amount-cell.inflow {
  color: var(--color-success);
}

.empty-row {
  text-align: center;
  padding: 48px !important;
  color: var(--color-text-muted);
  font-style: italic;
}

/* Pagination */
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  background: #f8fafc;
  border-top: 1px solid var(--color-border);
}

.page-btn {
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  transition: all 0.15s ease;
}

.page-btn:hover:not(:disabled) {
  background: var(--color-surface-hover);
  border-color: var(--color-border-hover);
}

.page-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}
</style>