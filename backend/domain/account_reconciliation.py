"""
Pure domain functions and dataclasses for Account Reconciliation.

Accounting convention:
- Outflows (debits, charges, expenses) are positive (+X).
- Inflows (credits, deposits, income) are negative (-X).
- Depository accounts represent cash assets:
    cleared_balance = prior_reconciled_balance - net_cleared_transactions
  where net_cleared_transactions is the sum of amounts of all cleared transactions
  participating in this reconciliation period.
- Difference:
    difference = statement_ending_balance - cleared_balance
- Balancing condition:
    is_balanced = (difference == Decimal("0.00"))
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence
from uuid import UUID

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ReconciliationTx:
    transaction_id: UUID
    account_id: UUID
    amount: Decimal
    date: date
    is_cleared: bool
    is_reconciled: bool = False
    pending: bool = False
    is_transfer: bool = False


@dataclass(frozen=True)
class ReconciliationCalculation:
    prior_reconciled_balance: Decimal
    statement_ending_date: date
    statement_ending_balance: Decimal
    cleared_balance: Decimal
    difference: Decimal
    cleared_count: int
    uncleared_count: int
    is_balanced: bool


def calculate_cleared_balance(
    prior_reconciled_balance: Decimal,
    net_cleared_transactions: Decimal,
) -> Decimal:
    """
    Computes the cleared balance for a depository account:
        cleared_balance = prior_reconciled_balance - net_cleared_transactions

    Example:
        prior_balance = 1000.00
        grocery (+50.00) + paycheck (-500.00) + utility (+100.00) = -350.00 net
        cleared_balance = 1000.00 - (-350.00) = 1350.00
    """
    return Decimal(str(prior_reconciled_balance)) - Decimal(str(net_cleared_transactions))


def calculate_reconciliation_difference(
    statement_ending_balance: Decimal,
    cleared_balance: Decimal,
) -> Decimal:
    """
    Computes the difference between statement ending balance and cleared balance:
        difference = statement_ending_balance - cleared_balance

    When balanced, difference is 0.00.
    """
    return Decimal(str(statement_ending_balance)) - Decimal(str(cleared_balance))


def is_reconciliation_balanced(
    statement_ending_balance: Decimal,
    cleared_balance: Decimal,
) -> bool:
    """
    Returns True if the reconciliation is exactly balanced to 0.00 cents.
    """
    return calculate_reconciliation_difference(statement_ending_balance, cleared_balance) == ZERO


def compute_reconciliation_state(
    prior_reconciled_balance: Decimal,
    statement_ending_date: date,
    statement_ending_balance: Decimal,
    transactions: Sequence[ReconciliationTx],
) -> ReconciliationCalculation:
    """
    Pure evaluation of reconciliation math across a sequence of candidate transactions:
    1. Filters to unreconciled transactions dated on or before statement_ending_date.
    2. Sums net amounts of cleared transactions.
    3. Calculates cleared balance, difference, and counts.
    """
    prior_dec = Decimal(str(prior_reconciled_balance))
    stmt_dec = Decimal(str(statement_ending_balance))

    eligible_txns = [
        t for t in transactions
        if not t.is_reconciled and t.date <= statement_ending_date
    ]

    cleared_txns = [t for t in eligible_txns if t.is_cleared]
    uncleared_txns = [t for t in eligible_txns if not t.is_cleared]

    cleared_net = sum((Decimal(str(t.amount)) for t in cleared_txns), ZERO)
    cleared_bal = calculate_cleared_balance(prior_dec, cleared_net)
    diff = calculate_reconciliation_difference(stmt_dec, cleared_bal)
    balanced = (diff == ZERO)

    return ReconciliationCalculation(
        prior_reconciled_balance=prior_dec,
        statement_ending_date=statement_ending_date,
        statement_ending_balance=stmt_dec,
        cleared_balance=cleared_bal,
        difference=diff,
        cleared_count=len(cleared_txns),
        uncleared_count=len(uncleared_txns),
        is_balanced=balanced,
    )
