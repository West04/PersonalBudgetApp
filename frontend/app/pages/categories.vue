<template>
  <div class="categories-page">
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">Categories</h1>
        <input
          type="month"
          v-model="selectedMonth"
          class="month-picker"
        />
      </div>
      <button class="primary-btn" @click="addGroup">
        + Add Category Group
      </button>
    </header>

    <!-- Error Banner -->
    <div v-if="error" class="error-banner">
      {{ error }}
      <button class="close-btn" @click="error = null">x</button>
    </div>

    <!-- Loading State -->
    <div v-if="pending" class="loading-state">
      <div class="spinner"></div>
      <p>Loading categories...</p>
    </div>

    <template v-else>
      <!-- Summary Cards -->
      <section class="summary-cards">
        <div class="card summary-card income">
          <div class="card-label">Planned Income</div>
          <div class="card-value">{{ formatCurrency(totalIncomePlanned) }}</div>
          <div class="card-sub">Actual: {{ formatCurrency(totalIncomeActual) }}</div>
        </div>

        <div class="card summary-card expense">
          <div class="card-label">Planned Expenses</div>
          <div class="card-value">{{ formatCurrency(totalExpensePlanned) }}</div>
          <div class="card-sub">Actual: {{ formatCurrency(totalExpenseActual) }}</div>
        </div>

        <div class="card summary-card assign" :class="{ 'warning': toBeAssigned < 0 }">
          <div class="card-label">To Be Assigned</div>
          <div class="card-value">{{ formatCurrency(toBeAssigned) }}</div>
          <div class="card-sub" v-if="toBeAssigned === 0">Every dollar has a job!</div>
          <div class="card-sub" v-else-if="toBeAssigned > 0">You have money to budget</div>
          <div class="card-sub" v-else>You are over-budgeted!</div>
        </div>
      </section>

      <!-- Empty State -->
      <div v-if="!categoryGroups.length" class="empty-state">
        <div class="empty-icon">*</div>
        <h2>No categories yet</h2>
        <p>Create category groups to organize your budget.</p>
      </div>

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
          <div class="group-section" :class="{ 'is-collapsed': isGroupCollapsed(group.category_group_id) }">
            <!-- Group Row -->
            <div
              class="group-header"
              :class="{ 'expanded': expandedGroupId === group.category_group_id }"
            >
              <div class="group-header-left">
                <span class="drag-handle group-drag-handle" title="Drag to reorder">:::</span>

                <!-- Collapse Toggle -->
                <button
                  class="collapse-toggle"
                  @click="toggleGroupCollapse(group.category_group_id)"
                  title="Toggle categories"
                >
                  <svg
                    class="collapse-icon"
                    :class="{ 'collapsed': isGroupCollapsed(group.category_group_id) }"
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <polyline points="6 9 12 15 18 9"></polyline>
                  </svg>
                </button>

                <!-- Collapsed View -->
                <template v-if="expandedGroupId !== group.category_group_id">
                  <h2 class="group-title" @click="toggleGroupExpand(group.category_group_id)">
                    {{ group.name }}
                  </h2>
                </template>

                <!-- Expanded View (Edit Mode) -->
                <template v-else>
                  <input
                    type="text"
                    v-model="group.name"
                    @blur="saveGroup(group)"
                    @keydown.enter="($event.target as HTMLInputElement).blur()"
                    class="inline-input group-name-input"
                    placeholder="Group name"
                  />
                </template>
              </div>

              <div class="group-header-right">
                <!-- Collapsed: Show totals -->
                <template v-if="expandedGroupId !== group.category_group_id">
                  <div class="group-totals" @click="toggleGroupExpand(group.category_group_id)">
                    <span>Planned: {{ formatCurrency(getGroupTotalPlanned(group)) }}</span>
                    <span>Remaining: {{ formatCurrency(getGroupTotalRemaining(group)) }}</span>
                  </div>
                  <button class="icon-btn expand-btn" @click="toggleGroupExpand(group.category_group_id)" title="Edit group">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                    </svg>
                  </button>
                </template>

                <!-- Expanded: Show delete button -->
                <template v-else>
                  <button class="icon-btn delete-btn" @click="confirmDeleteGroup(group)" title="Delete group">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                  </button>
                  <button class="icon-btn done-btn" @click="toggleGroupExpand(null)" title="Done editing">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                  </button>
                </template>
              </div>
            </div>

            <!-- Category List -->
            <draggable
              v-show="!isGroupCollapsed(group.category_group_id)"
              v-model="group.categories"
              item-key="category_id"
              handle=".category-drag-handle"
              ghost-class="ghost"
              @end="onCategoryDragEnd(group)"
              class="category-list"
            >
              <template #item="{ element: category }">
                <div
                  class="category-row"
                  :class="{ 'expanded': expandedCategoryId === category.category_id }"
                >
                  <span class="drag-handle category-drag-handle" title="Drag to reorder">:::</span>

                  <!-- Collapsed View -->
                  <template v-if="expandedCategoryId !== category.category_id">
                    <div class="category-info" @click="toggleCategoryExpand(category.category_id)">
                      <span class="category-name">{{ category.name }}</span>
                      <span :class="['type-badge', category.type]">{{ category.type }}</span>
                      <span v-if="!category.is_active" class="inactive-badge">Inactive</span>
                    </div>
                    <div class="category-budget">
                      <div class="budget-numbers">
                        <span class="budget-planned">{{ formatCurrency(getCategoryPlanned(category)) }}</span>
                        <span class="budget-separator">/</span>
                        <span class="budget-actual">{{ formatCurrency(getCategoryActual(category)) }}</span>
                        <span
                          class="budget-remaining"
                          :class="{ 'negative': getCategoryRemaining(category) < 0 }"
                        >
                          ({{ formatCurrency(getCategoryRemaining(category)) }})
                        </span>
                      </div>
                      <div class="progress-bar-bg">
                        <div
                          class="progress-bar-fill"
                          :class="{ 'over-budget': getCategoryRemaining(category) < 0 }"
                          :style="{ width: calculateProgress(category) + '%' }"
                        ></div>
                      </div>
                    </div>
                    <button class="icon-btn expand-btn" @click.stop="toggleCategoryExpand(category.category_id)" title="Edit category">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                      </svg>
                    </button>
                  </template>

                  <!-- Expanded View (Edit Mode) -->
                  <template v-else>
                    <div class="category-edit-form">
                      <input
                        type="text"
                        v-model="category.name"
                        @blur="saveCategory(category)"
                        @keydown.enter="($event.target as HTMLInputElement).blur()"
                        class="inline-input category-name-input"
                        placeholder="Category name"
                      />
                      <select
                        v-model="category.type"
                        @change="saveCategory(category)"
                        class="inline-select"
                      >
                        <option value="expense">Expense</option>
                        <option value="income">Income</option>
                        <option value="transfer">Transfer</option>
                      </select>
                      <label class="active-toggle">
                        <input
                          type="checkbox"
                          v-model="category.is_active"
                          @change="saveCategory(category)"
                        />
                        <span>Active</span>
                      </label>
                      <div class="planned-input-group">
                        <span class="planned-input-label">Planned</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          :value="getCategoryPlanned(category)"
                          @blur="savePlannedAmount(category, ($event.target as HTMLInputElement).value)"
                          @keydown.enter="($event.target as HTMLInputElement).blur()"
                          class="inline-input planned-amount-input"
                          placeholder="0.00"
                        />
                      </div>
                    </div>
                    <div class="category-edit-actions">
                      <button class="icon-btn delete-btn" @click="confirmDeleteCategory(category)" title="Delete category">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                          <polyline points="3 6 5 6 21 6"></polyline>
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                      </button>
                      <button class="icon-btn done-btn" @click="toggleCategoryExpand(null)" title="Done editing">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                          <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                      </button>
                    </div>
                  </template>
                </div>
              </template>
            </draggable>

            <!-- Add Category Button -->
            <button
              v-show="!isGroupCollapsed(group.category_group_id)"
              class="add-category-btn"
              @click="addCategory(group)"
            >
              + Add Category
            </button>
          </div>
        </template>
      </draggable>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import draggable from 'vuedraggable'

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

// --- State ---
const getCurrentMonth = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

const selectedMonth = ref(getCurrentMonth())
const categoryGroups = ref<CategoryGroup[]>([])
const budgetSummary = ref<BudgetSummary | null>(null)
const pending = ref(true)
const error = ref<string | null>(null)

// Expansion state - only one expanded at a time
const expandedGroupId = ref<string | null>(null)
const expandedCategoryId = ref<string | null>(null)

// Collapse state for groups (to hide/show categories)
const collapsedGroups = ref<Record<string, boolean>>({})

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

// --- Budget Summary Helpers ---
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

// --- Computed Totals ---
const totalIncomePlanned = computed(() => budgetSummary.value?.total_income_planned ?? 0)
const totalIncomeActual = computed(() => budgetSummary.value?.total_income_actual ?? 0)
const totalExpensePlanned = computed(() => budgetSummary.value?.total_expense_planned ?? 0)
const totalExpenseActual = computed(() => budgetSummary.value?.total_expense_actual ?? 0)
const toBeAssigned = computed(() => budgetSummary.value?.to_be_assigned ?? 0)

// --- Collapse Toggle (show/hide categories) ---
const toggleGroupCollapse = (groupId: string) => {
  collapsedGroups.value[groupId] = !collapsedGroups.value[groupId]
}

const isGroupCollapsed = (groupId: string): boolean => {
  return !!collapsedGroups.value[groupId]
}

// --- Expansion Toggle (edit mode) ---
const toggleGroupExpand = (groupId: string | null) => {
  expandedCategoryId.value = null // Close any expanded category
  expandedGroupId.value = expandedGroupId.value === groupId ? null : groupId
}

const toggleCategoryExpand = (categoryId: string | null) => {
  expandedGroupId.value = null // Close any expanded group
  expandedCategoryId.value = expandedCategoryId.value === categoryId ? null : categoryId
}

// --- Drag and Drop ---
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

// --- Group Actions ---
const addGroup = async () => {
  const maxOrder = categoryGroups.value.reduce((max, g) => Math.max(max, g.sort_order), -1)
  try {
    const newGroup = await $fetch<CategoryGroup>(`${API_BASE}/category-groups`, {
      method: 'POST',
      body: {
        name: 'New Group',
        sort_order: maxOrder + 1
      }
    })
    // Add to local state with empty categories
    categoryGroups.value.push({ ...newGroup, categories: [] })
    // Expand for editing
    expandedGroupId.value = newGroup.category_group_id
  } catch (err: any) {
    error.value = 'Failed to create group'
  }
}

const saveGroup = async (group: CategoryGroup) => {
  try {
    await $fetch(`${API_BASE}/category-groups/${group.category_group_id}`, {
      method: 'PUT',
      body: {
        name: group.name,
        sort_order: group.sort_order
      }
    })
  } catch (err: any) {
    error.value = 'Failed to save group'
    await fetchData()
  }
}

const confirmDeleteGroup = async (group: CategoryGroup) => {
  if (group.categories.length > 0) {
    alert('Cannot delete a group that contains categories. Move or delete categories first.')
    return
  }
  if (!confirm(`Are you sure you want to delete "${group.name}"?`)) return

  try {
    await $fetch(`${API_BASE}/category-groups/${group.category_group_id}`, {
      method: 'DELETE'
    })
    categoryGroups.value = categoryGroups.value.filter(g => g.category_group_id !== group.category_group_id)
    expandedGroupId.value = null
  } catch (err: any) {
    error.value = 'Failed to delete group'
  }
}

// --- Category Actions ---
const addCategory = async (group: CategoryGroup) => {
  const maxOrder = group.categories.reduce((max, c) => Math.max(max, c.sort_order), -1)
  try {
    const newCategory = await $fetch<Category>(`${API_BASE}/categories`, {
      method: 'POST',
      body: {
        name: 'New Category',
        group_id: group.category_group_id,
        sort_order: maxOrder + 1,
        type: 'expense',
        is_active: true
      }
    })
    group.categories.push(newCategory)
    // Expand for editing
    expandedCategoryId.value = newCategory.category_id
  } catch (err: any) {
    error.value = 'Failed to create category'
  }
}

const saveCategory = async (category: Category) => {
  try {
    await $fetch(`${API_BASE}/categories/${category.category_id}`, {
      method: 'PUT',
      body: {
        name: category.name,
        type: category.type,
        is_active: category.is_active
      }
    })
  } catch (err: any) {
    error.value = 'Failed to save category'
    await fetchData()
  }
}

const savePlannedAmount = async (category: Category, rawValue: string) => {
  const amount = parseFloat(rawValue) || 0
  const budgetCat = getBudgetCategory(category.category_id)
  try {
    if (budgetCat?.budget_id) {
      await $fetch(`${API_BASE}/budget/${budgetCat.budget_id}`, {
        method: 'PUT',
        body: { planned_amount: amount }
      })
    } else {
      await $fetch(`${API_BASE}/budget`, {
        method: 'POST',
        body: {
          category_id: category.category_id,
          budget_month: `${selectedMonth.value}-01`,
          planned_amount: amount
        }
      })
    }
    // Refresh summary so totals and budget_id update
    const summaryRes = await $fetch<BudgetSummary>(`${API_BASE}/summary/budget`, { query: { month: selectedMonth.value } })
    budgetSummary.value = summaryRes
  } catch (err: any) {
    error.value = 'Failed to save planned amount'
  }
}

const confirmDeleteCategory = async (category: Category) => {
  if (!confirm(`Are you sure you want to delete "${category.name}"?`)) return

  try {
    await $fetch(`${API_BASE}/categories/${category.category_id}`, {
      method: 'DELETE'
    })
    // Remove from local state
    for (const group of categoryGroups.value) {
      const idx = group.categories.findIndex(c => c.category_id === category.category_id)
      if (idx !== -1) {
        group.categories.splice(idx, 1)
        break
      }
    }
    expandedCategoryId.value = null
  } catch (err: any) {
    error.value = 'Failed to delete category'
  }
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

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-title {
  margin: 0;
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--text-color);
}

.month-picker {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 1rem;
  color: var(--text-color);
  background: white;
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
}

.primary-btn:hover {
  opacity: 0.9;
}

.error-banner {
  background: #fee2e2;
  color: #dc2626;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.2rem;
  color: inherit;
  cursor: pointer;
  padding: 0 4px;
}

.loading-state, .empty-state {
  text-align: center;
  padding: 60px;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 16px;
}

.spinner {
  border: 3px solid #f3f3f3;
  border-top: 3px solid var(--accent-color);
  border-radius: 50%;
  width: 30px;
  height: 30px;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 24px;
  margin-bottom: 40px;
}

.card {
  background: white;
  padding: 24px;
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  border: 1px solid var(--border-color);
}

.card-label {
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}

.card-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-color);
  margin-bottom: 4px;
}

.card-sub {
  font-size: 0.9rem;
  color: var(--text-muted);
}

.summary-card.income .card-value { color: #10b981; }
.summary-card.expense .card-value { color: #f59e0b; }
.summary-card.assign .card-value { color: var(--accent-color); }
.summary-card.assign.warning .card-value { color: #ef4444; }

/* Groups List */
.groups-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.group-section {
  background: white;
  border-radius: 16px;
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.group-header {
  padding: 16px 20px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 60px;
  transition: background-color 0.2s;
}

.group-header:hover {
  background: #f1f5f9;
}

.group-header.expanded {
  background: #eff6ff;
}

.group-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.collapse-toggle {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  border-radius: 4px;
  transition: all 0.2s;
}

.collapse-toggle:hover {
  background: #e2e8f0;
  color: var(--text-color);
}

.collapse-icon {
  transition: transform 0.2s ease;
}

.collapse-icon.collapsed {
  transform: rotate(-90deg);
}

.group-section.is-collapsed .group-header {
  border-bottom: none;
}

.group-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.drag-handle {
  cursor: grab;
  color: var(--text-muted);
  font-weight: bold;
  font-size: 1rem;
  letter-spacing: -2px;
  user-select: none;
  padding: 4px;
}

.drag-handle:active {
  cursor: grabbing;
}

.group-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-color);
  cursor: pointer;
}

.group-totals {
  font-size: 0.9rem;
  color: var(--text-muted);
  display: flex;
  gap: 16px;
  cursor: pointer;
}

.inline-input {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 1rem;
  background: white;
}

.inline-input:focus {
  outline: none;
  border-color: var(--accent-color);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.group-name-input {
  width: 250px;
  font-weight: 600;
}

.inline-select {
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 0.9rem;
  background: white;
}

.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.icon-btn:hover {
  background: #e2e8f0;
  color: var(--text-color);
}

.icon-btn.delete-btn:hover {
  background: #fee2e2;
  color: #dc2626;
}

.icon-btn.done-btn:hover {
  background: #dcfce7;
  color: #166534;
}

/* Category List */
.category-list {
  display: flex;
  flex-direction: column;
}

.category-row {
  display: flex;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid #f1f5f9;
  gap: 12px;
  min-height: 54px;
  transition: background-color 0.2s;
}

.category-row:hover {
  background: #fafafa;
}

.category-row.expanded {
  background: #eff6ff;
}

.category-row:last-child {
  border-bottom: none;
}

.category-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  cursor: pointer;
  min-width: 0;
}

.category-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.type-badge {
  font-size: 0.65rem;
  text-transform: uppercase;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.type-badge.income {
  background: #dcfce7;
  color: #166534;
}

.type-badge.expense {
  background: #f1f5f9;
  color: #475569;
}

.type-badge.transfer {
  background: #fef9c3;
  color: #854d0e;
}

.inactive-badge {
  font-size: 0.65rem;
  background: #fee2e2;
  color: #991b1b;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.category-budget {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 200px;
}

.budget-numbers {
  display: flex;
  gap: 4px;
  font-size: 0.9rem;
  font-variant-numeric: tabular-nums;
  justify-content: flex-end;
}

.budget-planned {
  color: var(--text-color);
  font-weight: 500;
}

.budget-separator {
  color: var(--text-muted);
}

.budget-actual {
  color: var(--text-muted);
}

.budget-remaining {
  color: var(--text-muted);
  font-size: 0.85rem;
}

.budget-remaining.negative {
  color: #ef4444;
}

.progress-bar-bg {
  background: #e2e8f0;
  height: 4px;
  border-radius: 2px;
  width: 100%;
  overflow: hidden;
}

.progress-bar-fill {
  background: #10b981;
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.progress-bar-fill.over-budget {
  background: #ef4444;
}

/* Category Edit Form */
.category-edit-form {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.category-name-input {
  width: 180px;
}

.active-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.9rem;
  color: var(--text-muted);
  cursor: pointer;
}

.active-toggle input {
  cursor: pointer;
}

.planned-input-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.planned-input-label {
  font-size: 0.85rem;
  color: var(--text-muted);
  white-space: nowrap;
}

.planned-amount-input {
  width: 110px;
}

.category-edit-actions {
  display: flex;
  gap: 4px;
}

/* Add Category Button */
.add-category-btn {
  width: 100%;
  padding: 12px 20px;
  background: none;
  border: none;
  border-top: 1px solid #f1f5f9;
  color: var(--accent-color);
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.2s;
}

.add-category-btn:hover {
  background: #f8fafc;
}

/* Drag Ghost */
.ghost {
  opacity: 0.5;
  background: #c8ebfb;
}
</style>
