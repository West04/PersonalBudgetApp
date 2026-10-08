"""
Pure domain functions and structures for credit card financial calculations.

Rules & Invariants:
1. Monetary convention:
   - Outflows (charges, debits): positive amount (+X).
   - Inflows (payments, credits): negative amount (-X).
2. balance_owed:
   - Actual card liability as of the point-in-time cutoff.
   - balance_owed = starting_balance + sum(tx.amount for tx in transactions if tx.date < cutoff_exclusive).
   - Includes ordinary purchases, merchant refunds/credits, card-payment transfers, and positive transfers.
   - Strictly excludes transactions occurring on or after cutoff_exclusive.
3. charges_this_month:
   - Sum of gross positive non-transfer transaction amounts (> 0) falling within [period_start, cutoff_exclusive).
   - Transactions marked with is_transfer=True are excluded.
   - Merchant refunds do not reduce this metric (gross charges).
4. payments_this_month:
   - Absolute value of the sum of negative transfer transaction amounts (< 0 and is_transfer=True)
     falling within [period_start, cutoff_exclusive).
   - Merchant refunds, statement credits, rewards, and other negative non-transfer transactions are excluded.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

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
    cutoff_exclusive: Optional[date] = None,
) -> CreditCardState:
    """
    Calculates credit card financial metrics:
    - balance_owed: starting_balance + net of transactions where tx.date < cutoff_exclusive.
      Includes purchases, refunds, and transfers. Excludes transactions on or after cutoff.
    - charges_this_month: sum of gross positive, non-transfer transactions in
      [period_start, cutoff_exclusive).
    - payments_this_month: absolute sum of negative transfer transactions in
      [period_start, cutoff_exclusive). Excludes refunds.
    """
    starting_bal = Decimal(str(starting_balance))
    all_time_net = ZERO
    charges_this_month = ZERO
    payments_raw = ZERO

    cutoff = cutoff_exclusive if cutoff_exclusive is not None else period_end

    for tx in transactions:
        tx_amount = Decimal(str(tx.amount))

        if tx.date < cutoff:
            all_time_net += tx_amount

        if period_start <= tx.date < cutoff:
            if tx_amount > ZERO and not tx.is_transfer:
                charges_this_month += tx_amount
            elif tx_amount < ZERO and tx.is_transfer:
                payments_raw += tx_amount

    balance_owed = starting_bal + all_time_net
    payments_this_month = abs(payments_raw)

    return CreditCardState(
        starting_balance=starting_bal,
        balance_owed=balance_owed,
        charges_this_month=charges_this_month,
        payments_this_month=payments_this_month,
    )

