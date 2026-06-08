// Single source of truth for account types and subtypes.
// Must stay in sync with backend schemas.ACCOUNT_SUBTYPES.

export interface AccountTypeOption {
  value: string
  label: string
}

export interface AccountTypeDefinition {
  value: string
  label: string
  subtypes: AccountTypeOption[]
}

export const ACCOUNT_TYPES: AccountTypeDefinition[] = [
  {
    value: 'depository',
    label: 'Checking / Savings',
    subtypes: [
      { value: 'checking', label: 'Checking' },
      { value: 'savings',  label: 'Savings' },
    ],
  },
  {
    value: 'credit',
    label: 'Credit Card',
    subtypes: [
      { value: 'credit card', label: 'Credit Card' },
    ],
  },
  {
    value: 'investment',
    label: 'Investment',
    subtypes: [
      { value: 'brokerage', label: 'Brokerage' },
      { value: 'ira',       label: 'IRA' },
      { value: '401k',      label: '401k' },
      { value: 'other',     label: 'Other' },
    ],
  },
  {
    value: 'loan',
    label: 'Loan',
    subtypes: [
      { value: 'mortgage', label: 'Mortgage' },
      { value: 'auto',     label: 'Auto' },
      { value: 'student',  label: 'Student' },
      { value: 'personal', label: 'Personal' },
      { value: 'other',    label: 'Other' },
    ],
  },
  {
    value: 'other',
    label: 'Other',
    subtypes: [
      { value: 'other', label: 'Other' },
    ],
  },
]

export function useAccountTypes() {
  const getTypeDef = (type: string): AccountTypeDefinition | undefined =>
    ACCOUNT_TYPES.find(t => t.value === type)

  const getTypeLabel = (type: string): string =>
    getTypeDef(type)?.label ?? type

  const getSubtypeLabel = (type: string, subtype: string): string => {
    const sub = getTypeDef(type)?.subtypes.find(s => s.value === subtype)
    return sub?.label ?? subtype
  }

  const getSubtypes = (type: string): AccountTypeOption[] =>
    getTypeDef(type)?.subtypes ?? []

  const defaultSubtype = (type: string): string =>
    getSubtypes(type)[0]?.value ?? ''

  return { ACCOUNT_TYPES, getTypeLabel, getSubtypeLabel, getSubtypes, defaultSubtype }
}
