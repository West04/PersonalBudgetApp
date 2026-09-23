"""
Resource access functions for Budget PostgreSQL resources.
"""

from collections.abc import Sequence
from datetime import date
from sqlalchemy.orm import Session

from .. import models


def get_budgets_for_month(db: Session, budget_month: date) -> Sequence[models.Budget]:
    """
    Retrieves all budget allocations for the specified month date.
    """
    return (
        db.query(models.Budget)
        .filter(models.Budget.budget_month == budget_month)
        .all()
    )
