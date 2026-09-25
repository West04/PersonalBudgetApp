from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..access import account_access
from ..database import get_db
from .. import schemas

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/types", response_model=dict)
def get_account_types():
    """Return canonical account types and their valid subtypes."""
    return schemas.ACCOUNT_SUBTYPES


@router.get("/", response_model=List[schemas.AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    return account_access.get_all_accounts_ordered(db)


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

