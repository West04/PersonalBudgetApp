"""
Characterization tests for Plaid Transaction Sync (POST /plaid/sync_transactions).
Freezes the existing legacy implementation behavior, error contracts,
ordering, transport protocols, and commit atomicity.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import re
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from plaid.exceptions import ApiException
import requests

from backend import models
from backend.crud.plaid import create_plaid_item
from backend.database import SessionLocal


# ---------------------------------------------------------------------------
# Test Helpers for Mocking Plaid API Responses
# ---------------------------------------------------------------------------

def _make_mock_account(
    account_id: str,
    name: str = "Plaid Checking",
    current_balance: float = 1000.0,
    available_balance: float = 950.0,
    iso_currency_code: str = "USD",
):
    """Constructs a mock Plaid SDK Account object for /accounts/get."""
    acct = MagicMock()
    acct.to_dict.return_value = {
        "account_id": account_id,
        "name": name,
        "mask": "1234",
        "type": "depository",
        "subtype": "checking",
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


def _setup_item_and_account(
    db_session,
    plaid_item_id: str = "item_tx_test",
    access_token: str = "test_access_token",
    plaid_account_id: str = "plaid_acc_default",
    cursor: str = None,
):
    """Creates and commits a PlaidItem and an associated Account in the test database."""
    item = create_plaid_item(db_session, plaid_item_id=plaid_item_id, access_token=access_token)
    if cursor is not None:
        item.transactions_cursor = cursor
        db_session.add(item)
        db_session.commit()

    account = models.Account(
        item_id=item.id,
        plaid_account_id=plaid_account_id,
        name="Test Account",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        available_balance=Decimal("950.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(item)
    db_session.refresh(account)
    return item, account


# ---------------------------------------------------------------------------
# 1. Identifier Contract & Precedence
# ---------------------------------------------------------------------------

def test_sync_transactions_missing_both_identifiers_400(client):
    """
    Verify POST /plaid/sync_transactions returns HTTP 400 with exact detail
    when neither item_id nor plaid_item_id is provided in the JSON body.
    """
    resp = client.post("/plaid/sync_transactions", json={})
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Must provide item_id or plaid_item_id"}


def test_sync_transactions_missing_item_by_uuid_404(client):
    """
    Verify POST /plaid/sync_transactions returns HTTP 404 when item_id UUID does not exist.
    """
    non_existent_uuid = str(uuid4())
    resp = client.post("/plaid/sync_transactions", json={"item_id": non_existent_uuid})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Plaid Item not found"}


def test_sync_transactions_missing_item_by_plaid_item_id_404(client):
    """
    Verify POST /plaid/sync_transactions returns HTTP 404 when plaid_item_id string does not exist.
    """
    resp = client.post("/plaid/sync_transactions", json={"plaid_item_id": "nonexistent_plaid_item_id"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Plaid Item not found"}


def test_sync_transactions_item_id_precedence_over_plaid_item_id(client, db_session):
    """
    Verify that when both item_id and plaid_item_id are supplied, item_id takes precedence:
    - Item Alpha has id_alpha and plaid_item_id="item_alpha" (access_token="token_alpha")
    - Item Beta has id_beta and plaid_item_id="item_beta" (access_token="token_beta")
    - Request sends item_id=id_alpha and plaid_item_id="item_beta"
    - Resulting sync uses Item Alpha's credentials for both /accounts/get and /transactions/sync.
    """
    item_alpha, _ = _setup_item_and_account(
        db_session,
        plaid_item_id="item_alpha",
        access_token="token_alpha",
        plaid_account_id="plaid_acc_alpha",
    )
    item_beta, _ = _setup_item_and_account(
        db_session,
        plaid_item_id="item_beta",
        access_token="token_beta",
        plaid_account_id="plaid_acc_beta",
    )

    mock_resp = _make_mock_accounts_response([])
    tx_page = {
        "added": [],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_alpha",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp) as mock_acct_get, \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp) as mock_tx_post:
        resp = client.post(
            "/plaid/sync_transactions",
            json={"item_id": str(item_alpha.id), "plaid_item_id": "item_beta"},
        )

    assert resp.status_code == 200
    # Verifies Item Alpha's access token was used for balance refresh
    assert mock_acct_get.call_args[0][0].access_token == "token_alpha"
    # Verifies Item Alpha's access token was used for transaction sync
    assert mock_tx_post.call_args[1]["json"]["access_token"] == "token_alpha"


def test_sync_transactions_invalid_item_id_no_fallback_to_valid_plaid_item_id_404(client, db_session):
    """
    Verify that when an invalid item_id is supplied alongside a valid plaid_item_id,
    the lookup does NOT fall back to plaid_item_id and returns HTTP 404.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="valid_plaid_item_id")

    resp = client.post(
        "/plaid/sync_transactions",
        json={"item_id": str(uuid4()), "plaid_item_id": "valid_plaid_item_id"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Plaid Item not found"}


# ---------------------------------------------------------------------------
# 2. Token Decoding Behavior
# ---------------------------------------------------------------------------

def test_sync_transactions_real_malformed_token_triggers_empty_token_behavior(client, db_session):
    """
    Characterize REAL decrypt_token behavior with malformed stored token:
    - decrypt_token catches the decode error internally and returns ""
    - sync_transactions does NOT raise HTTP 500 "Error decrypting access token"
    - Instead, AccountsGetRequest is constructed with access_token=""
    - Plaid /accounts/get then returns an ApiException (400 INVALID_ACCESS_TOKEN)
    - /transactions/sync is never called because balance refresh fails first.
    """
    item = models.PlaidItem(
        plaid_item_id="item_corrupt_tx",
        plaid_access_token_encrypted="!!!NOT_VALID_BASE64_PADDING!!!",
    )
    db_session.add(item)
    db_session.commit()

    api_exc = ApiException(status=400, reason="Bad Request")
    api_exc.body = '{"error_code": "INVALID_ACCESS_TOKEN", "error_message": "Provided access token is empty"}'

    with patch("backend.access.plaid_access.client.accounts_get", side_effect=api_exc) as mock_acct_get, \
         patch("backend.access.plaid_transaction_access.requests.post") as mock_tx_post:
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    # Balance refresh called with empty string access_token
    mock_acct_get.assert_called_once()
    assert mock_acct_get.call_args[0][0].access_token == ""
    # /transactions/sync was never invoked
    mock_tx_post.assert_not_called()
    # Response detail is from Plaid ApiException
    assert resp.status_code == 400
    assert resp.json() == {"detail": '{"error_code": "INVALID_ACCESS_TOKEN", "error_message": "Provided access token is empty"}'}


def test_sync_transactions_unhandled_decrypt_exception_500(client, db_session):
    """
    Characterize the Router's exception catch block when decrypt_token itself raises outward:
    - try: access_token = decrypt_token(...)
    - except Exception: raise HTTPException(500, "Error decrypting access token")
    - Neither /accounts/get nor /transactions/sync is called.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_decrypt_crash_tx")

    with patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", side_effect=RuntimeError("Cryptographic engine failed")), \
         patch("backend.access.plaid_access.client.accounts_get") as mock_acct_get, \
         patch("backend.access.plaid_transaction_access.requests.post") as mock_tx_post:
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Error decrypting access token"}
    mock_acct_get.assert_not_called()
    mock_tx_post.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Balance Refresh Coupling & Ordering
# ---------------------------------------------------------------------------

def test_sync_transactions_balance_refresh_precedes_tx_sync_and_ignores_count(client, db_session):
    """
    Verify that balance refresh strictly precedes transaction sync,
    and the count of updated accounts is completely omitted from the response.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_order_test")

    call_order = []

    def mock_accounts_get(req):
        call_order.append("accounts_get")
        mock_acct = _make_mock_account(account.plaid_account_id, current_balance=1234.56)
        return _make_mock_accounts_response([mock_acct])

    def mock_requests_post(url, **kwargs):
        call_order.append("transactions_sync")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "added": [],
            "modified": [],
            "removed": [],
            "has_more": False,
            "next_cursor": "cur_done",
        }
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    with patch("backend.access.plaid_access.client.accounts_get", side_effect=mock_accounts_get), \
         patch("backend.access.plaid_transaction_access.requests.post", side_effect=mock_requests_post):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    # Verification: balance refresh ran before transaction sync
    assert call_order == ["accounts_get", "transactions_sync"]

    # Public response contract has NO account count fields
    data = resp.json()
    assert data == {
        "message": "Sync successful",
        "added": 0,
        "modified": 0,
        "removed": 0,
        "next_cursor": "cur_done",
    }
    assert "accounts_updated" not in data


def test_sync_transactions_balance_refresh_failure_propagates_and_aborts_tx_sync(client, db_session):
    """
    Verify that if balance refresh fails with ApiException, the exception propagates
    with exact status and raw body, and /transactions/sync is never called.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_bal_fail")

    api_exc = ApiException(status=402, reason="Payment Required")
    api_exc.body = '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "User credentials revoked"}'

    with patch("backend.access.plaid_access.client.accounts_get", side_effect=api_exc), \
         patch("backend.access.plaid_transaction_access.requests.post") as mock_tx_post:
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 402
    assert resp.json() == {"detail": '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "User credentials revoked"}'}
    mock_tx_post.assert_not_called()


def test_sync_transactions_does_not_call_plaid_account_sync_manager(client, db_session):
    """
    Architectural invariant:
    sync_transactions currently calls legacy crud_plaid.sync_accounts_and_balances
    and does NOT call backend.managers.plaid_account_sync_manager.sync_plaid_accounts.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_no_manager")

    mock_resp = _make_mock_accounts_response([])
    tx_page = {"added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "c"}

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp), \
         patch("backend.managers.plaid_account_sync_manager.sync_plaid_accounts") as mock_account_sync_mgr:
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    mock_account_sync_mgr.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Cursor Request Payload & Transport Contract
# ---------------------------------------------------------------------------

def test_sync_transactions_initial_cursor_omitted_from_request(client, db_session):
    """
    Verify that when transactions_cursor is None (initial sync),
    the 'cursor' key is completely omitted from the JSON request payload.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_init_cur", cursor=None)

    mock_resp = _make_mock_accounts_response([])
    tx_page = {"added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "cur_initial_done"}

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp) as mock_post:
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    called_json = mock_post.call_args[1]["json"]
    assert "cursor" not in called_json
    assert called_json["count"] == 500
    assert called_json["access_token"] == "test_access_token"


def test_sync_transactions_empty_string_cursor_omitted_from_request(client, db_session):
    """
    Verify that when transactions_cursor is "" (empty string),
    the 'cursor' key is omitted because of the truthiness check in 'if cursor:'.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_empty_cur", cursor="")

    mock_resp = _make_mock_accounts_response([])
    tx_page = {"added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "cur_new"}

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp) as mock_post:
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    called_json = mock_post.call_args[1]["json"]
    assert "cursor" not in called_json


def test_sync_transactions_existing_cursor_sent_in_request(client, db_session):
    """
    Verify that when transactions_cursor has an existing value,
    'cursor' is passed in the JSON request payload with count=500.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_exist_cur", cursor="cursor_existing_123")

    mock_resp = _make_mock_accounts_response([])
    tx_page = {"added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "cur_next_456"}

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp) as mock_post:
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    called_json = mock_post.call_args[1]["json"]
    assert called_json["cursor"] == "cursor_existing_123"
    assert called_json["count"] == 500


def test_sync_transactions_raw_http_headers_and_timeout(client, db_session):
    """
    Verify the raw HTTP transport contract:
    POST to /transactions/sync with Content-Type, client credentials, and timeout=60.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_transport_test")

    mock_resp = _make_mock_accounts_response([])
    tx_page = {"added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "cur_tr"}

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp) as mock_post:
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    call_args, call_kwargs = mock_post.call_args
    assert "/transactions/sync" in call_args[0]
    assert call_kwargs["timeout"] == 60
    assert call_kwargs["headers"]["Content-Type"] == "application/json"
    assert "PLAID-CLIENT-ID" in call_kwargs["headers"]
    assert "PLAID-SECRET" in call_kwargs["headers"]


# ---------------------------------------------------------------------------
# 5. Success Response Contract & Multi-Page Pagination
# ---------------------------------------------------------------------------

def test_sync_transactions_single_page_success_response_contract(client, db_session):
    """
    Verify exact JSON response structure and count reporting for a single page.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_single_page")

    # Seed an existing transaction to be modified and one to be removed
    existing_mod = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_mod_1",
        description="Original Description",
        amount=Decimal("20.00"),
        date=date(2026, 6, 1),
        pending=True,
    )
    existing_del = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_del_1",
        description="To Delete",
        amount=Decimal("10.00"),
        date=date(2026, 6, 2),
        pending=False,
    )
    db_session.add_all([existing_mod, existing_del])
    db_session.commit()

    tx_page = {
        "added": [
            {
                "transaction_id": "tx_add_1",
                "account_id": account.plaid_account_id,
                "name": "Coffee Shop",
                "amount": 4.50,
                "date": "2026-06-15",
                "datetime": None,
                "pending": False,
            }
        ],
        "modified": [
            {
                "transaction_id": "tx_mod_1",
                "account_id": account.plaid_account_id,
                "name": "Updated Description",
                "amount": 25.00,
                "date": "2026-06-01",
                "datetime": None,
                "pending": False,
            }
        ],
        "removed": [{"transaction_id": "tx_del_1"}],
        "has_more": False,
        "next_cursor": "cursor_page_final",
    }

    mock_resp = _make_mock_accounts_response([])
    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json() == {
        "message": "Sync successful",
        "added": 1,
        "modified": 1,
        "removed": 1,
        "next_cursor": "cursor_page_final",
    }


def test_sync_transactions_multipage_pagination_and_cursor_progression(client, db_session):
    """
    Verify multi-page pagination loop:
    - Page 1 has has_more=True and next_cursor='cur_page_1'
    - Page 2 has has_more=False and next_cursor='cur_page_2'
    - Exactly two calls made to /transactions/sync
    - Second request passes cursor='cur_page_1'
    - Stored PlaidItem.transactions_cursor becomes 'cur_page_2'
    - Aggregated counts across pages are returned
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_multipage")

    page_1 = {
        "added": [
            {
                "transaction_id": "tx_p1_1",
                "account_id": account.plaid_account_id,
                "name": "P1 Tx",
                "amount": 10.0,
                "date": "2026-06-10",
                "pending": False,
            }
        ],
        "modified": [],
        "removed": [],
        "has_more": True,
        "next_cursor": "cur_page_1",
    }
    page_2 = {
        "added": [
            {
                "transaction_id": "tx_p2_1",
                "account_id": account.plaid_account_id,
                "name": "P2 Tx",
                "amount": 20.0,
                "date": "2026-06-11",
                "pending": False,
            }
        ],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_page_2",
    }

    mock_http_resp_1 = MagicMock()
    mock_http_resp_1.json.return_value = page_1
    mock_http_resp_1.raise_for_status.return_value = None

    mock_http_resp_2 = MagicMock()
    mock_http_resp_2.json.return_value = page_2
    mock_http_resp_2.raise_for_status.return_value = None

    mock_resp = _make_mock_accounts_response([])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", side_effect=[mock_http_resp_1, mock_http_resp_2]) as mock_post:
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert mock_post.call_count == 2
    # First page had no cursor
    assert "cursor" not in mock_post.call_args_list[0][1]["json"]
    # Second page passed next_cursor from page 1
    assert mock_post.call_args_list[1][1]["json"]["cursor"] == "cur_page_1"

    # Aggregated counts
    assert resp.json() == {
        "message": "Sync successful",
        "added": 2,
        "modified": 0,
        "removed": 0,
        "next_cursor": "cur_page_2",
    }

    # Stored cursor in DB is cur_page_2
    db_session.refresh(item)
    assert item.transactions_cursor == "cur_page_2"


# ---------------------------------------------------------------------------
# 6. Atomicity, Commit Piggybacking, and Partial-Commit Failures
# ---------------------------------------------------------------------------

def test_sync_transactions_multipage_partial_commit_failure_preserves_initial_cursor(client, db_session):
    """
    MANDATORY STRUCTURAL INVARIANT:
    In a 3-page sync where Page 1 and Page 2 succeed but Page 3 fails:
    - Page 1 and Page 2 mutations ARE committed in PostgreSQL
    - PlaidItem.transactions_cursor is NOT updated (retains its initial value)
    Verified through a fresh independent database session.
    """
    item, account = _setup_item_and_account(
        db_session,
        plaid_item_id="item_partial_fail",
        cursor="initial_cursor_000",
    )

    page_1 = {
        "added": [
            {
                "transaction_id": "tx_page1_committed",
                "account_id": account.plaid_account_id,
                "name": "Page 1 Item",
                "amount": 10.0,
                "date": "2026-06-01",
                "pending": False,
            }
        ],
        "modified": [],
        "removed": [],
        "has_more": True,
        "next_cursor": "cursor_after_page_1",
    }
    page_2 = {
        "added": [
            {
                "transaction_id": "tx_page2_committed",
                "account_id": account.plaid_account_id,
                "name": "Page 2 Item",
                "amount": 20.0,
                "date": "2026-06-02",
                "pending": False,
            }
        ],
        "modified": [],
        "removed": [],
        "has_more": True,
        "next_cursor": "cursor_after_page_2",
    }

    mock_http_resp_1 = MagicMock()
    mock_http_resp_1.json.return_value = page_1
    mock_http_resp_1.raise_for_status.return_value = None

    mock_http_resp_2 = MagicMock()
    mock_http_resp_2.json.return_value = page_2
    mock_http_resp_2.raise_for_status.return_value = None

    mock_error_resp = MagicMock()
    mock_error_resp.status_code = 502
    mock_error_resp.text = '{"error_code": "PLANNED_MAINTENANCE"}'
    page_3_error = requests.exceptions.HTTPError(response=mock_error_resp)

    mock_resp = _make_mock_accounts_response([])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", side_effect=[mock_http_resp_1, mock_http_resp_2, page_3_error]):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    # Request fails with HTTP 502
    assert resp.status_code == 502
    assert resp.json() == {"detail": 'Plaid Sync Error: {"error_code": "PLANNED_MAINTENANCE"}'}

    # Verify through a fresh independent session
    independent_session = SessionLocal()
    try:
        # Page 1 transaction IS committed
        tx1 = independent_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_page1_committed").first()
        assert tx1 is not None

        # Page 2 transaction IS committed
        tx2 = independent_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_page2_committed").first()
        assert tx2 is not None

        # Cursor was NOT updated (still initial_cursor_000)
        db_item = independent_session.query(models.PlaidItem).filter_by(id=item.id).first()
        assert db_item.transactions_cursor == "initial_cursor_000"
    finally:
        independent_session.close()


def test_sync_transactions_balance_refresh_commit_piggybacks_on_first_tx_commit(client, db_session):
    """
    Verify commit piggybacking:
    - sync_accounts_and_balances stages Account balance update and calls db.flush() (NO commit).
    - First transaction processed in sync_transactions_from_plaid executes db.commit().
    - In an independent session, the Account balance update is committed simultaneously with that first transaction.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_piggyback")

    # Plaid balance refresh returns balance = 4500.00
    mock_acct = _make_mock_account(account.plaid_account_id, current_balance=4500.00)
    mock_accounts_resp = _make_mock_accounts_response([mock_acct])

    tx_page = {
        "added": [
            {
                "transaction_id": "tx_piggyback_trigger",
                "account_id": account.plaid_account_id,
                "name": "Trigger Commit",
                "amount": 50.0,
                "date": "2026-06-01",
                "pending": False,
            }
        ],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_pb",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_accounts_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    independent_session = SessionLocal()
    try:
        db_acct = independent_session.query(models.Account).filter_by(id=account.id).first()
        assert db_acct.current_balance == Decimal("4500.00")
        db_tx = independent_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_piggyback_trigger").first()
        assert db_tx is not None
    finally:
        independent_session.close()


def test_sync_transactions_balance_refresh_zero_events_commits_via_cursor_commit(client, db_session):
    """
    Verify commit behavior when there are 0 transaction events:
    - Balance refresh changes Account balance (db.flush() only)
    - Zero transactions processed (no per-transaction commits happen)
    - update_transactions_cursor executes db.commit()
    - Account balance update is successfully committed in PostgreSQL.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_zero_events")

    mock_acct = _make_mock_account(account.plaid_account_id, current_balance=3333.33)
    mock_accounts_resp = _make_mock_accounts_response([mock_acct])

    tx_page = {
        "added": [],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_zero_tx",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_accounts_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    independent_session = SessionLocal()
    try:
        db_acct = independent_session.query(models.Account).filter_by(id=account.id).first()
        assert db_acct.current_balance == Decimal("3333.33")
        db_item = independent_session.query(models.PlaidItem).filter_by(id=item.id).first()
        assert db_item.transactions_cursor == "cur_zero_tx"
    finally:
        independent_session.close()


def test_sync_transactions_failure_before_first_tx_rolls_back_balance_refresh(client, db_session):
    """
    Verify failure before any transaction commit:
    - Balance refresh succeeds and flushes balance=9999.00
    - First call to /transactions/sync fails immediately with HTTPError
    - In an independent session, the flushed balance change was NEVER committed.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_fail_before_tx")
    original_balance = account.current_balance  # 1000.00

    mock_acct = _make_mock_account(account.plaid_account_id, current_balance=9999.00)
    mock_accounts_resp = _make_mock_accounts_response([mock_acct])

    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 500
    mock_err_resp.text = "Internal Plaid Error"
    tx_error = requests.exceptions.HTTPError(response=mock_err_resp)

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_accounts_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", side_effect=tx_error):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 500

    independent_session = SessionLocal()
    try:
        db_acct = independent_session.query(models.Account).filter_by(id=account.id).first()
        # Remains original balance; flushed change was rolled back on session teardown
        assert db_acct.current_balance == original_balance
    finally:
        independent_session.close()


def test_sync_transactions_per_event_commit_failure_preserves_earlier_commits(client, db_session):
    """
    Verify per-event commit isolation within a single page:
    - Added transaction 1 is valid and committed.
    - Added transaction 2 references a missing account_id and raises an exception.
    - In an independent session, transaction 1 remains committed!
    - PlaidItem.transactions_cursor remains unadvanced.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_per_event_commit")

    tx_page = {
        "added": [
            {
                "transaction_id": "tx_first_ok",
                "account_id": account.plaid_account_id,
                "name": "First Valid Tx",
                "amount": 10.0,
                "date": "2026-06-01",
                "pending": False,
            },
            {
                "transaction_id": "tx_second_bad",
                "account_id": "nonexistent_account_xyz",
                "name": "Failing Account Tx",
                "amount": 20.0,
                "date": "2026-06-02",
                "pending": False,
            },
        ],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_should_not_save",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    mock_resp = _make_mock_accounts_response([])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    # Fails with HTTP 500 because account nonexistent_account_xyz was not found
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Account nonexistent_account_xyz not found in database."}

    # Independent session check
    independent_session = SessionLocal()
    try:
        # First transaction WAS committed
        tx1 = independent_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_first_ok").first()
        assert tx1 is not None

        # Second transaction was NOT committed
        tx2 = independent_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_second_bad").first()
        assert tx2 is None

        # Cursor was NOT updated
        db_item = independent_session.query(models.PlaidItem).filter_by(id=item.id).first()
        assert db_item.transactions_cursor != "cur_should_not_save"
    finally:
        independent_session.close()


# ---------------------------------------------------------------------------
# 7. Added Event Invariants & Amount Sign Negation
# ---------------------------------------------------------------------------

def test_sync_transactions_added_new_row_fields_and_sign_inversion(client, db_session):
    """
    Verify complete field mapping for newly added transactions,
    including exact sign negation:
    - Plaid positive 35.00 -> local -35.00
    - Plaid negative -5.50 -> local 5.50
    - Plaid zero 0.0 -> local 0.00
    - category_id = None
    - is_transfer = False
    - description = tx_data['name']
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_signs")

    tx_page = {
        "added": [
            {
                "transaction_id": "tx_pos_plaid",
                "account_id": account.plaid_account_id,
                "name": "Grocery Store Charge",
                "amount": 35.00,  # Plaid positive -> local negative -35.00
                "date": "2026-06-15",
                "datetime": None,
                "pending": True,
            },
            {
                "transaction_id": "tx_neg_plaid",
                "account_id": account.plaid_account_id,
                "name": "Paycheck Deposit",
                "amount": -5.50,  # Plaid negative -> local positive 5.50
                "date": "2026-06-16",
                "datetime": None,
                "pending": False,
            },
            {
                "transaction_id": "tx_zero_plaid",
                "account_id": account.plaid_account_id,
                "name": "Zero Auth",
                "amount": 0.0,
                "date": "2026-06-17",
                "datetime": None,
                "pending": False,
            },
        ],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_signs",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    # 1. Grocery charge
    tx1 = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_pos_plaid").first()
    assert tx1 is not None
    assert tx1.account_id == account.id
    assert tx1.category_id is None
    assert tx1.is_transfer is False
    assert tx1.description == "Grocery Store Charge"
    assert tx1.amount == Decimal("-35.00")
    assert tx1.date == date(2026, 6, 15)
    assert tx1.datetime is None
    assert tx1.pending is True

    # 2. Deposit
    tx2 = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_neg_plaid").first()
    assert tx2 is not None
    assert tx2.amount == Decimal("5.50")
    assert tx2.datetime is None
    assert tx2.pending is False

    # 3. Zero auth
    tx3 = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_zero_plaid").first()
    assert tx3 is not None
    assert tx3.amount == Decimal("0.00")


def test_sync_transactions_added_new_row_non_null_datetime_string_fails_due_to_pydantic_schema_defect(client, db_session):
    """
    Characterize known defect / quirk:
    In backend/schemas.py, TransactionCreate defines 'datetime: Optional[datetime] = None'.
    Because of a Python scope name-collision with the imported datetime type,
    the annotation evaluates to NoneType.
    Consequently, any newly added transaction from Plaid with a non-null datetime string
    fails Pydantic validation when creating TransactionCreate, bubbling up to HTTP 500.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_dt_defect")

    tx_page = {
        "added": [
            {
                "transaction_id": "tx_with_datetime_str",
                "account_id": account.plaid_account_id,
                "name": "Datetime Str Charge",
                "amount": 10.00,
                "date": "2026-06-15",
                "datetime": "2026-06-15T10:30:00Z",
                "pending": False,
            }
        ],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_dt",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    assert "Input should be None" in resp.json()["detail"]


def test_sync_transactions_added_event_existing_id_updates_and_preserves_category_transfer(client, db_session):
    """
    Verify that if an 'added' event contains a plaid_transaction_id that already exists locally:
    - Existing row is updated in place, NOT duplicated
    - Existing category_id and is_transfer are strictly preserved
    - added count still increments
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_add_existing")

    # Create dummy category
    group = models.CategoryGroup(name="Existing Group")
    db_session.add(group)
    db_session.flush()
    cat = models.Category(name="Preserved Cat", group_id=group.category_group_id)
    db_session.add(cat)
    db_session.flush()

    existing = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_add_collision",
        description="Old Name",
        amount=Decimal("10.00"),
        date=date(2026, 6, 1),
        category_id=cat.category_id,
        is_transfer=True,
    )
    db_session.add(existing)
    db_session.commit()

    tx_page = {
        "added": [
            {
                "transaction_id": "tx_add_collision",
                "account_id": account.plaid_account_id,
                "name": "New Name from Added",
                "amount": 25.00,
                "date": "2026-06-05",
                "pending": False,
            }
        ],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_collision",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json()["added"] == 1

    # Exactly 1 row in DB (not duplicated)
    rows = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_add_collision").all()
    assert len(rows) == 1
    updated = rows[0]
    assert updated.description == "New Name from Added"
    assert updated.amount == Decimal("-25.00")
    # Preserved user fields
    assert updated.category_id == cat.category_id
    assert updated.is_transfer is True


# ---------------------------------------------------------------------------
# 8. Modified Event Invariants & Edge Cases
# ---------------------------------------------------------------------------

def test_sync_transactions_modified_existing_row_updates_and_preserves_user_fields(client, db_session):
    """
    Verify that a 'modified' event updates mutable fields while preserving:
    - transaction_id (PK)
    - account_id
    - category_id
    - is_transfer
    - plaid_transaction_id
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_mod_test")

    group = models.CategoryGroup(name="Mod Group")
    db_session.add(group)
    db_session.flush()
    cat = models.Category(name="Dining", group_id=group.category_group_id)
    db_session.add(cat)
    db_session.flush()

    original_tx = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_to_mod",
        description="Old Restaurant",
        amount=Decimal("-40.00"),
        date=date(2026, 6, 1),
        category_id=cat.category_id,
        is_transfer=True,
        pending=True,
    )
    db_session.add(original_tx)
    db_session.commit()
    orig_pk = original_tx.transaction_id

    tx_page = {
        "added": [],
        "modified": [
            {
                "transaction_id": "tx_to_mod",
                "account_id": account.plaid_account_id,
                "name": "New Restaurant Final",
                "amount": -50.00,  # Inverts to +50.00
                "date": "2026-06-03",
                "datetime": "2026-06-03T18:00:00Z",
                "pending": False,
            }
        ],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_mod",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json()["modified"] == 1

    db_session.refresh(original_tx)
    assert original_tx.transaction_id == orig_pk
    assert original_tx.account_id == account.id
    assert original_tx.category_id == cat.category_id
    assert original_tx.is_transfer is True
    assert original_tx.description == "New Restaurant Final"
    assert original_tx.amount == Decimal("50.00")
    assert original_tx.date == date(2026, 6, 3)
    assert original_tx.pending is False


def test_sync_transactions_modified_changed_account_id_preserves_original_account_id(client, db_session):
    """
    Characterize edge case:
    When a modified event arrives with a DIFFERENT remote account_id (Account B),
    the existing transaction's account_id remains Account A in PostgreSQL.
    """
    item, account_a = _setup_item_and_account(
        db_session,
        plaid_item_id="item_acct_change",
        plaid_account_id="plaid_acct_a",
    )
    account_b = models.Account(
        item_id=item.id,
        plaid_account_id="plaid_acct_b",
        name="Account B",
        type="depository",
        subtype="savings",
        current_balance=Decimal("2000.00"),
    )
    db_session.add(account_b)
    db_session.commit()

    tx = models.Transaction(
        account_id=account_a.id,
        plaid_transaction_id="tx_acct_switch",
        description="Merchant",
        amount=Decimal("10.00"),
        date=date(2026, 6, 1),
    )
    db_session.add(tx)
    db_session.commit()

    # Remote payload says transaction now belongs to plaid_acct_b
    tx_page = {
        "added": [],
        "modified": [
            {
                "transaction_id": "tx_acct_switch",
                "account_id": "plaid_acct_b",
                "name": "Merchant Updated",
                "amount": 10.0,
                "date": "2026-06-01",
                "pending": False,
            }
        ],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_sw",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    db_session.refresh(tx)
    # Stays linked to Account A!
    assert tx.account_id == account_a.id


def test_sync_transactions_modified_missing_account_id_raises_500(client, db_session):
    """
    Characterize edge case:
    Because create_or_update_transaction looks up the remote account_id unconditionally,
    a modified event with an unknown account_id raises an Exception -> HTTP 500,
    even though the existing transaction already has a valid account_id.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_mod_missing_acct")

    tx = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_mod_bad_acct",
        description="Merchant",
        amount=Decimal("10.00"),
        date=date(2026, 6, 1),
    )
    db_session.add(tx)
    db_session.commit()

    tx_page = {
        "added": [],
        "modified": [
            {
                "transaction_id": "tx_mod_bad_acct",
                "account_id": "completely_unknown_account_id",
                "name": "Merchant",
                "amount": 10.0,
                "date": "2026-06-01",
                "pending": False,
            }
        ],
        "removed": [],
        "has_more": False,
        "next_cursor": "c",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Account completely_unknown_account_id not found in database."}


def test_sync_transactions_modified_missing_transaction_creates_new_row(client, db_session):
    """
    Verify that if a transaction arrives in 'modified' but does NOT exist in PostgreSQL,
    create_or_update_transaction inserts it as a new row (category_id=None, is_transfer=False),
    while the response increments 'modified' (not 'added').
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_mod_unseen")

    tx_page = {
        "added": [],
        "modified": [
            {
                "transaction_id": "tx_unseen_in_modified",
                "account_id": account.plaid_account_id,
                "name": "Brand New via Modified",
                "amount": 15.00,
                "date": "2026-06-08",
                "pending": False,
            }
        ],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_mod_unseen",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json() == {
        "message": "Sync successful",
        "added": 0,
        "modified": 1,
        "removed": 0,
        "next_cursor": "cur_mod_unseen",
    }

    new_tx = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_unseen_in_modified").first()
    assert new_tx is not None
    assert new_tx.description == "Brand New via Modified"
    assert new_tx.amount == Decimal("-15.00")
    assert new_tx.category_id is None
    assert new_tx.is_transfer is False


# ---------------------------------------------------------------------------
# 9. Removed Event Invariants
# ---------------------------------------------------------------------------

def test_sync_transactions_removed_existing_transaction_physically_deleted(client, db_session):
    """
    Verify that an existing transaction in 'removed' is physically deleted from PostgreSQL.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_rem_phys")

    tx = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_to_delete",
        description="Will Be Deleted",
        amount=Decimal("10.00"),
        date=date(2026, 6, 1),
    )
    db_session.add(tx)
    db_session.commit()

    tx_page = {
        "added": [],
        "modified": [],
        "removed": [{"transaction_id": "tx_to_delete"}],
        "has_more": False,
        "next_cursor": "cur_del",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json()["removed"] == 1

    # Confirmed deleted in DB
    independent_session = SessionLocal()
    try:
        assert independent_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_to_delete").first() is None
    finally:
        independent_session.close()


def test_sync_transactions_removed_missing_transaction_ignored_count_increments(client, db_session):
    """
    Verify that removing a transaction ID that does not exist in PostgreSQL:
    - Produces no error
    - Increments 'removed' count anyway
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_rem_none")

    tx_page = {
        "added": [],
        "modified": [],
        "removed": [{"transaction_id": "tx_not_in_db_at_all"}],
        "has_more": False,
        "next_cursor": "cur_rem_none",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json() == {
        "message": "Sync successful",
        "added": 0,
        "modified": 0,
        "removed": 1,
        "next_cursor": "cur_rem_none",
    }


# ---------------------------------------------------------------------------
# 10. Event Processing Order & Count Semantics
# ---------------------------------------------------------------------------

def test_sync_transactions_event_processing_order_added_then_modified_then_removed(client, db_session):
    """
    Verify within-page processing order:
    added -> modified -> removed.
    If the same transaction_id appears in added and then removed:
    - added stages/commits the insert
    - removed deletes it
    - Final DB state: row does not exist.
    """
    item, account = _setup_item_and_account(db_session, plaid_item_id="item_lifecycle_order")

    tx_page = {
        "added": [
            {
                "transaction_id": "tx_same_page_lifecycle",
                "account_id": account.plaid_account_id,
                "name": "Created on Page",
                "amount": 12.00,
                "date": "2026-06-01",
                "pending": False,
            }
        ],
        "modified": [
            {
                "transaction_id": "tx_same_page_lifecycle",
                "account_id": account.plaid_account_id,
                "name": "Modified on Page",
                "amount": 15.00,
                "date": "2026-06-01",
                "pending": False,
            }
        ],
        "removed": [
            {
                "transaction_id": "tx_same_page_lifecycle",
            }
        ],
        "has_more": False,
        "next_cursor": "cur_order",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json() == {
        "message": "Sync successful",
        "added": 1,
        "modified": 1,
        "removed": 1,
        "next_cursor": "cur_order",
    }

    # Final DB state: deleted
    assert db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_same_page_lifecycle").first() is None


# ---------------------------------------------------------------------------
# 11. Error Mapping (Plaid HTTPError, Network, Missing Account)
# ---------------------------------------------------------------------------

def test_sync_transactions_plaid_http_error_prefixed_detail(client, db_session):
    """
    Verify that an HTTPError raised by requests.post:
    - Propagates with exact HTTP status code
    - Detail contains the 'Plaid Sync Error: ' prefix followed by response text.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_http_err")

    mock_error_resp = MagicMock()
    mock_error_resp.status_code = 400
    mock_error_resp.text = '{"error_code": "INVALID_ACCESS_TOKEN", "error_message": "Provided access token is invalid"}'
    tx_error = requests.exceptions.HTTPError(response=mock_error_resp)

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", side_effect=tx_error):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 400
    assert resp.json() == {"detail": 'Plaid Sync Error: {"error_code": "INVALID_ACCESS_TOKEN", "error_message": "Provided access token is invalid"}'}


def test_sync_transactions_generic_network_error_500(client, db_session):
    """
    Verify that an unexpected network/connection error from requests:
    - Propagates as HTTP 500
    - Detail contains str(exception)
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_net_err")

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", side_effect=requests.exceptions.ConnectionError("DNS resolution failed")):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "DNS resolution failed"}


def test_sync_transactions_missing_local_account_500(client, db_session):
    """
    Verify that an added transaction referencing an unknown remote account_id
    raises an Exception caught as HTTP 500 with exact detail.
    """
    item, _ = _setup_item_and_account(db_session, plaid_item_id="item_missing_acct")

    tx_page = {
        "added": [
            {
                "transaction_id": "tx_orphan",
                "account_id": "ghost_account_id",
                "name": "Ghost Merchant",
                "amount": 10.0,
                "date": "2026-06-01",
                "pending": False,
            }
        ],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "c",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_make_mock_accounts_response([])), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Account ghost_account_id not found in database."}
