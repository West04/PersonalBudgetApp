from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from datetime import datetime, date
from decimal import Decimal

from .. import models, schemas
from ..database import get_db

router = APIRouter(
    prefix="/summary",
    tags=["Summary"],
)

ZERO = Decimal("0.00")

def get_month_range(month_str: str):
    """
    Parses a YYYY-MM string and returns the start date (inclusive) 
    and end date (exclusive) for that month.
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
    
    # 1. Fetch Groups and Categories (Eager loading categories to avoid N+1)
    groups = (
        db.query(models.CategoryGroup)
        .options(selectinload(models.CategoryGroup.categories))
        .order_by(models.CategoryGroup.sort_order)
        .all()
    )
    
    # 2. Fetch Budgets for this month
    budgets = db.query(models.Budget).filter(models.Budget.budget_month == start_date).all()
    budget_map = {b.category_id: b.planned_amount for b in budgets}
    
    # 3. Fetch Transactions for this month (Actuals), ignoring uncategorized
    trx_stats = db.query(
        models.Transaction.category_id,
        func.sum(models.Transaction.amount).label("total")
    ).filter(
        models.Transaction.date >= start_date,
        models.Transaction.date < end_date,
        models.Transaction.category_id.isnot(None)
    ).group_by(models.Transaction.category_id).all()
    
    actual_map = {t.category_id: (t.total or ZERO) for t in trx_stats}
    
    # Build Response
    group_summaries = []
    
    total_income_planned = ZERO
    total_income_actual = ZERO
    total_expense_planned = ZERO
    total_expense_actual = ZERO
    
    for group in groups:
        cat_summaries = []
        group_planned = ZERO
        group_actual = ZERO
        group_remaining = ZERO
        
        # Explicit sorting by sort_order
        sorted_categories = sorted(group.categories, key=lambda c: c.sort_order)
        
        for cat in sorted_categories:
            planned = budget_map.get(cat.category_id, ZERO)
            raw_actual = actual_map.get(cat.category_id, ZERO)
            
            if cat.type == "income":
                actual = -raw_actual if raw_actual else ZERO
                remaining = planned - actual 
                is_over_budget = False
                
                total_income_planned += planned
                total_income_actual += actual
                
            elif cat.type == "expense":
                actual = raw_actual if raw_actual else ZERO
                remaining = planned - actual
                is_over_budget = remaining < ZERO
                
                total_expense_planned += planned
                total_expense_actual += actual
            
            else: # transfer
                actual = raw_actual if raw_actual else ZERO
                remaining = planned - actual
                is_over_budget = remaining < ZERO
                # Transfers are excluded from high-level income/expense totals

            group_planned += planned
            group_actual += actual
            group_remaining += remaining
            
            cat_summaries.append(schemas.BudgetCategorySummary(
                category_id=cat.category_id,
                name=cat.name,
                type=cat.type,
                planned=planned,
                actual=actual,
                remaining=remaining,
                is_over_budget=is_over_budget
            ))
            
        group_summaries.append(schemas.BudgetGroupSummary(
            group_id=group.category_group_id,
            name=group.name,
            categories=cat_summaries,
            total_planned=group_planned,
            total_actual=group_actual,
            total_remaining=group_remaining
        ))
        
    return schemas.BudgetSummaryResponse(
        month=month,
        groups=group_summaries,
        total_income_planned=total_income_planned,
        total_income_actual=total_income_actual,
        total_expense_planned=total_expense_planned,
        total_expense_actual=total_expense_actual
    )


@router.get("/dashboard", response_model=schemas.DashboardSummaryResponse)
def get_dashboard_summary(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    start_date, end_date = get_month_range(month)
    
    # 1. Fetch Groups and Categories (Eager loading)
    groups = (
        db.query(models.CategoryGroup)
        .options(selectinload(models.CategoryGroup.categories))
        .order_by(models.CategoryGroup.sort_order)
        .all()
    )
    
    # 2. Fetch Budgets
    budgets = db.query(models.Budget).filter(models.Budget.budget_month == start_date).all()
    budget_map = {b.category_id: b.planned_amount for b in budgets}
    
    # 3. Fetch Transaction Stats (Actuals), ignoring uncategorized
    trx_stats = db.query(
        models.Transaction.category_id,
        func.sum(models.Transaction.amount).label("total")
    ).filter(
        models.Transaction.date >= start_date,
        models.Transaction.date < end_date,
        models.Transaction.category_id.isnot(None)
    ).group_by(models.Transaction.category_id).all()
    actual_map = {t.category_id: (t.total or ZERO) for t in trx_stats}
    
    income_planned = ZERO
    income_actual = ZERO
    expense_planned = ZERO
    expense_actual = ZERO
    
    dashboard_groups = []
    
    for group in groups:
        g_planned = ZERO
        g_actual = ZERO
        
        for cat in group.categories:
            planned = budget_map.get(cat.category_id, ZERO)
            raw_actual = actual_map.get(cat.category_id, ZERO)
            
            if cat.type == "income":
                actual = -raw_actual if raw_actual else ZERO
                income_planned += planned
                income_actual += actual
            elif cat.type == "expense":
                actual = raw_actual if raw_actual else ZERO
                expense_planned += planned
                expense_actual += actual
            else: # transfer
                actual = raw_actual if raw_actual else ZERO
                # Transfers excluded from totals
            
            g_planned += planned
            g_actual += actual
            
        dashboard_groups.append(schemas.DashboardGroupStat(
            group_id=group.category_group_id,
            name=group.name,
            planned=g_planned,
            actual=g_actual
        ))
        
    # 4. Accounts Snapshot (Computed Balance from all time)
    account_stats = db.query(
        models.Transaction.account_id,
        func.sum(models.Transaction.amount).label("balance")
    ).group_by(models.Transaction.account_id).all()
    
    balance_map = {a.account_id: -(a.balance or ZERO) for a in account_stats}
    
    accounts = db.query(models.Account).all()
    account_summaries = []
    total_balance = ZERO
    for acc in accounts:
        bal = balance_map.get(acc.id, ZERO)
        total_balance += bal
        account_summaries.append(schemas.DashboardAccountSummary(
            account_id=acc.id,
            name=acc.name,
            type=acc.type,
            subtype=acc.subtype,
            balance=bal
        ))
        
    # 5. Recent Transactions (Filtered to current month)
    recent_txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.date >= start_date, models.Transaction.date < end_date)
        .order_by(models.Transaction.date.desc())
        .limit(10)
        .all()
    )
    
    # Explicitly validate transactions to match TransactionRead schema
    recent_tx_reads = [schemas.TransactionRead.model_validate(tx) for tx in recent_txs]
    
    return schemas.DashboardSummaryResponse(
        month=month,
        income_planned=income_planned,
        income_actual=income_actual,
        expense_planned=expense_planned,
        expense_actual=expense_actual,
        total_balance=total_balance,
        to_be_assigned=income_planned - expense_planned,
        groups=dashboard_groups,
        accounts=account_summaries,
        recent_transactions=recent_tx_reads
    )