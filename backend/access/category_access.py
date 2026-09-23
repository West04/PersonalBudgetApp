"""
Resource access functions for Category and CategoryGroup PostgreSQL resources.
"""

from collections.abc import Sequence
from sqlalchemy.orm import Session, selectinload

from .. import models


def get_category_groups(db: Session) -> Sequence[models.CategoryGroup]:
    """
    Retrieves all CategoryGroups with their associated Categories eagerly loaded,
    ordered by sort_order.
    """
    return (
        db.query(models.CategoryGroup)
        .options(selectinload(models.CategoryGroup.categories))
        .order_by(models.CategoryGroup.sort_order)
        .all()
    )
