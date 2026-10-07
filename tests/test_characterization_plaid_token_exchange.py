"""
Characterization tests for Plaid Public-Token Exchange (POST /plaid/exchange_public_token).
Freezes the existing implementation behavior, request payload construction,
SDK interactions, two-commit ordering, orphan semantics on account sync failure,
error translation semantics, and HTTP contracts.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID
import pytest
from plaid.exceptions import ApiException

from backend import models
from backend.access.plaid_item_access import create_plaid_item, get_plaid_item_by_plaid_item_id
from backend.schemas import AccountRead


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _make_mock_account(
    account_id: str,
    name: str = "Plaid Checking",
    mask: str = "1234",
    account_type: str = "depository",
    subtype: str = "checking",
    current_balance: float = 100.0,
    available_balance: float = 80.0,
    iso_currency_code: str = "USD",
):
    """Constructs a mock Plaid SDK AccountBase object returning a data dict via to_dict()."""
    acct = MagicMock()
    acct.to_dict.return_value = {
        "account_id": account_id,
        "name": name,
        "mask": mask,
        "type": account_type,
        "subtype": subtype,
        "balances": {
            "current": current_balance,
            "available": available_balance,
            "iso_currency_code": iso_currency_code,
        },
    }
    return acct


def _make_mock_accounts_response(accounts):
    """Constructs a mock Plaid AccountsGetResponse object."""
    resp = MagicMock()
    resp.accounts = accounts
    return resp


def _make_mock_exchange_response(access_token="access-sandbox-tok-123", item_id="item-sandbox-plaid-456"):
    """Constructs a mock ItemPublicTokenExchangeResponse."""
    resp = MagicMock()
    resp.access_token = access_token
    resp.item_id = item_id
    return resp


# ---------------------------------------------------------------------------
# 1. Happy Path: New Item Creation & Initial Account Sync
# ---------------------------------------------------------------------------

def test_exchange_public_token_new_item_success(client, db_session):
    """
    POST /plaid/exchange_public_token with valid token:
    - Calls client.item_public_token_exchange
    - Creates and commits new PlaidItem with encrypted token and cursor=None
    - Calls client.accounts_get and stages accounts
    - Commits accounts and returns list matching schemas.AccountRead
    """
    mock_exchange = _make_mock_exchange_response(
        access_token="access-test-token-001",
        item_id="plaid_item_test_001",
    )
    mock_acct_1 = _make_mock_account(
        account_id="plaid_act_001",
        name="Primary Checking",
        mask="1111",
        account_type="depository",
        subtype="checking",
        current_balance=2500.50,
        available_balance=2400.00,
        iso_currency_code="USD",
    )
    mock_acct_2 = _make_mock_account(
        account_id="plaid_act_002",
        name="Rewards Card",
        mask="2222",
        account_type="credit",
        subtype="credit card",
        current_balance=150.75,
        available_balance=None,
        iso_currency_code="USD",
    )
    mock_accounts_resp = _make_mock_accounts_response([mock_acct_1, mock_acct_2])

    with patch("backend.access.plaid_access.client.item_public_token_exchange", return_value=mock_exchange) as mock_ex, \
         patch("backend.access.plaid_access.client.accounts_get", return_value=mock_accounts_resp) as mock_accts:
        response = client.post("/plaid/exchange_public_token", json={"public_token": "public-sandbox-valid-001"})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    # Validate response fields match AccountRead contract
    acc_0 = data[0]
    assert UUID(acc_0["account_id"])
    assert acc_0["name"] == "Primary Checking"
    assert Decimal(str(acc_0["current_balance"])) == Decimal("2500.50")
    assert Decimal(str(acc_0["available_balance"])) == Decimal("2400.00")
    assert acc_0["type"] == "depository"
    assert acc_0["subtype"] == "checking"
    assert acc_0["is_active"] is True

    acc_1 = data[1]
    assert UUID(acc_1["account_id"])
    assert acc_1["name"] == "Rewards Card"
    assert Decimal(str(acc_1["current_balance"])) == Decimal("150.75")
    assert acc_1["available_balance"] is None
    assert acc_1["type"] == "credit"

    # Verify PlaidItem in database
    db_item = db_session.query(models.PlaidItem).filter_by(plaid_item_id="plaid_item_test_001").first()
    assert db_item is not None
    assert db_item.transactions_cursor is None
    assert len(db_item.plaid_access_token_encrypted) > 0

    # Verify Accounts in database
    db_accounts = db_session.query(models.Account).filter_by(item_id=db_item.id).all()
    assert len(db_accounts) == 2


# ---------------------------------------------------------------------------
# 2. Happy Path: Re-Linking Existing Item (Idempotency)
# ---------------------------------------------------------------------------

def test_exchange_public_token_existing_item_reused(client, db_session):
    """
    When plaid_item_id already exists in DB, exchange_public_token reuses
    the existing PlaidItem without creating duplicate records or failing.
    """
    existing_item = create_plaid_item(db_session, plaid_item_id="plaid_item_existing", access_token="old-token")

    mock_exchange = _make_mock_exchange_response(
        access_token="new-token-123",
        item_id="plaid_item_existing",
    )
    mock_acct = _make_mock_account(
        account_id="plaid_act_existing",
        name="Existing Checking",
        current_balance=500.00,
    )
    mock_accounts_resp = _make_mock_accounts_response([mock_acct])

    with patch("backend.access.plaid_access.client.item_public_token_exchange", return_value=mock_exchange), \
         patch("backend.access.plaid_access.client.accounts_get", return_value=mock_accounts_resp):
        response = client.post("/plaid/exchange_public_token", json={"public_token": "public-sandbox-relink"})

    assert response.status_code == 200
    # PlaidItem count must remain 1
    items = db_session.query(models.PlaidItem).filter_by(plaid_item_id="plaid_item_existing").all()
    assert len(items) == 1
    assert items[0].id == existing_item.id


# ---------------------------------------------------------------------------
# 3. Payload Validation: Missing Field (422) vs. Empty String (500)
# ---------------------------------------------------------------------------

def test_exchange_public_token_missing_field_422(client):
    """
    POST /plaid/exchange_public_token with empty payload {} fails Pydantic validation -> 422.
    """
    response = client.post("/plaid/exchange_public_token", json={})
    assert response.status_code == 422


def test_exchange_public_token_empty_string_reaches_sdk_500(client):
    """
    POST /plaid/exchange_public_token with {"public_token": ""} passes Pydantic validation,
    reaches Plaid SDK, fails at Plaid SDK with ApiException, and returns HTTP 500.
    """
    exc = ApiException(status=400, reason="Bad Request")
    exc.body = '{"error_code": "INVALID_PUBLIC_TOKEN", "error_message": "public_token must be non-empty"}'

    with patch("backend.access.plaid_access.client.item_public_token_exchange", side_effect=exc):
        response = client.post("/plaid/exchange_public_token", json={"public_token": ""})

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert data["detail"] == str(exc)


# ---------------------------------------------------------------------------
# 4. Plaid Exchange API Failure (No Item or Account Persisted)
# ---------------------------------------------------------------------------

def test_exchange_public_token_exchange_failure_returns_500_no_db_changes(client, db_session):
    """
    When item_public_token_exchange raises ApiException:
    - Returns HTTP 500 with detail == str(exc).
    - No PlaidItem or Account records are created in DB.
    """
    exc = ApiException(status=400, reason="Bad Request")
    exc.body = '{"error_code": "INVALID_PUBLIC_TOKEN", "error_message": "provided token expired"}'

    with patch("backend.access.plaid_access.client.item_public_token_exchange", side_effect=exc):
        response = client.post("/plaid/exchange_public_token", json={"public_token": "expired-token"})

    assert response.status_code == 500
    assert response.json()["detail"] == str(exc)
    assert db_session.query(models.PlaidItem).count() == 0
    assert db_session.query(models.Account).count() == 0


# ---------------------------------------------------------------------------
# 5. Two-Commit & Orphan Semantics Preservation: Account Sync Failure
# ---------------------------------------------------------------------------

def test_exchange_public_token_account_sync_failure_preserves_orphan_item(client, db_session):
    """
    When token exchange succeeds (creating the new PlaidItem) but the subsequent
    accounts_get call fails:
    - Commit #1 already committed the PlaidItem to the database.
    - Commit #2 (accounts) never happens.
    - Router catches the Exception and returns HTTP 500 with detail == str(exc).
    - The orphaned PlaidItem remains committed in PostgreSQL (observable invariant).
    """
    mock_exchange = _make_mock_exchange_response(
        access_token="access-tok-orphan-test",
        item_id="plaid_item_orphan_test",
    )
    api_exc = ApiException(status=500, reason="Plaid Internal Error")
    api_exc.body = '{"error_code": "INTERNAL_SERVER_ERROR", "error_message": "Plaid service unavailable"}'

    with patch("backend.access.plaid_access.client.item_public_token_exchange", return_value=mock_exchange), \
         patch("backend.access.plaid_access.client.accounts_get", side_effect=api_exc):
        response = client.post("/plaid/exchange_public_token", json={"public_token": "valid-token-fails-at-sync"})

    assert response.status_code == 500
    assert response.json()["detail"] == str(api_exc)

    # Invariant: PlaidItem WAS committed (Commit #1) despite downstream failure
    db_item = db_session.query(models.PlaidItem).filter_by(plaid_item_id="plaid_item_orphan_test").first()
    assert db_item is not None

    # Invariant: Accounts were not committed
    assert db_session.query(models.Account).filter_by(item_id=db_item.id).count() == 0
