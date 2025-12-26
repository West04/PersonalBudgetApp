from uuid import UUID
from pydantic import BaseModel, ConfigDict, condecimal
from datetime import date, datetime
from typing import Optional, List, Literal

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


# --- Plaid & Account Schemas ---

class PlaidItemRead(BaseModel):
    id: UUID
    plaid_item_id: str

    model_config = ConfigDict(from_attributes=True)


class AccountRead(BaseModel):
    id: UUID
    plaid_account_id: str
    item_id: UUID
    name: str
    mask: Optional[str] = None
    type: str
    subtype: str

    model_config = ConfigDict(from_attributes=True)


class PlaidPublicTokenRequest(BaseModel):
    public_token: str


class PlaidLinkTokenResponse(BaseModel):
    link_token: str


# --- Transaction Schemas ---

class TransactionCreate(BaseModel):
    plaid_transaction_id: str
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
    plaid_transaction_id: str
    account_id: UUID
    category_id: Optional[UUID] = None
    description: Optional[str] = None
    amount: DecimalAmount
    date: date
    datetime: Optional[datetime] = None
    pending: bool

    model_config = ConfigDict(from_attributes=True)


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

class DashboardGroupStat(BaseModel):
    group_id: UUID
    name: str
    planned: DecimalAmount
    actual: DecimalAmount

class DashboardAccountSummary(BaseModel):
    account_id: UUID
    name: str
    type: str
    subtype: str
    balance: DecimalAmount

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
