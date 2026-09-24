"""
Resource access functions for Account PostgreSQL resources.
"""

from collections.abc import Sequence
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

