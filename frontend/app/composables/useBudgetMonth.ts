import { computed, watch, onMounted, type Ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'

export const MONTH_REGEX = /^\d{4}-(0[1-9]|1[0-2])$/

export function isValidMonth(month: unknown): month is string {
  return typeof month === 'string' && MONTH_REGEX.test(month)
}

export function getLocalMonthString(date: Date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
}

export function useBudgetMonth() {
  const selectedMonth = useState<string>('selected_budget_month', () => getLocalMonthString())
  const route = useRoute()
  const router = useRouter()

  const setMonth = (newMonth: string, historyMode: 'push' | 'replace' = 'push') => {
    if (!isValidMonth(newMonth)) return

    if (selectedMonth.value !== newMonth) {
      selectedMonth.value = newMonth
    }

    if (route.query.month !== newMonth) {
      const nextQuery = { ...route.query, month: newMonth }
      if (historyMode === 'push') {
        router.push({ query: nextQuery })
      } else {
        router.replace({ query: nextQuery })
      }
    }
  }

  const syncRouteMonth = () => {
    const queryMonth = route.query.month
    if (isValidMonth(queryMonth)) {
      if (selectedMonth.value !== queryMonth) {
        selectedMonth.value = queryMonth
      }
    } else {
      // Normalize route if month query is missing or invalid on a month-scoped page
      router.replace({
        query: { ...route.query, month: selectedMonth.value }
      })
    }
  }

  return {
    selectedMonth,
    isValidMonth,
    getLocalMonthString,
    setMonth,
    syncRouteMonth
  }
}
