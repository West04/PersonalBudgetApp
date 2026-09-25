"""
Resource access functions for Account PostgreSQL resources.
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from .. import models


def get_account_by_id(
    db: Session,
    account_id: UUID,
) -> Optional[models.Account]:
    """
    Retrieves an Account by primary key without active-status or type filtering.
    """
    return (
        db.query(models.Account)
        .filter(models.Account.id == account_id)
        .first()
    )


def get_active_accounts(db: Session) -> Sequence[models.Account]:
    """
    Retrieves all active accounts ordered by name ascending.
    """
    return (
        db.query(models.Account)
        .filter(models.Account.is_active == True)
        .order_by(models.Account.name.asc())
        .all()
    )


def get_active_credit_accounts(db: Session) -> Sequence[models.Account]:
    """
    Retrieves all active credit accounts ordered by name ascending.
    """
    return (
        db.query(models.Account)
        .filter(models.Account.type == "credit", models.Account.is_active == True)
        .order_by(models.Account.name.asc())
        .all()
    )


def get_account_by_plaid_account_id(
    db: Session,
    plaid_account_id: str,
) -> Optional[models.Account]:
    """
    Retrieves an Account by exact plaid_account_id.
    """
    return (
        db.query(models.Account)
        .filter(models.Account.plaid_account_id == plaid_account_id)
        .first()
    )


def stage_or_update_plaid_account(
    db: Session,
    item_id: UUID,
    plaid_account_id: str,
    name: Optional[str],
    mask: Optional[str],
    account_type: Optional[str],
    subtype: Optional[str],
    current_balance: Decimal,
    available_balance: Optional[Decimal],
    currency: str,
    balance_last_updated: datetime,
) -> models.Account:
    """
    Locates an account by exact plaid_account_id:
    - If absent: stages a new models.Account record with is_active=True and ORM default starting_balance=0.00.
    - If present: updates mutable fields while preserving starting_balance, is_active, and item_id.
    Does not flush or commit.
    """
    account = (
        db.query(models.Account)
        .filter(models.Account.plaid_account_id == plaid_account_id)
        .first()
    )

    if account is None:
        account = models.Account(
            item_id=item_id,
            plaid_account_id=plaid_account_id,
            name=name or "Account",
            mask=mask,
            type=account_type or "unknown",
            subtype=subtype,
            is_active=True,
            current_balance=current_balance,
            available_balance=available_balance,
            currency=currency,
            balance_last_updated=balance_last_updated,
        )
        db.add(account)
        return account

    account.name = name or account.name
    account.mask = mask
    account.type = account_type or account.type
    account.subtype = subtype
    account.current_balance = current_balance
    account.available_balance = available_balance
    account.currency = currency
    account.balance_last_updated = balance_last_updated

    db.add(account)
    return account

