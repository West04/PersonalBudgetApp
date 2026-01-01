from uuid import UUID
from typing import Optional, List
from datetime import date

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..crud import transaction as crud_transaction
from ..database import get_db

router = APIRouter(
    prefix="/transactions",
    tags=["Transactions"],
)


@router.get("/", response_model=schemas.TransactionListResponse)
def list_transactions(
        account_id: Optional[UUID] = None,
        category_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        uncategorized: Optional[bool] = None,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        db: Session = Depends(get_db)
):
    """
    List transactions with pagination and filters.

    Can be filtered by:
    - `account_id`: To get transactions for a specific bank account.
    - `category_id`: To get transactions for a specific budget category.
    - `start_date`: The start of a date range (e.g., 2023-01-01)
    - `end_date`: The end of a date range (e.g., 2023-01-31)
    - `uncategorized`: If true, return only transactions with no category.
    - `q`: Search text for transaction description.
    """
    if limit > 200:
        limit = 200

    return crud_transaction.list_transaction(
        db=db,
        account_id=account_id,
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        uncategorized=uncategorized,
        q=q,
        limit=limit,
        offset=offset
    )


@router.get("/{transaction_id}", response_model=schemas.TransactionRead)
def read_transaction(
        transaction_id: UUID,
        db: Session = Depends(get_db)
):
    """
    Get a specific transaction by its ID.
    """
    db_transaction = crud_transaction.get_transaction(db=db, transaction_id=transaction_id)

    if db_transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Transaction not found'
        )
    return db_transaction


@router.post("/", response_model=schemas.TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: schemas.TransactionCreate,
    db: Session = Depends(get_db)
):
    """
    Manually create a transaction.
    """
    # Create the transaction model
    # Note: we must assign a plaid_transaction_id if it's unique/indexed, 
    # but we made it nullable. However, if we want to ensure uniqueness among 
    # manual transactions if we ever populated it, we could leave it None.
    # The DB model change made it nullable.
    
    new_txn = models.Transaction(
        account_id=payload.account_id,
        category_id=payload.category_id,
        description=payload.description,
        amount=payload.amount,
        date=payload.date,
        datetime=payload.datetime,
        pending=payload.pending,
        plaid_transaction_id=payload.plaid_transaction_id # might be None
    )
    
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)
    return new_txn


@router.put("/{transaction_id}", response_model=schemas.TransactionRead, status_code=status.HTTP_200_OK)
def update_transaction(
        transaction_id: UUID,
        payload: schemas.TransactionUpdate,
        db: Session = Depends(get_db)
):
    """
    Updates a specific transaction by its ID.
    """
    # This endpoint is now used for *categorizing* a transaction
    # or updating its description.
    # The 'payload' will only accept 'category_id' and 'description'
    # thanks to our updated TransactionUpdate schema.
    updated = crud_transaction.update_transaction(
        db=db,
        transaction_id=transaction_id,
        payload=payload
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Transaction not found or invalid update'
        )
    return updated


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
        transaction_id: UUID,
        db: Session = Depends(get_db)
):
    """
    Delete a specific transaction by its ID.
    """
    deleted = crud_transaction.delete_transaction(
        db=db,
        transaction_id=transaction_id
    )

    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Transaction not found'
        )
    return None