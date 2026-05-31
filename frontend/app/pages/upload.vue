<template>
  <div class="page">
    <div class="page-header">
      <h1 class="page-title">Upload Transactions</h1>
      <p class="page-subtitle">Import transactions from a bank CSV export</p>
    </div>

    <!-- Step indicator -->
    <div class="steps">
      <div
        v-for="(step, index) in stepLabels"
        :key="index"
        class="step"
        :class="{
          'step--active': currentStep === index + 1,
          'step--done': currentStep > index + 1,
        }"
      >
        <div class="step-bubble">
          <span v-if="currentStep > index + 1">✓</span>
          <span v-else>{{ index + 1 }}</span>
        </div>
        <span class="step-label">{{ step }}</span>
        <div v-if="index < stepLabels.length - 1" class="step-connector" />
      </div>
    </div>

    <!-- ------------------------------------------------------------------ -->
    <!-- Step 1 — Account selection                                          -->
    <!-- ------------------------------------------------------------------ -->
    <div v-if="currentStep === 1" class="card step-card">
      <h2 class="card-title">Select Account</h2>
      <p class="card-hint">Choose which account these transactions belong to, or create a new one.</p>

      <div v-if="accountsLoading" class="loading-state">Loading accounts…</div>

      <div v-else>
        <div class="field">
          <label class="field-label">Account</label>
          <select v-model="selectedAccountId" class="select">
            <option value="" disabled>— Select an account —</option>
            <option v-for="acct in accounts" :key="acct.account_id" :value="acct.account_id">
              {{ acct.name }} ({{ acct.type }}<span v-if="acct.subtype">/{{ acct.subtype }}</span>)
            </option>
            <option value="__new__">＋ Create new account…</option>
          </select>
        </div>

        <!-- Inline account creation form -->
        <div v-if="selectedAccountId === '__new__'" class="new-account-form">
          <h3 class="sub-title">New Account</h3>
          <div class="field-row">
            <div class="field">
              <label class="field-label">Name <span class="required">*</span></label>
              <input v-model="newAccount.name" class="input" placeholder="e.g. USAA Checking" />
            </div>
            <div class="field">
              <label class="field-label">Type <span class="required">*</span></label>
              <select v-model="newAccount.type" class="select">
                <option value="depository">Checking / Savings</option>
                <option value="credit">Credit Card</option>
                <option value="investment">Investment</option>
                <option value="loan">Loan</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">Subtype</label>
              <input v-model="newAccount.subtype" class="input" placeholder="e.g. checking" />
            </div>
            <div class="field">
              <label class="field-label">Starting Balance ($)</label>
              <input v-model="newAccount.current_balance" class="input" type="number" step="0.01" placeholder="0.00" />
            </div>
          </div>

          <div v-if="createAccountError" class="error-banner">{{ createAccountError }}</div>

          <button
            class="btn btn--primary"
            :disabled="!newAccount.name || creatingAccount"
            @click="createAccount"
          >
            {{ creatingAccount ? 'Creating…' : 'Create Account' }}
          </button>
        </div>
      </div>

      <div class="step-actions">
        <button
          class="btn btn--primary"
          :disabled="!selectedAccountId || selectedAccountId === '__new__'"
          @click="currentStep = 2"
        >
          Next →
        </button>
      </div>
    </div>

    <!-- ------------------------------------------------------------------ -->
    <!-- Step 2 — File upload & format                                       -->
    <!-- ------------------------------------------------------------------ -->
    <div v-if="currentStep === 2" class="card step-card">
      <h2 class="card-title">Upload CSV File</h2>
      <p class="card-hint">
        Select your bank's CSV export and choose the matching format.
      </p>

      <div class="field">
        <label class="field-label">Bank Format</label>
        <div class="format-options">
          <label
            v-for="fmt in formats"
            :key="fmt.value"
            class="format-option"
            :class="{ 'format-option--selected': selectedFormat === fmt.value }"
          >
            <input type="radio" v-model="selectedFormat" :value="fmt.value" class="sr-only" />
            <span class="format-name">{{ fmt.label }}</span>
            <span class="format-desc">{{ fmt.description }}</span>
          </label>
        </div>
      </div>

      <div class="field">
        <label class="field-label">CSV File</label>
        <div
          class="drop-zone"
          :class="{ 'drop-zone--active': isDragging, 'drop-zone--filled': selectedFile }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="onDrop"
          @click="fileInputRef?.click()"
        >
          <input
            ref="fileInputRef"
            type="file"
            accept=".csv"
            class="sr-only"
            @change="onFileChange"
          />
          <div v-if="!selectedFile" class="drop-prompt">
            <span class="drop-icon">📂</span>
            <span>Drag & drop a CSV file here, or <strong>click to browse</strong></span>
          </div>
          <div v-else class="drop-filled">
            <span class="drop-icon">📄</span>
            <span class="file-name">{{ selectedFile.name }}</span>
            <button class="clear-file" @click.stop="clearFile">✕</button>
          </div>
        </div>
      </div>

      <div v-if="parseError" class="error-banner">{{ parseError }}</div>

      <div class="step-actions">
        <button class="btn btn--ghost" @click="currentStep = 1">← Back</button>
        <button
          class="btn btn--primary"
          :disabled="!selectedFile || !selectedFormat || previewing"
          @click="runPreview"
        >
          {{ previewing ? 'Parsing…' : 'Preview →' }}
        </button>
      </div>
    </div>

    <!-- ------------------------------------------------------------------ -->
    <!-- Step 3 — Preview                                                    -->
    <!-- ------------------------------------------------------------------ -->
    <div v-if="currentStep === 3" class="card step-card">
      <h2 class="card-title">Preview Transactions</h2>

      <div class="preview-summary">
        <span class="badge badge--success">{{ preview.valid_rows }} valid</span>
        <span v-if="preview.error_rows > 0" class="badge badge--error">{{ preview.error_rows }} errors</span>
        <span class="preview-account">→ <strong>{{ selectedAccountName }}</strong></span>
      </div>

      <div class="table-wrapper">
        <table class="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Date</th>
              <th>Description</th>
              <th class="amount-col">Amount</th>
              <th>Pending</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in preview.rows"
              :key="row.row_number"
              :class="{ 'row--error': row.parse_error }"
            >
              <td class="row-num">{{ row.row_number }}</td>
              <template v-if="row.parse_error">
                <td colspan="4" class="error-cell">⚠️ {{ row.parse_error }}</td>
              </template>
              <template v-else>
                <td>{{ row.transaction_date }}</td>
                <td class="desc-cell">{{ row.description }}</td>
                <td class="amount-col" :class="row.amount >= 0 ? 'amount--out' : 'amount--in'">
                  {{ formatAmount(row.amount) }}
                </td>
                <td>
                  <span v-if="row.pending" class="badge badge--warning">Pending</span>
                  <span v-else class="badge badge--neutral">Posted</span>
                </td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="step-actions">
        <button class="btn btn--ghost" @click="currentStep = 2">← Back</button>
        <button
          class="btn btn--primary"
          :disabled="preview.valid_rows === 0 || importing"
          @click="runImport"
        >
          {{ importing ? 'Importing…' : `Import ${preview.valid_rows} Transaction${preview.valid_rows !== 1 ? 's' : ''}` }}
        </button>
      </div>
    </div>

    <!-- ------------------------------------------------------------------ -->
    <!-- Step 4 — Results                                                    -->
    <!-- ------------------------------------------------------------------ -->
    <div v-if="currentStep === 4" class="card step-card step-card--result">
      <div class="result-icon">✅</div>
      <h2 class="card-title">Import Complete</h2>

      <div class="result-stats">
        <div class="stat">
          <span class="stat-value">{{ importResult.imported }}</span>
          <span class="stat-label">Imported</span>
        </div>
        <div class="stat stat--muted">
          <span class="stat-value">{{ importResult.skipped }}</span>
          <span class="stat-label">Skipped (duplicates)</span>
        </div>
        <div v-if="importResult.errors.length > 0" class="stat stat--error">
          <span class="stat-value">{{ importResult.errors.length }}</span>
          <span class="stat-label">Errors</span>
        </div>
      </div>

      <div v-if="importResult.errors.length > 0" class="error-list">
        <p class="error-list-title">Row errors:</p>
        <ul>
          <li v-for="(err, i) in importResult.errors" :key="i">{{ err }}</li>
        </ul>
      </div>

      <div class="result-actions">
        <NuxtLink
          :to="`/transactions?account_id=${selectedAccountId}`"
          class="btn btn--primary"
        >
          View Transactions →
        </NuxtLink>
        <button class="btn btn--ghost" @click="resetWizard">Upload Another File</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const API_BASE = 'http://localhost:12344'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Account {
  account_id: string
  name: string
  type: string
  subtype?: string
  current_balance: number
}

interface CSVTransactionRow {
  row_number: number
  transaction_date?: string
  description?: string
  amount?: number
  pending?: boolean
  parse_error?: string
}

interface CSVPreviewResponse {
  rows: CSVTransactionRow[]
  total_rows: number
  valid_rows: number
  error_rows: number
}

interface CSVImportResult {
  imported: number
  skipped: number
  errors: string[]
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const currentStep = ref(1)
const stepLabels = ['Account', 'Upload', 'Preview', 'Done']

// Step 1
const accounts = ref<Account[]>([])
const accountsLoading = ref(true)
const selectedAccountId = ref('')
const newAccount = ref({ name: '', type: 'depository', subtype: '', current_balance: 0 })
const creatingAccount = ref(false)
const createAccountError = ref('')

// Step 2
const formats = [
  {
    value: 'usaa',
    label: 'USAA',
    description: 'Columns: Date, Description, Category, Amount, Status',
  },
  {
    value: 'discover',
    label: 'Discover',
    description: 'Columns: Trans. Date, Description, Amount, Category',
  },
]
const selectedFormat = ref('usaa')
const selectedFile = ref<File | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const parseError = ref('')
const previewing = ref(false)

// Step 3
const preview = ref<CSVPreviewResponse>({ rows: [], total_rows: 0, valid_rows: 0, error_rows: 0 })
const importing = ref(false)

// Step 4
const importResult = ref<CSVImportResult>({ imported: 0, skipped: 0, errors: [] })

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

const selectedAccountName = computed(() => {
  const acct = accounts.value.find(a => a.account_id === selectedAccountId.value)
  return acct?.name ?? ''
})

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(async () => {
  await fetchAccounts()
})

// ---------------------------------------------------------------------------
// Step 1 — Account
// ---------------------------------------------------------------------------

async function fetchAccounts() {
  accountsLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/accounts`)
    accounts.value = await res.json()
  } finally {
    accountsLoading.value = false
  }
}

async function createAccount() {
  creatingAccount.value = true
  createAccountError.value = ''
  try {
    const res = await fetch(`${API_BASE}/accounts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newAccount.value.name,
        type: newAccount.value.type,
        subtype: newAccount.value.subtype || null,
        current_balance: Number(newAccount.value.current_balance),
        currency: 'USD',
        is_active: true,
      }),
    })
    if (!res.ok) {
      const err = await res.json()
      createAccountError.value = err.detail ?? 'Failed to create account'
      return
    }
    const created: Account = await res.json()
    accounts.value = [...accounts.value, created]
    selectedAccountId.value = created.account_id
    newAccount.value = { name: '', type: 'depository', subtype: '', current_balance: 0 }
  } catch (e: any) {
    createAccountError.value = e.message
  } finally {
    creatingAccount.value = false
  }
}

// ---------------------------------------------------------------------------
// Step 2 — File upload
// ---------------------------------------------------------------------------

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.[0]) {
    selectedFile.value = input.files[0]
    parseError.value = ''
  }
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  const file = e.dataTransfer?.files[0]
  if (file) {
    if (!file.name.endsWith('.csv')) {
      parseError.value = 'Please drop a .csv file'
      return
    }
    selectedFile.value = file
    parseError.value = ''
  }
}

function clearFile() {
  selectedFile.value = null
  if (fileInputRef.value) fileInputRef.value.value = ''
  parseError.value = ''
}

async function runPreview() {
  if (!selectedFile.value) return
  previewing.value = true
  parseError.value = ''

  const form = new FormData()
  form.append('file', selectedFile.value)
  form.append('account_id', selectedAccountId.value)
  form.append('format', selectedFormat.value)

  try {
    const res = await fetch(`${API_BASE}/upload/preview`, {
      method: 'POST',
      body: form,
    })
    if (!res.ok) {
      const err = await res.json()
      parseError.value = err.detail ?? 'Failed to parse file'
      return
    }
    preview.value = await res.json()
    currentStep.value = 3
  } catch (e: any) {
    parseError.value = e.message
  } finally {
    previewing.value = false
  }
}

// ---------------------------------------------------------------------------
// Step 3 — Confirm import
// ---------------------------------------------------------------------------

async function runImport() {
  if (!selectedFile.value) return
  importing.value = true

  const form = new FormData()
  form.append('file', selectedFile.value)
  form.append('account_id', selectedAccountId.value)
  form.append('format', selectedFormat.value)

  try {
    const res = await fetch(`${API_BASE}/upload/confirm`, {
      method: 'POST',
      body: form,
    })
    if (!res.ok) {
      const err = await res.json()
      alert(`Import failed: ${err.detail ?? 'Unknown error'}`)
      return
    }
    importResult.value = await res.json()
    currentStep.value = 4
  } catch (e: any) {
    alert(`Import failed: ${e.message}`)
  } finally {
    importing.value = false
  }
}

// ---------------------------------------------------------------------------
// Reset
// ---------------------------------------------------------------------------

function resetWizard() {
  currentStep.value = 1
  selectedAccountId.value = ''
  selectedFile.value = null
  parseError.value = ''
  preview.value = { rows: [], total_rows: 0, valid_rows: 0, error_rows: 0 }
  importResult.value = { imported: 0, skipped: 0, errors: [] }
  if (fileInputRef.value) fileInputRef.value.value = ''
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatAmount(amount: number | undefined): string {
  if (amount == null) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(Math.abs(amount))
}
</script>

<style scoped>
.page {
  padding: 32px;
  max-width: 860px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 32px;
}

.page-title {
  font-size: 1.75rem;
  font-weight: 700;
  margin: 0 0 4px;
}

.page-subtitle {
  color: var(--text-muted);
  margin: 0;
}

/* ----------------------------- Step indicator ----------------------------- */

.steps {
  display: flex;
  align-items: center;
  margin-bottom: 32px;
  gap: 0;
}

.step {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
}

.step-bubble {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  font-weight: 600;
  flex-shrink: 0;
  background: #e2e8f0;
  color: #64748b;
  transition: all 0.2s;
}

.step--active .step-bubble {
  background: #2563eb;
  color: #fff;
}

.step--done .step-bubble {
  background: #16a34a;
  color: #fff;
}

.step-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: #64748b;
  white-space: nowrap;
}

.step--active .step-label {
  color: #2563eb;
}

.step--done .step-label {
  color: #16a34a;
}

.step-connector {
  flex: 1;
  height: 2px;
  background: #e2e8f0;
  margin: 0 8px;
}

/* ------------------------------- Cards ------------------------------------ */

.card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 28px 32px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.card-title {
  font-size: 1.2rem;
  font-weight: 600;
  margin: 0 0 6px;
}

.card-hint {
  color: #64748b;
  font-size: 0.9rem;
  margin: 0 0 24px;
}

.sub-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 20px 0 14px;
  padding-top: 20px;
  border-top: 1px solid #f1f5f9;
}

/* ----------------------------- Form fields -------------------------------- */

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.field-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: #374151;
}

.required {
  color: #ef4444;
}

.field-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
}

.input,
.select {
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 0.9rem;
  background: #fff;
  color: #1e293b;
  transition: border-color 0.15s, box-shadow 0.15s;
  outline: none;
  width: 100%;
}

.input:focus,
.select:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

/* ----------------------------- Format picker ------------------------------ */

.format-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.format-option {
  border: 2px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: all 0.15s;
}

.format-option:hover {
  border-color: #93c5fd;
  background: #f8faff;
}

.format-option--selected {
  border-color: #2563eb;
  background: #eff6ff;
}

.format-name {
  font-weight: 600;
  font-size: 0.95rem;
  color: #1e293b;
}

.format-desc {
  font-size: 0.78rem;
  color: #64748b;
}

/* ------------------------------- Drop zone -------------------------------- */

.drop-zone {
  border: 2px dashed #cbd5e1;
  border-radius: 10px;
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #f8fafc;
}

.drop-zone:hover,
.drop-zone--active {
  border-color: #2563eb;
  background: #eff6ff;
}

.drop-zone--filled {
  border-style: solid;
  border-color: #16a34a;
  background: #f0fdf4;
}

.drop-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #64748b;
  font-size: 0.9rem;
}

.drop-filled {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #15803d;
  font-size: 0.9rem;
}

.drop-icon {
  font-size: 1.8rem;
}

.file-name {
  font-weight: 500;
}

.clear-file {
  background: none;
  border: none;
  cursor: pointer;
  color: #64748b;
  font-size: 1rem;
  padding: 2px 6px;
  border-radius: 4px;
}

.clear-file:hover {
  background: #fee2e2;
  color: #dc2626;
}

/* ------------------------------ New account ------------------------------- */

.new-account-form {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 16px;
}

/* ------------------------------- Preview ---------------------------------- */

.preview-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.preview-account {
  font-size: 0.9rem;
  color: #64748b;
}

.table-wrapper {
  overflow-x: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  margin-bottom: 24px;
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.table th {
  text-align: left;
  padding: 10px 14px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  font-size: 0.8rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.table td {
  padding: 10px 14px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
}

.table tr:last-child td {
  border-bottom: none;
}

.table tbody tr:hover {
  background: #f8fafc;
}

.row--error td {
  background: #fff5f5 !important;
  color: #dc2626;
}

.row-num {
  color: #94a3b8;
  font-size: 0.78rem;
  width: 40px;
}

.desc-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.amount-col {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.amount--out {
  color: #dc2626;
}

.amount--in {
  color: #16a34a;
}

.error-cell {
  font-size: 0.85rem;
  padding: 8px 14px;
}

/* -------------------------------- Result ---------------------------------- */

.step-card--result {
  text-align: center;
  padding: 48px 32px;
}

.result-icon {
  font-size: 3rem;
  margin-bottom: 12px;
}

.result-stats {
  display: flex;
  justify-content: center;
  gap: 40px;
  margin: 28px 0;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: #1e293b;
}

.stat-label {
  font-size: 0.8rem;
  color: #64748b;
}

.stat--muted .stat-value {
  color: #94a3b8;
}

.stat--error .stat-value {
  color: #dc2626;
}

.error-list {
  text-align: left;
  background: #fff5f5;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 24px;
}

.error-list-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: #dc2626;
  margin: 0 0 8px;
}

.error-list ul {
  margin: 0;
  padding-left: 20px;
  font-size: 0.82rem;
  color: #7f1d1d;
}

.result-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

/* ----------------------------- Shared buttons ----------------------------- */

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid #f1f5f9;
}

.btn {
  padding: 9px 20px;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn--primary {
  background: #2563eb;
  color: #fff;
}

.btn--primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn--primary:disabled {
  background: #93c5fd;
  cursor: not-allowed;
}

.btn--ghost {
  background: transparent;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.btn--ghost:hover {
  background: #f1f5f9;
  color: #1e293b;
}

/* -------------------------------- Badges ---------------------------------- */

.badge {
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge--success {
  background: #dcfce7;
  color: #15803d;
}

.badge--error {
  background: #fee2e2;
  color: #dc2626;
}

.badge--warning {
  background: #fef9c3;
  color: #a16207;
}

.badge--neutral {
  background: #f1f5f9;
  color: #475569;
}

/* ----------------------------- Utilities ---------------------------------- */

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

.loading-state {
  color: #64748b;
  font-size: 0.9rem;
  padding: 12px 0;
}

.error-banner {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #dc2626;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 0.875rem;
  margin-bottom: 12px;
}
</style>
