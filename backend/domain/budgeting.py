"""
Pure domain functions and structures for Zero-Based Budget (ZBB) calculations.

Rules & Invariants:
1. Transaction monetary sign convention: Outflow > 0, Inflow < 0.
   - For display actuals, income inflows are inverted to positive numbers.
   - Expense outflows remain positive (or negative if net refunds exceed spending).
2. Category remaining:
   - remaining = planned - actual
   - is_over_budget: False for income; (remaining < 0) for expense and transfer categories.
3. High-level totals:
   - total_income_planned = sum of planned amounts for income categories
   - total_income_actual = sum of actual amounts for income categories
   - total_expense_planned = sum of planned amounts for expense categories
   - total_expense_actual = sum of actual amounts for expense categories
   - Transfer categories are excluded from high-level income/expense totals.
4. Zero-Based Budgeting:
   - to_be_assigned = total_income_planned - total_expense_planned
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class CategoryBudgetInput:
    category_id: UUID
    name: str
    type: str  # "income" | "expense" | "transfer"
    planned: Decimal = ZERO
    raw_actual: Decimal = ZERO
    budget_id: Optional[UUID] = None


@dataclass(frozen=True)
class GroupBudgetInput:
    group_id: UUID
    name: str
    categories: List[CategoryBudgetInput]


@dataclass(frozen=True)
class CategoryBudgetResult:
    category_id: UUID
    name: str
    type: str
    planned: Decimal
    actual: Decimal
    remaining: Decimal
    is_over_budget: bool
    budget_id: Optional[UUID] = None


@dataclass(frozen=True)
class GroupBudgetResult:
    group_id: UUID
    name: str
    categories: List[CategoryBudgetResult]
    total_planned: Decimal
    total_actual: Decimal
    total_remaining: Decimal


@dataclass(frozen=True)
class BudgetSummaryResult:
    groups: List[GroupBudgetResult]
    total_income_planned: Decimal
    total_income_actual: Decimal
    total_expense_planned: Decimal
    total_expense_actual: Decimal
    to_be_assigned: Decimal


def calculate_actual(category_type: str, raw_actual: Optional[Decimal]) -> Decimal:
    """
    Computes the display actual amount for a category.
    - Income inflows are negative in the transaction ledger, so they are inverted to positive.
    - Expenses and transfers retain their raw amounts.
    """
    if not raw_actual:
        return ZERO
    if category_type == "income":
        return -raw_actual
    return raw_actual


def calculate_remaining(planned: Optional[Decimal], actual: Optional[Decimal]) -> Decimal:
    """Computes remaining amount: planned - actual."""
    p = planned if planned is not None else ZERO
    a = actual if actual is not None else ZERO
    return p - a


def calculate_is_over_budget(category_type: str, remaining: Decimal) -> bool:
    """
    Determines whether a category is over budget.
    Income categories never flag as over budget.
    Expense and transfer categories are over budget when remaining < 0.
    """
    if category_type == "income":
        return False
    return remaining < ZERO


def calculate_to_be_assigned(total_income_planned: Decimal, total_expense_planned: Decimal) -> Decimal:
    """Zero-based budgeting calculation: total_income_planned - total_expense_planned."""
    return total_income_planned - total_expense_planned


def calculate_category_summary(category: CategoryBudgetInput) -> CategoryBudgetResult:
    """Calculates metrics for a single category."""
    planned = category.planned if category.planned is not None else ZERO
    actual = calculate_actual(category.type, category.raw_actual)
    remaining = calculate_remaining(planned, actual)
    is_over_budget = calculate_is_over_budget(category.type, remaining)
    return CategoryBudgetResult(
        category_id=category.category_id,
        name=category.name,
        type=category.type,
        planned=planned,
        actual=actual,
        remaining=remaining,
        is_over_budget=is_over_budget,
        budget_id=category.budget_id,
    )


def calculate_group_summary(group: GroupBudgetInput) -> GroupBudgetResult:
    """Calculates metrics for a category group and its categories."""
    cat_summaries: List[CategoryBudgetResult] = []
    group_planned = ZERO
    group_actual = ZERO
    group_remaining = ZERO

    for cat in group.categories:
        cat_result = calculate_category_summary(cat)
        cat_summaries.append(cat_result)
        group_planned += cat_result.planned
        group_actual += cat_result.actual
        group_remaining += cat_result.remaining

    return GroupBudgetResult(
        group_id=group.group_id,
        name=group.name,
        categories=cat_summaries,
        total_planned=group_planned,
        total_actual=group_actual,
        total_remaining=group_remaining,
    )


def calculate_budget_summary(groups: List[GroupBudgetInput]) -> BudgetSummaryResult:
    """
    Calculates the full monthly zero-based budget summary across all groups.
    Income categories contribute to total_income_planned and total_income_actual.
    Expense categories contribute to total_expense_planned and total_expense_actual.
    Transfer categories are excluded from high-level totals.
    to_be_assigned = total_income_planned - total_expense_planned.
    """
    group_summaries: List[GroupBudgetResult] = []
    total_income_planned = ZERO
    total_income_actual = ZERO
    total_expense_planned = ZERO
    total_expense_actual = ZERO

    for group in groups:
        group_result = calculate_group_summary(group)
        group_summaries.append(group_result)

        for cat_result in group_result.categories:
            if cat_result.type == "income":
                total_income_planned += cat_result.planned
                total_income_actual += cat_result.actual
            elif cat_result.type == "expense":
                total_expense_planned += cat_result.planned
                total_expense_actual += cat_result.actual
            # Transfer categories are excluded from high-level totals

    to_be_assigned = calculate_to_be_assigned(total_income_planned, total_expense_planned)

    return BudgetSummaryResult(
        groups=group_summaries,
        total_income_planned=total_income_planned,
        total_income_actual=total_income_actual,
        total_expense_planned=total_expense_planned,
        total_expense_actual=total_expense_actual,
        to_be_assigned=to_be_assigned,
    )
