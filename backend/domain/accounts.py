"""
Pure domain functions for account balance calculations.

Accounting convention:
- Outflows (debits, charges, expenses) are positive (+X).
- Inflows (credits, deposits, income) are negative (-X).
- Depository accounts represent assets: balance = starting_balance - net_transactions,
  where net_transactions is the sum of all transaction amounts.
"""

from decimal import Decimal

ZERO = Decimal("0.00")


def calculate_depository_balance(
    starting_balance: Decimal,
    net_transactions: Decimal,
) -> Decimal:
    """
    Calculates the authoritative current balance for a depository account.

    Formula:
        balance = starting_balance - net_transactions

    Example:
        starting_balance = 500.00
        grocery outflow  = +50.00
        paycheck inflow  = -200.00
        net_transactions = 50.00 + (-200.00) = -150.00
        balance          = 500.00 - (-150.00) = 650.00
    """
    return Decimal(str(starting_balance)) - Decimal(str(net_transactions))
