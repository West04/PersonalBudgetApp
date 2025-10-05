from uuid import UUID
from sqlalchemy.orm import Session

from ..models import Category
from ..schemas import CategoryCreate


def get_category(db: Session, category_id: UUID):
    return db.query(Category).filter(Category.category_id == category_id).first()


def create_category(db: Session, new_category: CategoryCreate):
    db_category = Category(name=new_category.name, parent_id=new_category.parent_id)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category
