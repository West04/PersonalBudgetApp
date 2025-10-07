from uuid import UUID
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..crud import category
from ..database import get_db

router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)


@router.post("/", response_model=schemas.CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new category.
    """
    return category.create_category(db=db, new_category=category)


from typing import Optional


@router.get("/", response_model=list[schemas.CategoryRead])
def list_categories(parent_id: Optional[UUID] = None, db: Session = Depends(get_db)):
    """
    List categories. Optionally filter by parent_id to get subcategories.
    """
    return category.list_categories(db=db, parent_id=parent_id)


@router.get("/{category_id}", response_model=schemas.CategoryRead)
def read_category(
    category_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get a specific category by its ID.
    """
    db_category = category.get_category(db=db, category_id=category_id)

    if db_category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found'
        )

    return db_category


@router.put("/{category_id}", response_model=schemas.CategoryRead, status_code=status.HTTP_202_ACCEPTED)
def update_category(
        category_id: UUID,
        payload: schemas.CategoryUpdate,
        db: Session = Depends(get_db)
):
    """
    Update a specific category by its ID.
    """

    updated = category.update_category(
        db=db,
        category_id=category_id,
        new_name=payload.name,
        new_parent_id=payload.parent_id
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found or invalid update'
        )

    return updated


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
        category_id: UUID,
        db: Session = Depends(get_db)
):
    deleted = category.delete_category(
        db=db,
        category_id=category_id
    )
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found'
        )
    return None
