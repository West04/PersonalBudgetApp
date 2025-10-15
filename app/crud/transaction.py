from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from datetime import date

from ..models import Transaction
from ..schemas import TransactionCreate, TransactionUpdate


def get_transaction(db: Session, transaction_id: UUID) -> Optional[Transaction]:
    db_transaction = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    return db_transaction


def list_transaction(db: Session, category_id: Optional[UUID] = None, transaction_date: Optional[date] = None) -> List[Transaction]:
    q = db.query(Transaction)

    if category_id is not None:
        q = q.filter(Transaction.category_id == category_id)

    if transaction_date is not None:
        q = q.filter(Transaction.transaction_date == transaction_date)
    return q.all()


def create_transaction(db: Session, new_transaction: TransactionCreate) -> Transaction:
    db_transaction = Transaction(
        description=new_transaction.description,
        amount=new_transaction.amount,
        category_id=new_transaction.category_id,
        transaction_date=new_transaction.transaction_date
    )
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction


def delete_transaction(db: Session, transaction_id: UUID) -> Optional[Transaction]:
    deleted = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()

    if deleted is None:
        return None
    db.delete(deleted)
    db.commit()
    return deleted


def update_transaction(
        db: Session,
        update_transaction: TransactionUpdate,
        transaction_id: Optional[UUID] = None
) -> Optional[Transaction]:
    db_transaction = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if db_transaction is None:
        return None

    if update_transaction.description is not None:
        db_transaction.description = update_transaction.description
    if update_transaction.amount is not None:
        db_transaction.amount = update_transaction.amount
    if db_transaction.category_id is not None:
        db_transaction.category_id = db_transaction.category_id
    if db_transaction.transaction_date is not None:
        db_transaction.transaction_date = db_transaction.transaction_date

    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction