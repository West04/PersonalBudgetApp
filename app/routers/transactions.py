from uuid import UUID
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..crud import transaction as crud_transaction
from ..database import get_db

router = APIRouter(
    prefix="/transactions",
    tags=["Transactions"],
)


@router.post("/", response_model=schemas.TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    transaction: schemas.TransactionCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new transaction.
    """
    return crud_transaction.create_transaction(db=db, new_transaction=transaction)


@router.get("/", response_model=list[schemas.TransactionRead])
def list_transactions(category_id: Optional[UUID] = None, transaction_data: Optional[date] = None, db: Session = Depends(get_db)):
    """
    List categories. Optionally filter by category_id and transaction_date.
    """
    return crud_transaction.list_transaction(db=db, category_id=category_id, transaction_date=transaction_data)


@router.get("/{transaction_id}", response_model=schemas.TransactionRead)
def read_transaction(
    transaction_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get a specific category by its ID.
    """
    db_transaction = crud_transaction.get_transaction(db=db, transaction_id=transaction_id)

    if db_transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Transaction not found'
        )

    return db_transaction


@router.put("/{transaction_id}", response_model=schemas.TransactionRead, status_code=status.HTTP_202_ACCEPTED)
def update_transaction(
        transaction_id: UUID,
        payload: schemas.TransactionUpdate,
        db: Session = Depends(get_db)
):
    """
    Update a specific transaction by its ID.
    """

    updated = crud_transaction.update_transaction(
        db=db,
        transaction_id=transaction_id,
        update_transaction=payload
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found or invalid update'
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
            detail='Category not found'
        )
    return None