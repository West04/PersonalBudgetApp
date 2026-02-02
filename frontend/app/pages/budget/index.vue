<template>
  <div class="page-container">
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">Budget</h1>
        <input
          type="month"
          v-model="selectedMonth"
          class="month-picker"
        />
      </div>
    </header>

    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <p>Loading budget...</p>
    </div>

    <div v-else-if="loadError" class="error-state">
      <p>Error loading budget: {{ loadError }}</p>
      <button @click="fetchData" class="btn btn-secondary">Retry</button>
    </div>

    <div v-else class="content-area">
      <!-- Summary Cards -->
      <section class="summary-cards">
        <div class="card summary-card income">
          <div class="card-label">Planned Income</div>
          <div class="card-value">{{ formatCurrency(totalIncome) }}</div>
          <div class="card-sub">Actual: {{ formatCurrency(totalIncomeActual) }}</div>
        </div>

        <div class="card summary-card expense">
          <div class="card-label">Planned Expenses</div>
          <div class="card-value">{{ formatCurrency(totalExpenses) }}</div>
          <div class="card-sub">Actual: {{ formatCurrency(totalExpensesActual) }}</div>
        </div>

        <div class="card summary-card assign" :class="{ 'warning': toBeAssigned < 0 }">
          <div class="card-label">To Be Assigned</div>
          <div class="card-value">{{ formatCurrency(toBeAssigned) }}</div>
          <div class="card-sub" v-if="toBeAssigned === 0">Every dollar has a job!</div>
          <div class="card-sub" v-else-if="toBeAssigned > 0">You have money to budget</div>
          <div class="card-sub" v-else>You are over-budgeted!</div>
        </div>
      </section>

      <!-- Budget Groups -->
      <div class="budget-groups">
        <div v-for="group in budgetGroups" :key="group.group_id" class="group-section" :class="{ 'is-collapsed': collapsedGroups[group.group_id] }">
          <div
            class="group-header"
            @click="toggleGroup(group.group_id)"
          >
            <div class="group-header-left">
              <svg
                class="collapse-icon"
                :class="{ 'collapsed': collapsedGroups[group.group_id] }"
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
              <h2 class="group-title">{{ group.name }}</h2>
            </div>
            <div class="group-totals">
              <span>Planned: {{ formatCurrency(groupTotalPlanned(group)) }}</span>
              <span>Remaining: {{ formatCurrency(groupTotalRemaining(group)) }}</span>
            </div>
          </div>

          <div class="category-list" v-show="!collapsedGroups[group.group_id]">
            <div class="category-header-row">
              <span class="col-name">Category</span>
              <span class="col-numeric">Planned</span>
              <span class="col-numeric">Actual</span>
              <span class="col-numeric">Remaining</span>
            </div>

            <div v-for="cat in group.categories" :key="cat.category_id" class="category-row">
              <div class="col-name">
                <div class="cat-name">{{ cat.name }}</div>
                <!-- Progress Bar -->
                <div class="progress-bar-bg">
                  <div
                    class="progress-bar-fill"
                    :class="{ 'over-budget': cat.remaining < 0 }"
                    :style="{ width: calculateProgress(cat.localPlanned, cat.actual) + '%' }"
                  ></div>
                </div>
              </div>
              <div class="col-numeric col-planned">
                <div class="input-wrapper">
                  <span class="currency-symbol">$</span>
                  <input
                    type="number"
                    v-model.number="cat.localPlanned"
                    @change="saveCategory(cat)"
                    class="amount-input"
                    :class="{ 'saving': cat.isSaving, 'error': cat.hasError }"
                    step="0.01"
                  />
                </div>
              </div>
              <div class="col-numeric">{{ formatCurrency(cat.actual) }}</div>
              <div class="col-numeric" :class="{ 'negative': cat.remaining < 0 }">
                {{ formatCurrency(cat.remaining) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

// --- State ---
const getCurrentMonth = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

const selectedMonth = ref(getCurrentMonth())
const budgetGroups = ref([])
const isLoading = ref(true)
const loadError = ref(null)
const collapsedGroups = ref({})

// --- Group Collapse ---
const toggleGroup = (groupId) => {
  collapsedGroups.value[groupId] = !collapsedGroups.value[groupId]
}

// --- Data Fetching ---
const fetchData = async () => {
  isLoading.value = true
  loadError.value = null

  try {
    // Fetch summary data (has actuals) and budget records (has budget_id for saving)
    const [summaryRes, budgetsRes] = await Promise.all([
      $fetch('/api/summary/budget', { query: { month: selectedMonth.value } }),
      $fetch('/api/budget', { query: { budget_month: `${selectedMonth.value}-01` } })
    ])

    // Create a map of budget_id by category_id
    const budgetMap = {}
    budgetsRes.forEach(b => {
      budgetMap[b.category_id] = b.budget_id
    })

    // Merge data: use summary structure but add editing fields
    budgetGroups.value = summaryRes.groups.map(group => ({
      ...group,
      categories: group.categories.map(cat => ({
        ...cat,
        localPlanned: Number(cat.planned) || 0,
        actual: Number(cat.actual) || 0,
        budget_id: budgetMap[cat.category_id] || null,
        isSaving: false,
        hasError: false,
        // remaining will be computed reactively
        get remaining() {
          return this.localPlanned - this.actual
        }
      }))
    }))

  } catch (err) {
    console.error('Failed to load budget data', err)
    loadError.value = err.message || 'Unknown error'
  } finally {
    isLoading.value = false
  }
}

// Initial fetch & watch month changes
watch(selectedMonth, fetchData, { immediate: true })

// --- Computed Totals ---
const totalIncome = computed(() => {
  let total = 0
  for (const group of budgetGroups.value) {
    for (const cat of group.categories) {
      if (cat.type === 'income') {
        total += (cat.localPlanned || 0)
      }
    }
  }
  return total
})

const totalIncomeActual = computed(() => {
  let total = 0
  for (const group of budgetGroups.value) {
    for (const cat of group.categories) {
      if (cat.type === 'income') {
        total += (cat.actual || 0)
      }
    }
  }
  return total
})

const totalExpenses = computed(() => {
  let total = 0
  for (const group of budgetGroups.value) {
    for (const cat of group.categories) {
      if (cat.type === 'expense') {
        total += (cat.localPlanned || 0)
      }
    }
  }
  return total
})

const totalExpensesActual = computed(() => {
  let total = 0
  for (const group of budgetGroups.value) {
    for (const cat of group.categories) {
      if (cat.type === 'expense') {
        total += (cat.actual || 0)
      }
    }
  }
  return total
})

const toBeAssigned = computed(() => totalIncome.value - totalExpenses.value)

const groupTotalPlanned = (group) => {
  return group.categories.reduce((sum, cat) => sum + (cat.localPlanned || 0), 0)
}

const groupTotalRemaining = (group) => {
  return group.categories.reduce((sum, cat) => sum + (cat.localPlanned - cat.actual), 0)
}

// --- Save Action ---
const saveCategory = async (cat) => {
  cat.isSaving = true
  cat.hasError = false

  try {
    let result
    if (cat.budget_id) {
      // Update existing budget
      result = await $fetch(`/api/budget/${cat.budget_id}`, {
        method: 'PUT',
        body: {
          budget_month: `${selectedMonth.value}-01`,
          planned_amount: cat.localPlanned || 0
        }
      })
    } else {
      // Create new budget
      result = await $fetch('/api/budget', {
        method: 'POST',
        body: {
          budget_month: `${selectedMonth.value}-01`,
          planned_amount: cat.localPlanned || 0,
          category_id: cat.category_id
        }
      })
    }

    // Update local budget_id if created
    if (result && result.budget_id) {
      cat.budget_id = result.budget_id
    }

  } catch (err) {
    console.error('Save failed', err)
    cat.hasError = true
  } finally {
    cat.isSaving = false
  }
}

// --- Helpers ---
const formatCurrency = (amount) => {
  const val = parseFloat(amount) || 0
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD'
  }).format(val)
}

const calculateProgress = (planned, actual) => {
  const p = parseFloat(planned) || 0
  const a = parseFloat(actual) || 0
  if (p === 0) return a > 0 ? 100 : 0
  const pct = (a / p) * 100
  return Math.min(Math.max(pct, 0), 100)
}
</script>

<style scoped>
.page-container {
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

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-secondary {
  background-color: #e2e8f0;
  color: var(--text-color);
}
.btn-secondary:hover {
  background-color: #cbd5e1;
}

/* Loading & Error States */
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px;
  color: var(--text-muted);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e2e8f0;
  border-top-color: var(--accent-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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

/* Budget Groups */
.group-section {
  background: white;
  border-radius: 16px;
  border: 1px solid var(--border-color);
  margin-bottom: 24px;
  overflow: hidden;
}

.group-header {
  padding: 16px 24px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s;
}

.group-header:hover {
  background: #f1f5f9;
}

.group-section.is-collapsed .group-header {
  border-bottom: none;
}

.group-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collapse-icon {
  color: var(--text-muted);
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.collapse-icon.collapsed {
  transform: rotate(-90deg);
}

.group-title {
  margin: 0;
  font-size: 1.1rem;
  color: var(--text-color);
}

.group-totals {
  font-size: 0.9rem;
  color: var(--text-muted);
  display: flex;
  gap: 16px;
}

.category-list {
  padding: 0;
}

.category-header-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-color);
  font-size: 0.85rem;
  color: var(--text-muted);
  font-weight: 600;
}

.category-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr;
  padding: 16px 24px;
  align-items: center;
  border-bottom: 1px solid #f1f5f9;
}
.category-row:last-child {
  border-bottom: none;
}

.col-numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.col-name {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-right: 16px;
}

.cat-name {
  font-weight: 500;
}

.progress-bar-bg {
  background: #e2e8f0;
  height: 6px;
  border-radius: 3px;
  width: 100%;
  overflow: hidden;
}

.progress-bar-fill {
  background: #10b981;
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease;
}

.progress-bar-fill.over-budget {
  background: #ef4444;
}

.negative {
  color: #ef4444;
}

/* Planned Column Input */
.col-planned {
  display: flex;
  justify-content: flex-end;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.currency-symbol {
  position: absolute;
  left: 10px;
  color: var(--text-muted);
  font-size: 0.9rem;
  pointer-events: none;
}

.amount-input {
  padding: 8px 12px 8px 24px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  width: 110px;
  text-align: right;
  font-size: 0.95rem;
  transition: border-color 0.2s, box-shadow 0.2s, background-color 0.2s;
}

.amount-input:focus {
  outline: none;
  border-color: var(--accent-color);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.amount-input.saving {
  background-color: #f0fdf4;
  border-color: #86efac;
}

.amount-input.error {
  border-color: #ef4444;
  background-color: #fef2f2;
}

/* Hide number input spinners */
.amount-input::-webkit-outer-spin-button,
.amount-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.amount-input[type=number] {
  -moz-appearance: textfield;
}
</style>
