/**
 * Presentation-only formatting for financial values.
 *
 * Formats a value the caller already computed. It never decides whether an
 * amount is good or bad: accounting meaning is passed in as a MoneyTone by the
 * caller (see components/Money.vue).
 */

export type MoneyTone =
  | 'neutral'
  | 'outflow'
  | 'inflow'
  | 'debt'
  | 'credit'
  | 'available'
  | 'overspent'

/**
 * auto:   "-$5.00" for negatives, "$5.00" otherwise (same as formatCurrency)
 * never:  absolute value, no sign
 * always: "+$5.00" / "-$5.00"; zero stays unsigned
 */
export type MoneySign = 'auto' | 'never' | 'always'

export const MONEY_TONES: readonly MoneyTone[] = [
  'neutral',
  'outflow',
  'inflow',
  'debt',
  'credit',
  'available',
  'overspent',
]

export function formatMoney(
  amount: number | string | null | undefined,
  sign: MoneySign = 'auto',
  currency = 'USD'
): string {
  let val = Number(amount)
  if (!Number.isFinite(val)) val = 0

  // Values that round to zero cents display as an unsigned zero ("-$0.00" never appears)
  if (Math.round(Math.abs(val) * 100) === 0) val = 0
  if (sign === 'never') val = Math.abs(val)

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: sign === 'always' ? 'exceptZero' : 'auto',
  }).format(val)
}
