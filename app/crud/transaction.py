from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from ..models import Transaction
from .. import schemas


def get_transaction(db: Session, transaction_id: UUID) -> Optional[Transaction]:
    db_transaction = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    return db_transaction


def list_transaction(db: Session, category_id: Optional[UUID] = None) -> List[Transaction]:
    q = db.query(Transaction)
    if category_id is not None:
        q = q.filter(Transaction.category_id == category_id)
    return q.all()


def create_transaction(db: Session, new_transaction: schemas.TransactionCreate) -> Transaction:
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


def update_transaction(db: Session, transaction_id: UUID, new_transaction: schemas.TransactionUpdate) -> Optional[Transaction]:
    db_transaction = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if db_transaction is None:
        return None

    if new_transaction.description is not None:
        db_transaction.description = new_transaction.description
    if new_transaction.amount is not None:
        db_transaction.amount = new_transaction.amount
    if new_transaction.category_id is not None:
        db_transaction.category_id = new_transaction.category_id
    if new_transaction.transaction_date is not None:
        db_transaction.transaction_date = new_transaction.transaction_date

    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction