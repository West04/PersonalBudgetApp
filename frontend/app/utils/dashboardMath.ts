/**
 * Pure domain presentation calculations for the Dashboard.
 *
 * Implements:
 * 1. Financial position aggregation (Cash/Depository, Credit Card Debt, Net Position).
 * 2. Credit card balance presentation (owed vs credit/overpayment without negative debt strings).
 * 3. Spending by group progress, remaining, and over-budget status.
 * 4. Derivable budgeting attention items (over-budget groups, unassigned money).
 * 5. Safe monetary formatting.
 */

export interface DashboardAccount {
  account_id: string
  name: string
  type: string
  subtype?: string | null
  current_balance: number | string | null
  available_balance?: number | string | null
  currency?: string
  is_active?: boolean
}

export interface CreditCardSummaryItem {
  account_id: string
  account_name: string
  starting_balance?: number | string
  balance_owed: number | string
  charges_this_month?: number | string
  payments_this_month?: number | string
}

export interface FinancialPositionSummary {
  depositoryBalance: number
  depositoryCount: number
  creditCardDebt: number
  netCreditBalance: number
  hasCreditBalance: boolean
  creditCardCount: number
  creditDisplayLabel: string
  netPosition: number
}

export interface CardBalanceDisplay {
  amount: number
  formatted: string
  isOwed: boolean
  isCredit: boolean
  displayLabel: string
}

export interface GroupSpendingSummary {
  actual: number
  planned: number
  remaining: number
  isOverBudget: boolean
  overAmount: number
  percentage: number
  statusLabel: string
}

export interface AttentionItem {
  id: string
  type: 'over_budget' | 'to_be_assigned' | 'over_assigned'
  title: string
  message: string
  overAmount?: number
}

/**
 * Formats a numeric value into USD (or specified currency) string.
 */
export function formatCurrency(amount: number | string | null | undefined, currency = 'USD'): string {
  const val = Number(amount)
  if (isNaN(val)) return '$0.00'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val)
}

/**
 * Formats an individual credit card balance.
 * Strictly adheres to rule:
 * - balance_owed > 0 => "$X.XX owed"
 * - balance_owed < 0 => "$X.XX credit"
 * - balance_owed === 0 => "$0.00"
 * Never displays "-$X owed".
 */
export function formatCardBalance(balanceOwed: number | string | null | undefined): CardBalanceDisplay {
  const num = Number(balanceOwed) || 0
  if (num > 0) {
    return {
      amount: num,
      formatted: formatCurrency(num),
      isOwed: true,
      isCredit: false,
      displayLabel: `${formatCurrency(num)} owed`,
    }
  } else if (num < 0) {
    const absVal = Math.abs(num)
    return {
      amount: absVal,
      formatted: formatCurrency(absVal),
      isOwed: false,
      isCredit: true,
      displayLabel: `${formatCurrency(absVal)} credit`,
    }
  } else {
    return {
      amount: 0,
      formatted: formatCurrency(0),
      isOwed: false,
      isCredit: false,
      displayLabel: formatCurrency(0),
    }
  }
}

/**
 * Aggregates accounts and credit cards into Financial Position metrics:
 * - Depository Balance (Checking, Savings, other depository)
 * - Credit Card Debt (authoritative balance_owed from credit card summary or accounts)
 * - Net Position (Depository cash minus net credit card balance)
 */
export function summarizeFinancialPosition(
  accounts: DashboardAccount[] = [],
  creditCards: CreditCardSummaryItem[] = []
): FinancialPositionSummary {
  // 1. Depository cash
  let depositoryBalance = 0
  let depositoryCount = 0

  for (const acc of accounts) {
    if (acc.is_active === false) continue
    const typeStr = (acc.type || '').toLowerCase()
    if (typeStr === 'depository') {
      depositoryBalance += Number(acc.current_balance) || 0
      depositoryCount++
    }
  }

  // 2. Credit Card calculations
  let netCreditBalance = 0
  let creditCardCount = 0

  if (creditCards && creditCards.length > 0) {
    creditCardCount = creditCards.length
    for (const card of creditCards) {
      const owed = Number(card.balance_owed) || 0
      netCreditBalance += owed
    }
  } else {
    // Fallback to accounts table if credit cards summary is unavailable
    for (const acc of accounts) {
      if (acc.is_active === false) continue
      const typeStr = (acc.type || '').toLowerCase()
      if (typeStr === 'credit') {
        creditCardCount++
        // If stored as negative in seed/manual, normalize to debt owed:
        const raw = Number(acc.current_balance) || 0
        netCreditBalance += raw < 0 ? Math.abs(raw) : raw
      }
    }
  }

  const hasCreditBalance = netCreditBalance < 0
  let creditCardDebt = 0
  let creditDisplayLabel = '$0.00'

  if (netCreditBalance > 0) {
    creditCardDebt = netCreditBalance
    creditDisplayLabel = formatCurrency(netCreditBalance)
  } else if (netCreditBalance < 0) {
    creditCardDebt = netCreditBalance
    creditDisplayLabel = `${formatCurrency(Math.abs(netCreditBalance))} credit`
  } else {
    creditCardDebt = 0
    creditDisplayLabel = formatCurrency(0)
  }

  // 3. Net Position: Cash / Depository minus net credit card balance
  // If credit card has an overpayment (netCreditBalance < 0), subtracting negative increases net position.
  const netPosition = depositoryBalance - netCreditBalance

  return {
    depositoryBalance,
    depositoryCount,
    creditCardDebt,
    netCreditBalance,
    hasCreditBalance,
    creditCardCount,
    creditDisplayLabel,
    netPosition,
  }
}

/**
 * Computes progress, remaining, and over-budget status for a spending group.
 */
export function calculateGroupSpending(
  actual: number | string | null | undefined,
  planned: number | string | null | undefined
): GroupSpendingSummary {
  const act = Number(actual) || 0
  const pln = Number(planned) || 0
  const remaining = pln - act
  const isOver = act > pln
  const overAmount = isOver ? act - pln : 0

  let percentage = 0
  if (pln <= 0) {
    percentage = act > 0 ? 100 : 0
  } else {
    percentage = Math.min(Math.max((act / pln) * 100, 0), 100)
  }

  let statusLabel = ''
  if (pln > 0) {
    if (isOver) {
      statusLabel = `Over by ${formatCurrency(overAmount)}`
    } else {
      statusLabel = `${formatCurrency(remaining)} remaining`
    }
  } else {
    statusLabel = act > 0 ? `${formatCurrency(act)} spent (unbudgeted)` : 'No budget'
  }

  return {
    actual: act,
    planned: pln,
    remaining,
    isOverBudget: isOver,
    overAmount,
    percentage,
    statusLabel,
  }
}

/**
 * Derives actionable budgeting attention items strictly from current API values:
 * 1. Groups that have exceeded their planned budget.
 * 2. Unassigned funds or over-budgeted allocation in the zero-based budget.
 */
export function getDerivableBudgetAttention(
  groups: Array<{ group_id: string; name: string; planned: number | string; actual: number | string }> = [],
  toBeAssigned?: number | string | null
): AttentionItem[] {
  const items: AttentionItem[] = []

  // 1. Groups over budget
  for (const group of groups) {
    const act = Number(group.actual) || 0
    const pln = Number(group.planned) || 0
    if (act > pln && pln > 0) {
      const over = act - pln
      items.push({
        id: `group-over-${group.group_id}`,
        type: 'over_budget',
        title: group.name,
        message: `${group.name} is over budget by ${formatCurrency(over)}`,
        overAmount: over,
      })
    }
  }

  // 2. Unassigned funds / over-allocated zero-based budget
  if (toBeAssigned !== undefined && toBeAssigned !== null) {
    const tba = Number(toBeAssigned)
    if (!isNaN(tba)) {
      if (tba > 0) {
        items.push({
          id: 'to-be-assigned',
          type: 'to_be_assigned',
          title: 'To Be Assigned',
          message: `${formatCurrency(tba)} left to assign in budget`,
        })
      } else if (tba < 0) {
        items.push({
          id: 'over-assigned',
          type: 'over_assigned',
          title: 'Over-assigned',
          message: `${formatCurrency(Math.abs(tba))} over-allocated across categories`,
        })
      }
    }
  }

  return items
}
