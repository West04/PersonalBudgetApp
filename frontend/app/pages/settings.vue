<template>
  <div class="settings-page">
    <PageHeader
      title="Settings"
      subtitle="Manage application settings and transaction automation rules"
    >
      <template #actions>
        <button
          type="button"
          class="btn btn-primary"
          @click="openAddModal"
          aria-label="Create new categorization rule"
        >
          + Add Rule
        </button>
      </template>
    </PageHeader>

    <!-- Error Banner -->
    <ErrorBanner
      v-if="pageError"
      :error="pageError"
      @dismiss="pageError = null"
    />

    <!-- Success Feedback Banner -->
    <div
      v-if="successMessage"
      class="success-banner"
      role="status"
      aria-live="polite"
    >
      <span class="success-icon" aria-hidden="true">✓</span>
      <span class="success-text">{{ successMessage }}</span>
      <button
        type="button"
        class="success-dismiss"
        @click="successMessage = null"
        aria-label="Dismiss success message"
      >
        ✕
      </button>
    </div>

    <!-- Main Card -->
    <div class="rules-card surface-card">
      <div class="card-header-row">
        <div>
          <h2 class="section-title">Categorization Rules</h2>
          <p class="section-desc">
            Rules automatically assign categories to new transactions from normalized merchant identity.
            Existing manual categories are always preserved.
          </p>
        </div>
        <div v-if="rules && rules.length > 0" class="rules-count-badge">
          {{ rules.length }} {{ rules.length === 1 ? 'rule' : 'rules' }}
        </div>
      </div>

      <!-- Loading State -->
      <LoadingState v-if="pending" message="Loading categorization rules..." />

      <template v-else>
        <!-- Empty State -->
        <EmptyState
          v-if="!rules || rules.length === 0"
          title="No categorization rules yet"
          description="Create deterministic rules to categorize transactions automatically when imported or added."
        >
          <template #actions>
            <button
              type="button"
              class="btn btn-primary"
              @click="openAddModal"
            >
              + Add First Rule
            </button>
          </template>
        </EmptyState>

        <!-- Rules Table -->
        <div v-else class="table-container">
          <table class="rules-table" aria-label="Categorization rules table">
            <thead>
              <tr>
                <th scope="col" class="th-merchant">Merchant</th>
                <th scope="col" class="th-category">Target Category</th>
                <th scope="col" class="th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rule in rules" :key="rule.id" class="rule-row">
                <td class="td-merchant">
                  <span class="merchant-badge">{{ rule.merchant }}</span>
                </td>
                <td class="td-category">
                  <div class="category-info">
                    <span class="category-name">{{ rule.category?.name || 'Unknown Category' }}</span>
                    <span v-if="getCategoryGroupName(rule.category_id)" class="group-name-tag">
                      {{ getCategoryGroupName(rule.category_id) }}
                    </span>
                  </div>
                </td>
                <td class="td-actions">
                  <div class="action-buttons">
                    <button
                      type="button"
                      class="btn-action btn-apply"
                      @click="openApplyModal(rule)"
                      :aria-label="`Apply rule for ${rule.merchant} to existing uncategorized transactions`"
                      title="Apply to matching uncategorized transactions"
                    >
                      ⚡ Apply
                    </button>
                    <button
                      type="button"
                      class="btn-action btn-edit"
                      @click="openEditModal(rule)"
                      :aria-label="`Edit rule for ${rule.merchant}`"
                      title="Edit rule"
                    >
                      ✎ Edit
                    </button>
                    <button
                      type="button"
                      class="btn-action btn-delete"
                      @click="openDeleteModal(rule)"
                      :aria-label="`Delete rule for ${rule.merchant}`"
                      title="Delete rule"
                    >
                      ✕ Delete
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

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
        <div class="callout-box">
          <p class="callout-text">
            • Future transactions will no longer be automatically categorized by this rule.<br />
            • Previously categorized transactions will remain unchanged.
          </p>
        </div>

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
            <div class="zero-icon">ℹ️</div>
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
.settings-page {
  max-width: var(--page-max-width);
  margin: 0 auto;
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.success-banner {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background-color: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
  color: var(--color-success-hover);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.success-icon {
  font-weight: var(--font-weight-bold);
}

.success-text {
  flex: 1;
}

.success-dismiss {
  background: none;
  border: none;
  color: currentColor;
  cursor: pointer;
  padding: var(--space-2xs) var(--space-xs);
  font-size: var(--font-size-base);
  opacity: 0.8;
  border-radius: var(--radius-xs);
}

.success-dismiss:hover {
  opacity: 1;
}

.rules-card {
  padding: var(--space-lg);
  border-radius: var(--radius-lg);
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
  padding-bottom: var(--space-md);
  border-bottom: 1px solid var(--color-border);
}

.section-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
  margin: 0 0 var(--space-xs) 0;
}

.section-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
  max-width: 650px;
  line-height: 1.45;
}

.rules-count-badge {
  padding: var(--space-2xs) var(--space-sm);
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.table-container {
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.rules-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.rules-table th {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-background);
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--color-border);
}

.rules-table td {
  padding: var(--space-md);
  border-bottom: 1px solid var(--color-border-subtle);
  vertical-align: middle;
}

.rule-row:last-child td {
  border-bottom: none;
}

.rule-row:hover {
  background: var(--color-surface-hover);
}

.merchant-badge {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  font-size: var(--font-size-base);
}

.category-info {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex-wrap: wrap;
}

.category-name {
  font-weight: var(--font-weight-medium);
  color: var(--color-text);
}

.group-name-tag {
  font-size: var(--font-size-2xs);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.action-buttons {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  flex-wrap: wrap;
}

.btn-action {
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  display: inline-flex;
  align-items: center;
  gap: var(--space-2xs);
  transition: all 0.15s ease;
  min-height: 32px;
}

.btn-action:hover {
  background: var(--color-surface-hover);
  border-color: var(--color-border-hover);
}

.btn-apply {
  color: var(--color-primary);
  border-color: rgba(37, 99, 235, 0.3);
  background: var(--color-primary-light);
}

.btn-apply:hover {
  background: #dbeafe;
  border-color: var(--color-primary);
}

.btn-delete:hover {
  color: var(--color-danger);
  border-color: var(--color-danger-border);
  background: var(--color-danger-bg);
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.form-input,
.form-select {
  width: 100%;
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  background: var(--color-surface);
  color: var(--color-text);
  font-family: inherit;
  transition: border-color 0.15s ease;
  min-height: 42px;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus);
}

.modal-content-delete {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.delete-warning {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--color-text);
  line-height: 1.5;
}

.callout-box {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-background);
  border-left: 3px solid var(--color-primary);
  border-radius: var(--radius-xs);
}

.callout-text {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  line-height: 1.5;
}

.modal-content-apply {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.preview-match-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--space-sm);
  padding: var(--space-md);
}

.match-count-number {
  font-size: 2.5rem;
  font-weight: var(--font-weight-bold);
  color: var(--color-primary);
  line-height: 1;
}

.match-count-label {
  font-size: var(--font-size-base);
  color: var(--color-text);
}

.preview-explanation {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
  max-width: 420px;
}

.preview-zero-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--space-xs);
  padding: var(--space-lg) var(--space-md);
}

.zero-icon {
  font-size: 2rem;
  margin-bottom: var(--space-xs);
}

.zero-title {
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-md);
  color: var(--color-text);
}

.zero-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
  max-width: 400px;
}

@media (max-width: 640px) {
  .settings-page {
    padding: var(--space-sm);
  }

  .card-header-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .rules-table th,
  .rules-table td {
    padding: var(--space-sm);
  }

  .action-buttons {
    flex-direction: column;
    align-items: stretch;
  }

  .btn-action {
    justify-content: center;
  }
}
</style>
