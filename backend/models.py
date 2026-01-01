import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    UUID,
    ForeignKey,
    Text,
    DECIMAL,
    DATE,
    UniqueConstraint,
    TIMESTAMP,
    func,
    String,
    Boolean,
    Integer,
)
from sqlalchemy.orm import relationship

from .database import Base


class CategoryGroup(Base):
    __tablename__ = "category_groups"

    category_group_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    categories = relationship(
        "Category",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="Category.sort_order",
    )


class Category(Base):
    __tablename__ = "categories"

    category_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    group_id = Column(
        UUID,
        ForeignKey("category_groups.category_group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    type = Column(String, nullable=False, default="expense")  # income|expense|transfer
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    group = relationship("CategoryGroup", back_populates="categories")
    transactions = relationship("Transaction", back_populates="category")
    budgets = relationship("Budget", back_populates="category")

    __table_args__ = (UniqueConstraint("group_id", "name", name="uq_category_group_name"),)


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    plaid_transaction_id = Column(String, unique=True, nullable=True, index=True)

    # NOTE: Keep this pointing to accounts.id (your current schema)
    account_id = Column(UUID, ForeignKey("accounts.id"), nullable=False)
    category_id = Column(UUID, ForeignKey("categories.category_id", ondelete="SET NULL"), nullable=True, index=True)

    description = Column(Text)
    amount = Column(DECIMAL(10, 2), nullable=False)  # Positive = outflow, Negative = inflow
    date = Column(DATE, nullable=False, index=True)
    datetime = Column(TIMESTAMP(timezone=True), nullable=True)
    pending = Column(Boolean, default=False, nullable=False)

    category = relationship("Category", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")


class Budget(Base):
    __tablename__ = "budgets"

    budget_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    budget_month = Column(DATE, nullable=False)
    planned_amount = Column(DECIMAL(10, 2), nullable=False)
    category_id = Column(UUID, ForeignKey("categories.category_id", ondelete="CASCADE"))

    __table_args__ = (UniqueConstraint("budget_month", "category_id", name="_budget_month_category_uc"),)

    category = relationship("Category", back_populates="budgets")


class PlaidItem(Base):
    __tablename__ = "plaid_items"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    plaid_item_id = Column(String, unique=True, nullable=False, index=True)
    plaid_access_token_encrypted = Column(String, nullable=False)
    transactions_cursor = Column(String, nullable=True)

    accounts = relationship("Account", back_populates="item")


class Account(Base):
    __tablename__ = "accounts"

    # Keep your existing PK name "id" to avoid breaking FKs
    id = Column(UUID, primary_key=True, default=uuid.uuid4)

    plaid_account_id = Column(String, unique=True, nullable=True, index=True)
    item_id = Column(UUID, ForeignKey("plaid_items.id"), nullable=True)

    name = Column(String, nullable=False)
    mask = Column(String, nullable=True)
    type = Column(String, nullable=False)
    subtype = Column(String, nullable=True)

    # ✅ Persisted balances (Plaid source of truth)
    current_balance = Column(DECIMAL(12, 2), nullable=False, default=0)
    available_balance = Column(DECIMAL(12, 2), nullable=True)
    currency = Column(String, nullable=False, default="USD")
    balance_last_updated = Column(TIMESTAMP(timezone=True), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    item = relationship("PlaidItem", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")
