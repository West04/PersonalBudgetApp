"""
Unit tests for pure domain functions in backend/domain/accounts.py.
"""

from decimal import Decimal
import pytest

from backend.domain.accounts import calculate_depository_balance


def test_depository_balance_zero_net_transactions():
    balance = calculate_depository_balance(
        starting_balance=Decimal("500.00"),
        net_transactions=Decimal("0.00"),
    )
    assert balance == Decimal("500.00")


def test_depository_balance_expense_only():
    # Outflow/expense = +50.00
    balance = calculate_depository_balance(
        starting_balance=Decimal("500.00"),
        net_transactions=Decimal("50.00"),
    )
    assert balance == Decimal("450.00")


def test_depository_balance_income_only():
    # Inflow/income = -200.00
    balance = calculate_depository_balance(
        starting_balance=Decimal("500.00"),
        net_transactions=Decimal("-200.00"),
    )
    assert balance == Decimal("700.00")


def test_depository_balance_mixed_expense_and_income_concrete_case():
    # Concrete prompt example:
    # opening balance: $500.00
    # grocery outflow: +$50.00
    # paycheck inflow: -$200.00
    # net_transactions = 50.00 + (-200.00) = -150.00
    # balance = 500.00 - (-150.00) = 650.00
    net_transactions = Decimal("50.00") + Decimal("-200.00")
    balance = calculate_depository_balance(
        starting_balance=Decimal("500.00"),
        net_transactions=net_transactions,
    )
    assert balance == Decimal("650.00")


def test_depository_balance_zero_starting_balance():
    balance = calculate_depository_balance(
        starting_balance=Decimal("0.00"),
        net_transactions=Decimal("75.25"),
    )
    assert balance == Decimal("-75.25")
