from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..managers import budget_summary_manager, dashboard_summary_manager

router = APIRouter(
    prefix="/summary",
    tags=["Summary"],
)


@router.get("/budget", response_model=schemas.BudgetSummaryResponse)
def get_budget_summary(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    try:
        budget_month = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    budget_result = budget_summary_manager.get_budget_summary(db, budget_month)

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
    try:
        budget_month = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    result = dashboard_summary_manager.get_dashboard_summary(db, budget_month)

    dashboard_groups = [
        schemas.DashboardGroupStat(
            group_id=g.group_id,
            name=g.name,
            planned=g.total_planned,
            actual=g.total_actual,
        )
        for g in result.budget_summary.groups
    ]

    account_summaries = [
        schemas.DashboardAccountSummary(
            account_id=acc.account_id,
            name=acc.name,
            type=acc.type,
            subtype=acc.subtype,
            current_balance=acc.current_balance,
            available_balance=acc.available_balance,
            currency=acc.currency,
            balance_last_updated=acc.balance_last_updated,
            is_active=acc.is_active,
        )
        for acc in result.accounts
    ]

    recent_tx_reads = [
        schemas.TransactionDetailRead(
            transaction_id=tx.transaction_id,
            account_id=tx.account_id,
            category_id=tx.category_id,
            description=tx.description,
            amount=tx.amount,
            date=tx.date,
            datetime=tx.datetime,
            pending=tx.pending,
            is_transfer=tx.is_transfer,
            account=schemas.AccountRead(
                id=tx.account.id,
                name=tx.account.name,
                type=tx.account.type,
                subtype=tx.account.subtype,
                current_balance=tx.account.current_balance,
                available_balance=tx.account.available_balance,
                starting_balance=tx.account.starting_balance,
                currency=tx.account.currency,
                balance_last_updated=tx.account.balance_last_updated,
                is_active=tx.account.is_active,
                plaid_account_id=tx.account.plaid_account_id,
                item_id=tx.account.item_id,
            ) if tx.account else None,
        )
        for tx in result.recent_transactions
    ]

    return schemas.DashboardSummaryResponse(
        month=month,
        income_planned=result.budget_summary.total_income_planned,
        income_actual=result.budget_summary.total_income_actual,
        expense_planned=result.budget_summary.total_expense_planned,
        expense_actual=result.budget_summary.total_expense_actual,
        total_balance=result.total_balance,
        to_be_assigned=result.budget_summary.to_be_assigned,
        groups=dashboard_groups,
        accounts=account_summaries,
        recent_transactions=recent_tx_reads,
    )