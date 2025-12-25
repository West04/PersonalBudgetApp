from uuid import UUID
from typing import Optional, List

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..crud import category as crud_category
from ..database import get_db

router = APIRouter(
    tags=["Categories"],
)

# ==========================================
# Category Groups
# ==========================================

@router.post("/category-groups", response_model=schemas.CategoryGroupRead, status_code=status.HTTP_201_CREATED)
def create_category_group(
    group: schemas.CategoryGroupCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new category group.
    """
    return crud_category.create_category_group(db=db, new_group=group)


@router.get("/category-groups", response_model=List[schemas.CategoryGroupWithCategories])
def list_category_groups(
    db: Session = Depends(get_db)
):
    """
    List all category groups, including their nested categories.
    Ordered by sort_order.
    """
    # The CRUD returns pure CategoryGroup models.
    # Pydantic's 'from_attributes=True' in CategoryGroupWithCategories
    # will handle the 'categories' relationship automatically.
    return crud_category.list_category_groups(db=db)


@router.get("/category-groups/{group_id}", response_model=schemas.CategoryGroupRead)
def read_category_group(
    group_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get a specific category group by its ID.
    """
    db_group = crud_category.get_category_group(db=db, group_id=group_id)
    if db_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category Group not found'
        )
    return db_group


@router.put("/category-groups/{group_id}", response_model=schemas.CategoryGroupRead, status_code=status.HTTP_200_OK)
def update_category_group(
    group_id: UUID,
    payload: schemas.CategoryGroupUpdate,
    db: Session = Depends(get_db)
):
    """
    Update a category group.
    """
    updated = crud_category.update_category_group(
        db=db,
        group_id=group_id,
        update_data=payload
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category Group not found'
        )
    return updated


@router.delete("/category-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category_group(
    group_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Delete a category group.
    """
    deleted = crud_category.delete_category_group(
        db=db,
        group_id=group_id
    )
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category Group not found'
        )
    return None


# ==========================================
# Categories
# ==========================================

@router.post("/categories", response_model=schemas.CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new category.
    """
    # We might want to validate that group_id exists,
    # but the FK constraint will catch it (500 error instead of 404/400).
    return crud_category.create_category(db=db, new_category=category)


@router.get("/categories", response_model=List[schemas.CategoryRead])
def list_categories(
    group_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    """
    List categories. Optionally filter by group_id.
    """
    return crud_category.list_categories(db=db, group_id=group_id)


@router.get("/categories/{category_id}", response_model=schemas.CategoryRead)
def read_category(
    category_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get a specific category by its ID.
    """
    db_category = crud_category.get_category(db=db, category_id=category_id)

    if db_category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found'
        )

    return db_category


@router.put("/categories/{category_id}", response_model=schemas.CategoryRead, status_code=status.HTTP_200_OK)
def update_category(
        category_id: UUID,
        payload: schemas.CategoryUpdate,
        db: Session = Depends(get_db)
):
    """
    Update a specific category by its ID.
    """
    updated = crud_category.update_category(
        db=db,
        category_id=category_id,
        update_category=payload
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found'
        )

    return updated


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
        category_id: UUID,
        db: Session = Depends(get_db)
):
    deleted = crud_category.delete_category(
        db=db,
        category_id=category_id
    )
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found'
        )
    return None
