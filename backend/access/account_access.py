"""
Resource access functions for Account PostgreSQL resources.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
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


def get_all_accounts_ordered(
    db: Session,
) -> Sequence[models.Account]:
    """
    Retrieves all accounts (active and inactive, manual and Plaid-linked)
    ordered by type ascending, then name ascending.
    """
    return (
        db.query(models.Account)
        .order_by(
            models.Account.type,
            models.Account.name.asc(),
        )
        .all()
    )


def create_manual_account(
    db: Session,
    name: str,
    account_type: str,
    subtype: Optional[str] = None,
    current_balance: Decimal = Decimal("0.00"),
    starting_balance: Decimal = Decimal("0.00"),
    currency: str = "USD",
    is_active: bool = True,
) -> models.Account:
    """
    Creates and persists a new manual account with plaid_account_id=None and item_id=None.
    Owns commit and refresh for standalone CRUD persistence.
    """
    account = models.Account(
        name=name,
        type=account_type,
        subtype=subtype,
        current_balance=current_balance,
        starting_balance=starting_balance,
        currency=currency,
        is_active=is_active,
        plaid_account_id=None,
        item_id=None,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def update_manual_account(
    db: Session,
    account_id: UUID,
    update_data: Mapping[str, Any],
) -> Optional[models.Account]:
    """
    Updates whitelisted scalar fields of an account if present and not None.
    Preserves existing values for omitted or explicitly null fields.
    Returns None if account does not exist.
    Owns commit and refresh for standalone CRUD persistence.
    """
    account = get_account_by_id(db, account_id)
    if account is None:
        return None

    allowed_fields = (
        "name",
        "type",
        "subtype",
        "is_active",
        "starting_balance",
        "current_balance",
    )
    for field in allowed_fields:
        if field in update_data:
            value = update_data[field]
            if value is not None:
                setattr(account, field, value)

    db.commit()
    db.refresh(account)
    return account


def delete_account(
    db: Session,
    account_id: UUID,
) -> bool:
    """
    Deletes an account by primary key.
    Returns False if account does not exist, True on successful deletion.
    Owns commit for standalone CRUD persistence.
    """
    account = get_account_by_id(db, account_id)
    if account is None:
        return False

    db.delete(account)
    db.commit()
    return True


