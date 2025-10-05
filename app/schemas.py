from uuid import UUID
from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from typing import Union


class CategoryCreate(BaseModel):
    name: str
    parent_id: Union[UUID, None] = None


class CategoryRead(BaseModel):
    category_id: UUID
    name: str
    parent_id: Union[UUID, None] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionCreate(BaseModel):
    description: str
    amount: float
    category_id: UUID


class TransactionRead(BaseModel):
    transaction_id: UUID
    description: str
    amount: float
    category_id: UUID
    transaction_date: datetime

    model_config = ConfigDict(from_attributes=True)


class BudgetCreate(BaseModel):
    budget_month: date
    planned_amount: float
    category_id: UUID


class BudgetRead(BaseModel):
    budget_id: UUID
    budget_month: date
    planned_amount: float
    category_id: UUID

    model_config = ConfigDict(from_attributes=True)


