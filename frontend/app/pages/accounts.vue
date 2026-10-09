<template>
  <div class="accounts-page page-container">
    <PageHeader
      title="Accounts"
      subtitle="Current balances across active accounts"
    >
      <template #actions>
        <button type="button" class="btn btn-primary" @click="openAddModal">
          <AppIcon name="plus" :size="16" />
          Add account
        </button>
      </template>
    </PageHeader>

    <ErrorBanner v-if="error" :error="error" @dismiss="error = null" />

    <LoadingState v-if="pending" message="Loading accounts..." />

    <!-- A failed load shows only the error, never "No accounts yet" -->
    <EmptyState
      v-else-if="!accounts.length && !error"
      title="No accounts yet"
      description="Add an account to start tracking balances."
    >
      <template #actions>
        <button type="button" class="btn btn-primary" @click="openAddModal">
          <AppIcon name="plus" :size="16" />
          Add account
        </button>
      </template>
    </EmptyState>

    <!-- One ledger surface: column labels once, then a band per account group -->
    <div v-else-if="accounts.length" class="ledger surface-card">
      <div class="ledger-row ledger-head" aria-hidden="true">
        <span class="col-account">Account</span>
        <span class="col-type">Type</span>
        <span class="col-balance">Balance</span>
        <span class="col-status">Status</span>
        <span class="col-actions"></span>
      </div>

      <section
        v-for="group in accountGroups"
        :key="group.key"
        class="account-group"
        :class="`account-group--${group.key}`"
        :aria-labelledby="group.headingId"
      >
        <div class="group-band">
          <h2 :id="group.headingId" class="group-title">{{ group.title }}</h2>
          <span class="group-count num">
            {{ group.accounts.length }} {{ group.accounts.length === 1 ? group.noun : `${group.noun}s` }}
          </span>
        </div>

        <ul class="account-list">
          <li
            v-for="account in group.accounts"
            :key="account.account_id"
            class="ledger-row account-row"
            :class="{ 'is-inactive': !account.is_active }"
          >
            <div class="cell-account">
              <span class="account-name">{{ account.name }}</span>
              <span v-if="account.mask" class="account-mask num">
                <span class="sr-only">ending in </span>••{{ account.mask }}
              </span>
            </div>

            <!-- Card balances use the Dashboard wording: figure, then "owed" / "credit" beneath -->
            <div class="cell-balance">
              <span
                class="money balance-figure"
                :class="getAccountBalance(account).isCredit ? 'money--credit' : 'money--neutral'"
              >{{ getAccountBalance(account).formatted }}</span>
              <span v-if="balanceWord(account)" class="balance-word">{{ balanceWord(account) }}</span>
            </div>

            <!-- Meta and actions share a line when stacked; separate columns when wider -->
            <div class="row-foot">
              <!-- Type and status: own columns when wide, one meta line otherwise -->
              <div class="cell-meta">
                <span class="account-type">{{ formatAccountType(account) }}</span>
                <span v-if="!account.is_active" class="account-status status-inactive">Inactive</span>
                <template v-else-if="group.key === 'depository'">
                  <span v-if="account.last_reconciled_date" class="account-status reconciled-meta">
                    Last reconciled {{ formatDateOnly(account.last_reconciled_date, { includeYear: true }) }}
                  </span>
                  <span v-else class="account-status reconciled-meta is-never">
                    Never reconciled
                  </span>
                </template>
              </div>

              <div class="cell-actions">
                <button
                  v-if="group.key === 'depository'"
                  type="button"
                  class="btn-reconcile"
                  @click="openReconcileModal(account)"
                  :aria-label="`Reconcile ${account.name}`"
                  title="Reconcile account"
                >
                  Reconcile
                </button>
                <button
                  type="button"
                  class="btn-icon"
                  @click="openEditModal(account)"
                  :aria-label="`Edit ${account.name}`"
                  title="Edit account"
                >
                  <AppIcon name="edit" :size="16" />
                </button>
                <button
                  type="button"
                  class="btn-icon btn-icon-danger"
                  @click="confirmDelete(account)"
                  :aria-label="`Delete ${account.name}`"
                  title="Delete account"
                >
                  <AppIcon name="trash" :size="16" />
                </button>
              </div>
            </div>
          </li>
        </ul>
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
  mask?: string | null
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

// Display order and headings for the ledger; empty groups are omitted
const accountGroups = computed(() =>
  [
    { key: 'depository', headingId: 'heading-depository', title: 'Checking and savings', noun: 'account', accounts: depositoryAccounts.value },
    { key: 'credit', headingId: 'heading-credit-cards', title: 'Credit cards', noun: 'card', accounts: creditCardAccounts.value },
    { key: 'other', headingId: 'heading-other', title: 'Other accounts', noun: 'account', accounts: otherAccounts.value },
    { key: 'inactive', headingId: 'heading-inactive', title: 'Inactive accounts', noun: 'account', accounts: inactiveAccounts.value },
  ].filter(group => group.accounts.length > 0)
)

// "owed" / "credit" wording from formatCardBalance; ordinary balances have none
const balanceWord = (account: Account): string => {
  const display = getAccountBalance(account)
  if (display.isOwed) return 'owed'
  if (display.isCredit) return 'credit'
  return ''
}

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
/* Ledger ---------------------------------------------------------------------
   One surface, container-sized tiers:
   stacked (< 560px), compact (560-879px), full (>= 880px).
   Fixed balance and action tracks keep every group's figures on one right edge. */

.ledger {
  container: accounts / inline-size;
  overflow: hidden;
}

.ledger-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    "account balance"
    "foot foot";
  column-gap: var(--space-md);
  row-gap: 2px;
  align-items: center;
  padding: 10px var(--space-md);
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

.ledger-head .col-balance {
  text-align: right;
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

.account-group + .account-group .group-band {
  border-top: 1px solid var(--border-default);
}

.group-title {
  margin: 0;
  font-size: var(--type-subheading-size);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.group-count {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.account-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.account-row + .account-row {
  border-top: 1px solid var(--border-subtle);
}

.account-row:hover {
  background: var(--table-hover);
}

/* Cells */

.cell-account {
  grid-area: account;
  min-width: 0;
  overflow-wrap: anywhere;
}

.account-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

/* Flows after the last word of the name, so long names wrap cleanly */
.account-mask {
  margin-left: var(--space-sm);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  white-space: nowrap;
}

.cell-meta {
  grid-area: meta;
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-md);
  min-width: 0;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.account-type,
.account-status {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-type {
  color: var(--text-secondary);
}

.reconciled-meta.is-never {
  color: var(--text-muted);
}

/* Inactive: subdued and named in text, never styled as an error */
.status-inactive {
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
}

.account-row.is-inactive .account-name {
  color: var(--text-secondary);
}

.cell-balance {
  grid-area: balance;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  text-align: right;
  min-width: 0;
}

.balance-figure {
  font-weight: var(--font-weight-semibold);
}

.account-row.is-inactive .money--neutral {
  color: var(--text-secondary);
}

/* "owed" / "credit" sits under the figure so amounts stay flush right */
.balance-word {
  font-size: var(--type-meta-size);
  line-height: 1.3;
  color: var(--text-muted);
}

.cell-actions {
  grid-area: actions;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}

.cell-actions .btn-icon {
  min-width: 36px;
  min-height: 36px;
  color: var(--text-muted);
}

.cell-actions .btn-icon:hover:not(:disabled) {
  color: var(--text-primary);
}

.cell-actions .btn-icon-danger:hover:not(:disabled),
.cell-actions .btn-icon-danger:focus-visible {
  color: var(--status-error);
}

/* Compact text action in the shared button language (btn btn-ghost btn-sm) */
.btn-reconcile {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  margin-right: var(--space-xs);
  padding: 4px 10px;
  font-family: inherit;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  line-height: 1.25;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.btn-reconcile:hover {
  background-color: var(--bg-subtle);
  color: var(--text-primary);
}

/* Stacked tier: name and balance lead; meta and actions share the line beneath */
@container accounts (width < 560px) {
  .cell-account,
  .cell-balance {
    align-self: start;
  }

  .account-status {
    white-space: normal;
  }

  .row-foot {
    grid-area: foot;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-sm);
    min-width: 0;
  }

  .cell-meta {
    flex: 1 1 auto;
  }

  .cell-actions {
    flex: none;
    margin: -2px -6px -4px 0;
  }
}

/* Compact tier: column labels return; type/status stay under the name */
@container accounts (min-width: 560px) {
  .ledger-row {
    grid-template-columns: minmax(0, 1fr) 9.5rem 9.5rem;
    grid-template-areas:
      "account balance actions"
      "meta balance actions";
    column-gap: var(--space-lg);
  }

  .row-foot {
    display: contents;
  }

  .ledger-head {
    display: grid;
    grid-template-areas: "account balance actions";
  }

  .ledger-head .col-account { grid-area: account; }
  .ledger-head .col-balance { grid-area: balance; }
  .ledger-head .col-actions { grid-area: actions; }
  .ledger-head .col-type,
  .ledger-head .col-status { display: none; }

  .cell-actions .btn-icon {
    min-width: 32px;
    min-height: 32px;
  }
}

/* Full tier: Account | Type | Balance | Status | Actions */
@container accounts (min-width: 880px) {
  .ledger-row {
    grid-template-columns: minmax(10rem, 1fr) 8rem 9.5rem 12.5rem 9.5rem;
    column-gap: var(--space-md);
    grid-template-areas: "account type balance status actions";
    min-height: 52px;
  }

  .ledger-head {
    grid-template-areas: "account type balance status actions";
    min-height: 0;
  }

  .ledger-head .col-type { display: block; grid-area: type; }
  .ledger-head .col-status { display: block; grid-area: status; }

  .cell-meta {
    display: contents;
  }

  .account-type {
    grid-area: type;
    font-size: var(--type-body-size);
  }

  .account-status {
    grid-area: status;
  }
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

/* Reconciliation dialog --------------------------------------------------- */
.right {
  text-align: right;
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
  border-color: var(--status-success-border);
  background-color: var(--status-success-bg);
}

.diff-balanced .card-value {
  color: var(--color-success);
}

.diff-mismatch {
  border-color: var(--status-warning-border);
  background-color: var(--status-warning-bg);
}

.diff-mismatch .card-value {
  color: var(--status-warning);
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
  color: var(--status-warning);
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
  background-color: var(--bg-sunken);
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
  background-color: var(--bg-subtle);
  color: var(--text-secondary);
}

.badge-pending {
  background-color: var(--status-warning-bg);
  color: var(--status-warning);
}

.badge-reviewed {
  background-color: var(--status-success-bg);
  color: var(--status-success);
}

.inflow {
  color: var(--financial-inflow);
}

.reconcile-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  width: 100%;
}

/* Narrow screens: dialog fields stack */
@media (max-width: 640px) {
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
