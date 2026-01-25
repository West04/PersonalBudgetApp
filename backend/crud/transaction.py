from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session, joinedload
from datetime import date

from ..models import Transaction
from ..schemas import TransactionCreate
from .plaid import get_account_by_plaid_account_id  # <-- Import this helper


def get_transaction(db: Session, transaction_id: UUID) -> Optional[Transaction]:
    """Gets a single transaction by its primary key (UUID)"""
    db_transaction = db.query(Transaction).options(joinedload(Transaction.account)).filter(Transaction.transaction_id == transaction_id).first()
    return db_transaction


def get_transaction_by_plaid_id(db: Session, plaid_transaction_id: str) -> Optional[Transaction]:
    """Gets a single transaction by its Plaid ID"""
    return db.query(Transaction).options(joinedload(Transaction.account)).filter(Transaction.plaid_transaction_id == plaid_transaction_id).first()


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


# --- NEW HELPER FUNCTIONS FOR PLAID SYNC ---

def create_or_update_transaction(db: Session, tx_data: Dict[str, Any]) -> Transaction:
    """
    Creates a new transaction or updates an existing one
    based on Plaid transaction data.
    """

    plaid_tx_id = tx_data['transaction_id']

    # 1. Check if we already have this transaction
    db_transaction = get_transaction_by_plaid_id(db, plaid_tx_id)

    # 2. Get our internal account_id
    db_account = get_account_by_plaid_account_id(db, tx_data['account_id'])
    if not db_account:
        # This should not happen if accounts are synced first,
        # but it's good to be defensive.
        raise Exception(f"Account {tx_data['account_id']} not found in database.")

    # 3. Create or Update
    if db_transaction is None:
        # Create new transaction

        # Plaid amounts are (positive = inflow, negative = outflow)
        # We want (positive = outflow, negative = inflow) for budgeting
        # So we must invert the amount.
        amount_for_budget = -tx_data['amount']

        new_tx_schema = TransactionCreate(
            plaid_transaction_id=tx_data['transaction_id'],
            account_id=db_account.id,
            category_id=None,  # New transactions are uncategorized
            description=tx_data['name'],  # Use Plaid's 'name' as description
            amount=amount_for_budget,
            date=tx_data['date'],
            datetime=tx_data.get('datetime'),  # Use .get() for optional fields
            pending=tx_data['pending']
        )
        db_transaction = Transaction(**new_tx_schema.model_dump())
        db.add(db_transaction)

    else:
        # Update existing transaction
        db_transaction.description = tx_data['name']
        db_transaction.amount = -tx_data['amount']  # Update amount
        db_transaction.date = tx_data['date']
        db_transaction.datetime = tx_data.get('datetime')
        db_transaction.pending = tx_data['pending']
        db.add(db_transaction)

    db.commit()
    db.refresh(db_transaction)
    return db_transaction


def delete_transaction_by_plaid_id(db: Session, plaid_transaction_id: str) -> Optional[Transaction]:
    """
    Deletes a transaction from our database given
    a Plaid transaction ID (from the 'removed' list).
    """
    db_transaction = get_transaction_by_plaid_id(db, plaid_transaction_id)

    if db_transaction:
        db.delete(db_transaction)
        db.commit()
        return db_transaction

    return None
