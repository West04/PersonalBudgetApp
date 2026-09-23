from decimal import Decimal
from datetime import date
from uuid import uuid4
import pytest

from backend import models


def test_dashboard_vs_budget_summary_parity(client, db_session):
    """
    Test parity and consistency between:
    - GET /summary/budget?month=YYYY-MM
    - GET /summary/dashboard?month=YYYY-MM
    Both endpoints calculate ZBB metrics and must produce identical totals for the same dataset.
    """
    month_str = "2026-06"
    budget_month = date(2026, 6, 1)

    # 1. Accounts
    acct1 = models.Account(name="Checking", type="depository", current_balance=Decimal("1500.00"), is_active=True, currency="USD")
    acct2 = models.Account(name="Savings", type="depository", current_balance=Decimal("3500.00"), is_active=True, currency="USD")
    acct_inactive = models.Account(name="Old Closed", type="depository", current_balance=Decimal("999.00"), is_active=False, currency="USD")
    db_session.add_all([acct1, acct2, acct_inactive])
    db_session.flush()

    # 2. Groups & Categories (Using unique names to avoid collision with init_db)
    g_inc = models.CategoryGroup(name="Parity Income G", sort_order=20)
    g_exp = models.CategoryGroup(name="Parity Living G", sort_order=21)
    db_session.add_all([g_inc, g_exp])
    db_session.flush()

    c_salary = models.Category(name="Parity Salary C", group_id=g_inc.category_group_id, type="income", sort_order=0)
    c_rent = models.Category(name="Parity Rent C", group_id=g_exp.category_group_id, type="expense", sort_order=0)
    c_food = models.Category(name="Parity Food C", group_id=g_exp.category_group_id, type="expense", sort_order=1)
    db_session.add_all([c_salary, c_rent, c_food])
    db_session.flush()

    # 3. Budgets
    b_salary = models.Budget(budget_month=budget_month, planned_amount=Decimal("4000.00"), category_id=c_salary.category_id)
    b_rent = models.Budget(budget_month=budget_month, planned_amount=Decimal("1500.00"), category_id=c_rent.category_id)
    b_food = models.Budget(budget_month=budget_month, planned_amount=Decimal("500.00"), category_id=c_food.category_id)
    db_session.add_all([b_salary, b_rent, b_food])
    db_session.flush()

    # 4. Transactions in June with non-null descriptions (TransactionRead schema requires str)
    t_income = models.Transaction(
        account_id=acct1.id,
        category_id=c_salary.category_id,
        description="Employer Paycheck",
        amount=Decimal("-3800.00"),
        date=date(2026, 6, 5)
    )
    t_rent = models.Transaction(
        account_id=acct1.id,
        category_id=c_rent.category_id,
        description="June Rent",
        amount=Decimal("1500.00"),
        date=date(2026, 6, 1)
    )
    t_food = models.Transaction(
        account_id=acct1.id,
        category_id=c_food.category_id,
        description="Weekly Groceries",
        amount=Decimal("420.00"),
        date=date(2026, 6, 10)
    )
    db_session.add_all([t_income, t_rent, t_food])
    db_session.commit()

    # 5. Fetch both summaries
    res_budget = client.get(f"/summary/budget?month={month_str}")
    res_dash = client.get(f"/summary/dashboard?month={month_str}")

    assert res_budget.status_code == 200
    assert res_dash.status_code == 200

    budget_data = res_budget.json()
    dash_data = res_dash.json()

    # 6. Verify Exact Metric Parity
    # Income Planned
    assert Decimal(str(dash_data["income_planned"])) == Decimal(str(budget_data["total_income_planned"]))
    assert Decimal(str(dash_data["income_planned"])) == Decimal("4000.00")

    # Income Actual
    assert Decimal(str(dash_data["income_actual"])) == Decimal(str(budget_data["total_income_actual"]))
    assert Decimal(str(dash_data["income_actual"])) == Decimal("3800.00")

    # Expense Planned
    assert Decimal(str(dash_data["expense_planned"])) == Decimal(str(budget_data["total_expense_planned"]))
    assert Decimal(str(dash_data["expense_planned"])) == Decimal("2000.00")

    # Expense Actual
    assert Decimal(str(dash_data["expense_actual"])) == Decimal(str(budget_data["total_expense_actual"]))
    assert Decimal(str(dash_data["expense_actual"])) == Decimal("1920.00")

    # To Be Assigned: 4000 - 2000 = 2000.00
    assert Decimal(str(dash_data["to_be_assigned"])) == Decimal(str(budget_data["to_be_assigned"]))
    assert Decimal(str(dash_data["to_be_assigned"])) == Decimal("2000.00")

    # Total Balance in Dashboard: only active accounts (1500 + 3500 = 5000.00; inactive 999 excluded)
    assert Decimal(str(dash_data["total_balance"])) == Decimal("5000.00")
    assert len(dash_data["accounts"]) == 2

    # Recent transactions in Dashboard should include the 3 transactions
    assert len(dash_data["recent_transactions"]) == 3
