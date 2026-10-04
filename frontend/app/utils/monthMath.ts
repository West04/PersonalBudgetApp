import { MONTH_REGEX } from '../composables/useBudgetMonth.ts'

/**
 * Returns the YYYY-MM string for the month preceding the given month.
 * Correctly rolls over year boundaries (e.g., 2026-01 -> 2025-12).
 */
export function getPreviousMonth(monthStr: string): string {
  if (!MONTH_REGEX.test(monthStr)) return monthStr
  const [yearStr, monthNumStr] = monthStr.split('-')
  let year = parseInt(yearStr, 10)
  let month = parseInt(monthNumStr, 10)

  month -= 1
  if (month < 1) {
    month = 12
    year -= 1
  }

  return `${year}-${String(month).padStart(2, '0')}`
}

/**
 * Returns the YYYY-MM string for the month following the given month.
 * Correctly rolls over year boundaries (e.g., 2026-12 -> 2027-01).
 */
export function getNextMonth(monthStr: string): string {
  if (!MONTH_REGEX.test(monthStr)) return monthStr
  const [yearStr, monthNumStr] = monthStr.split('-')
  let year = parseInt(yearStr, 10)
  let month = parseInt(monthNumStr, 10)

  month += 1
  if (month > 12) {
    month = 1
    year += 1
  }

  return `${year}-${String(month).padStart(2, '0')}`
}

/**
 * Formats a YYYY-MM string into a human-readable string in UTC (e.g. "June 2026").
 * Timezone-invariant to avoid calendar day or month shifts.
 */
export function formatMonthDisplay(monthStr: string): string {
  if (!MONTH_REGEX.test(monthStr)) return monthStr
  const [year, month] = monthStr.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, 1))
  return date.toLocaleDateString('en-US', {
    timeZone: 'UTC',
    month: 'long',
    year: 'numeric'
  })
}
