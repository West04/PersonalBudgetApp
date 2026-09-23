"""
Resource access functions for Transaction PostgreSQL resources.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models

ZERO = Decimal("0.00")


def get_actuals_by_category(
    db: Session,
    start_date: date,
    end_date: date,
) -> dict[UUID, Decimal]:
    """
    Aggregates transaction amount sums grouped by category_id for transactions
    within [start_date, end_date), ignoring uncategorized transactions.
    """
    trx_stats = (
        db.query(
            models.Transaction.category_id,
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(
            models.Transaction.date >= start_date,
            models.Transaction.date < end_date,
            models.Transaction.category_id.isnot(None),
        )
        .group_by(models.Transaction.category_id)
        .all()
    )
    return {t.category_id: (t.total or ZERO) for t in trx_stats}
