"""
Pure domain functions and structures for transfer reconciliation and matching.

Rules & Invariants:
1. Transfers consist of opposing transactions: one negative (inflow) and one positive (outflow).
2. Amounts must match in absolute value (|inflow.amount| == |outflow.amount|).
3. The transactions must belong to different accounts (outflow.account_id != inflow.account_id).
4. Date proximity: absolute difference between dates must be <= 2 days (0, 1, or 2 days).
5. Transactions already marked as transfers (is_transfer == True) are ineligible.
6. Each inflow transaction matches at most one outflow; matched outflows cannot be reused.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

ZERO = Decimal("0.00")
MAX_TRANSFER_DAYS_DIFFERENCE = 2


@dataclass(frozen=True)
class ReconciliationTransaction:
    transaction_id: UUID
    account_id: UUID
    amount: Decimal
    date: date
    is_transfer: bool = False


@dataclass(frozen=True)
class MatchedTransferCandidate:
    inflow: ReconciliationTransaction
    outflow: ReconciliationTransaction


def detect_transfer_candidates(
    inflows: Sequence[ReconciliationTransaction],
    outflows: Sequence[ReconciliationTransaction],
) -> list[MatchedTransferCandidate]:
    """
    Finds likely transfer pairs across different accounts:
    a negative transaction (inflow) matched to a same-magnitude positive transaction (outflow)
    on a different account within 2 days (MAX_TRANSFER_DAYS_DIFFERENCE),
    where neither transaction is already marked as a transfer.
    """
    inflow_list = [t for t in inflows if not t.is_transfer and t.amount < ZERO]
    outflow_list = [t for t in outflows if not t.is_transfer and t.amount > ZERO]

    # Index outflows by absolute amount for lookup
    outflow_by_amount: dict[Decimal, list[ReconciliationTransaction]] = {}
    for t in outflow_list:
        key = abs(Decimal(str(t.amount)))
        outflow_by_amount.setdefault(key, []).append(t)

    candidates: list[MatchedTransferCandidate] = []
    seen_outflow_ids: set[UUID] = set()

    for inflow_txn in inflow_list:
        match_amount = abs(Decimal(str(inflow_txn.amount)))
        possible_outflows = outflow_by_amount.get(match_amount, [])

        for outflow_txn in possible_outflows:
            # Must belong to a different account
            if outflow_txn.account_id == inflow_txn.account_id:
                continue

            # Must not have been matched to a prior inflow
            if outflow_txn.transaction_id in seen_outflow_ids:
                continue

            # Date proximity check
            date_diff = abs((outflow_txn.date - inflow_txn.date).days)
            if date_diff <= MAX_TRANSFER_DAYS_DIFFERENCE:
                seen_outflow_ids.add(outflow_txn.transaction_id)
                candidates.append(
                    MatchedTransferCandidate(
                        inflow=inflow_txn,
                        outflow=outflow_txn,
                    )
                )
                break  # Exactly one match per inflow transaction

    return candidates
