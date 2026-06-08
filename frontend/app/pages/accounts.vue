<template>
  <div class="accounts-page">
    <header class="page-header">
      <h1 class="page-title">Accounts</h1>
      <button class="primary-btn" @click="openAddModal">+ Add Account</button>
    </header>

    <!-- Error Banner -->
    <div v-if="error" class="error-banner">
      {{ error }}
      <button class="close-btn" @click="error = null">✕</button>
    </div>

    <!-- Loading -->
    <div v-if="pending" class="loading-state">
      <div class="spinner"></div>
      <p>Loading accounts...</p>
    </div>

    <!-- Empty -->
    <div v-else-if="!accounts.length" class="empty-state">
      <div class="empty-icon">🏦</div>
      <h2>No accounts yet</h2>
      <p>Add your bank accounts to start tracking.</p>
      <button class="primary-btn" @click="openAddModal">+ Add Account</button>
    </div>

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
            <span class="right mono">{{ formatCurrency(account.starting_balance) }}</span>
            <span class="right mono">{{ formatCurrency(account.current_balance) }}</span>
            <span>
              <span :class="['status-badge', account.is_active ? 'active' : 'inactive']">
                {{ account.is_active ? 'Active' : 'Inactive' }}
              </span>
            </span>
            <span class="row-actions">
              <button class="icon-btn" @click="openEditModal(account)" title="Edit">✏️</button>
              <button class="icon-btn delete" @click="confirmDelete(account)" title="Delete">🗑️</button>
            </span>
          </div>
        </div>
      </div>
    </template>

    <!-- Add / Edit Modal -->
    <div v-if="modalOpen" class="modal-backdrop" @click.self="closeModal">
      <div class="modal">
        <div class="modal-header">
          <h2 class="modal-title">{{ editingAccount ? 'Edit Account' : 'Add Account' }}</h2>
          <button class="close-btn" @click="closeModal">✕</button>
        </div>

        <div class="modal-body">
          <div class="field">
            <label class="field-label">Name <span class="required">*</span></label>
            <input v-model="form.name" class="input" placeholder="e.g. USAA Checking" />
          </div>

          <div class="field-row">
            <div class="field">
              <label class="field-label">Type <span class="required">*</span></label>
              <select v-model="form.type" class="select" @change="onTypeChange">
                <option v-for="t in ACCOUNT_TYPES" :key="t.value" :value="t.value">
                  {{ t.label }}
                </option>
              </select>
            </div>

            <div class="field">
              <label class="field-label">Subtype</label>
              <select v-model="form.subtype" class="select">
                <option v-for="s in getSubtypes(form.type)" :key="s.value" :value="s.value">
                  {{ s.label }}
                </option>
              </select>
            </div>
          </div>

          <div class="field-row">
            <div class="field">
              <label class="field-label">
                Starting Balance ($)
                <span class="field-hint">Balance when you started tracking</span>
              </label>
              <input v-model="form.starting_balance" type="number" step="0.01" class="input" placeholder="0.00" />
            </div>
            <div class="field">
              <label class="field-label">
                Current Balance ($)
                <span class="field-hint">Today's actual balance</span>
              </label>
              <input v-model="form.current_balance" type="number" step="0.01" class="input" placeholder="0.00" />
            </div>
          </div>

          <div class="field">
            <label class="checkbox-label">
              <input type="checkbox" v-model="form.is_active" />
              <span>Active</span>
            </label>
          </div>

          <div v-if="modalError" class="error-banner">{{ modalError }}</div>
        </div>

        <div class="modal-footer">
          <button class="ghost-btn" @click="closeModal">Cancel</button>
          <button class="primary-btn" :disabled="!form.name || saving" @click="saveAccount">
            {{ saving ? 'Saving…' : (editingAccount ? 'Save Changes' : 'Add Account') }}
          </button>
        </div>
      </div>
    </div>
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

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.page-title {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0;
  color: var(--text-color);
}

.primary-btn {
  background: var(--accent-color);
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
  font-size: 0.9rem;
}
.primary-btn:hover:not(:disabled) { opacity: 0.9; }
.primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.ghost-btn {
  background: white;
  border: 1px solid var(--border-color);
  color: var(--text-muted);
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.ghost-btn:hover { background: var(--nav-hover-bg); }

.error-banner {
  background: #fee2e2;
  color: #dc2626;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9rem;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  font-size: 1rem;
  padding: 0 4px;
}

.loading-state, .empty-state {
  text-align: center;
  padding: 60px;
  color: var(--text-muted);
}
.empty-icon { font-size: 3rem; margin-bottom: 16px; }
.empty-state h2 { margin: 0 0 8px; }
.empty-state p { margin: 0 0 24px; }

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
.mono { font-variant-numeric: tabular-nums; font-weight: 500; }

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

.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 5px 7px;
  border-radius: 6px;
  font-size: 0.9rem;
  transition: background 0.15s;
}
.icon-btn:hover { background: #f1f5f9; }
.icon-btn.delete:hover { background: #fee2e2; }

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 16px;
}

.modal {
  background: white;
  border-radius: 16px;
  width: 100%;
  max-width: 520px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.15);
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
}
.modal-title { margin: 0; font-size: 1.1rem; font-weight: 700; }

.modal-body { padding: 24px; display: flex; flex-direction: column; gap: 4px; }

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
  background: #f8fafc;
}

/* Form fields */
.field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.field-label {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.field-hint { font-weight: 400; text-transform: none; letter-spacing: 0; font-size: 0.78rem; }
.required { color: #ef4444; }

.input, .select {
  padding: 9px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 0.9rem;
  color: var(--text-color);
  background: white;
  width: 100%;
  box-sizing: border-box;
  transition: border-color 0.15s, box-shadow 0.15s;
  outline: none;
}
.input:focus, .select:focus {
  border-color: var(--accent-color);
  box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  cursor: pointer;
  color: var(--text-color);
}
.checkbox-label input { cursor: pointer; width: 16px; height: 16px; }
</style>
