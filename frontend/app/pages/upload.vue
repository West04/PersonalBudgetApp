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
    <!-- Step 1 — File upload & Format Resolution                            -->
    <!-- ------------------------------------------------------------------ -->
    <div v-if="currentStep === 1" class="card step-card">
      <h2 class="card-title">Upload CSV File</h2>
      <p class="card-hint">
        Select your bank's CSV export to automatically inspect and detect its format.
      </p>

      <!-- CSV File Drop Zone -->
      <div class="field">
        <label class="field-label">CSV File <span class="required">*</span></label>
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
            <button class="clear-file" title="Clear file" @click.stop="clearFile">✕</button>
          </div>
        </div>
      </div>

      <!-- Inspect Loading State -->
      <div v-if="inspectLoading" class="inspect-loading">
        <span class="spinner">⏳</span>
        <span>Inspecting CSV structure and matching formats…</span>
      </div>

      <!-- Inspect Error Banner -->
      <div v-if="inspectError" class="error-banner">
        <strong>Inspection Error:</strong> {{ inspectError }}
      </div>

      <!-- Inspection Results -->
      <div v-if="inspectResult && !inspectLoading" class="inspect-result">
        <!-- DETECTED FORMAT -->
        <div v-if="inspectResult.status === 'detected' && inspectResult.detected_format" class="detected-card">
          <div class="detected-icon">✓</div>
          <div class="detected-body">
            <div class="detected-title">
              Format Detected: <strong>{{ resolvedFormatName }}</strong>
            </div>
            <div class="detected-hint">
              This statement matches the <strong>{{ resolvedFormatName }}</strong> specification. Ready to proceed!
            </div>
          </div>
        </div>

        <!-- AMBIGUOUS FORMATS -->
        <div v-else-if="inspectResult.status === 'ambiguous'" class="ambiguous-card">
          <div class="ambiguous-header">
            <h3 class="ambiguous-title">Multiple Matching Formats</h3>
            <p class="ambiguous-hint">
              This statement matches multiple format definitions. Please select the correct format:
            </p>
          </div>
          <div class="format-options">
            <label
              v-for="fmt in inspectResult.matches"
              :key="fmt.identifier"
              class="format-option"
              :class="{ 'format-option--selected': resolvedFormatId === fmt.identifier }"
              @click="selectAmbiguousFormat(fmt)"
            >
              <input
                type="radio"
                name="ambiguousFormat"
                :value="fmt.identifier"
                :checked="resolvedFormatId === fmt.identifier"
                class="sr-only"
              />
              <span class="format-name">{{ fmt.name }}</span>
              <span class="format-desc">Format ID: {{ fmt.identifier }}</span>
            </label>
          </div>
        </div>

        <!-- UNKNOWN FORMAT & MAPPING FORM -->
        <div v-else-if="inspectResult.status === 'unknown'" class="unknown-section">
          <div class="unknown-header">
            <h3 class="unknown-title">Unrecognized CSV Format</h3>
            <p class="unknown-hint">
              We couldn't automatically match this CSV. Inspect the sample columns below and map them to create a reusable custom format.
            </p>
          </div>

          <!-- Duplicate header warning if applicable -->
          <div v-if="duplicateHeaderNames.length > 0" class="warning-banner">
            ⚠️ <strong>Duplicate Headers Detected:</strong> This file contains duplicate column names (<em>{{ duplicateHeaderNames.join(', ') }}</em>). Because format mappings address columns by name, duplicate header names cannot be uniquely mapped.
          </div>

          <!-- Positional Source CSV Sample Table -->
          <div class="sample-section">
            <h4 class="sample-title">Source CSV Sample (First {{ inspectResult.sample_rows.length }} Data Rows)</h4>
            <div class="sample-table-wrapper">
              <table class="sample-table">
                <thead>
                  <tr>
                    <th v-for="(h, idx) in sampleTableHeaders" :key="idx">
                      {{ h }}
                      <span v-if="duplicateHeaderNames.includes(h)" class="dup-tag">duplicate</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, rIdx) in inspectResult.sample_rows" :key="rIdx">
                    <td v-for="cIdx in sampleTableMaxCols" :key="cIdx">
                      <span v-if="row[cIdx - 1] !== undefined && row[cIdx - 1] !== ''">
                        {{ row[cIdx - 1] }}
                      </span>
                      <span v-else class="cell-empty">—</span>
                    </td>
                  </tr>
                  <tr v-if="inspectResult.sample_rows.length === 0">
                    <td :colspan="sampleTableMaxCols" class="cell-empty" style="text-align: center;">
                      No data rows found in CSV.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Custom Format Mapping Form -->
          <div class="mapping-card">
            <h4 class="mapping-title">Map & Save Custom Format</h4>

            <div v-if="formatSavedSuccess" class="success-banner">
              <div class="success-body">
                <span>✓ Custom format <strong>{{ resolvedFormatName }}</strong> saved successfully! Click <strong>Next →</strong> below to choose the destination account.</span>
                <button class="btn btn--small btn--ghost" type="button" @click="editSavedMapping">Edit Mapping</button>
              </div>
            </div>

            <fieldset :disabled="formatSavedSuccess || saveLoading" class="mapping-fieldset">
              <div class="field">
                <label class="field-label">Format Name <span class="required">*</span></label>
                <input
                  v-model="mappingForm.name"
                  class="input"
                  placeholder="e.g. My Credit Union Checking"
                />
                <span class="field-hint">A unique name to identify this bank format for future uploads.</span>
              </div>

              <div class="field-row">
                <div class="field">
                  <label class="field-label">Date Column <span class="required">*</span></label>
                  <select v-model="mappingForm.date_column" class="select">
                    <option value="" disabled>— Select date column —</option>
                    <option v-for="h in uniqueHeaderOptions" :key="h" :value="h">{{ h }}</option>
                  </select>
                </div>

                <div class="field">
                  <label class="field-label">Description Column <span class="required">*</span></label>
                  <select v-model="mappingForm.description_column" class="select">
                    <option value="" disabled>— Select description column —</option>
                    <option v-for="h in uniqueHeaderOptions" :key="h" :value="h">{{ h }}</option>
                  </select>
                </div>

                <div class="field">
                  <label class="field-label">Amount Column <span class="required">*</span></label>
                  <select v-model="mappingForm.amount_column" class="select">
                    <option value="" disabled>— Select amount column —</option>
                    <option v-for="h in uniqueHeaderOptions" :key="h" :value="h">{{ h }}</option>
                  </select>
                </div>
              </div>

              <div class="field-row">
                <div class="field">
                  <label class="field-label">Status Column (Optional)</label>
                  <select v-model="mappingForm.status_column" class="select">
                    <option value="">— None (all transactions treated as posted) —</option>
                    <option v-for="h in uniqueHeaderOptions" :key="h" :value="h">{{ h }}</option>
                  </select>
                  <span class="field-hint">Column distinguishing posted/cleared vs pending items.</span>
                </div>

                <div v-if="mappingForm.status_column" class="field">
                  <label class="field-label">Status Posted Value</label>
                  <input
                    v-model="mappingForm.status_posted_value"
                    class="input"
                    placeholder="posted"
                  />
                  <span class="field-hint">Token value meaning "posted" (case-insensitive; defaults to "posted").</span>
                </div>
              </div>

              <div class="field-row">
                <div class="field">
                  <label class="field-label">Date Format <span class="required">*</span></label>
                  <input
                    v-model="mappingForm.date_format"
                    class="input"
                    placeholder="%Y-%m-%d, %m/%d/%Y, or %d/%m/%Y"
                  />
                  <span class="field-hint">
                    Python strptime format: <code>%Y</code> (2026), <code>%m</code> (01-12), <code>%d</code> (01-31).
                  </span>
                </div>

                <div class="field">
                  <label class="field-label">Amount Sign Convention <span class="required">*</span></label>
                  <select v-model="mappingForm.amount_sign_convention" class="select">
                    <option value="positive_is_outflow">
                      Positive numbers are spending / outflows (charges, purchases)
                    </option>
                    <option value="positive_is_inflow">
                      Positive numbers are income / inflows (credits, deposits)
                    </option>
                  </select>
                  <span class="field-hint">How your bank denotes purchases vs deposits.</span>
                </div>
              </div>

              <div v-if="mappingValidationError && !formatSavedSuccess" class="form-hint-banner">
                ℹ {{ mappingValidationError }}
              </div>

              <div v-if="saveError" class="error-banner">
                <strong>Error Saving Format:</strong> {{ saveError }}
              </div>

              <div v-if="!formatSavedSuccess" class="form-actions">
                <button
                  type="button"
                  class="btn btn--primary"
                  :disabled="Boolean(mappingValidationError) || saveLoading"
                  @click="saveCustomFormat"
                >
                  {{ saveLoading ? 'Saving Format…' : 'Save Format' }}
                </button>
              </div>
            </fieldset>
          </div>
        </div>
      </div>

      <!-- Step 1 Navigation -->
      <div class="step-actions">
        <button
          class="btn btn--primary"
          :disabled="!selectedFile || !resolvedFormatId || inspectLoading || saveLoading"
          @click="currentStep = 2"
        >
          Next →
        </button>
      </div>
    </div>

    <!-- ------------------------------------------------------------------ -->
    <!-- Step 2 — Account selection                                          -->
    <!-- ------------------------------------------------------------------ -->
    <div v-if="currentStep === 2" class="card step-card">
      <div class="file-summary-bar">
        <span class="summary-item">📄 <strong>{{ selectedFile?.name }}</strong></span>
        <span class="summary-badge badge badge--neutral">Format: {{ resolvedFormatName }}</span>
      </div>

      <h2 class="card-title">Select Destination Account</h2>
      <p class="card-hint">Choose which account these transactions belong to, or create a new one.</p>

      <div v-if="accountsLoading" class="loading-state">Loading accounts…</div>

      <div v-else>
        <div class="field">
          <label class="field-label">Account <span class="required">*</span></label>
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
                <option v-for="t in ACCOUNT_TYPES" :key="t.value" :value="t.value">
                  {{ t.label }}
                </option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">Subtype</label>
              <select v-model="newAccount.subtype" class="select">
                <option v-for="s in getSubtypes(newAccount.type)" :key="s.value" :value="s.value">
                  {{ s.label }}
                </option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">Starting Balance ($)</label>
              <input v-model="newAccount.starting_balance" class="input" type="number" step="0.01" placeholder="0.00" />
            </div>
            <div class="field">
              <label class="field-label">Current Balance ($)</label>
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

      <div v-if="parseError" class="error-banner">{{ parseError }}</div>

      <div class="step-actions">
        <button class="btn btn--ghost" @click="currentStep = 1">← Back</button>
        <button
          class="btn btn--primary"
          :disabled="!selectedAccountId || selectedAccountId === '__new__' || previewing"
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
        <span class="preview-account">
          → <strong>{{ selectedAccountName }}</strong>
          <span class="preview-format">({{ resolvedFormatName }})</span>
        </span>
      </div>

      <div class="table-wrapper">
        <table class="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Date</th>
              <th>Description</th>
              <th class="amount-col">Amount</th>
              <th>Status</th>
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
          :to="{
            path: '/transactions',
            query: targetMonth
              ? { account_id: selectedAccountId, month: targetMonth }
              : { account_id: selectedAccountId },
          }"
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
import { ref, computed, onMounted, watch } from 'vue'
import { ACCOUNT_TYPES, useAccountTypes } from '~/composables/useAccountTypes'

const { getSubtypes, defaultSubtype } = useAccountTypes()

const API_BASE = '/api'

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

// Slice G contracts
interface CSVFormatMatchRead {
  identifier: string
  name: string
}

interface CSVInspectResponse {
  headers: string[]
  sample_rows: string[][]
  status: 'unknown' | 'detected' | 'ambiguous'
  detected_format: CSVFormatMatchRead | null
  matches: CSVFormatMatchRead[]
}

type AmountSignConvention = 'positive_is_outflow' | 'positive_is_inflow'

interface CSVFormatCreate {
  name: string
  date_column: string
  description_column: string
  amount_column: string
  status_column?: string | null
  date_format: string
  amount_sign_convention: AmountSignConvention
  status_posted_value?: string | null
}

interface CSVFormatRead {
  id: string
  name: string
  date_column: string
  description_column: string
  amount_column: string
  status_column?: string | null
  date_format: string
  amount_sign_convention: AmountSignConvention
  status_posted_value?: string | null
  created_at: string
}

interface MappingFormState {
  name: string
  date_column: string
  description_column: string
  amount_column: string
  status_column: string
  date_format: string
  amount_sign_convention: AmountSignConvention
  status_posted_value: string
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const currentStep = ref(1)
const stepLabels = ['Upload', 'Account', 'Preview', 'Done']

// Step 2 — Account
const accounts = ref<Account[]>([])
const accountsLoading = ref(true)
const selectedAccountId = ref('')
const newAccount = ref({
  name: '',
  type: 'depository',
  subtype: 'checking',
  current_balance: 0,
  starting_balance: 0,
})

watch(() => newAccount.value.type, (type) => {
  newAccount.value.subtype = defaultSubtype(type)
})
const creatingAccount = ref(false)
const createAccountError = ref('')

// Step 1 — File upload & Inspect
const selectedFile = ref<File | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)

const inspectLoading = ref(false)
const inspectResult = ref<CSVInspectResponse | null>(null)
const inspectError = ref<string | null>(null)

// The single authoritative format identifier driving Preview & Confirm
const resolvedFormatId = ref<string | null>(null)
const resolvedFormatName = ref<string | null>(null)

// Ambiguous state selection
const ambiguousSelectedId = ref<string | null>(null)

// Unknown format mapping form state
const mappingForm = ref<MappingFormState>({
  name: '',
  date_column: '',
  description_column: '',
  amount_column: '',
  status_column: '',
  date_format: '',
  amount_sign_convention: 'positive_is_outflow',
  status_posted_value: 'posted',
})
const saveLoading = ref(false)
const saveError = ref<string | null>(null)
const formatSavedSuccess = ref(false)

// Step 2/3 — Preview
const previewing = ref(false)
const parseError = ref('')
const preview = ref<CSVPreviewResponse>({ rows: [], total_rows: 0, valid_rows: 0, error_rows: 0 })

// Step 3/4 — Import
const importing = ref(false)
const importResult = ref<CSVImportResult>({ imported: 0, skipped: 0, errors: [] })

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

const selectedAccountName = computed(() => {
  const acct = accounts.value.find(a => a.account_id === selectedAccountId.value)
  return acct?.name ?? ''
})

const targetMonth = computed(() => {
  const dates = preview.value?.rows
    ?.filter(row => !row.parse_error && row.transaction_date)
    .map(row => row.transaction_date as string)
    ?? []

  if (!dates.length) return ''

  const latestDate = dates.reduce((latest, current) => (current > latest ? current : latest), dates[0])
  return latestDate.slice(0, 7)
})

// Duplicate header detection in Inspect headers
const duplicateHeaderNames = computed<string[]>(() => {
  if (!inspectResult.value?.headers) return []
  const counts: Record<string, number> = {}
  for (const h of inspectResult.value.headers) {
    counts[h] = (counts[h] || 0) + 1
  }
  return Object.keys(counts).filter(h => counts[h] > 1)
})

// Unique header options for mapping selects
const uniqueHeaderOptions = computed<string[]>(() => {
  if (!inspectResult.value?.headers) return []
  return Array.from(new Set(inspectResult.value.headers))
})

// Defensive sample table dimensions for ragged row handling
const sampleTableMaxCols = computed(() => {
  if (!inspectResult.value) return 0
  const headerLen = inspectResult.value.headers.length
  const rowMax = inspectResult.value.sample_rows.reduce(
    (max, row) => Math.max(max, row.length),
    0
  )
  return Math.max(headerLen, rowMax)
})

const sampleTableHeaders = computed(() => {
  if (!inspectResult.value) return []
  const headers = [...inspectResult.value.headers]
  const maxCols = sampleTableMaxCols.value
  for (let i = headers.length; i < maxCols; i++) {
    headers.push(`(col ${i + 1})`)
  }
  return headers
})

// Client-side mapping validation
const mappingValidationError = computed(() => {
  if (!inspectResult.value || inspectResult.value.status !== 'unknown') return null

  const name = mappingForm.value.name.trim()
  if (!name) {
    return 'Format name is required.'
  }

  const { date_column, description_column, amount_column, status_column } = mappingForm.value
  if (!date_column) {
    return 'Please select the Date column.'
  }
  if (!description_column) {
    return 'Please select the Description column.'
  }
  if (!amount_column) {
    return 'Please select the Amount column.'
  }

  const primaryCols = [date_column, description_column, amount_column]
  if (new Set(primaryCols).size !== primaryCols.length) {
    return 'Date, Description, and Amount must be mapped to distinct columns.'
  }

  if (status_column && primaryCols.includes(status_column)) {
    return 'Status column must be distinct from Date, Description, and Amount columns.'
  }

  const dupes = duplicateHeaderNames.value
  if (
    dupes.includes(date_column) ||
    dupes.includes(description_column) ||
    dupes.includes(amount_column) ||
    (status_column && dupes.includes(status_column))
  ) {
    return 'Mapped columns cannot use duplicate header names from the CSV.'
  }

  if (!mappingForm.value.date_format.trim()) {
    return 'Date format is required (e.g. %Y-%m-%d or %m/%d/%Y).'
  }

  if (!mappingForm.value.amount_sign_convention) {
    return 'Please select an amount sign convention.'
  }

  return null
})

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(async () => {
  await fetchAccounts()
})

// ---------------------------------------------------------------------------
// Step 2 — Accounts
// ---------------------------------------------------------------------------

async function fetchAccounts() {
  accountsLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/accounts/`)
    accounts.value = await res.json()
  } finally {
    accountsLoading.value = false
  }
}

async function createAccount() {
  creatingAccount.value = true
  createAccountError.value = ''
  try {
    const res = await fetch(`${API_BASE}/accounts/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newAccount.value.name,
        type: newAccount.value.type,
        subtype: newAccount.value.subtype || null,
        starting_balance: Number(newAccount.value.starting_balance) || 0,
        current_balance: Number(newAccount.value.current_balance) || 0,
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
    newAccount.value = { name: '', type: 'depository', subtype: 'checking', current_balance: 0, starting_balance: 0 }
  } catch (e: any) {
    createAccountError.value = e.message
  } finally {
    creatingAccount.value = false
  }
}

// Step 1 — File Upload & Inspect
let inspectRequestGeneration = 0
let saveRequestGeneration = 0
let previewRequestGeneration = 0

function resetMappingFormState() {
  mappingForm.value = {
    name: '',
    date_column: '',
    description_column: '',
    amount_column: '',
    status_column: '',
    date_format: '',
    amount_sign_convention: 'positive_is_outflow',
    status_posted_value: 'posted',
  }
  saveLoading.value = false
  saveError.value = null
  formatSavedSuccess.value = false
}

function clearFile() {
  inspectRequestGeneration++
  saveRequestGeneration++
  previewRequestGeneration++
  selectedFile.value = null
  inspectLoading.value = false
  inspectResult.value = null
  inspectError.value = null
  resolvedFormatId.value = null
  resolvedFormatName.value = null
  ambiguousSelectedId.value = null
  resetMappingFormState()
  parseError.value = ''
  preview.value = { rows: [], total_rows: 0, valid_rows: 0, error_rows: 0 }
  if (fileInputRef.value) fileInputRef.value.value = ''
}

async function handleFileSelected(file: File) {
  // Invalidate any in-flight Save or Preview requests from previous file
  saveRequestGeneration++
  previewRequestGeneration++

  // Clear any previous file-derived state while preserving selectedAccountId
  selectedFile.value = file
  inspectResult.value = null
  inspectError.value = null
  resolvedFormatId.value = null
  resolvedFormatName.value = null
  ambiguousSelectedId.value = null
  resetMappingFormState()
  parseError.value = ''
  preview.value = { rows: [], total_rows: 0, valid_rows: 0, error_rows: 0 }

  await runInspect(file)
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.[0]) {
    handleFileSelected(input.files[0])
  }
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  const file = e.dataTransfer?.files[0]
  if (file) {
    if (!file.name.endsWith('.csv')) {
      inspectError.value = 'Please drop a .csv file'
      return
    }
    handleFileSelected(file)
  }
}

async function runInspect(file: File) {
  const generation = ++inspectRequestGeneration
  inspectLoading.value = true
  inspectError.value = null

  const form = new FormData()
  form.append('file', file)

  try {
    const res = await fetch(`${API_BASE}/upload/inspect`, {
      method: 'POST',
      body: form,
    })

    // Discard response if request is obsolete or file changed
    if (generation !== inspectRequestGeneration || selectedFile.value !== file) {
      return
    }

    if (!res.ok) {
      let errorMsg = 'Failed to inspect CSV file'
      try {
        const err = await res.json()
        errorMsg = err.detail ?? errorMsg
      } catch {}

      if (generation !== inspectRequestGeneration || selectedFile.value !== file) {
        return
      }

      inspectError.value = errorMsg
      return
    }

    const data: CSVInspectResponse = await res.json()

    if (generation !== inspectRequestGeneration || selectedFile.value !== file) {
      return
    }

    inspectResult.value = data

    if (data.status === 'detected' && data.detected_format) {
      resolvedFormatId.value = data.detected_format.identifier
      resolvedFormatName.value = data.detected_format.name
    } else if (data.status === 'ambiguous') {
      // Ambiguous: require explicit user choice; no automatic selection
      resolvedFormatId.value = null
      resolvedFormatName.value = null
      ambiguousSelectedId.value = null
    } else if (data.status === 'unknown') {
      resolvedFormatId.value = null
      resolvedFormatName.value = null
    }
  } catch (e: any) {
    if (generation !== inspectRequestGeneration || selectedFile.value !== file) {
      return
    }
    inspectError.value = e.message || 'Network error during inspection'
  } finally {
    // Only the active generation for the current file may clear loading state
    if (generation === inspectRequestGeneration && selectedFile.value === file) {
      inspectLoading.value = false
    }
  }
}

function selectAmbiguousFormat(match: CSVFormatMatchRead) {
  ambiguousSelectedId.value = match.identifier
  resolvedFormatId.value = match.identifier
  resolvedFormatName.value = match.name
}

async function saveCustomFormat() {
  if (mappingValidationError.value) return
  const generation = ++saveRequestGeneration
  const targetFile = selectedFile.value
  saveLoading.value = true
  saveError.value = null

  const payload: CSVFormatCreate = {
    name: mappingForm.value.name.trim(),
    date_column: mappingForm.value.date_column,
    description_column: mappingForm.value.description_column,
    amount_column: mappingForm.value.amount_column,
    status_column: mappingForm.value.status_column || null,
    date_format: mappingForm.value.date_format.trim(),
    amount_sign_convention: mappingForm.value.amount_sign_convention,
    status_posted_value: mappingForm.value.status_column
      ? (mappingForm.value.status_posted_value.trim() || null)
      : null,
  }

  try {
    const res = await fetch(`${API_BASE}/upload/formats`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    if (generation !== saveRequestGeneration || selectedFile.value !== targetFile) {
      return
    }

    if (!res.ok) {
      let errorMsg = 'Failed to save format'
      try {
        const err = await res.json()
        errorMsg = err.detail ?? errorMsg
      } catch {}

      if (generation !== saveRequestGeneration || selectedFile.value !== targetFile) {
        return
      }

      saveError.value = errorMsg
      return
    }

    const created: CSVFormatRead = await res.json()

    if (generation !== saveRequestGeneration || selectedFile.value !== targetFile) {
      return
    }

    resolvedFormatId.value = created.id
    resolvedFormatName.value = created.name
    formatSavedSuccess.value = true
  } catch (e: any) {
    if (generation !== saveRequestGeneration || selectedFile.value !== targetFile) {
      return
    }
    saveError.value = e.message || 'Network error saving custom format'
  } finally {
    if (generation === saveRequestGeneration && selectedFile.value === targetFile) {
      saveLoading.value = false
    }
  }
}

function editSavedMapping() {
  formatSavedSuccess.value = false
  resolvedFormatId.value = null
  resolvedFormatName.value = null
}

// ---------------------------------------------------------------------------
// Step 2 & 3 — Preview & Confirm Import
// ---------------------------------------------------------------------------

async function runPreview() {
  if (!selectedFile.value || !resolvedFormatId.value || !selectedAccountId.value) return
  const generation = ++previewRequestGeneration
  const targetFile = selectedFile.value
  const targetFormatId = resolvedFormatId.value
  const targetAccountId = selectedAccountId.value
  previewing.value = true
  parseError.value = ''

  const form = new FormData()
  form.append('file', selectedFile.value)
  form.append('account_id', selectedAccountId.value)
  form.append('format', resolvedFormatId.value)

  try {
    const res = await fetch(`${API_BASE}/upload/preview`, {
      method: 'POST',
      body: form,
    })

    if (
      generation !== previewRequestGeneration ||
      selectedFile.value !== targetFile ||
      resolvedFormatId.value !== targetFormatId ||
      selectedAccountId.value !== targetAccountId
    ) {
      return
    }

    if (!res.ok) {
      const err = await res.json()
      if (
        generation !== previewRequestGeneration ||
        selectedFile.value !== targetFile ||
        resolvedFormatId.value !== targetFormatId ||
        selectedAccountId.value !== targetAccountId
      ) {
        return
      }
      parseError.value = err.detail ?? 'Failed to parse file'
      return
    }

    const data: CSVPreviewResponse = await res.json()

    if (
      generation !== previewRequestGeneration ||
      selectedFile.value !== targetFile ||
      resolvedFormatId.value !== targetFormatId ||
      selectedAccountId.value !== targetAccountId
    ) {
      return
    }

    preview.value = data
    currentStep.value = 3
  } catch (e: any) {
    if (
      generation !== previewRequestGeneration ||
      selectedFile.value !== targetFile ||
      resolvedFormatId.value !== targetFormatId ||
      selectedAccountId.value !== targetAccountId
    ) {
      return
    }
    parseError.value = e.message
  } finally {
    if (
      generation === previewRequestGeneration &&
      selectedFile.value === targetFile &&
      resolvedFormatId.value === targetFormatId &&
      selectedAccountId.value === targetAccountId
    ) {
      previewing.value = false
    }
  }
}

async function runImport() {
  if (!selectedFile.value || !resolvedFormatId.value || !selectedAccountId.value) return
  importing.value = true

  const form = new FormData()
  form.append('file', selectedFile.value)
  form.append('account_id', selectedAccountId.value)
  form.append('format', resolvedFormatId.value)

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

function resetWizard() {
  currentStep.value = 1
  selectedAccountId.value = ''
  clearFile()
  importResult.value = { imported: 0, skipped: 0, errors: [] }
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

.field-hint {
  font-size: 0.78rem;
  color: #64748b;
  margin-top: 2px;
}

.field-hint code {
  background: #f1f5f9;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 0.75rem;
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

/* --------------------------- Inspect States ------------------------------- */

.inspect-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  color: #475569;
  font-size: 0.9rem;
  margin-top: 16px;
}

.spinner {
  font-size: 1.1rem;
}

.detected-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px 20px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  margin-top: 20px;
}

.detected-icon {
  font-size: 1.4rem;
  color: #16a34a;
  line-height: 1;
}

.detected-title {
  font-size: 1rem;
  color: #166534;
  margin-bottom: 4px;
}

.detected-hint {
  font-size: 0.85rem;
  color: #15803d;
}

.ambiguous-card {
  margin-top: 20px;
  padding: 20px;
  background: #fffbeb;
  border: 1px solid #fef3c7;
  border-radius: 10px;
}

.ambiguous-title {
  font-size: 1rem;
  font-weight: 600;
  color: #92400e;
  margin: 0 0 4px;
}

.ambiguous-hint {
  font-size: 0.85rem;
  color: #b45309;
  margin: 0 0 16px;
}

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
  background: #fff;
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

/* ---------------------------- Unknown & Mapping --------------------------- */

.unknown-section {
  margin-top: 20px;
}

.unknown-title {
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 4px;
}

.unknown-hint {
  font-size: 0.85rem;
  color: #64748b;
  margin: 0 0 16px;
}

.sample-section {
  margin: 20px 0;
}

.sample-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 0 0 8px;
}

.sample-table-wrapper {
  overflow-x: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.sample-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
  white-space: nowrap;
}

.sample-table th {
  padding: 8px 12px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  font-weight: 600;
  color: #475569;
  text-align: left;
}

.sample-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #f1f5f9;
  color: #1e293b;
}

.sample-table tr:last-child td {
  border-bottom: none;
}

.dup-tag {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 5px;
  border-radius: 4px;
  background: #fee2e2;
  color: #dc2626;
  font-size: 0.7rem;
  font-weight: normal;
}

.cell-empty {
  color: #94a3b8;
  font-style: italic;
}

.mapping-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 20px;
  margin-top: 20px;
}

.mapping-title {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0 0 16px;
  color: #1e293b;
}

.mapping-fieldset {
  border: none;
  padding: 0;
  margin: 0;
}

.warning-banner {
  background: #fffbeb;
  border: 1px solid #fcd34d;
  color: #92400e;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 0.85rem;
  margin-bottom: 16px;
}

.form-hint-banner {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1e40af;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 0.85rem;
  margin: 12px 0;
}

.success-banner {
  background: #f0fdf4;
  border: 1px solid #86efac;
  color: #15803d;
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 0.875rem;
  margin-bottom: 16px;
}

.success-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.form-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-start;
}

.btn--small {
  padding: 4px 10px;
  font-size: 0.8rem;
}

/* ------------------------------ Step 2 ----------------------------------- */

.file-summary-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 16px;
  margin-bottom: 20px;
}

.summary-item {
  font-size: 0.88rem;
  color: #1e293b;
}

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

.preview-format {
  color: #64748b;
  font-weight: normal;
  margin-left: 4px;
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
