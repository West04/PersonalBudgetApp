<template>
  <div class="import-page page-container">
    <PageHeader
      title="Import"
      subtitle="Add transactions from a bank statement CSV"
    />

    <!-- The existing four-step sequence; Back buttons move between steps -->
    <ol class="progress" aria-label="Import steps">
      <li
        v-for="(step, index) in stepLabels"
        :key="step"
        class="progress-step"
        :class="{
          'is-current': currentStep === index + 1,
          'is-done': currentStep > index + 1,
        }"
        :aria-current="currentStep === index + 1 ? 'step' : undefined"
      >
        <span class="progress-marker" aria-hidden="true">
          <AppIcon v-if="currentStep > index + 1" name="check" :size="13" />
          <template v-else>{{ index + 1 }}</template>
        </span>
        <span class="progress-label">{{ step }}</span>
        <span v-if="currentStep > index + 1" class="sr-only">(done)</span>
      </li>
    </ol>

    <!-- ------------------------------------------------------------------ -->
    <!-- Step 1: file selection, inspection and format resolution            -->
    <!-- ------------------------------------------------------------------ -->
    <section v-if="currentStep === 1" class="step" aria-labelledby="step-file-heading">
      <header class="step-header">
        <h2 id="step-file-heading" class="step-title">Choose a statement file</h2>
        <p class="step-hint">
          Select a CSV export from your bank. The file is read to find a saved format that matches its columns.
        </p>
      </header>

      <!-- Drag and drop is an addition to the labelled file input, never a replacement -->
      <div
        class="file-picker"
        :class="{ 'is-dragging': isDragging, 'has-file': selectedFile }"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="onDrop"
      >
        <input
          id="import-file-input"
          ref="fileInputRef"
          type="file"
          accept=".csv"
          class="sr-only file-input"
          aria-describedby="import-file-help"
          @change="onFileChange"
        />
        <label v-if="!selectedFile" for="import-file-input" class="file-drop">
          <AppIcon name="import" :size="18" class="file-drop-icon" />
          <span class="file-drop-text">
            <span class="file-drop-action">Choose a CSV file</span>
            <span class="file-drop-alt">or drag one here</span>
          </span>
        </label>
        <div v-else class="file-selected">
          <AppIcon name="file" :size="18" class="file-selected-icon" />
          <span class="file-selected-name" :title="selectedFile.name">{{ selectedFile.name }}</span>
          <span class="file-selected-actions">
            <label for="import-file-input" class="btn btn-ghost btn-sm file-change">Change file</label>
            <button
              type="button"
              class="btn btn-ghost btn-sm"
              :aria-label="`Remove ${selectedFile.name}`"
              @click="clearFile"
            >
              Remove
            </button>
          </span>
        </div>
      </div>
      <p id="import-file-help" class="field-note">
        <template v-if="selectedFile">Selected file: {{ selectedFile.name }}. </template>CSV files (.csv) only.
      </p>

      <p v-if="inspectLoading" class="status-line" role="status">
        <span class="spinner" aria-hidden="true"></span>
        Inspecting the file and matching saved formats…
      </p>

      <ErrorBanner
        v-if="inspectError"
        :error="`Inspection failed: ${inspectError}`"
        :dismissible="false"
      />

      <div v-if="inspectResult && !inspectLoading" class="inspect-result">
        <!-- Detected: one saved format matches -->
        <div
          v-if="inspectResult.status === 'detected' && inspectResult.detected_format"
          class="status-note is-success"
          role="status"
        >
          <AppIcon name="check-circle" :size="18" class="status-note-icon" />
          <div class="status-note-body">
            <p class="status-note-title">Format recognized: {{ resolvedFormatName }}</p>
            <p class="status-note-text">Rows will be read with the {{ resolvedFormatName }} format.</p>
          </div>
        </div>

        <!-- Ambiguous: the user must choose -->
        <template v-else-if="inspectResult.status === 'ambiguous'">
          <div class="status-note is-warning">
            <AppIcon name="alert" :size="18" class="status-note-icon" />
            <div class="status-note-body">
              <p class="status-note-title">More than one saved format matches</p>
              <p class="status-note-text">Choose the format this file uses before continuing.</p>
            </div>
          </div>

          <fieldset class="format-choice">
            <legend class="subsection-title">Matching formats</legend>
            <label
              v-for="fmt in inspectResult.matches"
              :key="fmt.identifier"
              class="format-option"
              :class="{ 'is-selected': resolvedFormatId === fmt.identifier }"
              @click="selectAmbiguousFormat(fmt)"
            >
              <input
                type="radio"
                name="ambiguousFormat"
                :value="fmt.identifier"
                :checked="resolvedFormatId === fmt.identifier"
                class="format-radio"
              />
              <span class="format-text">
                <span class="format-name">{{ fmt.name }}</span>
                <span class="format-id">Format ID: {{ fmt.identifier }}</span>
              </span>
            </label>
          </fieldset>
        </template>

        <!-- Unknown: sample the columns and map a reusable format -->
        <div v-else-if="inspectResult.status === 'unknown'" class="unknown-section">
          <div class="status-note is-info">
            <div class="status-note-body">
              <p class="status-note-title">No saved format matches this file</p>
              <p class="status-note-text">
                Map its columns below and save them as a format. The format is reused for later imports from the same bank.
              </p>
            </div>
          </div>

          <div v-if="duplicateHeaderNames.length > 0" class="status-note is-warning">
            <AppIcon name="alert" :size="18" class="status-note-icon" />
            <div class="status-note-body">
              <p class="status-note-title">Duplicate column names: {{ duplicateHeaderNames.join(', ') }}</p>
              <p class="status-note-text">
                Formats map columns by name, so columns that share a name can't be mapped.
              </p>
            </div>
          </div>

          <section class="subsection" aria-labelledby="sample-heading">
            <div class="subsection-head">
              <h3 id="sample-heading" class="subsection-title">File sample</h3>
              <p class="subsection-meta">First {{ inspectResult.sample_rows.length }} data rows, as written in the file</p>
            </div>
            <div class="sample-scroll surface-card">
              <table class="sample-table" aria-labelledby="sample-heading">
                <thead>
                  <tr>
                    <th v-for="(h, idx) in sampleTableHeaders" :key="idx" scope="col">
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
                      <span v-else class="cell-empty" aria-label="Empty">—</span>
                    </td>
                  </tr>
                  <tr v-if="inspectResult.sample_rows.length === 0">
                    <td :colspan="sampleTableMaxCols" class="cell-empty sample-empty">
                      No data rows found in CSV.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="subsection mapping" aria-labelledby="mapping-heading">
            <div class="subsection-head">
              <h3 id="mapping-heading" class="subsection-title">Column mapping</h3>
            </div>

            <div v-if="formatSavedSuccess" class="status-note is-success" role="status">
              <AppIcon name="check-circle" :size="18" class="status-note-icon" />
              <div class="status-note-body">
                <p class="status-note-title">Format saved: {{ resolvedFormatName }}</p>
                <p class="status-note-text">Select Continue to choose the destination account.</p>
              </div>
              <button class="btn btn-ghost btn-sm status-note-action" type="button" @click="editSavedMapping">
                Edit mapping
              </button>
            </div>

            <fieldset :disabled="formatSavedSuccess || saveLoading" class="mapping-fieldset">
              <legend class="sr-only">Column mapping</legend>
              <FormField
                label="Format name"
                required
                hint="A unique name for this bank's format, shown on future imports."
                v-slot="{ id }"
              >
                <input
                  :id="id"
                  v-model="mappingForm.name"
                  class="form-input"
                  placeholder="e.g. My Credit Union Checking"
                />
              </FormField>

              <div class="field-grid field-grid--3">
                <FormField label="Date column" required v-slot="{ id }">
                  <select :id="id" v-model="mappingForm.date_column" class="form-select">
                    <option value="" disabled>Select a column</option>
                    <option v-for="h in uniqueHeaderOptions" :key="h" :value="h">{{ h }}</option>
                  </select>
                </FormField>

                <FormField label="Description column" required v-slot="{ id }">
                  <select :id="id" v-model="mappingForm.description_column" class="form-select">
                    <option value="" disabled>Select a column</option>
                    <option v-for="h in uniqueHeaderOptions" :key="h" :value="h">{{ h }}</option>
                  </select>
                </FormField>

                <FormField label="Amount column" required v-slot="{ id }">
                  <select :id="id" v-model="mappingForm.amount_column" class="form-select">
                    <option value="" disabled>Select a column</option>
                    <option v-for="h in uniqueHeaderOptions" :key="h" :value="h">{{ h }}</option>
                  </select>
                </FormField>
              </div>

              <div class="field-grid">
                <FormField
                  label="Status column (optional)"
                  hint="Column that separates posted or cleared items from pending ones."
                  v-slot="{ id }"
                >
                  <select :id="id" v-model="mappingForm.status_column" class="form-select">
                    <option value="">None (all transactions treated as posted)</option>
                    <option v-for="h in uniqueHeaderOptions" :key="h" :value="h">{{ h }}</option>
                  </select>
                </FormField>

                <FormField
                  v-if="mappingForm.status_column"
                  label="Posted status value"
                  hint='Value that means "posted" (case-insensitive; defaults to "posted").'
                  v-slot="{ id }"
                >
                  <input
                    :id="id"
                    v-model="mappingForm.status_posted_value"
                    class="form-input"
                    placeholder="posted"
                  />
                </FormField>
              </div>

              <div class="field-grid field-grid--sign">
                <FormField label="Date format" required v-slot="{ id }">
                  <input
                    :id="id"
                    v-model="mappingForm.date_format"
                    class="form-input"
                    placeholder="%Y-%m-%d, %m/%d/%Y, or %d/%m/%Y"
                    aria-describedby="date-format-help"
                  />
                  <p id="date-format-help" class="field-note field-note--tight">
                    Python strptime codes: <code>%Y</code> 2026, <code>%m</code> 01–12, <code>%d</code> 01–31.
                  </p>
                </FormField>

                <FormField
                  label="Amount sign convention"
                  required
                  hint="How your bank writes purchases versus deposits."
                  v-slot="{ id }"
                >
                  <select :id="id" v-model="mappingForm.amount_sign_convention" class="form-select">
                    <option value="positive_is_outflow">
                      Positive numbers are spending / outflows (charges, purchases)
                    </option>
                    <option value="positive_is_inflow">
                      Positive numbers are income / inflows (credits, deposits)
                    </option>
                  </select>
                </FormField>
              </div>

              <ErrorBanner
                v-if="saveError"
                :error="`Format not saved: ${saveError}`"
                :dismissible="false"
              />

              <div v-if="!formatSavedSuccess" class="mapping-actions">
                <button
                  type="button"
                  class="btn btn-secondary"
                  :disabled="Boolean(mappingValidationError) || saveLoading"
                  @click="saveCustomFormat"
                >
                  {{ saveLoading ? 'Saving format…' : 'Save format' }}
                </button>
                <p v-if="mappingValidationError" class="mapping-requirement">
                  {{ mappingValidationError }}
                </p>
              </div>
            </fieldset>
          </section>
        </div>
      </div>

      <div class="step-actions">
        <p class="step-status" aria-live="polite">{{ fileStepStatus }}</p>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!selectedFile || !resolvedFormatId || inspectLoading || saveLoading"
          @click="currentStep = 2"
        >
          Continue
        </button>
      </div>
    </section>

    <!-- ------------------------------------------------------------------ -->
    <!-- Step 2: destination account                                         -->
    <!-- ------------------------------------------------------------------ -->
    <section v-if="currentStep === 2" class="step" aria-labelledby="step-account-heading">
      <header class="step-header">
        <h2 id="step-account-heading" class="step-title">Choose the account</h2>
        <p class="step-hint">Transactions in this file are added to the account you choose.</p>
      </header>

      <dl class="import-facts">
        <div class="fact fact--file">
          <dt>File</dt>
          <dd :title="selectedFile?.name">{{ selectedFile?.name }}</dd>
        </div>
        <div class="fact">
          <dt>Format</dt>
          <dd>{{ resolvedFormatName }}</dd>
        </div>
      </dl>

      <p v-if="accountsLoading" class="status-line" role="status">
        <span class="spinner" aria-hidden="true"></span>
        Loading accounts…
      </p>

      <div v-else class="account-step">
        <FormField label="Account" required v-slot="{ id }">
          <select :id="id" v-model="selectedAccountId" class="form-select">
            <option value="" disabled>Select an account</option>
            <option v-for="acct in accounts" :key="acct.account_id" :value="acct.account_id">
              {{ acct.name }} ({{ acct.type }}{{ acct.subtype ? `/${acct.subtype}` : '' }})
            </option>
            <option value="__new__">Create new account…</option>
          </select>
        </FormField>

        <section
          v-if="selectedAccountId === '__new__'"
          class="new-account"
          aria-labelledby="new-account-heading"
        >
          <h3 id="new-account-heading" class="subsection-title">New account</h3>
          <div class="field-grid field-grid--3">
            <FormField label="Name" required v-slot="{ id }">
              <input :id="id" v-model="newAccount.name" class="form-input" placeholder="e.g. USAA Checking" />
            </FormField>
            <FormField label="Type" required v-slot="{ id }">
              <select :id="id" v-model="newAccount.type" class="form-select">
                <option v-for="t in ACCOUNT_TYPES" :key="t.value" :value="t.value">
                  {{ t.label }}
                </option>
              </select>
            </FormField>
            <FormField label="Subtype" v-slot="{ id }">
              <select :id="id" v-model="newAccount.subtype" class="form-select">
                <option v-for="s in getSubtypes(newAccount.type)" :key="s.value" :value="s.value">
                  {{ s.label }}
                </option>
              </select>
            </FormField>
            <FormField label="Starting balance ($)" v-slot="{ id }">
              <input :id="id" v-model="newAccount.starting_balance" class="form-input num" type="number" step="0.01" placeholder="0.00" />
            </FormField>
            <FormField label="Current balance ($)" v-slot="{ id }">
              <input :id="id" v-model="newAccount.current_balance" class="form-input num" type="number" step="0.01" placeholder="0.00" />
            </FormField>
          </div>

          <ErrorBanner
            v-if="createAccountError"
            :error="`Account not created: ${createAccountError}`"
            :dismissible="false"
          />

          <button
            type="button"
            class="btn btn-secondary"
            :disabled="!newAccount.name || creatingAccount"
            @click="createAccount"
          >
            {{ creatingAccount ? 'Creating account…' : 'Create account' }}
          </button>
        </section>
      </div>

      <ErrorBanner
        v-if="parseError"
        :error="`Preview failed: ${parseError}`"
        :dismissible="false"
      />

      <div class="step-actions">
        <button type="button" class="btn btn-ghost" @click="currentStep = 1">Back</button>
        <p class="step-status" aria-live="polite">{{ accountStepStatus }}</p>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!selectedAccountId || selectedAccountId === '__new__' || previewing"
          @click="runPreview"
        >
          {{ previewing ? 'Reading rows…' : 'Preview transactions' }}
        </button>
      </div>
    </section>

    <!-- ------------------------------------------------------------------ -->
    <!-- Step 3: preview (nothing is saved until Import)                     -->
    <!-- ------------------------------------------------------------------ -->
    <section v-if="currentStep === 3" class="step" aria-labelledby="step-preview-heading">
      <header class="step-header">
        <h2 id="step-preview-heading" class="step-title">Review before importing</h2>
        <p class="step-hint">Nothing has been saved yet. Check the rows below, then import them.</p>
      </header>

      <dl class="import-facts">
        <div class="fact">
          <dt>Account</dt>
          <dd>{{ selectedAccountName }}</dd>
        </div>
        <div class="fact">
          <dt>Format</dt>
          <dd>{{ resolvedFormatName }}</dd>
        </div>
        <div class="fact">
          <dt>Ready to import</dt>
          <dd class="num">{{ preview.valid_rows }}</dd>
        </div>
        <div class="fact" :class="{ 'fact--error': preview.error_rows > 0 }">
          <dt>Rows with errors</dt>
          <dd class="num">{{ preview.error_rows }}</dd>
        </div>
      </dl>

      <div v-if="preview.error_rows > 0" class="status-note is-warning">
        <AppIcon name="alert" :size="18" class="status-note-icon" />
        <div class="status-note-body">
          <p class="status-note-title">
            {{ preview.error_rows }} {{ preview.error_rows === 1 ? 'row' : 'rows' }} can't be read and won't be imported
          </p>
          <p class="status-note-text">They're marked "Can't read" in the table below with the reason.</p>
        </div>
      </div>

      <div class="preview-ledger surface-card">
        <table class="preview-table" role="table" aria-label="Rows in this file">
          <thead role="rowgroup">
            <tr role="row">
              <th scope="col" class="col-row" role="columnheader">Row</th>
              <th scope="col" class="col-date" role="columnheader">Date</th>
              <th scope="col" class="col-desc" role="columnheader">Description</th>
              <th scope="col" class="col-amount" role="columnheader">Amount</th>
              <th scope="col" class="col-status" role="columnheader">Status</th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            <tr
              v-for="row in preview.rows"
              :key="row.row_number"
              class="preview-row"
              :class="{ 'row--error': row.parse_error }"
              role="row"
            >
              <td class="row-cell num" role="cell">{{ row.row_number }}</td>
              <template v-if="row.parse_error">
                <td colspan="4" class="error-cell" role="cell">
                  <span class="error-label">
                    <AppIcon name="alert" :size="14" />
                    Can't read
                  </span>
                  <span class="error-reason">{{ row.parse_error }}</span>
                </td>
              </template>
              <template v-else>
                <td class="date-cell num" role="cell">{{ formatPreviewDate(row.transaction_date) }}</td>
                <td class="desc-cell" role="cell">
                  <span class="desc-text" :title="row.description">{{ row.description }}</span>
                </td>
                <td class="amount-cell" role="cell">
                  <!-- Same convention as Transactions: inflows (negative) display with an explicit + -->
                  <span class="money" :class="Number(row.amount) < 0 ? 'money--inflow' : 'money--outflow'">{{ formatPreviewAmount(row.amount) }}</span>
                </td>
                <td class="status-cell" role="cell">
                  <span v-if="row.pending" class="row-status is-pending">
                    <AppIcon name="clock" :size="14" />
                    Pending
                  </span>
                  <span v-else class="row-status">Posted</span>
                </td>
              </template>
            </tr>
            <tr v-if="preview.rows.length === 0" role="row" class="empty-tr">
              <td colspan="5" class="empty-cell" role="cell">This file has no transaction rows.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="step-actions">
        <button type="button" class="btn btn-ghost" @click="currentStep = 2">Back</button>
        <p class="step-status" aria-live="polite">{{ previewStepStatus }}</p>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="preview.valid_rows === 0 || importing"
          @click="runImport"
        >
          {{ importing ? 'Importing…' : `Import ${preview.valid_rows} Transaction${preview.valid_rows !== 1 ? 's' : ''}` }}
        </button>
      </div>
    </section>

    <!-- ------------------------------------------------------------------ -->
    <!-- Step 4: result                                                      -->
    <!-- ------------------------------------------------------------------ -->
    <section v-if="currentStep === 4" class="step" aria-labelledby="step-done-heading">
      <header class="step-header result-header">
        <AppIcon name="check-circle" :size="22" class="result-icon" />
        <div>
          <h2 id="step-done-heading" class="step-title">Import complete</h2>
          <p class="step-hint">{{ selectedAccountName }}, from {{ selectedFile?.name }}</p>
        </div>
      </header>

      <dl class="import-facts result-facts">
        <div class="fact">
          <dt>Imported</dt>
          <dd class="num">{{ importResult.imported }}</dd>
        </div>
        <div class="fact">
          <dt>Skipped as duplicates</dt>
          <dd class="num">{{ importResult.skipped }}</dd>
        </div>
        <div v-if="importResult.errors.length > 0" class="fact fact--error">
          <dt>Row errors</dt>
          <dd class="num">{{ importResult.errors.length }}</dd>
        </div>
      </dl>

      <p class="field-note">
        Duplicates are rows already in this account with the same date, amount and description.
      </p>

      <section
        v-if="importResult.errors.length > 0"
        class="subsection result-errors"
        aria-labelledby="result-errors-heading"
      >
        <h3 id="result-errors-heading" class="subsection-title">Rows not imported</h3>
        <ul class="error-list">
          <li v-for="(err, i) in importResult.errors" :key="i">{{ err }}</li>
        </ul>
      </section>

      <div class="step-actions step-actions--result">
        <NuxtLink
          :to="{
            path: '/transactions',
            query: targetMonth
              ? { account_id: selectedAccountId, month: targetMonth }
              : { account_id: selectedAccountId },
          }"
          class="btn btn-primary"
        >
          View transactions
        </NuxtLink>
        <button type="button" class="btn btn-ghost" @click="resetWizard">Import another file</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ACCOUNT_TYPES, useAccountTypes } from '~/composables/useAccountTypes'
import { formatMoney } from '~/utils/money'
import { formatDateOnly } from '~/utils/formatDate'

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
const stepLabels = ['File', 'Account', 'Preview', 'Done']

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

// Display-only status lines: say whether the user can continue, and what
// happens next. They read existing state and never change it.
const fileStepStatus = computed(() => {
  if (!selectedFile.value) return 'Choose a file to continue.'
  if (inspectLoading.value) return 'Inspecting the file…'
  if (saveLoading.value) return 'Saving the format…'
  if (inspectError.value && !resolvedFormatId.value) return 'This file could not be inspected. Choose the file again or pick another one.'
  if (!inspectResult.value) return ''
  if (resolvedFormatId.value) return `Ready to continue with the ${resolvedFormatName.value} format.`
  if (inspectResult.value.status === 'ambiguous') return 'Choose a format to continue.'
  if (inspectResult.value.status === 'unknown') return 'Save the column mapping to continue.'
  return ''
})

const accountStepStatus = computed(() => {
  if (accountsLoading.value) return ''
  if (!selectedAccountId.value) return 'Choose an account to continue.'
  if (selectedAccountId.value === '__new__') return 'Create the account to continue.'
  return ''
})

const previewStepStatus = computed(() => {
  const count = preview.value.valid_rows
  if (count === 0) return 'There are no readable rows to import.'
  return `Imports up to ${count} ${count === 1 ? 'transaction' : 'transactions'} into ${selectedAccountName.value}. Rows already in this account are skipped.`
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

function formatPreviewDate(date: string | undefined): string {
  return formatDateOnly(date, { includeYear: true })
}

// Displays the value the server returned without changing it: outflows
// (positive) unsigned, inflows (negative) with an explicit +, as on Transactions.
// The API serializes Decimal amounts as strings, hence Number().
function formatPreviewAmount(amount: number | string | undefined): string {
  if (amount == null) return '—'
  const text = formatMoney(amount, 'never')
  return Number(amount) < 0 ? `+${text}` : text
}
</script>


<style scoped>
/* Import ---------------------------------------------------------------------
   One working column. Controls and notes keep a 720px reading measure; the
   preview and file-sample tables use the full container width. */

/* Progress: the existing four steps, named in text --------------------------- */

.progress {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-lg);
  margin: 0 0 var(--space-lg);
  padding: 0 0 var(--space-md);
  list-style: none;
  border-bottom: 1px solid var(--border-subtle);
}

.progress-step {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.progress-marker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-full);
  font-family: var(--font-numeric);
  font-variant-numeric: var(--font-numeric-features);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--text-muted);
  background: var(--bg-surface);
}

.progress-step.is-current {
  color: var(--text-primary);
  font-weight: var(--font-weight-semibold);
}

.progress-step.is-current .progress-marker {
  border-color: var(--accent-primary);
  background: var(--accent-primary);
  color: var(--text-on-accent);
}

.progress-step.is-done {
  color: var(--text-secondary);
}

.progress-step.is-done .progress-marker {
  border-color: var(--accent-primary);
  color: var(--accent-text);
}

/* Step layout ---------------------------------------------------------------- */

.step {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  min-width: 0;
}

.step > :deep(.error-banner) {
  max-width: 720px;
  margin-bottom: 0;
}

.step-header {
  max-width: 720px;
}

.step-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--type-heading-size);
  font-weight: var(--type-heading-weight);
  line-height: var(--line-height-tight);
  color: var(--text-primary);
}

.step-hint {
  margin: var(--space-xs) 0 0;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  overflow-wrap: anywhere;
}

.subsection {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  min-width: 0;
}

.subsection-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2xs) var(--space-md);
}

.subsection-title {
  margin: 0;
  padding: 0;
  font-size: var(--type-subheading-size);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.subsection-meta {
  margin: 0;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.field-note {
  margin: calc(var(--space-sm) * -1) 0 0;
  max-width: 720px;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  overflow-wrap: anywhere;
}

.field-note--tight {
  margin: var(--space-xs) 0 0;
  font-size: var(--font-size-xs);
}

.field-note code {
  padding: 0 4px;
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border-radius: var(--radius-xs);
}

.status-line {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin: 0;
  font-size: var(--type-meta-size);
  color: var(--text-secondary);
}

.spinner {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-primary);
  border-radius: var(--radius-full);
  animation: import-spin 0.8s linear infinite;
}

@keyframes import-spin {
  to { transform: rotate(360deg); }
}

/* File picker ---------------------------------------------------------------- */

.file-picker {
  position: relative;
  max-width: 720px;
}

.file-drop {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  min-height: 64px;
  padding: var(--space-md);
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.file-drop:hover,
.is-dragging .file-drop,
.is-dragging .file-selected {
  border-color: var(--accent-primary);
  background: var(--accent-subtle);
}

.file-drop-icon {
  color: var(--accent-text);
}

.file-drop-text {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-xs);
  font-size: var(--type-body-size);
  color: var(--text-secondary);
}

.file-drop-action {
  font-weight: var(--font-weight-semibold);
  color: var(--accent-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.file-selected {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-sm) var(--space-md);
  padding: var(--space-sm) var(--space-sm) var(--space-sm) var(--space-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
}

.file-selected-icon {
  color: var(--text-secondary);
}

.file-selected-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.file-selected-actions {
  display: flex;
  gap: var(--space-xs);
}

/* The real input stays focusable; its focus ring is drawn on the visible control */
.file-input:focus-visible + .file-drop,
.file-input:focus-visible + .file-selected .file-change {
  outline: var(--focus-ring-width) solid var(--focus-ring);
  outline-offset: var(--focus-ring-offset);
}

/* Status notes: success, warning and info are named in text ------------------ */

.status-note {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  max-width: 720px;
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border-default);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
}

.status-note-icon {
  margin-top: 1px;
}

.status-note-body {
  flex: 1;
  min-width: 0;
}

.status-note-title {
  margin: 0;
  font-size: var(--type-body-size);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.status-note-text {
  margin: 2px 0 0;
  font-size: var(--type-meta-size);
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}

.status-note-action {
  flex-shrink: 0;
  align-self: center;
}

.status-note.is-success {
  border-color: var(--status-success-border);
  border-left-color: var(--status-success);
  background: var(--status-success-bg);
}

.status-note.is-success .status-note-icon {
  color: var(--status-success);
}

.status-note.is-warning {
  border-color: var(--status-warning-border);
  border-left-color: var(--status-warning);
  background: var(--status-warning-bg);
}

.status-note.is-warning .status-note-icon {
  color: var(--status-warning);
}

.status-note.is-info {
  border-color: var(--status-info-border);
  border-left-color: var(--status-info);
  background: var(--status-info-bg);
}

/* Inspection results --------------------------------------------------------- */

.inspect-result,
.unknown-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  min-width: 0;
}

.unknown-section {
  gap: var(--space-lg);
}

.unknown-section > .status-note + .status-note {
  margin-top: calc(var(--space-sm) - var(--space-lg));
}

.format-choice {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  max-width: 720px;
  margin: 0;
  padding: 0;
  border: 0;
}

.format-choice legend {
  margin-bottom: var(--space-xs);
}

.format-option {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  cursor: pointer;
}

.format-option:hover {
  border-color: var(--border-strong);
}

.format-option.is-selected {
  border-color: var(--accent-primary);
  background: var(--accent-subtle);
}

.format-radio {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--accent-primary);
}

.format-text {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 var(--space-md);
  min-width: 0;
}

.format-name {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.format-id {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  overflow-wrap: anywhere;
}

/* Raw file sample: columns are unknown, so this one table scrolls inside itself */
.sample-scroll {
  overflow-x: auto;
}

.sample-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
  white-space: nowrap;
}

.sample-table th {
  height: 34px;
  padding: 0 12px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  text-align: left;
  color: var(--table-header-text);
  background: var(--table-header);
  border-bottom: 1px solid var(--border-default);
}

.sample-table td {
  padding: 6px 12px;
  color: var(--text-primary);
  border-bottom: 1px solid var(--table-border);
}

.sample-table tbody tr:last-child td {
  border-bottom: 0;
}

.dup-tag {
  margin-left: var(--space-xs);
  padding: 0 6px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--status-warning);
  background: var(--status-warning-bg);
  border: 1px solid var(--status-warning-border);
  border-radius: var(--radius-xs);
}

.cell-empty {
  color: var(--text-muted);
}

.sample-empty {
  text-align: center;
}

/* Mapping form */
.mapping {
  max-width: 720px;
}

.mapping-fieldset {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: var(--space-md);
}

.field-grid--3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.field-grid--sign {
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
}

.mapping-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm) var(--space-md);
}

.mapping-requirement {
  margin: 0;
  font-size: var(--type-meta-size);
  color: var(--text-secondary);
}

/* Import facts (file, format, account, counts) -------------------------------- */

.import-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm) var(--space-xl);
  margin: 0;
  padding: var(--space-sm) 0;
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

.fact {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.fact dt {
  font-size: var(--type-label-size);
  color: var(--text-muted);
}

.fact dd {
  margin: 0;
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.fact--file {
  max-width: 100%;
}

.fact--file dd {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  overflow-wrap: normal;
}

.fact--error dd {
  color: var(--status-error);
}

.account-step,
.new-account {
  max-width: 720px;
}

.new-account {
  margin-top: var(--space-xs);
  padding: var(--space-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
}

.new-account .subsection-title {
  margin-bottom: var(--space-md);
}

.new-account :deep(.error-banner) {
  margin-bottom: var(--space-md);
}

/* Preview ledger --------------------------------------------------------------
   Container tiers: full (>= 720px), compact (560-719px), stacked (< 560px).
   The amount track is identical in full and compact, so every figure up to
   +$1,234,567.89 shares one right edge. */

.preview-ledger {
  container: preview / inline-size;
  overflow: hidden;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: var(--font-size-sm);
  text-align: left;
}

.preview-table th {
  height: 34px;
  padding: 0 12px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--table-header-text);
  background: var(--table-header);
  border-bottom: 1px solid var(--border-default);
  white-space: nowrap;
}

.col-row { width: 64px; }
.col-date { width: 120px; }
.col-amount { width: 136px; text-align: right; }
.col-status { width: 104px; }

.preview-table td {
  padding: 6px 12px;
  vertical-align: middle;
  border-bottom: 1px solid var(--table-border);
}

.preview-row:last-child td {
  border-bottom: 0;
}

.preview-row:hover td {
  background: var(--table-hover);
}

.row-cell {
  color: var(--text-muted);
  font-size: var(--font-size-xs);
}

.date-cell {
  color: var(--text-secondary);
  white-space: nowrap;
}

.desc-cell {
  min-width: 0;
}

.desc-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.amount-cell {
  text-align: right;
  white-space: nowrap;
  font-weight: var(--font-weight-medium);
}

.row-status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.row-status.is-pending {
  color: var(--text-secondary);
}

.error-cell {
  color: var(--text-primary);
}

.error-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  margin-right: var(--space-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--status-error);
  white-space: nowrap;
}

.error-reason {
  overflow-wrap: anywhere;
}

.empty-cell {
  padding: var(--space-lg) 12px !important;
  text-align: center;
  color: var(--text-muted);
}

@container preview (width < 720px) {
  .col-row { width: 48px; }
  .col-date { width: 104px; }
  .col-status { width: 88px; }

  .preview-table th,
  .preview-table td {
    padding-inline: 8px;
  }
}

/* Stacked: each row becomes a two-line record. Explicit ARIA roles in the
   markup keep table semantics when display changes. */
@container preview (width < 560px) {
  .preview-table,
  .preview-table tbody {
    display: block;
  }

  .preview-table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .preview-row {
    display: grid;
    grid-template-columns: auto auto minmax(0, 1fr) auto;
    grid-template-areas:
      "desc desc desc amount"
      "row date . status";
    align-items: center;
    gap: 2px var(--space-sm);
    padding: 8px var(--space-md);
    border-bottom: 1px solid var(--table-border);
  }

  .preview-row:last-child {
    border-bottom: 0;
  }

  .preview-table .preview-row td {
    padding: 0;
    border: 0;
    background: none;
  }

  .row-cell { grid-area: row; }
  .row-cell::before { content: "Row "; }
  .date-cell { grid-area: date; font-size: var(--font-size-xs); }
  .desc-cell { grid-area: desc; }
  .amount-cell { grid-area: amount; font-size: var(--type-body-size); }
  .status-cell { grid-area: status; text-align: right; }

  .preview-row.row--error {
    grid-template-columns: auto minmax(0, 1fr);
    grid-template-areas: "row error";
    align-items: baseline;
  }

  .error-cell { grid-area: error; }

  .error-label {
    display: flex;
    margin: 0 0 2px;
  }

  .empty-tr {
    display: block;
  }

  .empty-tr .empty-cell {
    display: block;
  }
}

/* Result ---------------------------------------------------------------------- */

.result-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
}

.result-icon {
  margin-top: 1px;
  color: var(--status-success);
}

.result-facts dd {
  font-size: var(--type-heading-size);
}

.result-errors {
  max-width: 720px;
}

.error-list {
  margin: 0;
  padding: var(--space-sm) var(--space-md) var(--space-sm) calc(var(--space-md) + 18px);
  font-size: var(--type-meta-size);
  color: var(--text-primary);
  border: 1px solid var(--status-error-border);
  border-left: 3px solid var(--status-error);
  border-radius: var(--radius-sm);
  background: var(--status-error-bg);
  overflow-wrap: anywhere;
}

.error-list li + li {
  margin-top: var(--space-xs);
}

/* Step actions: Back on the left, the one primary action on the right, and a
   line that says what the primary action does or why it is unavailable. */

.step-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm) var(--space-md);
  margin-top: var(--space-sm);
  padding-top: var(--space-md);
  border-top: 1px solid var(--border-subtle);
}

.step-status {
  flex: 1 1 240px;
  min-width: 0;
  margin: 0;
  font-size: var(--type-meta-size);
  color: var(--text-secondary);
  text-align: right;
  overflow-wrap: anywhere;
}

.step-actions--result {
  justify-content: flex-start;
}

/* Narrow pages --------------------------------------------------------------- */

@media (width < 640px) {
  .field-grid,
  .field-grid--3,
  .field-grid--sign {
    grid-template-columns: minmax(0, 1fr);
  }

  .progress {
    gap: var(--space-xs) var(--space-md);
  }

  /* Only the current step keeps its word; the others keep marker + accessible name */
  .progress-step:not(.is-current) .progress-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .step-status {
    order: -1;
    flex-basis: 100%;
    text-align: left;
  }

  .step-actions .btn-primary {
    flex: 1 1 auto;
  }

  .file-selected {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .file-selected-actions {
    grid-column: 1 / -1;
  }

  .status-note {
    flex-wrap: wrap;
  }

  .status-note-action {
    margin-left: calc(18px + var(--space-sm));
  }
}
</style>
