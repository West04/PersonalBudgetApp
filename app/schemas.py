from uuid import UUID
from pydantic import BaseModel, ConfigDict, condecimal
from datetime import date, datetime
from typing import Union

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


class TransactionCreate(BaseModel):
    description: str
    amount: DecimalAmount
    category_id: UUID
    transaction_date: datetime

class TransactionUpdate(BaseModel):
    description: Union[str, None] = None
    amount: Union[DecimalAmount, None] = None
    category_id: Union[UUID, None] = None
    transaction_date: Union[datetime, None] = None


class TransactionRead(BaseModel):
    transaction_id: UUID
    description: str
    amount: DecimalAmount
    category_id: UUID
    transaction_date: datetime

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


