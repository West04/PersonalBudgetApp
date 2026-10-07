from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..access import account_access
from ..database import get_db
from ..managers import account_summary_manager, account_reconciliation_manager

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/types", response_model=dict)
def get_account_types():
    """Return canonical account types and their valid subtypes."""
    return schemas.ACCOUNT_SUBTYPES


@router.get("/", response_model=List[schemas.AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    return account_summary_manager.get_accounts_summary(db)



@router.post("/", response_model=schemas.AccountRead, status_code=201)
def create_account(payload: schemas.AccountCreate, db: Session = Depends(get_db)):
    return account_access.create_manual_account(
        db=db,
        name=payload.name,
        account_type=payload.type,
        subtype=payload.subtype,
        current_balance=payload.current_balance,
        starting_balance=payload.starting_balance,
        currency=payload.currency,
        is_active=payload.is_active,
    )


@router.put("/{account_id}", response_model=schemas.AccountRead)
def update_account(account_id: UUID, payload: schemas.AccountUpdate, db: Session = Depends(get_db)):
    account = account_access.update_manual_account(
        db=db,
        account_id=account_id,
        update_data=payload.model_dump(),
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: UUID, db: Session = Depends(get_db)):
    success = account_access.delete_account(db, account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")


@router.get("/{account_id}/reconciliation", response_model=schemas.AccountReconciliationSummary)
def get_account_reconciliation(
    account_id: UUID,
    ending_date: Optional[date] = None,
    ending_balance: Optional[Decimal] = None,
    db: Session = Depends(get_db),
):
    """
    Returns the reconciliation workspace summary for a depository account,
    evaluating eligible unreconciled transactions through ending_date against ending_balance.
    """
    target_date = ending_date or date.today()
    target_balance = ending_balance if ending_balance is not None else Decimal("0.00")
    try:
        return account_reconciliation_manager.get_reconciliation_summary(
            db=db,
            account_id=account_id,
            statement_ending_date=target_date,
            statement_ending_balance=target_balance,
        )
    except account_reconciliation_manager.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except account_reconciliation_manager.UnsupportedAccountTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{account_id}/reconciliation/complete", response_model=schemas.AccountReconciliationSummary)
def complete_account_reconciliation(
    account_id: UUID,
    payload: schemas.CompleteReconciliationRequest,
    db: Session = Depends(get_db),
):
    """
    Finalizes reconciliation for an account when difference is zero.
    Marks participating cleared transactions as reconciled, and updates account reconciliation metadata.
    """
    try:
        return account_reconciliation_manager.complete_reconciliation(
            db=db,
            account_id=account_id,
            statement_ending_date=payload.statement_ending_date,
            statement_ending_balance=payload.statement_ending_balance,
        )
    except account_reconciliation_manager.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except account_reconciliation_manager.UnsupportedAccountTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except account_reconciliation_manager.UnbalancedReconciliationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

