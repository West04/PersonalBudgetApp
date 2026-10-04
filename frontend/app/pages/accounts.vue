<template>
  <div class="accounts-page">
    <PageHeader title="Accounts">
      <template #actions>
        <button type="button" class="btn btn-primary" @click="openAddModal">+ Add Account</button>
      </template>
    </PageHeader>

    <!-- Error Banner -->
    <ErrorBanner :error="error" @dismiss="error = null" />

    <!-- Loading -->
    <LoadingState v-if="pending" message="Loading accounts..." />

    <!-- Empty -->
    <EmptyState
      v-else-if="!accounts.length"
      title="No accounts yet"
      description="Add your bank accounts to start tracking."
    >
      <template #actions>
        <button type="button" class="btn btn-primary" @click="openAddModal">+ Add Account</button>
      </template>
    </EmptyState>

    <!-- Accounts grouped by type -->
    <template v-else>
      <div v-for="typeDef in accountTypeGroups" :key="typeDef.value" class="type-group">
        <h2 class="type-group-label">{{ typeDef.label }}</h2>
        <div class="accounts-table">
          <div class="table-header">
            <span>Name</span>
            <span>Subtype</span>
            <span class="right">Starting Balance</span>
            <span class="right">Current Balance</span>
            <span>Status</span>
            <span></span>
          </div>
          <div
            v-for="account in getAccountsByType(typeDef.value)"
            :key="account.account_id"
            class="table-row"
            :class="{ 'inactive': !account.is_active }"
          >
            <span class="account-name">{{ account.name }}</span>
            <span class="account-subtype">{{ getSubtypeLabel(account.type, account.subtype ?? '') || '—' }}</span>
            <span class="right font-mono">{{ formatCurrency(account.starting_balance) }}</span>
            <span class="right font-mono">{{ formatCurrency(account.current_balance) }}</span>
            <span>
              <span :class="['status-badge', account.is_active ? 'active' : 'inactive']">
                {{ account.is_active ? 'Active' : 'Inactive' }}
              </span>
            </span>
            <span class="row-actions">
              <button
                type="button"
                class="btn-icon"
                @click="openEditModal(account)"
                aria-label="Edit account"
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
                aria-label="Delete account"
                title="Delete account"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </span>
          </div>
        </div>
      </div>
    </template>

    <!-- Add / Edit Modal -->
    <AppDialog
      :open="modalOpen"
      :title="editingAccount ? 'Edit Account' : 'Add Account'"
      @close="closeModal"
    >
      <FormField label="Name" required v-slot="{ id }">
        <input
          :id="id"
          v-model="form.name"
          class="form-input"
          placeholder="e.g. USAA Checking"
        />
      </FormField>

      <div class="field-row">
        <FormField label="Type" required v-slot="{ id }">
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

      <div class="field-row">
        <FormField
          label="Starting Balance ($)"
          hint="Balance when you started tracking"
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

        <FormField
          label="Current Balance ($)"
          hint="Today's actual balance"
          v-slot="{ id }"
        >
          <input
            :id="id"
            v-model="form.current_balance"
            type="number"
            step="0.01"
            class="form-input font-mono"
            placeholder="0.00"
          />
        </FormField>
      </div>

      <div class="status-toggle-wrapper">
        <label class="checkbox-label">
          <input type="checkbox" v-model="form.is_active" class="form-checkbox" />
          <span>Active</span>
        </label>
      </div>

      <ErrorBanner v-if="modalError" :error="modalError" :dismissible="false" />

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeModal">Cancel</button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!form.name || saving"
          @click="saveAccount"
        >
          {{ saving ? 'Saving…' : (editingAccount ? 'Save Changes' : 'Add Account') }}
        </button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ACCOUNT_TYPES, useAccountTypes } from '~/composables/useAccountTypes'

const { getSubtypes, getSubtypeLabel, defaultSubtype } = useAccountTypes()

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
}

// --- State ---
const accounts = ref<Account[]>([])
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
  current_balance: 0,
  is_active: true,
})
const form = ref(emptyForm())

// --- Fetch ---
const fetchAccounts = async () => {
  pending.value = true
  error.value = null
  try {
    accounts.value = await $fetch<Account[]>(`${API_BASE}/accounts/`)
  } catch (e: any) {
    error.value = e.message || 'Failed to load accounts'
  } finally {
    pending.value = false
  }
}

onMounted(fetchAccounts)

// --- Grouping ---
const accountTypeGroups = computed(() =>
  ACCOUNT_TYPES.filter(t => accounts.value.some(a => a.type === t.value))
)

const getAccountsByType = (type: string) =>
  accounts.value.filter(a => a.type === type)

// --- Modal ---
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
    starting_balance: Number(account.starting_balance),
    current_balance: Number(account.current_balance),
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

// --- Save ---
const saveAccount = async () => {
  if (!form.value.name) return
  saving.value = true
  modalError.value = ''
  try {
    const body = {
      name: form.value.name,
      type: form.value.type,
      subtype: form.value.subtype || null,
      starting_balance: Number(form.value.starting_balance) || 0,
      current_balance: Number(form.value.current_balance) || 0,
      is_active: form.value.is_active,
    }
    if (editingAccount.value) {
      await $fetch(`${API_BASE}/accounts/${editingAccount.value.account_id}`, {
        method: 'PUT',
        body,
      })
    } else {
      await $fetch(`${API_BASE}/accounts/`, {
        method: 'POST',
        body: { ...body, currency: 'USD' },
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

// --- Delete ---
const confirmDelete = async (account: Account) => {
  if (!confirm(`Delete "${account.name}"? This cannot be undone.`)) return
  try {
    await $fetch(`${API_BASE}/accounts/${account.account_id}`, { method: 'DELETE' })
    await fetchAccounts()
  } catch (e: any) {
    error.value = e.data?.detail ?? e.message ?? 'Failed to delete account'
  }
}

// --- Helpers ---
const formatCurrency = (val: number | string) => {
  const n = parseFloat(String(val)) || 0
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
}
</script>

<style scoped>
.accounts-page {
  padding: 24px;
  max-width: 1000px;
  margin: 0 auto;
}

/* Type groups */
.type-group { margin-bottom: 36px; }

.type-group-label {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin: 0 0 10px;
}

/* Table */
.accounts-table {
  background: white;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.table-header {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr 90px 80px;
  padding: 10px 20px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border-color);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.table-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr 90px 80px;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid #f1f5f9;
  font-size: 0.9rem;
  transition: background 0.15s;
}
.table-row:last-child { border-bottom: none; }
.table-row:hover { background: #fafafa; }
.table-row.inactive { opacity: 0.55; }

.account-name { font-weight: 600; }
.account-subtype { color: var(--text-muted); text-transform: capitalize; }

.right { text-align: right; }

.status-badge {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 99px;
  text-transform: uppercase;
}
.status-badge.active { background: #dcfce7; color: #15803d; }
.status-badge.inactive { background: #f1f5f9; color: #94a3b8; }

.row-actions { display: flex; gap: 4px; justify-content: flex-end; }

/* Modal form layout */
.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

.status-toggle-wrapper {
  margin-top: var(--space-xs);
  margin-bottom: var(--space-md);
}
</style>
