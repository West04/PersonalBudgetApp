"""
Integration tests for merchant normalization across CSV imports, Plaid sync, and FastAPI endpoints.
"""

from decimal import Decimal
from datetime import date
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend import models
from backend.main import app
from backend.bank_statement_loader import USAALoader
from backend.managers.csv_import_manager import confirm_csv_import
from backend.database import migrate_merchant_state


@pytest.fixture(autouse=True)
def ensure_schema(db_session):
    migrate_merchant_state(db_session.get_bind())


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_account(db_session):
    account = models.Account(
        name="Integration Test Account",
        type="depository",
        subtype="checking",
    )
    db_session.add(account)
    db_session.commit()
    return account


def test_csv_import_populates_normalized_merchant(db_session, test_account):
    """
    Verifies that confirm_csv_import retains raw description and populates normalized merchant.
    """
    csv_text = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-15,SQ *BLUE BOTTLE 12345 SAN FRANCISCO CA,Coffee,-5.75,posted\n"
        "2026-06-16,HEB GROCERY,Groceries,-64.20,posted\n"
    )
    raw_bytes = csv_text.encode("utf-8")
    summary = confirm_csv_import(
        db=db_session,
        account_id=test_account.id,
        format_identifier="usaa",
        raw_bytes=raw_bytes,
    )
    assert summary.imported == 2
    assert summary.skipped == 0

    txns = (
        db_session.query(models.Transaction)
        .filter(models.Transaction.account_id == test_account.id)
        .order_by(models.Transaction.date.asc())
        .all()
    )
    assert len(txns) == 2

    # Row 1
    assert txns[0].description == "SQ *BLUE BOTTLE 12345 SAN FRANCISCO CA"
    assert txns[0].merchant == "Blue Bottle"
    assert txns[0].is_merchant_overridden is False

    # Row 2
    assert txns[1].description == "HEB GROCERY"
    assert txns[1].merchant == "HEB Grocery"
    assert txns[1].is_merchant_overridden is False


def test_transactions_api_create_read_update_merchant(client, test_account):
    """
    Verifies POST /transactions/, GET /transactions/, and PUT /transactions/{id}.
    """
    # 1. Create transaction with raw description
    create_payload = {
        "account_id": str(test_account.id),
        "description": "TST* CHIPOTLE 1234",
        "amount": "14.25",
        "date": "2026-06-18",
    }
    create_resp = client.post("/transactions/", json=create_payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["description"] == "TST* CHIPOTLE 1234"
    assert created_data["merchant"] == "Chipotle"
    assert created_data["is_merchant_overridden"] is False

    tx_id = created_data["transaction_id"]

    # 2. Search by merchant name
    get_resp = client.get("/transactions/?q=Chipotle")
    assert get_resp.status_code == 200
    items = get_resp.json()["items"]
    assert any(t["transaction_id"] == tx_id for t in items)

    # 3. Search by statement fragment
    get_noise_resp = client.get("/transactions/?q=1234")
    assert get_noise_resp.status_code == 200
    noise_items = get_noise_resp.json()["items"]
    assert any(t["transaction_id"] == tx_id for t in noise_items)

    # 4. User corrects merchant via PUT
    put_resp = client.put(f"/transactions/{tx_id}", json={"merchant": "Chipotle Downtown"})
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["merchant"] == "Chipotle Downtown"
    assert put_data["is_merchant_overridden"] is True
    assert put_data["description"] == "TST* CHIPOTLE 1234"


def test_plaid_sync_populates_normalized_merchant(client, db_session):
    """
    Verifies that Plaid sync populates normalized merchant using provider merchant
    precedence, and normalizes raw description when merchant_name is missing.
    """
    from unittest.mock import patch, MagicMock

    item = models.PlaidItem(
        plaid_item_id="item_merchant_sync",
        plaid_access_token_encrypted="encrypted_token",
        transactions_cursor=None,
    )
    account = models.Account(
        plaid_account_id="acc_plaid_merchant",
        name="Plaid Account",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
        is_active=True,
    )
    db_session.add(item)
    db_session.add(account)
    db_session.commit()

    page = {
        "added": [
            {
                "transaction_id": "tx_plaid_with_merchant",
                "account_id": "acc_plaid_merchant",
                "name": "SQ *BLUE BOTTLE 12345",
                "merchant_name": "Blue Bottle Coffee",
                "amount": 6.50,
                "date": "2026-06-20",
                "pending": False,
            },
            {
                "transaction_id": "tx_plaid_raw_only",
                "account_id": "acc_plaid_merchant",
                "name": "TST* CHIPOTLE 1234",
                "merchant_name": None,
                "amount": 14.00,
                "date": "2026-06-21",
                "pending": False,
            },
        ],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_done",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = page
    mock_http_resp.raise_for_status.return_value = None

    mock_accounts_resp = MagicMock()
    mock_accounts_resp.accounts = []

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_accounts_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp), \
         patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value="access-token"):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    tx1 = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_plaid_with_merchant").one()
    assert tx1.description == "SQ *BLUE BOTTLE 12345"
    assert tx1.merchant == "Blue Bottle Coffee"
    assert tx1.is_merchant_overridden is False

    tx2 = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_plaid_raw_only").one()
    assert tx2.description == "TST* CHIPOTLE 1234"
    assert tx2.merchant == "Chipotle"
    assert tx2.is_merchant_overridden is False
