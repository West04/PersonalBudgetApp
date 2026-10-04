<template>
  <div class="categories-page">
    <PageHeader title="Budget" subtitle="Plan and track monthly spending across category groups">
      <template #controls>
        <MonthNavigator />
      </template>
      <template #actions>
        <button type="button" class="btn btn-primary" @click="openAddGroupModal">
          + Add Group
        </button>
      </template>
    </PageHeader>

    <!-- Error Banner -->
    <ErrorBanner :error="error" @dismiss="error = null" />

    <!-- Loading State -->
    <LoadingState v-if="pending" message="Loading budget..." />

    <template v-else>
      <!-- Summary Cards -->
      <section class="summary-cards" aria-label="Monthly budget summary">
        <div class="surface-card summary-card income">
          <div class="card-label">Planned Income</div>
          <div class="card-value font-mono">{{ formatCurrency(totalIncomePlanned) }}</div>
          <div class="card-sub font-mono">Actual: {{ formatCurrency(totalIncomeActual) }}</div>
        </div>

        <div class="surface-card summary-card expense">
          <div class="card-label">Planned Expenses</div>
          <div class="card-value font-mono">{{ formatCurrency(totalExpensePlanned) }}</div>
          <div class="card-sub font-mono">Actual: {{ formatCurrency(totalExpenseActual) }}</div>
        </div>

        <div class="surface-card summary-card assign" :class="{ 'warning': toBeAssigned < 0 }">
          <div class="card-label">To Be Assigned</div>
          <div class="card-value font-mono">{{ formatCurrency(toBeAssigned) }}</div>
          <div class="card-sub" v-if="toBeAssigned === 0">Every dollar has a job!</div>
          <div class="card-sub" v-else-if="toBeAssigned > 0">You have money to budget</div>
          <div class="card-sub" v-else>You are over-budgeted!</div>
        </div>
      </section>

      <!-- Empty State -->
      <EmptyState
        v-if="!categoryGroups.length"
        title="No category groups yet"
        description="Create category groups to organize your budget and allocate planned spending."
      >
        <template #actions>
          <button type="button" class="btn btn-primary" @click="openAddGroupModal">
            + Add Group
          </button>
        </template>
      </EmptyState>

      <!-- Draggable Group List -->
      <draggable
        v-else
        v-model="categoryGroups"
        item-key="category_group_id"
        handle=".group-drag-handle"
        ghost-class="ghost"
        @end="onGroupDragEnd"
        class="groups-list"
      >
        <template #item="{ element: group }">
          <section
            class="group-section surface-card"
            :class="{ 'is-collapsed': isGroupCollapsed(group.category_group_id) }"
            :aria-label="group.name"
          >
            <!-- Group Header -->
            <div class="group-header">
              <span
                class="drag-handle group-drag-handle"
                title="Drag to reorder group"
                aria-label="Drag group to reorder"
                tabindex="-1"
              >⋮⋮</span>

              <!-- Entire reasonable non-interactive area toggles expand/collapse -->
              <button
                type="button"
                class="group-toggle-btn"
                :aria-expanded="!isGroupCollapsed(group.category_group_id)"
                :aria-controls="`group-categories-${group.category_group_id}`"
                :aria-label="`${group.name} group, ${isGroupCollapsed(group.category_group_id) ? 'collapsed' : 'expanded'}`"
                @click="toggleGroupCollapse(group.category_group_id)"
              >
                <div class="group-identity">
                  <svg
                    class="group-chevron"
                    :class="{ 'collapsed': isGroupCollapsed(group.category_group_id) }"
                    viewBox="0 0 24 24"
                    width="18"
                    height="18"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <polyline points="6 9 12 15 18 9"></polyline>
                  </svg>
                  <h2 class="group-title">{{ group.name }}</h2>
                  <span class="group-count text-muted">({{ group.categories.length }})</span>
                </div>

                <div class="group-totals font-mono">
                  <span class="group-metric">
                    <span class="metric-label">Planned:</span>
                    <span class="metric-val">{{ formatCurrency(getGroupTotalPlanned(group)) }}</span>
                  </span>
                  <span class="group-metric">
                    <span class="metric-label">Activity:</span>
                    <span class="metric-val text-muted">{{ formatCurrency(getGroupTotalActual(group)) }}</span>
                  </span>
                  <span
                    class="group-metric"
                    :class="{ 'negative': getGroupTotalRemaining(group) < 0 }"
                  >
                    <span class="metric-label">Remaining:</span>
                    <span class="metric-val">{{ formatCurrency(getGroupTotalRemaining(group)) }}</span>
                  </span>
                </div>
              </button>

              <!-- Group Actions -->
              <div class="group-actions">
                <button
                  type="button"
                  class="btn btn-secondary btn-sm"
                  @click="openAddCategoryModal(group)"
                  :aria-label="`Add category to ${group.name}`"
                  title="Add Category"
                >
                  + Add Category
                </button>
                <button
                  type="button"
                  class="btn-icon"
                  @click="openEditGroupModal(group)"
                  :aria-label="`Edit ${group.name} group`"
                  title="Edit Group"
                >
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                  </svg>
                </button>
                <button
                  type="button"
                  class="btn-icon btn-icon-danger"
                  @click="confirmDeleteGroup(group)"
                  :aria-label="`Delete ${group.name} group`"
                  title="Delete Group"
                >
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polyline points="3 6 5 6 21 6"></polyline>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                  </svg>
                </button>
              </div>
            </div>

            <!-- Categories Container -->
            <div
              :id="`group-categories-${group.category_group_id}`"
              v-show="!isGroupCollapsed(group.category_group_id)"
              class="group-body"
            >
              <!-- Empty state inside group -->
              <div v-if="!group.categories.length" class="empty-group-body">
                <p class="text-muted">No categories in this group yet.</p>
                <button
                  type="button"
                  class="btn btn-secondary btn-sm"
                  @click="openAddCategoryModal(group)"
                >
                  + Add First Category
                </button>
              </div>

              <!-- Categories Draggable List -->
              <draggable
                v-else
                v-model="group.categories"
                item-key="category_id"
                handle=".category-drag-handle"
                ghost-class="ghost"
                @end="onCategoryDragEnd(group)"
                class="category-list"
              >
                <template #item="{ element: category }">
                  <div class="category-row">
                    <span
                      class="drag-handle category-drag-handle"
                      title="Drag to reorder category"
                      aria-label="Drag category to reorder"
                      tabindex="-1"
                    >⋮⋮</span>

                    <!-- Info: Name & badges -->
                    <div class="category-info">
                      <span class="category-name">{{ category.name }}</span>
                      <span :class="['type-badge', category.type]">{{ category.type }}</span>
                      <span v-if="!category.is_active" class="inactive-badge">Inactive</span>
                    </div>

                    <!-- Planned Amount Input -->
                    <div class="category-planned">
                      <label :for="`planned-${category.category_id}`" class="sr-only">
                        Planned amount for {{ category.name }}
                      </label>
                      <div class="amount-input-box">
                        <span class="currency-symbol" aria-hidden="true">$</span>
                        <input
                          :id="`planned-${category.category_id}`"
                          type="number"
                          min="0"
                          step="0.01"
                          :value="getCategoryPlanned(category)"
                          @change="onPlannedAmountChange(category, ($event.target as HTMLInputElement).value)"
                          @keydown.enter="($event.target as HTMLInputElement).blur()"
                          @keydown.escape="revertPlannedAmount(category, $event.target as HTMLInputElement)"
                          class="form-input font-mono amount-input"
                          placeholder="0.00"
                        />
                      </div>
                    </div>

                    <!-- Activity / Actual -->
                    <div class="category-metric category-actual font-mono text-muted">
                      <span class="metric-mobile-label">Activity: </span>
                      <span>{{ formatCurrency(getCategoryActual(category)) }}</span>
                    </div>

                    <!-- Remaining -->
                    <div
                      class="category-metric category-remaining font-mono"
                      :class="{ 'negative': getCategoryRemaining(category) < 0 }"
                    >
                      <span class="metric-mobile-label">Remaining: </span>
                      <span>{{ formatCurrency(getCategoryRemaining(category)) }}</span>
                    </div>

                    <!-- Progress Bar -->
                    <div class="category-progress" :title="`${Math.round(calculateProgress(category))}% of planned`" aria-hidden="true">
                      <div class="progress-bar-bg">
                        <div
                          class="progress-bar-fill"
                          :class="{ 'over-budget': getCategoryRemaining(category) < 0 }"
                          :style="{ width: calculateProgress(category) + '%' }"
                        ></div>
                      </div>
                    </div>

                    <!-- Actions -->
                    <div class="category-actions">
                      <button
                        type="button"
                        class="btn-icon"
                        @click="openEditCategoryModal(category)"
                        :aria-label="`Edit ${category.name}`"
                        title="Edit Category"
                      >
                        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                        </svg>
                      </button>
                      <button
                        type="button"
                        class="btn-icon btn-icon-danger"
                        @click="confirmDeleteCategory(category)"
                        :aria-label="`Delete ${category.name}`"
                        title="Delete Category"
                      >
                        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                          <polyline points="3 6 5 6 21 6"></polyline>
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                      </button>
                    </div>
                  </div>
                </template>
              </draggable>
            </div>
          </section>
        </template>
      </draggable>
    </template>

    <!-- Dialog: Add Group -->
    <AppDialog
      :open="isAddGroupOpen"
      title="Add Category Group"
      @close="closeAddGroupModal"
    >
      <FormField label="Group Name" required :error="groupFormErrors.name" v-slot="{ id }">
        <input
          :id="id"
          v-model="groupForm.name"
          class="form-input"
          placeholder="e.g. Housing, Utilities, Food"
          autofocus
          @keydown.enter.prevent="submitAddGroup"
        />
      </FormField>

      <ErrorBanner v-if="groupModalError" :error="groupModalError" :dismissible="false" />

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeAddGroupModal">Cancel</button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!groupForm.name.trim() || isSubmittingGroup"
          @click="submitAddGroup"
        >
          {{ isSubmittingGroup ? 'Adding…' : 'Add Group' }}
        </button>
      </template>
    </AppDialog>

    <!-- Dialog: Edit Group -->
    <AppDialog
      :open="isEditGroupOpen"
      title="Edit Category Group"
      @close="closeEditGroupModal"
    >
      <FormField label="Group Name" required :error="groupFormErrors.name" v-slot="{ id }">
        <input
          :id="id"
          v-model="groupEditForm.name"
          class="form-input"
          placeholder="Group name"
          autofocus
          @keydown.enter.prevent="submitEditGroup"
        />
      </FormField>

      <ErrorBanner v-if="groupModalError" :error="groupModalError" :dismissible="false" />

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeEditGroupModal">Cancel</button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!groupEditForm.name.trim() || isSubmittingGroup"
          @click="submitEditGroup"
        >
          {{ isSubmittingGroup ? 'Saving…' : 'Save Changes' }}
        </button>
      </template>
    </AppDialog>

    <!-- Dialog: Add Category -->
    <AppDialog
      :open="isAddCategoryOpen"
      title="Add Category"
      @close="closeAddCategoryModal"
    >
      <div v-if="selectedGroupForCategory" class="target-group-badge">
        <span class="target-group-label">Group:</span>
        <strong class="target-group-name">{{ selectedGroupForCategory.name }}</strong>
      </div>

      <FormField v-else label="Category Group" required v-slot="{ id }">
        <select :id="id" v-model="categoryForm.group_id" class="form-select">
          <option
            v-for="g in categoryGroups"
            :key="g.category_group_id"
            :value="g.category_group_id"
          >
            {{ g.name }}
          </option>
        </select>
      </FormField>

      <FormField label="Category Name" required :error="categoryFormErrors.name" v-slot="{ id }">
        <input
          :id="id"
          v-model="categoryForm.name"
          class="form-input"
          placeholder="e.g. Groceries, Rent, Electric"
          autofocus
          @keydown.enter.prevent="submitAddCategory"
        />
      </FormField>

      <div class="field-row">
        <FormField label="Type" required v-slot="{ id }">
          <select :id="id" v-model="categoryForm.type" class="form-select">
            <option value="expense">Expense</option>
            <option value="income">Income</option>
            <option value="transfer">Transfer</option>
          </select>
        </FormField>

        <FormField
          label="Planned Amount ($)"
          hint="Initial monthly allocation"
          v-slot="{ id }"
        >
          <input
            :id="id"
            v-model="categoryForm.planned_amount"
            type="number"
            min="0"
            step="0.01"
            class="form-input font-mono"
            placeholder="0.00"
            @keydown.enter.prevent="submitAddCategory"
          />
        </FormField>
      </div>

      <div class="status-toggle-wrapper">
        <label class="checkbox-label">
          <input type="checkbox" v-model="categoryForm.is_active" class="form-checkbox" />
          <span>Active</span>
        </label>
      </div>

      <ErrorBanner v-if="categoryModalError" :error="categoryModalError" :dismissible="false" />

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeAddCategoryModal">Cancel</button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!categoryForm.name.trim() || isSubmittingCategory"
          @click="submitAddCategory"
        >
          {{ isSubmittingCategory ? 'Adding…' : 'Add Category' }}
        </button>
      </template>
    </AppDialog>

    <!-- Dialog: Edit Category -->
    <AppDialog
      :open="isEditCategoryOpen"
      title="Edit Category"
      @close="closeEditCategoryModal"
    >
      <FormField label="Category Group" required v-slot="{ id }">
        <select :id="id" v-model="categoryEditForm.group_id" class="form-select">
          <option
            v-for="g in categoryGroups"
            :key="g.category_group_id"
            :value="g.category_group_id"
          >
            {{ g.name }}
          </option>
        </select>
      </FormField>

      <FormField label="Category Name" required :error="categoryFormErrors.name" v-slot="{ id }">
        <input
          :id="id"
          v-model="categoryEditForm.name"
          class="form-input"
          placeholder="Category name"
          autofocus
          @keydown.enter.prevent="submitEditCategory"
        />
      </FormField>

      <div class="field-row">
        <FormField label="Type" required v-slot="{ id }">
          <select :id="id" v-model="categoryEditForm.type" class="form-select">
            <option value="expense">Expense</option>
            <option value="income">Income</option>
            <option value="transfer">Transfer</option>
          </select>
        </FormField>

        <FormField
          label="Planned Amount ($)"
          hint="Monthly planned amount"
          v-slot="{ id }"
        >
          <input
            :id="id"
            v-model="categoryEditForm.planned_amount"
            type="number"
            min="0"
            step="0.01"
            class="form-input font-mono"
            placeholder="0.00"
            @keydown.enter.prevent="submitEditCategory"
          />
        </FormField>
      </div>

      <div class="status-toggle-wrapper">
        <label class="checkbox-label">
          <input type="checkbox" v-model="categoryEditForm.is_active" class="form-checkbox" />
          <span>Active</span>
        </label>
      </div>

      <ErrorBanner v-if="categoryModalError" :error="categoryModalError" :dismissible="false" />

      <template #footer>
        <button type="button" class="btn btn-ghost" @click="closeEditCategoryModal">Cancel</button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!categoryEditForm.name.trim() || isSubmittingCategory"
          @click="submitEditCategory"
        >
          {{ isSubmittingCategory ? 'Saving…' : 'Save Changes' }}
        </button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import draggable from 'vuedraggable'
import { useBudgetMonth } from '~/composables/useBudgetMonth'

const API_BASE = '/api'

// --- Types ---
interface BudgetSummaryCategory {
  budget_id: string | null
  category_id: string
  name: string
  type: string
  planned: number
  actual: number
  remaining: number
  is_over_budget: boolean
}

interface BudgetSummaryGroup {
  group_id: string
  name: string
  categories: BudgetSummaryCategory[]
  total_planned: number
  total_actual: number
  total_remaining: number
}

interface BudgetSummary {
  month: string
  groups: BudgetSummaryGroup[]
  total_income_planned: number
  total_income_actual: number
  total_expense_planned: number
  total_expense_actual: number
  to_be_assigned: number
}

interface Category {
  category_id: string
  group_id: string
  name: string
  sort_order: number
  type: 'income' | 'expense' | 'transfer'
  is_active: boolean
}

interface CategoryGroup {
  category_group_id: string
  name: string
  sort_order: number
  categories: Category[]
}

// --- State & Month Synchronization ---
const { selectedMonth } = useBudgetMonth()

const categoryGroups = ref<CategoryGroup[]>([])
const budgetSummary = ref<BudgetSummary | null>(null)
const pending = ref(true)
const error = ref<string | null>(null)

// Collapse state for groups (to hide/show categories)
const collapsedGroups = ref<Record<string, boolean>>({})

// Modal Open States
const isAddGroupOpen = ref(false)
const isEditGroupOpen = ref(false)
const isAddCategoryOpen = ref(false)
const isEditCategoryOpen = ref(false)

// Forms State
const groupForm = ref({ name: '' })
const groupEditForm = ref<{ id: string; name: string; sort_order: number }>({
  id: '',
  name: '',
  sort_order: 0
})
const groupFormErrors = ref<{ name?: string }>({})
const groupModalError = ref<string | null>(null)
const isSubmittingGroup = ref(false)

const selectedGroupForCategory = ref<CategoryGroup | null>(null)
const categoryForm = ref<{
  name: string
  group_id: string
  type: 'expense' | 'income' | 'transfer'
  planned_amount: string | number
  is_active: boolean
}>({
  name: '',
  group_id: '',
  type: 'expense',
  planned_amount: '',
  is_active: true
})
const categoryFormErrors = ref<{ name?: string }>({})

const categoryEditForm = ref<{
  id: string
  name: string
  group_id: string
  type: 'expense' | 'income' | 'transfer'
  planned_amount: string | number
  is_active: boolean
}>({
  id: '',
  name: '',
  group_id: '',
  type: 'expense',
  planned_amount: '',
  is_active: true
})
const categoryModalError = ref<string | null>(null)
const isSubmittingCategory = ref(false)

// --- Data Fetching ---
const fetchData = async () => {
  pending.value = true
  error.value = null
  try {
    const [groupsRes, summaryRes] = await Promise.all([
      $fetch<CategoryGroup[]>(`${API_BASE}/category-groups`),
      $fetch<BudgetSummary>(`${API_BASE}/summary/budget`, { query: { month: selectedMonth.value } })
    ])
    categoryGroups.value = groupsRes
    budgetSummary.value = summaryRes
  } catch (err: any) {
    error.value = err.message || 'Failed to fetch data'
  } finally {
    pending.value = false
  }
}

// Watch month changes
watch(selectedMonth, fetchData, { immediate: true })

// Refresh summary data
const refreshSummary = async () => {
  try {
    const summaryRes = await $fetch<BudgetSummary>(`${API_BASE}/summary/budget`, {
      query: { month: selectedMonth.value }
    })
    budgetSummary.value = summaryRes
  } catch (err: any) {
    error.value = err.message || 'Failed to refresh budget summary'
  }
}

// --- Budget Summary Calculation Helpers ---
const getBudgetCategory = (categoryId: string): BudgetSummaryCategory | null => {
  if (!budgetSummary.value) return null
  for (const group of budgetSummary.value.groups) {
    const cat = group.categories.find(c => c.category_id === categoryId)
    if (cat) return cat
  }
  return null
}

const getCategoryPlanned = (category: Category): number => {
  const budgetCat = getBudgetCategory(category.category_id)
  return budgetCat ? Number(budgetCat.planned) : 0
}

const getCategoryActual = (category: Category): number => {
  const budgetCat = getBudgetCategory(category.category_id)
  return budgetCat ? Number(budgetCat.actual) : 0
}

const getCategoryRemaining = (category: Category): number => {
  const budgetCat = getBudgetCategory(category.category_id)
  return budgetCat ? Number(budgetCat.remaining) : 0
}

const getGroupTotalPlanned = (group: CategoryGroup): number => {
  return group.categories.reduce((sum, cat) => sum + getCategoryPlanned(cat), 0)
}

const getGroupTotalActual = (group: CategoryGroup): number => {
  return group.categories.reduce((sum, cat) => sum + getCategoryActual(cat), 0)
}

const getGroupTotalRemaining = (group: CategoryGroup): number => {
  return group.categories.reduce((sum, cat) => sum + getCategoryRemaining(cat), 0)
}

const calculateProgress = (category: Category): number => {
  const planned = getCategoryPlanned(category)
  const actual = getCategoryActual(category)
  if (planned === 0) return actual > 0 ? 100 : 0
  const pct = (actual / planned) * 100
  return Math.min(Math.max(pct, 0), 100)
}

// --- Computed Summary Totals ---
const totalIncomePlanned = computed(() => budgetSummary.value?.total_income_planned ?? 0)
const totalIncomeActual = computed(() => budgetSummary.value?.total_income_actual ?? 0)
const totalExpensePlanned = computed(() => budgetSummary.value?.total_expense_planned ?? 0)
const totalExpenseActual = computed(() => budgetSummary.value?.total_expense_actual ?? 0)
const toBeAssigned = computed(() => budgetSummary.value?.to_be_assigned ?? 0)

// --- Group Collapse Toggle ---
const toggleGroupCollapse = (groupId: string) => {
  collapsedGroups.value[groupId] = !collapsedGroups.value[groupId]
}

const isGroupCollapsed = (groupId: string): boolean => {
  return !!collapsedGroups.value[groupId]
}

// --- Drag and Drop Handlers ---
const onGroupDragEnd = async () => {
  const orderedIds = categoryGroups.value.map(g => g.category_group_id)
  try {
    await $fetch(`${API_BASE}/category-groups/reorder`, {
      method: 'POST',
      body: { order: orderedIds }
    })
  } catch (err: any) {
    error.value = 'Failed to save group order'
    await fetchData() // Rollback on error
  }
}

const onCategoryDragEnd = async (group: CategoryGroup) => {
  const orderedIds = group.categories.map(c => c.category_id)
  try {
    await $fetch(`${API_BASE}/categories/reorder`, {
      method: 'POST',
      body: { group_id: group.category_group_id, order: orderedIds }
    })
  } catch (err: any) {
    error.value = 'Failed to save category order'
    await fetchData() // Rollback on error
  }
}

// --- Group Actions & Modals ---
const openAddGroupModal = () => {
  groupForm.value = { name: '' }
  groupFormErrors.value = {}
  groupModalError.value = null
  isAddGroupOpen.value = true
}

const closeAddGroupModal = () => {
  isAddGroupOpen.value = false
  groupFormErrors.value = {}
  groupModalError.value = null
}

const submitAddGroup = async () => {
  const name = groupForm.value.name.trim()
  if (!name) {
    groupFormErrors.value = { name: 'Group name is required' }
    return
  }
  groupFormErrors.value = {}
  groupModalError.value = null
  isSubmittingGroup.value = true

  const maxOrder = categoryGroups.value.reduce((max, g) => Math.max(max, g.sort_order), -1)
  try {
    const newGroup = await $fetch<CategoryGroup>(`${API_BASE}/category-groups`, {
      method: 'POST',
      body: {
        name,
        sort_order: maxOrder + 1
      }
    })
    categoryGroups.value.push({ ...newGroup, categories: [] })
    closeAddGroupModal()
  } catch (err: any) {
    groupModalError.value = err.data?.detail || err.message || 'Failed to create group'
  } finally {
    isSubmittingGroup.value = false
  }
}

const openEditGroupModal = (group: CategoryGroup) => {
  groupEditForm.value = {
    id: group.category_group_id,
    name: group.name,
    sort_order: group.sort_order
  }
  groupFormErrors.value = {}
  groupModalError.value = null
  isEditGroupOpen.value = true
}

const closeEditGroupModal = () => {
  isEditGroupOpen.value = false
  groupFormErrors.value = {}
  groupModalError.value = null
}

const submitEditGroup = async () => {
  const name = groupEditForm.value.name.trim()
  if (!name) {
    groupFormErrors.value = { name: 'Group name is required' }
    return
  }
  groupFormErrors.value = {}
  groupModalError.value = null
  isSubmittingGroup.value = true

  try {
    await $fetch(`${API_BASE}/category-groups/${groupEditForm.value.id}`, {
      method: 'PUT',
      body: {
        name,
        sort_order: groupEditForm.value.sort_order
      }
    })
    const group = categoryGroups.value.find(g => g.category_group_id === groupEditForm.value.id)
    if (group) {
      group.name = name
    }
    closeEditGroupModal()
  } catch (err: any) {
    groupModalError.value = err.data?.detail || err.message || 'Failed to update group'
  } finally {
    isSubmittingGroup.value = false
  }
}

const confirmDeleteGroup = async (group: CategoryGroup) => {
  if (group.categories.length > 0) {
    const count = group.categories.length
    error.value = `Cannot delete "${group.name}" because it contains ${count} ${count === 1 ? 'category' : 'categories'}. Move or delete categories first.`
    return
  }
  if (!confirm(`Are you sure you want to delete "${group.name}"?`)) return

  try {
    await $fetch(`${API_BASE}/category-groups/${group.category_group_id}`, {
      method: 'DELETE'
    })
    categoryGroups.value = categoryGroups.value.filter(g => g.category_group_id !== group.category_group_id)
  } catch (err: any) {
    error.value = err.data?.detail || err.message || 'Failed to delete group'
  }
}

// --- Category Actions & Modals ---
const openAddCategoryModal = (group: CategoryGroup) => {
  selectedGroupForCategory.value = group
  categoryForm.value = {
    name: '',
    group_id: group.category_group_id,
    type: 'expense',
    planned_amount: '',
    is_active: true
  }
  categoryFormErrors.value = {}
  categoryModalError.value = null
  isAddCategoryOpen.value = true
}

const closeAddCategoryModal = () => {
  isAddCategoryOpen.value = false
  selectedGroupForCategory.value = null
  categoryFormErrors.value = {}
  categoryModalError.value = null
}

const submitAddCategory = async () => {
  const name = categoryForm.value.name.trim()
  const groupId = categoryForm.value.group_id
  if (!name) {
    categoryFormErrors.value = { name: 'Category name is required' }
    return
  }
  categoryFormErrors.value = {}
  categoryModalError.value = null
  isSubmittingCategory.value = true

  const targetGroup = categoryGroups.value.find(g => g.category_group_id === groupId)
  const maxOrder = targetGroup ? targetGroup.categories.reduce((max, c) => Math.max(max, c.sort_order), -1) : -1

  try {
    const newCategory = await $fetch<Category>(`${API_BASE}/categories`, {
      method: 'POST',
      body: {
        name,
        group_id: groupId,
        sort_order: maxOrder + 1,
        type: categoryForm.value.type,
        is_active: categoryForm.value.is_active
      }
    })

    // If initial planned amount provided, create budget entry
    const plannedVal = parseFloat(String(categoryForm.value.planned_amount)) || 0
    if (plannedVal > 0) {
      await $fetch(`${API_BASE}/budget/`, {
        method: 'POST',
        body: {
          category_id: newCategory.category_id,
          budget_month: `${selectedMonth.value}-01`,
          planned_amount: plannedVal
        }
      })
    }

    if (targetGroup) {
      targetGroup.categories.push(newCategory)
    }

    await refreshSummary()
    closeAddCategoryModal()
  } catch (err: any) {
    categoryModalError.value = err.data?.detail || err.message || 'Failed to create category'
  } finally {
    isSubmittingCategory.value = false
  }
}

const openEditCategoryModal = (category: Category) => {
  categoryEditForm.value = {
    id: category.category_id,
    name: category.name,
    group_id: category.group_id,
    type: category.type,
    planned_amount: getCategoryPlanned(category),
    is_active: category.is_active
  }
  categoryFormErrors.value = {}
  categoryModalError.value = null
  isEditCategoryOpen.value = true
}

const closeEditCategoryModal = () => {
  isEditCategoryOpen.value = false
  categoryFormErrors.value = {}
  categoryModalError.value = null
}

const submitEditCategory = async () => {
  const name = categoryEditForm.value.name.trim()
  const groupId = categoryEditForm.value.group_id
  if (!name) {
    categoryFormErrors.value = { name: 'Category name is required' }
    return
  }
  categoryFormErrors.value = {}
  categoryModalError.value = null
  isSubmittingCategory.value = true

  try {
    const updatedCategory = await $fetch<Category>(`${API_BASE}/categories/${categoryEditForm.value.id}`, {
      method: 'PUT',
      body: {
        name,
        group_id: groupId,
        type: categoryEditForm.value.type,
        is_active: categoryEditForm.value.is_active
      }
    })

    // Check if planned amount changed
    const currentPlanned = getCategoryPlanned(updatedCategory)
    const newPlanned = parseFloat(String(categoryEditForm.value.planned_amount)) || 0
    if (newPlanned !== currentPlanned) {
      await savePlannedAmount(updatedCategory, newPlanned)
    }

    // Handle group migration in local state if group changed
    for (const group of categoryGroups.value) {
      const idx = group.categories.findIndex(c => c.category_id === updatedCategory.category_id)
      if (idx !== -1) {
        if (group.category_group_id !== groupId) {
          group.categories.splice(idx, 1)
          const newParent = categoryGroups.value.find(g => g.category_group_id === groupId)
          if (newParent) {
            newParent.categories.push(updatedCategory)
          }
        } else {
          group.categories[idx] = updatedCategory
        }
        break
      }
    }

    await refreshSummary()
    closeEditCategoryModal()
  } catch (err: any) {
    categoryModalError.value = err.data?.detail || err.message || 'Failed to update category'
  } finally {
    isSubmittingCategory.value = false
  }
}

const confirmDeleteCategory = async (category: Category) => {
  if (!confirm(`Are you sure you want to delete "${category.name}"?`)) return

  try {
    await $fetch(`${API_BASE}/categories/${category.category_id}`, {
      method: 'DELETE'
    })
    for (const group of categoryGroups.value) {
      const idx = group.categories.findIndex(c => c.category_id === category.category_id)
      if (idx !== -1) {
        group.categories.splice(idx, 1)
        break
      }
    }
    await refreshSummary()
  } catch (err: any) {
    error.value = err.data?.detail || err.message || 'Failed to delete category'
  }
}

// --- Planned Amount Editing ---
const savePlannedAmount = async (category: Category, rawValue: string | number) => {
  const amount = typeof rawValue === 'number' ? rawValue : (parseFloat(rawValue) || 0)
  const budgetCat = getBudgetCategory(category.category_id)
  try {
    if (budgetCat?.budget_id) {
      await $fetch(`${API_BASE}/budget/${budgetCat.budget_id}`, {
        method: 'PUT',
        body: { planned_amount: amount }
      })
    } else {
      await $fetch(`${API_BASE}/budget/`, {
        method: 'POST',
        body: {
          category_id: category.category_id,
          budget_month: `${selectedMonth.value}-01`,
          planned_amount: amount
        }
      })
    }
    await refreshSummary()
  } catch (err: any) {
    error.value = err.data?.detail || err.message || 'Failed to save planned amount'
  }
}

const onPlannedAmountChange = async (category: Category, rawValue: string) => {
  const amount = parseFloat(rawValue) || 0
  const current = getCategoryPlanned(category)
  if (amount === current) return
  await savePlannedAmount(category, amount)
}

const revertPlannedAmount = (category: Category, inputEl: HTMLInputElement) => {
  inputEl.value = String(getCategoryPlanned(category))
  inputEl.blur()
}

// --- Helpers ---
const formatCurrency = (amount: number | string) => {
  const val = parseFloat(String(amount)) || 0
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD'
  }).format(val)
}
</script>

<style scoped>
.categories-page {
  padding: var(--space-lg);
  max-width: var(--page-max-width);
  margin: 0 auto;
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-xl);
}

.summary-card {
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
}

.card-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: var(--font-weight-semibold);
}

.card-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
  margin-bottom: var(--space-2xs);
}

.card-sub {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.summary-card.income .card-value { color: var(--color-success); }
.summary-card.expense .card-value { color: var(--color-warning); }
.summary-card.assign .card-value { color: var(--color-primary); }
.summary-card.assign.warning .card-value { color: var(--color-danger); }

/* Groups List */
.groups-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.group-section {
  overflow: hidden;
  transition: box-shadow 0.15s ease;
}

.group-section:hover {
  box-shadow: var(--shadow-md);
}

.group-header {
  display: flex;
  align-items: center;
  padding: var(--space-xs) var(--space-sm);
  background-color: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  min-height: 56px;
  gap: var(--space-xs);
}

.group-section.is-collapsed .group-header {
  border-bottom: none;
}

.drag-handle {
  cursor: grab;
  color: var(--color-text-light);
  font-size: 1.1rem;
  padding: var(--space-xs) var(--space-sm);
  user-select: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s ease;
  flex-shrink: 0;
}

.drag-handle:hover {
  color: var(--color-text);
}

.drag-handle:active {
  cursor: grabbing;
}

/* Group toggle button spans entire non-interactive middle area */
.group-toggle-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  color: inherit;
  transition: background-color 0.15s ease;
  min-width: 0;
}

.group-toggle-btn:hover {
  background-color: var(--color-surface-hover);
}

.group-toggle-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.group-identity {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-width: 0;
}

.group-chevron {
  color: var(--color-text-muted);
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.group-chevron.collapsed {
  transform: rotate(-90deg);
}

.group-title {
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.group-count {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-normal);
  flex-shrink: 0;
}

.group-totals {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  font-size: var(--font-size-sm);
  flex-shrink: 0;
}

.group-metric {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.metric-label {
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.metric-val {
  font-weight: var(--font-weight-medium);
  color: var(--color-text);
}

.group-metric.negative .metric-val {
  color: var(--color-danger);
  font-weight: var(--font-weight-semibold);
}

.group-actions {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding-right: var(--space-xs);
  flex-shrink: 0;
}

.btn-sm {
  padding: 4px 10px;
  font-size: var(--font-size-sm);
  border-radius: var(--radius-sm);
}

/* Category List Container */
.group-body {
  background-color: var(--color-surface);
}

.empty-group-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md) var(--space-lg);
  font-size: var(--font-size-sm);
}

.category-list {
  display: flex;
  flex-direction: column;
}

.category-row {
  display: flex;
  align-items: center;
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--color-border-subtle);
  gap: var(--space-sm);
  min-height: 48px;
  transition: background-color 0.12s ease;
}

.category-row:hover {
  background-color: var(--color-surface-hover);
}

.category-row:last-child {
  border-bottom: none;
}

.category-info {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex: 1;
  min-width: 140px;
}

.category-name {
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-base);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.type-badge {
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
  font-weight: var(--font-weight-bold);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  flex-shrink: 0;
  letter-spacing: 0.03em;
}

.type-badge.income {
  background-color: var(--color-success-bg);
  color: var(--color-success);
}

.type-badge.expense {
  background-color: var(--color-surface-hover);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.type-badge.transfer {
  background-color: var(--color-warning-bg);
  color: var(--color-warning);
}

.inactive-badge {
  font-size: var(--font-size-2xs);
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  font-weight: var(--font-weight-semibold);
  flex-shrink: 0;
}

.category-planned {
  width: 110px;
  flex-shrink: 0;
}

.amount-input-box {
  position: relative;
  display: flex;
  align-items: center;
}

.currency-symbol {
  position: absolute;
  left: 8px;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  pointer-events: none;
  font-family: var(--font-family-mono);
}

.amount-input {
  padding: 5px 8px 5px 18px;
  height: 32px;
  font-size: var(--font-size-sm);
  text-align: right;
}

.category-metric {
  width: 100px;
  text-align: right;
  font-size: var(--font-size-sm);
  flex-shrink: 0;
}

.category-remaining.negative {
  color: var(--color-danger);
  font-weight: var(--font-weight-semibold);
}

.metric-mobile-label {
  display: none;
}

.category-progress {
  width: 80px;
  flex-shrink: 0;
}

.progress-bar-bg {
  background: var(--color-border);
  height: 4px;
  border-radius: var(--radius-full);
  width: 100%;
  overflow: hidden;
}

.progress-bar-fill {
  background: var(--color-success);
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.25s ease;
}

.progress-bar-fill.over-budget {
  background: var(--color-danger);
}

.category-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  margin-left: var(--space-xs);
}

/* Modals & Dialogs */
.target-group-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  background-color: var(--color-primary-light);
  color: var(--color-primary);
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-md);
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

.status-toggle-wrapper {
  margin-bottom: var(--space-md);
}

.ghost {
  opacity: 0.4;
  background: var(--color-primary-light);
}

/* Responsive Adaptations */
@media (max-width: 850px) {
  .group-totals {
    gap: var(--space-sm);
  }
  .category-progress {
    display: none;
  }
}

@media (max-width: 680px) {
  .group-header {
    flex-wrap: wrap;
    padding: var(--space-sm);
  }
  .group-toggle-btn {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-xs);
    padding: var(--space-xs);
  }
  .group-totals {
    flex-wrap: wrap;
    gap: var(--space-sm);
  }
  .category-row {
    flex-wrap: wrap;
    gap: var(--space-xs);
    padding: var(--space-sm);
  }
  .category-info {
    width: 100%;
    flex: none;
  }
  .category-planned {
    width: 100px;
  }
  .metric-mobile-label {
    display: inline;
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
  }
}
</style>
