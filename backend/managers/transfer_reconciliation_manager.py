"""
Manager for the Transfer Candidate Search workflow.

Coordinates:
1. Retrieval of unmatched candidate inflows and outflows via Transaction ResourceAccess.
2. Mapping candidate persistence records to pure ReconciliationTransaction domain models.
3. Invocation of the pure Reconciliation Engine (detect_transfer_candidates).
4. Correlating matched candidate IDs back to original persistence records.
5. Resolving Account metadata for matched transactions via Transaction ResourceAccess.
6. Mapping persistence records into immutable application dataclasses.
7. Returning Sequence[TransferCandidateItem].
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from ..access.transaction_access import (
    get_account_for_transaction,
    get_unmatched_inflow_transactions,
    get_unmatched_outflow_transactions,
)
from ..domain.reconciliation import (
    ReconciliationTransaction,
    detect_transfer_candidates,
)


@dataclass(frozen=True)
class TransferInflowSideItem:
    transaction_id: UUID
    description: str
    amount: Decimal
    date: date
    is_transfer: bool
    category_id: Optional[UUID] = None


@dataclass(frozen=True)
class TransferOutflowAccountItem:
    id: UUID
    name: str
    type: str
    subtype: Optional[str]
    current_balance: Decimal
    available_balance: Optional[Decimal]
    starting_balance: Decimal
    currency: str
    balance_last_updated: Optional[datetime]
    is_active: bool
    mask: Optional[str] = None
    plaid_account_id: Optional[str] = None
    item_id: Optional[UUID] = None


@dataclass(frozen=True)
class TransferOutflowSideItem:
    transaction_id: UUID
    account_id: UUID
    description: str
    amount: Decimal
    date: date
    is_transfer: bool
    category_id: Optional[UUID] = None
    plaid_transaction_id: Optional[str] = None
    datetime: Optional[datetime] = None
    pending: bool = False
    account: Optional[TransferOutflowAccountItem] = None


@dataclass(frozen=True)
class TransferCandidateItem:
    inflow_side: TransferInflowSideItem
    inflow_account_name: str
    outflow_side: TransferOutflowSideItem
    outflow_account_name: str


def get_transfer_candidates(
    db: Session,
) -> Sequence[TransferCandidateItem]:
    """
    Coordinates the transfer candidate search workflow:
    1. Loads unmatched inflows and outflows via Transaction ResourceAccess.
    2. Builds ID-to-transaction lookup dictionaries for correlation.
    3. Maps records to ReconciliationTransaction domain models, preserving query order.
    4. Invokes the pure Reconciliation Engine (detect_transfer_candidates).
    5. Correlates matched candidate IDs back to persistence records.
    6. For matched transactions only, resolves accounts via Transaction ResourceAccess.
    7. Maps records into immutable application dataclasses.
    8. Returns Sequence[TransferCandidateItem].
    """
    inflow_txns = get_unmatched_inflow_transactions(db)
    outflow_txns = get_unmatched_outflow_transactions(db)

    inflow_by_id = {t.transaction_id: t for t in inflow_txns}
    outflow_by_id = {t.transaction_id: t for t in outflow_txns}

    # Map preserving Accessor iteration sequence directly (no sorting)
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

    candidates: list[TransferCandidateItem] = []
    for c in matches:
        inflow_txn = inflow_by_id[c.inflow.transaction_id]
        outflow_txn = outflow_by_id[c.outflow.transaction_id]

        inflow_account = get_account_for_transaction(inflow_txn)
        outflow_account = get_account_for_transaction(outflow_txn)

        if inflow_account is None:
            raise AttributeError(f"Account relationship missing for inflow transaction {inflow_txn.transaction_id}")
        if outflow_account is None:
            raise AttributeError(f"Account relationship missing for outflow transaction {outflow_txn.transaction_id}")

        outflow_account_item = TransferOutflowAccountItem(
            id=outflow_account.id,
            name=outflow_account.name,
            type=outflow_account.type,
            subtype=outflow_account.subtype,
            current_balance=outflow_account.current_balance,
            available_balance=outflow_account.available_balance,
            starting_balance=outflow_account.starting_balance,
            currency=outflow_account.currency,
            balance_last_updated=outflow_account.balance_last_updated,
            is_active=outflow_account.is_active,
            mask=outflow_account.mask,
            plaid_account_id=outflow_account.plaid_account_id,
            item_id=outflow_account.item_id,
        )

        inflow_side_item = TransferInflowSideItem(
            transaction_id=inflow_txn.transaction_id,
            description=inflow_txn.description,
            amount=inflow_txn.amount,
            date=inflow_txn.date,
            is_transfer=inflow_txn.is_transfer,
            category_id=inflow_txn.category_id,
        )

        outflow_side_item = TransferOutflowSideItem(
            transaction_id=outflow_txn.transaction_id,
            account_id=outflow_txn.account_id,
            description=outflow_txn.description,
            amount=outflow_txn.amount,
            date=outflow_txn.date,
            is_transfer=outflow_txn.is_transfer,
            category_id=outflow_txn.category_id,
            plaid_transaction_id=outflow_txn.plaid_transaction_id,
            datetime=outflow_txn.datetime,
            pending=outflow_txn.pending,
            account=outflow_account_item,
        )

        candidates.append(
            TransferCandidateItem(
                inflow_side=inflow_side_item,
                inflow_account_name=inflow_account.name,
                outflow_side=outflow_side_item,
                outflow_account_name=outflow_account.name,
            )
        )

    return candidates
