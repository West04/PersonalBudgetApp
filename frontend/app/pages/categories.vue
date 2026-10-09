<template>
  <div class="categories-page page-container">
    <PageHeader title="Budget" subtitle="Assign planned income to categories and track activity against the plan">
      <template #controls>
        <MonthNavigator />
      </template>
      <template #actions>
        <button type="button" class="btn btn-primary" @click="openAddGroupModal">
          <AppIcon name="plus" :size="16" />
          Add group
        </button>
      </template>
    </PageHeader>

    <!-- Error Banner -->
    <ErrorBanner :error="error" @dismiss="error = null" />

    <!-- Loading State -->
    <LoadingState v-if="pending" message="Loading budget..." />

    <!-- First load failed: no budget data to show, so do not render a $0.00 budget -->
    <EmptyState
      v-else-if="loadFailed"
      title="Budget not loaded"
      description="The budget for this month could not be loaded. Try again, or pick another month."
    >
      <template #actions>
        <button type="button" class="btn btn-secondary" @click="fetchData">Try again</button>
      </template>
    </EmptyState>

    <template v-else>
      <!-- Summary: the zero-based equation, income - expenses = to be assigned.
           Every figure comes straight from /summary/budget. -->
      <section class="budget-summary" aria-labelledby="heading-budget-summary">
        <h2 id="heading-budget-summary" class="sr-only">Monthly budget summary</h2>
        <dl class="budget-equation">
          <div class="eq-term eq-term--income">
            <dt class="eq-label">Planned income</dt>
            <dd class="eq-value"><Money :amount="totalIncomePlanned" /></dd>
            <dd class="eq-note">Received <Money :amount="totalIncomeActual" /></dd>
          </div>

          <div class="eq-term eq-term--expense">
            <dt class="eq-label">Planned expenses</dt>
            <dd class="eq-value"><Money :amount="totalExpensePlanned" /></dd>
            <dd class="eq-note">Spent <Money :amount="totalExpenseActual" /></dd>
          </div>

          <div class="eq-term eq-term--assign" :class="`tba--${tbaState}`">
            <dt class="eq-label">To be assigned</dt>
            <dd class="eq-value eq-value--lead">
              <Money
                :amount="toBeAssigned"
                sign="never"
                :tone="tbaState === 'over' ? 'overspent' : tbaState === 'unassigned' ? 'available' : 'neutral'"
              />
            </dd>
            <dd class="eq-note tba-status">
              <template v-if="tbaState === 'over'">Over-assigned: planned expenses exceed planned income</template>
              <template v-else-if="tbaState === 'unassigned'">Left to assign to categories</template>
              <template v-else>Every dollar has a job</template>
            </dd>
          </div>
        </dl>
      </section>

      <!-- Empty State -->
      <EmptyState
        v-if="!categoryGroups.length"
        title="No category groups yet"
        description="Create category groups to organize your budget and allocate planned spending."
      >
        <template #actions>
          <button type="button" class="btn btn-primary" @click="openAddGroupModal">
            <AppIcon name="plus" :size="16" />
            Add group
          </button>
        </template>
      </EmptyState>

      <!-- Budget ledger: one surface, fixed numeric tracks so every group aligns -->
      <div v-else class="ledger surface-card">
        <div class="ledger-head ledger-grid" aria-hidden="true">
          <span class="col-name">Category</span>
          <span class="col-planned">Planned</span>
          <span class="col-activity">Activity</span>
          <span class="col-remaining">Remaining</span>
          <span class="col-status">Progress</span>
        </div>

        <!-- Draggable Group List -->
        <draggable
          v-model="categoryGroups"
          item-key="category_group_id"
          handle=".group-drag-handle"
          ghost-class="ghost"
          @end="onGroupDragEnd"
          class="groups-list"
        >
          <template #item="{ element: group }">
            <section
              class="group-section"
              :class="{ 'is-collapsed': isGroupCollapsed(group.category_group_id) }"
              :aria-label="group.name"
            >
              <!-- Group Header -->
              <div class="group-header ledger-grid">
                <span
                  class="drag-handle group-drag-handle"
                  title="Drag to reorder group"
                  aria-label="Drag group to reorder"
                  tabindex="-1"
                ><AppIcon name="grip" :size="16" /></span>

                <div class="group-name-cell">
                  <h2 class="group-heading">
                    <button
                      type="button"
                      class="group-toggle-btn"
                      :aria-expanded="!isGroupCollapsed(group.category_group_id)"
                      :aria-controls="`group-categories-${group.category_group_id}`"
                      :aria-label="`${group.name} group, ${isGroupCollapsed(group.category_group_id) ? 'collapsed' : 'expanded'}`"
                      @click="toggleGroupCollapse(group.category_group_id)"
                    >
                      <AppIcon
                        name="chevron"
                        :size="16"
                        class="group-chevron"
                        :class="{ 'collapsed': isGroupCollapsed(group.category_group_id) }"
                      />
                      <span class="group-title" :title="group.name">{{ group.name }}</span>
                    </button>
                  </h2>
                  <p class="group-meta" :title="groupKind(group) === 'mixed' ? 'Group totals add every category in the group, whatever its type' : undefined">
                    {{ groupMetaLabel(group) }}
                  </p>
                </div>

                <!-- Group totals: existing per-category sums, aligned under the category columns.
                     Pointer convenience only; the heading button is the keyboard toggle. -->
                <div class="group-totals row-figures" @click="toggleGroupCollapse(group.category_group_id)">
                  <span class="cell cell-planned">
                    <span class="cell-label">Planned</span>
                    <Money :amount="getGroupTotalPlanned(group)" />
                  </span>
                  <span class="cell cell-activity">
                    <span class="cell-label">Activity</span>
                    <Money :amount="getGroupTotalActual(group)" />
                  </span>
                  <span class="cell cell-remaining">
                    <span class="cell-label">Remaining</span>
                    <Money
                      :amount="getGroupTotalRemaining(group)"
                      :tone="groupRemainingTone(group)"
                    />
                  </span>
                </div>

                <!-- Group Actions -->
                <div class="group-actions">
                  <button
                    type="button"
                    class="btn-icon add-category-btn"
                    @click="openAddCategoryModal(group)"
                    :aria-label="`Add category to ${group.name}`"
                    title="Add category"
                  >
                    <AppIcon name="plus" :size="16" />
                    <span class="add-category-text" aria-hidden="true">Add category</span>
                  </button>
                  <span class="icon-actions">
                    <button
                      type="button"
                      class="btn-icon"
                      @click="openEditGroupModal(group)"
                      :aria-label="`Edit ${group.name} group`"
                      title="Edit group"
                    >
                      <AppIcon name="edit" :size="16" />
                    </button>
                    <button
                      type="button"
                      class="btn-icon btn-icon-danger"
                      @click="confirmDeleteGroup(group)"
                      :aria-label="`Delete ${group.name} group`"
                      title="Delete group"
                    >
                      <AppIcon name="trash" :size="16" />
                    </button>
                  </span>
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
                  <p>No categories in this group yet.</p>
                  <button
                    type="button"
                    class="btn btn-secondary btn-sm"
                    @click="openAddCategoryModal(group)"
                  >
                    <AppIcon name="plus" :size="14" />
                    Add first category
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
                    <div
                      class="category-row ledger-grid"
                      :class="[
                        `is-${categoryStatus(category).kind}`,
                        { 'is-inactive': !category.is_active }
                      ]"
                    >
                      <span
                        class="drag-handle category-drag-handle"
                        title="Drag to reorder category"
                        aria-label="Drag category to reorder"
                        tabindex="-1"
                      ><AppIcon name="grip" :size="16" /></span>

                      <!-- Info: name, plus type/inactive as quiet text (expense is the default) -->
                      <div class="category-info">
                        <span class="category-name" :title="category.name">{{ category.name }}</span>
                        <span v-if="categoryMetaLabel(category)" class="category-meta">{{ categoryMetaLabel(category) }}</span>
                      </div>

                      <div class="row-figures">
                        <!-- Planned Amount Input -->
                        <div class="cell cell-planned category-planned">
                          <span class="cell-label" aria-hidden="true">Planned</span>
                          <label :for="`planned-${category.category_id}`" class="sr-only">
                            Planned amount for {{ category.name }}
                          </label>
                          <div class="amount-input-box">
                            <span class="currency-symbol" aria-hidden="true">$</span>
                            <input
                              :id="`planned-${category.category_id}`"
                              type="number"
                              inputmode="decimal"
                              min="0"
                              step="0.01"
                              :value="formatPlannedInput(getCategoryPlanned(category))"
                              @change="onPlannedAmountChange(category, ($event.target as HTMLInputElement).value)"
                              @keydown.enter="($event.target as HTMLInputElement).blur()"
                              @keydown.escape="revertPlannedAmount(category, $event.target as HTMLInputElement)"
                              class="form-input num amount-input"
                              placeholder="0.00"
                            />
                          </div>
                        </div>

                        <!-- Activity / Actual -->
                        <span class="cell cell-activity category-actual" :class="{ 'is-zero': getCategoryActual(category) === 0 }">
                          <span class="cell-label">Activity</span>
                          <Money :amount="getCategoryActual(category)" :tone="categoryActivityTone(category)" />
                        </span>

                        <!-- Remaining -->
                        <span class="cell cell-remaining category-remaining" :class="{ 'is-zero': getCategoryRemaining(category) === 0 }">
                          <span class="cell-label">Remaining</span>
                          <Money :amount="getCategoryRemaining(category)" :tone="categoryRemainingTone(category)" />
                        </span>
                      </div>

                      <!-- Progress: text carries the meaning; the bar is a visual aid -->
                      <div class="category-progress">
                        <div
                          v-if="categoryStatus(category).showBar"
                          class="progress-track"
                          aria-hidden="true"
                        >
                          <div
                            class="progress-fill"
                            :class="{ 'over-budget': categoryStatus(category).kind === 'over' }"
                            :style="{ width: calculateProgress(category) + '%' }"
                          ></div>
                        </div>
                        <span class="status-text">{{ categoryStatus(category).label }}</span>
                      </div>

                      <!-- Actions -->
                      <div class="category-actions">
                        <button
                          type="button"
                          class="btn-icon"
                          @click="openEditCategoryModal(category)"
                          :aria-label="`Edit ${category.name}`"
                          title="Edit category"
                        >
                          <AppIcon name="edit" :size="16" />
                        </button>
                        <button
                          type="button"
                          class="btn-icon btn-icon-danger"
                          @click="confirmDeleteCategory(category)"
                          :aria-label="`Delete ${category.name}`"
                          title="Delete category"
                        >
                          <AppIcon name="trash" :size="16" />
                        </button>
                      </div>
                    </div>
                  </template>
                </draggable>
              </div>
            </section>
          </template>
        </draggable>
      </div>
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
            class="form-input num"
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
            class="form-input num"
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
import type { MoneyTone } from '~/utils/money'

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

// After loading, a missing summary means the fetch failed; later save errors keep the page visible
const loadFailed = computed(() => !budgetSummary.value)

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
  inputEl.value = formatPlannedInput(getCategoryPlanned(category))
  inputEl.blur()
}

// Shows the stored planned amount with cents so the input scans like the other figures.
// Display only: parsing and saving above are unchanged.
const formatPlannedInput = (amount: number): string => amount.toFixed(2)

// --- Presentation states ---
// These only choose wording and tone for values the API already supplied
// (planned, actual, remaining, is_over_budget). Nothing here recalculates a figure.

const tbaState = computed<'unassigned' | 'over' | 'assigned'>(() => {
  if (toBeAssigned.value > 0) return 'unassigned'
  if (toBeAssigned.value < 0) return 'over'
  return 'assigned'
})

type GroupKind = 'expense' | 'income' | 'transfer' | 'mixed' | 'empty'

const groupKind = (group: CategoryGroup): GroupKind => {
  const types = new Set(group.categories.map(c => c.type))
  if (types.size === 0) return 'empty'
  if (types.size > 1) return 'mixed'
  return [...types][0] as GroupKind
}

const groupMetaLabel = (group: CategoryGroup): string => {
  const count = group.categories.length
  const noun = count === 1 ? 'category' : 'categories'
  switch (groupKind(group)) {
    case 'empty': return 'No categories'
    case 'income': return `${count} income ${noun}`
    case 'transfer': return `${count} transfer ${noun}`
    case 'mixed': return `${count} ${noun}, mixed types`
    default: return `${count} ${noun}`
  }
}

// Group totals add every category regardless of type, so a negative sum only means
// "over plan" when the group holds spending categories alone.
const groupRemainingTone = (group: CategoryGroup): MoneyTone => {
  const kind = groupKind(group)
  if ((kind === 'expense' || kind === 'transfer') && getGroupTotalRemaining(group) < 0) return 'overspent'
  return 'neutral'
}

const categoryMetaLabel = (category: Category): string => {
  const parts: string[] = []
  if (category.type === 'income') parts.push('Income')
  if (category.type === 'transfer') parts.push('Transfer')
  if (!category.is_active) parts.push(parts.length ? 'inactive' : 'Inactive')
  return parts.join(', ')
}

const isCategoryOverBudget = (category: Category): boolean =>
  !!getBudgetCategory(category.category_id)?.is_over_budget

type CategoryStatusKind = 'over' | 'unplanned' | 'refund' | 'full' | 'within' | 'received' | 'none'

const categoryStatus = (category: Category): { kind: CategoryStatusKind; label: string; showBar: boolean } => {
  const planned = getCategoryPlanned(category)
  const actual = getCategoryActual(category)
  const remaining = getCategoryRemaining(category)
  const pct = Math.round(calculateProgress(category))
  const refundLabel = category.type === 'transfer' ? 'Net inflow' : 'Net refund'

  if (category.type === 'income') {
    // Income: actual is money received; remaining is what is still expected
    if (planned === 0) return actual > 0
      ? { kind: 'received', label: 'Unplanned', showBar: false }
      : { kind: 'none', label: 'No plan', showBar: false }
    if (remaining < 0) return { kind: 'received', label: 'Above plan', showBar: true }
    if (remaining === 0) return { kind: 'received', label: 'Received', showBar: true }
    return { kind: 'within', label: `${pct}% received`, showBar: true }
  }

  if (planned === 0) {
    if (isCategoryOverBudget(category)) return { kind: 'unplanned', label: 'Unplanned', showBar: false }
    if (actual < 0) return { kind: 'refund', label: refundLabel, showBar: false }
    return { kind: 'none', label: 'No plan', showBar: false }
  }
  if (isCategoryOverBudget(category)) return { kind: 'over', label: 'Over plan', showBar: true }
  if (actual < 0) return { kind: 'refund', label: refundLabel, showBar: false }
  if (remaining === 0) return { kind: 'full', label: 'Fully spent', showBar: true }
  return { kind: 'within', label: `${pct}% spent`, showBar: true }
}

const categoryActivityTone = (category: Category): MoneyTone => {
  const actual = getCategoryActual(category)
  if (category.type === 'income') return actual === 0 ? 'neutral' : 'inflow'
  // A negative expense actual is a net refund: money coming back, not an error
  if (category.type === 'expense' && actual < 0) return 'inflow'
  return 'neutral'
}

const categoryRemainingTone = (category: Category): MoneyTone => {
  // Income remaining is money still expected, not money available to spend
  if (category.type === 'income') return 'neutral'
  if (isCategoryOverBudget(category)) return 'overspent'
  return getCategoryRemaining(category) > 0 ? 'available' : 'neutral'
}
</script>

<style scoped>
/* Summary: the zero-based equation ------------------------------------------ */

.budget-summary {
  container: summary / inline-size;
  margin-bottom: var(--space-lg);
}

.budget-equation {
  margin: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.3fr);
  border-top: 1px solid var(--border-default);
  border-bottom: 1px solid var(--border-default);
}

.eq-term {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: var(--space-md) var(--space-lg);
  border-left: 1px solid var(--border-subtle);
}

.eq-term dd {
  margin: 0;
}

.eq-term--income {
  padding-left: 0;
  border-left: 0;
}

/* The operators sit on the dividers: income - expenses = to be assigned */
.eq-term--expense::before,
.eq-term--assign::before {
  position: absolute;
  top: 50%;
  left: 0;
  transform: translate(-50%, -50%);
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  background: var(--bg-page);
  color: var(--text-muted);
  font-size: 1rem;
  line-height: 1;
}

.eq-term--expense::before {
  content: "\2212" / "";
}

.eq-term--assign::before {
  content: "=" / "";
}

.eq-term--assign {
  padding-left: calc(var(--space-lg) + 4px);
  background: var(--bg-surface);
  border-left-color: var(--border-default);
  box-shadow: inset 0 3px 0 var(--border-strong);
}

.eq-term--assign.tba--unassigned {
  box-shadow: inset 0 3px 0 var(--financial-available);
}

.eq-term--assign.tba--over {
  box-shadow: inset 0 3px 0 var(--financial-overspent);
}

.eq-label {
  font-size: var(--type-label-size);
  font-weight: var(--type-label-weight);
  color: var(--text-secondary);
}

.eq-term .eq-value {
  margin-top: var(--space-xs);
  font-size: 1.375rem;
  font-weight: var(--type-metric-weight);
  letter-spacing: -0.015em;
  line-height: var(--line-height-tight);
  overflow-wrap: anywhere;
}

.eq-term .eq-value--lead {
  font-size: clamp(1.625rem, 1.2rem + 2cqi, 2.125rem);
  letter-spacing: -0.025em;
}

.eq-note {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.eq-note .money {
  color: var(--text-secondary);
}

.tba--unassigned .tba-status {
  color: var(--financial-available);
  font-weight: var(--font-weight-medium);
}

.tba--over .tba-status {
  color: var(--financial-overspent);
  font-weight: var(--font-weight-medium);
}

@container summary (max-width: 560px) {
  .budget-equation {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .eq-term {
    padding: var(--space-sm) 0 var(--space-sm) var(--space-md);
  }

  .eq-term--income {
    padding-left: 0;
  }

  .eq-term--assign {
    grid-column: 1 / -1;
    padding: var(--space-md);
    border-left: 0;
    border-top: 1px solid var(--border-default);
  }

  .eq-term--assign::before {
    top: 0;
    left: 50%;
  }
}

/* Ledger -------------------------------------------------------------------- */
/* One surface. Every row uses the same fixed numeric tracks, so group headers
   and category rows line up across groups. Three tiers by ledger width:
   stacked (< 660px), compact (660-779px), full (>= 780px).
   Tracks: handle 1.5rem, planned 7.25rem, activity/remaining 6.5rem,
   progress 9rem, actions 4.25rem (6.25rem compact, where group actions merge). */

.ledger {
  container: ledger / inline-size;
  overflow: hidden;
}

.ledger-grid {
  display: grid;
  grid-template-columns: 1.5rem minmax(0, 1fr) auto;
  column-gap: 10px;
  row-gap: 6px;
  align-items: center;
  padding: 10px var(--space-sm) 10px var(--space-xs);
}

.ledger-head {
  display: none;
  padding-top: var(--space-sm);
  padding-bottom: var(--space-sm);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-default);
}

.ledger-head .col-planned,
.ledger-head .col-activity,
.ledger-head .col-remaining {
  text-align: right;
}

.groups-list {
  display: flex;
  flex-direction: column;
}

/* Group header -------------------------------------------------------------- */

.group-section + .group-section .group-header {
  border-top: 1px solid var(--border-default);
}

.group-header {
  grid-template-areas:
    "handle name actions"
    "handle figures figures";
  background: var(--bg-sunken);
  border-bottom: 1px solid var(--border-subtle);
}

.group-section.is-collapsed .group-header {
  border-bottom: 0;
}

.group-drag-handle { grid-area: handle; }
.group-name-cell { grid-area: name; }
.group-actions { grid-area: actions; }

.group-name-cell {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.group-heading {
  display: flex;
  min-width: 0;
  margin: 0;
  font: inherit;
}

.group-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  margin-left: -4px;
  padding: 2px 6px 2px 4px;
  background: transparent;
  border: 0;
  border-radius: var(--radius-xs);
  cursor: pointer;
  font-family: var(--font-display);
  font-size: var(--type-subheading-size);
  font-weight: var(--font-weight-semibold);
  line-height: var(--line-height-tight);
  color: var(--text-primary);
  text-align: left;
}

.group-toggle-btn:hover {
  background: var(--bg-subtle);
}

.group-chevron {
  color: var(--text-muted);
  transition: transform 0.15s ease;
}

.group-chevron.collapsed {
  transform: rotate(-90deg);
}

.group-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-meta {
  margin: 1px 0 0 22px;
  font-size: var(--type-meta-size);
  line-height: var(--line-height-tight);
  color: var(--text-muted);
}

.group-totals {
  cursor: pointer;
}

.group-totals .money {
  font-weight: var(--font-weight-semibold);
}

.group-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}

.icon-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.add-category-text {
  display: none;
}

/* Category rows ------------------------------------------------------------- */

.category-row {
  grid-template-areas:
    "handle name actions"
    "handle figures figures"
    "handle status status";
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  transition: background-color 0.12s ease;
}

.category-list > .category-row:last-child {
  border-bottom: 0;
}

.category-row:hover {
  background: var(--table-hover);
}

/* Over plan or unplanned spending: a quiet rule on the leading edge, named in text */
.category-row.is-over,
.category-row.is-unplanned {
  box-shadow: inset 2px 0 0 var(--financial-overspent);
}

.category-drag-handle { grid-area: handle; }
.category-info { grid-area: name; }
.category-actions { grid-area: actions; }
.category-progress { grid-area: status; }

.category-info {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
  min-width: 0;
}

.category-name {
  min-width: 0;
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.category-meta {
  flex-shrink: 0;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

/* Inactive is a quieter state, not an error */
.category-row.is-inactive .category-name {
  color: var(--text-secondary);
  font-weight: var(--font-weight-regular);
}

.category-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}

.category-actions .btn-icon,
.group-actions .btn-icon {
  color: var(--text-muted);
}

.category-actions .btn-icon:hover:not(:disabled),
.group-actions .btn-icon:hover:not(:disabled) {
  color: var(--text-primary);
}

.category-actions .btn-icon-danger:hover:not(:disabled),
.group-actions .btn-icon-danger:hover:not(:disabled),
.btn-icon-danger:focus-visible {
  color: var(--status-error);
}

/* Figures -------------------------------------------------------------------- */

.row-figures {
  grid-area: figures;
  display: grid;
  /* Planned gets a little extra room for the input; group totals use the same tracks */
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) minmax(0, 1fr);
  column-gap: 10px;
}

.cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  min-width: 0;
  text-align: right;
}

.cell .money {
  font-size: var(--type-body-size);
}

.category-remaining .money {
  font-weight: var(--font-weight-medium);
}

.cell.is-zero .money {
  color: var(--text-muted);
}

/* Labels show in the stacked layout; elsewhere the ledger head names the column */
.cell-label {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  line-height: var(--line-height-tight);
  margin-bottom: 2px;
}

.category-planned {
  align-items: stretch;
}

.category-planned .cell-label {
  text-align: right;
}

.amount-input-box {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
}

.currency-symbol {
  position: absolute;
  left: 8px;
  color: var(--text-muted);
  font-size: var(--type-meta-size);
  pointer-events: none;
}

/* Reads as a figure at rest; the border firms up on hover and focus */
.amount-input {
  height: 32px;
  padding: 4px 8px 4px 20px;
  font-size: var(--type-body-size);
  font-weight: var(--font-weight-medium);
  text-align: right;
  background-color: transparent;
  border-color: var(--border-subtle);
  -moz-appearance: textfield;
  appearance: textfield;
}

.amount-input::-webkit-outer-spin-button,
.amount-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.category-row:hover .amount-input,
.amount-input:hover:not(:disabled) {
  background-color: var(--input-bg);
  border-color: var(--border-strong);
}

.amount-input:focus {
  background-color: var(--input-bg);
  border-color: var(--accent-primary);
}

/* Progress -------------------------------------------------------------------- */

.category-progress {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-width: 0;
}

.progress-track {
  flex: 1;
  min-width: 2rem;
  height: 6px;
  background: var(--bg-subtle);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  max-width: 100%;
  background: var(--text-muted);
  border-radius: var(--radius-full);
}

.progress-fill.over-budget {
  background: var(--financial-overspent);
}

.status-text {
  flex-shrink: 0;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  white-space: nowrap;
}

.category-row.is-over .status-text,
.category-row.is-unplanned .status-text {
  color: var(--financial-overspent);
  font-weight: var(--font-weight-medium);
}

.category-row.is-refund .status-text {
  color: var(--financial-inflow);
}

.category-row.is-full .status-text,
.category-row.is-received .status-text {
  color: var(--text-secondary);
}

/* Drag handles ---------------------------------------------------------------- */

.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: stretch;
  color: var(--text-disabled);
  cursor: grab;
  user-select: none;
  touch-action: none;
  border-radius: var(--radius-xs);
}

.drag-handle:hover {
  color: var(--text-secondary);
  background: var(--bg-subtle);
}

.drag-handle:active {
  cursor: grabbing;
}

.ghost {
  opacity: 0.5;
  background: var(--accent-subtle) !important;
}

/* Empty group ------------------------------------------------------------------ */

.empty-group-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-sm) var(--space-md);
  padding: var(--space-md) var(--space-md) var(--space-md) calc(1.5rem + 10px + var(--space-xs));
  background: var(--bg-surface);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.empty-group-body p {
  margin: 0;
}

/* Stacked tier: touch-sized controls */
@container ledger (max-width: 659px) {
  .category-actions .btn-icon,
  .group-actions .btn-icon {
    min-width: 36px;
    min-height: 36px;
  }

  .ledger-grid {
    padding-top: var(--space-sm);
    padding-bottom: var(--space-sm);
  }

  .amount-input {
    padding-left: 16px;
    padding-right: 6px;
  }

  .currency-symbol {
    left: 6px;
  }
}

/* Compact tier ------------------------------------------------------------------ */
@container ledger (min-width: 660px) {
  .ledger-grid {
    grid-template-columns:
      1.5rem
      minmax(8.5rem, 1fr)
      7.25rem
      6.5rem
      6.5rem
      6.25rem;
    padding: 8px var(--space-sm) 8px var(--space-xs);
  }

  .ledger-head {
    display: grid;
  }

  .ledger-head .col-name { grid-column: 2; }
  .ledger-head .col-status { display: none; }

  .row-figures {
    display: contents;
  }

  .cell-planned { grid-area: planned; }
  .cell-activity { grid-area: activity; }
  .cell-remaining { grid-area: remaining; }

  .cell-label {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .group-header {
    grid-template-areas: "handle name planned activity remaining actions";
  }

  /* Status moves under the category name; the bar returns at full width */
  .category-row {
    grid-template-areas:
      "handle name planned activity remaining actions"
      "handle status planned activity remaining actions";
    row-gap: 0;
  }

  .category-progress {
    align-self: start;
  }

  .category-progress .progress-track {
    display: none;
  }
}

/* Full tier --------------------------------------------------------------------- */
@container ledger (min-width: 780px) {
  .ledger-grid {
    grid-template-columns:
      1.5rem
      minmax(8.5rem, 1fr)
      7.25rem
      6.5rem
      6.5rem
      9rem
      4.25rem;
    column-gap: 12px;
  }

  .ledger-head .col-status { display: block; }

  .group-header {
    grid-template-areas: "handle name planned activity remaining status actions";
  }

  .category-row {
    grid-template-areas: "handle name planned activity remaining status actions";
    min-height: 48px;
  }

  .category-progress {
    align-self: center;
  }

  .category-progress .progress-track {
    display: block;
  }

  .status-text {
    min-width: 5.25rem;
  }

  /* Group actions split: "Add category" sits in the progress column,
     edit and delete line up with the category row actions */
  .group-actions {
    display: contents;
  }

  .add-category-btn {
    grid-area: status;
    justify-self: start;
    gap: 6px;
    padding: 4px 8px 4px 6px;
    font-size: var(--type-meta-size);
    font-weight: var(--font-weight-medium);
  }

  .group-actions .add-category-btn {
    color: var(--accent-text);
  }

  .group-actions .add-category-btn:hover:not(:disabled) {
    color: var(--accent-hover);
    background: var(--accent-subtle);
  }

  .add-category-text {
    display: inline;
  }

  .icon-actions {
    grid-area: actions;
    justify-self: end;
  }
}

/* Dialogs ------------------------------------------------------------------------- */

.target-group-badge {
  display: flex;
  align-items: baseline;
  gap: var(--space-xs);
  margin-bottom: var(--space-md);
  font-size: var(--type-meta-size);
  color: var(--text-secondary);
}

.target-group-name {
  color: var(--text-primary);
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

.status-toggle-wrapper {
  margin-bottom: var(--space-md);
}

@media (max-width: 480px) {
  .field-row {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
