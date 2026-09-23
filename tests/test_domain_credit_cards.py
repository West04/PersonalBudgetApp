from datetime import date
from decimal import Decimal
import pytest

from backend.domain.credit_cards import (
    CreditCardTransaction,
    CreditCardState,
    calculate_credit_card_state,
)

PERIOD_START = date(2026, 6, 1)
PERIOD_END = date(2026, 7, 1)


def test_zero_starting_balance_no_transactions():
    """Verify zero starting balance with no transactions yields zero metrics."""
    state = calculate_credit_card_state(
        starting_balance=Decimal("0.00"),
        transactions=[],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.starting_balance == Decimal("0.00")
    assert state.balance_owed == Decimal("0.00")
    assert state.charges_this_month == Decimal("0.00")
    assert state.payments_this_month == Decimal("0.00")


def test_non_zero_starting_balance_no_transactions():
    """Verify non-zero starting balance sets balance_owed with no transactions."""
    state = calculate_credit_card_state(
        starting_balance=Decimal("450.00"),
        transactions=[],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.starting_balance == Decimal("450.00")
    assert state.balance_owed == Decimal("450.00")
    assert state.charges_this_month == Decimal("0.00")
    assert state.payments_this_month == Decimal("0.00")


def test_positive_charge_transactions():
    """Verify positive non-transfer charges increase balance_owed and charges_this_month."""
    tx1 = CreditCardTransaction(
        amount=Decimal("120.50"),
        date=date(2026, 6, 5),
        is_transfer=False,
    )
    tx2 = CreditCardTransaction(
        amount=Decimal("35.25"),
        date=date(2026, 6, 15),
        is_transfer=False,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("100.00"),
        transactions=[tx1, tx2],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("255.75")
    assert state.charges_this_month == Decimal("155.75")
    assert state.payments_this_month == Decimal("0.00")


def test_negative_payment_transactions():
    """Verify negative payment transactions reduce balance_owed and report positive payments_this_month."""
    tx = CreditCardTransaction(
        amount=Decimal("-80.00"),
        date=date(2026, 6, 20),
        is_transfer=False,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("200.00"),
        transactions=[tx],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("120.00")
    assert state.charges_this_month == Decimal("0.00")
    assert state.payments_this_month == Decimal("80.00")


def test_historical_transactions_affect_balance_owed():
    """Verify transactions prior to current month affect balance_owed but not this month's charges/payments."""
    tx_past_charge = CreditCardTransaction(
        amount=Decimal("150.00"),
        date=date(2026, 5, 10),
        is_transfer=False,
    )
    tx_past_payment = CreditCardTransaction(
        amount=Decimal("-50.00"),
        date=date(2026, 5, 25),
        is_transfer=False,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("500.00"),
        transactions=[tx_past_charge, tx_past_payment],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    # Net past transactions: +150 - 50 = +100
    assert state.balance_owed == Decimal("600.00")
    assert state.charges_this_month == Decimal("0.00")
    assert state.payments_this_month == Decimal("0.00")


def test_future_transactions_affect_balance_owed():
    """Verify transactions after current month affect all-time balance_owed but not current-month metrics."""
    tx_future = CreditCardTransaction(
        amount=Decimal("300.00"),
        date=date(2026, 7, 5),
        is_transfer=False,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("500.00"),
        transactions=[tx_future],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("800.00")
    assert state.charges_this_month == Decimal("0.00")
    assert state.payments_this_month == Decimal("0.00")


def test_current_month_transactions_affect_monthly_metrics():
    """Verify transactions in the current month affect both balance_owed and monthly metrics."""
    tx_charge = CreditCardTransaction(
        amount=Decimal("200.00"),
        date=date(2026, 6, 10),
        is_transfer=False,
    )
    tx_payment = CreditCardTransaction(
        amount=Decimal("-150.00"),
        date=date(2026, 6, 20),
        is_transfer=False,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("100.00"),
        transactions=[tx_charge, tx_payment],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("150.00")
    assert state.charges_this_month == Decimal("200.00")
    assert state.payments_this_month == Decimal("150.00")


def test_transfer_transaction_included_in_balance_owed():
    """
    Verify preserved unresolved behavior:
    Transfer transactions (is_transfer=True) ARE included in all-time balance_owed calculation.
    """
    tx_transfer = CreditCardTransaction(
        amount=Decimal("75.00"),
        date=date(2026, 6, 15),
        is_transfer=True,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("500.00"),
        transactions=[tx_transfer],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("575.00")


def test_transfer_transaction_excluded_from_charges_this_month():
    """
    Verify preserved unresolved behavior:
    Transfer transactions (is_transfer=True) with positive amount ARE EXCLUDED from charges_this_month.
    """
    tx_normal_charge = CreditCardTransaction(
        amount=Decimal("100.00"),
        date=date(2026, 6, 10),
        is_transfer=False,
    )
    tx_transfer_charge = CreditCardTransaction(
        amount=Decimal("75.00"),
        date=date(2026, 6, 15),
        is_transfer=True,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("0.00"),
        transactions=[tx_normal_charge, tx_transfer_charge],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    # charges_this_month must only include tx_normal_charge
    assert state.charges_this_month == Decimal("100.00")
    # while balance_owed includes both
    assert state.balance_owed == Decimal("175.00")


def test_transfer_payment_included_in_payments_this_month():
    """
    Verify preserved unresolved behavior:
    Negative payments with is_transfer=True ARE included in payments_this_month.
    """
    tx_transfer_payment = CreditCardTransaction(
        amount=Decimal("-250.00"),
        date=date(2026, 6, 20),
        is_transfer=True,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("500.00"),
        transactions=[tx_transfer_payment],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.payments_this_month == Decimal("250.00")
    assert state.balance_owed == Decimal("250.00")


def test_decimal_precision_and_sign_behavior():
    """Verify precise Decimal math without float rounding drift, preserving 2 decimal places."""
    tx1 = CreditCardTransaction(
        amount=Decimal("0.10"),
        date=date(2026, 6, 1),
        is_transfer=False,
    )
    tx2 = CreditCardTransaction(
        amount=Decimal("0.20"),
        date=date(2026, 6, 2),
        is_transfer=False,
    )
    tx3 = CreditCardTransaction(
        amount=Decimal("-0.30"),
        date=date(2026, 6, 3),
        is_transfer=False,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("0.00"),
        transactions=[tx1, tx2, tx3],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("0.00")
    assert state.charges_this_month == Decimal("0.30")
    assert state.payments_this_month == Decimal("0.30")
