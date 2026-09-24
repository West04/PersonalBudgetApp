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
    # Verify account order (name ascending)
    assert dash_data["accounts"][0]["name"] == "Checking"
    assert dash_data["accounts"][1]["name"] == "Savings"

    # Recent transactions in Dashboard should include the 3 transactions in descending date order
    assert len(dash_data["recent_transactions"]) == 3
    assert dash_data["recent_transactions"][0]["date"] == "2026-06-10"
    assert dash_data["recent_transactions"][1]["date"] == "2026-06-05"
    assert dash_data["recent_transactions"][2]["date"] == "2026-06-01"
    # Verify nested account data is populated on recent transactions
    assert dash_data["recent_transactions"][0]["account"]["name"] == "Checking"


def test_dashboard_detail_characteristics(client, db_session):
    """
    Characterize specific Dashboard behaviors:
    1. Account balance fallback: current_balance = None falls back to 0.00.
    2. Account ordering: active accounts ordered by name ascending.
    3. Recent transactions limit: exactly 10 returned when >10 exist.
    4. Recent transactions ordering: strictly date descending.
    5. Recent transactions date filtering: transactions outside the requested month are excluded.
    """
    # 1. Accounts with alphabetical ordering and None current_balance
    acct_b = models.Account(name="Beta Checking", type="depository", current_balance=None, is_active=True)
    acct_a = models.Account(name="Alpha Savings", type="depository", current_balance=Decimal("250.00"), is_active=True)
    acct_c = models.Account(name="Inactive Acct", type="depository", current_balance=Decimal("1000.00"), is_active=False)
    db_session.add_all([acct_b, acct_a, acct_c])
    db_session.commit()

    # 2. Insert 12 transactions in June and 2 outside June
    for i in range(1, 13):
        db_session.add(
            models.Transaction(
                account_id=acct_a.id,
                description=f"June Tx {i:02d}",
                amount=Decimal("10.00"),
                date=date(2026, 6, i)
            )
        )
    # Outside June: May 31 and July 1
    db_session.add(
        models.Transaction(account_id=acct_a.id, description="May Tx", amount=Decimal("10.00"), date=date(2026, 5, 31))
    )
    db_session.add(
        models.Transaction(account_id=acct_a.id, description="July Tx", amount=Decimal("10.00"), date=date(2026, 7, 1))
    )
    db_session.commit()

    resp = client.get("/summary/dashboard?month=2026-06")
    assert resp.status_code == 200
    data = resp.json()

    # Verify accounts: only active, ordered by name ("Alpha Savings", then "Beta Checking")
    assert len(data["accounts"]) == 2
    assert data["accounts"][0]["name"] == "Alpha Savings"
    assert Decimal(str(data["accounts"][0]["current_balance"])) == Decimal("250.00")
    assert data["accounts"][1]["name"] == "Beta Checking"
    assert Decimal(str(data["accounts"][1]["current_balance"])) == Decimal("0.00")

    # Verify total_balance: 250.00 + 0.00 = 250.00 (inactive excluded)
    assert Decimal(str(data["total_balance"])) == Decimal("250.00")

    # Verify recent transactions: exactly 10 returned (out of 12 June txs), ordered date desc (June 12 down to June 3)
    recent = data["recent_transactions"]
    assert len(recent) == 10
    assert recent[0]["description"] == "June Tx 12"
    assert recent[0]["date"] == "2026-06-12"
    assert recent[9]["description"] == "June Tx 03"
    assert recent[9]["date"] == "2026-06-03"
    assert recent[0]["account"]["name"] == "Alpha Savings"
