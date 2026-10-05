/**
 * Pure query construction and date range helpers for the Transactions ledger.
 */

export interface TransactionQueryParams {
  start_date: string
  end_date: string
  limit: number
  offset: number
  q?: string
  account_id?: string
  category_id?: string
  uncategorized?: boolean
  is_reviewed?: boolean
}

/**
 * Computes UTC start and end dates for a YYYY-MM month string.
 * Example: "2026-06" => { startDate: "2026-06-01", endDate: "2026-06-30" }
 */
export function computeMonthDateRange(monthStr: string): { startDate: string; endDate: string } {
  if (!monthStr || !/^\d{4}-\d{2}$/.test(monthStr)) {
    return { startDate: '', endDate: '' }
  }
  const [yearStr, monthNumStr] = monthStr.split('-')
  const year = Number(yearStr)
  const month = Number(monthNumStr)
  const startDate = `${yearStr}-${monthNumStr}-01`
  // Day 0 of next month in UTC gives last day of current month
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate()
  const endDate = `${yearStr}-${monthNumStr}-${String(lastDay).padStart(2, '0')}`
  return { startDate, endDate }
}

/**
 * Builds clean API query parameters for GET /api/transactions/.
 */
export function buildTransactionQuery(options: {
  month: string
  accountId?: string | null
  categoryId?: string | null
  search?: string | null
  uncategorized?: boolean | null
  reviewFilter?: 'all' | 'needs_review' | 'reviewed' | null
  is_reviewed?: boolean | null
  limit?: number | null
  offset?: number | null
}): TransactionQueryParams {
  const { startDate, endDate } = computeMonthDateRange(options.month)
  const params: TransactionQueryParams = {
    start_date: startDate,
    end_date: endDate,
    limit: options.limit ?? 50,
    offset: options.offset ?? 0,
  }

  const trimmedSearch = (options.search || '').trim()
  if (trimmedSearch) {
    params.q = trimmedSearch
  }

  if (options.accountId && options.accountId.trim() !== '') {
    params.account_id = options.accountId.trim()
  }

  if (options.categoryId && options.categoryId.trim() !== '') {
    params.category_id = options.categoryId.trim()
  }

  if (options.uncategorized === true) {
    params.uncategorized = true
  }

  if (options.reviewFilter === 'needs_review' || options.is_reviewed === false) {
    params.is_reviewed = false
  } else if (options.reviewFilter === 'reviewed' || options.is_reviewed === true) {
    params.is_reviewed = true
  }

  return params
}
