"""
Unit tests for pure Recurrence Engine (backend/domain/recurring_transactions.py).
Verifies all supported cadences, date jitter tolerances, month-end handling,
amount stability, negative test cases, and order invariance.
"""

import random
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.domain.recurring_transactions import (
    DetectedRecurringSeries,
    RecurrenceTransactionInput,
    add_one_month,
    add_one_year,
    calculate_next_expected_date,
    detect_cadence,
    detect_recurring_series,
    evaluate_amount_stability,
    is_month_end,
)


def _make_tx(
    date_val: date,
    amount: Decimal,
    merchant: str = "Netflix",
    account_id=None,
    tx_id=None,
) -> RecurrenceTransactionInput:
    return RecurrenceTransactionInput(
        transaction_id=tx_id or uuid4(),
        account_id=account_id or uuid4(),
        date=date_val,
        amount=amount,
        merchant=merchant,
        description=f"{merchant} charge",
    )


def test_monthly_fixed_recurrence():
    """Clear monthly fixed payment across 4 months."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 6, 15), Decimal("15.49"), "Netflix", account_id=acc_id),
        _make_tx(date(2026, 7, 15), Decimal("15.49"), "Netflix", account_id=acc_id),
        _make_tx(date(2026, 8, 15), Decimal("15.49"), "Netflix", account_id=acc_id),
        _make_tx(date(2026, 9, 15), Decimal("15.49"), "Netflix", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 1
    s = detected[0]
    assert s.merchant == "Netflix"
    assert s.cadence == "monthly"
    assert s.amount_type == "fixed"
    assert s.expected_amount == Decimal("15.49")
    assert s.direction == "outflow"
    assert s.occurrence_count == 4
    assert s.last_date == date(2026, 9, 15)
    assert s.next_expected_date == date(2026, 10, 15)


def test_monthly_variable_bill_recurrence():
    """Monthly utility bill with varying amounts within conservative tolerance."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 6, 10), Decimal("82.00"), "Electric Utility", account_id=acc_id),
        _make_tx(date(2026, 7, 11), Decimal("97.00"), "Electric Utility", account_id=acc_id),
        _make_tx(date(2026, 8, 9), Decimal("74.00"), "Electric Utility", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 1
    s = detected[0]
    assert s.merchant == "Electric Utility"
    assert s.cadence == "monthly"
    assert s.amount_type == "variable"
    assert s.expected_amount == Decimal("84.33")  # (82 + 97 + 74) / 3 = 84.33
    assert s.occurrence_count == 3
    assert s.next_expected_date == date(2026, 9, 9)


def test_weekly_recurrence():
    """Weekly lawn service every 7 days."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 7, 3), Decimal("40.00"), "Lawn Care", account_id=acc_id),
        _make_tx(date(2026, 7, 10), Decimal("40.00"), "Lawn Care", account_id=acc_id),
        _make_tx(date(2026, 7, 17), Decimal("40.00"), "Lawn Care", account_id=acc_id),
        _make_tx(date(2026, 7, 24), Decimal("40.00"), "Lawn Care", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 1
    s = detected[0]
    assert s.merchant == "Lawn Care"
    assert s.cadence == "weekly"
    assert s.amount_type == "fixed"
    assert s.expected_amount == Decimal("40.00")
    assert s.next_expected_date == date(2026, 7, 31)


def test_biweekly_income_recurrence():
    """Biweekly paycheck (inflow/negative amount) every 14 days."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 6, 5), Decimal("-2500.00"), "Employer Payroll", account_id=acc_id),
        _make_tx(date(2026, 6, 19), Decimal("-2500.00"), "Employer Payroll", account_id=acc_id),
        _make_tx(date(2026, 7, 3), Decimal("-2500.00"), "Employer Payroll", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 1
    s = detected[0]
    assert s.merchant == "Employer Payroll"
    assert s.direction == "inflow"
    assert s.cadence == "biweekly"
    assert s.expected_amount == Decimal("2500.00")
    assert s.next_expected_date == date(2026, 7, 17)


def test_annual_membership_recurrence():
    """Annual membership renewal once a year across 3 years."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2024, 5, 20), Decimal("139.00"), "Amazon Prime", account_id=acc_id),
        _make_tx(date(2025, 5, 21), Decimal("139.00"), "Amazon Prime", account_id=acc_id),
        _make_tx(date(2026, 5, 20), Decimal("139.00"), "Amazon Prime", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 1
    s = detected[0]
    assert s.merchant == "Amazon Prime"
    assert s.cadence == "annual"
    assert s.amount_type == "fixed"
    assert s.expected_amount == Decimal("139.00")
    assert s.next_expected_date == date(2027, 5, 20)


def test_date_jitter_monthly():
    """Monthly billing with date jitter due to weekends (Jan 15, Feb 14, Mar 15, Apr 16)."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("50.00"), "Internet Service", account_id=acc_id),
        _make_tx(date(2026, 2, 14), Decimal("50.00"), "Internet Service", account_id=acc_id),
        _make_tx(date(2026, 3, 15), Decimal("50.00"), "Internet Service", account_id=acc_id),
        _make_tx(date(2026, 4, 16), Decimal("50.00"), "Internet Service", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 1
    assert detected[0].cadence == "monthly"
    assert detected[0].occurrence_count == 4


def test_month_end_recurrence():
    """Month-end recurrence (Jan 31, Feb 28, Mar 31)."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 31), Decimal("29.99"), "Cloud Storage", account_id=acc_id),
        _make_tx(date(2026, 2, 28), Decimal("29.99"), "Cloud Storage", account_id=acc_id),
        _make_tx(date(2026, 3, 31), Decimal("29.99"), "Cloud Storage", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 1
    s = detected[0]
    assert s.cadence == "monthly"
    # End of March (31) -> next is end of April (30)
    assert s.next_expected_date == date(2026, 4, 30)


def test_opposite_sign_not_grouped():
    """Charges (+100) and refunds (-100) on same merchant must not form a recurring series."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("100.00"), "Merchant X", account_id=acc_id),
        _make_tx(date(2026, 2, 15), Decimal("-100.00"), "Merchant X", account_id=acc_id),
        _make_tx(date(2026, 3, 15), Decimal("100.00"), "Merchant X", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    # Neither outflow (2 txns) nor inflow (1 txn) meets the threshold of 3
    assert len(detected) == 0


def test_different_accounts_not_merged():
    """Same merchant on different accounts must not merge across accounts."""
    acc_1 = uuid4()
    acc_2 = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("15.00"), "Spotify", account_id=acc_1),
        _make_tx(date(2026, 2, 15), Decimal("15.00"), "Spotify", account_id=acc_1),
        _make_tx(date(2026, 3, 15), Decimal("15.00"), "Spotify", account_id=acc_2),  # different account
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 0


def test_different_merchants_not_merged():
    """Different merchants on the same cadence are not merged."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("10.00"), "Apple", account_id=acc_id),
        _make_tx(date(2026, 2, 15), Decimal("10.00"), "Google", account_id=acc_id),
        _make_tx(date(2026, 3, 15), Decimal("10.00"), "Microsoft", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 0


def test_amount_outlier_rejected():
    """Erratic amounts ($10, $500, $5) fail variable amount stability check."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("10.00"), "Random Store", account_id=acc_id),
        _make_tx(date(2026, 2, 15), Decimal("500.00"), "Random Store", account_id=acc_id),
        _make_tx(date(2026, 3, 15), Decimal("5.00"), "Random Store", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 0


def test_date_outlier_rejected():
    """Irregular dates (Jan 15, Jan 20, Apr 15) fail cadence detection."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("25.00"), "Coffee Shop", account_id=acc_id),
        _make_tx(date(2026, 1, 20), Decimal("25.00"), "Coffee Shop", account_id=acc_id),
        _make_tx(date(2026, 4, 15), Decimal("25.00"), "Coffee Shop", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 0


def test_insufficient_occurrences_rejected():
    """2 occurrences cannot establish a recurring pattern (requires minimum 3)."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("15.00"), "Music Service", account_id=acc_id),
        _make_tx(date(2026, 2, 15), Decimal("15.00"), "Music Service", account_id=acc_id),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 0


def test_blank_merchant_excluded():
    """Transactions with blank or whitespace-only merchant do not form a series."""
    acc_id = uuid4()
    txns = [
        RecurrenceTransactionInput(
            transaction_id=uuid4(),
            account_id=acc_id,
            date=date(2026, 1, 15),
            amount=Decimal("20.00"),
            merchant="",
            description="",
        ),
        RecurrenceTransactionInput(
            transaction_id=uuid4(),
            account_id=acc_id,
            date=date(2026, 2, 15),
            amount=Decimal("20.00"),
            merchant="   ",
            description="   ",
        ),
        RecurrenceTransactionInput(
            transaction_id=uuid4(),
            account_id=acc_id,
            date=date(2026, 3, 15),
            amount=Decimal("20.00"),
            merchant=None,
            description=None,
        ),
    ]

    detected = detect_recurring_series(txns)
    assert len(detected) == 0


def test_order_invariance():
    """Input list order does not alter detection results."""
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("15.49"), "Netflix", account_id=acc_id),
        _make_tx(date(2026, 2, 15), Decimal("15.49"), "Netflix", account_id=acc_id),
        _make_tx(date(2026, 3, 15), Decimal("15.49"), "Netflix", account_id=acc_id),
        _make_tx(date(2026, 4, 15), Decimal("15.49"), "Netflix", account_id=acc_id),
        _make_tx(date(2026, 1, 1), Decimal("50.00"), "Water Utility", account_id=acc_id),
        _make_tx(date(2026, 2, 1), Decimal("52.00"), "Water Utility", account_id=acc_id),
        _make_tx(date(2026, 3, 1), Decimal("48.00"), "Water Utility", account_id=acc_id),
    ]

    result_original = detect_recurring_series(txns)

    # Shuffle repeatedly
    for seed in [42, 101, 999]:
        shuffled = list(txns)
        random.seed(seed)
        random.shuffle(shuffled)
        result_shuffled = detect_recurring_series(shuffled)
        assert result_original == result_shuffled


def test_next_date_helpers():
    """Verifies calendar math helpers for leap years and month ends."""
    # Jan 31 -> Feb 28 on a non-leap year (2025)
    assert add_one_month(date(2025, 1, 31)) == date(2025, 2, 28)
    # Jan 31 -> Feb 29 on a leap year (2024)
    assert add_one_month(date(2024, 1, 31)) == date(2024, 2, 29)
    # Feb 28 on non-leap year (2025) -> Mar 31
    assert add_one_month(date(2025, 2, 28)) == date(2025, 3, 31)
    # Mar 31 -> Apr 30
    assert add_one_month(date(2026, 3, 31)) == date(2026, 4, 30)
    # Dec 15 -> Jan 15 of next year
    assert add_one_month(date(2026, 12, 15)) == date(2027, 1, 15)

    # Annual leap year: Feb 29 2024 -> Feb 28 2025
    assert add_one_year(date(2024, 2, 29)) == date(2025, 2, 28)


def test_inflow_fixed_paycheck_stability():
    """
    Fixed recurring inflows (e.g. -2500.00 biweekly paycheck) use absolute monetary magnitudes,
    preserve direction='inflow', and report expected positive magnitude.
    """
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 2), Decimal("-2500.00"), "Acme Employer Inc", account_id=acc_id),
        _make_tx(date(2026, 1, 16), Decimal("-2500.00"), "Acme Employer Inc", account_id=acc_id),
        _make_tx(date(2026, 1, 30), Decimal("-2500.00"), "Acme Employer Inc", account_id=acc_id),
    ]

    # Evaluate amount stability directly
    eval_res = evaluate_amount_stability([t.amount for t in txns])
    assert eval_res == ("fixed", Decimal("2500.00"))

    # Full series detection
    detected = detect_recurring_series(txns)
    assert len(detected) == 1
    s = detected[0]
    assert s.merchant == "Acme Employer Inc"
    assert s.direction == "inflow"
    assert s.cadence == "biweekly"
    assert s.amount_type == "fixed"
    assert s.expected_amount == Decimal("2500.00")
    assert s.next_expected_date == date(2026, 2, 13)


def test_inflow_variable_income_stability():
    """
    Reasonable variable negative inflows (e.g. -1210.00, -1180.00, -1250.00) pass
    conservative absolute CV threshold and yield positive typical amount.
    """
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("-1210.00"), "Consulting Client", account_id=acc_id),
        _make_tx(date(2026, 2, 15), Decimal("-1180.00"), "Consulting Client", account_id=acc_id),
        _make_tx(date(2026, 3, 15), Decimal("-1250.00"), "Consulting Client", account_id=acc_id),
    ]

    eval_res = evaluate_amount_stability([t.amount for t in txns])
    assert eval_res is not None
    amt_type, mean_val = eval_res
    assert amt_type == "variable"
    assert mean_val == Decimal("1213.33")

    detected = detect_recurring_series(txns)
    assert len(detected) == 1
    assert detected[0].direction == "inflow"
    assert detected[0].amount_type == "variable"
    assert detected[0].expected_amount == Decimal("1213.33")
    assert detected[0].cadence == "monthly"


def test_inflow_wildly_variable_negative_amounts_rejected():
    """
    Wildly variable negative amounts (e.g. -500, -1500, -3000) MUST be rejected.
    They must not pass merely because signed calculations or negative CV could occur.
    """
    acc_id = uuid4()
    txns = [
        _make_tx(date(2026, 1, 15), Decimal("-500.00"), "Irregular Gig", account_id=acc_id),
        _make_tx(date(2026, 2, 15), Decimal("-1500.00"), "Irregular Gig", account_id=acc_id),
        _make_tx(date(2026, 3, 15), Decimal("-3000.00"), "Irregular Gig", account_id=acc_id),
    ]

    # Directly evaluate: ratio = 3000/500 = 6.0 > 2.5, cv = 1027.4/1666.67 = 0.616 > 0.35
    eval_res = evaluate_amount_stability([t.amount for t in txns])
    assert eval_res is None

    detected = detect_recurring_series(txns)
    assert len(detected) == 0

