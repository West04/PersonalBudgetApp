from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from .. import models, schemas
from ..database import get_db
from ..domain.credit_cards import (
    CreditCardTransaction,
    calculate_credit_card_state,
)
from ..domain.reconciliation import (
    ReconciliationTransaction,
    detect_transfer_candidates,
)

router = APIRouter(prefix="/credit-cards", tags=["Credit Cards"])


def get_month_range(month_str: str) -> tuple[date, date]:
    try:
        start_date = datetime.strptime(month_str, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
    if start_date.month == 12:
        end_date = date(start_date.year + 1, 1, 1)
    else:
        end_date = date(start_date.year, start_date.month + 1, 1)
    return start_date, end_date


@router.get("/summary", response_model=schemas.CreditCardSummaryResponse)
def get_credit_card_summary(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    """
    Returns spending summary per credit card account for the given month.
    balance_owed = starting_balance + net of ALL transactions on the account (all time).
    """
    start_date, end_date = get_month_range(month)

    credit_accounts = (
        db.query(models.Account)
        .filter(models.Account.type == "credit", models.Account.is_active == True)
        .order_by(models.Account.name)
        .all()
    )

    cards: List[schemas.CreditCardAccountSummary] = []

    for account in credit_accounts:
        account_txns = (
            db.query(models.Transaction)
            .filter(models.Transaction.account_id == account.id)
            .order_by(models.Transaction.date.desc())
            .all()
        )

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
        )

        monthly_txns = [
            t for t in account_txns
            if start_date <= t.date < end_date
        ]

        cards.append(
            schemas.CreditCardAccountSummary(
                account_id=account.id,
                account_name=account.name,
                starting_balance=state.starting_balance,
                balance_owed=state.balance_owed,
                charges_this_month=state.charges_this_month,
                payments_this_month=state.payments_this_month,
                transactions=[
                    schemas.CreditCardTransactionRead(
                        transaction_id=t.transaction_id,
                        description=t.description,
                        amount=t.amount,
                        date=t.date,
                        is_transfer=t.is_transfer,
                        category_id=t.category_id,
                    )
                    for t in monthly_txns
                ],
            )
        )

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
