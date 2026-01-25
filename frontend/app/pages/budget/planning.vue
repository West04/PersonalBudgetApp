<template>
  <div class="page-container">
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">Budget Planning</h1>
        <input 
          type="month" 
          v-model="selectedMonth" 
          class="month-picker"
        />
      </div>
      <div class="header-right">
        <NuxtLink to="/budget" class="btn btn-secondary">
          Done
        </NuxtLink>
      </div>
    </header>

    <!-- Sticky Summary Bar -->
    <div class="sticky-summary" :class="{ 'scrolled': isScrolled }">
      <div class="summary-item">
        <span class="label">Total Income</span>
        <span class="value income">{{ formatCurrency(totalIncome) }}</span>
      </div>
      <div class="operator">-</div>
      <div class="summary-item">
        <span class="label">Total Planned</span>
        <span class="value expense">{{ formatCurrency(totalExpenses) }}</span>
      </div>
      <div class="operator">=</div>
      <div class="summary-item highlight" :class="{ 'negative': toBeAssigned < 0 }">
        <span class="label">To Be Assigned</span>
        <span class="value">{{ formatCurrency(toBeAssigned) }}</span>
      </div>
    </div>

    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <p>Loading planning data...</p>
    </div>

    <div v-else class="content-area">
      <div v-for="group in plannedGroups" :key="group.group_id" class="group-section">
        <div class="group-header">
          <h2 class="group-title">{{ group.name }}</h2>
          <div class="group-total">{{ formatCurrency(groupTotal(group)) }}</div>
        </div>

        <div class="category-list">
          <div v-for="cat in group.categories" :key="cat.category_id" class="category-row">
            <div class="cat-name">{{ cat.name }}</div>
            <div class="cat-input-wrapper">
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
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useFetch } from '#app'

// --- State ---
const getCurrentMonth = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

const selectedMonth = ref(getCurrentMonth())
const plannedGroups = ref([]) // Local merged state
const isLoading = ref(true)
const isScrolled = ref(false)

// --- Scroll Detection ---
const checkScroll = () => {
  isScrolled.value = window.scrollY > 100
}
onMounted(() => window.addEventListener('scroll', checkScroll))
onUnmounted(() => window.removeEventListener('scroll', checkScroll))

// --- Data Fetching & Merging ---
const fetchData = async () => {
  isLoading.value = true
  try {
    // Parallel fetch
    const [groupsRes, budgetsRes] = await Promise.all([
      $fetch('/api/category-groups'),
      $fetch('/api/budget', { query: { budget_month: `${selectedMonth.value}-01` } })
    ])

    // Create a map of existing budgets: category_id -> budget_obj
    const budgetMap = {}
    budgetsRes.forEach(b => {
      budgetMap[b.category_id] = b
    })

    // Merge into local state
    plannedGroups.value = groupsRes.map(group => ({
      ...group,
      categories: group.categories.map(cat => {
        const existing = budgetMap[cat.category_id]
        return {
          ...cat,
          // If existing budget, use its planned_amount, else 0
          localPlanned: existing ? Number(existing.planned_amount) : 0,
          budget_id: existing ? existing.budget_id : null,
          isSaving: false,
          hasError: false
        }
      })
    }))

  } catch (err) {
    console.error('Failed to load planning data', err)
    alert('Error loading data. Please refresh.')
  } finally {
    isLoading.value = false
  }
}

// Initial fetch & Watch month
watch(selectedMonth, fetchData, { immediate: true })

// --- Computed Totals ---
const totalIncome = computed(() => {
  let total = 0
  for (const group of plannedGroups.value) {
    for (const cat of group.categories) {
      if (cat.type === 'income') {
        total += (cat.localPlanned || 0)
      }
    }
  }
  return total
})

const totalExpenses = computed(() => {
  let total = 0
  for (const group of plannedGroups.value) {
    for (const cat of group.categories) {
      if (cat.type === 'expense') {
        total += (cat.localPlanned || 0)
      }
    }
  }
  return total
})

const toBeAssigned = computed(() => totalIncome.value - totalExpenses.value)

const groupTotal = (group) => {
  return group.categories.reduce((sum, cat) => sum + (cat.localPlanned || 0), 0)
}

// --- Actions ---
const saveCategory = async (cat) => {
  cat.isSaving = true
  cat.hasError = false
  
  try {
    let result
    if (cat.budget_id) {
      // Update - only send fields defined in BudgetUpdate
      result = await $fetch(`/api/budget/${cat.budget_id}`, {
        method: 'PUT',
        body: {
            budget_month: `${selectedMonth.value}-01`,
            planned_amount: cat.localPlanned || 0
        }
      })
    } else {
      // Create - send all fields for BudgetCreate
      result = await $fetch('/api/budget', {
        method: 'POST',
        body: {
            budget_month: `${selectedMonth.value}-01`,
            planned_amount: cat.localPlanned || 0,
            category_id: cat.category_id
        }
      })
    }

    // Update local budget_id in case it was a create
    if (result && result.budget_id) {
      cat.budget_id = result.budget_id
    }

  } catch (err) {
    console.error('Save failed', err)
    cat.hasError = true
    // Optional: revert value or show toast
  } finally {
    cat.isSaving = false
  }
}

// --- Helpers ---
const formatCurrency = (amount) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD'
  }).format(amount)
}
</script>

<style scoped>
.page-container {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}

/* ... (header styles remain) ... */

/* Sticky Summary */
.sticky-summary {
  position: sticky;
  top: 0;
  margin: -24px -24px 24px -24px; /* Negative margin to span full width of padding */
  padding: 16px 32px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 24px;
  z-index: 10;
  transition: all 0.3s;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.label {
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: uppercase;
  font-weight: 600;
}

.value {
  font-size: 1.2rem;
  font-weight: 700;
}

.operator {
  font-size: 1.5rem;
  color: var(--text-muted);
  font-weight: 300;
}

.income { color: #10b981; }
.expense { color: var(--text-color); }
.highlight .value { color: var(--accent-color); }
.highlight.negative .value { color: #ef4444; }

/* Groups */
.group-section {
  background: white;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  margin-bottom: 24px;
  overflow: hidden;
}

.group-header {
  padding: 12px 24px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.group-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.group-total {
  font-weight: 600;
  color: var(--text-muted);
}

.category-list {
  padding: 8px 0;
}

.category-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 24px;
  border-bottom: 1px solid #f1f5f9;
}
.category-row:last-child { border-bottom: none; }

.cat-input-wrapper {
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
  width: 120px;
  text-align: right;
  font-size: 1rem;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.amount-input:focus {
  outline: none;
  border-color: var(--accent-color);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.amount-input.saving {
  background-color: #f0fdf4; /* Green tint */
  border-color: #86efac;
}

.amount-input.error {
  border-color: #ef4444;
  background-color: #fef2f2;
}

/* Spinner */
.loading-state {
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
</style>