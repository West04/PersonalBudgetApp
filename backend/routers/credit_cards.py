from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from .. import models, schemas
from ..database import get_db
from ..managers import credit_card_summary_manager
from ..domain.reconciliation import (
    ReconciliationTransaction,
    detect_transfer_candidates,
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
    # All unmatched inflows (negative amounts) on any account
    inflow_txns = (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Transaction.amount < 0,
            models.Transaction.is_transfer == False,
        )
        .all()
    )

    # All unmatched outflows (positive amounts) on any account
    outflow_txns = (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Transaction.amount > 0,
            models.Transaction.is_transfer == False,
        )
        .all()
    )

    inflow_by_id = {t.transaction_id: t for t in inflow_txns}
    outflow_by_id = {t.transaction_id: t for t in outflow_txns}

    domain_inflows = [
        ReconciliationTransaction(
            transaction_id=t.transaction_id,
            account_id=t.account_id,
            amount=t.amount,
            date=t.date,
            is_transfer=t.is_transfer,
        )
        for t in inflow_txns
    ]

    domain_outflows = [
        ReconciliationTransaction(
            transaction_id=t.transaction_id,
            account_id=t.account_id,
            amount=t.amount,
            date=t.date,
            is_transfer=t.is_transfer,
        )
        for t in outflow_txns
    ]

    matches = detect_transfer_candidates(inflows=domain_inflows, outflows=domain_outflows)

    candidates: list[schemas.TransferCandidate] = []
    for c in matches:
        inflow_txn = inflow_by_id[c.inflow.transaction_id]
        outflow_txn = outflow_by_id[c.outflow.transaction_id]
        candidates.append(
            schemas.TransferCandidate(
                inflow_side=schemas.CreditCardTransactionRead(
                    transaction_id=inflow_txn.transaction_id,
                    description=inflow_txn.description,
                    amount=inflow_txn.amount,
                    date=inflow_txn.date,
                    is_transfer=inflow_txn.is_transfer,
                    category_id=inflow_txn.category_id,
                ),
                inflow_account_name=inflow_txn.account.name,
                outflow_side=schemas.TransactionRead.model_validate(outflow_txn),
                outflow_account_name=outflow_txn.account.name,
            )
        )

    return candidates


@router.post("/mark-transfers", status_code=204)
def mark_transfers(
    payload: schemas.MarkTransfersRequest,
    db: Session = Depends(get_db),
):
    """
    Marks a list of transactions as transfers (is_transfer = True).
    """
    db.query(models.Transaction).filter(
        models.Transaction.transaction_id.in_(payload.transaction_ids)
    ).update({models.Transaction.is_transfer: True}, synchronize_session=False)
    db.commit()
