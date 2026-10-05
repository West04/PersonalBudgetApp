"""
Pure domain tests for Account Reconciliation calculations and invariants.
"""

from decimal import Decimal
from datetime import date
from uuid import uuid4
import pytest

from backend.domain.account_reconciliation import (
    ReconciliationTx,
    ReconciliationCalculation,
    calculate_cleared_balance,
    calculate_reconciliation_difference,
    is_reconciliation_balanced,
    compute_reconciliation_state,
    ZERO,
)


def test_section_10_deterministic_worked_example():
    """
    Directly tests the prompt's required concrete characterization example:
    Prior reconciled balance: $1,000
    Transactions:
      +50 grocery
      -500 paycheck
      +100 utility
    Statement ending balance: $1,350

    Under existing sign convention:
      cleared balance = 1,000 - (+50 + -500 + 100) = 1,000 - (-350) = 1,350.00
      statement balance = 1,350.00
      difference = 0.00
    """
    prior_balance = Decimal("1000.00")
    net_cleared = Decimal("50.00") + Decimal("-500.00") + Decimal("100.00")  # -350.00

    cleared_balance = calculate_cleared_balance(prior_balance, net_cleared)
    assert cleared_balance == Decimal("1350.00")

    statement_ending_balance = Decimal("1350.00")
    diff = calculate_reconciliation_difference(statement_ending_balance, cleared_balance)
    assert diff == Decimal("0.00")
    assert is_reconciliation_balanced(statement_ending_balance, cleared_balance) is True


def test_section_24_difference_presentation_example():
    """
    Tests Section 24 example:
    Statement Balance: $1,350.00
    Cleared Balance:   $1,300.00
    Difference:           $50.00
    """
    statement_balance = Decimal("1350.00")
    cleared_balance = Decimal("1300.00")
    diff = calculate_reconciliation_difference(statement_balance, cleared_balance)
    assert diff == Decimal("50.00")
    assert is_reconciliation_balanced(statement_balance, cleared_balance) is False


def test_cent_accuracy_and_one_cent_mismatch():
    """
    Tests exact 0.01 cent boundary conditions:
    - 0.01 positive difference
    - 0.01 negative difference
    - exact 0.00 zero
    """
    stmt = Decimal("1000.00")

    # Off by +0.01 (statement is $1000.00, cleared is $999.99)
    assert calculate_reconciliation_difference(stmt, Decimal("999.99")) == Decimal("0.01")
    assert is_reconciliation_balanced(stmt, Decimal("999.99")) is False

    # Off by -0.01 (statement is $1000.00, cleared is $1000.01)
    assert calculate_reconciliation_difference(stmt, Decimal("1000.01")) == Decimal("-0.01")
    assert is_reconciliation_balanced(stmt, Decimal("1000.01")) is False

    # Exact match
    assert calculate_reconciliation_difference(stmt, Decimal("1000.00")) == Decimal("0.00")
    assert is_reconciliation_balanced(stmt, Decimal("1000.00")) is True


def test_ending_date_boundary_and_reconciled_filtering():
    """
    Tests that compute_reconciliation_state strictly:
    1. Includes transactions on or before statement_ending_date.
    2. Excludes transactions after statement_ending_date.
    3. Excludes transactions already marked is_reconciled=True.
    """
    acc_id = uuid4()
    ending_date = date(2026, 10, 31)

    t_before = ReconciliationTx(
        transaction_id=uuid4(),
        account_id=acc_id,
        amount=Decimal("50.00"),
        date=date(2026, 10, 15),
        is_cleared=True,
    )
    t_on_date = ReconciliationTx(
        transaction_id=uuid4(),
        account_id=acc_id,
        amount=Decimal("-200.00"),
        date=date(2026, 10, 31),
        is_cleared=True,
    )
    t_after_date = ReconciliationTx(
        transaction_id=uuid4(),
        account_id=acc_id,
        amount=Decimal("300.00"),
        date=date(2026, 11, 2),  # Future date relative to ending_date
        is_cleared=True,
    )
    t_already_reconciled = ReconciliationTx(
        transaction_id=uuid4(),
        account_id=acc_id,
        amount=Decimal("40.00"),
        date=date(2026, 10, 10),
        is_cleared=True,
        is_reconciled=True,  # Should be excluded
    )
    t_uncleared = ReconciliationTx(
        transaction_id=uuid4(),
        account_id=acc_id,
        amount=Decimal("75.00"),
        date=date(2026, 10, 20),
        is_cleared=False,  # Uncleared
    )

    all_txns = [t_before, t_on_date, t_after_date, t_already_reconciled, t_uncleared]

    calc = compute_reconciliation_state(
        prior_reconciled_balance=Decimal("500.00"),
        statement_ending_date=ending_date,
        statement_ending_balance=Decimal("650.00"),
        transactions=all_txns,
    )

    # Cleared net includes ONLY t_before (+50) and t_on_date (-200) = -150.00
    # Cleared balance = 500 - (-150) = 650.00
    assert calc.cleared_balance == Decimal("650.00")
    assert calc.statement_ending_balance == Decimal("650.00")
    assert calc.difference == Decimal("0.00")
    assert calc.is_balanced is True
    assert calc.cleared_count == 2
    assert calc.uncleared_count == 1  # t_uncleared is eligible and uncleared


def test_transfer_transaction_participation():
    """
    Tests that transfer transactions participate normally in cleared cash balance.
    """
    acc_id = uuid4()
    ending_date = date(2026, 10, 31)

    t_transfer_outflow = ReconciliationTx(
        transaction_id=uuid4(),
        account_id=acc_id,
        amount=Decimal("250.00"),
        date=date(2026, 10, 15),
        is_cleared=True,
        is_transfer=True,
    )
    calc = compute_reconciliation_state(
        prior_reconciled_balance=Decimal("1000.00"),
        statement_ending_date=ending_date,
        statement_ending_balance=Decimal("750.00"),
        transactions=[t_transfer_outflow],
    )
    assert calc.cleared_balance == Decimal("750.00")
    assert calc.is_balanced is True
