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
    """Verify negative payment transfer transactions reduce balance_owed and report positive payments_this_month."""
    tx = CreditCardTransaction(
        amount=Decimal("-80.00"),
        date=date(2026, 6, 20),
        is_transfer=True,
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
        is_transfer=True,
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


def test_future_transactions_excluded_from_historical_balance_and_metrics():
    """Verify transactions after selected month cutoff do NOT affect balance_owed or monthly metrics."""
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
        cutoff_exclusive=PERIOD_END,
    )
    assert state.balance_owed == Decimal("500.00")
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
        is_transfer=True,
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
    Verify transfer transactions (is_transfer=True) are included in balance_owed calculation.
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
    Verify transfer transactions (is_transfer=True) with positive amount are excluded from charges_this_month.
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
    Verify negative payments with is_transfer=True are included in payments_this_month.
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
        is_transfer=True,
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


# --- Explicit New Domain Specification Tests ---

def test_merchant_refund_reduces_balance_not_payments_nor_charges():
    """
    Regression scenario 1 (Refund):
    +100 purchase (non-transfer)
    -25 refund (non-transfer)
    Expected: balance = 75, charges = 100, payments = 0.
    Refund reduces liability but is neither a charge nor a cardholder payment.
    """
    tx_purchase = CreditCardTransaction(
        amount=Decimal("100.00"),
        date=date(2026, 6, 5),
        is_transfer=False,
    )
    tx_refund = CreditCardTransaction(
        amount=Decimal("-25.00"),
        date=date(2026, 6, 12),
        is_transfer=False,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("0.00"),
        transactions=[tx_purchase, tx_refund],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("75.00")
    assert state.charges_this_month == Decimal("100.00")
    assert state.payments_this_month == Decimal("0.00")


def test_card_payment_reduces_balance_and_counts_as_payment():
    """
    Regression scenario 2 (Payment):
    +100 purchase (non-transfer)
    -100 transfer payment (is_transfer=True)
    Expected: balance = 0, charges = 100, payments = 100.
    """
    tx_purchase = CreditCardTransaction(
        amount=Decimal("100.00"),
        date=date(2026, 6, 5),
        is_transfer=False,
    )
    tx_payment = CreditCardTransaction(
        amount=Decimal("-100.00"),
        date=date(2026, 6, 20),
        is_transfer=True,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("0.00"),
        transactions=[tx_purchase, tx_payment],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("0.00")
    assert state.charges_this_month == Decimal("100.00")
    assert state.payments_this_month == Decimal("100.00")


def test_refund_and_payment_together():
    """
    Regression scenario 3 (Refund + Payment):
    +100 purchase (non-transfer)
    -25 refund (non-transfer)
    -50 transfer payment (is_transfer=True)
    Expected: balance = 25, charges = 100, payments = 50.
    """
    tx_purchase = CreditCardTransaction(
        amount=Decimal("100.00"),
        date=date(2026, 6, 5),
        is_transfer=False,
    )
    tx_refund = CreditCardTransaction(
        amount=Decimal("-25.00"),
        date=date(2026, 6, 12),
        is_transfer=False,
    )
    tx_payment = CreditCardTransaction(
        amount=Decimal("-50.00"),
        date=date(2026, 6, 22),
        is_transfer=True,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("0.00"),
        transactions=[tx_purchase, tx_refund, tx_payment],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("25.00")
    assert state.charges_this_month == Decimal("100.00")
    assert state.payments_this_month == Decimal("50.00")


def test_future_current_month_purchase_excluded_until_date_reached():
    """
    Regression scenario 4 (Future current-month purchase):
    Assume today is June 7 (cutoff_exclusive = June 8).
    June 2 purchase +100
    June 20 purchase +60
    Expected: balance = 100, charges = 100, payments = 0.
    Future transaction must affect none of balance, charges, or payments until reached.
    """
    tx_past = CreditCardTransaction(
        amount=Decimal("100.00"),
        date=date(2026, 6, 2),
        is_transfer=False,
    )
    tx_future = CreditCardTransaction(
        amount=Decimal("60.00"),
        date=date(2026, 6, 20),
        is_transfer=False,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("0.00"),
        transactions=[tx_past, tx_future],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        cutoff_exclusive=date(2026, 6, 8),
    )
    assert state.balance_owed == Decimal("100.00")
    assert state.charges_this_month == Decimal("100.00")
    assert state.payments_this_month == Decimal("0.00")


def test_future_current_month_payment_excluded_until_date_reached():
    """
    Regression scenario 5 (Future payment):
    June 2 purchase +100
    June 20 payment -50 (transfer)
    When cutoff is June 8:
    Future payment must not prematurely reduce balance or increase Paid This Month.
    """
    tx_past = CreditCardTransaction(
        amount=Decimal("100.00"),
        date=date(2026, 6, 2),
        is_transfer=False,
    )
    tx_future_pay = CreditCardTransaction(
        amount=Decimal("-50.00"),
        date=date(2026, 6, 20),
        is_transfer=True,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("0.00"),
        transactions=[tx_past, tx_future_pay],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        cutoff_exclusive=date(2026, 6, 8),
    )
    assert state.balance_owed == Decimal("100.00")
    assert state.charges_this_month == Decimal("100.00")
    assert state.payments_this_month == Decimal("0.00")


def test_historical_month_isolation_from_later_activity():
    """
    Regression scenario 6 (Historical month isolation):
    Sep 15 purchase +200
    Sep 25 payment -150 (transfer)
    Oct 05 purchase +300
    When viewing September (cutoff = Oct 1):
    Later-month transactions must not contaminate prior month's Balance Owed.
    """
    tx_sep_charge = CreditCardTransaction(
        amount=Decimal("200.00"),
        date=date(2026, 9, 15),
        is_transfer=False,
    )
    tx_sep_pay = CreditCardTransaction(
        amount=Decimal("-150.00"),
        date=date(2026, 9, 25),
        is_transfer=True,
    )
    tx_oct_charge = CreditCardTransaction(
        amount=Decimal("300.00"),
        date=date(2026, 10, 5),
        is_transfer=False,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("0.00"),
        transactions=[tx_sep_charge, tx_sep_pay, tx_oct_charge],
        period_start=date(2026, 9, 1),
        period_end=date(2026, 10, 1),
        cutoff_exclusive=date(2026, 10, 1),
    )
    assert state.balance_owed == Decimal("50.00")
    assert state.charges_this_month == Decimal("200.00")
    assert state.payments_this_month == Decimal("150.00")


def test_transfer_out_increases_balance_not_charges_nor_payments():
    """
    Regression scenario 7 (Transfer out):
    Positive transfer: amount > 0, is_transfer = True.
    Must increase balance, not increase charges, not increase payments.
    """
    tx_transfer_out = CreditCardTransaction(
        amount=Decimal("200.00"),
        date=date(2026, 6, 10),
        is_transfer=True,
    )

    state = calculate_credit_card_state(
        starting_balance=Decimal("100.00"),
        transactions=[tx_transfer_out],
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    assert state.balance_owed == Decimal("300.00")
    assert state.charges_this_month == Decimal("0.00")
    assert state.payments_this_month == Decimal("0.00")
