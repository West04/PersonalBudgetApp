"""
Manager for the Budget Summary workflow.

Coordinates:
1. Determination of the budget period [start_date, end_date).
2. Data retrieval via ResourceAccess (category groups, budgets, transaction actuals).
3. Mapping raw records to domain input models (GroupBudgetInput, CategoryBudgetInput).
4. Invocation of the pure Budget Engine (calculate_budget_summary).
"""

from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session

from ..access.budget_access import get_budgets_for_month
from ..access.category_access import get_category_groups
from ..access.transaction_access import get_actuals_by_category
from ..domain.budgeting import (
    BudgetSummaryResult,
    CategoryBudgetInput,
    GroupBudgetInput,
    calculate_budget_summary,
)

ZERO = Decimal("0.00")


def determine_month_range(budget_month: date) -> tuple[date, date]:
    """
    Determines the half-open interval [start_date, end_date) for a budget month.
    """
    start_date = date(budget_month.year, budget_month.month, 1)
    if start_date.month == 12:
        end_date = date(start_date.year + 1, 1, 1)
    else:
        end_date = date(start_date.year, start_date.month + 1, 1)
    return start_date, end_date


def get_budget_summary(
    db: Session,
    budget_month: date,
) -> BudgetSummaryResult:
    """
    Coordinates the budget summary workflow:
    1. Determines period dates.
    2. Retrieves data from ResourceAccess.
    3. Assembles domain inputs.
    4. Calculates budget summary via Budget Engine.
    """
    start_date, end_date = determine_month_range(budget_month)

    # 1. Fetch raw data from ResourceAccess
    groups = get_category_groups(db)
    budgets = get_budgets_for_month(db, start_date)
    budget_map = {b.category_id: b for b in budgets}
    actual_map = get_actuals_by_category(db, start_date, end_date)

    # 2. Assemble domain inputs
    domain_groups = [
        GroupBudgetInput(
            group_id=group.category_group_id,
            name=group.name,
            categories=[
                CategoryBudgetInput(
                    category_id=cat.category_id,
                    name=cat.name,
                    type=cat.type,
                    planned=(budget_map[cat.category_id].planned_amount or ZERO) if cat.category_id in budget_map else ZERO,
                    raw_actual=actual_map.get(cat.category_id, ZERO),
                    budget_id=budget_map[cat.category_id].budget_id if cat.category_id in budget_map else None,
                )
                for cat in sorted(group.categories, key=lambda c: c.sort_order)
            ],
        )
        for group in groups
    ]

    # 3. Invoke pure Budget Engine
    return calculate_budget_summary(domain_groups)
