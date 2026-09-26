"""
Resource access functions for Budget PostgreSQL resources.
"""

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from .. import models


def get_budgets_for_month(db: Session, budget_month: date) -> Sequence[models.Budget]:
    """
    Retrieves all budget allocations for the specified month date.
    Used by BudgetSummaryManager for monthly budget calculations.
    """
    return (
        db.query(models.Budget)
        .filter(models.Budget.budget_month == budget_month)
        .all()
    )


def get_budget_by_id(db: Session, budget_id: UUID) -> Optional[models.Budget]:
    """
    Retrieves a single Budget allocation by primary key.
    """
    return db.query(models.Budget).filter(models.Budget.budget_id == budget_id).first()


def list_budgets(
    db: Session,
    budget_month: Optional[date] = None,
) -> Sequence[models.Budget]:
    """
    Lists budget allocations, optionally filtered by budget_month.
    Ordering is unspecified to match existing behavior.
    """
    q = db.query(models.Budget)
    if budget_month is not None:
        q = q.filter(models.Budget.budget_month == budget_month)
    return q.all()


def create_budget(
    db: Session,
    budget_month: date,
    planned_amount: Decimal,
    category_id: UUID,
) -> models.Budget:
    """
    Creates and persists a new Budget allocation.
    """
    db_budget = models.Budget(
        budget_month=budget_month,
        planned_amount=planned_amount,
        category_id=category_id,
    )
    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget


def update_budget(
    db: Session,
    budget_id: UUID,
    update_data: Mapping[str, Any],
) -> Optional[models.Budget]:
    """
    Updates attributes on an existing Budget allocation from a mapping.
    Preserves omitted fields and applies explicit None values.
    """
    db_budget = get_budget_by_id(db, budget_id)
    if db_budget is None:
        return None

    for key, value in update_data.items():
        setattr(db_budget, key, value)

    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget


def delete_budget(
    db: Session,
    budget_id: UUID,
) -> Optional[models.Budget]:
    """
    Deletes an existing Budget allocation by primary key.
    Returns the deleted instance if found, or None if not found.
    """
    db_budget = get_budget_by_id(db, budget_id)
    if db_budget is None:
        return None

    db.delete(db_budget)
    db.commit()
    return db_budget
