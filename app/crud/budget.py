from uuid import UUID
from datetime import date

from sqlalchemy.orm import Session

from ..models import Budgets
from ..schemas import BudgetCreate


def create_budget(db: Session, new_budget: BudgetCreate):
    db_budget = Budgets(
        budget_month=new_budget.budget_month,
        planned_amount=new_budget.planned_amount,
        category_id=new_budget.category_id
    )
    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget


def list_budget(db: Session, budget_month: date = None):
    q = db.query(Budgets)
    if budget_month is not None:
        q = q.filter(Budgets.category_id == budget_month)
    return q.all()


def get_budget(db: Session, budget_id: UUID):
    return db.query(Budgets).filter(Budgets.budget_id == budget_id).first()


def update_budget(db: Session, budget_id: UUID, new_name: str, new_amount: float):
    db_budget = db.query(Budgets).filter(Budgets.budget_id == budget_id).first()
    if db_budget is None:
        return None

    if new_name is not None:
        db_budget.name = new_name

    if new_amount is not None:
        db_budget.amount = new_amount

    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget



def delete_budget(db: Session, budget_id: UUID):
    db_budget = db.query(Budgets).filter(Budgets.budget_id == budget_id).first()
    if db_budget is None:
        return None
    db.delete(db_budget)
    db.commit()
    return db_budget
