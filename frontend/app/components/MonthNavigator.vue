<template>
  <div class="month-navigator" role="group" aria-label="Budget Month Navigation">
    <button
      type="button"
      class="nav-btn prev-btn"
      @click="handlePrevious"
      aria-label="Previous month"
      title="Previous month"
    >
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <polyline points="15 18 9 12 15 6"></polyline>
      </svg>
    </button>

    <div class="month-display-container">
      <label class="month-label" :title="`Selected: ${displayMonth}. Click to choose another month.`">
        <span class="calendar-icon" aria-hidden="true">📅</span>
        <span class="month-text">{{ displayMonth }}</span>
        <input
          type="month"
          class="month-picker-input"
          :value="selectedMonth"
          @change="onPickerChange"
          aria-label="Direct month selection"
        />
      </label>
    </div>

    <button
      type="button"
      class="nav-btn next-btn"
      @click="handleNext"
      aria-label="Next month"
      title="Next month"
    >
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <polyline points="9 18 15 12 9 6"></polyline>
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useBudgetMonth, isValidMonth } from '~/composables/useBudgetMonth'
import { getPreviousMonth, getNextMonth, formatMonthDisplay } from '~/utils/monthMath'

const { selectedMonth, setMonth, syncRouteMonth } = useBudgetMonth()
const route = useRoute()

const displayMonth = computed(() => formatMonthDisplay(selectedMonth.value))

const handlePrevious = () => {
  const prevMonth = getPreviousMonth(selectedMonth.value)
  setMonth(prevMonth)
}

const handleNext = () => {
  const nextMonth = getNextMonth(selectedMonth.value)
  setMonth(nextMonth)
}

const onPickerChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target?.value && isValidMonth(target.value)) {
    setMonth(target.value)
  }
}

onMounted(() => {
  syncRouteMonth()
})

watch(
  () => route.query.month,
  (newMonth) => {
    if (isValidMonth(newMonth) && newMonth !== selectedMonth.value) {
      selectedMonth.value = newMonth
    } else if (!isValidMonth(newMonth)) {
      syncRouteMonth()
    }
  }
)
</script>

<style scoped>
.month-navigator {
  display: inline-flex;
  align-items: center;
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 2px;
  box-shadow: var(--shadow-sm);
  user-select: none;
}

.nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
}

.nav-btn:hover {
  background-color: var(--color-surface-hover);
  color: var(--color-text);
}

.nav-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.month-display-container {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.month-label {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.month-label:hover {
  background-color: var(--color-surface-hover);
}

.month-label:focus-within {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.calendar-icon {
  font-size: 0.9rem;
  line-height: 1;
}

.month-text {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.month-picker-input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}
</style>
