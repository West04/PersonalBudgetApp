"""
Manager for the Credit Card Summary workflow.

Coordinates:
1. Determination of the budget period [start_date, end_date) using shared domain dates helper.
2. Retrieval of active credit accounts via Account ResourceAccess.
3. For each active credit account:
   - Retrieval of all historical transactions via Transaction ResourceAccess.
   - Mapping persistence records to pure CreditCardTransaction domain models.
   - Invocation of the authoritative pure Credit Card Engine (calculate_credit_card_state).
   - Selection of current-month transactions for display in [start_date, end_date).
   - Mapping display transactions into immutable application values.
4. Assembling and returning composite CreditCardSummaryResult.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from ..access.account_access import get_active_credit_accounts
from ..access.transaction_access import get_transactions_for_account
from ..domain.credit_cards import (
    CreditCardState,
    CreditCardTransaction,
    calculate_credit_card_state,
)
from ..domain.dates import determine_effective_cutoff, determine_month_range



@dataclass(frozen=True)
class CreditCardMonthlyTransactionItem:
    transaction_id: UUID
    description: str
    amount: Decimal
    date: date
    is_transfer: bool
    category_id: Optional[UUID] = None


@dataclass(frozen=True)
class CreditCardAccountSummaryItem:
    account_id: UUID
    account_name: str
    state: CreditCardState
    transactions: Sequence[CreditCardMonthlyTransactionItem]


@dataclass(frozen=True)
class CreditCardSummaryResult:
    cards: Sequence[CreditCardAccountSummaryItem]


def get_credit_card_summary(
    db: Session,
    budget_month: date,
    as_of_date: Optional[date] = None,
) -> CreditCardSummaryResult:
    """
    Coordinates the credit card summary workflow:
    1. Determines period dates using shared determine_month_range.
    2. Determines point-in-time cutoff using determine_effective_cutoff.
    3. Retrieves active credit accounts ordered by name ascending.
    4. For each card:
       - Retrieves all historical transactions ordered by date descending.
       - Maps to pure domain CreditCardTransaction.
       - Computes financial state via calculate_credit_card_state with cutoff_exclusive.
       - Filters monthly transactions in [start_date, end_date) preserving date descending order.
       - Maps monthly transactions to immutable application items.
    5. Returns CreditCardSummaryResult.
    """
    start_date, end_date = determine_month_range(budget_month)
    effective_today = as_of_date if as_of_date is not None else date.today()
    cutoff_exclusive = determine_effective_cutoff(end_date, effective_today)

    credit_accounts = get_active_credit_accounts(db)

    cards: list[CreditCardAccountSummaryItem] = []

    for account in credit_accounts:
        account_txns = get_transactions_for_account(db, account.id)

        domain_txns = [
            CreditCardTransaction(
                amount=t.amount,
                date=t.date,
                is_transfer=t.is_transfer,
            )
            for t in account_txns
        ]

        state = calculate_credit_card_state(
            starting_balance=account.starting_balance,
            transactions=domain_txns,
            period_start=start_date,
            period_end=end_date,
            cutoff_exclusive=cutoff_exclusive,
        )

        monthly_items = [
            CreditCardMonthlyTransactionItem(
                transaction_id=t.transaction_id,
                description=t.description,
                amount=t.amount,
                date=t.date,
                is_transfer=t.is_transfer,
                category_id=t.category_id,
            )
            for t in account_txns
            if start_date <= t.date < end_date
        ]

        cards.append(
            CreditCardAccountSummaryItem(
                account_id=account.id,
                account_name=account.name,
                state=state,
                transactions=monthly_items,
            )
        )

    return CreditCardSummaryResult(cards=cards)
