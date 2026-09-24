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


def test_multiple_active_credit_cards_and_isolation(client, db_session):
    """
    Characterize behavior with multiple active credit cards:
    - Cards returned in alphabetical order by name ascending
    - Transactions on one card do not affect the balance or metrics of another
    - All response fields and types match existing schema
    - category_id handles both UUID and None correctly
    """
    month_str = "2026-06"

    # Seed CategoryGroup & Category for category_id testing
    group = models.CategoryGroup(name="CC Char Group", sort_order=99)
    db_session.add(group)
    db_session.flush()

    category = models.Category(
        name="Dining Out",
        group_id=group.category_group_id,
        type="expense",
        sort_order=0
    )
    db_session.add(category)
    db_session.flush()

    # Seed two active cards out of alphabetical order
    card_zeta = models.Account(
        name="Zeta Card",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("300.00"),
        is_active=True,
        currency="USD"
    )
    card_alpha = models.Account(
        name="Alpha Visa",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("100.00"),
        is_active=True,
        currency="USD"
    )
    db_session.add_all([card_zeta, card_alpha])
    db_session.flush()

    # Transactions for Alpha Visa:
    # 1 charge with category_id, 1 payment without category_id (None)
    tx_alpha_charge = models.Transaction(
        account_id=card_alpha.id,
        category_id=category.category_id,
        amount=Decimal("50.00"),
        date=date(2026, 6, 10),
        description="Alpha Restaurant",
        is_transfer=False
    )
    tx_alpha_payment = models.Transaction(
        account_id=card_alpha.id,
        category_id=None,
        amount=Decimal("-40.00"),
        date=date(2026, 6, 20),
        description="Alpha Payment",
        is_transfer=False
    )

    # Transactions for Zeta Card:
    # 1 charge of 120.00
    tx_zeta_charge = models.Transaction(
        account_id=card_zeta.id,
        category_id=None,
        amount=Decimal("120.00"),
        date=date(2026, 6, 15),
        description="Zeta Electronics",
        is_transfer=False
    )

    db_session.add_all([tx_alpha_charge, tx_alpha_payment, tx_zeta_charge])
    db_session.commit()

    resp = client.get(f"/credit-cards/summary?month={month_str}")
    assert resp.status_code == 200
    data = resp.json()

    # Verify Summary response fields
    assert "month" in data
    assert data["month"] == month_str
    assert "cards" in data
    assert len(data["cards"]) == 2

    # 1. Alphabetical ordering: Alpha Visa must come before Zeta Card
    c0 = data["cards"][0]
    c1 = data["cards"][1]
    assert c0["account_name"] == "Alpha Visa"
    assert c1["account_name"] == "Zeta Card"

    # 2. Verify exact fields for AccountSummary
    expected_card_keys = {
        "account_id",
        "account_name",
        "starting_balance",
        "balance_owed",
        "charges_this_month",
        "payments_this_month",
        "transactions"
    }
    assert set(c0.keys()) == expected_card_keys

    # 3. Alpha metrics and transaction isolation:
    # starting_balance = 100, charges = 50, payments = 40, balance_owed = 100 + 50 - 40 = 110
    assert c0["account_id"] == str(card_alpha.id)
    assert Decimal(str(c0["starting_balance"])) == Decimal("100.00")
    assert Decimal(str(c0["balance_owed"])) == Decimal("110.00")
    assert Decimal(str(c0["charges_this_month"])) == Decimal("50.00")
    assert Decimal(str(c0["payments_this_month"])) == Decimal("40.00")
    assert len(c0["transactions"]) == 2

    # Verify transaction fields & category_id handling
    expected_tx_keys = {
        "transaction_id",
        "description",
        "amount",
        "date",
        "is_transfer",
        "category_id"
    }
    for tx in c0["transactions"]:
        assert set(tx.keys()) == expected_tx_keys

    # Check category_id values
    tx_with_cat = next(t for t in c0["transactions"] if t["transaction_id"] == str(tx_alpha_charge.transaction_id))
    assert tx_with_cat["category_id"] == str(category.category_id)
    assert tx_with_cat["description"] == "Alpha Restaurant"

    tx_no_cat = next(t for t in c0["transactions"] if t["transaction_id"] == str(tx_alpha_payment.transaction_id))
    assert tx_no_cat["category_id"] is None
    assert tx_no_cat["description"] == "Alpha Payment"

    # 4. Zeta metrics and transaction isolation:
    # starting_balance = 300, charges = 120, payments = 0, balance_owed = 300 + 120 = 420
    assert c1["account_id"] == str(card_zeta.id)
    assert Decimal(str(c1["starting_balance"])) == Decimal("300.00")
    assert Decimal(str(c1["balance_owed"])) == Decimal("420.00")
    assert Decimal(str(c1["charges_this_month"])) == Decimal("120.00")
    assert Decimal(str(c1["payments_this_month"])) == Decimal("0.00")
    assert len(c1["transactions"]) == 1


def test_active_card_zero_transactions(client, db_session):
    """
    Characterize behavior when an active card has zero transactions:
    - balance_owed == starting_balance
    - charges_this_month == 0.00
    - payments_this_month == 0.00
    - transactions == []
    """
    month_str = "2026-06"
    card = models.Account(
        name="Empty Card",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("250.00"),
        is_active=True,
        currency="USD"
    )
    db_session.add(card)
    db_session.commit()

    resp = client.get(f"/credit-cards/summary?month={month_str}")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["cards"]) == 1
    summary = data["cards"][0]
    assert summary["account_id"] == str(card.id)
    assert Decimal(str(summary["starting_balance"])) == Decimal("250.00")
    assert Decimal(str(summary["balance_owed"])) == Decimal("250.00")
    assert Decimal(str(summary["charges_this_month"])) == Decimal("0.00")
    assert Decimal(str(summary["payments_this_month"])) == Decimal("0.00")
    assert summary["transactions"] == []


def test_no_active_credit_cards(client, db_session):
    """
    Characterize behavior when no active credit accounts exist in the database:
    - Returns 200 OK
    - cards list is empty []
    """
    month_str = "2026-06"
    # Seed only a depository account and an inactive credit card
    checking = models.Account(
        name="My Checking",
        type="depository",
        current_balance=Decimal("500.00"),
        is_active=True,
        currency="USD"
    )
    inactive_cc = models.Account(
        name="Closed Card",
        type="credit",
        current_balance=Decimal("0.00"),
        is_active=False,
        currency="USD"
    )
    db_session.add_all([checking, inactive_cc])
    db_session.commit()

    resp = client.get(f"/credit-cards/summary?month={month_str}")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"month": month_str, "cards": []}


def test_monthly_display_transaction_ordering(client, db_session):
    """
    Characterize transaction ordering for monthly display:
    - Transactions within the requested month must be returned strictly in date descending order.
    """
    month_str = "2026-06"
    card = models.Account(
        name="Order Test Card",
        type="credit",
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        is_active=True,
        currency="USD"
    )
    db_session.add(card)
    db_session.flush()

    # Add transactions inserted out of date order
    t_mid = models.Transaction(
        account_id=card.id,
        amount=Decimal("20.00"),
        date=date(2026, 6, 12),
        description="Mid month",
        is_transfer=False
    )
    t_late = models.Transaction(
        account_id=card.id,
        amount=Decimal("30.00"),
        date=date(2026, 6, 25),
        description="Late month",
        is_transfer=False
    )
    t_early = models.Transaction(
        account_id=card.id,
        amount=Decimal("10.00"),
        date=date(2026, 6, 3),
        description="Early month",
        is_transfer=False
    )
    db_session.add_all([t_mid, t_late, t_early])
    db_session.commit()

    resp = client.get(f"/credit-cards/summary?month={month_str}")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["cards"]) == 1
    txs = data["cards"][0]["transactions"]
    assert len(txs) == 3

    # Must be ordered date DESC: June 25, then June 12, then June 3
    dates = [t["date"] for t in txs]
    assert dates == ["2026-06-25", "2026-06-12", "2026-06-03"]


def test_invalid_month_format_errors(client):
    """
    Characterize error responses on invalid month query parameter:
    - Valid regex format but invalid calendar month (e.g. 2026-13) yields 400 Bad Request
    - Non-matching regex (e.g. 'not-a-month') yields 422 Unprocessable Entity
    """
    # 1. Regex matches ^\d{4}-\d{2}$ but month 13 is invalid
    resp_400 = client.get("/credit-cards/summary?month=2026-13")
    assert resp_400.status_code == 400
    assert resp_400.json() == {"detail": "Invalid month format. Use YYYY-MM"}

    # 2. Non-matching string
    resp_422 = client.get("/credit-cards/summary?month=invalid-date")
    assert resp_422.status_code == 422

