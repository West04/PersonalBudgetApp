from datetime import date
from uuid import UUID

from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..crud import budget as crud_budget
from ..database import get_db


router = APIRouter(
    prefix="/budget",
    tags=["Budget"],
)

@router.post("/", response_model=schemas.BudgetRead, status_code=status.HTTP_201_CREATED)
def create_budget(
        budget: schemas.BudgetCreate,
        db: Session = Depends(get_db)
):
    """
        Create a new Budget.
    """

    return crud_budget.create_budget(db=db, new_budget=budget)


@router.get("/", response_model=list[schemas.BudgetRead], status_code=status.HTTP_200_OK)
def list_budget(
        budget_month: date = None,
        db: Session = Depends(get_db)
):
    """
        List budgets. Optionally filter by budget_month.
    """
    return crud_budget.list_budget(db=db, budget_month=budget_month)


@router.get("/{budget_id}", response_model=schemas.BudgetRead, status_code=status.HTTP_200_OK)
def get_budget(
        budget_id: UUID,
        db: Session = Depends(get_db)
):
    """
    Get a specific budget by its ID.
    """
    db_budget = crud_budget.get_budget(budget_id=budget_id, db=db)

    if db_budget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found'
        )

    return db_budget


@router.put("/{budget_id}", response_model=schemas.BudgetRead, status_code=status.HTTP_202_ACCEPTED)
def update_budget(
        budget_id: UUID,
        payload: schemas.BudgetUpdate,
        db: Session = Depends(get_db)
):
    db_budget = crud_budget.update_budget(
        db=db,
        budget_id=budget_id,
        update_budget=payload
    )

    if db_budget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found or invalid update'
        )

    return db_budget


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
        budget_id: UUID,
        db: Session = Depends(get_db)
):
    deleted = crud_budget.delete_budget(
        db=db,
        budget_id=budget_id
    )

    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found'
        )

    return None
