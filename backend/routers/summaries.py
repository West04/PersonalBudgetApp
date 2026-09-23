from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal

from .. import models, schemas
from ..access.budget_access import get_budgets_for_month
from ..access.category_access import get_category_groups
from ..access.transaction_access import get_actuals_by_category
from ..database import get_db
from ..domain.budgeting import (
    CategoryBudgetInput,
    GroupBudgetInput,
    calculate_budget_summary,
)

router = APIRouter(
    prefix="/summary",
    tags=["Summary"],
)

ZERO = Decimal("0.00")


def get_month_range(month_str: str) -> tuple[date, date]:
    """
    Parses a YYYY-MM string and returns:
      - start_date (inclusive)
      - end_date (exclusive)
    """
    try:
        start_date = datetime.strptime(month_str, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    if start_date.month == 12:
        end_date = date(start_date.year + 1, 1, 1)
    else:
        end_date = date(start_date.year, start_date.month + 1, 1)

    return start_date, end_date


@router.get("/budget", response_model=schemas.BudgetSummaryResponse)
def get_budget_summary(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    start_date, end_date = get_month_range(month)

    # 1) Fetch Groups and Categories via ResourceAccess
    groups = get_category_groups(db)

    # 2) Fetch Budgets for this month via ResourceAccess
    budgets = get_budgets_for_month(db, start_date)
    budget_map = {b.category_id: b for b in budgets}

    # 3) Fetch Transaction actuals for this month via ResourceAccess
    actual_map = get_actuals_by_category(db, start_date, end_date)

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

    budget_result = calculate_budget_summary(domain_groups)

    group_summaries = [
        schemas.BudgetGroupSummary(
            group_id=g.group_id,
            name=g.name,
            categories=[
                schemas.BudgetCategorySummary(
                    budget_id=c.budget_id,
                    category_id=c.category_id,
                    name=c.name,
                    type=c.type,
                    planned=c.planned,
                    actual=c.actual,
                    remaining=c.remaining,
                    is_over_budget=c.is_over_budget,
                )
                for c in g.categories
            ],
            total_planned=g.total_planned,
            total_actual=g.total_actual,
            total_remaining=g.total_remaining,
        )
        for g in budget_result.groups
    ]

    return schemas.BudgetSummaryResponse(
        month=month,
        groups=group_summaries,
        total_income_planned=budget_result.total_income_planned,
        total_income_actual=budget_result.total_income_actual,
        total_expense_planned=budget_result.total_expense_planned,
        total_expense_actual=budget_result.total_expense_actual,
        to_be_assigned=budget_result.to_be_assigned,
    )


@router.get("/dashboard", response_model=schemas.DashboardSummaryResponse)
def get_dashboard_summary(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    start_date, end_date = get_month_range(month)

    # 1) Fetch Groups and Categories (Eager loading)
    groups = (
        db.query(models.CategoryGroup)
        .options(selectinload(models.CategoryGroup.categories))
        .order_by(models.CategoryGroup.sort_order)
        .all()
    )

    # 2) Fetch Budgets for this month
    budgets = (
        db.query(models.Budget)
        .filter(models.Budget.budget_month == start_date)
        .all()
    )
    budget_map = {b.category_id: (b.planned_amount or ZERO) for b in budgets}

    # 3) Fetch Transaction actuals for this month, ignoring uncategorized
    trx_stats = (
        db.query(
            models.Transaction.category_id,
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(
            models.Transaction.date >= start_date,
            models.Transaction.date < end_date,
            models.Transaction.category_id.isnot(None),
        )
        .group_by(models.Transaction.category_id)
        .all()
    )
    actual_map = {t.category_id: (t.total or ZERO) for t in trx_stats}

    domain_groups = [
        GroupBudgetInput(
            group_id=group.category_group_id,
            name=group.name,
            categories=[
                CategoryBudgetInput(
                    category_id=cat.category_id,
                    name=cat.name,
                    type=cat.type,
                    planned=budget_map.get(cat.category_id, ZERO),
                    raw_actual=actual_map.get(cat.category_id, ZERO),
                )
                for cat in sorted(group.categories, key=lambda c: c.sort_order)
            ],
        )
        for group in groups
    ]

    budget_result = calculate_budget_summary(domain_groups)

    dashboard_groups = [
        schemas.DashboardGroupStat(
            group_id=g.group_id,
            name=g.name,
            planned=g.total_planned,
            actual=g.total_actual,
        )
        for g in budget_result.groups
    ]

    # ✅ 4) Accounts Snapshot (Persisted Plaid balances)
    # Use Account.current_balance instead of summing transactions
    accounts = (
        db.query(models.Account)
        .filter(models.Account.is_active == True)
        .order_by(models.Account.name.asc())
        .all()
    )

    account_summaries: List[schemas.DashboardAccountSummary] = []
    total_balance = ZERO

    for acc in accounts:
        current = acc.current_balance or ZERO
        total_balance += current

        account_summaries.append(
            schemas.DashboardAccountSummary(
                account_id=acc.id,
                name=acc.name,
                type=acc.type,
                subtype=acc.subtype,
                current_balance=current,
                available_balance=acc.available_balance,
                currency=getattr(acc, "currency", "USD") or "USD",
                balance_last_updated=getattr(acc, "balance_last_updated", None),
                is_active=acc.is_active,
            )
        )

    # 5) Recent Transactions (Filtered to current month)
    recent_txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.date >= start_date, models.Transaction.date < end_date)
        .order_by(models.Transaction.date.desc())
        .limit(10)
        .all()
    )
    recent_tx_reads = [schemas.TransactionRead.model_validate(tx) for tx in recent_txs]

    return schemas.DashboardSummaryResponse(
        month=month,
        income_planned=budget_result.total_income_planned,
        income_actual=budget_result.total_income_actual,
        expense_planned=budget_result.total_expense_planned,
        expense_actual=budget_result.total_expense_actual,
        total_balance=total_balance,
        to_be_assigned=budget_result.to_be_assigned,
        groups=dashboard_groups,
        accounts=account_summaries,
        recent_transactions=recent_tx_reads,
    )