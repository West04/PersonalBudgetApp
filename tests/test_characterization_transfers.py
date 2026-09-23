from decimal import Decimal
from datetime import date
from uuid import uuid4
import pytest

from backend import models


def test_transfer_candidate_matching_heuristics(client, db_session):
    """
    Characterize the transfer candidate matching logic in GET /credit-cards/transfer-candidates.
    Matches opposing transactions (inflow < 0 and outflow > 0) with identical absolute amount,
    different account_ids, date separation <= 2 days, and is_transfer == False.
    """
    # Create two accounts: Checking and Credit Card
    acct_checking = models.Account(
        name="Checking Account",
        type="depository",
        subtype="checking",
        current_balance=Decimal("2000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD"
    )
    acct_card = models.Account(
        name="Credit Card",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("-500.00"),
        starting_balance=Decimal("0.00"),
        currency="USD"
    )
    db_session.add_all([acct_checking, acct_card])
    db_session.flush()

    # 1. Day separation = 0 (same date: 2026-06-10): SHOULD MATCH
    # Checking pays out $100 (+100.00 outflow)
    tx_out_0 = models.Transaction(
        account_id=acct_checking.id,
        amount=Decimal("100.00"),
        date=date(2026, 6, 10),
        description="PAYMENT TO CARD",
        is_transfer=False
    )
    # Card receives payment of $100 (-100.00 inflow)
    tx_in_0 = models.Transaction(
        account_id=acct_card.id,
        amount=Decimal("-100.00"),
        date=date(2026, 6, 10),
        description="PAYMENT RECEIVED - THANK YOU",
        is_transfer=False
    )

    # 2. Day separation = 1 (2026-06-12 vs 2026-06-13): SHOULD MATCH
    tx_out_1 = models.Transaction(
        account_id=acct_checking.id,
        amount=Decimal("50.00"),
        date=date(2026, 6, 12),
        description="TRANSFER OUT",
        is_transfer=False
    )
    tx_in_1 = models.Transaction(
        account_id=acct_card.id,
        amount=Decimal("-50.00"),
        date=date(2026, 6, 13),
        description="TRANSFER IN",
        is_transfer=False
    )

    # 3. Day separation = 2 (2026-06-15 vs 2026-06-17): SHOULD MATCH
    tx_out_2 = models.Transaction(
        account_id=acct_checking.id,
        amount=Decimal("75.00"),
        date=date(2026, 6, 15),
        description="TRANSFER OUT",
        is_transfer=False
    )
    tx_in_2 = models.Transaction(
        account_id=acct_card.id,
        amount=Decimal("-75.00"),
        date=date(2026, 6, 17),
        description="TRANSFER IN",
        is_transfer=False
    )

    # 4. Day separation = 3 (2026-06-15 vs 2026-06-18): SHOULD NOT MATCH (> 2 days)
    tx_out_3 = models.Transaction(
        account_id=acct_checking.id,
        amount=Decimal("200.00"),
        date=date(2026, 6, 15),
        description="TRANSFER OUT TOO LATE",
        is_transfer=False
    )
    tx_in_3 = models.Transaction(
        account_id=acct_card.id,
        amount=Decimal("-200.00"),
        date=date(2026, 6, 18),
        description="TRANSFER IN TOO LATE",
        is_transfer=False
    )

    # 5. Same account: Outflow +60 and Inflow -60 on SAME account: SHOULD NOT MATCH
    tx_out_same = models.Transaction(
        account_id=acct_checking.id,
        amount=Decimal("60.00"),
        date=date(2026, 6, 20),
        description="INTERNAL MOVE OUT",
        is_transfer=False
    )
    tx_in_same = models.Transaction(
        account_id=acct_checking.id,
        amount=Decimal("-60.00"),
        date=date(2026, 6, 20),
        description="INTERNAL MOVE IN",
        is_transfer=False
    )

    # 6. Already marked transfer: Outflow +80 and Inflow -80, but is_transfer=True: SHOULD NOT MATCH
    tx_out_marked = models.Transaction(
        account_id=acct_checking.id,
        amount=Decimal("80.00"),
        date=date(2026, 6, 22),
        description="ALREADY MARKED",
        is_transfer=True
    )
    tx_in_marked = models.Transaction(
        account_id=acct_card.id,
        amount=Decimal("-80.00"),
        date=date(2026, 6, 22),
        description="ALREADY MARKED INFLOW",
        is_transfer=True
    )

    # 7. Amount mismatch (+90.00 vs -90.01): SHOULD NOT MATCH
    tx_out_mismatch = models.Transaction(
        account_id=acct_checking.id,
        amount=Decimal("90.00"),
        date=date(2026, 6, 25),
        description="OUT 90",
        is_transfer=False
    )
    tx_in_mismatch = models.Transaction(
        account_id=acct_card.id,
        amount=Decimal("-90.01"),
        date=date(2026, 6, 25),
        description="IN 90.01",
        is_transfer=False
    )

    db_session.add_all([
        tx_out_0, tx_in_0,
        tx_out_1, tx_in_1,
        tx_out_2, tx_in_2,
        tx_out_3, tx_in_3,
        tx_out_same, tx_in_same,
        tx_out_marked, tx_in_marked,
        tx_out_mismatch, tx_in_mismatch,
    ])
    db_session.commit()

    # Call endpoint
    resp = client.get("/credit-cards/transfer-candidates")
    assert resp.status_code == 200
    candidates = resp.json()

    # We expect exactly 3 matches: pair 0 (100.00), pair 1 (50.00), pair 2 (75.00)
    assert len(candidates) == 3

    matched_amounts = {
        abs(Decimal(str(c["outflow_side"]["amount"]))) for c in candidates
    }
    assert matched_amounts == {Decimal("100.00"), Decimal("50.00"), Decimal("75.00")}

    # Verify candidate fields
    for c in candidates:
        assert Decimal(str(c["inflow_side"]["amount"])) < Decimal("0.00")
        assert Decimal(str(c["outflow_side"]["amount"])) > Decimal("0.00")
        assert abs(Decimal(str(c["inflow_side"]["amount"]))) == Decimal(str(c["outflow_side"]["amount"]))
        assert c["inflow_account_name"] == "Credit Card"
        assert c["outflow_account_name"] == "Checking Account"
