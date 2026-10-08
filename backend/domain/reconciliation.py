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
    Finds likely transfer pairs across different accounts using deterministic
    closest-first greedy suggestion matching.

    Eligibility:
    - Inflow is strictly negative (amount < 0) and not marked as transfer.
    - Outflow is strictly positive (amount > 0) and not marked as transfer.
    - Exact absolute amount equality (|inflow.amount| == |outflow.amount|).
    - Different accounts (inflow.account_id != outflow.account_id).
    - Absolute calendar date difference <= MAX_TRANSFER_DAYS_DIFFERENCE (2 days).

    Selection & Ranking:
    Eligible candidate pairs are evaluated and ranked deterministically by:
    1. Absolute date distance ascending (0-day > 1-day > 2-day).
    2. Inflow date ascending.
    3. Outflow date ascending.
    4. Canonical string representation of inflow transaction_id ascending.
    5. Canonical string representation of outflow transaction_id ascending.

    Walks the ranked candidate pairs, greedily selecting pairs where neither
    inflow nor outflow has already been selected (single-use constraint).
    """
    inflow_list = [t for t in inflows if not t.is_transfer and t.amount < ZERO]
    outflow_list = [t for t in outflows if not t.is_transfer and t.amount > ZERO]

    # Index outflows by exact absolute amount
    outflows_by_amount: dict[Decimal, list[ReconciliationTransaction]] = {}
    for t in outflow_list:
        outflows_by_amount.setdefault(abs(Decimal(str(t.amount))), []).append(t)

    # Index inflows by exact absolute amount
    inflows_by_amount: dict[Decimal, list[ReconciliationTransaction]] = {}
    for t in inflow_list:
        inflows_by_amount.setdefault(abs(Decimal(str(t.amount))), []).append(t)

    eligible_pairs: list[
        tuple[int, date, date, str, str, ReconciliationTransaction, ReconciliationTransaction]
    ] = []

    for amount, group_inflows in inflows_by_amount.items():
        group_outflows = outflows_by_amount.get(amount)
        if not group_outflows:
            continue

        for inf in group_inflows:
            for outf in group_outflows:
                # Must belong to a different account
                if inf.account_id == outf.account_id:
                    continue

                date_diff = abs((outf.date - inf.date).days)
                if date_diff <= MAX_TRANSFER_DAYS_DIFFERENCE:
                    eligible_pairs.append((
                        date_diff,
                        inf.date,
                        outf.date,
                        str(inf.transaction_id),
                        str(outf.transaction_id),
                        inf,
                        outf,
                    ))

    # Deterministic ranking tuple:
    # 1. date distance ascending (0-day > 1-day > 2-day)
    # 2. inflow date ascending
    # 3. outflow date ascending
    # 4. inflow transaction_id ascending
    # 5. outflow transaction_id ascending
    eligible_pairs.sort(key=lambda p: (p[0], p[1], p[2], p[3], p[4]))

    candidates: list[MatchedTransferCandidate] = []
    used_inflow_ids: set[UUID] = set()
    used_outflow_ids: set[UUID] = set()

    for _, _, _, _, _, inf, outf in eligible_pairs:
        if inf.transaction_id in used_inflow_ids or outf.transaction_id in used_outflow_ids:
            continue

        used_inflow_ids.add(inf.transaction_id)
        used_outflow_ids.add(outf.transaction_id)
        candidates.append(
            MatchedTransferCandidate(
                inflow=inf,
                outflow=outf,
            )
        )

    return candidates
