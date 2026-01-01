from uuid import UUID
from pydantic import BaseModel, ConfigDict, condecimal, Field
from datetime import date, datetime
from typing import Optional, List, Literal
from decimal import Decimal

DecimalAmount = condecimal(max_digits=10, decimal_places=2)

# --- Category Group Schemas ---

class CategoryGroupCreate(BaseModel):
    name: str
    sort_order: int = 0


class CategoryGroupRead(BaseModel):
    category_group_id: UUID
    name: str
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class CategoryGroupUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


# --- Category Schemas ---

CategoryType = Literal["income", "expense", "transfer"]


class CategoryCreate(BaseModel):
    name: str
    group_id: UUID
    sort_order: int = 0
    type: CategoryType = "expense"
    is_active: bool = True


class CategoryRead(BaseModel):
    category_id: UUID
    group_id: UUID
    name: str
    sort_order: int
    type: CategoryType
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    group_id: Optional[UUID] = None
    sort_order: Optional[int] = None
    type: Optional[CategoryType] = None
    is_active: Optional[bool] = None


# UI-friendly nested schema
class CategoryGroupWithCategories(CategoryGroupRead):
    categories: List[CategoryRead]


# --- Transaction Schemas ---

class TransactionCreate(BaseModel):
    plaid_transaction_id: Optional[str] = None
    account_id: UUID
    category_id: Optional[UUID] = None
    description: Optional[str] = None
    amount: DecimalAmount
    date: date
    datetime: Optional[datetime] = None
    pending: bool = False


class TransactionUpdate(BaseModel):
    description: Optional[str] = None
    category_id: Optional[UUID] = None


class TransactionRead(BaseModel):
    transaction_id: UUID
    plaid_transaction_id: Optional[str]
    account_id: UUID
    category_id: Optional[UUID] = None
    description: Optional[str] = None
    amount: DecimalAmount
    date: date
    datetime: Optional[datetime] = None
    pending: bool

    model_config = ConfigDict(from_attributes=True)


class TransactionListResponse(BaseModel):
    items: List[TransactionRead]
    total: int
    limit: int
    offset: int


# --- Budget Schemas ---

class BudgetCreate(BaseModel):
    budget_month: date
    planned_amount: DecimalAmount
    category_id: UUID


class BudgetUpdate(BaseModel):
    planned_amount: Optional[DecimalAmount] = None
    budget_month: Optional[date] = None


class BudgetRead(BaseModel):
    budget_id: UUID
    budget_month: date
    planned_amount: DecimalAmount
    category_id: UUID

    model_config = ConfigDict(from_attributes=True)


# --- Summary Schemas ---

class BudgetCategorySummary(BaseModel):
    category_id: UUID
    name: str
    type: str  # income, expense, transfer
    planned: DecimalAmount
    actual: DecimalAmount
    remaining: DecimalAmount
    is_over_budget: bool

class BudgetGroupSummary(BaseModel):
    group_id: UUID
    name: str
    categories: List[BudgetCategorySummary]
    total_planned: DecimalAmount
    total_actual: DecimalAmount
    total_remaining: DecimalAmount

class BudgetSummaryResponse(BaseModel):
    month: str
    groups: List[BudgetGroupSummary]
    total_income_planned: DecimalAmount
    total_income_actual: DecimalAmount
    total_expense_planned: DecimalAmount
    total_expense_actual: DecimalAmount
    to_be_assigned: DecimalAmount

class DashboardGroupStat(BaseModel):
    group_id: UUID
    name: str
    planned: DecimalAmount
    actual: DecimalAmount

class DashboardAccountSummary(BaseModel):
    account_id: UUID
    name: str
    type: str
    subtype: Optional[str] = None

    current_balance: DecimalAmount
    available_balance: Optional[DecimalAmount] = None
    currency: str = "USD"
    balance_last_updated: Optional[datetime] = None

    is_active: bool = True

class DashboardSummaryResponse(BaseModel):
    month: str
    income_planned: DecimalAmount
    income_actual: DecimalAmount
    expense_planned: DecimalAmount
    expense_actual: DecimalAmount
    total_balance: DecimalAmount
    to_be_assigned: DecimalAmount
    groups: List[DashboardGroupStat]
    accounts: List[DashboardAccountSummary]
    recent_transactions: List[TransactionRead]

class AccountCreate(BaseModel):
    name: str
    type: str
    subtype: Optional[str] = None
    current_balance: DecimalAmount = Decimal("0.00")
    currency: str = "USD"
    is_active: bool = True


class AccountRead(BaseModel):
    """
    API contract uses account_id, but DB model uses Account.id.
    We map Account.id -> account_id here.
    """
    model_config = ConfigDict(from_attributes=True)

    account_id: UUID = Field(validation_alias="id")

    plaid_account_id: Optional[str] = None
    item_id: Optional[UUID] = None

    name: str
    mask: Optional[str] = None
    type: str
    subtype: Optional[str] = None

    current_balance: Decimal
    available_balance: Optional[Decimal] = None
    currency: str = "USD"
    balance_last_updated: Optional[datetime] = None

    is_active: bool = True
    status: str = "connected"


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


# --- Plaid & Account Schemas ---

class PlaidItemRead(BaseModel):
    id: UUID
    plaid_item_id: str

    model_config = ConfigDict(from_attributes=True)


class PlaidLinkTokenResponse(BaseModel):
    link_token: str


class PlaidPublicTokenRequest(BaseModel):
    public_token: str


class PlaidSyncRequest(BaseModel):
    plaid_item_id: str
