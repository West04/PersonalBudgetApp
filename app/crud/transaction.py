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
        q = q.filter(Transaction.transaction_date >= transaction_date)
    return q.all()


def create_transaction(db: Session, new_transaction: TransactionCreate) -> Transaction:
    db_transaction = Transaction(
        **new_transaction.model_dump()
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
        transaction_id: UUID,
        payload: TransactionUpdate
) -> Optional[Transaction]:
    db_transaction = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if db_transaction is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_transaction, key, value)

    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction
