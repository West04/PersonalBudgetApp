import { computed, type ComputedRef, type Ref } from 'vue'

export interface TransactionFiltersState {
  searchQuery: Ref<string>
  selectedCategory: Ref<string>
  uncategorizedOnly: Ref<boolean>
  offset: Ref<number>
  hasActiveSecondaryFilters: ComputedRef<boolean>
  clearSecondaryFilters: () => void
}

/**
 * Manages working-session secondary filters for the Transactions page.
 *
 * State ownership:
 * - Month: owned by useBudgetMonth() + route.query.month
 * - Account: owned by route.query.account_id
 * - Search, Category, Uncategorized: owned by useState() session persistence
 * - Offset: owned by useState() session persistence
 */
export function useTransactionFilters(): TransactionFiltersState {
  const searchQuery = useState<string>('tx_filter_search', () => '')
  const selectedCategory = useState<string>('tx_filter_category', () => '')
  const uncategorizedOnly = useState<boolean>('tx_filter_uncategorized', () => false)
  const offset = useState<number>('tx_filter_offset', () => 0)

  const hasActiveSecondaryFilters = computed(() => {
    return Boolean(
      searchQuery.value.trim() !== '' ||
      selectedCategory.value !== '' ||
      uncategorizedOnly.value === true
    )
  })

  const clearSecondaryFilters = () => {
    searchQuery.value = ''
    selectedCategory.value = ''
    uncategorizedOnly.value = false
    offset.value = 0
  }

  return {
    searchQuery,
    selectedCategory,
    uncategorizedOnly,
    offset,
    hasActiveSecondaryFilters,
    clearSecondaryFilters,
  }
}
