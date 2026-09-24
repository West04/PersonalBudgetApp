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

