from uuid import UUID
from pydantic import BaseModel, ConfigDict, condecimal
from datetime import date, datetime
from typing import Union, Optional, List

DecimalAmount = condecimal(max_digits=10, decimal_places=2)


class CategoryCreate(BaseModel):
    name: str
    parent_id: Union[UUID, None] = None


class CategoryRead(BaseModel):
    category_id: UUID
    name: str
    parent_id: Union[UUID, None] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CategoryUpdate(BaseModel):
    name: Union[str, None] = None
    parent_id: Union[UUID, None] = None


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


class TransactionCreate(BaseModel):
    plaid_transaction_id: str
    account_id: UUID
    category_id: Optional[UUID] = None
    description: str
    amount: DecimalAmount
    date: date
    datetime: Optional[datetime] = None
    pending: bool = False


class TransactionUpdate(BaseModel):
    description: Union[str, None] = None
    category_id: Union[UUID, None] = None


class TransactionRead(BaseModel):
    transaction_id: UUID
    plaid_transaction_id: str
    account_id: UUID
    category_id: Optional[UUID] = None
    description: str
    amount: DecimalAmount
    date: date
    datetime: Optional[datetime] = None
    pending: bool

    model_config = ConfigDict(from_attributes=True)


class BudgetCreate(BaseModel):
    budget_month: date
    planned_amount: DecimalAmount
    category_id: UUID


class BudgetUpdate(BaseModel):
    planned_amount: Union[DecimalAmount, None] = None
    budget_month: Union[date, None] = None


class BudgetRead(BaseModel):
    budget_id: UUID
    budget_month: date
    planned_amount: DecimalAmount
    category_id: UUID

    model_config = ConfigDict(from_attributes=True)