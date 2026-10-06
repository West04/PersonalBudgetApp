"""
FastAPI router for Recurring Transactions.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..managers import recurring_transaction_manager

router = APIRouter(
    prefix="/recurring",
    tags=["Recurring Transactions"],
)


@router.get("/", response_model=List[schemas.RecurringItemRead])
def list_recurring_items(
    account_id: Optional[UUID] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Lists recurring transaction patterns.
    If no patterns have been detected yet, runs an initial detection pass.
    Can be filtered by account_id and status (detected, confirmed, dismissed).
    """
    return recurring_transaction_manager.list_recurring_items(
        db=db,
        account_id=account_id,
        status=status,
    )


@router.post("/detect", response_model=List[schemas.RecurringItemRead])
def detect_recurring_items(
    account_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """
    Scans historical posted transactions and detects genuine recurring series.
    Syncs newly detected patterns into persistence without overwriting
    existing user confirmations or dismissals.
    """
    return recurring_transaction_manager.detect_and_sync_recurring_items(
        db=db,
        account_id=account_id,
    )


@router.get("/{item_id}", response_model=schemas.RecurringItemDetailRead)
def get_recurring_item_detail(
    item_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Returns full details of a specific recurring pattern, including
    its member transaction history.
    """
    detail = recurring_transaction_manager.get_recurring_item_detail(
        db=db,
        item_id=item_id,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recurring item not found",
        )
    return detail


@router.post("/{item_id}/confirm", response_model=schemas.RecurringItemRead)
def confirm_recurring_item(
    item_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Confirms a detected recurring item as an authoritative repeating pattern.
    """
    confirmed = recurring_transaction_manager.confirm_recurring_item(
        db=db,
        item_id=item_id,
    )
    if confirmed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recurring item not found",
        )
    return confirmed


@router.post("/{item_id}/dismiss", response_model=schemas.RecurringItemRead)
def dismiss_recurring_item(
    item_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Dismisses a detected recurring item from active consideration.
    """
    dismissed = recurring_transaction_manager.dismiss_recurring_item(
        db=db,
        item_id=item_id,
    )
    if dismissed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recurring item not found",
        )
    return dismissed
