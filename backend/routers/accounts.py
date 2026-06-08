from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/types", response_model=dict)
def get_account_types():
    """Return canonical account types and their valid subtypes."""
    return schemas.ACCOUNT_SUBTYPES


@router.get("/", response_model=List[schemas.AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    return (
        db.query(models.Account)
        .order_by(models.Account.type, models.Account.name.asc())
        .all()
    )


@router.post("/", response_model=schemas.AccountRead, status_code=201)
def create_account(payload: schemas.AccountCreate, db: Session = Depends(get_db)):
    new_account = models.Account(
        name=payload.name,
        type=payload.type,
        subtype=payload.subtype,
        current_balance=payload.current_balance,
        starting_balance=payload.starting_balance,
        currency=payload.currency,
        is_active=payload.is_active,
        plaid_account_id=None,
        item_id=None,
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    return new_account


@router.put("/{account_id}", response_model=schemas.AccountRead)
def update_account(account_id: UUID, payload: schemas.AccountUpdate, db: Session = Depends(get_db)):
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    for field in ("name", "type", "subtype", "is_active", "starting_balance", "current_balance"):
        val = getattr(payload, field)
        if val is not None:
            setattr(account, field, val)

    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: UUID, db: Session = Depends(get_db)):
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    db.delete(account)
    db.commit()
