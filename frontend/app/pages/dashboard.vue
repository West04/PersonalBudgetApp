<template>
  <div class="dashboard">
    <!-- Header -->
    <header class="page-header">
      <h1 class="page-title">Dashboard</h1>
      <div class="month-selector">
        <input 
          type="month" 
          v-model="currentMonth" 
          class="month-input"
        />
      </div>
    </header>

    <!-- Loading State -->
    <div v-if="pending" class="loading-state">
      <div class="spinner"></div>
      <p>Loading dashboard...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <p>⚠️ Failed to load dashboard data.</p>
      <button @click="refresh" class="retry-btn">Retry</button>
    </div>

    <!-- Dashboard Content -->
    <div v-else-if="data" class="dashboard-content">
      
      <!-- Summary Cards -->
      <div class="summary-grid">
        <!-- Income Card -->
        <div class="card summary-card">
          <div class="card-header">
            <h3>Income</h3>
            <span class="badge" :class="data.income_actual >= data.income_planned ? 'success' : 'warning'">
              {{ formatCurrency(data.income_actual) }}
            </span>
          </div>
          <div class="card-body">
            <div class="row">
              <span class="label">Planned</span>
              <span class="value">{{ formatCurrency(data.income_planned) }}</span>
            </div>
          </div>
        </div>

        <!-- Expenses Card -->
        <div class="card summary-card">
          <div class="card-header">
            <h3>Expenses</h3>
            <span class="badge" :class="data.expense_actual > data.expense_planned ? 'danger' : 'neutral'">
              {{ formatCurrency(data.expense_actual) }}
            </span>
          </div>
          <div class="card-body">
            <div class="row">
              <span class="label">Planned</span>
              <span class="value">{{ formatCurrency(data.expense_planned) }}</span>
            </div>
          </div>
        </div>

        <!-- Balance Card -->
        <div class="card summary-card highlight">
          <div class="card-header">
            <h3>Total Balance</h3>
          </div>
          <div class="card-body centered">
             <span class="big-number">{{ formatCurrency(data.total_balance) }}</span>
          </div>
        </div>

        <!-- To Be Assigned -->
        <div class="card summary-card" v-if="data.to_be_assigned > 0">
           <div class="card-header">
            <h3>Left to Budget</h3>
          </div>
          <div class="card-body centered">
             <span class="big-number success-text">{{ formatCurrency(data.to_be_assigned) }}</span>
          </div>
        </div>
      </div>

      <!-- Main Content Grid -->
      <div class="main-grid">
        
        <!-- Left Column: Spending by Group -->
        <div class="column">
          <div class="card">
            <div class="card-title">Spending by Group</div>
            <div class="group-list">
              <div v-for="group in data.groups" :key="group.group_id" class="group-item">
                <div class="group-header">
                  <span class="group-name">{{ group.name }}</span>
                  <span class="group-values">
                    {{ formatCurrency(group.actual) }} <span class="muted">/ {{ formatCurrency(group.planned) }}</span>
                  </span>
                </div>
                <div class="progress-bar-bg">
                  <div 
                    class="progress-bar-fill" 
                    :style="{ width: calculatePercentage(group.actual, group.planned) + '%' }"
                    :class="{ 'over-budget': group.actual > group.planned }"
                  ></div>
                </div>
              </div>
              <div v-if="data.groups.length === 0" class="empty-message">
                No budget groups found.
              </div>
            </div>
          </div>
        </div>

        <!-- Right Column: Accounts & Transactions -->
        <div class="column">
          
          <!-- Accounts -->
          <div class="card">
            <div class="card-title">Accounts</div>
            <div class="account-list">
              <div v-for="acc in data.accounts" :key="acc.account_id" class="account-item">
                <div class="account-info">
                  <span class="account-name">{{ acc.name }}</span>
                  <span class="account-type">{{ acc.subtype || acc.type }}</span>
                </div>
                <div class="account-balance">
                  {{ formatCurrency(acc.current_balance, acc.currency) }}
                </div>
              </div>
              <div v-if="data.accounts.length === 0" class="empty-message">
                No accounts connected.
              </div>
            </div>
            <div class="card-footer" v-if="data.accounts.length === 0">
              <NuxtLink to="/accounts" class="link-btn">Connect Account</NuxtLink>
            </div>
          </div>

          <!-- Recent Transactions -->
          <div class="card">
            <div class="card-title">Recent Transactions</div>
            <div class="transaction-list">
              <div v-for="tx in data.recent_transactions" :key="tx.transaction_id" class="transaction-item">
                <div class="tx-date">{{ formatDate(tx.date) }}</div>
                <div class="tx-desc">{{ tx.description }}</div>
                <div class="tx-amount" :class="{ 'inflow': tx.amount < 0 }">
                  {{ formatCurrency(Math.abs(tx.amount)) }}
                </div>
              </div>
              <div v-if="data.recent_transactions.length === 0" class="empty-message">
                No recent transactions.
              </div>
            </div>
            <div class="card-footer">
              <NuxtLink to="/transactions" class="link-btn">View All</NuxtLink>
            </div>
          </div>

        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const API_BASE = 'http://localhost:12344'

// --- State ---
const currentMonth = ref(new Date().toISOString().slice(0, 7)) // YYYY-MM

// --- Data Fetching ---
const { data, pending, error, refresh } = await useFetch(`${API_BASE}/summary/dashboard`, {
  query: { month: currentMonth },
  watch: [currentMonth],
  server: false
})

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
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const calculatePercentage = (actual: number | string, planned: number | string) => {
  const act = Number(actual)
  const pln = Number(planned)
  if (pln === 0) return act > 0 ? 100 : 0
  return Math.min((act / pln) * 100, 100)
}
</script>

<style scoped>
.dashboard {
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

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.card {
  background: white;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-header h3 {
  margin: 0;
  font-size: 1rem;
  color: var(--text-muted);
  font-weight: 600;
}

.card-title {
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 12px;
}

.badge {
  font-weight: 700;
  font-size: 1.1rem;
}

.badge.success { color: #16a34a; }
.badge.warning { color: #d97706; }
.badge.danger { color: #dc2626; }
.badge.neutral { color: var(--text-color); }

.row {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
  color: var(--text-muted);
}

.centered {
  display: flex;
  justify-content: center;
  align-items: center;
  flex: 1;
}

.big-number {
  font-size: 1.8rem;
  font-weight: 700;
}

.success-text {
  color: #16a34a;
}

.main-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 24px;
}

@media (max-width: 900px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}

.column {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Group List Styles */
.group-item {
  margin-bottom: 16px;
}

.group-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 0.95rem;
}

.group-name {
  font-weight: 500;
}

.muted {
  color: var(--text-muted);
  font-size: 0.85rem;
}

.progress-bar-bg {
  height: 8px;
  background: #f1f5f9;
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: var(--accent-color);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-bar-fill.over-budget {
  background: #dc2626;
}

/* Account List Styles */
.account-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #f1f5f9;
}

.account-item:last-child {
  border-bottom: none;
}

.account-info {
  display: flex;
  flex-direction: column;
}

.account-name {
  font-weight: 600;
}

.account-type {
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: capitalize;
}

.account-balance {
  font-weight: 600;
}

/* Transaction List Styles */
.transaction-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 0.95rem;
}

.transaction-item:last-child {
  border-bottom: none;
}

.tx-date {
  color: var(--text-muted);
  width: 60px;
  font-size: 0.85rem;
}

.tx-desc {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 12px;
}

.tx-amount {
  font-weight: 500;
}

.tx-amount.inflow {
  color: #16a34a;
}

.empty-message {
  text-align: center;
  padding: 20px;
  color: var(--text-muted);
  font-style: italic;
}

.link-btn {
  display: block;
  text-align: center;
  margin-top: 10px;
  color: var(--accent-color);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.9rem;
}
.link-btn:hover {
  text-decoration: underline;
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
