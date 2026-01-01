from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/", response_model=List[schemas.AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    """
    List all connected accounts.
    """
    return (
        db.query(models.Account)
        .order_by(models.Account.name.asc())
        .all()
    )


@router.post("/", response_model=schemas.AccountRead, status_code=201)
def create_account(payload: schemas.AccountCreate, db: Session = Depends(get_db)):
    """
    Manually create an account (e.g. for cash or unlinked accounts).
    """
    new_account = models.Account(
        name=payload.name,
        type=payload.type,
        subtype=payload.subtype,
        current_balance=payload.current_balance,
        currency=payload.currency,
        is_active=payload.is_active,
        # Plaid fields can be None now
        plaid_account_id=None,
        item_id=None
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    return new_account


@router.put("/{account_id}", response_model=schemas.AccountRead)
def update_account(account_id: UUID, payload: schemas.AccountUpdate, db: Session = Depends(get_db)):
    """
    Update account name or active status.
    """
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if payload.name is not None:
        account.name = payload.name
    if payload.is_active is not None:
        account.is_active = payload.is_active

    db.commit()
    db.refresh(account)
    return account