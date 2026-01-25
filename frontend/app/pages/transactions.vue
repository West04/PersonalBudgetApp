<template>
  <div class="transactions-page">
    <!-- Header -->
    <header class="page-header">
      <h1 class="page-title">Transactions</h1>
      <div class="header-actions">
        <div class="month-selector">
          <input 
            type="month" 
            v-model="currentMonth" 
            class="month-input"
          />
        </div>
      </div>
    </header>

    <!-- Filters Section -->
    <div class="filters-card card">
      <div class="filters-grid">
        <div class="filter-group">
          <label>Search</label>
          <input 
            type="text" 
            v-model="searchQuery" 
            placeholder="Search description..." 
            class="filter-input"
          />
        </div>
        
        <div class="filter-group">
          <label>Account</label>
          <select v-model="selectedAccount" class="filter-input">
            <option value="">All Accounts</option>
            <option v-for="acc in accounts" :key="acc.id" :value="acc.id">
              {{ acc.name }}
            </option>
          </select>
        </div>

        <div class="filter-group">
          <label>Category</label>
          <select v-model="selectedCategory" class="filter-input">
            <option value="">All Categories</option>
            <optgroup v-for="group in categoryGroups" :key="group.category_group_id" :label="group.name">
              <option v-for="cat in group.categories" :key="cat.category_id" :value="cat.category_id">
                {{ cat.name }}
              </option>
            </optgroup>
          </select>
        </div>

        <div class="filter-group checkbox-group">
          <label class="checkbox-label">
            <input type="checkbox" v-model="uncategorizedOnly" />
            Uncategorized Only
          </label>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="pending" class="loading-state">
      <div class="spinner"></div>
      <p>Loading transactions...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <p>⚠️ Failed to load transactions.</p>
      <button @click="refresh" class="retry-btn">Retry</button>
    </div>

    <!-- Transactions Table -->
    <div v-else class="transactions-container">
      <div class="card table-card">
        <table class="transactions-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Account</th>
              <th>Category</th>
              <th class="amount-col">Amount</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="tx in transactionsData?.items" :key="tx.transaction_id">
              <td class="date-cell">{{ formatDate(tx.date) }}</td>
              <td class="desc-cell">
                <div class="desc-text" :title="tx.description">{{ tx.description }}</div>
              </td>
              <td class="account-cell">
                <span class="account-tag">{{ tx.account?.name || 'Unknown' }}</span>
              </td>
              <td class="category-cell">
                <select 
                  :value="tx.category_id || ''" 
                  @change="updateTransactionCategory(tx.transaction_id, $event.target.value)"
                  class="category-select"
                  :class="{ 'uncategorized': !tx.category_id }"
                >
                  <option value="">Uncategorized</option>
                  <optgroup v-for="group in categoryGroups" :key="group.category_group_id" :label="group.name">
                    <option v-for="cat in group.categories" :key="cat.category_id" :value="cat.category_id">
                      {{ cat.name }}
                    </option>
                  </optgroup>
                </select>
              </td>
              <td class="amount-cell" :class="{ 'inflow': tx.amount < 0 }">
                {{ formatCurrency(Math.abs(tx.amount)) }}
              </td>
            </tr>
            <tr v-if="transactionsData?.items.length === 0">
              <td colspan="5" class="empty-row">No transactions found matching filters.</td>
            </tr>
          </tbody>
        </table>

        <!-- Pagination -->
        <div class="pagination" v-if="transactionsData?.total > limit">
          <button 
            :disabled="offset === 0" 
            @click="offset -= limit"
            class="page-btn"
          >
            Previous
          </button>
          <span class="page-info">
            Showing {{ offset + 1 }} - {{ Math.min(offset + limit, transactionsData.total) }} of {{ transactionsData.total }}
          </span>
          <button 
            :disabled="offset + limit >= transactionsData.total" 
            @click="offset += limit"
            class="page-btn"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const API_BASE = 'http://localhost:12344'

// --- State ---
const currentMonth = ref(new Date().toISOString().slice(0, 7)) // YYYY-MM
const searchQuery = ref('')
const selectedAccount = ref('')
const selectedCategory = ref('')
const uncategorizedOnly = ref(false)
const limit = ref(50)
const offset = ref(0)

// --- Fetching Metadata ---
const { data: accounts } = await useFetch<any[]>(`${API_BASE}/accounts/`)
const { data: categoryGroups } = await useFetch<any[]>(`${API_BASE}/category-groups`)

// --- Fetching Transactions ---
const queryParams = computed(() => {
  const [year, month] = currentMonth.value.split('-')
  const start_date = `${year}-${month}-01`
  const end_date = new Date(Number(year), Number(month), 0).toISOString().slice(0, 10)

  const params: any = {
    start_date,
    end_date,
    limit: limit.value,
    offset: offset.value
  }

  if (searchQuery.value) params.q = searchQuery.value
  if (selectedAccount.value) params.account_id = selectedAccount.value
  if (selectedCategory.value) params.category_id = selectedCategory.value
  if (uncategorizedOnly.value) params.uncategorized = true

  return params
})

const { 
  data: transactionsData, 
  pending, 
  error, 
  refresh 
} = await useFetch<any>(`${API_BASE}/transactions/`, {
  query: queryParams,
  watch: [queryParams],
  server: false
})

// Reset offset when filters change
watch([searchQuery, selectedAccount, selectedCategory, uncategorizedOnly, currentMonth], () => {
  offset.value = 0
})

// --- Actions ---
const updateTransactionCategory = async (transactionId: string, categoryId: string) => {
  try {
    const response = await fetch(`${API_BASE}/transactions/${transactionId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category_id: categoryId || null })
    })

    if (!response.ok) throw new Error('Failed to update category')
    
    // Refresh the list to show updated category
    refresh()
  } catch (err) {
    alert('Failed to update category. Please try again.')
    console.error(err)
  }
}

// --- Helpers ---
const formatCurrency = (amount: number | string, currency = 'USD') => {
  const val = Number(amount)
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2
  }).format(val)
}

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleDateString('en-US', { 
    year: 'numeric',
    month: 'short', 
    day: 'numeric' 
  })
}
</script>

<style scoped>
.transactions-page {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0;
}

.month-input {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 1rem;
  font-family: inherit;
  color: var(--text-color);
  background: white;
}

.card {
  background: white;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.filters-card {
  padding: 20px;
  margin-bottom: 24px;
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  align-items: flex-end;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-group label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-muted);
}

.filter-input {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 0.95rem;
  font-family: inherit;
}

.checkbox-group {
  justify-content: center;
  height: 38px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 0.95rem !important;
  color: var(--text-color) !important;
}

.table-card {
  overflow: hidden;
}

.transactions-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.transactions-table th {
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border-color);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.transactions-table td {
  padding: 12px 16px;
  border-bottom: 1px solid #f1f5f9;
  font-size: 0.95rem;
}

.transactions-table tr:last-child td {
  border-bottom: none;
}

.date-cell {
  color: var(--text-muted);
  white-space: nowrap;
  width: 120px;
}

.desc-cell {
  max-width: 300px;
}

.desc-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

.account-tag {
  background: #f1f5f9;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-muted);
}

.amount-col {
  text-align: right;
  width: 120px;
}

.amount-cell {
  text-align: right;
  font-weight: 600;
  font-family: monospace;
}

.amount-cell.inflow {
  color: #16a34a;
}

.category-select {
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 0.9rem;
  width: 100%;
  max-width: 200px;
  background: white;
}

.category-select.uncategorized {
  border-color: #fca5a5;
  background-color: #fffafb;
  color: #b91c1c;
}

.empty-row {
  text-align: center;
  padding: 40px !important;
  color: var(--text-muted);
  font-style: italic;
}

.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: #f8fafc;
  border-top: 1px solid var(--border-color);
}

.page-btn {
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  background: white;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.9rem;
  color: var(--text-muted);
}

.loading-state, .error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: var(--text-muted);
}

.spinner {
  border: 4px solid #f3f3f3;
  border-top: 4px solid var(--accent-color);
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.retry-btn {
  margin-top: 12px;
  padding: 8px 16px;
  background: var(--accent-color);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
</style>