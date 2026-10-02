export interface FormatDateOptions {
  includeYear?: boolean
}

export function formatDateOnly(
  dateStr: string | null | undefined,
  options: FormatDateOptions = {}
): string {
  if (!dateStr) return ''

  const [year, month, day] = dateStr.slice(0, 10).split('-').map(Number)

  if (!year || !month || !day) {
    return dateStr
  }

  const date = new Date(Date.UTC(year, month - 1, day))

  return date.toLocaleDateString('en-US', {
    timeZone: 'UTC',
    month: 'short',
    day: 'numeric',
    ...(options.includeYear ? { year: 'numeric' } : {})
  })
}
