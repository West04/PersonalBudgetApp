from uuid import UUID
from typing import Optional, List
from datetime import date

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..access import transaction_access
from ..database import get_db
from ..managers import transfer_reconciliation_manager

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
        is_reviewed: Optional[bool] = None,
        reviewed: Optional[bool] = None,
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
    - `is_reviewed`: If true, return only reviewed; if false, return only unreviewed.
    - `reviewed`: Alias for is_reviewed.
    - `q`: Search text for transaction description.
    """
    if limit > 200:
        limit = 200

    effective_is_reviewed = is_reviewed if is_reviewed is not None else reviewed

    return transaction_access.list_transactions(
        db=db,
        account_id=account_id,
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        uncategorized=uncategorized,
        is_reviewed=effective_is_reviewed,
        q=q,
        limit=limit,
        offset=offset
    )


@router.get("/transfer-candidates", response_model=List[schemas.TransferCandidate])
def get_transfer_candidates(
    db: Session = Depends(get_db),
):
    """
    Finds likely transfer pairs across any account types: a negative transaction
    (inflow) on one account matched to a same-amount positive transaction (outflow)
    on a different account within 2 days, where neither is already marked as a transfer.

    Covers: credit card payments, checking→savings moves, and any other inter-account transfer.
    """
    candidates = transfer_reconciliation_manager.get_transfer_candidates(db)

    return [
        schemas.TransferCandidate(
            inflow_side=schemas.CreditCardTransactionRead(
                transaction_id=c.inflow_side.transaction_id,
                description=c.inflow_side.description,
                amount=c.inflow_side.amount,
                date=c.inflow_side.date,
                is_transfer=c.inflow_side.is_transfer,
                category_id=c.inflow_side.category_id,
            ),
            inflow_account_name=c.inflow_account_name,
            outflow_side=schemas.TransactionRead(
                transaction_id=c.outflow_side.transaction_id,
                plaid_transaction_id=c.outflow_side.plaid_transaction_id,
                account_id=c.outflow_side.account_id,
                category_id=c.outflow_side.category_id,
                description=c.outflow_side.description,
                amount=c.outflow_side.amount,
                date=c.outflow_side.date,
                datetime=c.outflow_side.datetime,
                pending=c.outflow_side.pending,
                is_transfer=c.outflow_side.is_transfer,
                is_reviewed=c.outflow_side.is_transfer,  # fallback if needed, but schema handles defaults
                account=schemas.AccountRead(
                    id=c.outflow_side.account.id,
                    plaid_account_id=c.outflow_side.account.plaid_account_id,
                    item_id=c.outflow_side.account.item_id,
                    name=c.outflow_side.account.name,
                    mask=c.outflow_side.account.mask,
                    type=c.outflow_side.account.type,
                    subtype=c.outflow_side.account.subtype,
                    current_balance=c.outflow_side.account.current_balance,
                    available_balance=c.outflow_side.account.available_balance,
                    starting_balance=c.outflow_side.account.starting_balance,
                    currency=c.outflow_side.account.currency,
                    balance_last_updated=c.outflow_side.account.balance_last_updated,
                    is_active=c.outflow_side.account.is_active,
                ) if c.outflow_side.account else None,
            ),
            outflow_account_name=c.outflow_account_name,
        )
        for c in candidates
    ]


@router.post("/mark-transfers", status_code=204)
def mark_transfers(
    payload: schemas.MarkTransfersRequest,
    db: Session = Depends(get_db),
):
    """
    Marks a list of transactions as transfers (is_transfer = True).
    """
    transaction_access.mark_transactions_as_transfers(db, payload.transaction_ids)


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
        is_reviewed=payload.is_reviewed,
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
    Rejects modification of financial fields (amount, date, account_id) if reconciled.
    """
    update_data = payload.model_dump(exclude_unset=True)
    try:
        updated = transaction_access.update_manual_transaction(
            db=db,
            transaction_id=transaction_id,
            update_data=update_data,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Transaction not found or invalid update'
        )
    return updated


@router.patch("/{transaction_id}/cleared", response_model=schemas.TransactionRead)
def set_transaction_cleared_status(
    transaction_id: UUID,
    payload: schemas.TransactionClearedUpdate,
    db: Session = Depends(get_db),
):
    """
    Updates the is_cleared status of a transaction.
    Rejects modification if the transaction is already reconciled.
    """
    try:
        updated = transaction_access.set_transaction_cleared(
            db=db,
            transaction_id=transaction_id,
            is_cleared=payload.is_cleared,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    return updated


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
        transaction_id: UUID,
        db: Session = Depends(get_db)
):
    """
    Delete a specific transaction by its ID.
    Blocks deletion if the transaction is reconciled.
    """
    try:
        deleted = transaction_access.delete_manual_transaction(
            db=db,
            transaction_id=transaction_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Transaction not found'
        )
    return None