"""
Unit tests for Plaid External ResourceAccess (backend/access/plaid_access.py).
Mocks the Plaid SDK completely.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from plaid.exceptions import ApiException

from backend.access.plaid_access import (
    PlaidAccountSnapshot,
    PlaidAccessError,
    fetch_accounts_for_token,
)


def _make_mock_response(accounts_data):
    resp = MagicMock()
    mock_accounts = []
    for data in accounts_data:
        acct = MagicMock()
        acct.to_dict.return_value = data
        mock_accounts.append(acct)
    resp.accounts = mock_accounts
    return resp


def test_accounts_get_request_receives_exact_access_token():
    mock_resp = _make_mock_response([])
    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp) as mock_get:
        snapshots = fetch_accounts_for_token("custom_access_token_123")

    mock_get.assert_called_once()
    called_request = mock_get.call_args[0][0]
    assert called_request.access_token == "custom_access_token_123"
    assert snapshots == []


def test_remote_account_maps_into_plaid_account_snapshot():
    raw_account = {
        "account_id": "acc_001",
        "name": "Checking Account",
        "mask": "1234",
        "type": "depository",
        "subtype": "checking",
        "balances": {
            "current": 1250.50,
            "available": 1200.00,
            "iso_currency_code": "USD",
        },
    }
    mock_resp = _make_mock_response([raw_account])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        snapshots = fetch_accounts_for_token("token_abc")

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert isinstance(snapshot, PlaidAccountSnapshot)
    assert snapshot.account_id == "acc_001"
    assert snapshot.name == "Checking Account"
    assert snapshot.mask == "1234"
    assert snapshot.account_type == "depository"
    assert snapshot.subtype == "checking"
    assert snapshot.current_balance == Decimal("1250.50")
    assert snapshot.available_balance == Decimal("1200.00")
    assert snapshot.currency == "USD"


def test_balance_current_and_none_fallbacks():
    raw_account = {
        "account_id": "acc_none_bal",
        "name": "Test Account",
        "mask": None,
        "type": "depository",
        "subtype": None,
        "balances": {
            "current": None,    # None current -> Decimal("0")
            "available": None,  # None available remains None
            "iso_currency_code": None,  # Missing currency -> "USD"
        },
    }
    mock_resp = _make_mock_response([raw_account])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        snapshots = fetch_accounts_for_token("token_abc")

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.current_balance == Decimal("0")
    assert snapshot.available_balance is None
    assert snapshot.currency == "USD"


def test_no_sign_inversion():
    """
    Positive values from Plaid remain positive Decimal numbers in snapshots.
    """
    raw_account = {
        "account_id": "acc_sign",
        "name": "Credit Card",
        "mask": "9999",
        "type": "credit",
        "subtype": "credit card",
        "balances": {
            "current": 540.25,
            "available": 1459.75,
            "iso_currency_code": "USD",
        },
    }
    mock_resp = _make_mock_response([raw_account])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        snapshots = fetch_accounts_for_token("token_abc")

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.current_balance == Decimal("540.25")
    assert snapshot.available_balance == Decimal("1459.75")


def test_falsy_name_and_type_remain_distinguishable():
    """
    Empty strings and None values for name and type must not be eagerly converted to 'Account' or 'unknown'.
    """
    raw_account = {
        "account_id": "acc_falsy",
        "name": "",
        "mask": None,
        "type": None,
        "subtype": None,
        "balances": {
            "current": 10.0,
            "available": None,
            "iso_currency_code": "USD",
        },
    }
    mock_resp = _make_mock_response([raw_account])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        snapshots = fetch_accounts_for_token("token_abc")

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.name == ""
    assert snapshot.account_type is None


def test_api_exception_maps_to_plaid_access_error():
    exc = ApiException(status=401, reason="Unauthorized")
    exc.body = '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "Credentials revoked"}'

    with patch("backend.access.plaid_access.client.accounts_get", side_effect=exc):
        with pytest.raises(PlaidAccessError) as exc_info:
            fetch_accounts_for_token("bad_token")

    err = exc_info.value
    assert err.status_code == 401
    assert err.detail == '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "Credentials revoked"}'


def test_generic_external_exception_maps_to_500_plaid_access_error():
    with patch("backend.access.plaid_access.client.accounts_get", side_effect=TimeoutError("Plaid socket timeout")):
        with pytest.raises(PlaidAccessError) as exc_info:
            fetch_accounts_for_token("token_timeout")

    err = exc_info.value
    assert err.status_code == 500
    assert err.detail == "Plaid socket timeout"
