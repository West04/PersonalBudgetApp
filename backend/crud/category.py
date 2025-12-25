from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session, selectinload

from ..models import Category, CategoryGroup
from ..schemas import CategoryCreate, CategoryUpdate, CategoryGroupCreate, CategoryGroupUpdate


# --- Category Group CRUD ---

def get_category_group(db: Session, group_id: UUID) -> Optional[CategoryGroup]:
    return db.query(CategoryGroup).filter(CategoryGroup.category_group_id == group_id).first()


def list_category_groups(db: Session) -> List[CategoryGroup]:
    return (
        db.query(CategoryGroup)
        .options(selectinload(CategoryGroup.categories))
        .order_by(CategoryGroup.sort_order)
        .all()
    )


def create_category_group(db: Session, new_group: CategoryGroupCreate) -> CategoryGroup:
    db_group = CategoryGroup(
        **new_group.model_dump()
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group


def update_category_group(db: Session, group_id: UUID, update_data: CategoryGroupUpdate) -> Optional[CategoryGroup]:
    db_group = get_category_group(db, group_id)
    if not db_group:
        return None

    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(db_group, key, value)

    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group


def delete_category_group(db: Session, group_id: UUID) -> Optional[CategoryGroup]:
    db_group = get_category_group(db, group_id)
    if not db_group:
        return None

    db.delete(db_group)
    db.commit()
    return db_group


# --- Category CRUD ---

def get_category(db: Session, category_id: UUID) -> Optional[Category]:
    return db.query(Category).filter(Category.category_id == category_id).first()


def list_categories(db: Session, group_id: Optional[UUID] = None) -> List[Category]:
    q = db.query(Category)
    if group_id is not None:
        q = q.filter(Category.group_id == group_id)
    # Order by sort_order
    q = q.order_by(Category.sort_order)
    return q.all()


def create_category(db: Session, new_category: CategoryCreate) -> Category:
    db_category = Category(
        **new_category.model_dump()
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def update_category(db: Session, category_id: UUID, update_category: CategoryUpdate) -> Optional[Category]:
    db_category = get_category(db, category_id)
    if not db_category:
        return None

    # This will automatically handle name, group_id, sort_order, type, is_active
    # as long as they are in the CategoryUpdate schema
    update_dict = update_category.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(db_category, key, value)

    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, category_id: UUID) -> Optional[Category]:
    db_category = get_category(db, category_id)
    if not db_category:
        return None

    db.delete(db_category)
    db.commit()
    return db_category
