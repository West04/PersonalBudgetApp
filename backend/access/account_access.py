"""
Resource access functions for Account PostgreSQL resources.
"""

from collections.abc import Sequence
from sqlalchemy.orm import Session

from .. import models


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
