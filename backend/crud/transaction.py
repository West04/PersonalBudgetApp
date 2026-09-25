from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session, joinedload
from datetime import date

from ..models import Transaction


def get_transaction(db: Session, transaction_id: UUID) -> Optional[Transaction]:
    """Gets a single transaction by its primary key (UUID)"""
    db_transaction = db.query(Transaction).options(joinedload(Transaction.account)).filter(Transaction.transaction_id == transaction_id).first()
    return db_transaction


def list_transaction(
        db: Session,
        account_id: Optional[UUID] = None,
        category_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        uncategorized: Optional[bool] = None,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
) -> Dict[str, Any]:
    """
    Lists transactions with optional filters for account, category,
    search text, and a date range. Supports pagination.
    """
    query = db.query(Transaction).options(joinedload(Transaction.account))

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    if category_id is not None:
        query = query.filter(Transaction.category_id == category_id)
    if start_date is not None:
        query = query.filter(Transaction.date >= start_date)
    if end_date is not None:
        query = query.filter(Transaction.date <= end_date)
    
    # New filters
    if uncategorized is True:
        query = query.filter(Transaction.category_id == None)
    if q:
        # Case-insensitive search on description
        query = query.filter(Transaction.description.ilike(f"%{q}%"))

    # Get total count before pagination
    total = query.count()

    # Sorting: Date DESC, then Transaction ID DESC (stable sort)
    query = query.order_by(Transaction.date.desc(), Transaction.transaction_id.desc())

    # Pagination
    query = query.offset(offset).limit(limit)

    items = query.all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


def update_transaction(db: Session, transaction_id: UUID, payload) -> Optional[Transaction]:
    """
    Updates a transaction's category or description.
    """
    db_transaction = get_transaction(db, transaction_id)
    if not db_transaction:
        return None
    
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_transaction, key, value)

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
