"""
Manager for the Dashboard Summary workflow.

Coordinates:
1. Determination of the budget period [start_date, end_date) using shared domain dates helper.
2. Invocation of the existing Budget Summary workflow (BudgetSummaryManager).
3. Retrieval of active accounts via Account ResourceAccess.
4. Retrieval of recent transactions via Transaction ResourceAccess.
5. Computation of total balance across active accounts.
6. Mapping persistence records to immutable application result values.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from ..access.account_access import get_active_accounts
from ..access.transaction_access import get_recent_transactions_for_month
from ..domain.budgeting import BudgetSummaryResult
from ..domain.dates import determine_month_range
from . import budget_summary_manager

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class DashboardAccountItem:
    account_id: UUID
    name: str
    type: str
    subtype: Optional[str]
    current_balance: Decimal
    available_balance: Optional[Decimal]
    currency: str
    balance_last_updated: Optional[datetime]
    is_active: bool


@dataclass(frozen=True)
class DashboardTransactionAccountItem:
    id: UUID
    name: str
    type: str
    subtype: Optional[str]
    current_balance: Optional[Decimal]
    available_balance: Optional[Decimal]
    starting_balance: Decimal
    currency: str
    balance_last_updated: Optional[datetime]
    is_active: bool
    plaid_account_id: Optional[str]
    item_id: Optional[UUID]


@dataclass(frozen=True)
class DashboardRecentTransactionItem:
    transaction_id: UUID
    account_id: UUID
    category_id: Optional[UUID]
    description: str
    amount: Decimal
    date: date
    datetime: Optional[datetime]
    pending: bool
    is_transfer: bool
    account: Optional[DashboardTransactionAccountItem] = None


@dataclass(frozen=True)
class DashboardSummaryResult:
    budget_summary: BudgetSummaryResult
    accounts: Sequence[DashboardAccountItem]
    total_balance: Decimal
    recent_transactions: Sequence[DashboardRecentTransactionItem]


def get_dashboard_summary(
    db: Session,
    budget_month: date,
) -> DashboardSummaryResult:
    """
    Coordinates the dashboard summary workflow:
    1. Determines period dates using shared determine_month_range.
    2. Reuses existing BudgetSummaryManager workflow.
    3. Retrieves active accounts via Account ResourceAccess.
    4. Retrieves recent transactions via Transaction ResourceAccess.
    5. Computes total balance across active accounts.
    6. Maps persistence records to immutable application result values.
    7. Returns composite DashboardSummaryResult.
    """
    start_date, end_date = determine_month_range(budget_month)

    # 1. Reuse existing budget summary workflow
    budget_summary = budget_summary_manager.get_budget_summary(db, budget_month)

    # 2. Retrieve persistence records from Accessors
    raw_accounts = get_active_accounts(db)
    raw_transactions = get_recent_transactions_for_month(db, start_date, end_date)

    # 3. Compute total balance & map accounts to application value objects
    accounts: list[DashboardAccountItem] = []
    total_balance = ZERO

    for acc in raw_accounts:
        current = acc.current_balance or ZERO
        total_balance += current
        accounts.append(
            DashboardAccountItem(
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

    # 4. Map recent transactions to application value objects
    recent_transactions: list[DashboardRecentTransactionItem] = []
    for tx in raw_transactions:
        acc_item = None
        if tx.account:
            acc_item = DashboardTransactionAccountItem(
                id=tx.account.id,
                name=tx.account.name,
                type=tx.account.type,
                subtype=tx.account.subtype,
                current_balance=tx.account.current_balance,
                available_balance=tx.account.available_balance,
                starting_balance=getattr(tx.account, "starting_balance", ZERO) or ZERO,
                currency=getattr(tx.account, "currency", "USD") or "USD",
                balance_last_updated=getattr(tx.account, "balance_last_updated", None),
                is_active=tx.account.is_active,
                plaid_account_id=getattr(tx.account, "plaid_account_id", None),
                item_id=getattr(tx.account, "item_id", None),
            )

        recent_transactions.append(
            DashboardRecentTransactionItem(
                transaction_id=tx.transaction_id,
                account_id=tx.account_id,
                category_id=tx.category_id,
                description=tx.description,
                amount=tx.amount,
                date=tx.date,
                datetime=tx.datetime,
                pending=tx.pending,
                is_transfer=tx.is_transfer,
                account=acc_item,
            )
        )

    return DashboardSummaryResult(
        budget_summary=budget_summary,
        accounts=accounts,
        total_balance=total_balance,
        recent_transactions=recent_transactions,
    )
