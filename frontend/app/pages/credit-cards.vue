<template>
  <div class="cc-page">
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">Credit Cards</h1>
        <input type="month" v-model="selectedMonth" class="month-picker" />
      </div>
      <button class="secondary-btn" @click="loadCandidates" :disabled="candidatesLoading">
        🔍 Find Transfer Matches
      </button>
    </header>

    <!-- Error Banner -->
    <div v-if="error" class="error-banner">
      {{ error }}
      <button class="close-btn" @click="error = null">✕</button>
    </div>

    <!-- Loading -->
    <div v-if="pending" class="loading-state">
      <div class="spinner"></div>
      <p>Loading credit cards...</p>
    </div>

    <template v-else>
      <!-- Empty state -->
      <div v-if="!summary?.cards.length" class="empty-state">
        <div class="empty-icon">💳</div>
        <h2>No credit card accounts found</h2>
        <p>Add an account with type <strong>credit</strong> to get started.</p>
      </div>

      <template v-else>
        <!-- Transfer Review Panel -->
        <section v-if="candidates.length" class="transfer-panel">
          <div class="panel-header">
            <h2 class="panel-title">⚠️ Unreviewed Transfer Matches ({{ candidates.length }})</h2>
            <p class="panel-sub">These look like transfers appearing on both accounts (credit card payments, savings moves, etc.). Confirm pairs to mark them as transfers.</p>
          </div>
          <div class="candidate-list">
            <div v-for="(pair, idx) in candidates" :key="idx" class="candidate-row">
              <div class="candidate-side outflow">
                <div class="cand-account">{{ pair.outflow_account_name }}</div>
                <div class="cand-desc">{{ pair.outflow_side.description }}</div>
                <div class="cand-meta">{{ formatDate(pair.outflow_side.date) }}</div>
              </div>
              <div class="candidate-arrow">
                <span class="amount-badge">{{ formatCurrency(Math.abs(Number(pair.outflow_side.amount))) }}</span>
                <span class="arrow">→</span>
              </div>
              <div class="candidate-side inflow">
                <div class="cand-account">{{ pair.inflow_account_name }}</div>
                <div class="cand-desc">{{ pair.inflow_side.description }}</div>
                <div class="cand-meta">{{ formatDate(pair.inflow_side.date) }}</div>
              </div>
              <div class="candidate-actions">
                <button class="confirm-btn" @click="confirmTransfer(pair, idx)">✓ Confirm</button>
                <button class="dismiss-btn" @click="candidates.splice(idx, 1)">✕</button>
              </div>
            </div>
          </div>
        </section>

        <!-- Per-card summaries -->
        <div class="cards-grid">
          <div v-for="card in summary.cards" :key="card.account_id" class="cc-card">
            <!-- Card Header -->
            <div class="cc-card-header">
              <div class="cc-card-title-row">
                <span class="cc-icon">💳</span>
                <h2 class="cc-card-name">{{ card.account_name }}</h2>
              </div>
              <div class="cc-balance-owed">
                <div class="balance-label">Balance Owed</div>
                <div class="balance-amount" :class="{ 'positive-balance': card.balance_owed > 0 }">
                  {{ formatCurrency(card.balance_owed) }}
                </div>
              </div>
            </div>

            <!-- Stats Row -->
            <div class="cc-stats">
              <div class="stat">
                <div class="stat-label">Charged This Month</div>
                <div class="stat-value charges">{{ formatCurrency(card.charges_this_month) }}</div>
              </div>
              <div class="stat">
                <div class="stat-label">Paid This Month</div>
                <div class="stat-value payments">{{ formatCurrency(card.payments_this_month) }}</div>
              </div>
              <div class="stat">
                <div class="stat-label">Starting Balance</div>
                <div class="stat-value">
                  <template v-if="editingStartingBalance === card.account_id">
                    <input
                      type="number"
                      step="0.01"
                      class="inline-input starting-balance-input"
                      :value="card.starting_balance"
                      @blur="saveStartingBalance(card, ($event.target as HTMLInputElement).value)"
                      @keydown.enter="($event.target as HTMLInputElement).blur()"
                      ref="startingBalanceInput"
                      autofocus
                    />
                  </template>
                  <template v-else>
                    <span
                      class="starting-balance-display"
                      @click="editingStartingBalance = card.account_id"
                      title="Click to edit"
                    >{{ formatCurrency(card.starting_balance) }} ✏️</span>
                  </template>
                </div>
              </div>
            </div>

            <!-- Transactions List -->
            <div class="cc-transactions">
              <div class="txn-list-header">
                <span>Transactions ({{ card.transactions.length }})</span>
              </div>
              <div v-if="!card.transactions.length" class="txn-empty">
                No transactions this month.
              </div>
              <div
                v-for="txn in card.transactions"
                :key="txn.transaction_id"
                class="txn-row"
                :class="{ 'is-transfer': txn.is_transfer }"
              >
                <div class="txn-left">
                  <span class="txn-date">{{ formatDate(txn.date) }}</span>
                  <span class="txn-desc">{{ txn.description }}</span>
                  <span v-if="txn.is_transfer" class="transfer-badge">transfer</span>
                </div>
                <div class="txn-right">
                  <span
                    class="txn-amount"
                    :class="txn.amount < 0 ? 'payment' : 'charge'"
                  >
                    {{ txn.amount < 0 ? '-' : '+' }}{{ formatCurrency(Math.abs(Number(txn.amount))) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const API_BASE = '/api'

// --- Types ---
interface CreditCardTransaction {
  transaction_id: string
  description: string
  amount: number
  date: string
  is_transfer: boolean
  category_id: string | null
}

interface CreditCardAccountSummary {
  account_id: string
  account_name: string
  starting_balance: number
  balance_owed: number
  charges_this_month: number
  payments_this_month: number
  transactions: CreditCardTransaction[]
}

interface CreditCardSummaryResponse {
  month: string
  cards: CreditCardAccountSummary[]
}

interface TransactionRead {
  transaction_id: string
  description: string
  amount: number
  date: string
  is_transfer: boolean
  account_id: string
}

interface TransferCandidate {
  inflow_side: CreditCardTransaction
  inflow_account_name: string
  outflow_side: TransactionRead
  outflow_account_name: string
}

// --- State ---
const getCurrentMonth = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

const selectedMonth = ref(getCurrentMonth())
const summary = ref<CreditCardSummaryResponse | null>(null)
const candidates = ref<TransferCandidate[]>([])
const pending = ref(true)
const candidatesLoading = ref(false)
const error = ref<string | null>(null)
const editingStartingBalance = ref<string | null>(null)

// --- Fetch ---
const fetchSummary = async () => {
  pending.value = true
  error.value = null
  try {
    summary.value = await $fetch<CreditCardSummaryResponse>(`${API_BASE}/credit-cards/summary`, {
      query: { month: selectedMonth.value }
    })
  } catch (err: any) {
    error.value = err.message || 'Failed to load credit card data'
  } finally {
    pending.value = false
  }
}

const loadCandidates = async () => {
  candidatesLoading.value = true
  error.value = null
  try {
    candidates.value = await $fetch<TransferCandidate[]>(`${API_BASE}/credit-cards/transfer-candidates`)
  } catch (err: any) {
    error.value = err.message || 'Failed to load transfer candidates'
  } finally {
    candidatesLoading.value = false
  }
}

watch(selectedMonth, fetchSummary, { immediate: true })

// --- Actions ---
const confirmTransfer = async (pair: TransferCandidate, idx: number) => {
  try {
    await $fetch(`${API_BASE}/credit-cards/mark-transfers`, {
      method: 'POST',
      body: { transaction_ids: [pair.inflow_side.transaction_id, pair.outflow_side.transaction_id] }
    })
    candidates.value.splice(idx, 1)
    await fetchSummary()
  } catch (err: any) {
    error.value = 'Failed to mark transfers'
  }
}

const saveStartingBalance = async (card: CreditCardAccountSummary, rawValue: string) => {
  const amount = parseFloat(rawValue) || 0
  editingStartingBalance.value = null
  try {
    await $fetch(`${API_BASE}/accounts/${card.account_id}`, {
      method: 'PUT',
      body: { starting_balance: amount }
    })
    await fetchSummary()
  } catch (err: any) {
    error.value = 'Failed to save starting balance'
  }
}

// --- Helpers ---
const formatCurrency = (val: number | string) => {
  const n = parseFloat(String(val)) || 0
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
}

const formatDate = (d: string) =>
  new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
</script>

<style scoped>
.cc-page {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-title {
  margin: 0;
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--text-color);
}

.month-picker {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 1rem;
  color: var(--text-color);
  background: white;
}

.secondary-btn {
  background: white;
  color: var(--accent-color);
  border: 1px solid var(--accent-color);
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.secondary-btn:hover { background: var(--nav-active-bg); }
.secondary-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.error-banner {
  background: #fee2e2;
  color: #dc2626;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.close-btn {
  background: none;
  border: none;
  font-size: 1rem;
  color: inherit;
  cursor: pointer;
}

.loading-state, .empty-state {
  text-align: center;
  padding: 60px;
  color: var(--text-muted);
}
.empty-icon { font-size: 3rem; margin-bottom: 16px; }

.spinner {
  border: 3px solid #f3f3f3;
  border-top: 3px solid var(--accent-color);
  border-radius: 50%;
  width: 30px;
  height: 30px;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Transfer Panel */
.transfer-panel {
  background: #fffbeb;
  border: 1px solid #f59e0b;
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 32px;
}
.panel-header { margin-bottom: 16px; }
.panel-title { margin: 0 0 4px; font-size: 1rem; font-weight: 700; color: #92400e; }
.panel-sub { margin: 0; font-size: 0.85rem; color: #b45309; }

.candidate-list { display: flex; flex-direction: column; gap: 10px; }

.candidate-row {
  background: white;
  border: 1px solid #fde68a;
  border-radius: 10px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.candidate-side {
  flex: 1;
  min-width: 0;
}
.candidate-side.outflow { text-align: right; }
.candidate-side.inflow { text-align: left; }

.cand-account {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 2px;
}
.cand-desc {
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cand-meta { font-size: 0.8rem; color: var(--text-muted); }

.candidate-arrow {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.amount-badge {
  background: #f59e0b;
  color: white;
  font-size: 0.8rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 12px;
}
.arrow { font-size: 1.2rem; color: var(--text-muted); }

.candidate-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.confirm-btn {
  background: #10b981;
  color: white;
  border: none;
  padding: 6px 14px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  font-size: 0.85rem;
  transition: opacity 0.2s;
}
.confirm-btn:hover { opacity: 0.85; }
.dismiss-btn {
  background: #f1f5f9;
  color: var(--text-muted);
  border: none;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.2s;
}
.dismiss-btn:hover { background: #fee2e2; color: #dc2626; }

/* Cards Grid */
.cards-grid {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.cc-card {
  background: white;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.cc-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border-color);
}

.cc-card-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cc-icon { font-size: 1.4rem; }
.cc-card-name { margin: 0; font-size: 1.2rem; font-weight: 700; }

.balance-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.05em;
  text-align: right;
}
.balance-amount {
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--text-color);
}
.balance-amount.positive-balance { color: #ef4444; }

/* Stats */
.cc-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-bottom: 1px solid var(--border-color);
}
.stat {
  padding: 16px 24px;
  border-right: 1px solid var(--border-color);
}
.stat:last-child { border-right: none; }
.stat-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.stat-value {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-color);
}
.stat-value.charges { color: #f59e0b; }
.stat-value.payments { color: #10b981; }

.starting-balance-display {
  cursor: pointer;
  border-bottom: 1px dashed var(--border-color);
  font-size: 0.95rem;
}
.inline-input {
  padding: 4px 8px;
  border: 1px solid var(--accent-color);
  border-radius: 6px;
  font-size: 0.95rem;
  width: 120px;
}

/* Transactions */
.cc-transactions { padding: 0; }
.txn-list-header {
  padding: 10px 24px;
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  background: #fafafa;
  border-bottom: 1px solid var(--border-color);
}
.txn-empty {
  padding: 20px 24px;
  color: var(--text-muted);
  font-size: 0.9rem;
}
.txn-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 24px;
  border-bottom: 1px solid #f1f5f9;
  transition: background 0.15s;
}
.txn-row:last-child { border-bottom: none; }
.txn-row:hover { background: #fafafa; }
.txn-row.is-transfer { opacity: 0.5; }

.txn-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.txn-date {
  font-size: 0.8rem;
  color: var(--text-muted);
  flex-shrink: 0;
  width: 52px;
}
.txn-desc {
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.transfer-badge {
  font-size: 0.65rem;
  background: #e2e8f0;
  color: #64748b;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 700;
  text-transform: uppercase;
  flex-shrink: 0;
}

.txn-amount {
  font-size: 0.9rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.txn-amount.charge { color: #f59e0b; }
.txn-amount.payment { color: #10b981; }
</style>
