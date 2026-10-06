from decimal import Decimal
from datetime import date
from unittest.mock import patch
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
        "is_reviewed",
        "is_cleared",
        "is_reconciled",
        "merchant",
        "is_merchant_overridden",
        "category_source",
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
    assert outflow["is_reviewed"] is False
    assert outflow["is_cleared"] is False
    assert outflow["is_reconciled"] is False

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
        "last_reconciled_date",
        "last_reconciled_balance",
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


# =============================================================================
# Transfer Confirmation (POST /credit-cards/mark-transfers) Characterization
# =============================================================================


def test_mark_transfers_normal_success_cardinalities(client, db_session):
    """
    Characterize POST /credit-cards/mark-transfers for normal successful marking
    across different cardinalities (1 ID, 2 IDs, 3+ IDs):
    - HTTP 204 No Content returned.
    - Response body is empty.
    - All matching transaction records are mutated to is_transfer = True.
    - Database commit persists the state.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t1 = models.Transaction(account_id=acct.id, amount=Decimal("10.00"), date=date(2026, 6, 1), is_transfer=False)
    t2 = models.Transaction(account_id=acct.id, amount=Decimal("20.00"), date=date(2026, 6, 2), is_transfer=False)
    t3 = models.Transaction(account_id=acct.id, amount=Decimal("30.00"), date=date(2026, 6, 3), is_transfer=False)
    t4 = models.Transaction(account_id=acct.id, amount=Decimal("40.00"), date=date(2026, 6, 4), is_transfer=False)
    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    # 1. Single ID
    resp1 = client.post("/credit-cards/mark-transfers", json={"transaction_ids": [str(t1.transaction_id)]})
    assert resp1.status_code == 204
    assert resp1.text == ""
    db_session.refresh(t1)
    assert t1.is_transfer is True

    # 2. Pair of IDs
    resp2 = client.post("/credit-cards/mark-transfers", json={"transaction_ids": [str(t2.transaction_id), str(t3.transaction_id)]})
    assert resp2.status_code == 204
    assert resp2.text == ""
    db_session.refresh(t2)
    db_session.refresh(t3)
    assert t2.is_transfer is True
    assert t3.is_transfer is True

    # 3. Three IDs at once
    t1.is_transfer = False
    t2.is_transfer = False
    t3.is_transfer = False
    db_session.commit()

    resp3 = client.post("/credit-cards/mark-transfers", json={
        "transaction_ids": [str(t1.transaction_id), str(t2.transaction_id), str(t4.transaction_id)]
    })
    assert resp3.status_code == 204
    assert resp3.text == ""
    db_session.refresh(t1)
    db_session.refresh(t2)
    db_session.refresh(t3)
    db_session.refresh(t4)
    assert t1.is_transfer is True
    assert t2.is_transfer is True
    assert t3.is_transfer is False  # untouched
    assert t4.is_transfer is True


def test_mark_transfers_empty_list(client, db_session):
    """
    Characterize POST /credit-cards/mark-transfers with empty transaction_ids list:
    - Pydantic schema permits empty list [].
    - Returns HTTP 204 No Content.
    - Response body is empty.
    - No rows updated.
    - Commit still executes without error.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t = models.Transaction(account_id=acct.id, amount=Decimal("10.00"), date=date(2026, 6, 1), is_transfer=False)
    db_session.add(t)
    db_session.commit()

    resp = client.post("/credit-cards/mark-transfers", json={"transaction_ids": []})
    assert resp.status_code == 204
    assert resp.text == ""

    db_session.refresh(t)
    assert t.is_transfer is False


def test_mark_transfers_schema_validation_rejections(client, db_session):
    """
    Characterize Presentation/Pydantic validation contract for malformed payloads:
    - Missing required 'transaction_ids' key -> HTTP 422 (type: missing).
    - Invalid UUID string -> HTTP 422 (type: uuid_parsing).
    - Wrong JSON type (string instead of list) -> HTTP 422 (type: list_type).
    - Null item inside list -> HTTP 422 (type: uuid_parsing).
    - Does not reach persistence layer.
    """
    # 1. Missing transaction_ids field
    resp_missing = client.post("/credit-cards/mark-transfers", json={})
    assert resp_missing.status_code == 422
    err_missing = resp_missing.json()["detail"][0]
    assert err_missing["loc"] == ["body", "transaction_ids"]
    assert err_missing["type"] == "missing"

    # 2. Invalid UUID format
    resp_uuid = client.post("/credit-cards/mark-transfers", json={"transaction_ids": ["not-a-valid-uuid"]})
    assert resp_uuid.status_code == 422
    err_uuid = resp_uuid.json()["detail"][0]
    assert err_uuid["loc"] == ["body", "transaction_ids", 0]
    assert err_uuid["type"] == "uuid_parsing"

    # 3. Wrong type for list
    resp_type = client.post("/credit-cards/mark-transfers", json={"transaction_ids": "not-a-list"})
    assert resp_type.status_code == 422
    err_type = resp_type.json()["detail"][0]
    assert err_type["loc"] == ["body", "transaction_ids"]
    assert err_type["type"] == "list_type"

    # 4. Null item inside list
    resp_null = client.post("/credit-cards/mark-transfers", json={"transaction_ids": [None]})
    assert resp_null.status_code == 422
    err_null = resp_null.json()["detail"][0]
    assert err_null["loc"] == ["body", "transaction_ids", 0]
    assert err_null["type"] == "uuid_type"


def test_mark_transfers_nonexistent_ids_silently_succeeds(client, db_session):
    """
    Characterize POST /credit-cards/mark-transfers when all supplied IDs do not exist:
    - Does NOT return HTTP 404.
    - Returns HTTP 204 No Content.
    - Zero rows updated.
    - Commit executes cleanly.
    """
    fake_id_1 = str(uuid4())
    fake_id_2 = str(uuid4())

    resp = client.post("/credit-cards/mark-transfers", json={"transaction_ids": [fake_id_1, fake_id_2]})
    assert resp.status_code == 204
    assert resp.text == ""


def test_mark_transfers_mixed_existing_and_nonexistent_ids(client, db_session):
    """
    Characterize POST /credit-cards/mark-transfers with a mixture of existing and nonexistent IDs:
    - Returns HTTP 204 No Content (not 404 or 400).
    - Demonstrates partial mutation behavior: existing transaction rows are mutated to is_transfer = True.
    - Nonexistent IDs are silently ignored.
    - Mutation commits successfully.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t_real = models.Transaction(account_id=acct.id, amount=Decimal("50.00"), date=date(2026, 6, 1), is_transfer=False)
    db_session.add(t_real)
    db_session.commit()

    fake_id = str(uuid4())

    resp = client.post("/credit-cards/mark-transfers", json={
        "transaction_ids": [str(t_real.transaction_id), fake_id]
    })
    assert resp.status_code == 204

    db_session.refresh(t_real)
    assert t_real.is_transfer is True


def test_mark_transfers_duplicate_ids_in_payload(client, db_session):
    """
    Characterize POST /credit-cards/mark-transfers when the payload contains duplicate IDs:
    - Schema does not reject duplicates.
    - Returns HTTP 204 No Content.
    - SQL IN (...) clause updates the single matched row.
    - Row is set to is_transfer = True.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t = models.Transaction(account_id=acct.id, amount=Decimal("75.00"), date=date(2026, 6, 1), is_transfer=False)
    db_session.add(t)
    db_session.commit()

    tx_id_str = str(t.transaction_id)
    resp = client.post("/credit-cards/mark-transfers", json={"transaction_ids": [tx_id_str, tx_id_str]})
    assert resp.status_code == 204

    db_session.refresh(t)
    assert t.is_transfer is True


def test_mark_transfers_idempotence_and_mixed_already_marked(client, db_session):
    """
    Characterize POST /credit-cards/mark-transfers idempotence and mixed already-marked state:
    - Transactions already having is_transfer = True are updated idempotently without error.
    - Submitting a mix of already-true and false records updates false records to True and preserves already-true records.
    - Returns HTTP 204 No Content.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t_already = models.Transaction(account_id=acct.id, amount=Decimal("100.00"), date=date(2026, 6, 1), is_transfer=True)
    t_unmarked = models.Transaction(account_id=acct.id, amount=Decimal("200.00"), date=date(2026, 6, 2), is_transfer=False)
    db_session.add_all([t_already, t_unmarked])
    db_session.commit()

    # Call with already-marked record alone
    resp1 = client.post("/credit-cards/mark-transfers", json={"transaction_ids": [str(t_already.transaction_id)]})
    assert resp1.status_code == 204
    db_session.refresh(t_already)
    assert t_already.is_transfer is True

    # Call with mixed already-marked and unmarked records
    resp2 = client.post("/credit-cards/mark-transfers", json={
        "transaction_ids": [str(t_already.transaction_id), str(t_unmarked.transaction_id)]
    })
    assert resp2.status_code == 204
    db_session.refresh(t_already)
    db_session.refresh(t_unmarked)
    assert t_already.is_transfer is True
    assert t_unmarked.is_transfer is True


def test_mark_transfers_does_not_validate_account_separation(client, db_session):
    """
    Characterize that POST /credit-cards/mark-transfers does NOT enforce account separation:
    - Candidate search rejects same-account pairs.
    - Confirmation endpoint blindly updates all supplied IDs regardless of account.
    - Both transactions on the SAME account are marked is_transfer = True.
    - Returns HTTP 204 No Content.
    """
    acct = models.Account(name="Single Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t1 = models.Transaction(account_id=acct.id, amount=Decimal("50.00"), date=date(2026, 6, 1), is_transfer=False)
    t2 = models.Transaction(account_id=acct.id, amount=Decimal("-50.00"), date=date(2026, 6, 1), is_transfer=False)
    db_session.add_all([t1, t2])
    db_session.commit()

    resp = client.post("/credit-cards/mark-transfers", json={
        "transaction_ids": [str(t1.transaction_id), str(t2.transaction_id)]
    })
    assert resp.status_code == 204

    db_session.refresh(t1)
    db_session.refresh(t2)
    assert t1.is_transfer is True
    assert t2.is_transfer is True


def test_mark_transfers_does_not_validate_amount_or_sign(client, db_session):
    """
    Characterize that POST /credit-cards/mark-transfers does NOT validate amounts or signs:
    - Candidate search requires opposing signs and equal absolute amounts.
    - Confirmation endpoint marks transactions regardless of:
      - both positive (outflow + outflow)
      - both negative (inflow + inflow)
      - unequal absolute amounts (+100.00 vs -25.00)
      - zero amounts (0.00)
    - Returns HTTP 204 No Content.
    """
    acct1 = models.Account(name="Acct 1", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    acct2 = models.Account(name="Acct 2", type="credit", current_balance=Decimal("-500.00"), currency="USD")
    db_session.add_all([acct1, acct2])
    db_session.flush()

    t_pos1 = models.Transaction(account_id=acct1.id, amount=Decimal("100.00"), date=date(2026, 6, 1), is_transfer=False)
    t_pos2 = models.Transaction(account_id=acct2.id, amount=Decimal("50.00"), date=date(2026, 6, 1), is_transfer=False)
    t_zero = models.Transaction(account_id=acct1.id, amount=Decimal("0.00"), date=date(2026, 6, 1), is_transfer=False)
    db_session.add_all([t_pos1, t_pos2, t_zero])
    db_session.commit()

    resp = client.post("/credit-cards/mark-transfers", json={
        "transaction_ids": [str(t_pos1.transaction_id), str(t_pos2.transaction_id), str(t_zero.transaction_id)]
    })
    assert resp.status_code == 204

    db_session.refresh(t_pos1)
    db_session.refresh(t_pos2)
    db_session.refresh(t_zero)
    assert t_pos1.is_transfer is True
    assert t_pos2.is_transfer is True
    assert t_zero.is_transfer is True


def test_mark_transfers_does_not_validate_date_proximity(client, db_session):
    """
    Characterize that POST /credit-cards/mark-transfers does NOT validate transaction dates:
    - Candidate search enforces <= 2 days separation.
    - Confirmation endpoint marks transactions whose dates are weeks or months apart.
    - Returns HTTP 204 No Content.
    """
    acct1 = models.Account(name="Acct 1", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    acct2 = models.Account(name="Acct 2", type="credit", current_balance=Decimal("-500.00"), currency="USD")
    db_session.add_all([acct1, acct2])
    db_session.flush()

    t_early = models.Transaction(account_id=acct1.id, amount=Decimal("100.00"), date=date(2026, 1, 1), is_transfer=False)
    t_late = models.Transaction(account_id=acct2.id, amount=Decimal("-100.00"), date=date(2026, 6, 1), is_transfer=False)
    db_session.add_all([t_early, t_late])
    db_session.commit()

    resp = client.post("/credit-cards/mark-transfers", json={
        "transaction_ids": [str(t_early.transaction_id), str(t_late.transaction_id)]
    })
    assert resp.status_code == 204

    db_session.refresh(t_early)
    db_session.refresh(t_late)
    assert t_early.is_transfer is True
    assert t_late.is_transfer is True


def test_mark_transfers_downstream_candidate_search_effect(client, db_session):
    """
    Characterize downstream effect of mark-transfers on candidate search:
    - A matching pair initially appears in GET /credit-cards/transfer-candidates.
    - After calling POST /credit-cards/mark-transfers on the pair, is_transfer becomes True.
    - Subsequent call to GET /credit-cards/transfer-candidates returns empty list [].
    """
    chk = models.Account(name="Downstream Checking", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    cc = models.Account(name="Downstream CC", type="credit", current_balance=Decimal("-100.00"), currency="USD")
    db_session.add_all([chk, cc])
    db_session.flush()

    tx_out = models.Transaction(account_id=chk.id, amount=Decimal("100.00"), date=date(2026, 6, 10), description="Checking Transfer Out", is_transfer=False)
    tx_in = models.Transaction(account_id=cc.id, amount=Decimal("-100.00"), date=date(2026, 6, 10), description="CC Payment In", is_transfer=False)
    db_session.add_all([tx_out, tx_in])
    db_session.commit()

    # Verify present before confirmation
    resp_before = client.get("/credit-cards/transfer-candidates")
    assert resp_before.status_code == 200
    assert len(resp_before.json()) == 1

    # Confirm pair
    resp_confirm = client.post("/credit-cards/mark-transfers", json={
        "transaction_ids": [str(tx_out.transaction_id), str(tx_in.transaction_id)]
    })
    assert resp_confirm.status_code == 204

    # Verify absent after confirmation
    resp_after = client.get("/credit-cards/transfer-candidates")
    assert resp_after.status_code == 200
    assert resp_after.json() == []


def test_mark_transfers_downstream_credit_card_summary_effect(client, db_session):
    """
    Characterize downstream effect of mark-transfers on credit card summary:
    - A positive credit card transaction initially contributes to charges_this_month in GET /credit-cards/summary.
    - After marking as transfer (is_transfer=True), charges_this_month excludes the transaction.
    - all-time balance_owed remains unchanged (still includes the transaction).
    """
    cc = models.Account(name="Rewards Card", type="credit", subtype="credit card", starting_balance=Decimal("0.00"), current_balance=Decimal("-200.00"), currency="USD")
    db_session.add(cc)
    db_session.flush()

    tx = models.Transaction(account_id=cc.id, amount=Decimal("80.00"), date=date(2026, 6, 15), description="Card Charge", is_transfer=False)
    db_session.add(tx)
    db_session.commit()

    # Before: charges_this_month = 80.00, balance_owed = 80.00
    resp_before = client.get("/credit-cards/summary?month=2026-06")
    assert resp_before.status_code == 200
    card_before = resp_before.json()["cards"][0]
    assert Decimal(str(card_before["charges_this_month"])) == Decimal("80.00")
    assert Decimal(str(card_before["balance_owed"])) == Decimal("80.00")

    # Mark as transfer
    resp_mark = client.post("/credit-cards/mark-transfers", json={"transaction_ids": [str(tx.transaction_id)]})
    assert resp_mark.status_code == 204

    # After: charges_this_month drops to 0.00, balance_owed remains 80.00
    resp_after = client.get("/credit-cards/summary?month=2026-06")
    assert resp_after.status_code == 200
    card_after = resp_after.json()["cards"][0]
    assert Decimal(str(card_after["charges_this_month"])) == Decimal("0.00")
    assert Decimal(str(card_after["balance_owed"])) == Decimal("80.00")


def test_mark_transfers_downstream_budget_summary_actuals_unaffected(client, db_session):
    """
    Characterize downstream effect of mark-transfers on Zero-Based Budgeting summary actuals:
    - Freezes CURRENT behavior: get_actuals_by_category filters only by date range and category_id.isnot(None).
    - Setting is_transfer = True does NOT change get_actuals_by_category output or total_expense_actual.
    - Category actuals remain identical before and after calling POST /credit-cards/mark-transfers.
    """
    grp = models.CategoryGroup(name="Daily Living", sort_order=1)
    db_session.add(grp)
    db_session.flush()

    cat = models.Category(name="Fuel", group_id=grp.category_group_id, type="expense", sort_order=1)
    acc = models.Account(name="Main Checking", type="depository", current_balance=Decimal("500.00"), currency="USD")
    db_session.add_all([cat, acc])
    db_session.flush()

    tx = models.Transaction(account_id=acc.id, category_id=cat.category_id, amount=Decimal("45.00"), date=date(2026, 6, 12), is_transfer=False)
    db_session.add(tx)
    db_session.commit()

    # Before mark-transfers
    resp_before = client.get("/summary/budget?month=2026-06")
    assert resp_before.status_code == 200
    data_before = resp_before.json()
    assert Decimal(str(data_before["total_expense_actual"])) == Decimal("45.00")

    # Mark as transfer
    resp_mark = client.post("/credit-cards/mark-transfers", json={"transaction_ids": [str(tx.transaction_id)]})
    assert resp_mark.status_code == 204

    # After mark-transfers: total_expense_actual remains 45.00 under current implementation
    resp_after = client.get("/summary/budget?month=2026-06")
    assert resp_after.status_code == 200
    data_after = resp_after.json()
    assert Decimal(str(data_after["total_expense_actual"])) == Decimal("45.00")


def test_mark_transfers_commit_semantics_and_single_commit(client, db_session):
    """
    Characterize mutation transaction semantics:
    - Exactly one db.commit() is invoked per request.
    - Bulk update is executed via a single query update statement (synchronize_session=False).
    - Commit occurs even when input list is empty or IDs are nonexistent.
    """
    with patch.object(db_session, "commit", wraps=db_session.commit) as spy_commit:
        resp = client.post("/credit-cards/mark-transfers", json={"transaction_ids": []})
        assert resp.status_code == 204
        assert spy_commit.call_count == 1

    with patch.object(db_session, "commit", wraps=db_session.commit) as spy_commit_nonexistent:
        resp2 = client.post("/credit-cards/mark-transfers", json={"transaction_ids": [str(uuid4())]})
        assert resp2.status_code == 204
        assert spy_commit_nonexistent.call_count == 1


