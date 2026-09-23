from decimal import Decimal
from datetime import date
from uuid import uuid4
import pytest

from backend import models


def test_zbb_budget_summary_calculations(client, db_session):
    """
    Test the Zero-Based Budgeting calculation in GET /summary/budget?month=YYYY-MM:
    - total_income_planned, total_income_actual (with sign inversion)
    - total_expense_planned, total_expense_actual
    - to_be_assigned = total_income_planned - total_expense_planned
    - category remaining = planned - actual
    - category is_over_budget logic
    - transfer category behavior
    - refund / negative expense behavior
    """
    month_str = "2026-06"
    budget_month = date(2026, 6, 1)

    # 1. Create an Account
    account = models.Account(
        name="Primary Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("5000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD"
    )
    db_session.add(account)

    # 2. Create Category Groups with unique names to avoid collisions with init_db seeds
    income_group = models.CategoryGroup(name="Custom Income Group", sort_order=10)
    expense_group = models.CategoryGroup(name="Custom Expenses Group", sort_order=11)
    transfer_group = models.CategoryGroup(name="Custom Transfers Group", sort_order=12)
    db_session.add_all([income_group, expense_group, transfer_group])
    db_session.flush()

    # 3. Create Categories
    # Income category
    cat_salary = models.Category(name="Custom Salary", group_id=income_group.category_group_id, type="income", sort_order=0)
    # Expense categories
    cat_rent = models.Category(name="Custom Rent", group_id=expense_group.category_group_id, type="expense", sort_order=0)
    cat_groceries = models.Category(name="Custom Groceries", group_id=expense_group.category_group_id, type="expense", sort_order=1)
    cat_shopping = models.Category(name="Custom Shopping", group_id=expense_group.category_group_id, type="expense", sort_order=2)
    cat_dining = models.Category(name="Custom Dining Out", group_id=expense_group.category_group_id, type="expense", sort_order=3)
    # Transfer category
    cat_transfer = models.Category(name="Custom Savings Transfer", group_id=transfer_group.category_group_id, type="transfer", sort_order=0)

    db_session.add_all([cat_salary, cat_rent, cat_groceries, cat_shopping, cat_dining, cat_transfer])
    db_session.flush()

    # 4. Set Planned Budgets for the month
    # Salary: planned 5000.00
    b_salary = models.Budget(budget_month=budget_month, planned_amount=Decimal("5000.00"), category_id=cat_salary.category_id)
    # Rent: planned 2000.00
    b_rent = models.Budget(budget_month=budget_month, planned_amount=Decimal("2000.00"), category_id=cat_rent.category_id)
    # Groceries: planned 600.00
    b_groceries = models.Budget(budget_month=budget_month, planned_amount=Decimal("600.00"), category_id=cat_groceries.category_id)
    # Shopping: planned 2400.00 (Total expense planned: 2000 + 600 + 2400 = 5000 -> to_be_assigned = 0)
    b_shopping = models.Budget(budget_month=budget_month, planned_amount=Decimal("2400.00"), category_id=cat_shopping.category_id)
    # Dining: planned 0.00 (Zero planned budget)
    b_dining = models.Budget(budget_month=budget_month, planned_amount=Decimal("0.00"), category_id=cat_dining.category_id)
    # Transfer: planned 300.00 (Should be excluded from high-level totals)
    b_transfer = models.Budget(budget_month=budget_month, planned_amount=Decimal("300.00"), category_id=cat_transfer.category_id)

    db_session.add_all([b_salary, b_rent, b_groceries, b_shopping, b_dining, b_transfer])
    db_session.flush()

    # 5. Add Transactions for June 2026
    # Salary inflow (negative in app convention: -4800.00)
    tx_salary = models.Transaction(
        account_id=account.id,
        category_id=cat_salary.category_id,
        description="Employer Paycheck",
        amount=Decimal("-4800.00"),
        date=date(2026, 6, 5)
    )
    # Rent paid: +2000.00 (exact)
    tx_rent = models.Transaction(
        account_id=account.id,
        category_id=cat_rent.category_id,
        description="Rent June",
        amount=Decimal("2000.00"),
        date=date(2026, 6, 1)
    )
    # Groceries: over-budget! spent 750.00 against 600.00
    tx_groc1 = models.Transaction(
        account_id=account.id,
        category_id=cat_groceries.category_id,
        description="Groceries Trip 1",
        amount=Decimal("450.00"),
        date=date(2026, 6, 8)
    )
    tx_groc2 = models.Transaction(
        account_id=account.id,
        category_id=cat_groceries.category_id,
        description="Groceries Trip 2",
        amount=Decimal("300.00"),
        date=date(2026, 6, 20)
    )
    # Shopping: spent 200.00, but got a refund of -50.00 (net actual = 150.00)
    tx_shop1 = models.Transaction(
        account_id=account.id,
        category_id=cat_shopping.category_id,
        description="Shoes purchase",
        amount=Decimal("200.00"),
        date=date(2026, 6, 12)
    )
    tx_shop_refund = models.Transaction(
        account_id=account.id,
        category_id=cat_shopping.category_id,
        description="Shoes return refund",
        amount=Decimal("-50.00"),
        date=date(2026, 6, 15)
    )
    # Dining: spent 80.00 with 0.00 planned -> over budget
    tx_dining = models.Transaction(
        account_id=account.id,
        category_id=cat_dining.category_id,
        description="Dinner Out",
        amount=Decimal("80.00"),
        date=date(2026, 6, 18)
    )
    # Transfer transaction: 300.00
    tx_trans = models.Transaction(
        account_id=account.id,
        category_id=cat_transfer.category_id,
        description="Transfer to savings",
        amount=Decimal("300.00"),
        date=date(2026, 6, 22),
        is_transfer=True
    )
    # Transaction in July (should be ignored in June summary!)
    tx_july = models.Transaction(
        account_id=account.id,
        category_id=cat_rent.category_id,
        description="July Rent Early",
        amount=Decimal("2000.00"),
        date=date(2026, 7, 1)
    )

    db_session.add_all([
        tx_salary, tx_rent, tx_groc1, tx_groc2,
        tx_shop1, tx_shop_refund, tx_dining, tx_trans, tx_july
    ])
    db_session.commit()

    # 6. Call the endpoint
    resp = client.get(f"/summary/budget?month={month_str}")
    assert resp.status_code == 200
    data = resp.json()

    # 7. Assert High-Level Zero-Based Budgeting Totals
    # Total Income Planned: 5000.00
    assert Decimal(str(data["total_income_planned"])) == Decimal("5000.00")
    # Total Income Actual: raw inflow is -4800.00, converted to positive actual income 4800.00
    assert Decimal(str(data["total_income_actual"])) == Decimal("4800.00")

    # Total Expense Planned: Rent(2000) + Groceries(600) + Shopping(2400) + Dining(0) = 5000.00
    # Transfer category (300) must be excluded from total_expense_planned!
    assert Decimal(str(data["total_expense_planned"])) == Decimal("5000.00")

    # Total Expense Actual: Rent(2000) + Groceries(750) + Shopping(150) + Dining(80) = 2980.00
    # Transfer category (300) must be excluded from total_expense_actual!
    assert Decimal(str(data["total_expense_actual"])) == Decimal("2980.00")

    # To Be Assigned: total_income_planned (5000) - total_expense_planned (5000) = 0.00
    assert Decimal(str(data["to_be_assigned"])) == Decimal("0.00")

    # 8. Assert Category-Level Math by ID
    categories_by_id = {}
    for group in data["groups"]:
        for cat in group["categories"]:
            categories_by_id[cat["category_id"]] = cat

    # Salary: planned 5000, actual 4800, remaining 200, is_over_budget False
    sal = categories_by_id[str(cat_salary.category_id)]
    assert Decimal(str(sal["planned"])) == Decimal("5000.00")
    assert Decimal(str(sal["actual"])) == Decimal("4800.00")
    assert Decimal(str(sal["remaining"])) == Decimal("200.00")
    assert sal["is_over_budget"] is False

    # Rent: planned 2000, actual 2000, remaining 0, is_over_budget False
    rent = categories_by_id[str(cat_rent.category_id)]
    assert Decimal(str(rent["planned"])) == Decimal("2000.00")
    assert Decimal(str(rent["actual"])) == Decimal("2000.00")
    assert Decimal(str(rent["remaining"])) == Decimal("0.00")
    assert rent["is_over_budget"] is False

    # Groceries: planned 600, actual 750, remaining -150, is_over_budget True
    groc = categories_by_id[str(cat_groceries.category_id)]
    assert Decimal(str(groc["planned"])) == Decimal("600.00")
    assert Decimal(str(groc["actual"])) == Decimal("750.00")
    assert Decimal(str(groc["remaining"])) == Decimal("-150.00")
    assert groc["is_over_budget"] is True

    # Shopping: planned 2400, actual 150 (200 - 50 refund), remaining 2250, is_over_budget False
    shop = categories_by_id[str(cat_shopping.category_id)]
    assert Decimal(str(shop["planned"])) == Decimal("2400.00")
    assert Decimal(str(shop["actual"])) == Decimal("150.00")
    assert Decimal(str(shop["remaining"])) == Decimal("2250.00")
    assert shop["is_over_budget"] is False

    # Dining: planned 0, actual 80, remaining -80, is_over_budget True
    din = categories_by_id[str(cat_dining.category_id)]
    assert Decimal(str(din["planned"])) == Decimal("0.00")
    assert Decimal(str(din["actual"])) == Decimal("80.00")
    assert Decimal(str(din["remaining"])) == Decimal("-80.00")
    assert din["is_over_budget"] is True
