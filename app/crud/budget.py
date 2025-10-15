from uuid import UUID
from datetime import date

from sqlalchemy.orm import Session

from ..models import Budget
from ..schemas import BudgetCreate, BudgetUpdate


def create_budget(db: Session, new_budget: BudgetCreate):
    db_budget = Budget(
        budget_month=new_budget.budget_month,
        planned_amount=new_budget.planned_amount,
        category_id=new_budget.category_id
    )
    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget


def list_budget(db: Session, budget_month: date = None):
    q = db.query(Budget)
    if budget_month is not None:
        q = q.filter(Budget.budget_month == budget_month)
    return q.all()


def get_budget(db: Session, budget_id: UUID):
    return db.query(Budget).filter(Budget.budget_id == budget_id).first()


def update_budget(db: Session, budget_id: UUID, update_budget: BudgetUpdate):
    db_budget = db.query(Budget).filter(Budget.budget_id == budget_id).first()
    if db_budget is None:
        return None

    if update_budget.budget_month is not None:
        db_budget.budget_month = update_budget.budget_month

    if update_budget.planned_amount is not None:
        db_budget.planned_amount = update_budget.planned_amount

    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget



def delete_budget(db: Session, budget_id: UUID):
    db_budget = db.query(Budget).filter(Budget.budget_id == budget_id).first()
    if db_budget is None:
        return None
    db.delete(db_budget)
    db.commit()
    return db_budget
