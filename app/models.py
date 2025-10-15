import uuid

from sqlalchemy import Column, UUID, ForeignKey, Text, DECIMAL, DATE, UniqueConstraint, TIMESTAMP, func
from sqlalchemy.orm import relationship

from .database import Base


class Category(Base):
    __tablename__ = 'categories'

    category_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)
    parent_id = Column(UUID, ForeignKey('categories.category_id', ondelete="CASCADE"))
    created_at = Column(TIMESTAMP,
                        server_default=func.now(),
                        nullable=False)

    # Relationships
    transactions = relationship("Transaction", back_populates="category")
    budgets = relationship("Budget", back_populates="category")
    parent = relationship("Category", remote_side=[category_id], back_populates="subcategories")
    subcategories = relationship("Category", back_populates="parent")


class Transaction(Base):
    __tablename__ = 'transactions'

    transaction_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    description = Column(Text)
    amount = Column(DECIMAL(10, 2), nullable=False)
    category_id = Column(UUID, ForeignKey('categories.category_id', ondelete="SET NULL"))
    transaction_date = Column(TIMESTAMP,
                              server_default=func.now(),
                              nullable=False)

    # Relationship
    category = relationship("Category", back_populates="transactions")


class Budget(Base):
    __tablename__ = 'budgets'

    budget_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    budget_month = Column(DATE, nullable=False)
    planned_amount = Column(DECIMAL(10, 2), nullable=False)
    category_id = Column(UUID, ForeignKey('categories.category_id', ondelete="CASCADE"))

    __table_args__ = (
        UniqueConstraint('budget_month', 'category_id', name='_budget_month_category_uc'),
    )

    # Relationship
    category = relationship("Category", back_populates="budgets")
