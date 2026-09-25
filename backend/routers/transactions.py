from uuid import UUID
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..access import transaction_access
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

    return transaction_access.list_transactions(
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
    db_transaction = transaction_access.get_transaction_by_id(db=db, transaction_id=transaction_id)

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
    return transaction_access.create_manual_transaction(
        db=db,
        account_id=payload.account_id,
        category_id=payload.category_id,
        description=payload.description,
        amount=payload.amount,
        transaction_date=payload.date,
        transaction_datetime=payload.datetime,
        pending=payload.pending,
        plaid_transaction_id=payload.plaid_transaction_id,
    )


@router.put("/{transaction_id}", response_model=schemas.TransactionRead, status_code=status.HTTP_200_OK)
def update_transaction(
        transaction_id: UUID,
        payload: schemas.TransactionUpdate,
        db: Session = Depends(get_db)
):
    """
    Updates a specific transaction by its ID.
    """
    update_data = payload.model_dump(exclude_unset=True)
    updated = transaction_access.update_manual_transaction(
        db=db,
        transaction_id=transaction_id,
        update_data=update_data,
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
    deleted = transaction_access.delete_manual_transaction(
        db=db,
        transaction_id=transaction_id
    )

    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Transaction not found'
        )
    return None