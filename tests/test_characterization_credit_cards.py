from decimal import Decimal
from datetime import date
from uuid import uuid4
import pytest

from backend import models


def test_credit_card_summary_and_balance_owed(client, db_session):
    """
    Characterize credit card summary math in GET /credit-cards/summary?month=YYYY-MM:
    - balance_owed = starting_balance + all_time_net
    - charges_this_month = sum(amount > 0 and is_transfer == False)
    - payments_this_month = abs(sum(amount < 0))
    - Verify past-month transactions affect balance_owed but not this month's charges/payments
    - Verify transfer charges (is_transfer == True) are excluded from charges_this_month
    """
    month_str = "2026-06"

    # Create active credit card account with starting balance $500.00
    card = models.Account(
        name="Amex Blue",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("500.00"),
        is_active=True,
        currency="USD"
    )
    # Create inactive credit card (must be excluded)
    inactive_card = models.Account(
        name="Old Closed Card",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("100.00"),
        is_active=False,
        currency="USD"
    )
    # Create depository account (must be excluded from credit card summary)
    checking = models.Account(
        name="Main Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("0.00"),
        is_active=True,
        currency="USD"
    )
    db_session.add_all([card, inactive_card, checking])
    db_session.flush()

    # 1. Past month (May 2026):
    # Charge of +150.00, Payment of -100.00 -> Net +50.00
    tx_past_charge = models.Transaction(
        account_id=card.id,
        amount=Decimal("150.00"),
        date=date(2026, 5, 10),
        description="May Grocery",
        is_transfer=False
    )
    tx_past_payment = models.Transaction(
        account_id=card.id,
        amount=Decimal("-100.00"),
        date=date(2026, 5, 20),
        description="May Payment",
        is_transfer=False
    )

    # 2. Current month (June 2026):
    # Charge 1: +220.00
    tx_june_charge1 = models.Transaction(
        account_id=card.id,
        amount=Decimal("220.00"),
        date=date(2026, 6, 4),
        description="Electronics",
        is_transfer=False
    )
    # Charge 2: +80.00
    tx_june_charge2 = models.Transaction(
        account_id=card.id,
        amount=Decimal("80.00"),
        date=date(2026, 6, 12),
        description="Gas",
        is_transfer=False
    )
    # Payment 1: -250.00
    tx_june_pay1 = models.Transaction(
        account_id=card.id,
        amount=Decimal("-250.00"),
        date=date(2026, 6, 18),
        description="June Payment",
        is_transfer=False
    )
    # Payment 2: -50.00
    tx_june_pay2 = models.Transaction(
        account_id=card.id,
        amount=Decimal("-50.00"),
        date=date(2026, 6, 25),
        description="June Extra Payment",
        is_transfer=False
    )
    # Transfer transaction: +75.00 with is_transfer = True (e.g. balance transfer or fee transfer)
    tx_june_transfer = models.Transaction(
        account_id=card.id,
        amount=Decimal("75.00"),
        date=date(2026, 6, 20),
        description="Card Transfer In",
        is_transfer=True
    )

    # 3. Future month (July 2026):
    # Future charge: +300.00 (Affects all-time balance_owed, but NOT June charges)
    tx_july_charge = models.Transaction(
        account_id=card.id,
        amount=Decimal("300.00"),
        date=date(2026, 7, 2),
        description="July Charge",
        is_transfer=False
    )

    db_session.add_all([
        tx_past_charge, tx_past_payment,
        tx_june_charge1, tx_june_charge2,
        tx_june_pay1, tx_june_pay2,
        tx_june_transfer, tx_july_charge
    ])
    db_session.commit()

    # Call endpoint for June 2026
    resp = client.get(f"/credit-cards/summary?month={month_str}")
    assert resp.status_code == 200
    data = resp.json()

    # Only active credit cards should be returned (1 card)
    assert len(data["cards"]) == 1
    card_summary = data["cards"][0]
    assert card_summary["account_id"] == str(card.id)
    assert card_summary["account_name"] == "Amex Blue"
    assert Decimal(str(card_summary["starting_balance"])) == Decimal("500.00")

    # Math verification:
    # All-time transactions net:
    # May: +150 - 100 = +50
    # June: +220 + 80 - 250 - 50 + 75 = +75
    # July: +300
    # Total net all-time = 50 + 75 + 300 = +425.00
    # balance_owed = starting_balance (500) + all_time_net (425) = 925.00
    assert Decimal(str(card_summary["balance_owed"])) == Decimal("925.00")

    # June Charges: non-transfer positive transactions in June
    # 220.00 + 80.00 = 300.00 (tx_june_transfer of 75.00 is excluded because is_transfer=True)
    assert Decimal(str(card_summary["charges_this_month"])) == Decimal("300.00")

    # June Payments: absolute sum of negative transactions in June
    # |-250.00| + |-50.00| = 300.00
    assert Decimal(str(card_summary["payments_this_month"])) == Decimal("300.00")

    # June Transactions list should only have June items (5 items: 2 charges, 2 payments, 1 transfer)
    assert len(card_summary["transactions"]) == 5
