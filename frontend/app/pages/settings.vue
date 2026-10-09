<template>
  <div class="settings-page page-container page-container--narrow">
    <PageHeader
      title="Settings"
      subtitle="Transaction categorization rules, the suggestion model and appearance"
    />

    <ErrorBanner
      v-if="pageError"
      :error="pageError"
      @dismiss="pageError = null"
    />

    <!-- Inline confirmation: icon and text, not color alone -->
    <div
      v-if="successMessage"
      class="success-banner"
      role="status"
      aria-live="polite"
    >
      <AppIcon name="check-circle" :size="18" class="success-icon" />
      <span class="success-text">{{ successMessage }}</span>
      <button
        type="button"
        class="btn-icon success-dismiss"
        @click="successMessage = null"
        aria-label="Dismiss success message"
      >
        <AppIcon name="close" :size="16" />
      </button>
    </div>

    <!-- Categorization rules -->
    <section class="settings-section" aria-labelledby="heading-rules">
      <div class="section-head">
        <div class="section-titles">
          <h2 id="heading-rules" class="section-heading">Categorization rules</h2>
          <p class="section-meta">
            Rules automatically assign categories to new transactions from normalized merchant identity.
            Existing manual categories are always preserved.
          </p>
        </div>
        <div class="section-actions">
          <span v-if="rules && rules.length > 0" class="rules-count num">
            {{ rules.length }} {{ rules.length === 1 ? 'rule' : 'rules' }}
          </span>
          <button
            type="button"
            class="btn btn-primary"
            @click="openAddModal"
            aria-label="Create new categorization rule"
          >
            <AppIcon name="plus" :size="16" />
            Add rule
          </button>
        </div>
      </div>

      <LoadingState v-if="pending" message="Loading categorization rules..." />

      <!-- A failed load shows only the error, never "No categorization rules yet" -->
      <ErrorBanner
        v-else-if="fetchError && !rules"
        error="Couldn't load categorization rules. Reload the page to try again."
        :dismissible="false"
      />

      <EmptyState
        v-else-if="!rules || rules.length === 0"
        title="No categorization rules yet"
        description="Create deterministic rules to categorize transactions automatically when imported or added."
      >
        <template #actions>
          <button
            type="button"
            class="btn btn-primary"
            @click="openAddModal"
          >
            <AppIcon name="plus" :size="16" />
            Add first rule
          </button>
        </template>
      </EmptyState>

      <!-- Explicit ARIA roles keep table semantics when the narrow tier changes display -->
      <div v-else class="table-container surface-card">
        <table class="rules-table" role="table" aria-label="Categorization rules table">
          <thead>
            <tr role="row">
              <th scope="col" role="columnheader" class="th-merchant">Merchant</th>
              <th scope="col" role="columnheader" class="th-category">Target Category</th>
              <th scope="col" role="columnheader" class="th-actions"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rule in rules" :key="rule.id" role="row" class="rule-row">
              <td role="cell" class="td-merchant">
                <span class="merchant-name">{{ rule.merchant }}</span>
              </td>
              <td role="cell" class="td-category">
                <span class="category-name">{{ rule.category?.name || 'Unknown Category' }}</span>
                <span v-if="getCategoryGroupName(rule.category_id)" class="group-name">
                  {{ getCategoryGroupName(rule.category_id) }}
                </span>
              </td>
              <td role="cell" class="td-actions">
                <div class="action-buttons">
                  <button
                    type="button"
                    class="btn btn-ghost btn-sm btn-apply"
                    @click="openApplyModal(rule)"
                    :aria-label="`Apply rule for ${rule.merchant} to existing uncategorized transactions`"
                    title="Apply to matching uncategorized transactions"
                  >
                    Apply
                  </button>
                  <button
                    type="button"
                    class="btn-icon btn-edit"
                    @click="openEditModal(rule)"
                    :aria-label="`Edit rule for ${rule.merchant}`"
                    title="Edit rule"
                  >
                    <AppIcon name="edit" :size="16" />
                  </button>
                  <button
                    type="button"
                    class="btn-icon btn-icon-danger btn-delete"
                    @click="openDeleteModal(rule)"
                    :aria-label="`Delete rule for ${rule.merchant}`"
                    title="Delete rule"
                  >
                    <AppIcon name="trash" :size="16" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ML categorization -->
    <section class="settings-section" aria-labelledby="heading-ml">
      <div class="section-head">
        <div class="section-titles">
          <h2 id="heading-ml" class="section-heading">ML categorization</h2>
          <p class="section-meta">
            Local supervised model that learns from historical manual categorizations to suggest categories for transactions that remain uncategorized after deterministic rules.
          </p>
        </div>
        <div class="section-actions">
          <button
            type="button"
            class="btn btn-secondary"
            @click="triggerRetrain"
            :disabled="retraining"
            aria-label="Retrain categorization model"
          >
            <span v-if="retraining">Retraining...</span>
            <span v-else>Retrain model</span>
          </button>
        </div>
      </div>

      <!-- A failed status load never shows "0 examples / Never" as if it were real -->
      <ErrorBanner
        v-if="mlStatusError && !mlStatus"
        error="Couldn't load model status. Reload the page to try again."
        :dismissible="false"
      />

      <template v-else>
        <dl class="model-facts">
          <div class="fact">
            <dt class="fact-label">Model status</dt>
            <dd class="fact-value">
              <span class="status-badge" :class="statusBadgeClass">{{ mlStatus?.status || 'Unknown' }}</span>
            </dd>
          </div>
          <div class="fact">
            <dt class="fact-label">Training examples</dt>
            <dd class="fact-value num">{{ mlStatus?.training_example_count ?? 0 }}</dd>
          </div>
          <div class="fact">
            <dt class="fact-label">New labels since training</dt>
            <dd class="fact-value num">{{ mlStatus?.new_labels_since_training ?? 0 }}</dd>
          </div>
          <div class="fact">
            <dt class="fact-label">Last trained</dt>
            <dd class="fact-value num">{{ formatTrainedDate(mlStatus?.trained_at) }}</dd>
          </div>
          <div v-if="mlStatus?.accuracy !== null && mlStatus?.accuracy !== undefined" class="fact">
            <dt class="fact-label">Test accuracy</dt>
            <dd class="fact-value num">{{ Math.round((mlStatus?.accuracy || 0) * 100) }}%</dd>
          </div>
          <div v-if="mlStatus?.macro_f1 !== null && mlStatus?.macro_f1 !== undefined" class="fact">
            <dt class="fact-label">Macro F1</dt>
            <dd class="fact-value num">{{ mlStatus?.macro_f1 }}</dd>
          </div>
        </dl>

        <p v-if="mlStatus?.status_message" class="model-message">
          {{ mlStatus.status_message }}
        </p>
      </template>
    </section>

    <!-- Appearance: a local display preference, applied immediately; no API call -->
    <section class="settings-section" aria-labelledby="heading-appearance">
      <div class="section-head">
        <div class="section-titles">
          <h2 id="heading-appearance" class="section-heading">Appearance</h2>
          <p class="section-meta">
            Changes colors only. Amounts, budget states and warnings keep the same meaning in every theme.
            Saved in this browser.
          </p>
        </div>
      </div>

      <fieldset class="theme-fieldset">
        <legend class="theme-legend">Theme</legend>
        <div class="theme-options">
          <label
            v-for="option in themeOptions"
            :key="option.value"
            class="theme-option"
            :class="{ 'is-selected': themePreference === option.value }"
          >
            <input
              type="radio"
              name="theme"
              class="theme-radio"
              :value="option.value"
              :checked="themePreference === option.value"
              :aria-describedby="`theme-desc-${option.value}`"
              @change="setThemePreference(option.value)"
            />
            <span class="theme-option-text">
              <span class="theme-option-label">{{ option.label }}</span>
              <span :id="`theme-desc-${option.value}`" class="theme-option-desc">{{ option.description }}</span>
            </span>
          </label>
        </div>
      </fieldset>
    </section>

    <!-- Dialog: Add Rule -->
    <AppDialog
      :open="isAddOpen"
      title="Add Categorization Rule"
      @close="closeAddModal"
    >
      <div class="modal-form">
        <FormField label="Merchant Name" required :error="formErrors.merchant" v-slot="{ id }">
          <input
            :id="id"
            v-model="ruleForm.merchant"
            class="form-input"
            placeholder="e.g. Starbucks, Netflix, Trader Joe's"
            autofocus
            @keydown.enter.prevent="submitAddRule"
          />
        </FormField>

        <FormField label="Target Category" required :error="formErrors.category_id" v-slot="{ id }">
          <select
            :id="id"
            v-model="ruleForm.category_id"
            class="form-select"
          >
            <option value="" disabled>Select a category...</option>
            <optgroup
              v-for="group in categoryGroups"
              :key="group.category_group_id"
              :label="group.name"
            >
              <option
                v-for="cat in group.categories"
                :key="cat.category_id"
                :value="cat.category_id"
              >
                {{ cat.name }}
              </option>
            </optgroup>
          </select>
        </FormField>

        <ErrorBanner v-if="modalError" :error="modalError" :dismissible="false" />
      </div>

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeAddModal">Cancel</button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!isFormValid || isSubmitting"
          @click="submitAddRule"
        >
          {{ isSubmitting ? 'Creating…' : 'Create Rule' }}
        </button>
      </template>
    </AppDialog>

    <!-- Dialog: Edit Rule -->
    <AppDialog
      :open="isEditOpen"
      title="Edit Categorization Rule"
      @close="closeEditModal"
    >
      <div class="modal-form">
        <FormField label="Merchant Name" required :error="formErrors.merchant" v-slot="{ id }">
          <input
            :id="id"
            v-model="editForm.merchant"
            class="form-input"
            placeholder="e.g. Starbucks"
            autofocus
            @keydown.enter.prevent="submitEditRule"
          />
        </FormField>

        <FormField label="Target Category" required :error="formErrors.category_id" v-slot="{ id }">
          <select
            :id="id"
            v-model="editForm.category_id"
            class="form-select"
          >
            <option value="" disabled>Select a category...</option>
            <optgroup
              v-for="group in categoryGroups"
              :key="group.category_group_id"
              :label="group.name"
            >
              <option
                v-for="cat in group.categories"
                :key="cat.category_id"
                :value="cat.category_id"
              >
                {{ cat.name }}
              </option>
            </optgroup>
          </select>
        </FormField>

        <ErrorBanner v-if="modalError" :error="modalError" :dismissible="false" />
      </div>

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeEditModal">Cancel</button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!isEditFormValid || isSubmitting"
          @click="submitEditRule"
        >
          {{ isSubmitting ? 'Saving…' : 'Save Changes' }}
        </button>
      </template>
    </AppDialog>

    <!-- Dialog: Delete Rule Confirmation -->
    <AppDialog
      :open="isDeleteOpen"
      title="Delete Categorization Rule"
      @close="closeDeleteModal"
    >
      <div v-if="selectedRule" class="modal-content-delete">
        <p class="delete-warning">
          Are you sure you want to delete the categorization rule for
          <strong>{{ selectedRule.merchant }}</strong>?
        </p>
        <ul class="callout-box callout-list">
          <li>Future transactions will no longer be automatically categorized by this rule.</li>
          <li>Previously categorized transactions will remain unchanged.</li>
        </ul>

        <ErrorBanner v-if="modalError" :error="modalError" :dismissible="false" />
      </div>

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeDeleteModal">Cancel</button>
        <button
          type="button"
          class="btn btn-danger"
          :disabled="isSubmitting"
          @click="submitDeleteRule"
        >
          {{ isSubmitting ? 'Deleting…' : 'Delete Rule' }}
        </button>
      </template>
    </AppDialog>

    <!-- Dialog: Apply to Existing Uncategorized -->
    <AppDialog
      :open="isApplyOpen"
      title="Apply Rule to Uncategorized Transactions"
      @close="closeApplyModal"
    >
      <div v-if="selectedRule" class="modal-content-apply">
        <LoadingState v-if="isLoadingPreview" message="Checking for matching transactions..." />

        <div v-else>
          <div v-if="previewCount > 0" class="preview-match-box">
            <div class="match-count-number">{{ previewCount }}</div>
            <div class="match-count-label">
              uncategorized {{ previewCount === 1 ? 'transaction matches' : 'transactions match' }}
              <strong>{{ selectedRule.merchant }}</strong>
            </div>
            <p class="preview-explanation">
              Applying this rule will assign the category
              <strong>{{ selectedRule.category?.name || 'target category' }}</strong>
              to all {{ previewCount }} matching uncategorized transactions.
            </p>
            <div class="callout-box">
              <p class="callout-text">
                Transactions that already have a category will never be modified.
              </p>
            </div>
          </div>

          <div v-else class="preview-zero-box">
            <div class="zero-title">No matching uncategorized transactions</div>
            <p class="zero-desc">
              All transactions matching <strong>{{ selectedRule.merchant }}</strong> already have a category assigned, or no transactions match this merchant yet.
            </p>
          </div>

          <ErrorBanner v-if="modalError" :error="modalError" :dismissible="false" />
        </div>
      </div>

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeApplyModal">
          {{ previewCount === 0 ? 'Close' : 'Cancel' }}
        </button>
        <button
          v-if="previewCount > 0"
          type="button"
          class="btn btn-primary"
          :disabled="isSubmitting || isLoadingPreview"
          @click="submitApplyRule"
        >
          {{ isSubmitting ? 'Applying…' : `Apply to ${previewCount} ${previewCount === 1 ? 'Transaction' : 'Transactions'}` }}
        </button>
      </template>
    </AppDialog>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, reactive } from 'vue'

const { preference: themePreference, setPreference: setThemePreference, options: themeOptions } = useTheme()

const config = useRuntimeConfig()
const API_BASE = config.public.apiBase || '/api'

// Metadata
const { data: categoryGroups } = await useFetch<any[]>(`${API_BASE}/category-groups`)

// Rules Fetching
const {
  data: rules,
  pending,
  error: fetchError,
  refresh: refreshRules,
} = await useFetch<any[]>(`${API_BASE}/rules/`)

// ML Model Status Fetching
const {
  data: mlStatus,
  error: mlStatusError,
  refresh: refreshMLStatus,
} = await useFetch<any>(`${API_BASE}/ml/status`)

const retraining = ref(false)

const triggerRetrain = async () => {
  pageError.value = null
  successMessage.value = null
  retraining.value = true
  try {
    const res = await $fetch<any>(`${API_BASE}/ml/retrain?force=true`, {
      method: 'POST',
    })
    if (res.success) {
      successMessage.value = res.message
    } else {
      pageError.value = res.message || 'Model retraining did not activate a new candidate.'
    }
    await refreshMLStatus()
  } catch (err: any) {
    pageError.value = err?.data?.detail || err.message || 'Retraining failed.'
  } finally {
    retraining.value = false
  }
}

const statusBadgeClass = computed(() => {
  const s = mlStatus.value?.status
  if (s === 'Ready') return 'status-ready'
  if (s === 'Stale') return 'status-stale'
  return 'status-needs-data'
})

const formatTrainedDate = (d: string | null | undefined) => {
  if (!d) return 'Never'
  try {
    const date = new Date(d)
    return date.toLocaleString()
  } catch {
    return d
  }
}

// Page Alerts
const pageError = ref<string | null>(null)
const successMessage = ref<string | null>(null)

// Modal State
const isAddOpen = ref(false)
const isEditOpen = ref(false)
const isDeleteOpen = ref(false)
const isApplyOpen = ref(false)

const selectedRule = ref<any | null>(null)
const isSubmitting = ref(false)
const modalError = ref<string | null>(null)

// Apply / Preview State
const isLoadingPreview = ref(false)
const previewCount = ref(0)

// Form State
const ruleForm = reactive({
  merchant: '',
  category_id: '',
})

const editForm = reactive({
  merchant: '',
  category_id: '',
})

const formErrors = reactive({
  merchant: '',
  category_id: '',
})

// Category Group helper
const getCategoryGroupName = (categoryId: string) => {
  for (const group of categoryGroups.value || []) {
    const found = group.categories?.find((c: any) => c.category_id === categoryId)
    if (found) {
      return group.name
    }
  }
  return ''
}

// Form validation
const isFormValid = computed(() => {
  return ruleForm.merchant.trim().length > 0 && !!ruleForm.category_id
})

const isEditFormValid = computed(() => {
  return editForm.merchant.trim().length > 0 && !!editForm.category_id
})

// --- Modal Handlers ---

const openAddModal = () => {
  ruleForm.merchant = ''
  ruleForm.category_id = ''
  formErrors.merchant = ''
  formErrors.category_id = ''
  modalError.value = null
  isAddOpen.value = true
}

const closeAddModal = () => {
  isAddOpen.value = false
  modalError.value = null
}

const openEditModal = (rule: any) => {
  selectedRule.value = rule
  editForm.merchant = rule.merchant
  editForm.category_id = rule.category_id
  formErrors.merchant = ''
  formErrors.category_id = ''
  modalError.value = null
  isEditOpen.value = true
}

const closeEditModal = () => {
  isEditOpen.value = false
  selectedRule.value = null
  modalError.value = null
}

const openDeleteModal = (rule: any) => {
  selectedRule.value = rule
  modalError.value = null
  isDeleteOpen.value = true
}

const closeDeleteModal = () => {
  isDeleteOpen.value = false
  selectedRule.value = null
  modalError.value = null
}

const openApplyModal = async (rule: any) => {
  selectedRule.value = rule
  previewCount.value = 0
  modalError.value = null
  isLoadingPreview.value = true
  isApplyOpen.value = true

  try {
    const response = await fetch(`${API_BASE}/rules/${rule.id}/preview`)
    if (!response.ok) {
      const err = await response.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to preview rule matches')
    }
    const data = await response.json()
    previewCount.value = data.matching_count ?? 0
  } catch (err: any) {
    modalError.value = err.message || 'Error checking matching transactions.'
  } finally {
    isLoadingPreview.value = false
  }
}

const closeApplyModal = () => {
  isApplyOpen.value = false
  selectedRule.value = null
  modalError.value = null
  previewCount.value = 0
}

// --- Submit Actions ---

const submitAddRule = async () => {
  if (!isFormValid.value) return

  isSubmitting.value = true
  modalError.value = null

  try {
    const response = await fetch(`${API_BASE}/rules/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        merchant: ruleForm.merchant.trim(),
        category_id: ruleForm.category_id,
      }),
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || 'Failed to create categorization rule')
    }

    closeAddModal()
    await refreshRules()
    successMessage.value = `Created categorization rule for "${ruleForm.merchant.trim()}".`
  } catch (err: any) {
    modalError.value = err.message || 'Failed to create rule. Please try again.'
  } finally {
    isSubmitting.value = false
  }
}

const submitEditRule = async () => {
  if (!isEditFormValid.value || !selectedRule.value) return

  isSubmitting.value = true
  modalError.value = null

  try {
    const response = await fetch(`${API_BASE}/rules/${selectedRule.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        merchant: editForm.merchant.trim(),
        category_id: editForm.category_id,
      }),
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || 'Failed to update categorization rule')
    }

    const savedName = editForm.merchant.trim()
    closeEditModal()
    await refreshRules()
    successMessage.value = `Updated categorization rule for "${savedName}".`
  } catch (err: any) {
    modalError.value = err.message || 'Failed to update rule. Please try again.'
  } finally {
    isSubmitting.value = false
  }
}

const submitDeleteRule = async () => {
  if (!selectedRule.value) return

  isSubmitting.value = true
  modalError.value = null

  try {
    const merchantName = selectedRule.value.merchant
    const response = await fetch(`${API_BASE}/rules/${selectedRule.value.id}`, {
      method: 'DELETE',
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || 'Failed to delete categorization rule')
    }

    closeDeleteModal()
    await refreshRules()
    successMessage.value = `Deleted categorization rule for "${merchantName}".`
  } catch (err: any) {
    modalError.value = err.message || 'Failed to delete rule. Please try again.'
  } finally {
    isSubmitting.value = false
  }
}

const submitApplyRule = async () => {
  if (!selectedRule.value) return

  isSubmitting.value = true
  modalError.value = null

  try {
    const categoryName = selectedRule.value.category?.name || 'target category'
    const ruleId = selectedRule.value.id
    const response = await fetch(`${API_BASE}/rules/${ruleId}/apply`, {
      method: 'POST',
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || 'Failed to apply categorization rule')
    }

    const data = await response.json()
    const applied = data.applied_count ?? 0
    closeApplyModal()
    successMessage.value = `Successfully categorized ${applied} ${applied === 1 ? 'transaction' : 'transactions'} as "${categoryName}".`
  } catch (err: any) {
    modalError.value = err.message || 'Failed to apply rule. Please try again.'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
/* Sections sit on the page: a heading row, then content. One rule between them. */
.settings-section {
  min-width: 0;
}

.settings-section + .settings-section {
  margin-top: var(--space-xl);
  padding-top: var(--space-lg);
  border-top: 1px solid var(--border-subtle);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: var(--space-sm) var(--space-lg);
  margin-bottom: var(--space-md);
}

.section-titles {
  flex: 1 1 22rem;
  min-width: 0;
  max-width: 62ch;
}

.section-heading {
  margin: 0;
  font-size: var(--type-heading-size);
  font-weight: var(--type-heading-weight);
  line-height: var(--line-height-tight);
  color: var(--text-primary);
}

.section-meta {
  margin: var(--space-xs) 0 0;
  font-size: var(--type-meta-size);
  line-height: 1.45;
  color: var(--text-muted);
}

.section-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-md);
}

.rules-count {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  white-space: nowrap;
}

/* Feedback ------------------------------------------------------------------ */

.success-banner {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
  padding: 8px 8px 8px var(--space-md);
  background-color: var(--status-success-bg);
  border: 1px solid var(--status-success-border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.success-icon {
  color: var(--status-success);
}

.success-text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.success-dismiss {
  color: var(--text-secondary);
}

/* Rules table ---------------------------------------------------------------
   One bounded surface. Wide by default; a single narrow tier below 520px
   (no adjacent ranges, so no fractional gaps). */

.table-container {
  container: rules / inline-size;
  overflow: hidden;
}

.rules-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.rules-table th {
  padding: var(--space-sm) var(--space-md);
  background: var(--table-header);
  color: var(--text-muted);
  font-size: var(--type-meta-size);
  font-weight: var(--font-weight-medium);
  border-bottom: 1px solid var(--border-default);
}

.rules-table td {
  padding: 10px var(--space-md);
  vertical-align: middle;
}

.rule-row + .rule-row td {
  border-top: 1px solid var(--table-border);
}

.rule-row:hover {
  background: var(--table-hover);
}

.th-merchant,
.td-merchant {
  width: 38%;
}

.th-actions,
.td-actions {
  width: 1%;
  white-space: nowrap;
}

.merchant-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.td-category {
  overflow-wrap: anywhere;
}

.category-name {
  color: var(--text-primary);
}

.group-name {
  margin-left: var(--space-sm);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.action-buttons {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}

.btn-apply {
  margin-right: var(--space-xs);
}

.action-buttons .btn-icon {
  min-width: 32px;
  min-height: 32px;
  color: var(--text-muted);
}

.action-buttons .btn-icon:hover:not(:disabled) {
  color: var(--text-primary);
}

.action-buttons .btn-icon-danger:hover:not(:disabled),
.action-buttons .btn-icon-danger:focus-visible {
  color: var(--status-error);
}

/* Narrow tier: merchant over category, actions held on the right */
@container rules (width < 520px) {
  .rules-table,
  .rules-table tbody {
    display: block;
  }

  .rules-table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .rule-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      "merchant actions"
      "category actions";
    column-gap: var(--space-sm);
    align-items: center;
    padding: 10px var(--space-sm) 10px var(--space-md);
  }

  .rule-row + .rule-row {
    border-top: 1px solid var(--table-border);
  }

  .rule-row + .rule-row td {
    border-top: none;
  }

  .rules-table td {
    padding: 0;
    width: auto;
  }

  .td-merchant { grid-area: merchant; }
  .td-category { grid-area: category; font-size: var(--type-meta-size); }
  .td-actions { grid-area: actions; }

  .action-buttons .btn-icon {
    min-width: 36px;
    min-height: 36px;
  }
}

/* Model facts --------------------------------------------------------------- */

.model-facts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
  gap: var(--space-md) var(--space-lg);
  margin: 0;
}

.fact {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  min-width: 0;
}

.fact-label {
  font-size: var(--type-label-size);
  font-weight: var(--type-label-weight);
  color: var(--text-muted);
}

.fact-value {
  margin: 0;
  font-size: var(--type-subheading-size);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

/* Status is named in text; tone only reinforces it */
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: var(--type-meta-size);
  font-weight: var(--font-weight-medium);
}

.status-ready {
  background: var(--status-success-bg);
  border-color: var(--status-success-border);
  color: var(--status-success);
}

.status-stale {
  background: var(--status-warning-bg);
  border-color: var(--status-warning-border);
  color: var(--status-warning);
}

.status-needs-data {
  background: var(--bg-subtle);
  border-color: var(--border-default);
  color: var(--text-secondary);
}

.model-message {
  margin: var(--space-md) 0 0;
  max-width: 62ch;
  font-size: var(--type-meta-size);
  line-height: 1.45;
  color: var(--text-muted);
}

/* Appearance ---------------------------------------------------------------- */

.theme-fieldset {
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
}

.theme-legend {
  padding: 0;
  margin-bottom: var(--space-sm);
  font-size: var(--type-label-size);
  font-weight: var(--type-label-weight);
  color: var(--text-secondary);
}

/* One bounded list of rows, like the rules table; the selected row carries */
/* the native radio state plus an accent tint and edge, never color alone.  */
.theme-options {
  max-width: 34rem;
  background-color: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.theme-option {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: 10px var(--space-md);
  cursor: pointer;
  box-shadow: inset 3px 0 0 transparent;
}

.theme-option + .theme-option {
  border-top: 1px solid var(--border-subtle);
}

.theme-option:hover {
  background-color: var(--table-hover);
}

.theme-option.is-selected {
  background-color: var(--accent-subtle);
  box-shadow: inset 3px 0 0 var(--accent-primary);
}

.theme-radio {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  margin: 2px 0 0;
  cursor: pointer;
}

.theme-option-text {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 var(--space-sm);
  min-width: 0;
}

.theme-option-label {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.theme-option.is-selected .theme-option-label {
  font-weight: var(--font-weight-semibold);
}

.theme-option-desc {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

/* Dialogs ------------------------------------------------------------------- */

.modal-form,
.modal-content-delete,
.modal-content-apply {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.modal-form :deep(.form-field) {
  margin-bottom: 0;
}

.delete-warning {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.5;
}

.callout-box {
  margin: 0;
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-sunken);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
}

.callout-list {
  padding-left: calc(var(--space-md) + 1.1em);
}

.callout-list li,
.callout-text {
  margin: 0;
  font-size: var(--type-meta-size);
  color: var(--text-secondary);
  line-height: 1.5;
}

.callout-list li + li {
  margin-top: var(--space-2xs);
}

.preview-match-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
}

.match-count-number {
  font-family: var(--font-numeric);
  font-variant-numeric: var(--font-numeric-features);
  font-size: var(--type-metric-size);
  font-weight: var(--type-metric-weight);
  letter-spacing: var(--type-metric-tracking);
  line-height: 1;
  color: var(--text-primary);
}

.match-count-label {
  color: var(--text-primary);
}

.preview-explanation,
.zero-desc {
  margin: 0;
  max-width: 420px;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.preview-zero-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--space-xs);
  padding: var(--space-md) 0;
}

.zero-title {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}
</style>
