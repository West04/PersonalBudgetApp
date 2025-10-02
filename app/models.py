import uuid
from datetime import datetime

from sqlalchemy import Column, UUID, ForeignKey, Text, DECIMAL, DATE, UniqueConstraint, TIMESTAMP, func
from .database import Base


class Category(Base):
    __tablename__ = 'categories'

    category_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    parent_id = Column(UUID, ForeignKey('categories.category_id'))
    created_at = Column(TIMESTAMP,
                        server_default=func.now(),
                        nullable=False)


class Transaction(Base):
    __tablename__ = 'transactions'

    transaction_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    description = Column(Text)
    amount = Column(DECIMAL(10, 2), nullable=False)
    transaction_date = Column(TIMESTAMP,
                              server_default=func.now(),
                              nullable=False)
    category_id = Column(UUID, ForeignKey('categories.category_id'))


class Budgets(Base):
    __tablename__ = 'budgets'

    budget_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    budget_month = Column(DATE, nullable=False)
    planned_amount = Column(DECIMAL(10, 2), nullable=False)
    category_id = Column(UUID, ForeignKey('categories.category_id'))

    __table_args__ = (
        UniqueConstraint(budget_month, category_id)
    )

    