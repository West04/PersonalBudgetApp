"""
Resource access functions for Category and CategoryGroup PostgreSQL resources.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session, selectinload

from .. import models


# --- CategoryGroup Persistence Operations ---

def get_category_groups(db: Session) -> Sequence[models.CategoryGroup]:
    """
    Retrieves all CategoryGroups with their associated Categories eagerly loaded,
    ordered by sort_order.
    """
    return (
        db.query(models.CategoryGroup)
        .options(selectinload(models.CategoryGroup.categories))
        .order_by(models.CategoryGroup.sort_order)
        .all()
    )


def get_category_group_by_id(db: Session, group_id: UUID) -> Optional[models.CategoryGroup]:
    """
    Retrieves a single CategoryGroup by primary key.
    """
    return db.query(models.CategoryGroup).filter(models.CategoryGroup.category_group_id == group_id).first()


def create_category_group(
    db: Session,
    name: str,
    sort_order: int = 0,
) -> models.CategoryGroup:
    """
    Creates and persists a new CategoryGroup.
    """
    db_group = models.CategoryGroup(
        name=name,
        sort_order=sort_order,
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group


def update_category_group(
    db: Session,
    group_id: UUID,
    update_data: Mapping[str, Any],
) -> Optional[models.CategoryGroup]:
    """
    Updates attributes on an existing CategoryGroup.
    Applies all supplied keys without filtering out None values,
    preserving schema/database integrity constraints.
    """
    db_group = get_category_group_by_id(db, group_id)
    if not db_group:
        return None

    for key, value in update_data.items():
        setattr(db_group, key, value)

    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group


def delete_category_group(db: Session, group_id: UUID) -> Optional[models.CategoryGroup]:
    """
    Deletes a CategoryGroup. Blocks deletion if the group contains child categories.
    """
    db_group = get_category_group_by_id(db, group_id)
    if not db_group:
        return None

    has_categories = (
        db.query(models.Category)
        .filter(models.Category.group_id == group_id)
        .first()
        is not None
    )
    if has_categories:
        raise ValueError("Cannot delete category group containing categories. Move or delete categories first.")

    db.delete(db_group)
    db.commit()
    return db_group


def reorder_category_groups(
    db: Session,
    ordered_ids: Sequence[UUID],
) -> Sequence[models.CategoryGroup]:
    """
    Updates sort_order for category groups based on their index in ordered_ids.
    Unknown IDs are ignored; unlisted groups retain existing sort_order.
    Duplicate IDs use last occurrence wins.
    Performs a single commit and returns all category groups with nested categories.
    """
    for index, group_id in enumerate(ordered_ids):
        db_group = get_category_group_by_id(db, group_id)
        if db_group:
            db_group.sort_order = index
            db.add(db_group)
    db.commit()
    return get_category_groups(db)


# --- Category Persistence Operations ---

def get_category_by_id(db: Session, category_id: UUID) -> Optional[models.Category]:
    """
    Retrieves a single Category by primary key.
    """
    return db.query(models.Category).filter(models.Category.category_id == category_id).first()


def list_categories(
    db: Session,
    group_id: Optional[UUID] = None,
) -> Sequence[models.Category]:
    """
    Retrieves categories ordered by sort_order, optionally filtered by group_id.
    """
    q = db.query(models.Category)
    if group_id is not None:
        q = q.filter(models.Category.group_id == group_id)
    return q.order_by(models.Category.sort_order).all()


def create_category(
    db: Session,
    name: str,
    group_id: UUID,
    sort_order: int = 0,
    type: str = "expense",
    is_active: bool = True,
) -> models.Category:
    """
    Creates and persists a new Category.
    """
    db_category = models.Category(
        name=name,
        group_id=group_id,
        sort_order=sort_order,
        type=type,
        is_active=is_active,
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def update_category(
    db: Session,
    category_id: UUID,
    update_data: Mapping[str, Any],
) -> Optional[models.Category]:
    """
    Updates attributes on an existing Category.
    Applies all supplied keys without filtering out None values,
    preserving schema/database integrity constraints.
    """
    db_category = get_category_by_id(db, category_id)
    if not db_category:
        return None

    for key, value in update_data.items():
        setattr(db_category, key, value)

    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, category_id: UUID) -> Optional[models.Category]:
    """
    Deletes a Category. Transactions and budgets survive with category_id = NULL.
    Blocks deletion if referenced by any split allocations to protect split accounting invariants.
    """
    db_category = get_category_by_id(db, category_id)
    if not db_category:
        return None

    from . import split_access
    if split_access.count_splits_by_category(db, category_id) > 0:
        raise ValueError("Cannot delete category referenced by split allocations. Reassign or remove splits first.")

    db.delete(db_category)
    db.commit()
    return db_category


def reorder_categories(
    db: Session,
    group_id: UUID,
    ordered_ids: Sequence[UUID],
) -> Sequence[models.Category]:
    """
    Updates sort_order for categories belonging to group_id based on index in ordered_ids.
    Unknown IDs and categories from other groups are ignored; unlisted categories retain existing sort_order.
    Duplicate IDs use last occurrence wins.
    Performs a single commit and returns all categories in group_id.
    """
    for index, category_id in enumerate(ordered_ids):
        db_category = get_category_by_id(db, category_id)
        if db_category and db_category.group_id == group_id:
            db_category.sort_order = index
            db.add(db_category)
    db.commit()
    return list_categories(db, group_id=group_id)
