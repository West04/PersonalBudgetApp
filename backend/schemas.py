from uuid import UUID
from pydantic import BaseModel, ConfigDict, condecimal, Field, field_validator, model_validator
from datetime import date, date as DateType, datetime, datetime as DateTime
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


# --- Account Schemas ---

AccountType = Literal["depository", "credit", "investment", "loan", "other"]

ACCOUNT_SUBTYPES: dict[str, list[str]] = {
    "depository": ["checking", "savings"],
    "credit":     ["credit card"],
    "investment": ["brokerage", "ira", "401k", "other"],
    "loan":       ["mortgage", "auto", "student", "personal", "other"],
    "other":      ["other"],
}


class AccountCreate(BaseModel):
    name: str
    type: AccountType
    subtype: Optional[str] = None
    current_balance: DecimalAmount = Decimal("0.00")
    starting_balance: DecimalAmount = Decimal("0.00")
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
    starting_balance: Decimal = Decimal("0.00")
    currency: str = "USD"
    balance_last_updated: Optional[datetime] = None
    last_reconciled_date: Optional[date] = None
    last_reconciled_balance: Optional[Decimal] = None

    is_active: bool = True
    status: str = "connected"


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[AccountType] = None
    subtype: Optional[str] = None
    is_active: Optional[bool] = None
    starting_balance: Optional[Decimal] = None
    current_balance: Optional[Decimal] = None


# --- Transaction Schemas ---

class TransactionCreate(BaseModel):
    account_id: UUID
    category_id: Optional[UUID] = None
    description: str
    merchant: Optional[str] = None
    amount: DecimalAmount
    date: date
    datetime: Optional[DateTime] = None
    pending: bool = False
    is_reviewed: bool = False
    is_cleared: bool = False
    is_reconciled: bool = False
    plaid_transaction_id: Optional[str] = None
    category_source: Optional[str] = None


class TransactionUpdate(BaseModel):
    account_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[DecimalAmount] = None
    date: Optional[DateType] = None
    is_transfer: Optional[bool] = None
    is_reviewed: Optional[bool] = None


class TransactionClearedUpdate(BaseModel):
    is_cleared: bool


class TransactionRead(BaseModel):
    transaction_id: UUID
    plaid_transaction_id: Optional[str] = None
    account_id: UUID
    category_id: Optional[UUID] = None
    category_source: Optional[str] = None
    description: str
    merchant: Optional[str] = None
    is_merchant_overridden: bool = False
    amount: DecimalAmount
    date: date
    datetime: Optional[DateTime] = None
    pending: bool
    is_transfer: bool = False
    is_reviewed: bool = False
    is_cleared: bool = False
    is_reconciled: bool = False
    account: Optional[AccountRead] = None

    model_config = ConfigDict(from_attributes=True)


class ReconciliationTransactionRead(BaseModel):
    transaction_id: UUID
    account_id: UUID
    date: date
    description: str
    merchant: Optional[str] = None
    amount: DecimalAmount
    pending: bool = False
    is_transfer: bool = False
    is_reviewed: bool = False
    is_cleared: bool = False
    is_reconciled: bool = False

    model_config = ConfigDict(from_attributes=True)


class AccountReconciliationSummary(BaseModel):
    account_id: UUID
    account_name: str
    account_type: str
    starting_balance: DecimalAmount
    last_reconciled_date: Optional[date] = None
    last_reconciled_balance: Optional[DecimalAmount] = None
    prior_reconciled_balance: DecimalAmount
    statement_ending_date: date
    statement_ending_balance: DecimalAmount
    cleared_balance: DecimalAmount
    difference: DecimalAmount
    cleared_count: int
    uncleared_count: int
    is_balanced: bool
    transactions: List[ReconciliationTransactionRead]


class CompleteReconciliationRequest(BaseModel):
    statement_ending_date: date
    statement_ending_balance: DecimalAmount


class TransactionDetailRead(TransactionRead):
    pass


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
    budget_id: Optional[UUID] = None
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
    recent_transactions: List[TransactionDetailRead]

# --- Credit Card Schemas ---

class CreditCardTransactionRead(BaseModel):
    transaction_id: UUID
    description: str
    amount: DecimalAmount
    date: date
    is_transfer: bool
    category_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class CreditCardAccountSummary(BaseModel):
    account_id: UUID
    account_name: str
    starting_balance: Decimal
    balance_owed: Decimal           # starting_balance + net of all transactions all-time
    charges_this_month: Decimal     # sum of positive non-transfer transactions this month
    payments_this_month: Decimal    # sum of payments received this month (negative txns)
    transactions: List[CreditCardTransactionRead]


class CreditCardSummaryResponse(BaseModel):
    month: str
    cards: List[CreditCardAccountSummary]


class TransferCandidate(BaseModel):
    inflow_side: CreditCardTransactionRead    # negative amount — money arriving at this account
    inflow_account_name: str
    outflow_side: TransactionRead             # positive amount — money leaving this account
    outflow_account_name: str


class MarkTransfersRequest(BaseModel):
    transaction_ids: List[UUID]


class PlaidItemRead(BaseModel):
    id: UUID
    plaid_item_id: str

    model_config = ConfigDict(from_attributes=True)


class PlaidLinkTokenResponse(BaseModel):
    link_token: str


class PlaidPublicTokenRequest(BaseModel):
    public_token: str


class PlaidSyncRequest(BaseModel):
    plaid_item_id: Optional[str] = None
    item_id: Optional[UUID] = None


# --- Reorder Schemas ---

class ReorderRequest(BaseModel):
    """Request to reorder category groups by providing ordered list of IDs"""
    order: List[UUID]


class CategoryReorderRequest(BaseModel):
    """Request to reorder categories within a group"""
    group_id: UUID
    order: List[UUID]


# --- CSV Upload Schemas ---

class CSVTransactionRow(BaseModel):
    """A single parsed row from a CSV upload, with optional parse error."""
    row_number: int
    # Use str for date to avoid Pydantic v2 name-collision with the imported `date` type
    transaction_date: Optional[str] = None  # ISO format YYYY-MM-DD
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    pending: Optional[bool] = None
    parse_error: Optional[str] = None  # set if this row could not be parsed


class CSVPreviewResponse(BaseModel):
    """Response from the CSV preview endpoint."""
    rows: List[CSVTransactionRow]
    total_rows: int
    valid_rows: int
    error_rows: int


class CSVImportResult(BaseModel):
    """Result from the CSV confirm/import endpoint."""
    imported: int
    skipped: int        # duplicates that were silently skipped
    errors: List[str]   # non-fatal row errors logged during import


# --- CSV Format Schemas ---

AmountSignConvention = Literal["positive_is_outflow", "positive_is_inflow"]


class CSVFormatCreate(BaseModel):
    name: str
    date_column: str
    description_column: str
    amount_column: str
    status_column: Optional[str] = None
    date_format: str
    amount_sign_convention: AmountSignConvention
    status_posted_value: Optional[str] = "posted"

    @field_validator("name", "date_column", "description_column", "amount_column", "date_format")
    @classmethod
    def check_non_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Field cannot be empty or whitespace")
        return s

    @field_validator("status_column", mode="before")
    @classmethod
    def clean_status_column(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("status_posted_value", mode="before")
    @classmethod
    def clean_status_posted_value(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @model_validator(mode="after")
    def validate_and_normalize(self):
        col_list = [self.date_column, self.description_column, self.amount_column]
        if len(col_list) != len(set(col_list)):
            raise ValueError("date_column, description_column, and amount_column must be distinct source columns")
        if self.status_column and self.status_column in col_list:
            raise ValueError("status_column must be distinct from date, description, and amount columns")

        # Canonicalize status configuration:
        # If status_column is absent, status_posted_value is irrelevant -> canonicalize to None.
        # If status_column is present, normalize status_posted_value to trimmed lowercase (default "posted").
        if self.status_column is None:
            self.status_posted_value = None
        else:
            val = (str(self.status_posted_value) if self.status_posted_value is not None else "").strip().lower()
            self.status_posted_value = val if val else "posted"

        return self


class CSVFormatRead(BaseModel):
    id: UUID
    name: str
    date_column: str
    description_column: str
    amount_column: str
    status_column: Optional[str] = None
    date_format: str
    amount_sign_convention: AmountSignConvention
    status_posted_value: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- CSV Inspection Schemas ---

class CSVFormatMatchRead(BaseModel):
    identifier: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class CSVInspectResponse(BaseModel):
    headers: list[str]
    sample_rows: list[list[str]]
    status: Literal["unknown", "detected", "ambiguous"]
    detected_format: Optional[CSVFormatMatchRead] = None
    matches: list[CSVFormatMatchRead]


# --- Categorization Rule Schemas ---

class CategorizationRuleCreate(BaseModel):
    merchant: str = Field(min_length=1)
    category_id: UUID

    @field_validator("merchant")
    @classmethod
    def validate_merchant(cls, v: str) -> str:
        s = " ".join(v.split()).strip()
        if not s:
            raise ValueError("Merchant cannot be blank")
        return s


class CategorizationRuleUpdate(BaseModel):
    merchant: Optional[str] = None
    category_id: Optional[UUID] = None

    @field_validator("merchant")
    @classmethod
    def validate_merchant(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        s = " ".join(v.split()).strip()
        if not s:
            raise ValueError("Merchant cannot be blank")
        return s


class CategorizationRuleRead(BaseModel):
    id: UUID
    merchant: str
    category_id: UUID
    created_at: datetime
    updated_at: datetime
    category: Optional[CategoryRead] = None

    model_config = ConfigDict(from_attributes=True)


class CategorizationRulePreviewResponse(BaseModel):
    rule_id: UUID
    merchant: str
    category_id: UUID
    matching_count: int


class CategorizationRuleBatchApplyResponse(BaseModel):
    rule_id: UUID
    applied_count: int


# --- ML Categorization Schemas ---

class MLModelStatusRead(BaseModel):
    model_available: bool
    status: str  # Ready | Needs more data | Stale
    trained_at: Optional[datetime] = None
    trained_revision: int
    current_training_revision: int
    new_labels_since_training: int
    training_example_count: int
    retrain_threshold: int
    accuracy: Optional[float] = None
    macro_f1: Optional[float] = None
    top2_accuracy: Optional[float] = None
    coverage: Optional[float] = None
    status_message: Optional[str] = None


class MLRetrainResponse(BaseModel):
    success: bool
    message: str
    model_activated: bool
    status: MLModelStatusRead


class TransactionCategorySuggestionRead(BaseModel):
    transaction_id: UUID
    suggested_category_id: Optional[UUID] = None
    suggested_category_name: Optional[str] = None
    confidence: Optional[float] = None
    score_label: Optional[str] = None
    reason: Optional[str] = None


class BatchCategorySuggestionsRequest(BaseModel):
    transaction_ids: List[UUID]


class BatchCategorySuggestionsResponse(BaseModel):
    suggestions: dict[UUID, TransactionCategorySuggestionRead]


class AcceptSuggestionRequest(BaseModel):
    category_id: UUID


# --- Recurring Transaction Schemas ---

RecurringCadence = Literal["weekly", "biweekly", "monthly", "annual"]
RecurringStatus = Literal["detected", "confirmed", "dismissed"]
RecurringAmountType = Literal["fixed", "variable"]
RecurringDirection = Literal["outflow", "inflow"]


class RecurringItemRead(BaseModel):
    id: UUID
    account_id: UUID
    account_name: Optional[str] = None
    merchant: str
    direction: RecurringDirection
    cadence: RecurringCadence
    amount_type: RecurringAmountType
    expected_amount: DecimalAmount
    status: RecurringStatus
    last_date: date
    next_expected_date: Optional[date] = None
    occurrence_count: int = 0
    explanation: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    transaction_ids: List[UUID] = []

    model_config = ConfigDict(from_attributes=True)


class RecurringItemDetailRead(RecurringItemRead):
    transactions: List[TransactionRead] = []



