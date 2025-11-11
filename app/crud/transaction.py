from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from datetime import date

from ..models import Transaction
from ..schemas import TransactionCreate, TransactionUpdate


def get_transaction(db: Session, transaction_id: UUID) -> Optional[Transaction]:
    """Gets a single transaction by its primary key (UUID)"""
    db_transaction = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    return db_transaction


def get_transaction_by_plaid_id(db: Session, plaid_transaction_id: str) -> Optional[Transaction]:
    """Gets a single transaction by its Plaid ID"""
    return db.query(Transaction).filter(Transaction.plaid_transaction_id == plaid_transaction_id).first()


def list_transaction(
        db: Session,
        account_id: Optional[UUID] = None,
        category_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
) -> List[Transaction]:
    """
    Lists transactions with optional filters for account, category,
    and a date range.
    """
    q = db.query(Transaction)

    if account_id is not None:
        q = q.filter(Transaction.account_id == account_id)

    if category_id is not None:
        q = q.filter(Transaction.category_id == category_id)

    if start_date is not None:
        # Filter on the 'date' column, not the old 'transaction_date'
        q = q.filter(Transaction.date >= start_date)

    if end_date is not None:
        q = q.filter(Transaction.date <= end_date)

    # By default, let's order by the posting date, most recent first
    q = q.order_by(Transaction.date.desc())

    return q.all()


def create_transaction(db: Session, new_transaction: TransactionCreate) -> Transaction:
    """
    Creates a new transaction.
    This is intended to be used by the Plaid sync process.
    """
    db_transaction = Transaction(
        **new_transaction.model_dump()
    )
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction


def delete_transaction(db: Session, transaction_id: UUID) -> Optional[Transaction]:
    """Deletes a transaction by its primary key (UUID)"""
    deleted = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()

    if deleted is None:
        return None
    db.delete(deleted)
    db.commit()
    return deleted


def update_transaction(
        db: Session,
        transaction_id: UUID,
        payload: TransactionUpdate
) -> Optional[Transaction]:
    """
    Updates a transaction. Because the TransactionUpdate schema
    only includes 'description' and 'category_id', this function
    will only update those fields. This is perfect for categorizing.
    """
    db_transaction = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if db_transaction is None:
        return None

    # This generic logic still works perfectly.
    # It will only see `description` or `category_id` in the payload.
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_transaction, key, value)

    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction