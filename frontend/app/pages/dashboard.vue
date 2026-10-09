<template>
  <div class="dashboard-page page-container">
    <PageHeader
      title="Dashboard"
      subtitle="Financial position and this month's spending"
    >
      <template #controls>
        <MonthNavigator />
      </template>
    </PageHeader>

    <ErrorBanner
      v-if="error"
      :error="errorMsg"
      @dismiss="dismissError"
    />

    <LoadingState
      v-if="pending && !dashboardData"
      message="Loading financial overview..."
    />

    <div v-else-if="dashboardData" class="dashboard-content">
      <!-- 1. Financial position: Net leads, Cash and card balance support it -->
      <section class="dash-section" aria-labelledby="heading-financial-position">
        <div class="section-head">
          <div class="section-titles">
            <h2 id="heading-financial-position" class="section-heading">Financial position</h2>
            <p class="section-meta">Current balances across active accounts</p>
          </div>
        </div>

        <dl class="position-strip">
          <div class="position-figure position-figure--lead">
            <dt class="position-label">Net position</dt>
            <dd class="position-value position-value--lead">
              <Money
                :amount="position?.netPosition"
                :tone="(position?.netPosition ?? 0) < 0 ? 'debt' : 'neutral'"
              />
            </dd>
            <dd class="position-note">Cash minus credit card debt</dd>
          </div>

          <div class="position-figure">
            <dt class="position-label">Cash</dt>
            <dd class="position-value">
              <Money :amount="position?.depositoryBalance" />
            </dd>
            <dd class="position-note">
              {{ position?.depositoryCount }} depository {{ position?.depositoryCount === 1 ? 'account' : 'accounts' }}
            </dd>
          </div>

          <div class="position-figure">
            <dt class="position-label">
              {{ position?.hasCreditBalance ? 'Credit card balance' : 'Credit card debt' }}
            </dt>
            <dd class="position-value">
              <!-- creditDisplayLabel carries the "credit" wording; tone is chosen explicitly -->
              <span
                class="money"
                :class="position?.hasCreditBalance ? 'money--credit' : 'money--neutral'"
              >{{ position?.creditDisplayLabel }}</span>
            </dd>
            <dd class="position-note">
              {{ position?.hasCreditBalance ? 'Overpayment credit' : 'Total owed' }}
              on {{ position?.creditCardCount }} {{ position?.creditCardCount === 1 ? 'card' : 'cards' }}
            </dd>
          </div>
        </dl>
      </section>

      <!-- 2. Budget attention (derivable, only when present) -->
      <section
        v-if="attentionItems.length > 0"
        class="attention"
        aria-labelledby="heading-attention"
      >
        <div class="attention-head">
          <svg class="attention-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <path d="M10.3 4.2 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z" />
            <path d="M12 9.5v4" />
            <path d="M12 17h.01" />
          </svg>
          <h2 id="heading-attention" class="attention-title">Needs attention</h2>
          <span class="attention-meta">
            {{ attentionItems.length }} budget {{ attentionItems.length === 1 ? 'notice' : 'notices' }}
            for {{ formatMonthDisplay(selectedMonth) }}
          </span>
        </div>
        <ul class="attention-list">
          <li
            v-for="item in attentionItems"
            :key="item.id"
            class="attention-row"
            :class="`attention-row--${item.type}`"
          >
            <span :id="`attention-msg-${item.id}`" class="attention-msg">{{ item.message }}</span>
            <NuxtLink
              :to="{ path: '/categories', query: { month: selectedMonth } }"
              class="attention-link"
              :aria-describedby="`attention-msg-${item.id}`"
            >
              Adjust in budget
            </NuxtLink>
          </li>
        </ul>
      </section>

      <!-- 3. This month's budget: To Be Assigned + spending by group -->
      <section class="dash-section" aria-labelledby="heading-spending-by-group">
        <div class="section-head">
          <div class="section-titles">
            <h2 id="heading-spending-by-group" class="section-heading">Spending by group</h2>
            <p class="section-meta">Spent against plan for {{ formatMonthDisplay(selectedMonth) }}</p>
          </div>
          <NuxtLink
            :to="{ path: '/categories', query: { month: selectedMonth } }"
            class="section-link"
          >
            View full budget
          </NuxtLink>
        </div>

        <div class="budget-panel surface-card">
          <!-- To Be Assigned: value comes straight from the API; only presentation here -->
          <p class="tba" :class="`tba--${tbaState}`">
            <span class="tba-label">To be assigned</span>
            <Money
              class="tba-amount"
              :amount="toBeAssigned"
              sign="never"
              :tone="tbaState === 'over' ? 'overspent' : tbaState === 'unassigned' ? 'available' : 'neutral'"
            />
            <span class="tba-status">
              <template v-if="tbaState === 'over'">over-assigned</template>
              <template v-else-if="tbaState === 'unassigned'">left to assign</template>
              <template v-else>Every dollar has a job</template>
            </span>
          </p>

          <div v-if="groupSpendingList.length === 0" class="panel-empty">
            <p>No budget groups configured for this month.</p>
            <NuxtLink :to="{ path: '/categories', query: { month: selectedMonth } }" class="inline-link">
              Configure budget groups
            </NuxtLink>
          </div>

          <div v-else class="spending-table">
            <div class="spending-columns" aria-hidden="true">
              <span>Group</span>
              <span></span>
              <span class="col-num">Spent</span>
              <span class="col-num">Planned</span>
              <span class="col-num">Remaining</span>
            </div>
            <ul class="spending-list">
              <li
                v-for="{ group, spending } in groupSpendingList"
                :key="group.group_id"
                class="spending-row"
                :class="`is-${spendingState(spending)}`"
              >
                <span class="group-name">{{ group.name }}</span>

                <div
                  class="progress-track"
                  role="progressbar"
                  :aria-valuenow="Math.round(spending.percentage)"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  :aria-valuetext="spendingValueText(spending)"
                  :aria-label="group.name + ' spending progress'"
                >
                  <div
                    class="progress-fill"
                    :style="{ width: spending.percentage + '%' }"
                    :class="{ 'is-over': spending.isOverBudget }"
                  ></div>
                </div>

                <span class="spending-actual">
                  <span class="fig-label">Spent </span><Money :amount="spending.actual" tone="outflow" />
                </span>
                <span class="spending-planned">
                  <span class="fig-label">of </span><Money :amount="spending.planned" /><span class="fig-label"> planned</span>
                </span>

                <span class="spending-status">
                  <template v-if="spendingState(spending) === 'over'">
                    <Money :amount="spending.overAmount" tone="overspent" /> <span class="status-word status-word--over">over</span>
                  </template>
                  <template v-else-if="spendingState(spending) === 'within'">
                    <Money :amount="spending.remaining" tone="available" /><span class="sr-only"> remaining</span>
                  </template>
                  <span v-else-if="spendingState(spending) === 'unbudgeted'" class="status-word">Unbudgeted</span>
                  <span v-else class="status-word status-word--quiet">No budget</span>
                </span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <!-- 4. Supporting context: accounts and recent activity -->
      <div class="supporting-grid">
        <section class="dash-section" aria-labelledby="heading-current-accounts">
          <div class="section-head">
            <div class="section-titles">
              <h2 id="heading-current-accounts" class="section-heading">Current accounts</h2>
              <p class="section-meta">Active accounts and balances</p>
            </div>
            <NuxtLink to="/accounts" class="section-link">Manage accounts</NuxtLink>
          </div>

          <div v-if="activeAccounts.length === 0" class="list-empty">
            <p>No active accounts found.</p>
            <NuxtLink to="/accounts" class="inline-link">Add account</NuxtLink>
          </div>

          <ul v-else class="ledger-list">
            <li
              v-for="acc in activeAccounts"
              :key="acc.account_id"
              class="account-row"
            >
              <span class="row-main">
                <span class="account-name">{{ acc.name }}</span>
                <span class="row-meta">{{ formatAccountTypeLabel(acc) }}</span>
              </span>
              <!-- Card balances keep formatCardBalance wording ("$X owed" / "$X credit");
                   the word is set on its own line so the figures align -->
              <span class="account-balance">
                <span
                  class="money"
                  :class="getAccountBalanceDisplay(acc).isCredit ? 'money--credit' : 'money--neutral'"
                >{{ getAccountBalanceDisplay(acc).formatted }}</span> <span v-if="balanceWord(acc)" class="balance-word">{{ balanceWord(acc) }}</span>
              </span>
            </li>
          </ul>
        </section>

        <section class="dash-section" aria-labelledby="heading-recent-activity">
          <div class="section-head">
            <div class="section-titles">
              <h2 id="heading-recent-activity" class="section-heading">Recent activity</h2>
              <p class="section-meta">Latest transactions in {{ formatMonthDisplay(selectedMonth) }}</p>
            </div>
            <NuxtLink
              :to="{ path: '/transactions', query: { month: selectedMonth } }"
              class="section-link"
            >
              View all transactions
            </NuxtLink>
          </div>

          <div v-if="recentTransactions.length === 0" class="list-empty">
            <p>No transactions in {{ formatMonthDisplay(selectedMonth) }}.</p>
            <NuxtLink to="/upload" class="inline-link">Import statement</NuxtLink>
          </div>

          <ul v-else class="ledger-list">
            <li
              v-for="tx in recentTransactions"
              :key="tx.transaction_id"
              class="tx-row"
            >
              <time class="tx-date num" :datetime="tx.date">{{ formatDate(tx.date) }}</time>
              <span class="row-main">
                <span class="tx-desc" :title="tx.description">{{ tx.description }}</span>
                <span v-if="tx.account?.name" class="row-meta">{{ tx.account.name }}</span>
              </span>
              <span
                class="tx-amount money"
                :class="tx.amount < 0 ? 'money--inflow' : 'money--outflow'"
              >{{ tx.amount < 0 ? '+' : '' }}{{ formatCurrency(Math.abs(Number(tx.amount))) }}</span>
            </li>
          </ul>
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
  type GroupSpendingSummary,
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

// --- Presentation states ---
// These only choose wording and tone for values already supplied by the API
// or computed in dashboardMath; nothing here recalculates a financial figure.

const toBeAssigned = computed(() => Number(dashboardData.value?.to_be_assigned) || 0)

const tbaState = computed<'unassigned' | 'over' | 'assigned'>(() => {
  if (toBeAssigned.value > 0) return 'unassigned'
  if (toBeAssigned.value < 0) return 'over'
  return 'assigned'
})

type SpendingState = 'over' | 'within' | 'unbudgeted' | 'none'

// Mirrors the statusLabel branches in calculateGroupSpending
const spendingState = (s: GroupSpendingSummary): SpendingState => {
  if (s.planned > 0) return s.isOverBudget ? 'over' : 'within'
  return s.actual > 0 ? 'unbudgeted' : 'none'
}

const spendingValueText = (s: GroupSpendingSummary): string =>
  `${formatCurrency(s.actual)} spent of ${formatCurrency(s.planned)} planned. ${s.statusLabel}`

const balanceWord = (acc: DashboardAccount): string => {
  const display = getAccountBalanceDisplay(acc)
  if (display.isOwed) return 'owed'
  if (display.isCredit) return 'credit'
  return ''
}
</script>

<style scoped>
/* Layout ------------------------------------------------------------------ */

.dashboard-content {
  container: dash / inline-size;
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
}

.dash-section {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-md);
  margin-bottom: var(--space-sm);
}

.section-titles {
  min-width: 0;
}

.section-heading {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--type-heading-size);
  font-weight: var(--type-heading-weight);
  line-height: var(--line-height-tight);
  color: var(--text-primary);
}

.section-meta {
  margin: 2px 0 0;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.section-link,
.inline-link,
.attention-link {
  color: var(--accent-text);
  font-weight: var(--font-weight-medium);
  text-decoration: none;
  border-radius: var(--radius-xs);
}

.section-link {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  font-size: var(--type-meta-size);
  white-space: nowrap;
}

.inline-link {
  font-size: var(--type-meta-size);
}

.section-link:hover,
.inline-link:hover,
.attention-link:hover {
  color: var(--accent-hover);
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* 1. Financial position -------------------------------------------------- */

.position-strip {
  margin: 0;
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1fr);
  border-top: 1px solid var(--border-default);
  border-bottom: 1px solid var(--border-default);
}

.position-figure {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: var(--space-md) var(--space-lg);
  border-left: 1px solid var(--border-subtle);
}

.position-figure--lead {
  padding-left: 0;
  border-left: 0;
}

.position-figure dd {
  margin: 0;
}

.position-label {
  font-size: var(--type-label-size);
  font-weight: var(--type-label-weight);
  color: var(--text-secondary);
}

.position-figure .position-value {
  margin-top: var(--space-xs);
}

.position-value {
  font-size: 1.375rem;
  font-weight: var(--type-metric-weight);
  letter-spacing: -0.015em;
  line-height: var(--line-height-tight);
  overflow-wrap: anywhere;
}

.position-value--lead {
  font-size: clamp(1.875rem, 1.25rem + 2.2cqi, 2.5rem);
  letter-spacing: -0.025em;
}

.position-note {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

@container dash (max-width: 560px) {
  .position-strip {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .position-figure {
    padding: var(--space-md) 0 var(--space-md) var(--space-md);
  }

  .position-figure--lead {
    grid-column: 1 / -1;
    padding-left: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .position-figure--lead + .position-figure {
    padding-left: 0;
    border-left: 0;
  }
}

/* 2. Attention ----------------------------------------------------------- */

.attention {
  /* sits closer to the position summary it qualifies */
  margin-top: calc(var(--space-md) - var(--space-xl));
  padding: var(--space-sm) var(--space-md) var(--space-sm) var(--space-md);
  background: var(--status-warning-bg);
  border-left: 3px solid var(--status-warning);
}

.attention-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2xs) var(--space-sm);
}

.attention-icon {
  flex-shrink: 0;
  color: var(--status-warning);
}

.attention-title {
  margin: 0;
  font-size: var(--type-subheading-size);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.attention-meta {
  font-size: var(--type-meta-size);
  color: var(--text-secondary);
}

.attention-list {
  list-style: none;
  margin: var(--space-2xs) 0 0;
  padding: 0 0 0 26px;
}

.attention-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--space-2xs) var(--space-md);
  padding: 6px 0;
}

.attention-row + .attention-row {
  border-top: 1px solid var(--status-warning-border);
}

.attention-msg {
  color: var(--text-primary);
  font-variant-numeric: var(--font-numeric-features);
}

.attention-link {
  font-size: var(--type-meta-size);
  white-space: nowrap;
}

/* 3. Budget panel -------------------------------------------------------- */

.tba {
  margin: 0;
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--space-2xs) var(--space-sm);
  padding: 12px var(--space-md);
  background: var(--bg-sunken);
  border-bottom: 1px solid var(--border-subtle);
  border-radius: var(--radius-md) var(--radius-md) 0 0;
}

.tba-label {
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
}

.tba-amount {
  font-size: 1.0625rem;
  font-weight: var(--font-weight-semibold);
}

.tba-status {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.tba--over .tba-status {
  color: var(--financial-overspent);
  font-weight: var(--font-weight-medium);
}

.tba--unassigned .tba-status {
  color: var(--financial-available);
  font-weight: var(--font-weight-medium);
}

.panel-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-xs);
  padding: var(--space-lg) var(--space-md);
  color: var(--text-muted);
}

.panel-empty p,
.list-empty p {
  margin: 0;
}

.spending-table {
  padding: 0 var(--space-md);
}

.spending-columns,
.spending-row {
  display: grid;
  grid-template-columns:
    minmax(9rem, 1.5fr)
    minmax(3rem, 1.2fr)
    minmax(5.5rem, auto)
    minmax(5.5rem, auto)
    minmax(7.5rem, auto);
  column-gap: clamp(var(--space-sm), 2.5cqi, var(--space-lg));
  align-items: center;
}

.spending-columns {
  padding: 10px 0 6px;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-subtle);
}

.col-num {
  text-align: right;
}

.spending-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.spending-row {
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.spending-row:last-child {
  border-bottom: 0;
}

.group-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.progress-track {
  height: 6px;
  background: var(--bg-subtle);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--text-muted);
  border-radius: var(--radius-full);
}

.progress-fill.is-over {
  background: var(--financial-overspent);
}

/* Spending with no plan is not "over budget": a quiet fill, named in text */
.spending-row.is-unbudgeted .progress-fill {
  background: var(--border-strong);
}

.spending-actual,
.spending-planned,
.spending-status {
  text-align: right;
  white-space: nowrap;
}

.spending-actual {
  font-weight: var(--font-weight-medium);
}

.spending-planned .money {
  color: var(--text-secondary);
}

.status-word {
  font-size: var(--type-meta-size);
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
}

.status-word--over {
  color: var(--financial-overspent);
}

.status-word--quiet {
  font-weight: var(--font-weight-regular);
  color: var(--text-muted);
}

/* Inline words that only appear in the stacked layout */
.fig-label {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

@container dash (max-width: 640px) {
  .spending-table {
    padding: 0 var(--space-md);
  }

  .spending-columns {
    display: none;
  }

  .spending-row {
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas:
      "name name status"
      "bar bar bar"
      "actual planned planned";
    column-gap: 0.3em;
    row-gap: 6px;
    padding: 12px 0;
  }

  .group-name { grid-area: name; }
  .progress-track { grid-area: bar; }
  .spending-status { grid-area: status; padding-left: var(--space-md); }

  .spending-actual,
  .spending-planned {
    text-align: left;
    font-size: var(--type-meta-size);
    color: var(--text-secondary);
  }

  .spending-actual { grid-area: actual; }
  .spending-planned { grid-area: planned; }

  .fig-label {
    position: static;
    width: auto;
    height: auto;
    margin: 0;
    overflow: visible;
    clip: auto;
  }
}

/* 4. Accounts and recent activity ---------------------------------------- */

.supporting-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-xl);
}

@container dash (min-width: 680px) {
  .supporting-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    column-gap: var(--space-2xl);
  }

  /* Share the heading row so both lists start on the same line,
     even when one heading's link wraps */
  .supporting-grid > .dash-section {
    display: grid;
    grid-row: span 2;
    grid-template-rows: subgrid;
    row-gap: 0;
  }

  .supporting-grid .section-head {
    align-content: flex-end;
  }
}

.ledger-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--border-default);
}

.ledger-list > li {
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.row-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.row-meta {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  column-gap: var(--space-md);
}

.account-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.account-balance {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-weight: var(--font-weight-medium);
}

/* "owed" / "credit" sits under the figure so amounts stay flush right */
.balance-word {
  font-size: var(--type-meta-size);
  font-weight: var(--font-weight-regular);
  color: var(--text-muted);
}

.tx-row {
  display: grid;
  grid-template-columns: 3.5rem minmax(0, 1fr) auto;
  align-items: baseline;
  column-gap: var(--space-sm);
}

.tx-date {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.tx-desc {
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tx-amount {
  font-weight: var(--font-weight-medium);
  text-align: right;
}

.list-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-xs);
  padding: var(--space-md) 0;
  border-top: 1px solid var(--border-default);
  color: var(--text-muted);
  font-size: var(--type-meta-size);
}

@media (max-width: 767px) {
  .attention-list {
    padding-left: 0;
  }

  .section-link {
    min-height: 44px;
  }

  .attention-link {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
  }
}
</style>
