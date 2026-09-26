"""
Unit tests for Plaid External ResourceAccess (backend/access/plaid_access.py).
Mocks the Plaid SDK completely.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from plaid.exceptions import ApiException
from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from backend.access.plaid_access import (
    PlaidAccountSnapshot,
    PlaidAccessError,
    fetch_accounts_for_token,
    create_link_token,
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


# ---------------------------------------------------------------------------
# create_link_token ResourceAccess Tests
# ---------------------------------------------------------------------------

def test_create_link_token_request_construction():
    """
    Verifies the Accessor constructs LinkTokenCreateRequest with exact
    constants: client_user_id, client_name, products, country_codes, language,
    and that optional fields are None.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = "link-test-token"

    with patch("backend.access.plaid_access.client.link_token_create", return_value=mock_resp) as mock_create:
        token = create_link_token()

    mock_create.assert_called_once()
    request = mock_create.call_args[0][0]
    assert isinstance(request, LinkTokenCreateRequest)

    # user: LinkTokenCreateRequestUser(client_user_id="static-user-id-for-now")
    assert isinstance(request.user, LinkTokenCreateRequestUser)
    assert request.user.client_user_id == "static-user-id-for-now"

    # client_name: "My Personal Budget App"
    assert request.client_name == "My Personal Budget App"

    # products: [Products("transactions")]
    assert request.products == [Products("transactions")]
    assert len(request.products) == 1
    assert isinstance(request.products[0], Products)
    assert request.products[0].value == "transactions"

    # country_codes: [CountryCode("US")]
    assert request.country_codes == [CountryCode("US")]
    assert len(request.country_codes) == 1
    assert isinstance(request.country_codes[0], CountryCode)
    assert request.country_codes[0].value == "US"

    # language: "en"
    assert request.language == "en"

    # Verify optional fields remain unsupplied
    assert getattr(request, "redirect_uri", None) is None
    assert getattr(request, "webhook", None) is None
    assert getattr(request, "account_filters", None) is None
    assert getattr(request, "access_token", None) is None


def test_create_link_token_success_extraction():
    """
    Verifies that the Accessor extracts response.link_token and returns only the token string.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = "link-sandbox-test-token-123"

    with patch("backend.access.plaid_access.client.link_token_create", return_value=mock_resp):
        token = create_link_token()

    assert token == "link-sandbox-test-token-123"


def test_create_link_token_empty_string_returned_unchanged():
    """
    Verifies that an empty string link_token is returned unchanged without failing truthiness checks.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = ""

    with patch("backend.access.plaid_access.client.link_token_create", return_value=mock_resp):
        token = create_link_token()

    assert token == ""


def test_create_link_token_none_returned_unchanged_for_presentation_validation():
    """
    Verifies that None is returned as-is by the Accessor, leaving Presentation response
    validation to handle/reject it.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = None

    with patch("backend.access.plaid_access.client.link_token_create", return_value=mock_resp):
        token = create_link_token()

    assert token is None


def test_create_link_token_api_exception_normalized_to_500_plaid_access_error():
    """
    Verifies Plaid ApiException is normalized to PlaidAccessError with status_code=500
    and detail=str(exc).
    """
    exc = ApiException(status=400, reason="Bad Request")
    exc.body = '{"error_code": "INVALID_FIELD"}'

    with patch("backend.access.plaid_access.client.link_token_create", side_effect=exc):
        with pytest.raises(PlaidAccessError) as exc_info:
            create_link_token()

    err = exc_info.value
    assert err.status_code == 500
    assert err.detail == str(exc)
    assert "Status Code: 400" in err.detail


def test_create_link_token_runtime_error_normalized_to_500_plaid_access_error():
    """
    Verifies generic non-Plaid exception is normalized to PlaidAccessError with status_code=500
    and detail=str(exc).
    """
    with patch("backend.access.plaid_access.client.link_token_create", side_effect=RuntimeError("Network failure")):
        with pytest.raises(PlaidAccessError) as exc_info:
            create_link_token()

    err = exc_info.value
    assert err.status_code == 500
    assert err.detail == "Network failure"


def test_create_link_token_missing_link_token_attribute_raises_plaid_access_error():
    """
    Verifies that when response lacks link_token attribute, the resulting AttributeError
    is normalized to PlaidAccessError with status_code=500 preserving the attribute error detail.
    """
    mock_resp = object()  # plain object without link_token attribute

    with patch("backend.access.plaid_access.client.link_token_create", return_value=mock_resp):
        with pytest.raises(PlaidAccessError) as exc_info:
            create_link_token()

    err = exc_info.value
    assert err.status_code == 500
    assert "'object' object has no attribute 'link_token'" in err.detail

