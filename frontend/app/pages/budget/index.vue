<template>
  <div class="page-container">
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">Budget Overview</h1>
        <input 
          type="month" 
          v-model="selectedMonth" 
          class="month-picker"
        />
      </div>
      <div class="header-right">
        <NuxtLink to="/budget/planning" class="btn btn-primary">
          📝 Plan Budget
        </NuxtLink>
      </div>
    </header>

    <div v-if="pending" class="loading-state">
      <div class="spinner"></div>
      <p>Loading budget...</p>
    </div>

    <div v-else-if="error" class="error-state">
      <p>Error loading budget: {{ error.message }}</p>
      <button @click="refresh" class="btn btn-secondary">Retry</button>
    </div>

    <div v-else class="content-area">
      <!-- Summary Cards -->
      <section class="summary-cards">
        <div class="card summary-card income">
          <div class="card-label">Planned Income</div>
          <div class="card-value">{{ formatCurrency(data.total_income_planned) }}</div>
          <div class="card-sub">Actual: {{ formatCurrency(data.total_income_actual) }}</div>
        </div>
        
        <div class="card summary-card expense">
          <div class="card-label">Planned Expenses</div>
          <div class="card-value">{{ formatCurrency(data.total_expense_planned) }}</div>
          <div class="card-sub">Actual: {{ formatCurrency(data.total_expense_actual) }}</div>
        </div>

        <div class="card summary-card assign" :class="{ 'warning': data.to_be_assigned < 0 }">
          <div class="card-label">To Be Assigned</div>
          <div class="card-value">{{ formatCurrency(data.to_be_assigned) }}</div>
          <div class="card-sub" v-if="data.to_be_assigned === 0">Every dollar has a job! 🎉</div>
          <div class="card-sub" v-else-if="data.to_be_assigned > 0">You have money to budget</div>
          <div class="card-sub" v-else>You are over-budgeted!</div>
        </div>
      </section>

      <!-- Budget Groups -->
      <div class="budget-groups">
        <div v-for="group in data.groups" :key="group.group_id" class="group-section">
          <div class="group-header">
            <h2 class="group-title">{{ group.name }}</h2>
            <div class="group-totals">
              <span>Planned: {{ formatCurrency(group.total_planned) }}</span>
              <span>Remaining: {{ formatCurrency(group.total_remaining) }}</span>
            </div>
          </div>

          <div class="category-list">
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
                    :class="{ 'over-budget': cat.is_over_budget }"
                    :style="{ width: calculateProgress(cat.planned, cat.actual) + '%' }"
                  ></div>
                </div>
              </div>
              <div class="col-numeric">{{ formatCurrency(cat.planned) }}</div>
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
import { ref, watch } from 'vue'
import { useFetch } from '#app'

// Helper for default month (YYYY-MM)
const getCurrentMonth = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

const selectedMonth = ref(getCurrentMonth())

const { data, pending, error, refresh } = await useFetch('/api/summary/budget', {
  query: { month: selectedMonth }
})

// Watch for month changes to refetch
watch(selectedMonth, () => {
  // useFetch with reactive params usually auto-refetches, but if not we can trigger it.
  // In Nuxt 3, passing a ref to query makes it reactive.
})

const formatCurrency = (amount) => {
  const val = parseFloat(amount)
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD'
  }).format(val)
}

const calculateProgress = (planned, actual) => {
  const p = parseFloat(planned)
  const a = parseFloat(actual)
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

.btn-primary {
  background-color: var(--accent-color);
  color: white;
}
.btn-primary:hover {
  filter: brightness(110%);
}

.btn-secondary {
  background-color: #e2e8f0;
  color: var(--text-color);
}
.btn-secondary:hover {
  background-color: #cbd5e1;
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

.summary-card.income .card-value { color: #10b981; } /* Green */
.summary-card.expense .card-value { color: #f59e0b; } /* Amber */
.summary-card.assign .card-value { color: var(--accent-color); }
.summary-card.assign.warning .card-value { color: #ef4444; } /* Red */

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
</style>