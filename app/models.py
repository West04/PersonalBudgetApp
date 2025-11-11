import uuid

from sqlalchemy import Column, UUID, ForeignKey, Text, DECIMAL, DATE, UniqueConstraint, TIMESTAMP, func, String, Boolean
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
    plaid_transaction_id = Column(String, unique=True, nullable=False, index=True)

    account_id = Column(UUID, ForeignKey('accounts.id'), nullable=False)
    category_id = Column(UUID, ForeignKey('categories.category_id', ondelete="SET NULL"), nullable=True, index=True)
    description = Column(Text)
    amount = Column(DECIMAL(10, 2), nullable=False)  # Positive = outflow, Negative = inflow
    date = Column(DATE, nullable=False, index=True)  # The date the transaction posted
    datetime = Column(TIMESTAMP(timezone=True), nullable=True)  # The datetime of the transaction
    pending = Column(Boolean, default=False, nullable=False)

    # Relationship
    category = relationship("Category", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")


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


class PlaidItem(Base):
    __tablename__ = 'plaid_items'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    plaid_item_id = Column(String, unique=True, nullable=False, index=True)
    plaid_access_token_encrypted = Column(String, nullable=False)
    transactions_cursor = Column(String, nullable=True)

    # Relationships
    accounts = relationship("Account", back_populates="item")


class Account(Base):
    __tablename__ = 'accounts'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    plaid_account_id = Column(String, unique=True, nullable=False, index=True)

    # Link back to the parent item
    item_id = Column(UUID, ForeignKey('plaid_items.id'), nullable=False)

    name = Column(String, nullable=False)
    mask = Column(String, nullable=True)
    type = Column(String, nullable=False)
    subtype = Column(String, nullable=False)

    # Relationships
    item = relationship("PlaidItem", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")