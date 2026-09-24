from datetime import date
from decimal import Decimal
from unittest.mock import patch
import pytest

from backend import models
from backend.domain.budgeting import BudgetSummaryResult
from backend.managers import budget_summary_manager
from backend.managers.dashboard_summary_manager import (
    DashboardAccountItem,
    DashboardRecentTransactionItem,
    DashboardSummaryResult,
    DashboardTransactionAccountItem,
    get_dashboard_summary,
)


def test_manager_get_dashboard_summary_composition(db_session):
    """
    Verify get_dashboard_summary coordinates:
    - Reuse of BudgetSummaryManager.
    - Active account retrieval, ordering, None balance -> 0.00 fallback.
    - Total balance calculation across active accounts.
    - Recent transaction retrieval for the month (descending order, limit 10).
    - Mapping to immutable application dataclasses without ORM model leakage.
    """
    # 1. Setup Category Groups & Categories
    g_income = models.CategoryGroup(name="Income Group", sort_order=1)
    g_expense = models.CategoryGroup(name="Expenses Group", sort_order=2)
    db_session.add_all([g_income, g_expense])
    db_session.flush()

    cat_salary = models.Category(
        group_id=g_income.category_group_id,
        name="Salary",
        type="income",
        sort_order=1,
    )
    cat_groceries = models.Category(
        group_id=g_expense.category_group_id,
        name="Groceries",
        type="expense",
        sort_order=1,
    )
    db_session.add_all([cat_salary, cat_groceries])
    db_session.flush()

    # 2. Setup Budgets for June 2026
    b_salary = models.Budget(
        category_id=cat_salary.category_id,
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("4000.00"),
    )
    b_groceries = models.Budget(
        category_id=cat_groceries.category_id,
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("600.00"),
    )
    db_session.add_all([b_salary, b_groceries])

    # 3. Setup Accounts:
    # - Account A: Alpha Savings, active, balance 1000.00
    # - Account B: Beta Checking, active, balance None (tests fallback to 0.00)
    # - Account C: Gamma Credit, active, balance 250.50
    # - Account D: Omega Inactive, inactive, balance 9999.00 (must be excluded)
    acc_a = models.Account(
        name="Alpha Savings",
        type="depository",
        subtype="savings",
        current_balance=Decimal("1000.00"),
        is_active=True,
    )
    acc_b = models.Account(
        name="Beta Checking",
        type="depository",
        subtype="checking",
        current_balance=None,
        is_active=True,
    )
    acc_c = models.Account(
        name="Gamma Credit",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("250.50"),
        is_active=True,
    )
    acc_d = models.Account(
        name="Omega Inactive",
        type="depository",
        subtype="checking",
        current_balance=Decimal("9999.00"),
        is_active=False,
    )
    db_session.add_all([acc_a, acc_b, acc_c, acc_d])
    db_session.flush()

    # 4. Setup Transactions for June 2026:
    # 1 income transaction, 2 expense transactions, 1 outside June (May)
    tx_income = models.Transaction(
        account_id=acc_b.id,
        category_id=cat_salary.category_id,
        description="Paycheck",
        amount=Decimal("-4000.00"),
        date=date(2026, 6, 5),
    )
    tx_groceries_1 = models.Transaction(
        account_id=acc_a.id,
        category_id=cat_groceries.category_id,
        description="Supermarket A",
        amount=Decimal("150.00"),
        date=date(2026, 6, 10),
    )
    tx_groceries_2 = models.Transaction(
        account_id=acc_a.id,
        category_id=cat_groceries.category_id,
        description="Supermarket B",
        amount=Decimal("80.00"),
        date=date(2026, 6, 12),
    )
    tx_may = models.Transaction(
        account_id=acc_a.id,
        category_id=cat_groceries.category_id,
        description="Old Expense",
        amount=Decimal("50.00"),
        date=date(2026, 5, 28),
    )
    db_session.add_all([tx_income, tx_groceries_1, tx_groceries_2, tx_may])
    db_session.commit()

    # Run Manager workflow
    result = get_dashboard_summary(db_session, date(2026, 6, 1))

    # Assert top-level structure
    assert isinstance(result, DashboardSummaryResult)

    # 1. Verify budget summary composition
    assert isinstance(result.budget_summary, BudgetSummaryResult)
    assert result.budget_summary.total_income_planned == Decimal("4000.00")
    assert result.budget_summary.total_income_actual == Decimal("4000.00")
    assert result.budget_summary.total_expense_planned == Decimal("600.00")
    assert result.budget_summary.total_expense_actual == Decimal("230.00")
    assert result.budget_summary.to_be_assigned == Decimal("3400.00")

    # 2. Verify accounts mapping, filtering, and ordering
    assert len(result.accounts) == 3
    assert [a.name for a in result.accounts] == ["Alpha Savings", "Beta Checking", "Gamma Credit"]
    assert all(isinstance(a, DashboardAccountItem) for a in result.accounts)

    # Verify None fallback to 0.00
    beta_acc = next(a for a in result.accounts if a.name == "Beta Checking")
    assert beta_acc.current_balance == Decimal("0.00")

    # 3. Verify total balance: 1000.00 + 0.00 + 250.50 = 1250.50 (excluding inactive 9999.00)
    assert result.total_balance == Decimal("1250.50")

    # 4. Verify recent transactions (only June, descending date, mapped to dataclasses)
    assert len(result.recent_transactions) == 3
    assert all(isinstance(t, DashboardRecentTransactionItem) for t in result.recent_transactions)
    # Ordered descending: June 12, June 10, June 5
    assert result.recent_transactions[0].description == "Supermarket B"
    assert result.recent_transactions[0].date == date(2026, 6, 12)
    assert result.recent_transactions[1].description == "Supermarket A"
    assert result.recent_transactions[1].date == date(2026, 6, 10)
    assert result.recent_transactions[2].description == "Paycheck"
    assert result.recent_transactions[2].date == date(2026, 6, 5)

    # 5. Verify nested account data is an application dataclass
    for t in result.recent_transactions:
        assert isinstance(t.account, DashboardTransactionAccountItem)
        assert not isinstance(t.account, models.Account)


def test_manager_get_dashboard_summary_reuses_budget_summary_manager(db_session):
    """
    Verify get_dashboard_summary directly delegates to budget_summary_manager.get_budget_summary
    without independently recalculating or invoking the budget engine.
    """
    dummy_budget_result = BudgetSummaryResult(
        groups=[],
        total_income_planned=Decimal("111.00"),
        total_income_actual=Decimal("222.00"),
        total_expense_planned=Decimal("333.00"),
        total_expense_actual=Decimal("444.00"),
        to_be_assigned=Decimal("555.00"),
    )

    with patch.object(
        budget_summary_manager,
        "get_budget_summary",
        return_value=dummy_budget_result,
    ) as mock_budget_mgr:
        result = get_dashboard_summary(db_session, date(2026, 6, 1))

        mock_budget_mgr.assert_called_once_with(db_session, date(2026, 6, 1))
        assert result.budget_summary == dummy_budget_result


def test_manager_get_dashboard_summary_empty_database(db_session):
    """Verify clean behavior with an empty database."""
    result = get_dashboard_summary(db_session, date(2026, 6, 1))

    assert isinstance(result, DashboardSummaryResult)
    assert isinstance(result.budget_summary, BudgetSummaryResult)
    assert len(result.budget_summary.groups) == 0
    assert result.total_balance == Decimal("0.00")
    assert len(result.accounts) == 0
    assert len(result.recent_transactions) == 0
