"""
Resource access functions for Transaction PostgreSQL resources.
"""

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .. import models

ZERO = Decimal("0.00")
DASHBOARD_RECENT_TRANSACTIONS_LIMIT = 10


def get_actuals_by_category(
    db: Session,
    start_date: date,
    end_date: date,
) -> dict[UUID, Decimal]:
    """
    Aggregates transaction amount sums grouped by category_id for transactions
    within [start_date, end_date), ignoring uncategorized transactions.
    """
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
    return {t.category_id: (t.total or ZERO) for t in trx_stats}


def get_recent_transactions_for_month(
    db: Session,
    start_date: date,
    end_date: date,
) -> Sequence[models.Transaction]:
    """
    Retrieves the 10 most recent transactions within [start_date, end_date),
    ordered by date descending, with associated account eagerly loaded.
    """
    return (
        db.query(models.Transaction)
        .options(joinedload(models.Transaction.account))
        .filter(
            models.Transaction.date >= start_date,
            models.Transaction.date < end_date,
        )
        .order_by(models.Transaction.date.desc())
        .limit(DASHBOARD_RECENT_TRANSACTIONS_LIMIT)
        .all()
    )


def get_transactions_for_account(
    db: Session,
    account_id: UUID,
) -> Sequence[models.Transaction]:
    """
    Retrieves all historical transactions for a specific account ordered by date descending.
    """
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.account_id == account_id)
        .order_by(models.Transaction.date.desc())
        .all()
    )


def get_unmatched_inflow_transactions(
    db: Session,
) -> Sequence[models.Transaction]:
    """
    Retrieves all unmatched negative transactions (amount < 0, is_transfer == False)
    across all accounts, preserving current query shape and introducing no explicit ordering.
    """
    return (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Transaction.amount < 0,
            models.Transaction.is_transfer == False,
        )
        .all()
    )


def get_unmatched_outflow_transactions(
    db: Session,
) -> Sequence[models.Transaction]:
    """
    Retrieves all unmatched positive transactions (amount > 0, is_transfer == False)
    across all accounts, preserving current query shape and introducing no explicit ordering.
    """
    return (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Transaction.amount > 0,
            models.Transaction.is_transfer == False,
        )
        .all()
    )


def get_account_for_transaction(
    transaction: models.Transaction,
) -> Optional[models.Account]:
    """
    Resolves the Account relationship associated with a Transaction.

    Accessing transaction.account may trigger SQLAlchemy lazy loading.
    Relationship loading remains a concrete persistence concern owned by
    Transaction ResourceAccess.
    """
    return transaction.account


def csv_import_transaction_exists(
    db: Session,
    account_id: UUID,
    transaction_date: date,
    amount: Decimal,
    description: str,
) -> bool:
    """
    Checks if an identical transaction exists for the given account.
    Matches exact account_id, date, amount, and description (case-sensitive).
    """
    return (
        db.query(models.Transaction)
        .filter(
            models.Transaction.account_id == account_id,
            models.Transaction.date == transaction_date,
            models.Transaction.amount == amount,
            models.Transaction.description == description,
        )
        .first()
    ) is not None


def stage_csv_import_transaction(
    db: Session,
    account_id: UUID,
    transaction_date: date,
    amount: Decimal,
    description: str,
    pending: bool = False,
    category_id: Optional[UUID] = None,
    transaction_datetime: Optional[datetime] = None,
) -> models.Transaction:
    """
    Instantiates and stages a new manual CSV import Transaction in the session.
    Explicitly sets plaid_transaction_id = None.
    Does not flush or commit.
    """
    txn = models.Transaction(
        account_id=account_id,
        category_id=category_id,
        description=description,
        amount=amount,
        date=transaction_date,
        datetime=transaction_datetime,
        pending=pending,
        plaid_transaction_id=None,
    )
    db.add(txn)
    return txn


