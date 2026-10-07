"""
Resource access functions for PlaidItem PostgreSQL resources.
"""

from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from .. import models


def get_plaid_item_by_id(
    db: Session,
    item_id: UUID,
) -> Optional[models.PlaidItem]:
    """
    Retrieves a PlaidItem by its primary key UUID.
    """
    return (
        db.query(models.PlaidItem)
        .filter(models.PlaidItem.id == item_id)
        .first()
    )


def get_plaid_item_by_plaid_item_id(
    db: Session,
    plaid_item_id: str,
) -> Optional[models.PlaidItem]:
    """
    Retrieves a PlaidItem by its unique Plaid item ID string.
    """
    return (
        db.query(models.PlaidItem)
        .filter(models.PlaidItem.plaid_item_id == plaid_item_id)
        .first()
    )


def stage_transactions_cursor(
    db: Session,
    plaid_item_id: str,
    cursor: str,
) -> None:
    """
    Looks up PlaidItem by plaid_item_id, assigns transactions_cursor, and adds to session.
    Performs NO database commit or flush.
    """
    plaid_item = get_plaid_item_by_plaid_item_id(db, plaid_item_id)
    if plaid_item:
        plaid_item.transactions_cursor = cursor
        db.add(plaid_item)


def create_plaid_item(
    db: Session,
    plaid_item_id: str,
    access_token: str,
) -> models.PlaidItem:
    """
    Encapsulates token encryption, stages a new models.PlaidItem, and flushes
    to assign the primary key UUID. Performs NO database commit.
    """
    from ..security import encrypt_token

    encrypted_access_token = encrypt_token(access_token)
    db_item = models.PlaidItem(
        plaid_item_id=plaid_item_id,
        plaid_access_token_encrypted=encrypted_access_token,
        transactions_cursor=None,
    )
    db.add(db_item)
    db.flush()
    return db_item


