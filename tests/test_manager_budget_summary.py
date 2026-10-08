from datetime import date
from decimal import Decimal
import pytest

from backend import models
from backend.domain.budgeting import BudgetSummaryResult
from backend.domain.dates import determine_month_range
from backend.managers.budget_summary_manager import get_budget_summary


def test_determine_month_range_mid_year():
    """Verify standard mid-year month range calculation [start, end)."""
    start, end = determine_month_range(date(2026, 6, 15))
    assert start == date(2026, 6, 1)
    assert end == date(2026, 7, 1)


def test_determine_month_range_december_year_wrap():
    """Verify December wraps to January of the next year."""
    start, end = determine_month_range(date(2026, 12, 1))
    assert start == date(2026, 12, 1)
    assert end == date(2027, 1, 1)


def test_manager_get_budget_summary_coordination(db_session):
    """
    Verify get_budget_summary coordinates ResourceAccess data retrieval,
    builds domain inputs, and computes BudgetSummaryResult correctly.
    """
    # Create category groups
    g_income = models.CategoryGroup(name="Income Group", sort_order=1)
    g_expense = models.CategoryGroup(name="Expenses Group", sort_order=2)
    db_session.add_all([g_income, g_expense])
    db_session.flush()

    # Create categories
    cat_salary = models.Category(
        group_id=g_income.category_group_id,
        name="Salary",
        type="income",
        sort_order=1,
    )
    cat_rent = models.Category(
        group_id=g_expense.category_group_id,
        name="Rent",
        type="expense",
        sort_order=1,
    )
    db_session.add_all([cat_salary, cat_rent])
    db_session.flush()

    # Create budgets for June 2026
    b_salary = models.Budget(
        category_id=cat_salary.category_id,
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("5000.00"),
    )
    b_rent = models.Budget(
        category_id=cat_rent.category_id,
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("1500.00"),
    )
    db_session.add_all([b_salary, b_rent])

    # Create account and transactions
    account = models.Account(
        name="Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("5000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.flush()

    # Income inflow: -4800.00
    tx_income = models.Transaction(
        account_id=account.id,
        category_id=cat_salary.category_id,
        amount=Decimal("-4800.00"),
        date=date(2026, 6, 5),
        description="Salary",
    )
    # Expense outflow: +1500.00
    tx_rent = models.Transaction(
        account_id=account.id,
        category_id=cat_rent.category_id,
        amount=Decimal("1500.00"),
        date=date(2026, 6, 1),
        description="Rent",
    )
    db_session.add_all([tx_income, tx_rent])
    db_session.commit()

    # Run Manager workflow
    result = get_budget_summary(db_session, date(2026, 6, 1))

    assert isinstance(result, BudgetSummaryResult)
    assert result.total_income_planned == Decimal("5000.00")
    assert result.total_income_actual == Decimal("4800.00")
    assert result.total_expense_planned == Decimal("1500.00")
    assert result.total_expense_actual == Decimal("1500.00")
    assert result.to_be_assigned == Decimal("3500.00")

    assert len(result.groups) == 2
    assert result.groups[0].name == "Income Group"
    assert result.groups[1].name == "Expenses Group"


def test_manager_get_budget_summary_empty_database(db_session):
    """Verify Manager behaves cleanly when database has no groups or transactions."""
    result = get_budget_summary(db_session, date(2026, 6, 1))

    assert isinstance(result, BudgetSummaryResult)
    assert len(result.groups) == 0
    assert result.total_income_planned == Decimal("0.00")
    assert result.total_income_actual == Decimal("0.00")
    assert result.total_expense_planned == Decimal("0.00")
    assert result.total_expense_actual == Decimal("0.00")
    assert result.to_be_assigned == Decimal("0.00")
