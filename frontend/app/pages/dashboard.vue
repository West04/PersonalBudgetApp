<template>
  <div class="dashboard-page">
    <!-- Header -->
    <PageHeader
      title="Dashboard"
      subtitle="Current financial position and monthly spending overview"
    >
      <template #controls>
        <MonthNavigator />
      </template>
    </PageHeader>

    <!-- Error Banner -->
    <ErrorBanner
      v-if="error"
      :error="errorMsg"
      @dismiss="dismissError"
    />

    <!-- Loading State -->
    <LoadingState
      v-if="pending && !dashboardData"
      message="Loading financial overview..."
    />

    <!-- Dashboard Content -->
    <div v-else-if="dashboardData" class="dashboard-content">
      <!-- 1. Financial Position Section -->
      <section class="dashboard-section" aria-labelledby="heading-financial-position">
        <div class="section-header">
          <div>
            <h2 id="heading-financial-position" class="section-title">Current Financial Position</h2>
            <p class="section-sub">Current balances across active accounts</p>
          </div>
        </div>

        <div class="position-grid">
          <!-- Cash / Depository -->
          <div class="position-card">
            <div class="card-meta">
              <span class="card-label">Cash / Depository</span>
              <span class="card-hint">Checking & Savings</span>
            </div>
            <div class="card-value font-mono">
              {{ formatCurrency(position?.depositoryBalance) }}
            </div>
            <div class="card-footer-info">
              {{ position?.depositoryCount }} {{ position?.depositoryCount === 1 ? 'account' : 'accounts' }}
            </div>
          </div>

          <!-- Credit Card Debt -->
          <div class="position-card" :class="{ 'has-credit': position?.hasCreditBalance }">
            <div class="card-meta">
              <span class="card-label">{{ position?.hasCreditBalance ? 'Credit Card Balance' : 'Credit Card Debt' }}</span>
              <span class="card-hint">{{ position?.hasCreditBalance ? 'Overpayment credit' : 'Total owed' }}</span>
            </div>
            <div
              class="card-value font-mono"
              :class="{
                'debt-val': !position?.hasCreditBalance && (position?.creditCardDebt ?? 0) > 0,
                'credit-val': position?.hasCreditBalance
              }"
            >
              {{ position?.creditDisplayLabel }}
            </div>
            <div class="card-footer-info">
              {{ position?.creditCardCount }} {{ position?.creditCardCount === 1 ? 'card' : 'cards' }}
            </div>
          </div>

          <!-- Net Position -->
          <div class="position-card highlight-card">
            <div class="card-meta">
              <span class="card-label">Net Position</span>
              <span class="card-hint">Cash minus credit debt</span>
            </div>
            <div
              class="card-value font-mono"
              :class="(position?.netPosition ?? 0) >= 0 ? 'positive-net' : 'negative-net'"
            >
              {{ formatCurrency(position?.netPosition) }}
            </div>
            <div class="card-footer-info">
              Depository cash − credit debt
            </div>
          </div>
        </div>
      </section>

      <!-- 2. Budget Attention Section (derivable, if any) -->
      <section
        v-if="attentionItems.length > 0"
        class="attention-section"
        aria-label="Budget items requiring attention"
      >
        <div class="attention-header">
          <span class="attention-tag">Attention</span>
          <span class="attention-summary">
            Budget notices for {{ formatMonthDisplay(selectedMonth) }}
          </span>
        </div>
        <div class="attention-list">
          <div
            v-for="item in attentionItems"
            :key="item.id"
            class="attention-row"
            :class="item.type"
          >
            <div class="attention-content">
              <span class="attention-bullet" aria-hidden="true">•</span>
              <span class="attention-msg">{{ item.message }}</span>
            </div>
            <NuxtLink
              :to="{ path: '/categories', query: { month: selectedMonth } }"
              class="attention-action-link"
            >
              Adjust in Budget →
            </NuxtLink>
          </div>
        </div>
      </section>

      <!-- 3. Spending by Group Section -->
      <section class="dashboard-section" aria-labelledby="heading-spending-by-group">
        <div class="section-header">
          <div>
            <h2 id="heading-spending-by-group" class="section-title">Spending by Group</h2>
            <p class="section-sub">
              Spending activity vs planned budget for {{ formatMonthDisplay(selectedMonth) }}
            </p>
          </div>
          <NuxtLink
            :to="{ path: '/categories', query: { month: selectedMonth } }"
            class="section-action-link"
          >
            View Full Budget →
          </NuxtLink>
        </div>

        <div v-if="groupSpendingList.length === 0" class="empty-section-box">
          <p>No budget groups configured for this month.</p>
          <NuxtLink :to="{ path: '/categories', query: { month: selectedMonth } }" class="btn-link">
            Configure Budget Groups
          </NuxtLink>
        </div>

        <div v-else class="spending-list">
          <div
            v-for="{ group, spending } in groupSpendingList"
            :key="group.group_id"
            class="spending-row"
          >
            <div class="spending-info">
              <span class="group-name">{{ group.name }}</span>
              <div class="spending-metrics">
                <span class="spending-actual font-mono">{{ formatCurrency(spending.actual) }}</span>
                <span class="spending-separator">/</span>
                <span class="spending-planned font-mono">{{ formatCurrency(spending.planned) }}</span>
                <span
                  class="spending-status"
                  :class="{
                    'status-over': spending.isOverBudget,
                    'status-remaining': !spending.isOverBudget && spending.planned > 0,
                    'status-unbudgeted': spending.planned === 0
                  }"
                >
                  {{ spending.statusLabel }}
                </span>
              </div>
            </div>

            <!-- Progress Bar -->
            <div
              class="progress-track"
              role="progressbar"
              :aria-valuenow="Math.round(spending.percentage)"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-label="group.name + ' spending progress'"
            >
              <div
                class="progress-fill"
                :style="{ width: spending.percentage + '%' }"
                :class="{ 'is-over': spending.isOverBudget }"
              ></div>
            </div>
          </div>
        </div>
      </section>

      <!-- 4. Supporting Context: Current Accounts & Recent Activity -->
      <div class="supporting-grid">
        <!-- Current Accounts Column -->
        <section class="dashboard-card supporting-card" aria-labelledby="heading-current-accounts">
          <div class="card-inner-header">
            <div>
              <h2 id="heading-current-accounts" class="card-inner-title">Current Accounts</h2>
              <p class="card-inner-sub">Active accounts and balances</p>
            </div>
          </div>

          <div v-if="activeAccounts.length === 0" class="empty-list-note">
            <p>No active accounts found.</p>
            <NuxtLink to="/accounts" class="btn-link">Add Account</NuxtLink>
          </div>

          <div v-else class="account-items">
            <div
              v-for="acc in activeAccounts"
              :key="acc.account_id"
              class="account-row"
            >
              <div class="account-meta">
                <span class="account-name">{{ acc.name }}</span>
                <span class="account-subtype-badge">
                  {{ formatAccountTypeLabel(acc) }}
                </span>
              </div>
              <div
                class="account-balance font-mono"
                :class="{
                  'debt-text': getAccountBalanceDisplay(acc).isOwed,
                  'credit-text': getAccountBalanceDisplay(acc).isCredit
                }"
              >
                {{ getAccountBalanceDisplay(acc).displayLabel }}
              </div>
            </div>
          </div>

          <div class="card-inner-footer">
            <NuxtLink to="/accounts" class="footer-link">
              Manage Accounts →
            </NuxtLink>
          </div>
        </section>

        <!-- Recent Activity Column -->
        <section class="dashboard-card supporting-card" aria-labelledby="heading-recent-activity">
          <div class="card-inner-header">
            <div>
              <h2 id="heading-recent-activity" class="card-inner-title">Recent Activity</h2>
              <p class="card-inner-sub">
                Latest transactions in {{ formatMonthDisplay(selectedMonth) }}
              </p>
            </div>
          </div>

          <div v-if="recentTransactions.length === 0" class="empty-list-note">
            <p>No transactions in {{ formatMonthDisplay(selectedMonth) }}.</p>
            <NuxtLink to="/upload" class="btn-link">Import Statement</NuxtLink>
          </div>

          <div v-else class="transaction-items">
            <div
              v-for="tx in recentTransactions"
              :key="tx.transaction_id"
              class="tx-row"
            >
              <div class="tx-date font-mono">{{ formatDate(tx.date) }}</div>
              <div class="tx-details">
                <div class="tx-desc" :title="tx.description">{{ tx.description }}</div>
                <div v-if="tx.account?.name" class="tx-account-name">{{ tx.account.name }}</div>
              </div>
              <div
                class="tx-amount font-mono"
                :class="{ 'inflow': tx.amount < 0 }"
              >
                {{ tx.amount < 0 ? '+' : '' }}{{ formatCurrency(Math.abs(Number(tx.amount))) }}
              </div>
            </div>
          </div>

          <div class="card-inner-footer">
            <NuxtLink
              :to="{ path: '/transactions', query: { month: selectedMonth } }"
              class="footer-link"
            >
              View All Transactions →
            </NuxtLink>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useBudgetMonth } from '~/composables/useBudgetMonth'
import { useAccountTypes } from '~/composables/useAccountTypes'
import { formatDateOnly } from '~/utils/formatDate'
import { formatMonthDisplay } from '~/utils/monthMath'
import {
  formatCurrency,
  formatCardBalance,
  summarizeFinancialPosition,
  calculateGroupSpending,
  getDerivableBudgetAttention,
  type DashboardAccount,
} from '~/utils/dashboardMath'

const API_BASE = '/api'
const { selectedMonth } = useBudgetMonth()
const { getSubtypeLabel, getTypeLabel } = useAccountTypes()

const manualErrorDismissed = ref(false)

// --- Composed Data Fetching ---
// Reuses existing characterized backend endpoints via frontend composition
const [dashboardRes, creditCardsRes] = await Promise.all([
  useFetch<any>(`${API_BASE}/summary/dashboard`, {
    query: { month: selectedMonth },
    watch: [selectedMonth],
    server: false,
  }),
  useFetch<any>(`${API_BASE}/credit-cards/summary`, {
    query: { month: selectedMonth },
    watch: [selectedMonth],
    server: false,
  }),
])

const dashboardData = dashboardRes.data
const creditCardsData = creditCardsRes.data

const pending = computed(() => dashboardRes.pending.value || creditCardsRes.pending.value)
const error = computed(() => {
  if (manualErrorDismissed.value) return null
  return dashboardRes.error.value || creditCardsRes.error.value || null
})

const errorMsg = computed(() => {
  if (!error.value) return ''
  return error.value.message || 'Failed to load dashboard data. Please try again.'
})

const dismissError = () => {
  manualErrorDismissed.value = true
}

// --- Financial Position Calculations ---
const position = computed(() => {
  if (!dashboardData.value) return null
  return summarizeFinancialPosition(
    dashboardData.value.accounts || [],
    creditCardsData.value?.cards || []
  )
})

// --- Credit Card Lookup Map ---
const creditCardMap = computed(() => {
  const map = new Map<string, number>()
  if (creditCardsData.value?.cards) {
    for (const card of creditCardsData.value.cards) {
      map.set(card.account_id, Number(card.balance_owed) || 0)
    }
  }
  return map
})

// --- Active Accounts & Display ---
const activeAccounts = computed<DashboardAccount[]>(() => {
  if (!dashboardData.value?.accounts) return []
  return dashboardData.value.accounts.filter((a: DashboardAccount) => a.is_active !== false)
})

const getAccountBalanceDisplay = (acc: DashboardAccount) => {
  const typeStr = (acc.type || '').toLowerCase()
  if (typeStr === 'credit') {
    const cardOwed = creditCardMap.value.get(acc.account_id)
    if (cardOwed !== undefined) {
      return formatCardBalance(cardOwed)
    }
    return formatCardBalance(acc.current_balance)
  }
  const bal = Number(acc.current_balance) || 0
  return {
    amount: bal,
    formatted: formatCurrency(bal),
    isOwed: false,
    isCredit: false,
    displayLabel: formatCurrency(bal),
  }
}

const formatAccountTypeLabel = (acc: DashboardAccount): string => {
  if (acc.subtype) {
    return getSubtypeLabel(acc.type, acc.subtype)
  }
  return getTypeLabel(acc.type) || acc.type
}

// --- Spending by Group ---
const groupSpendingList = computed(() => {
  if (!dashboardData.value?.groups) return []
  return dashboardData.value.groups.map((group: any) => ({
    group,
    spending: calculateGroupSpending(group.actual, group.planned),
  }))
})

// --- Attention Items ---
const attentionItems = computed(() => {
  if (!dashboardData.value) return []
  return getDerivableBudgetAttention(
    dashboardData.value.groups || [],
    dashboardData.value.to_be_assigned
  )
})

// --- Recent Transactions ---
const recentTransactions = computed(() => {
  return (dashboardData.value?.recent_transactions || []).slice(0, 5)
})

const formatDate = (dateStr: string) => formatDateOnly(dateStr)
</script>

<style scoped>
.dashboard-page {
  padding: var(--space-lg);
  max-width: var(--page-max-width);
  margin: 0 auto;
}

.dashboard-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
}

.dashboard-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-md);
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
  margin: 0;
  letter-spacing: -0.01em;
}

.section-sub {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 2px 0 0 0;
}

.section-action-link {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-primary);
  text-decoration: none;
  white-space: nowrap;
}

.section-action-link:hover {
  text-decoration: underline;
}

/* 1. Financial Position Grid */
.position-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--space-md);
}

.position-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  box-shadow: var(--shadow-sm);
  transition: border-color 0.15s ease;
}

.position-card.highlight-card {
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border-color: var(--color-border-hover);
}

.card-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.card-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-light);
}

.card-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
  line-height: 1.15;
  margin: var(--space-2xs) 0;
}

.card-value.debt-val {
  color: var(--color-text);
}

.card-value.credit-val {
  color: var(--color-success);
}

.card-value.positive-net {
  color: var(--color-text);
}

.card-value.negative-net {
  color: var(--color-danger);
}

.card-footer-info {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

/* 2. Budget Attention Callout */
.attention-section {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-md);
  padding: var(--space-md) var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.attention-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.attention-tag {
  background: var(--color-warning);
  color: white;
  font-size: var(--font-size-2xs);
  font-weight: var(--font-weight-bold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 6px;
  border-radius: var(--radius-xs);
}

.attention-summary {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-warning-hover);
}

.attention-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.attention-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-2xs) 0;
  font-size: var(--font-size-sm);
}

.attention-content {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.attention-bullet {
  color: var(--color-warning);
  font-size: 1.2rem;
  line-height: 0;
}

.attention-msg {
  color: #78350f;
  font-weight: var(--font-weight-medium);
}

.attention-action-link {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
  text-decoration: none;
  white-space: nowrap;
}

.attention-action-link:hover {
  text-decoration: underline;
}

/* 3. Spending by Group List */
.spending-list {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-md) var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  box-shadow: var(--shadow-sm);
}

.spending-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-xs) 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.spending-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.spending-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.group-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
}

.spending-metrics {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: var(--font-size-sm);
}

.spending-actual {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
}

.spending-separator {
  color: var(--color-text-light);
}

.spending-planned {
  color: var(--color-text-muted);
}

.spending-status {
  margin-left: var(--space-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.status-remaining {
  background: var(--color-success-bg);
  color: var(--color-success-hover);
  border: 1px solid var(--color-success-border);
}

.status-over {
  background: var(--color-danger-bg);
  color: var(--color-danger-hover);
  border: 1px solid var(--color-danger-border);
  font-weight: var(--font-weight-semibold);
}

.status-unbudgeted {
  background: var(--color-surface-hover);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.progress-track {
  height: 8px;
  background: var(--color-surface-hover);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: var(--radius-full);
  transition: width 0.3s ease;
}

.progress-fill.is-over {
  background: var(--color-danger);
}

.empty-section-box {
  background: var(--color-surface);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  text-align: center;
  color: var(--color-text-muted);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  align-items: center;
}

/* 4. Supporting Grid (Accounts & Recent Activity) */
.supporting-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-lg);
}

@media (max-width: 860px) {
  .supporting-grid {
    grid-template-columns: 1fr;
  }
}

.dashboard-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-sm);
}

.card-inner-header {
  margin-bottom: var(--space-md);
  border-bottom: 1px solid var(--color-border-subtle);
  padding-bottom: var(--space-sm);
}

.card-inner-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
  margin: 0;
}

.card-inner-sub {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin: 2px 0 0 0;
}

.account-items,
.transaction-items {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.account-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.account-row:last-child {
  border-bottom: none;
}

.account-meta {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.account-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
}

.account-subtype-badge {
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  background: var(--color-surface-hover);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  text-transform: capitalize;
}

.account-balance {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
}

.account-balance.debt-text {
  color: var(--color-text);
}

.account-balance.credit-text {
  color: var(--color-success);
}

/* Recent Transaction Rows */
.tx-row {
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border-subtle);
  gap: var(--space-sm);
}

.tx-row:last-child {
  border-bottom: none;
}

.tx-date {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  width: 54px;
  flex-shrink: 0;
}

.tx-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.tx-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tx-account-name {
  font-size: var(--font-size-2xs);
  color: var(--color-text-light);
}

.tx-amount {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  flex-shrink: 0;
}

.tx-amount.inflow {
  color: var(--color-success);
}

.empty-list-note {
  padding: var(--space-lg);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  align-items: center;
}

.card-inner-footer {
  margin-top: var(--space-md);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--color-border-subtle);
  display: flex;
  justify-content: flex-end;
}

.footer-link {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
  text-decoration: none;
}

.footer-link:hover {
  text-decoration: underline;
}

.btn-link {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
  text-decoration: none;
  font-weight: var(--font-weight-medium);
}

.btn-link:hover {
  text-decoration: underline;
}
</style>
