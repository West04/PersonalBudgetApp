"""
Pure domain functions and structures for credit card financial calculations.

Rules & Invariants:
1. Monetary convention:
   - Outflows (charges, debits): positive amount (+X).
   - Inflows (payments, credits): negative amount (-X).
2. balance_owed:
   - balance_owed = starting_balance + all_time_net
   - all_time_net = sum of all transaction amounts across all time.
   - UNRESOLVED DOMAIN BEHAVIOR (PRESERVED): Transactions marked with is_transfer=True
     are currently INCLUDED in balance_owed.
3. charges_this_month:
   - Sum of positive transaction amounts (> 0) falling within [period_start, period_end).
   - UNRESOLVED DOMAIN BEHAVIOR (PRESERVED): Transactions marked with is_transfer=True
     are currently EXCLUDED from charges_this_month.
4. payments_this_month:
   - Absolute value of the sum of negative transaction amounts (< 0) falling within [period_start, period_end).
   - UNRESOLVED DOMAIN BEHAVIOR (PRESERVED): All negative transactions in the period are included,
     regardless of whether is_transfer is True or False.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class CreditCardTransaction:
    amount: Decimal
    date: date
    is_transfer: bool = False


@dataclass(frozen=True)
class CreditCardState:
    starting_balance: Decimal
    balance_owed: Decimal
    charges_this_month: Decimal
    payments_this_month: Decimal


def calculate_credit_card_state(
    starting_balance: Decimal,
    transactions: Sequence[CreditCardTransaction],
    period_start: date,
    period_end: date,
) -> CreditCardState:
    """
    Calculates credit card financial metrics:
    - balance_owed: starting_balance + all-time net transactions (including transfers).
    - charges_this_month: sum of positive, non-transfer transactions in [period_start, period_end).
    - payments_this_month: absolute sum of negative transactions in [period_start, period_end).
    """
    starting_bal = Decimal(str(starting_balance))
    all_time_net = ZERO
    charges_this_month = ZERO
    payments_raw = ZERO

    for tx in transactions:
        tx_amount = Decimal(str(tx.amount))
        all_time_net += tx_amount

        if period_start <= tx.date < period_end:
            if tx_amount > ZERO and not tx.is_transfer:
                charges_this_month += tx_amount
            elif tx_amount < ZERO:
                payments_raw += tx_amount

    balance_owed = starting_bal + all_time_net
    payments_this_month = abs(payments_raw)

    return CreditCardState(
        starting_balance=starting_bal,
        balance_owed=balance_owed,
        charges_this_month=charges_this_month,
        payments_this_month=payments_this_month,
    )
