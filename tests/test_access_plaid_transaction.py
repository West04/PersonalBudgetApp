"""
Focused unit tests for PlaidTransactionAccess (backend/access/plaid_transaction_access.py).
Verifies HTTP contract, environment resolution, headers, payload, pagination adaptation,
and transport error translation without real network calls.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from backend.access import plaid_transaction_access
from backend.access.plaid_transaction_access import (
    PlaidTransactionHttpError,
    PlaidTransactionNetworkError,
    PlaidTransactionPage,
    fetch_transactions_page,
)


def _make_dummy_response(
    added=None,
    modified=None,
    removed=None,
    next_cursor="cur_next",
    has_more=False,
):
    resp = MagicMock()
    resp.json.return_value = {
        "added": added or [],
        "modified": modified or [],
        "removed": removed or [],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_transactions_page_omits_cursor_when_none():
    mock_resp = _make_dummy_response()
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_123", cursor=None)

    payload = mock_post.call_args[1]["json"]
    assert "cursor" not in payload
    assert payload["access_token"] == "tok_123"


def test_fetch_transactions_page_omits_cursor_when_empty_string():
    mock_resp = _make_dummy_response()
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_123", cursor="")

    payload = mock_post.call_args[1]["json"]
    assert "cursor" not in payload


def test_fetch_transactions_page_includes_cursor_when_truthy():
    mock_resp = _make_dummy_response()
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_123", cursor="cur_old_456")

    payload = mock_post.call_args[1]["json"]
    assert payload["cursor"] == "cur_old_456"


def test_fetch_transactions_page_count_is_500():
    mock_resp = _make_dummy_response()
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_123")

    payload = mock_post.call_args[1]["json"]
    assert payload["count"] == 500


def test_fetch_transactions_page_timeout_is_60():
    mock_resp = _make_dummy_response()
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_123")

    timeout = mock_post.call_args[1]["timeout"]
    assert timeout == 60


def test_fetch_transactions_page_base_url_resolution(monkeypatch):
    mock_resp = _make_dummy_response()

    # 1. Sandbox
    monkeypatch.setenv("PLAID_ENVIRONMENT", "Sandbox")
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_test")
        assert mock_post.call_args[0][0] == "https://sandbox.plaid.com/transactions/sync"

    # 2. Development
    monkeypatch.setenv("PLAID_ENVIRONMENT", "Development")
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_test")
        assert mock_post.call_args[0][0] == "https://development.plaid.com/transactions/sync"

    # 3. Production
    monkeypatch.setenv("PLAID_ENVIRONMENT", "Production")
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_test")
        assert mock_post.call_args[0][0] == "https://production.plaid.com/transactions/sync"

    # 4. Default fallback when unset
    monkeypatch.delenv("PLAID_ENVIRONMENT", raising=False)
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_test")
        assert mock_post.call_args[0][0] == "https://sandbox.plaid.com/transactions/sync"


def test_fetch_transactions_page_client_id_secret_headers(monkeypatch):
    monkeypatch.setenv("PLAID_CLIENT_ID", "test_client_id_abc")
    monkeypatch.setenv("PLAID_SECRET", "test_secret_xyz")

    mock_resp = _make_dummy_response()
    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp) as mock_post:
        fetch_transactions_page(access_token="tok_test")

    headers = mock_post.call_args[1]["headers"]
    assert headers["Content-Type"] == "application/json"
    assert headers["PLAID-CLIENT-ID"] == "test_client_id_abc"
    assert headers["PLAID-SECRET"] == "test_secret_xyz"


def test_fetch_transactions_page_adaptation():
    dummy_added = [{"transaction_id": "tx_1"}]
    dummy_modified = [{"transaction_id": "tx_2"}]
    dummy_removed = [{"transaction_id": "tx_3"}]
    mock_resp = _make_dummy_response(
        added=dummy_added,
        modified=dummy_modified,
        removed=dummy_removed,
        next_cursor="cursor_page_2",
        has_more=True,
    )

    with patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_resp):
        page = fetch_transactions_page(access_token="tok_test", cursor="cur_init")

    assert isinstance(page, PlaidTransactionPage)
    assert page.added == dummy_added
    assert page.modified == dummy_modified
    assert page.removed == dummy_removed
    assert page.next_cursor == "cursor_page_2"
    assert page.has_more is True


def test_fetch_transactions_page_http_error_translation():
    mock_http_resp = MagicMock()
    mock_http_resp.status_code = 401
    mock_http_resp.text = '{"error_code": "INVALID_ACCESS_TOKEN"}'
    exc = requests.exceptions.HTTPError(response=mock_http_resp)

    with patch("backend.access.plaid_transaction_access.requests.post", side_effect=exc):
        with pytest.raises(PlaidTransactionHttpError) as err_info:
            fetch_transactions_page(access_token="bad_tok")

    assert err_info.value.status_code == 401
    assert err_info.value.detail == '{"error_code": "INVALID_ACCESS_TOKEN"}'


def test_fetch_transactions_page_http_error_preserves_raw_response_text():
    mock_http_resp = MagicMock()
    mock_http_resp.status_code = 502
    mock_http_resp.text = "Bad Gateway from upstream"
    exc = requests.exceptions.HTTPError(response=mock_http_resp)

    with patch("backend.access.plaid_transaction_access.requests.post", side_effect=exc):
        with pytest.raises(PlaidTransactionHttpError) as err_info:
            fetch_transactions_page(access_token="tok")

    # Detail must be exact raw text without any prepended prefix
    assert err_info.value.detail == "Bad Gateway from upstream"
    assert "Plaid Sync Error: " not in err_info.value.detail


def test_fetch_transactions_page_network_timeout_error_translation():
    exc = requests.exceptions.Timeout("Read timeout after 60s")

    with patch("backend.access.plaid_transaction_access.requests.post", side_effect=exc):
        with pytest.raises(PlaidTransactionNetworkError) as err_info:
            fetch_transactions_page(access_token="tok")

    assert err_info.value.detail == "Read timeout after 60s"


def test_fetch_transactions_page_network_error_detail_is_str_exc():
    exc = requests.exceptions.ConnectionError("Connection refused by host")

    with patch("backend.access.plaid_transaction_access.requests.post", side_effect=exc):
        with pytest.raises(PlaidTransactionNetworkError) as err_info:
            fetch_transactions_page(access_token="tok")

    assert err_info.value.detail == "Connection refused by host"


def test_no_manager_dependencies():
    import inspect
    source = inspect.getsource(plaid_transaction_access)
    assert "managers" not in source
    assert "fastapi" not in source
    assert "sqlalchemy" not in source
