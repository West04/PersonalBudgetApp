import uuid
from datetime import datetime
from typing import Optional

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
    Index,
    CheckConstraint,
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
    categorization_rules = relationship("CategorizationRule", back_populates="category", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("group_id", "name", name="uq_category_group_name"),)


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    plaid_transaction_id = Column(String, unique=True, nullable=True, index=True)

    # NOTE: Keep this pointing to accounts.id (your current schema)
    account_id = Column(UUID, ForeignKey("accounts.id"), nullable=False)
    category_id = Column(UUID, ForeignKey("categories.category_id", ondelete="SET NULL"), nullable=True, index=True)

    description = Column(Text)
    merchant = Column(String, nullable=True)
    is_merchant_overridden = Column(Boolean, default=False, nullable=False, server_default="false")
    amount = Column(DECIMAL(10, 2), nullable=False)  # Positive = outflow, Negative = inflow
    date = Column(DATE, nullable=False, index=True)
    datetime = Column(TIMESTAMP(timezone=True), nullable=True)
    pending = Column(Boolean, default=False, nullable=False)
    is_transfer = Column(Boolean, default=False, nullable=False)
    is_reviewed = Column(Boolean, default=False, nullable=False, server_default="false")
    is_cleared = Column(Boolean, default=False, nullable=False, server_default="false")
    is_reconciled = Column(Boolean, default=False, nullable=False, server_default="false")
    category_source = Column(String(20), nullable=True)  # manual | rule | ml | legacy
    plaid_reconciliation_conflict_amount = Column(DECIMAL(10, 2), nullable=True)
    plaid_reconciliation_conflict_at = Column(TIMESTAMP(timezone=True), nullable=True)

    category = relationship("Category", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    splits = relationship(
        "TransactionSplit",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionSplit.created_at",
    )

    @property
    def is_split(self) -> bool:
        return bool(self.splits)

    @property
    def split_count(self) -> int:
        return len(self.splits) if self.splits else 0


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

    # Balances
    current_balance = Column(DECIMAL(12, 2), nullable=False, default=0)
    available_balance = Column(DECIMAL(12, 2), nullable=True)
    starting_balance = Column(DECIMAL(12, 2), nullable=False, default=0)  # Seed balance for CSV-based accounts
    currency = Column(String, nullable=False, default="USD")
    balance_last_updated = Column(TIMESTAMP(timezone=True), nullable=True)
    last_reconciled_date = Column(DATE, nullable=True)
    last_reconciled_balance = Column(DECIMAL(12, 2), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    item = relationship("PlaidItem", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")


class CSVFormat(Base):
    __tablename__ = "csv_formats"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)

    date_column = Column(String(100), nullable=False)
    description_column = Column(String(100), nullable=False)
    amount_column = Column(String(100), nullable=False)
    status_column = Column(String(100), nullable=True)

    date_format = Column(String(50), nullable=False)
    amount_sign_convention = Column(String(30), nullable=False)
    status_posted_value = Column(String(50), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_csv_formats_name_lower", func.lower(name), unique=True),
        CheckConstraint(
            "amount_sign_convention IN ('positive_is_outflow', 'positive_is_inflow')",
            name="chk_csv_formats_amount_sign_convention",
        ),
    )


class CategorizationRule(Base):
    __tablename__ = "categorization_rules"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    merchant = Column(String, nullable=False)
    category_id = Column(
        UUID,
        ForeignKey("categories.category_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    category = relationship("Category", back_populates="categorization_rules")

    __table_args__ = (
        Index(
            "uq_categorization_rules_merchant_canonical",
            func.lower(func.trim(merchant)),
            unique=True,
        ),
    )


class MLModelMetadata(Base):
    __tablename__ = "ml_model_metadata"

    id = Column(Integer, primary_key=True, default=1)
    current_training_revision = Column(Integer, nullable=False, default=0)
    trained_revision = Column(Integer, nullable=False, default=0)
    trained_at = Column(TIMESTAMP(timezone=True), nullable=True)
    training_example_count = Column(Integer, nullable=False, default=0)
    model_available = Column(Boolean, nullable=False, default=False)
    accuracy = Column(DECIMAL(5, 4), nullable=True)
    macro_f1 = Column(DECIMAL(5, 4), nullable=True)
    top2_accuracy = Column(DECIMAL(5, 4), nullable=True)
    coverage = Column(DECIMAL(5, 4), nullable=True)
    status_message = Column(String, nullable=True)


class RecurringItem(Base):
    __tablename__ = "recurring_items"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant = Column(String, nullable=False)
    direction = Column(String(10), nullable=False)  # outflow | inflow
    cadence = Column(String(20), nullable=False)    # weekly | biweekly | monthly | annual
    amount_type = Column(String(20), nullable=False, default="fixed")  # fixed | variable
    expected_amount = Column(DECIMAL(10, 2), nullable=False)
    status = Column(String(20), nullable=False, default="detected")  # detected | confirmed | dismissed
    last_date = Column(DATE, nullable=False)
    next_expected_date = Column(DATE, nullable=True)
    occurrence_count = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    account = relationship("Account")

    __table_args__ = (
        Index(
            "uq_recurring_items_identity",
            account_id,
            func.lower(func.trim(merchant)),
            direction,
            cadence,
            unique=True,
        ),
    )


class TransactionSplit(Base):
    __tablename__ = "transaction_splits"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    transaction_id = Column(
        UUID,
        ForeignKey("transactions.transaction_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id = Column(
        UUID,
        ForeignKey("categories.category_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount = Column(DECIMAL(10, 2), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    transaction = relationship("Transaction", back_populates="splits")
    category = relationship("Category")

    @property
    def category_name(self) -> Optional[str]:
        return self.category.name if self.category else None

    __table_args__ = (
        UniqueConstraint(
            "transaction_id",
            "category_id",
            name="uq_transaction_splits_tx_cat",
        ),
    )



