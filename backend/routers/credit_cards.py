from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from .. import schemas
from ..access import transaction_access
from ..database import get_db
from ..managers import (
    credit_card_summary_manager,
    transfer_reconciliation_manager,
)

router = APIRouter(prefix="/credit-cards", tags=["Credit Cards"])


@router.get("/summary", response_model=schemas.CreditCardSummaryResponse)
def get_credit_card_summary(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    """
    Returns spending summary per credit card account for the given month.
    balance_owed = starting_balance + net of ALL transactions on the account (all time).
    """
    try:
        budget_month = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    result = credit_card_summary_manager.get_credit_card_summary(db, budget_month)

    cards = [
        schemas.CreditCardAccountSummary(
            account_id=card.account_id,
            account_name=card.account_name,
            starting_balance=card.state.starting_balance,
            balance_owed=card.state.balance_owed,
            charges_this_month=card.state.charges_this_month,
            payments_this_month=card.state.payments_this_month,
            transactions=[
                schemas.CreditCardTransactionRead(
                    transaction_id=t.transaction_id,
                    description=t.description,
                    amount=t.amount,
                    date=t.date,
                    is_transfer=t.is_transfer,
                    category_id=t.category_id,
                )
                for t in card.transactions
            ],
        )
        for card in result.cards
    ]

    return schemas.CreditCardSummaryResponse(month=month, cards=cards)



@router.get("/transfer-candidates", response_model=List[schemas.TransferCandidate])
def get_transfer_candidates(
    db: Session = Depends(get_db),
):
    """
    Finds likely transfer pairs across any account types: a negative transaction
    (inflow) on one account matched to a same-amount positive transaction (outflow)
    on a different account within 2 days, where neither is already marked as a transfer.

    Covers: credit card payments, checking→savings moves, and any other inter-account transfer.
    """
    candidates = transfer_reconciliation_manager.get_transfer_candidates(db)

    return [
        schemas.TransferCandidate(
            inflow_side=schemas.CreditCardTransactionRead(
                transaction_id=c.inflow_side.transaction_id,
                description=c.inflow_side.description,
                amount=c.inflow_side.amount,
                date=c.inflow_side.date,
                is_transfer=c.inflow_side.is_transfer,
                category_id=c.inflow_side.category_id,
            ),
            inflow_account_name=c.inflow_account_name,
            outflow_side=schemas.TransactionRead(
                transaction_id=c.outflow_side.transaction_id,
                plaid_transaction_id=c.outflow_side.plaid_transaction_id,
                account_id=c.outflow_side.account_id,
                category_id=c.outflow_side.category_id,
                description=c.outflow_side.description,
                amount=c.outflow_side.amount,
                date=c.outflow_side.date,
                datetime=c.outflow_side.datetime,
                pending=c.outflow_side.pending,
                is_transfer=c.outflow_side.is_transfer,
                account=schemas.AccountRead(
                    id=c.outflow_side.account.id,
                    plaid_account_id=c.outflow_side.account.plaid_account_id,
                    item_id=c.outflow_side.account.item_id,
                    name=c.outflow_side.account.name,
                    mask=c.outflow_side.account.mask,
                    type=c.outflow_side.account.type,
                    subtype=c.outflow_side.account.subtype,
                    current_balance=c.outflow_side.account.current_balance,
                    available_balance=c.outflow_side.account.available_balance,
                    starting_balance=c.outflow_side.account.starting_balance,
                    currency=c.outflow_side.account.currency,
                    balance_last_updated=c.outflow_side.account.balance_last_updated,
                    is_active=c.outflow_side.account.is_active,
                ) if c.outflow_side.account else None,
            ),
            outflow_account_name=c.outflow_account_name,
        )
        for c in candidates
    ]


@router.post("/mark-transfers", status_code=204)
def mark_transfers(
    payload: schemas.MarkTransfersRequest,
    db: Session = Depends(get_db),
):
    """
    Marks a list of transactions as transfers (is_transfer = True).
    """
    transaction_access.mark_transactions_as_transfers(db, payload.transaction_ids)

