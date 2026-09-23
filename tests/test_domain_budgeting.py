from decimal import Decimal
from uuid import uuid4
import pytest

from backend.domain.budgeting import (
    CategoryBudgetInput,
    GroupBudgetInput,
    calculate_actual,
    calculate_remaining,
    calculate_is_over_budget,
    calculate_to_be_assigned,
    calculate_category_summary,
    calculate_group_summary,
    calculate_budget_summary,
    ZERO,
)


def test_calculate_actual():
    # Income: negative transaction inflow -> positive actual
    assert calculate_actual("income", Decimal("-2500.00")) == Decimal("2500.00")
    assert calculate_actual("income", None) == ZERO
    assert calculate_actual("income", ZERO) == ZERO

    # Expense: positive transaction outflow -> positive actual
    assert calculate_actual("expense", Decimal("45.50")) == Decimal("45.50")
    # Expense refund (negative inflow) -> negative actual
    assert calculate_actual("expense", Decimal("-15.00")) == Decimal("-15.00")
    assert calculate_actual("expense", None) == ZERO

    # Transfer: preserves raw amount
    assert calculate_actual("transfer", Decimal("200.00")) == Decimal("200.00")
    assert calculate_actual("transfer", None) == ZERO


def test_calculate_remaining():
    # Standard under-budget
    assert calculate_remaining(Decimal("500.00"), Decimal("350.00")) == Decimal("150.00")
    # Exact match
    assert calculate_remaining(Decimal("500.00"), Decimal("500.00")) == Decimal("0.00")
    # Over-budget
    assert calculate_remaining(Decimal("500.00"), Decimal("650.00")) == Decimal("-150.00")
    # None inputs default to 0.00
    assert calculate_remaining(None, Decimal("100.00")) == Decimal("-100.00")
    assert calculate_remaining(Decimal("100.00"), None) == Decimal("100.00")


def test_calculate_is_over_budget():
    # Income categories never flag as over-budget
    assert calculate_is_over_budget("income", Decimal("-500.00")) is False
    assert calculate_is_over_budget("income", Decimal("0.00")) is False
    assert calculate_is_over_budget("income", Decimal("500.00")) is False

    # Expense categories flag over-budget when remaining < 0
    assert calculate_is_over_budget("expense", Decimal("-0.01")) is True
    assert calculate_is_over_budget("expense", Decimal("0.00")) is False
    assert calculate_is_over_budget("expense", Decimal("50.00")) is False

    # Transfer categories flag over-budget when remaining < 0
    assert calculate_is_over_budget("transfer", Decimal("-10.00")) is True
    assert calculate_is_over_budget("transfer", Decimal("0.00")) is False


def test_calculate_to_be_assigned():
    # Balanced zero-based budget
    assert calculate_to_be_assigned(Decimal("5000.00"), Decimal("5000.00")) == Decimal("0.00")
    # Under-assigned (more income planned than expenses)
    assert calculate_to_be_assigned(Decimal("5000.00"), Decimal("4200.00")) == Decimal("800.00")
    # Over-budgeted (more expenses planned than income)
    assert calculate_to_be_assigned(Decimal("5000.00"), Decimal("5500.00")) == Decimal("-500.00")


def test_calculate_category_summary():
    cat_id = uuid4()
    b_id = uuid4()

    # Expense category
    input_cat = CategoryBudgetInput(
        category_id=cat_id,
        name="Groceries",
        type="expense",
        planned=Decimal("400.00"),
        raw_actual=Decimal("450.00"),
        budget_id=b_id,
    )
    res = calculate_category_summary(input_cat)
    assert res.category_id == cat_id
    assert res.name == "Groceries"
    assert res.type == "expense"
    assert res.planned == Decimal("400.00")
    assert res.actual == Decimal("450.00")
    assert res.remaining == Decimal("-50.00")
    assert res.is_over_budget is True
    assert res.budget_id == b_id

    # Income category
    input_income = CategoryBudgetInput(
        category_id=cat_id,
        name="Salary",
        type="income",
        planned=Decimal("5000.00"),
        raw_actual=Decimal("-5200.00"),
    )
    res_inc = calculate_category_summary(input_income)
    assert res_inc.planned == Decimal("5000.00")
    assert res_inc.actual == Decimal("5200.00")
    assert res_inc.remaining == Decimal("-200.00")
    assert res_inc.is_over_budget is False


def test_calculate_budget_summary_full():
    gid1, gid2, gid3 = uuid4(), uuid4(), uuid4()

    # Income Group
    g_income = GroupBudgetInput(
        group_id=gid1,
        name="Income Group",
        categories=[
            CategoryBudgetInput(
                category_id=uuid4(),
                name="Salary",
                type="income",
                planned=Decimal("5000.00"),
                raw_actual=Decimal("-4800.00"),
            ),
        ],
    )

    # Expense Group
    g_expense = GroupBudgetInput(
        group_id=gid2,
        name="Living Expenses",
        categories=[
            CategoryBudgetInput(
                category_id=uuid4(),
                name="Rent",
                type="expense",
                planned=Decimal("2000.00"),
                raw_actual=Decimal("2000.00"),
            ),
            CategoryBudgetInput(
                category_id=uuid4(),
                name="Food",
                type="expense",
                planned=Decimal("600.00"),
                raw_actual=Decimal("750.00"),
            ),
            CategoryBudgetInput(
                category_id=uuid4(),
                name="Shopping",
                type="expense",
                planned=Decimal("2400.00"),
                raw_actual=Decimal("150.00"),
            ),
        ],
    )

    # Transfer Group (should be excluded from high-level totals)
    g_transfer = GroupBudgetInput(
        group_id=gid3,
        name="Transfers",
        categories=[
            CategoryBudgetInput(
                category_id=uuid4(),
                name="Savings Transfer",
                type="transfer",
                planned=Decimal("300.00"),
                raw_actual=Decimal("300.00"),
            ),
        ],
    )

    summary = calculate_budget_summary([g_income, g_expense, g_transfer])

    # Income totals
    assert summary.total_income_planned == Decimal("5000.00")
    assert summary.total_income_actual == Decimal("4800.00")

    # Expense totals (Rent 2000 + Food 600 + Shopping 2400 = 5000.00; Transfer 300 excluded)
    assert summary.total_expense_planned == Decimal("5000.00")
    # Expense actuals (2000 + 750 + 150 = 2900.00; Transfer 300 excluded)
    assert summary.total_expense_actual == Decimal("2900.00")

    # Zero-based budget: 5000 - 5000 = 0.00
    assert summary.to_be_assigned == Decimal("0.00")

    # Groups verification
    assert len(summary.groups) == 3
    # Group 1 totals
    assert summary.groups[0].total_planned == Decimal("5000.00")
    assert summary.groups[0].total_actual == Decimal("4800.00")
    assert summary.groups[0].total_remaining == Decimal("200.00")

    # Group 2 totals
    assert summary.groups[1].total_planned == Decimal("5000.00")
    assert summary.groups[1].total_actual == Decimal("2900.00")
    assert summary.groups[1].total_remaining == Decimal("2100.00")

    # Group 3 totals
    assert summary.groups[2].total_planned == Decimal("300.00")
    assert summary.groups[2].total_actual == Decimal("300.00")
    assert summary.groups[2].total_remaining == Decimal("0.00")
