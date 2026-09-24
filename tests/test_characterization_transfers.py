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


def test_transfer_candidates_empty_database(client, db_session):
    """
    Characterize GET /credit-cards/transfer-candidates when no transactions exist:
    - Returns HTTP 200 OK
    - Returns empty list []
    """
    resp = client.get("/credit-cards/transfer-candidates")
    assert resp.status_code == 200
    assert resp.json() == []


def test_transfer_candidates_no_qualifying_candidates(client, db_session):
    """
    Characterize GET /credit-cards/transfer-candidates when transactions exist but none qualify:
    - Transactions already marked is_transfer=True
    - Opposing transactions separated by > 2 days
    - Same-account opposing transactions
    - Returns HTTP 200 OK with empty list []
    """
    acct1 = models.Account(name="Acct 1", type="depository", current_balance=Decimal("100.00"), currency="USD")
    acct2 = models.Account(name="Acct 2", type="credit", current_balance=Decimal("-100.00"), currency="USD")
    db_session.add_all([acct1, acct2])
    db_session.flush()

    # Already marked
    t1 = models.Transaction(account_id=acct1.id, amount=Decimal("50.00"), date=date(2026, 6, 1), is_transfer=True)
    t2 = models.Transaction(account_id=acct2.id, amount=Decimal("-50.00"), date=date(2026, 6, 1), is_transfer=True)
    # Outside 2-day window
    t3 = models.Transaction(account_id=acct1.id, amount=Decimal("75.00"), date=date(2026, 6, 1), is_transfer=False)
    t4 = models.Transaction(account_id=acct2.id, amount=Decimal("-75.00"), date=date(2026, 6, 5), is_transfer=False)
    # Same account
    t5 = models.Transaction(account_id=acct1.id, amount=Decimal("30.00"), date=date(2026, 6, 10), is_transfer=False)
    t6 = models.Transaction(account_id=acct1.id, amount=Decimal("-30.00"), date=date(2026, 6, 10), is_transfer=False)

    db_session.add_all([t1, t2, t3, t4, t5, t6])
    db_session.commit()

    resp = client.get("/credit-cards/transfer-candidates")
    assert resp.status_code == 200
    assert resp.json() == []


def test_transfer_candidates_unmatched_transactions_ignored(client, db_session):
    """
    Characterize that solitary unmatched inflows and outflows are excluded from results:
    - Solitary inflow with no matching outflow does not appear in candidate list.
    - Solitary outflow with no matching inflow does not appear in candidate list.
    - Only legitimately paired candidates are returned.
    """
    checking = models.Account(name="Main Checking", type="depository", current_balance=Decimal("2000.00"), currency="USD")
    card = models.Account(name="Main Card", type="credit", current_balance=Decimal("-500.00"), currency="USD")
    db_session.add_all([checking, card])
    db_session.flush()

    # Solitary unmatched inflow (e.g. paycheck -2000.00 on checking)
    t_paycheck = models.Transaction(
        account_id=checking.id,
        amount=Decimal("-2000.00"),
        date=date(2026, 6, 1),
        description="Employer Direct Deposit",
        is_transfer=False,
    )
    # Solitary unmatched outflow (e.g. grocery +120.00 on checking)
    t_grocery = models.Transaction(
        account_id=checking.id,
        amount=Decimal("120.00"),
        date=date(2026, 6, 2),
        description="Grocery Store",
        is_transfer=False,
    )
    # Valid matching pair: +150.00 outflow on checking, -150.00 inflow on card
    t_pair_out = models.Transaction(
        account_id=checking.id,
        amount=Decimal("150.00"),
        date=date(2026, 6, 5),
        description="Payment to Card",
        is_transfer=False,
    )
    t_pair_in = models.Transaction(
        account_id=card.id,
        amount=Decimal("-150.00"),
        date=date(2026, 6, 6),
        description="Card Payment Received",
        is_transfer=False,
    )
    db_session.add_all([t_paycheck, t_grocery, t_pair_out, t_pair_in])
    db_session.commit()

    resp = client.get("/credit-cards/transfer-candidates")
    assert resp.status_code == 200
    candidates = resp.json()

    assert len(candidates) == 1
    c = candidates[0]
    assert c["inflow_side"]["description"] == "Card Payment Received"
    assert Decimal(str(c["inflow_side"]["amount"])) == Decimal("-150.00")
    assert c["outflow_side"]["description"] == "Payment to Card"
    assert Decimal(str(c["outflow_side"]["amount"])) == Decimal("150.00")

    # Verify solitary transactions are completely absent from both sides of response
    returned_descriptions = {
        c["inflow_side"]["description"],
        c["outflow_side"]["description"],
    }
    assert "Employer Direct Deposit" not in returned_descriptions
    assert "Grocery Store" not in returned_descriptions


def test_transfer_candidates_response_contract_and_enrichment(client, db_session):
    """
    Characterize the exact HTTP response schema, field types, category handling,
    verbatim description handling, and account enrichment:
    - inflow_side has CreditCardTransactionRead fields (no account_id, pending, datetime).
    - outflow_side has TransactionRead fields (including account_id, pending, datetime, and nested account).
    - inflow_account_name is top-level string from inflow transaction's account.
    - outflow_account_name is top-level string from outflow transaction's account.
    - outflow_side.account is nested AccountRead with all fields and status='connected' default.
    - category_id pass-through: preserved when UUID exists, None when absent.
    - verbatim description: preserves original description string on both sides.
    """
    # 1. Accounts
    acct_chk = models.Account(
        name="Contract Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("3500.50"),
        starting_balance=Decimal("500.00"),
        currency="USD",
        mask="9876",
        is_active=True,
    )
    acct_cc = models.Account(
        name="Contract Card",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("-250.75"),
        starting_balance=Decimal("0.00"),
        currency="USD",
        mask="1234",
        is_active=True,
    )
    db_session.add_all([acct_chk, acct_cc])
    db_session.flush()

    # 2. Category for category_id pass-through test
    grp = models.CategoryGroup(name="Transfer Group", sort_order=10)
    db_session.add(grp)
    db_session.flush()
    cat = models.Category(name="CC Payment Cat", group_id=grp.category_group_id, type="transfer", sort_order=1)
    db_session.add(cat)
    db_session.flush()

    # 3. Transfer pair: outflow has category_id and plaid_transaction_id; inflow has category_id=None
    tx_out = models.Transaction(
        account_id=acct_chk.id,
        category_id=cat.category_id,
        description="AutoPay to Contract Card #1234",
        amount=Decimal("250.75"),
        date=date(2026, 6, 15),
        plaid_transaction_id="plaid_tx_out_abc",
        pending=False,
        is_transfer=False,
    )
    tx_in = models.Transaction(
        account_id=acct_cc.id,
        category_id=None,
        description="Payment Received - Thank You!",
        amount=Decimal("-250.75"),
        date=date(2026, 6, 16),
        pending=False,
        is_transfer=False,
    )
    db_session.add_all([tx_out, tx_in])
    db_session.commit()

    resp = client.get("/credit-cards/transfer-candidates")
    assert resp.status_code == 200
    candidates = resp.json()

    assert len(candidates) == 1
    c = candidates[0]

    # Verify top-level candidate keys
    assert set(c.keys()) == {
        "inflow_side",
        "inflow_account_name",
        "outflow_side",
        "outflow_account_name",
    }

    # Verify top-level account enrichment names
    assert c["inflow_account_name"] == "Contract Card"
    assert c["outflow_account_name"] == "Contract Checking"

    # Verify inflow_side (CreditCardTransactionRead schema contract)
    inflow = c["inflow_side"]
    expected_inflow_keys = {
        "transaction_id",
        "description",
        "amount",
        "date",
        "is_transfer",
        "category_id",
    }
    assert set(inflow.keys()) == expected_inflow_keys
    assert inflow["transaction_id"] == str(tx_in.transaction_id)
    assert inflow["description"] == "Payment Received - Thank You!"
    assert Decimal(str(inflow["amount"])) == Decimal("-250.75")
    assert inflow["date"] == "2026-06-16"
    assert inflow["is_transfer"] is False
    assert inflow["category_id"] is None

    # Verify outflow_side (TransactionRead schema contract)
    outflow = c["outflow_side"]
    expected_outflow_keys = {
        "transaction_id",
        "plaid_transaction_id",
        "account_id",
        "category_id",
        "description",
        "amount",
        "date",
        "datetime",
        "pending",
        "is_transfer",
        "account",
    }
    assert set(outflow.keys()) == expected_outflow_keys
    assert outflow["transaction_id"] == str(tx_out.transaction_id)
    assert outflow["plaid_transaction_id"] == "plaid_tx_out_abc"
    assert outflow["account_id"] == str(acct_chk.id)
    assert outflow["category_id"] == str(cat.category_id)
    assert outflow["description"] == "AutoPay to Contract Card #1234"
    assert Decimal(str(outflow["amount"])) == Decimal("250.75")
    assert outflow["date"] == "2026-06-15"
    assert outflow["datetime"] is None
    assert outflow["pending"] is False
    assert outflow["is_transfer"] is False

    # Verify nested outflow account (AccountRead schema contract)
    acc = outflow["account"]
    assert acc is not None
    expected_account_keys = {
        "account_id",
        "plaid_account_id",
        "item_id",
        "name",
        "mask",
        "type",
        "subtype",
        "current_balance",
        "available_balance",
        "starting_balance",
        "currency",
        "balance_last_updated",
        "is_active",
        "status",
    }
    assert set(acc.keys()) == expected_account_keys
    assert acc["account_id"] == str(acct_chk.id)
    assert acc["name"] == "Contract Checking"
    assert acc["mask"] == "9876"
    assert acc["type"] == "depository"
    assert acc["subtype"] == "checking"
    assert Decimal(str(acc["current_balance"])) == Decimal("3500.50")
    assert acc["available_balance"] is None
    assert Decimal(str(acc["starting_balance"])) == Decimal("500.00")
    assert acc["currency"] == "USD"
    assert acc["balance_last_updated"] is None
    assert acc["is_active"] is True
    # status is supplied by Pydantic schema default (not an ORM column)
    assert acc["status"] == "connected"


def test_transfer_candidates_single_match_when_multiple_eligible(client, db_session):
    """
    Characterize that 1-to-1 matching is enforced when multiple opposing transactions qualify:
    - 1 inflow (-100.00 on Card)
    - 2 qualifying outflows (+100.00 on Checking A, +100.00 on Checking B, same date)
    - Verifies exactly 1 candidate is returned (no duplicate matching of the single inflow).
    - Does NOT assert which outflow wins (avoiding brittle dependence on unspecified SQL order).
    - Verifies the selected match pairs the inflow with one of the valid accounts.
    """
    card = models.Account(name="Card", type="credit", current_balance=Decimal("-100.00"), currency="USD")
    chk_a = models.Account(name="Checking Alpha", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    chk_b = models.Account(name="Checking Beta", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add_all([card, chk_a, chk_b])
    db_session.flush()

    tx_in = models.Transaction(
        account_id=card.id,
        amount=Decimal("-100.00"),
        date=date(2026, 6, 10),
        description="Card Payment",
        is_transfer=False,
    )
    tx_out_a = models.Transaction(
        account_id=chk_a.id,
        amount=Decimal("100.00"),
        date=date(2026, 6, 10),
        description="Transfer Out from Alpha",
        is_transfer=False,
    )
    tx_out_b = models.Transaction(
        account_id=chk_b.id,
        amount=Decimal("100.00"),
        date=date(2026, 6, 10),
        description="Transfer Out from Beta",
        is_transfer=False,
    )
    db_session.add_all([tx_in, tx_out_a, tx_out_b])
    db_session.commit()

    resp = client.get("/credit-cards/transfer-candidates")
    assert resp.status_code == 200
    candidates = resp.json()

    # Exactly 1 match must be returned (one inflow matches at most one outflow)
    assert len(candidates) == 1
    c = candidates[0]

    assert c["inflow_account_name"] == "Card"
    assert Decimal(str(c["inflow_side"]["amount"])) == Decimal("-100.00")
    assert Decimal(str(c["outflow_side"]["amount"])) == Decimal("100.00")
    # Must be either Checking Alpha or Checking Beta without assuming unspecified DB order
    assert c["outflow_account_name"] in {"Checking Alpha", "Checking Beta"}
    assert c["outflow_side"]["description"] in {"Transfer Out from Alpha", "Transfer Out from Beta"}

