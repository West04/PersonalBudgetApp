from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)


@router.post("/", response_model=schemas.CategoryRead)
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new category.
    """
    return crud.create_category(db=db, new_category=category)


@router.get("/{category_id}", response_model=schemas.CategoryRead)
def read_category(
    category_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get a specific category by its ID.
    """
    return crud.get_category(db=db, category_id=category_id)
