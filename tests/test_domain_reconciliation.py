from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest

from backend.domain.reconciliation import (
    MAX_TRANSFER_DAYS_DIFFERENCE,
    ReconciliationTransaction,
    detect_transfer_candidates,
)


def test_transfer_candidate_same_date():
    """Verify transactions on the same date (0-day difference) match."""
    acct1, acct2 = uuid4(), uuid4()
    tx_in = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("-100.00"),
        date=date(2026, 6, 10),
    )
    tx_out = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("100.00"),
        date=date(2026, 6, 10),
    )

    matches = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out])
    assert len(matches) == 1
    assert matches[0].inflow == tx_in
    assert matches[0].outflow == tx_out


def test_transfer_candidate_one_day_difference():
    """Verify transactions with a 1-day difference match (inflow earlier or outflow earlier)."""
    acct1, acct2 = uuid4(), uuid4()
    tx_out = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("50.00"),
        date=date(2026, 6, 10),
    )
    tx_in = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("-50.00"),
        date=date(2026, 6, 11),
    )

    matches = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out])
    assert len(matches) == 1
    assert matches[0].inflow == tx_in
    assert matches[0].outflow == tx_out


def test_transfer_candidate_two_day_difference():
    """Verify transactions with exactly a 2-day difference match (boundary condition)."""
    acct1, acct2 = uuid4(), uuid4()
    tx_in = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("-75.00"),
        date=date(2026, 6, 10),
    )
    tx_out = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("75.00"),
        date=date(2026, 6, 12),
    )

    matches = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out])
    assert len(matches) == 1
    assert matches[0].inflow == tx_in
    assert matches[0].outflow == tx_out


def test_transfer_candidate_three_day_difference():
    """Verify transactions with a 3-day difference do NOT match (> 2 days)."""
    acct1, acct2 = uuid4(), uuid4()
    tx_out = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("200.00"),
        date=date(2026, 6, 10),
    )
    tx_in = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("-200.00"),
        date=date(2026, 6, 13),
    )

    matches = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out])
    assert len(matches) == 0


def test_transfer_candidate_same_account():
    """Verify opposing transactions on the SAME account do NOT match."""
    same_acct = uuid4()
    tx_out = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=same_acct,
        amount=Decimal("60.00"),
        date=date(2026, 6, 10),
    )
    tx_in = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=same_acct,
        amount=Decimal("-60.00"),
        date=date(2026, 6, 10),
    )

    matches = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out])
    assert len(matches) == 0


def test_transfer_candidate_mismatched_amount():
    """Verify transactions with different absolute amounts do NOT match."""
    acct1, acct2 = uuid4(), uuid4()
    tx_out = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("100.00"),
        date=date(2026, 6, 10),
    )
    tx_in = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("-100.01"),
        date=date(2026, 6, 10),
    )

    matches = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out])
    assert len(matches) == 0


def test_transfer_candidate_same_sign_amounts():
    """Verify transactions with the same sign do NOT match across inflows/outflows."""
    acct1, acct2 = uuid4(), uuid4()

    tx_out_1 = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("150.00"),
        date=date(2026, 6, 10),
    )
    tx_out_2 = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("150.00"),
        date=date(2026, 6, 10),
    )
    # Passing outflows as inflows should not match
    assert len(detect_transfer_candidates(inflows=[tx_out_1], outflows=[tx_out_2])) == 0

    tx_in_1 = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("-150.00"),
        date=date(2026, 6, 10),
    )
    tx_in_2 = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("-150.00"),
        date=date(2026, 6, 10),
    )
    # Passing inflows as outflows should not match
    assert len(detect_transfer_candidates(inflows=[tx_in_1], outflows=[tx_in_2])) == 0


def test_transfer_candidate_already_marked_excluded():
    """Verify transactions marked with is_transfer=True are excluded from matching."""
    acct1, acct2 = uuid4(), uuid4()
    tx_out = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("80.00"),
        date=date(2026, 6, 10),
        is_transfer=True,
    )
    tx_in = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("-80.00"),
        date=date(2026, 6, 10),
        is_transfer=False,
    )

    assert len(detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out])) == 0


def test_transfer_candidate_outflow_not_reused():
    """Verify an outflow is matched at most once and cannot be reused across multiple inflows."""
    acct1, acct2, acct3 = uuid4(), uuid4(), uuid4()
    # Single outflow of 100
    tx_out = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("100.00"),
        date=date(2026, 6, 10),
    )
    # Two identical inflows of -100
    tx_in_1 = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("-100.00"),
        date=date(2026, 6, 10),
    )
    tx_in_2 = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct3,
        amount=Decimal("-100.00"),
        date=date(2026, 6, 11),
    )

    matches = detect_transfer_candidates(inflows=[tx_in_1, tx_in_2], outflows=[tx_out])
    assert len(matches) == 1
    assert matches[0].inflow == tx_in_1
    assert matches[0].outflow == tx_out


def test_reconciliation_transaction_has_no_payload():
    """Verify ReconciliationTransaction does not accept or carry infrastructure payload."""
    tx = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=uuid4(),
        amount=Decimal("50.00"),
        date=date(2026, 6, 10),
    )
    assert not hasattr(tx, "payload")
    with pytest.raises(TypeError):
        ReconciliationTransaction(  # type: ignore[call-arg]
            transaction_id=uuid4(),
            account_id=uuid4(),
            amount=Decimal("50.00"),
            date=date(2026, 6, 10),
            payload={"infra": True},
        )


def test_detect_transfer_candidates_calling_convention():
    """Verify signature only accepts inflows and outflows, with 2-day named constant."""
    assert MAX_TRANSFER_DAYS_DIFFERENCE == 2

    # Single-list transactions convention should raise TypeError
    with pytest.raises(TypeError):
        detect_transfer_candidates([ReconciliationTransaction(uuid4(), uuid4(), Decimal("10"), date.today())])  # type: ignore[call-arg]

    # max_days_difference keyword should raise TypeError
    with pytest.raises(TypeError):
        detect_transfer_candidates(inflows=[], outflows=[], max_days_difference=5)  # type: ignore[call-arg]


def test_detect_transfer_candidates_closest_date_wins():
    """
    Verify 0-day match is preferred over 2-day match regardless of input ordering.
    """
    acct1, acct2 = uuid4(), uuid4()
    tx_in = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct1,
        amount=Decimal("-100.00"),
        date=date(2026, 6, 10),
    )
    tx_out_far = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("100.00"),
        date=date(2026, 6, 12),  # distance 2
    )
    tx_out_close = ReconciliationTransaction(
        transaction_id=uuid4(),
        account_id=acct2,
        amount=Decimal("100.00"),
        date=date(2026, 6, 10),  # distance 0
    )

    # Order 1: far first
    matches1 = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out_far, tx_out_close])
    assert len(matches1) == 1
    assert matches1[0].inflow == tx_in
    assert matches1[0].outflow == tx_out_close

    # Order 2: close first
    matches2 = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out_close, tx_out_far])
    assert len(matches2) == 1
    assert matches2[0].inflow == tx_in
    assert matches2[0].outflow == tx_out_close


def test_detect_transfer_candidates_input_order_invariance():
    """
    Verify candidate selection is 100% invariant under input list permutations.
    """
    acct1, acct2, acct3 = uuid4(), uuid4(), uuid4()
    in1 = ReconciliationTransaction(uuid4(), acct1, Decimal("-50.00"), date(2026, 6, 1))
    in2 = ReconciliationTransaction(uuid4(), acct1, Decimal("-50.00"), date(2026, 6, 2))
    in3 = ReconciliationTransaction(uuid4(), acct1, Decimal("-50.00"), date(2026, 6, 3))

    out1 = ReconciliationTransaction(uuid4(), acct2, Decimal("50.00"), date(2026, 6, 1))
    out2 = ReconciliationTransaction(uuid4(), acct3, Decimal("50.00"), date(2026, 6, 2))

    expected_pairs = None
    permutations = [
        ([in1, in2, in3], [out1, out2]),
        ([in3, in2, in1], [out2, out1]),
        ([in2, in1, in3], [out1, out2]),
        ([in1, in3, in2], [out2, out1]),
    ]

    for inf_list, outf_list in permutations:
        res = detect_transfer_candidates(inflows=inf_list, outflows=outf_list)
        pair_ids = [(m.inflow.transaction_id, m.outflow.transaction_id) for m in res]
        if expected_pairs is None:
            expected_pairs = pair_ids
        else:
            assert pair_ids == expected_pairs


def test_detect_transfer_candidates_consecutive_transfers_no_crossing():
    """
    Verify consecutive-date transfers match same-day pairs and never cross into 1-day pairs:
    Outflow 1: +100 on Oct 1
    Outflow 2: +100 on Oct 2
    Inflow 1:  -100 on Oct 1
    Inflow 2:  -100 on Oct 2
    Must yield (In1, Out1) and (In2, Out2).
    """
    acct1, acct2 = uuid4(), uuid4()
    in1 = ReconciliationTransaction(uuid4(), acct1, Decimal("-100.00"), date(2026, 10, 1))
    in2 = ReconciliationTransaction(uuid4(), acct1, Decimal("-100.00"), date(2026, 10, 2))
    out1 = ReconciliationTransaction(uuid4(), acct2, Decimal("100.00"), date(2026, 10, 1))
    out2 = ReconciliationTransaction(uuid4(), acct2, Decimal("100.00"), date(2026, 10, 2))

    # Pass in crossed/reversed order
    matches = detect_transfer_candidates(inflows=[in1, in2], outflows=[out2, out1])
    assert len(matches) == 2

    # Map matched pairs
    pair_map = {m.inflow.transaction_id: m.outflow.transaction_id for m in matches}
    assert pair_map[in1.transaction_id] == out1.transaction_id
    assert pair_map[in2.transaction_id] == out2.transaction_id


def test_detect_transfer_candidates_equal_distance_tie_resolved_by_dates():
    """
    Verify equal date distance (both 1 day) is deterministically resolved
    by date ranking (outflow.date ascending).
    """
    acct1, acct2 = uuid4(), uuid4()
    tx_in = ReconciliationTransaction(uuid4(), acct1, Decimal("-100.00"), date(2026, 10, 2))
    tx_out_earlier = ReconciliationTransaction(uuid4(), acct2, Decimal("100.00"), date(2026, 10, 1))
    tx_out_later = ReconciliationTransaction(uuid4(), acct2, Decimal("100.00"), date(2026, 10, 3))

    matches_fwd = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out_earlier, tx_out_later])
    matches_rev = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out_later, tx_out_earlier])

    assert len(matches_fwd) == 1
    assert len(matches_rev) == 1
    # Both resolve to tx_out_earlier because outf.date (Oct 1) < (Oct 3)
    assert matches_fwd[0].outflow.transaction_id == tx_out_earlier.transaction_id
    assert matches_rev[0].outflow.transaction_id == tx_out_earlier.transaction_id


def test_detect_transfer_candidates_exact_tie_resolved_by_uuid():
    """
    Verify exact date and amount tie is deterministically resolved
    by transaction UUID lexicographical order.
    """
    acct1, acct2, acct3 = uuid4(), uuid4(), uuid4()
    tx_in = ReconciliationTransaction(uuid4(), acct1, Decimal("-100.00"), date(2026, 10, 1))

    id_a = uuid4()
    id_b = uuid4()
    # Ensure id_low < id_high
    id_low, id_high = sorted([id_a, id_b], key=str)

    tx_out_low = ReconciliationTransaction(id_low, acct2, Decimal("100.00"), date(2026, 10, 1))
    tx_out_high = ReconciliationTransaction(id_high, acct3, Decimal("100.00"), date(2026, 10, 1))

    # Test both orders
    res1 = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out_high, tx_out_low])
    res2 = detect_transfer_candidates(inflows=[tx_in], outflows=[tx_out_low, tx_out_high])

    assert len(res1) == 1
    assert len(res2) == 1
    assert res1[0].outflow.transaction_id == id_low
    assert res2[0].outflow.transaction_id == id_low


def test_detect_transfer_candidates_strongest_suggestion_priority():
    """
    Verify algorithm does NOT sacrifice a 0-day match merely to maximize total pair count.
    I1: -100 on Jun 1
    I2: -100 on Jun 3
    O1: +100 on Jun 1
    O2: +100 on May 30
    Possible pairs:
      I1 <-> O1: 0 days
      I1 <-> O2: 2 days
      I2 <-> O1: 2 days
    Must select I1 <-> O1 (0-day strong match), leaving I2 and O2 un-paired.
    """
    acct1, acct2 = uuid4(), uuid4()
    i1 = ReconciliationTransaction(uuid4(), acct1, Decimal("-100.00"), date(2026, 6, 1))
    i2 = ReconciliationTransaction(uuid4(), acct1, Decimal("-100.00"), date(2026, 6, 3))
    o1 = ReconciliationTransaction(uuid4(), acct2, Decimal("100.00"), date(2026, 6, 1))
    o2 = ReconciliationTransaction(uuid4(), acct2, Decimal("100.00"), date(2026, 5, 30))

    matches = detect_transfer_candidates(inflows=[i1, i2], outflows=[o1, o2])
    assert len(matches) == 1
    assert matches[0].inflow == i1
    assert matches[0].outflow == o1

