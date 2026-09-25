from uuid import UUID
from typing import Optional, List

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..access import category_access
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
    return category_access.create_category_group(
        db=db,
        name=group.name,
        sort_order=group.sort_order,
    )


@router.get("/category-groups", response_model=List[schemas.CategoryGroupWithCategories])
def list_category_groups(
    db: Session = Depends(get_db)
):
    """
    List all category groups, including their nested categories.
    Ordered by sort_order.
    """
    # Pydantic's 'from_attributes=True' in CategoryGroupWithCategories
    # will handle the 'categories' relationship automatically.
    return category_access.get_category_groups(db=db)


@router.get("/category-groups/{group_id}", response_model=schemas.CategoryGroupRead)
def read_category_group(
    group_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get a specific category group by its ID.
    """
    db_group = category_access.get_category_group_by_id(db=db, group_id=group_id)
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
    updated = category_access.update_category_group(
        db=db,
        group_id=group_id,
        update_data=payload.model_dump(exclude_unset=True),
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
    deleted = category_access.delete_category_group(
        db=db,
        group_id=group_id,
    )
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category Group not found'
        )
    return None


@router.post("/category-groups/reorder", response_model=List[schemas.CategoryGroupWithCategories])
def reorder_category_groups(
    payload: schemas.ReorderRequest,
    db: Session = Depends(get_db)
):
    """
    Bulk reorder category groups by providing an ordered list of group IDs.
    """
    return category_access.reorder_category_groups(db=db, ordered_ids=payload.order)


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
    return category_access.create_category(
        db=db,
        name=category.name,
        group_id=category.group_id,
        sort_order=category.sort_order,
        type=category.type,
        is_active=category.is_active,
    )


@router.get("/categories", response_model=List[schemas.CategoryRead])
def list_categories(
    group_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    """
    List categories. Optionally filter by group_id.
    """
    return category_access.list_categories(db=db, group_id=group_id)


@router.get("/categories/{category_id}", response_model=schemas.CategoryRead)
def read_category(
    category_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get a specific category by its ID.
    """
    db_category = category_access.get_category_by_id(db=db, category_id=category_id)

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
    updated = category_access.update_category(
        db=db,
        category_id=category_id,
        update_data=payload.model_dump(exclude_unset=True),
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
    deleted = category_access.delete_category(
        db=db,
        category_id=category_id,
    )
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Category not found'
        )
    return None


@router.post("/categories/reorder", response_model=List[schemas.CategoryRead])
def reorder_categories(
    payload: schemas.CategoryReorderRequest,
    db: Session = Depends(get_db)
):
    """
    Bulk reorder categories within a group by providing an ordered list of category IDs.
    """
    return category_access.reorder_categories(
        db=db,
        group_id=payload.group_id,
        ordered_ids=payload.order,
    )
