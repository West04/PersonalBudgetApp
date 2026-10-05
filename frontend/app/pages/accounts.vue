<template>
  <div class="accounts-page">
    <PageHeader
      title="Accounts"
      subtitle="Current balances across active accounts"
    >
      <template #actions>
        <button type="button" class="btn btn-primary" @click="openAddModal">
          + Add Account
        </button>
      </template>
    </PageHeader>

    <!-- Error Banner -->
    <ErrorBanner v-if="error" :error="error" @dismiss="error = null" />

    <!-- Loading State -->
    <LoadingState v-if="pending" message="Loading accounts..." />

    <!-- Empty State -->
    <EmptyState
      v-else-if="!accounts.length"
      title="No accounts yet"
      description="Add an account to start tracking balances."
    >
      <template #actions>
        <button type="button" class="btn btn-primary" @click="openAddModal">
          + Add Account
        </button>
      </template>
    </EmptyState>

    <!-- Accounts Content -->
    <div v-else class="accounts-content">
      <!-- 1. Depository Group -->
      <section
        v-if="depositoryAccounts.length"
        class="account-group"
        aria-labelledby="heading-depository"
      >
        <div class="group-header">
          <h2 id="heading-depository" class="group-title">Depository</h2>
          <span class="group-count">
            {{ depositoryAccounts.length }} {{ depositoryAccounts.length === 1 ? 'account' : 'accounts' }}
          </span>
        </div>
        <div class="accounts-table surface-card">
          <div class="table-header">
            <span>Account</span>
            <span>Type</span>
            <span class="right">Current Balance</span>
            <span class="sr-only">Actions</span>
          </div>
          <div
            v-for="account in depositoryAccounts"
            :key="account.account_id"
            class="table-row"
          >
            <div class="account-info">
              <div class="account-titles">
                <span class="account-name">{{ account.name }}</span>
                <span v-if="account.last_reconciled_date" class="reconciled-meta">
                  Last reconciled {{ formatDateOnly(account.last_reconciled_date, { includeYear: true }) }}
                </span>
                <span v-else class="reconciled-meta text-muted">
                  Never reconciled
                </span>
              </div>
            </div>
            <div class="account-type-cell">
              <span class="account-subtype">
                {{ formatAccountType(account) }}
              </span>
            </div>
            <div class="account-balance-cell right font-mono">
              {{ formatCurrency(account.current_balance) }}
            </div>
            <div class="row-actions">
              <button
                type="button"
                class="btn-reconcile"
                @click="openReconcileModal(account)"
                :aria-label="`Reconcile ${account.name}`"
                title="Reconcile account"
              >
                ⚖ Reconcile
              </button>
              <button
                type="button"
                class="btn-icon"
                @click="openEditModal(account)"
                :aria-label="`Edit ${account.name}`"
                title="Edit account"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
              </button>
              <button
                type="button"
                class="btn-icon btn-icon-danger"
                @click="confirmDelete(account)"
                :aria-label="`Delete ${account.name}`"
                title="Delete account"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. Credit Cards Group -->
      <section
        v-if="creditCardAccounts.length"
        class="account-group"
        aria-labelledby="heading-credit-cards"
      >
        <div class="group-header">
          <h2 id="heading-credit-cards" class="group-title">Credit Cards</h2>
          <span class="group-count">
            {{ creditCardAccounts.length }} {{ creditCardAccounts.length === 1 ? 'card' : 'cards' }}
          </span>
        </div>
        <div class="accounts-table surface-card">
          <div class="table-header">
            <span>Account</span>
            <span>Type</span>
            <span class="right">Current Balance</span>
            <span class="sr-only">Actions</span>
          </div>
          <div
            v-for="account in creditCardAccounts"
            :key="account.account_id"
            class="table-row"
          >
            <div class="account-info">
              <span class="account-name">{{ account.name }}</span>
            </div>
            <div class="account-type-cell">
              <span class="account-subtype">
                {{ formatAccountType(account) }}
              </span>
            </div>
            <div class="account-balance-cell right font-mono">
              <span
                :class="{
                  'balance-debt': getAccountBalance(account).isOwed,
                  'balance-credit': getAccountBalance(account).isCredit,
                  'balance-zero': !getAccountBalance(account).isOwed && !getAccountBalance(account).isCredit
                }"
              >
                {{ getAccountBalance(account).displayLabel }}
              </span>
            </div>
            <div class="row-actions">
              <button
                type="button"
                class="btn-icon"
                @click="openEditModal(account)"
                :aria-label="`Edit ${account.name}`"
                title="Edit account"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
              </button>
              <button
                type="button"
                class="btn-icon btn-icon-danger"
                @click="confirmDelete(account)"
                :aria-label="`Delete ${account.name}`"
                title="Delete account"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 3. Other Accounts Group (Investments, Loans, etc.) -->
      <section
        v-if="otherAccounts.length"
        class="account-group"
        aria-labelledby="heading-other"
      >
        <div class="group-header">
          <h2 id="heading-other" class="group-title">Other Accounts</h2>
          <span class="group-count">
            {{ otherAccounts.length }} {{ otherAccounts.length === 1 ? 'account' : 'accounts' }}
          </span>
        </div>
        <div class="accounts-table surface-card">
          <div class="table-header">
            <span>Account</span>
            <span>Type</span>
            <span class="right">Current Balance</span>
            <span class="sr-only">Actions</span>
          </div>
          <div
            v-for="account in otherAccounts"
            :key="account.account_id"
            class="table-row"
          >
            <div class="account-info">
              <span class="account-name">{{ account.name }}</span>
            </div>
            <div class="account-type-cell">
              <span class="account-subtype">
                {{ formatAccountType(account) }}
              </span>
            </div>
            <div class="account-balance-cell right font-mono">
              {{ formatCurrency(account.current_balance) }}
            </div>
            <div class="row-actions">
              <button
                type="button"
                class="btn-icon"
                @click="openEditModal(account)"
                :aria-label="`Edit ${account.name}`"
                title="Edit account"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
              </button>
              <button
                type="button"
                class="btn-icon btn-icon-danger"
                @click="confirmDelete(account)"
                :aria-label="`Delete ${account.name}`"
                title="Delete account"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 4. Inactive Accounts Group -->
      <section
        v-if="inactiveAccounts.length"
        class="account-group inactive-group"
        aria-labelledby="heading-inactive"
      >
        <div class="group-header">
          <h2 id="heading-inactive" class="group-title">Inactive Accounts</h2>
          <span class="group-count">
            {{ inactiveAccounts.length }} {{ inactiveAccounts.length === 1 ? 'account' : 'accounts' }}
          </span>
        </div>
        <div class="accounts-table surface-card">
          <div class="table-header">
            <span>Account</span>
            <span>Type</span>
            <span class="right">Current Balance</span>
            <span class="sr-only">Actions</span>
          </div>
          <div
            v-for="account in inactiveAccounts"
            :key="account.account_id"
            class="table-row inactive-row"
          >
            <div class="account-info">
              <span class="account-name">{{ account.name }}</span>
              <span class="status-badge inactive">Inactive</span>
            </div>
            <div class="account-type-cell">
              <span class="account-subtype">
                {{ formatAccountType(account) }}
              </span>
            </div>
            <div class="account-balance-cell right font-mono">
              <span
                :class="{
                  'balance-debt': getAccountBalance(account).isOwed,
                  'balance-credit': getAccountBalance(account).isCredit,
                  'balance-zero': !getAccountBalance(account).isOwed && !getAccountBalance(account).isCredit
                }"
              >
                {{ getAccountBalance(account).displayLabel }}
              </span>
            </div>
            <div class="row-actions">
              <button
                type="button"
                class="btn-icon"
                @click="openEditModal(account)"
                :aria-label="`Edit ${account.name}`"
                title="Edit account"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
              </button>
              <button
                type="button"
                class="btn-icon btn-icon-danger"
                @click="confirmDelete(account)"
                :aria-label="`Delete ${account.name}`"
                title="Delete account"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- Add / Edit Modal -->
    <AppDialog
      :open="modalOpen"
      :title="editingAccount ? 'Edit Account' : 'Add Account'"
      @close="closeModal"
    >
      <FormField label="Account Name" required v-slot="{ id }">
        <input
          :id="id"
          v-model="form.name"
          class="form-input"
          placeholder="e.g. USAA Checking"
          required
        />
      </FormField>

      <div class="field-row">
        <FormField label="Account Type" required v-slot="{ id }">
          <select :id="id" v-model="form.type" class="form-select" @change="onTypeChange">
            <option v-for="t in ACCOUNT_TYPES" :key="t.value" :value="t.value">
              {{ t.label }}
            </option>
          </select>
        </FormField>

        <FormField label="Subtype" v-slot="{ id }">
          <select :id="id" v-model="form.subtype" class="form-select">
            <option v-for="s in getSubtypes(form.type)" :key="s.value" :value="s.value">
              {{ s.label }}
            </option>
          </select>
        </FormField>
      </div>

      <FormField
        label="Starting Balance ($)"
        hint="Balance when tracking began (setup metadata)"
        v-slot="{ id }"
      >
        <input
          :id="id"
          v-model="form.starting_balance"
          type="number"
          step="0.01"
          class="form-input font-mono"
          placeholder="0.00"
        />
      </FormField>

      <div class="status-toggle-wrapper">
        <label class="checkbox-label">
          <input type="checkbox" v-model="form.is_active" class="form-checkbox" />
          <span>Active Account</span>
        </label>
      </div>

      <ErrorBanner v-if="modalError" :error="modalError" :dismissible="false" />

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeModal">Cancel</button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!form.name.trim() || saving"
          @click="saveAccount"
        >
          {{ saving ? 'Saving…' : (editingAccount ? 'Save Changes' : 'Add Account') }}
        </button>
      </template>
    </AppDialog>

    <!-- Reconcile Account Dialog -->
    <AppDialog
      :open="reconcileModalOpen"
      :title="`Reconcile ${reconcilingAccount?.name || 'Account'}`"
      max-width="840px"
      @close="closeReconcileModal"
    >
      <div class="reconcile-dialog-content">
        <!-- Top Inputs: Ending Date and Ending Balance -->
        <div class="reconcile-inputs-grid">
          <FormField label="Statement Ending Date" required v-slot="{ id }">
            <input
              :id="id"
              type="date"
              v-model="reconcileForm.endingDate"
              class="form-input"
              @change="loadReconciliation"
              required
            />
          </FormField>
          <FormField label="Statement Ending Balance ($)" required v-slot="{ id }">
            <input
              :id="id"
              type="number"
              step="0.01"
              v-model.number="reconcileForm.endingBalance"
              class="form-input"
              @input="recalculateDifference"
              placeholder="0.00"
              required
            />
          </FormField>
        </div>

        <!-- Summary Strip (Statement Balance, Cleared Balance, Difference) -->
        <div class="reconcile-summary-strip">
          <div class="summary-card">
            <div class="card-label">Statement Balance</div>
            <div class="card-value font-mono">{{ formatCurrency(Number(reconcileForm.endingBalance) || 0) }}</div>
          </div>
          <div class="summary-card">
            <div class="card-label">Cleared Balance</div>
            <div class="card-value font-mono">{{ formatCurrency(calculatedClearedBalance) }}</div>
            <div class="card-subtext">
              Baseline: {{ formatCurrency(Number(reconcileSummary?.prior_reconciled_balance) || 0) }}
            </div>
          </div>
          <div
            class="summary-card diff-card"
            :class="{ 'diff-balanced': isBalanced, 'diff-mismatch': !isBalanced }"
          >
            <div class="card-label">Difference</div>
            <div class="card-value font-mono">{{ formatCurrency(differenceAmount) }}</div>
            <div class="card-status-text" aria-live="polite">
              {{ isBalanced ? '✓ Balanced ($0.00)' : `${formatCurrency(Math.abs(differenceAmount))} to balance` }}
            </div>
          </div>
        </div>

        <!-- Error Banner inside modal -->
        <ErrorBanner
          v-if="reconcileError"
          :error="reconcileError"
          @dismiss="reconcileError = null"
        />

        <!-- Loading State -->
        <LoadingState v-if="reconcileLoading" message="Loading account transactions..." />

        <!-- Transactions Section -->
        <div v-else class="reconcile-transactions-section">
          <div class="tx-header-bar">
            <div class="tx-counts">
              <span class="count-badge">
                <strong>{{ clearedCount }}</strong> of <strong>{{ totalTxnCount }}</strong> cleared
              </span>
            </div>
            <button
              v-if="totalTxnCount > 0"
              type="button"
              class="btn-text"
              @click="toggleClearAll"
            >
              {{ allCleared ? 'Unclear All' : 'Clear All' }}
            </button>
          </div>

          <div v-if="!reconcileSummary?.transactions?.length" class="empty-reconcile-txns">
            <p>No unreconciled transactions dated on or before {{ reconcileForm.endingDate }}.</p>
          </div>

          <div v-else class="reconcile-table-wrapper">
            <table class="reconcile-table" aria-label="Transactions to reconcile">
              <thead>
                <tr>
                  <th scope="col" class="th-cleared">Cleared</th>
                  <th scope="col">Date</th>
                  <th scope="col">Description</th>
                  <th scope="col" class="right">Amount</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="tx in reconcileSummary.transactions"
                  :key="tx.transaction_id"
                  :class="{ 'row-cleared': tx.is_cleared }"
                >
                  <td class="td-cleared">
                    <input
                      type="checkbox"
                      :checked="tx.is_cleared"
                      @change="toggleTxCleared(tx)"
                      :aria-label="`Mark ${tx.description} as cleared`"
                      class="reconcile-checkbox"
                    />
                  </td>
                  <td class="font-mono text-sm">{{ formatDateOnly(tx.date) }}</td>
                  <td class="desc-cell">
                    <span class="tx-desc" :title="tx.description">{{ tx.description }}</span>
                    <span v-if="tx.is_transfer" class="badge-transfer">transfer</span>
                    <span v-if="tx.pending" class="badge-pending">pending</span>
                    <span v-if="tx.is_reviewed" class="badge-reviewed">reviewed</span>
                  </td>
                  <td
                    class="font-mono right text-sm"
                    :class="{ 'inflow': Number(tx.amount) < 0 }"
                  >
                    {{ Number(tx.amount) < 0 ? '+' : '' }}{{ formatCurrency(Math.abs(Number(tx.amount))) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="reconcile-footer">
          <button type="button" class="btn btn-ghost" @click="closeReconcileModal">
            Cancel
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="!isBalanced || completingReconcile || reconcileLoading"
            @click="finishReconciliation"
          >
            {{ completingReconcile ? 'Finishing…' : 'Finish Reconciliation' }}
          </button>
        </div>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ACCOUNT_TYPES, useAccountTypes } from '~/composables/useAccountTypes'
import { formatCurrency, formatCardBalance } from '~/utils/dashboardMath'
import { formatDateOnly } from '~/utils/formatDate'

const { getSubtypes, getSubtypeLabel, getTypeLabel, defaultSubtype } = useAccountTypes()

const API_BASE = '/api'

// --- Types ---
interface Account {
  account_id: string
  name: string
  type: string
  subtype: string | null
  current_balance: number
  starting_balance: number
  available_balance: number | null
  currency: string
  is_active: boolean
  last_reconciled_date?: string | null
  last_reconciled_balance?: number | null
}

interface CreditCardAccountSummary {
  account_id: string
  account_name: string
  starting_balance: number
  balance_owed: number
  charges_this_month: number
  payments_this_month: number
}

interface CreditCardSummaryResponse {
  month: string
  cards: CreditCardAccountSummary[]
}

// --- State ---
const accounts = ref<Account[]>([])
const creditCardsSummary = ref<CreditCardSummaryResponse | null>(null)
const pending = ref(true)
const error = ref<string | null>(null)
const modalOpen = ref(false)
const editingAccount = ref<Account | null>(null)
const saving = ref(false)
const modalError = ref('')

const emptyForm = () => ({
  name: '',
  type: 'depository',
  subtype: 'checking',
  starting_balance: 0,
  is_active: true,
})
const form = ref(emptyForm())

// --- Fetch & Composition ---
// Composes /api/accounts/ with /api/credit-cards/summary so that credit card
// accounts display authoritative balance_owed rather than uncalculated static columns.
const fetchAccounts = async () => {
  pending.value = true
  error.value = null
  try {
    const currentMonth = new Date().toISOString().slice(0, 7)
    const [accountsData, creditCardsData] = await Promise.all([
      $fetch<Account[]>(`${API_BASE}/accounts/`),
      $fetch<CreditCardSummaryResponse>(`${API_BASE}/credit-cards/summary`, {
        query: { month: currentMonth },
      }).catch((err) => {
        console.warn('Failed to load credit cards summary:', err)
        return null
      }),
    ])
    accounts.value = accountsData || []
    creditCardsSummary.value = creditCardsData
  } catch (e: any) {
    error.value = e.message || 'Failed to load accounts'
  } finally {
    pending.value = false
  }
}

onMounted(fetchAccounts)

// --- Authoritative Credit Card Owed Lookup Map ---
const creditCardOwedMap = computed(() => {
  const map = new Map<string, number>()
  if (creditCardsSummary.value?.cards) {
    for (const card of creditCardsSummary.value.cards) {
      map.set(card.account_id, Number(card.balance_owed) || 0)
    }
  }
  return map
})

// --- Account Balance Formatter ---
// Follows contract:
// - Depository/Other: $X.XX
// - Credit card: balance_owed > 0 => "$X.XX owed", balance_owed < 0 => "$X.XX credit", 0 => "$0.00"
const getAccountBalance = (account: Account) => {
  const typeStr = (account.type || '').toLowerCase()
  if (typeStr === 'credit') {
    const cardOwed = creditCardOwedMap.value.get(account.account_id)
    if (cardOwed !== undefined) {
      return formatCardBalance(cardOwed)
    }
    return formatCardBalance(account.current_balance)
  }
  const bal = Number(account.current_balance) || 0
  return {
    amount: bal,
    formatted: formatCurrency(bal),
    isOwed: false,
    isCredit: false,
    displayLabel: formatCurrency(bal),
  }
}

const formatAccountType = (account: Account): string => {
  if (account.subtype) {
    return getSubtypeLabel(account.type, account.subtype)
  }
  return getTypeLabel(account.type) || account.type
}

// --- Semantic Groupings ---
const activeAccounts = computed(() => accounts.value.filter(a => a.is_active))
const inactiveAccounts = computed(() => accounts.value.filter(a => !a.is_active))

const depositoryAccounts = computed(() =>
  activeAccounts.value.filter(a => (a.type || '').toLowerCase() === 'depository')
)

const creditCardAccounts = computed(() =>
  activeAccounts.value.filter(a => (a.type || '').toLowerCase() === 'credit')
)

const otherAccounts = computed(() =>
  activeAccounts.value.filter(a => {
    const t = (a.type || '').toLowerCase()
    return t !== 'depository' && t !== 'credit'
  })
)

// --- Modal Handlers ---
const openAddModal = () => {
  editingAccount.value = null
  form.value = emptyForm()
  modalError.value = ''
  modalOpen.value = true
}

const openEditModal = (account: Account) => {
  editingAccount.value = account
  form.value = {
    name: account.name,
    type: account.type,
    subtype: account.subtype ?? defaultSubtype(account.type),
    starting_balance: Number(account.starting_balance) || 0,
    is_active: account.is_active,
  }
  modalError.value = ''
  modalOpen.value = true
}

const closeModal = () => {
  modalOpen.value = false
  editingAccount.value = null
}

const onTypeChange = () => {
  form.value.subtype = defaultSubtype(form.value.type)
}

// --- Save & Delete ---
const saveAccount = async () => {
  if (!form.value.name.trim()) return
  saving.value = true
  modalError.value = ''
  try {
    const startingBalance = Number(form.value.starting_balance) || 0
    if (editingAccount.value) {
      // Edit Account: update metadata and setup starting balance.
      // current_balance is NOT sent to prevent arbitrary direct overwrite.
      await $fetch(`${API_BASE}/accounts/${editingAccount.value.account_id}`, {
        method: 'PUT',
        body: {
          name: form.value.name.trim(),
          type: form.value.type,
          subtype: form.value.subtype || null,
          starting_balance: startingBalance,
          is_active: form.value.is_active,
        },
      })
    } else {
      // Add Account: newly created account baseline.
      // current_balance initialized to starting_balance as opening baseline with 0 transactions.
      await $fetch(`${API_BASE}/accounts/`, {
        method: 'POST',
        body: {
          name: form.value.name.trim(),
          type: form.value.type,
          subtype: form.value.subtype || null,
          starting_balance: startingBalance,
          current_balance: startingBalance,
          currency: 'USD',
          is_active: form.value.is_active,
        },
      })
    }
    await fetchAccounts()
    closeModal()
  } catch (e: any) {
    modalError.value = e.data?.detail ?? e.message ?? 'Failed to save account'
  } finally {
    saving.value = false
  }
}

const confirmDelete = async (account: Account) => {
  if (!confirm(`Delete "${account.name}"? This cannot be undone.`)) return
  try {
    await $fetch(`${API_BASE}/accounts/${account.account_id}`, { method: 'DELETE' })
    await fetchAccounts()
  } catch (e: any) {
    error.value = e.data?.detail ?? e.message ?? 'Failed to delete account'
  }
}

// --- Reconciliation State & Handlers ---
interface ReconciliationTransaction {
  transaction_id: string
  account_id: string
  date: string
  description: string
  amount: number
  pending: boolean
  is_transfer: boolean
  is_reviewed: boolean
  is_cleared: boolean
  is_reconciled: boolean
}

interface ReconciliationSummary {
  account_id: string
  account_name: string
  account_type: string
  starting_balance: number
  last_reconciled_date: string | null
  last_reconciled_balance: number | null
  prior_reconciled_balance: number
  statement_ending_date: string
  statement_ending_balance: number
  cleared_balance: number
  difference: number
  cleared_count: number
  uncleared_count: number
  is_balanced: boolean
  transactions: ReconciliationTransaction[]
}

const reconcileModalOpen = ref(false)
const reconcilingAccount = ref<Account | null>(null)
const reconcileForm = ref({
  endingDate: new Date().toISOString().slice(0, 10),
  endingBalance: 0,
})
const reconcileSummary = ref<ReconciliationSummary | null>(null)
const reconcileLoading = ref(false)
const reconcileError = ref<string | null>(null)
const completingReconcile = ref(false)

const openReconcileModal = async (account: Account) => {
  reconcilingAccount.value = account
  reconcileError.value = null
  const today = new Date().toISOString().slice(0, 10)
  const defaultBalance = account.current_balance !== undefined ? Number(account.current_balance) : 0
  reconcileForm.value = {
    endingDate: today,
    endingBalance: defaultBalance,
  }
  reconcileModalOpen.value = true
  await loadReconciliation()
}

const closeReconcileModal = () => {
  reconcileModalOpen.value = false
  reconcilingAccount.value = null
  reconcileSummary.value = null
}

const loadReconciliation = async () => {
  if (!reconcilingAccount.value) return
  reconcileLoading.value = true
  reconcileError.value = null
  try {
    const data = await $fetch<ReconciliationSummary>(
      `${API_BASE}/accounts/${reconcilingAccount.value.account_id}/reconciliation`,
      {
        query: {
          ending_date: reconcileForm.value.endingDate,
          ending_balance: reconcileForm.value.endingBalance,
        },
      }
    )
    reconcileSummary.value = data
  } catch (err: any) {
    reconcileError.value = err.data?.detail || err.message || 'Failed to load reconciliation data'
  } finally {
    reconcileLoading.value = false
  }
}

const clearedCount = computed(() => {
  return reconcileSummary.value?.transactions.filter(t => t.is_cleared).length || 0
})

const totalTxnCount = computed(() => {
  return reconcileSummary.value?.transactions.length || 0
})

const allCleared = computed(() => {
  return totalTxnCount.value > 0 && clearedCount.value === totalTxnCount.value
})

const calculatedClearedBalance = computed(() => {
  if (!reconcileSummary.value) return 0
  const prior = Number(reconcileSummary.value.prior_reconciled_balance) || 0
  const clearedNet = reconcileSummary.value.transactions
    .filter(t => t.is_cleared)
    .reduce((sum, t) => sum + Number(t.amount), 0)
  return Math.round((prior - clearedNet) * 100) / 100
})

const differenceAmount = computed(() => {
  const stmt = Number(reconcileForm.value.endingBalance) || 0
  return Math.round((stmt - calculatedClearedBalance.value) * 100) / 100
})

const isBalanced = computed(() => {
  return Math.abs(differenceAmount.value) < 0.005
})

const recalculateDifference = () => {
  // Computed reactively
}

const toggleTxCleared = async (tx: ReconciliationTransaction) => {
  const newStatus = !tx.is_cleared
  tx.is_cleared = newStatus
  try {
    await $fetch(`${API_BASE}/transactions/${tx.transaction_id}/cleared`, {
      method: 'PATCH',
      body: { is_cleared: newStatus },
    })
  } catch (err: any) {
    tx.is_cleared = !newStatus
    reconcileError.value = err.data?.detail || 'Failed to update transaction cleared status'
  }
}

const toggleClearAll = async () => {
  if (!reconcileSummary.value) return
  const targetStatus = !allCleared.value
  const txsToUpdate = reconcileSummary.value.transactions.filter(t => t.is_cleared !== targetStatus)
  for (const tx of txsToUpdate) {
    tx.is_cleared = targetStatus
    try {
      await $fetch(`${API_BASE}/transactions/${tx.transaction_id}/cleared`, {
        method: 'PATCH',
        body: { is_cleared: targetStatus },
      })
    } catch (err: any) {
      console.warn('Failed to toggle cleared status', tx.transaction_id, err)
    }
  }
}

const finishReconciliation = async () => {
  if (!reconcilingAccount.value || !isBalanced.value) return
  completingReconcile.value = true
  reconcileError.value = null
  try {
    await $fetch(
      `${API_BASE}/accounts/${reconcilingAccount.value.account_id}/reconciliation/complete`,
      {
        method: 'POST',
        body: {
          statement_ending_date: reconcileForm.value.endingDate,
          statement_ending_balance: reconcileForm.value.endingBalance,
        },
      }
    )
    closeReconcileModal()
    await fetchAccounts()
  } catch (err: any) {
    reconcileError.value = err.data?.detail || err.message || 'Failed to complete reconciliation'
  } finally {
    completingReconcile.value = false
  }
}
</script>

<style scoped>
.accounts-page {
  padding: var(--space-lg);
  max-width: var(--page-max-width);
  margin: 0 auto;
}

.accounts-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
}

/* Account Groups */
.account-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 0 var(--space-2xs);
}

.group-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
  margin: 0;
  letter-spacing: -0.01em;
}

.group-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-weight: var(--font-weight-medium);
}

/* Table */
.accounts-table {
  overflow: hidden;
}

.table-header {
  display: grid;
  grid-template-columns: minmax(180px, 2fr) minmax(120px, 1fr) minmax(140px, 1fr) auto;
  align-items: center;
  padding: 10px var(--space-md);
  background-color: var(--color-background);
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.table-row {
  display: grid;
  grid-template-columns: minmax(180px, 2fr) minmax(120px, 1fr) minmax(140px, 1fr) auto;
  align-items: center;
  padding: 14px var(--space-md);
  border-bottom: 1px solid var(--color-border-subtle);
  font-size: var(--font-size-base);
  transition: background-color 0.15s ease;
}

.table-row:last-child {
  border-bottom: none;
}

.table-row:hover {
  background-color: var(--color-surface-hover);
}

.account-info {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-width: 0;
}

.account-name {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.account-subtype {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.account-balance-cell {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-base);
}

.balance-debt {
  color: var(--color-danger);
}

.balance-credit {
  color: var(--color-success);
}

.balance-zero {
  color: var(--color-text);
}

.right {
  text-align: right;
}

.row-actions {
  display: flex;
  gap: var(--space-2xs);
  justify-content: flex-end;
}

/* Inactive Accounts Styling */
.inactive-group {
  opacity: 0.85;
}

.inactive-row {
  background-color: #fafbfc;
}

.status-badge {
  font-size: var(--font-size-2xs);
  font-weight: var(--font-weight-bold);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  display: inline-block;
}

.status-badge.inactive {
  background-color: var(--color-surface-hover);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

/* Modal Form Layout */
.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

.status-toggle-wrapper {
  margin-top: var(--space-xs);
  margin-bottom: var(--space-md);
}

/* Reconciliation Styling */
.account-titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.reconciled-meta {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
}

.reconciled-meta.text-muted {
  color: var(--color-text-muted);
  font-weight: normal;
}

.btn-reconcile {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-sm);
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-reconcile:hover {
  background-color: var(--color-surface-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.reconcile-dialog-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.reconcile-inputs-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

.reconcile-summary-strip {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--space-sm);
}

.summary-card {
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-sm) var(--space-md);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.summary-card .card-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: var(--font-weight-bold);
  margin-bottom: 2px;
}

.summary-card .card-value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
}

.summary-card .card-subtext {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
}

.diff-card {
  border-width: 2px;
}

.diff-balanced {
  border-color: var(--color-success);
  background-color: #f0fdf4;
}

.diff-balanced .card-value {
  color: var(--color-success);
}

.diff-mismatch {
  border-color: #f59e0b;
  background-color: #fffbeb;
}

.diff-mismatch .card-value {
  color: #b45309;
}

.card-status-text {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  margin-top: 2px;
}

.diff-balanced .card-status-text {
  color: var(--color-success);
}

.diff-mismatch .card-status-text {
  color: #b45309;
}

.reconcile-transactions-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.tx-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
}

.count-badge {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.btn-text {
  background: none;
  border: none;
  color: var(--color-primary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  padding: 2px 6px;
  text-decoration: underline;
}

.empty-reconcile-txns {
  padding: var(--space-lg);
  text-align: center;
  background-color: var(--color-background);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.reconcile-table-wrapper {
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.reconcile-table {
  width: 100%;
  border-collapse: collapse;
}

.reconcile-table th {
  position: sticky;
  top: 0;
  background-color: var(--color-background);
  border-bottom: 1px solid var(--color-border);
  padding: 8px 12px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-muted);
  text-align: left;
  z-index: 1;
}

.reconcile-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border-subtle);
  font-size: var(--font-size-sm);
}

.th-cleared, .td-cleared {
  width: 48px;
  text-align: center !important;
}

.reconcile-checkbox {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.row-cleared {
  background-color: #f8fafc;
}

.desc-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 320px;
}

.tx-desc {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.badge-transfer, .badge-pending, .badge-reviewed {
  font-size: 10px;
  font-weight: var(--font-weight-semibold);
  padding: 1px 5px;
  border-radius: var(--radius-sm);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}

.badge-transfer {
  background-color: #e0e7ff;
  color: #3730a3;
}

.badge-pending {
  background-color: #fef3c7;
  color: #92400e;
}

.badge-reviewed {
  background-color: #d1fae5;
  color: #065f46;
}

.inflow {
  color: var(--color-success);
}

.reconcile-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  width: 100%;
}

/* Responsive Narrow Screen Adaptations */
@media (max-width: 640px) {
  .accounts-page {
    padding: var(--space-md);
  }

  .table-header {
    display: none;
  }

  .table-row {
    grid-template-columns: 1fr auto;
    grid-template-areas:
      "info actions"
      "type balance";
    row-gap: var(--space-xs);
    padding: var(--space-md);
  }

  .account-info {
    grid-area: info;
  }

  .row-actions {
    grid-area: actions;
  }

  .account-type-cell {
    grid-area: type;
  }

  .account-balance-cell {
    grid-area: balance;
  }

  .field-row {
    grid-template-columns: 1fr;
  }

  .reconcile-inputs-grid {
    grid-template-columns: 1fr;
  }

  .reconcile-summary-strip {
    grid-template-columns: 1fr;
  }
}
</style>
