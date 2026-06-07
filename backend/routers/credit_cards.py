from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import UUID

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/credit-cards", tags=["Credit Cards"])

ZERO = Decimal("0.00")


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
        # All-time net to calculate running balance owed
        all_time_net = (
            db.query(func.coalesce(func.sum(models.Transaction.amount), ZERO))
            .filter(models.Transaction.account_id == account.id)
            .scalar()
        ) or ZERO

        balance_owed = Decimal(str(account.starting_balance)) + Decimal(str(all_time_net))

        # This month: charges (positive, non-transfer)
        charges_this_month = (
            db.query(func.coalesce(func.sum(models.Transaction.amount), ZERO))
            .filter(
                models.Transaction.account_id == account.id,
                models.Transaction.amount > 0,
                models.Transaction.is_transfer == False,
                models.Transaction.date >= start_date,
                models.Transaction.date < end_date,
            )
            .scalar()
        ) or ZERO

        # This month: payments received (negative amounts = money coming into the card)
        payments_raw = (
            db.query(func.coalesce(func.sum(models.Transaction.amount), ZERO))
            .filter(
                models.Transaction.account_id == account.id,
                models.Transaction.amount < 0,
                models.Transaction.date >= start_date,
                models.Transaction.date < end_date,
            )
            .scalar()
        ) or ZERO
        payments_this_month = abs(Decimal(str(payments_raw)))

        # Transactions this month for detail view
        txns = (
            db.query(models.Transaction)
            .filter(
                models.Transaction.account_id == account.id,
                models.Transaction.date >= start_date,
                models.Transaction.date < end_date,
            )
            .order_by(models.Transaction.date.desc())
            .all()
        )

        cards.append(
            schemas.CreditCardAccountSummary(
                account_id=account.id,
                account_name=account.name,
                starting_balance=Decimal(str(account.starting_balance)),
                balance_owed=balance_owed,
                charges_this_month=Decimal(str(charges_this_month)),
                payments_this_month=payments_this_month,
                transactions=[
                    schemas.CreditCardTransactionRead(
                        transaction_id=t.transaction_id,
                        description=t.description,
                        amount=t.amount,
                        date=t.date,
                        is_transfer=t.is_transfer,
                        category_id=t.category_id,
                    )
                    for t in txns
                ],
            )
        )

    return schemas.CreditCardSummaryResponse(month=month, cards=cards)


@router.get("/transfer-candidates", response_model=List[schemas.TransferCandidate])
def get_transfer_candidates(
    db: Session = Depends(get_db),
):
    """
    Finds likely payment pairs: a negative transaction on a credit account
    matched to a same-amount positive transaction on a non-credit account
    within 2 days, where neither has been marked as a transfer yet.
    """
    # All unmatched payments received on credit cards (negative amounts)
    credit_payments = (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Account.type == "credit",
            models.Transaction.amount < 0,
            models.Transaction.is_transfer == False,
        )
        .all()
    )

    # All unmatched outflows from non-credit accounts (positive amounts)
    debit_outflows = (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Account.type != "credit",
            models.Transaction.amount > 0,
            models.Transaction.is_transfer == False,
        )
        .all()
    )

    # Index debit outflows by amount for fast lookup
    debit_by_amount: dict[Decimal, list[models.Transaction]] = {}
    for t in debit_outflows:
        key = abs(Decimal(str(t.amount)))
        debit_by_amount.setdefault(key, []).append(t)

    candidates: List[schemas.TransferCandidate] = []
    seen_debit_ids: set[UUID] = set()

    for credit_txn in credit_payments:
        match_amount = abs(Decimal(str(credit_txn.amount)))
        possible_debits = debit_by_amount.get(match_amount, [])

        for debit_txn in possible_debits:
            if debit_txn.transaction_id in seen_debit_ids:
                continue
            date_diff = abs((debit_txn.date - credit_txn.date).days)
            if date_diff <= 2:
                seen_debit_ids.add(debit_txn.transaction_id)
                candidates.append(
                    schemas.TransferCandidate(
                        credit_side=schemas.CreditCardTransactionRead(
                            transaction_id=credit_txn.transaction_id,
                            description=credit_txn.description,
                            amount=credit_txn.amount,
                            date=credit_txn.date,
                            is_transfer=credit_txn.is_transfer,
                            category_id=credit_txn.category_id,
                        ),
                        credit_account_name=credit_txn.account.name,
                        debit_side=schemas.TransactionRead.model_validate(debit_txn),
                        debit_account_name=debit_txn.account.name,
                    )
                )
                break  # one match per credit payment

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
