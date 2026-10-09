<template>
  <div class="cc-page page-container">
    <PageHeader
      title="Credit Cards"
      subtitle="Card balances and monthly activity"
    >
      <template #controls>
        <MonthNavigator />
      </template>
      <template #actions>
        <button
          type="button"
          class="btn btn-ghost btn-sm btn-transfer-matches"
          @click="loadCandidates"
          :disabled="candidatesLoading"
        >
          <AppIcon name="transactions" :size="16" />
          {{ candidatesLoading ? 'Finding transfer matches…' : 'Find transfer matches' }}
        </button>
      </template>
    </PageHeader>

    <ErrorBanner v-if="error" :error="error" @dismiss="error = null" />

    <LoadingState v-if="pending" message="Loading credit cards..." />

    <template v-else-if="summary">
      <EmptyState
        v-if="!summary.cards.length"
        title="No credit cards"
        description="Add an account with the Credit Card type to track card balances here."
      >
        <template #actions>
          <NuxtLink to="/accounts" class="btn btn-secondary">Go to accounts</NuxtLink>
        </template>
      </EmptyState>

      <div v-else class="cc-content">
        <!-- Transfer review: opened by "Find transfer matches" -->
        <section
          v-if="showCandidates"
          class="cc-panel transfer-panel"
          aria-labelledby="heading-transfer-matches"
        >
          <div class="panel-header">
            <div class="panel-titles">
              <h2 id="heading-transfer-matches" class="panel-title">Potential transfers</h2>
              <span v-if="candidates.length > 0" class="panel-count">
                {{ candidates.length }} {{ candidates.length === 1 ? 'match' : 'matches' }}
              </span>
            </div>
            <button
              type="button"
              class="btn-icon btn-close-panel"
              @click="showCandidates = false"
              aria-label="Close transfer matches panel"
            >
              <AppIcon name="close" :size="16" />
            </button>
            <p class="panel-sub">
              These look like transfers appearing on both accounts (credit card payments, savings moves, etc.). Confirm pairs to mark them as transfers.
            </p>
          </div>

          <div v-if="candidates.length === 0" class="panel-empty">
            <p>No potential transfer matches found.</p>
          </div>

          <ul v-else class="candidate-list panel-scroll" tabindex="0" aria-label="Transfer match candidates">
            <li v-for="(pair, idx) in candidates" :key="idx" class="candidate-row">
              <div class="candidate-side outflow">
                <span class="sr-only">From</span>
                <span class="cand-account">{{ pair.outflow_account_name }}</span>
                <span class="cand-desc" :title="pair.outflow_side.description">{{ pair.outflow_side.description }}</span>
                <span class="cand-meta num">{{ formatDate(pair.outflow_side.date) }}</span>
              </div>
              <div class="candidate-arrow">
                <span class="amount-badge money">{{ formatCurrency(Math.abs(Number(pair.outflow_side.amount))) }}</span>
                <AppIcon name="arrow" :size="16" />
              </div>
              <div class="candidate-side inflow">
                <span class="sr-only">To</span>
                <span class="cand-account">{{ pair.inflow_account_name }}</span>
                <span class="cand-desc" :title="pair.inflow_side.description">{{ pair.inflow_side.description }}</span>
                <span class="cand-meta num">{{ formatDate(pair.inflow_side.date) }}</span>
              </div>
              <div class="candidate-actions">
                <button
                  type="button"
                  class="btn btn-secondary btn-sm confirm-btn"
                  @click="confirmTransfer(pair, idx)"
                  :aria-label="`Confirm transfer between ${pair.outflow_account_name} and ${pair.inflow_account_name}`"
                >
                  Confirm
                </button>
                <button
                  type="button"
                  class="btn btn-ghost btn-sm dismiss-btn"
                  @click="candidates.splice(idx, 1)"
                  :aria-label="`Dismiss candidate match between ${pair.outflow_account_name} and ${pair.inflow_account_name}`"
                >
                  Dismiss
                </button>
              </div>
            </li>
          </ul>
        </section>

        <!-- Card ledger: what is owed (or in credit), then the month's movement -->
        <section class="cc-section" aria-labelledby="heading-card-balances">
          <div class="section-head">
            <h2 id="heading-card-balances" class="section-heading">Card balances</h2>
            <p class="section-meta">
              Balances through {{ monthLabel }}; charges and payments in {{ monthLabel }}
            </p>
          </div>

          <div class="ledger surface-card">
            <div class="ledger-row ledger-head" aria-hidden="true">
              <span class="col-card">Card</span>
              <span class="col-num col-balance">Balance</span>
              <span class="col-num col-charged">Charged</span>
              <span class="col-num col-paid">Paid</span>
              <span class="col-num col-starting">Starting balance</span>
            </div>

            <ul class="card-list">
              <li v-for="card in summary.cards" :key="card.account_id" class="ledger-row card-row">
                <div class="cell-card">
                  <h3 class="card-name">{{ card.account_name }}</h3>
                </div>

                <!-- Same wording as Dashboard: figure, then "owed" / "credit" beneath; zero has no word -->
                <div class="cell-balance">
                  <span
                    class="money balance-figure"
                    :class="formatCardBalance(card.balance_owed).isCredit ? 'money--credit' : 'money--neutral'"
                  >{{ formatCardBalance(card.balance_owed).formatted }}</span>
                  <span v-if="cardBalanceWord(card)" class="balance-word">{{ cardBalanceWord(card) }}</span>
                </div>

                <div class="card-metrics">
                  <div class="cell-metric cell-charged">
                    <span class="metric-label">Charged</span>
                    <Money :amount="card.charges_this_month" tone="outflow" />
                  </div>
                  <div class="cell-metric cell-paid">
                    <span class="metric-label">Paid</span>
                    <Money :amount="card.payments_this_month" />
                  </div>
                  <div class="cell-metric cell-starting">
                    <span class="metric-label">Starting balance</span>
                    <input
                      v-if="editingStartingBalance === card.account_id"
                      :id="`starting-balance-${card.account_id}`"
                      type="number"
                      step="0.01"
                      class="form-input inline-input num"
                      :value="card.starting_balance"
                      :aria-label="`Starting balance for ${card.account_name}`"
                      @blur="saveStartingBalance(card, ($event.target as HTMLInputElement).value)"
                      @keydown.enter="($event.target as HTMLInputElement).blur()"
                    />
                    <span v-else class="starting-value">
                      <Money :amount="card.starting_balance" />
                      <button
                        type="button"
                        class="btn-icon btn-edit-starting"
                        :aria-label="`Edit starting balance for ${card.account_name}`"
                        title="Edit starting balance"
                        @click="startEditingStartingBalance(card)"
                      >
                        <AppIcon name="edit" :size="14" />
                      </button>
                    </span>
                  </div>
                </div>
              </li>
            </ul>
          </div>
        </section>

        <!-- Per-card transactions for the month -->
        <section class="cc-section" aria-labelledby="heading-card-activity">
          <div class="section-head">
            <h2 id="heading-card-activity" class="section-heading">Card activity</h2>
            <p class="section-meta">Transactions in {{ monthLabel }}</p>
          </div>

          <div class="activity surface-card">
            <section
              v-for="card in summary.cards"
              :key="card.account_id"
              class="activity-group"
              :aria-labelledby="`activity-${card.account_id}`"
            >
              <div class="group-band">
                <h3 :id="`activity-${card.account_id}`" class="group-title">{{ card.account_name }}</h3>
                <span class="group-count num">
                  {{ card.transactions.length }} {{ card.transactions.length === 1 ? 'transaction' : 'transactions' }}
                </span>
              </div>

              <p v-if="!card.transactions.length" class="activity-empty">
                No transactions this month.
              </p>

              <ul v-else class="txn-list">
                <li
                  v-for="txn in card.transactions"
                  :key="txn.transaction_id"
                  class="txn-row"
                  :class="{ 'is-transfer': txn.is_transfer }"
                >
                  <time class="txn-date num" :datetime="txn.date">{{ formatDate(txn.date) }}</time>
                  <span class="txn-main">
                    <span class="txn-desc" :title="txn.description">{{ txn.description }}</span>
                    <span v-if="txn.is_transfer" class="txn-flag">
                      <AppIcon name="transactions" :size="12" />Transfer
                    </span>
                  </span>
                  <!-- Same amount convention as Transactions: inflow "+", outflow unsigned -->
                  <span
                    class="txn-amount money"
                    :class="txn.amount < 0 ? 'money--inflow' : 'money--outflow'"
                  >{{ txn.amount < 0 ? '+' : '' }}{{ formatCurrency(Math.abs(Number(txn.amount))) }}</span>
                </li>
              </ul>
            </section>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useBudgetMonth } from '~/composables/useBudgetMonth'
import { formatDateOnly } from '~/utils/formatDate'
import { formatMonthDisplay } from '~/utils/monthMath'
import { formatCardBalance, formatCurrency } from '~/utils/dashboardMath'

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

// --- State & Month Synchronization ---
const { selectedMonth } = useBudgetMonth()
const summary = ref<CreditCardSummaryResponse | null>(null)
const candidates = ref<TransferCandidate[]>([])
const showCandidates = ref(false)
const pending = ref(true)
const candidatesLoading = ref(false)
const error = ref<string | null>(null)
const editingStartingBalance = ref<string | null>(null)

// Labels the month the loaded data belongs to (the response's own month), so data
// left over from a failed month change is never presented as the newly selected month
const monthLabel = computed(() => formatMonthDisplay(summary.value?.month ?? selectedMonth.value))

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
    showCandidates.value = true
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

const startEditingStartingBalance = async (card: CreditCardAccountSummary) => {
  editingStartingBalance.value = card.account_id
  await nextTick()
  const input = document.getElementById(`starting-balance-${card.account_id}`) as HTMLInputElement | null
  input?.focus()
  input?.select()
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
// "owed" / "credit" wording from formatCardBalance; a zero balance has none
const cardBalanceWord = (card: CreditCardAccountSummary): string => {
  const display = formatCardBalance(card.balance_owed)
  if (display.isOwed) return 'owed'
  if (display.isCredit) return 'credit'
  return ''
}

const formatDate = (d: string) => formatDateOnly(d)
</script>

<style scoped>
.cc-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
}

.cc-section {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.section-head {
  margin-bottom: var(--space-sm);
}

.section-heading {
  margin: 0;
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

/* Header action: quiet, like the Transactions secondary workflows */
.btn-transfer-matches {
  color: var(--text-secondary);
}

/* Card ledger ----------------------------------------------------------------
   Container-sized tiers: stacked (< 560px), compact (560-859px), full (>= 860px).
   Balance and metric tracks are fixed so right edges line up card to card. */

.ledger {
  container: cards / inline-size;
  overflow: hidden;
}

.ledger-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    "card balance"
    "metrics metrics";
  column-gap: var(--space-md);
  row-gap: 6px;
  align-items: start;
  padding: 12px var(--space-md);
}

.ledger-head {
  display: none;
  padding-top: var(--space-sm);
  padding-bottom: var(--space-sm);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  background: var(--table-header);
  border-bottom: 1px solid var(--border-default);
}

.col-num {
  text-align: right;
}

.card-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.card-row + .card-row {
  border-top: 1px solid var(--border-subtle);
}

.cell-card {
  grid-area: card;
  min-width: 0;
}

.card-name {
  margin: 0;
  font-size: var(--type-body-size);
  font-weight: var(--font-weight-medium);
  line-height: var(--line-height-body);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.cell-balance {
  grid-area: balance;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  text-align: right;
}

.balance-figure {
  font-size: 1.0625rem;
  font-weight: var(--font-weight-semibold);
  line-height: var(--line-height-body);
}

/* "owed" / "credit" sits under the figure so amounts stay flush right */
.balance-word {
  font-size: var(--type-meta-size);
  line-height: 1.3;
  color: var(--text-muted);
}

/* Stacked: supporting metrics share one wrapping line under the card */
.card-metrics {
  grid-area: metrics;
  display: flex;
  flex-wrap: wrap;
  gap: 2px var(--space-lg);
  min-width: 0;
}

.cell-metric {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: var(--type-meta-size);
}

.metric-label {
  color: var(--text-muted);
  white-space: nowrap;
}

.cell-starting {
  flex-wrap: wrap;
}

.cell-metric .money {
  color: var(--text-secondary);
}

.starting-value {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.btn-edit-starting {
  min-width: 28px;
  min-height: 28px;
  padding: 4px;
  color: var(--text-muted);
}

.btn-edit-starting:hover:not(:disabled) {
  color: var(--text-primary);
}

.inline-input {
  width: 8.5rem;
  padding: 4px 8px;
  text-align: right;
}

@container cards (max-width: 559px) {
  .btn-edit-starting {
    min-width: 36px;
    min-height: 36px;
  }
}

/* Compact tier: Card | Balance | Charged | Paid, starting balance under the card */
@container cards (min-width: 560px) {
  .ledger-row {
    grid-template-columns: minmax(0, 1fr) 9.5rem 7.5rem 7.5rem;
    grid-template-areas:
      "card balance charged paid"
      "starting balance charged paid";
    column-gap: var(--space-lg);
    row-gap: 0;
  }

  .ledger-head {
    display: grid;
    grid-template-areas: "card balance charged paid";
  }

  .ledger-head .col-card { grid-area: card; }
  .ledger-head .col-balance { grid-area: balance; }
  .ledger-head .col-charged { grid-area: charged; }
  .ledger-head .col-paid { grid-area: paid; }
  .ledger-head .col-starting { display: none; }

  .card-metrics {
    display: contents;
  }

  .cell-charged { grid-area: charged; }
  .cell-paid { grid-area: paid; }
  .cell-starting { grid-area: starting; }

  .cell-charged,
  .cell-paid {
    justify-content: flex-end;
    font-size: var(--type-body-size);
    line-height: var(--line-height-body);
  }

  /* Column labels carry these names once the header is visible */
  .cell-charged .metric-label,
  .cell-paid .metric-label {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }
}

/* Full tier: Card | Balance | Charged | Paid | Starting balance */
@container cards (min-width: 860px) {
  .ledger-row {
    grid-template-columns: minmax(10rem, 1fr) 9.5rem 8rem 8rem 11rem;
    grid-template-areas: "card balance charged paid starting";
    column-gap: var(--space-md);
    align-items: start;
  }

  .ledger-head {
    grid-template-areas: "card balance charged paid starting";
  }

  .ledger-head .col-starting { display: block; grid-area: starting; }

  .cell-starting {
    justify-content: flex-end;
    font-size: var(--type-body-size);
    line-height: var(--line-height-body);
  }

  .cell-starting .metric-label {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }
}

/* Card activity -------------------------------------------------------------- */

.activity {
  container: activity / inline-size;
  overflow: hidden;
}

.group-band {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px var(--space-sm);
  padding: 8px var(--space-md);
  background: var(--bg-sunken);
  border-bottom: 1px solid var(--border-subtle);
}

.activity-group + .activity-group .group-band {
  border-top: 1px solid var(--border-default);
}

.group-title {
  margin: 0;
  min-width: 0;
  font-size: var(--type-subheading-size);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.group-count {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.activity-empty {
  margin: 0;
  padding: 10px var(--space-md);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.txn-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.txn-row {
  display: grid;
  grid-template-columns: 3.5rem minmax(0, 1fr) auto;
  align-items: baseline;
  column-gap: var(--space-md);
  padding: 7px var(--space-md);
}

.txn-row + .txn-row {
  border-top: 1px solid var(--border-subtle);
}

.txn-date {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.txn-main {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
  min-width: 0;
}

.txn-desc {
  min-width: 0;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.txn-row.is-transfer .txn-desc {
  color: var(--text-secondary);
}

.txn-flag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.txn-amount {
  text-align: right;
  font-weight: var(--font-weight-medium);
}

/* Narrow: the transfer flag drops under the description so it keeps its width */
@container activity (max-width: 559px) {
  .txn-row {
    column-gap: var(--space-sm);
  }

  .txn-main {
    flex-direction: column;
    gap: 0;
  }

  .txn-desc {
    max-width: 100%;
  }
}

/* Transfer review panel (matches the Transactions panel treatment) ----------- */

.cc-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.panel-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  column-gap: var(--space-sm);
  padding: 10px 8px 10px var(--space-md);
}

.panel-titles {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px var(--space-sm);
  min-width: 0;
}

.panel-title {
  margin: 0;
  font-size: var(--type-subheading-size);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.panel-count {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  font-variant-numeric: var(--font-numeric-features);
}

.panel-sub {
  grid-column: 1 / -1;
  margin: 2px 0 0;
  max-width: 80ch;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.panel-empty {
  padding: var(--space-md);
  border-top: 1px solid var(--border-subtle);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.panel-empty p {
  margin: 0;
}

.panel-scroll {
  max-height: 296px;
  overflow: auto;
  border-top: 1px solid var(--border-subtle);
  overscroll-behavior: contain;
}

.panel-scroll:focus-visible {
  outline-offset: -2px;
}

.candidate-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.candidate-row {
  display: grid;
  /* fixed amount/action tracks so every pair lines up with the next */
  grid-template-columns: minmax(0, 1fr) 8.5rem minmax(0, 1fr) 10.5rem;
  align-items: center;
  gap: var(--space-xs) var(--space-md);
  padding: 8px var(--space-md);
}

.candidate-row + .candidate-row {
  border-top: 1px solid var(--border-subtle);
}

.candidate-side {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}

.cand-account {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cand-desc,
.cand-meta {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-arrow {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-sm);
  color: var(--text-muted);
}

.amount-badge {
  font-weight: var(--font-weight-semibold);
  color: var(--financial-neutral);
}

.candidate-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-xs);
}

@media (max-width: 767px) {
  .candidate-row {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    grid-template-areas:
      "amount amount"
      "out in"
      "actions actions";
    align-items: start;
  }

  .candidate-side.outflow { grid-area: out; }
  .candidate-side.inflow { grid-area: in; }
  .candidate-arrow { grid-area: amount; }
  .candidate-actions { grid-area: actions; }

  .candidate-arrow {
    flex-direction: row-reverse;
    justify-content: flex-end;
  }

  .candidate-actions .btn,
  .btn-close-panel {
    min-height: 40px;
  }
}
</style>
