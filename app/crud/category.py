from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from ..models import Category
from ..schemas import CategoryCreate, CategoryUpdate


def get_category(db: Session, category_id: UUID) -> Optional[Category]:
    return db.query(Category).filter(Category.category_id == category_id).first()


def list_categories(db: Session, parent_id: Optional[UUID] = None) -> List[Category]:
    q = db.query(Category)
    if parent_id is not None:
        q = q.filter(Category.parent_id == parent_id)
    return q.all()


def create_category(db: Session, new_category: CategoryCreate) -> Category:
    db_category = Category(
        **new_category.model_dump()
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, category_id: UUID) -> Optional[Category]:
    db_category = db.query(Category).filter(Category.category_id == category_id).first()
    if db_category is None:
        return None

    db.delete(db_category)
    db.commit()
    return db_category


def update_category(db: Session, category_id: UUID, update_category: CategoryUpdate) -> Optional[Category]:
    db_category = db.query(Category).filter(Category.category_id == category_id).first()
    if db_category is None:
        return None

    if update_category.name is not None:
        db_category.name = update_category.name

    if update_category.parent_id is not None:
        # Prevent setting a category's parent to itself
        if update_category.parent_id == category_id:
            return None
        db_category.parent_id = update_category.parent_id

    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category
