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
