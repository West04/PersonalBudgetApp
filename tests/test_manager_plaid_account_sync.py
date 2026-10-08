"""
Unit tests for PlaidAccountSyncManager (backend/managers/plaid_account_sync_manager.py).
Uses controlled mocks to verify workflow sequencing and error translation.
"""

from dataclasses import is_dataclass
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, call, patch
from uuid import uuid4
import pytest

from backend.access.plaid_access import PlaidAccountSnapshot, PlaidAccessError
from backend.managers.plaid_account_sync_manager import (
    PlaidAccountSyncDecryptionError,
    PlaidAccountSyncExternalApiError,
    PlaidAccountSyncItemNotFoundError,
    PlaidAccountSyncMissingIdentifierError,
    PlaidAccountSyncResult,
    sync_plaid_accounts,
)


def _make_mock_item(item_id=None, plaid_item_id="item_plaid_123", encrypted_token=None):
    from backend.security import encrypt_token

    if encrypted_token is None:
        encrypted_token = encrypt_token("token")
    mock_item = MagicMock()
    mock_item.id = item_id or uuid4()
    mock_item.plaid_item_id = plaid_item_id
    mock_item.plaid_access_token_encrypted = encrypted_token
    return mock_item


# 1. Missing identifiers raise application error
def test_sync_accounts_missing_both_identifiers_raises():
    mock_db = MagicMock()
    with pytest.raises(PlaidAccountSyncMissingIdentifierError, match="Must provide item_id or plaid_item_id"):
        sync_plaid_accounts(mock_db, item_id=None, plaid_item_id=None)


# 2. item_id precedence over plaid_item_id
@patch("backend.managers.plaid_account_sync_manager.plaid_access.fetch_accounts_for_token", return_value=[])
@patch("backend.managers.plaid_account_sync_manager.decrypt_token", return_value="token_123")
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_item_id_precedence(mock_item_access, mock_decrypt, mock_fetch):
    mock_db = MagicMock()
    uuid_id = uuid4()
    mock_item = _make_mock_item(item_id=uuid_id)
    mock_item_access.get_plaid_item_by_id.return_value = mock_item

    res = sync_plaid_accounts(mock_db, item_id=uuid_id, plaid_item_id="ignored_plaid_id")

    mock_item_access.get_plaid_item_by_id.assert_called_once_with(mock_db, uuid_id)
    mock_item_access.get_plaid_item_by_plaid_item_id.assert_not_called()
    assert res.accounts_updated == 0


# 3. Item not found behavior (for both item_id and plaid_item_id)
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_item_not_found_raises(mock_item_access):
    mock_db = MagicMock()
    mock_item_access.get_plaid_item_by_id.return_value = None
    mock_item_access.get_plaid_item_by_plaid_item_id.return_value = None

    with pytest.raises(PlaidAccountSyncItemNotFoundError, match="Plaid Item not found"):
        sync_plaid_accounts(mock_db, item_id=uuid4())

    with pytest.raises(PlaidAccountSyncItemNotFoundError, match="Plaid Item not found"):
        sync_plaid_accounts(mock_db, plaid_item_id="missing_str")


# 4. Escaping decrypt exception translation
@patch("backend.managers.plaid_account_sync_manager.decrypt_token", side_effect=ValueError("Corrupt cipher key"))
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_escaping_decrypt_exception_raises(mock_item_access, mock_decrypt):
    mock_db = MagicMock()
    mock_item_access.get_plaid_item_by_id.return_value = _make_mock_item()

    with pytest.raises(PlaidAccountSyncDecryptionError, match="Error decrypting access token"):
        sync_plaid_accounts(mock_db, item_id=uuid4())


# 5. Empty decoded token still reaches PlaidAccess (characterization invariant)
@patch("backend.managers.plaid_account_sync_manager.plaid_access.fetch_accounts_for_token", return_value=[])
@patch("backend.managers.plaid_account_sync_manager.decrypt_token", return_value="")
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_empty_decoded_token_reaches_plaid_access(mock_item_access, mock_decrypt, mock_fetch):
    mock_db = MagicMock()
    mock_item_access.get_plaid_item_by_id.return_value = _make_mock_item()

    sync_plaid_accounts(mock_db, item_id=uuid4())
    mock_fetch.assert_called_once_with("")


# 6. PlaidAccess error translation
@patch("backend.managers.plaid_account_sync_manager.plaid_access.fetch_accounts_for_token", side_effect=PlaidAccessError(400, '{"error_code":"INVALID_TOKEN"}'))
@patch("backend.managers.plaid_account_sync_manager.decrypt_token", return_value="tok")
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_plaid_access_error_translated(mock_item_access, mock_decrypt, mock_fetch):
    mock_db = MagicMock()
    mock_item_access.get_plaid_item_by_id.return_value = _make_mock_item()

    with pytest.raises(PlaidAccountSyncExternalApiError) as exc_info:
        sync_plaid_accounts(mock_db, item_id=uuid4())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == '{"error_code":"INVALID_TOKEN"}'


# 7. External call occurs before AccountAccess calls
# 8. Each snapshot is unpacked to scalar AccountAccess arguments
# 9. Timestamp generated per account
# 10. accounts_updated increments per snapshot
@patch("backend.managers.plaid_account_sync_manager.account_access")
@patch("backend.managers.plaid_account_sync_manager.plaid_access.fetch_accounts_for_token")
@patch("backend.managers.plaid_account_sync_manager.decrypt_token", return_value="valid_token")
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_ordering_unpacking_and_per_account_timestamps(
    mock_item_access, mock_decrypt, mock_fetch, mock_account_access
):
    mock_db = MagicMock()
    item_uuid = uuid4()
    mock_item_access.get_plaid_item_by_id.return_value = _make_mock_item(item_id=item_uuid)

    snap1 = PlaidAccountSnapshot(
        account_id="acc_1",
        name="Checking",
        mask="1111",
        account_type="depository",
        subtype="checking",
        current_balance=Decimal("100.00"),
        available_balance=Decimal("90.00"),
        currency="USD",
    )
    snap2 = PlaidAccountSnapshot(
        account_id="acc_2",
        name=None,
        mask=None,
        account_type=None,
        subtype=None,
        current_balance=Decimal("50.00"),
        available_balance=None,
        currency="USD",
    )
    mock_fetch.return_value = [snap1, snap2]

    # Verify execution order: fetch before stage
    manager_calls = []
    mock_fetch.side_effect = lambda tok: (manager_calls.append("fetch"), [snap1, snap2])[1]
    mock_account_access.stage_or_update_plaid_account.side_effect = lambda *args, **kwargs: manager_calls.append("stage")

    res = sync_plaid_accounts(mock_db, item_id=item_uuid)

    assert manager_calls == ["fetch", "stage", "stage"]
    assert mock_account_access.stage_or_update_plaid_account.call_count == 2

    # Verify unpacked scalar arguments on first call
    call1 = mock_account_access.stage_or_update_plaid_account.call_args_list[0]
    assert call1.args[0] == mock_db
    assert call1.kwargs["item_id"] == item_uuid
    assert call1.kwargs["plaid_account_id"] == "acc_1"
    assert call1.kwargs["name"] == "Checking"
    assert call1.kwargs["mask"] == "1111"
    assert call1.kwargs["account_type"] == "depository"
    assert call1.kwargs["subtype"] == "checking"
    assert call1.kwargs["current_balance"] == Decimal("100.00")
    assert call1.kwargs["available_balance"] == Decimal("90.00")
    assert call1.kwargs["currency"] == "USD"
    assert isinstance(call1.kwargs["balance_last_updated"], datetime)

    # Verify unpacked scalar arguments on second call
    call2 = mock_account_access.stage_or_update_plaid_account.call_args_list[1]
    assert call2.kwargs["plaid_account_id"] == "acc_2"
    assert call2.kwargs["name"] is None
    assert call2.kwargs["available_balance"] is None
    assert isinstance(call2.kwargs["balance_last_updated"], datetime)

    # Result count is 2
    assert res.accounts_updated == 2


# 11. Zero accounts returns count 0
@patch("backend.managers.plaid_account_sync_manager.account_access")
@patch("backend.managers.plaid_account_sync_manager.plaid_access.fetch_accounts_for_token", return_value=[])
@patch("backend.managers.plaid_account_sync_manager.decrypt_token", return_value="valid_token")
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_zero_accounts_returns_count_zero(
    mock_item_access, mock_decrypt, mock_fetch, mock_account_access
):
    mock_db = MagicMock()
    mock_item_access.get_plaid_item_by_id.return_value = _make_mock_item()

    res = sync_plaid_accounts(mock_db, item_id=uuid4())
    assert res.accounts_updated == 0
    mock_account_access.stage_or_update_plaid_account.assert_not_called()
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_called_once()


# 12. One final db.flush()
# 13. Flush occurs after all account staging
# 14. One final db.commit()
# 15. Commit occurs after flush
@patch("backend.managers.plaid_account_sync_manager.account_access")
@patch("backend.managers.plaid_account_sync_manager.plaid_access.fetch_accounts_for_token")
@patch("backend.managers.plaid_account_sync_manager.decrypt_token", return_value="token")
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_flush_and_commit_lifecycle(
    mock_item_access, mock_decrypt, mock_fetch, mock_account_access
):
    mock_db = MagicMock()
    mock_item_access.get_plaid_item_by_id.return_value = _make_mock_item()
    snap = PlaidAccountSnapshot(
        account_id="acc_x",
        name="Name",
        mask="0000",
        account_type="depository",
        subtype=None,
        current_balance=Decimal("1.00"),
        available_balance=None,
        currency="USD",
    )
    mock_fetch.return_value = [snap]

    call_order = []
    mock_account_access.stage_or_update_plaid_account.side_effect = lambda *args, **kwargs: call_order.append("stage")
    mock_db.flush.side_effect = lambda: call_order.append("flush")
    mock_db.commit.side_effect = lambda: call_order.append("commit")

    sync_plaid_accounts(mock_db, item_id=uuid4())

    assert call_order == ["stage", "flush", "commit"]
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_called_once()


# 16. Flush failure prevents commit
@patch("backend.managers.plaid_account_sync_manager.account_access")
@patch("backend.managers.plaid_account_sync_manager.plaid_access.fetch_accounts_for_token", return_value=[])
@patch("backend.managers.plaid_account_sync_manager.decrypt_token", return_value="tok")
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_flush_failure_prevents_commit(
    mock_item_access, mock_decrypt, mock_fetch, mock_account_access
):
    mock_db = MagicMock()
    mock_item_access.get_plaid_item_by_id.return_value = _make_mock_item()
    mock_db.flush.side_effect = RuntimeError("DB Flush Failure")

    with pytest.raises(RuntimeError, match="DB Flush Failure"):
        sync_plaid_accounts(mock_db, item_id=uuid4())

    mock_db.commit.assert_not_called()


# 17. Commit failure propagates
@patch("backend.managers.plaid_account_sync_manager.account_access")
@patch("backend.managers.plaid_account_sync_manager.plaid_access.fetch_accounts_for_token", return_value=[])
@patch("backend.managers.plaid_account_sync_manager.decrypt_token", return_value="tok")
@patch("backend.managers.plaid_account_sync_manager.plaid_item_access")
def test_sync_accounts_commit_failure_propagates(
    mock_item_access, mock_decrypt, mock_fetch, mock_account_access
):
    mock_db = MagicMock()
    mock_item_access.get_plaid_item_by_id.return_value = _make_mock_item()
    mock_db.commit.side_effect = RuntimeError("DB Commit Failure")

    with pytest.raises(RuntimeError, match="DB Commit Failure"):
        sync_plaid_accounts(mock_db, item_id=uuid4())

    mock_db.flush.assert_called_once()
    mock_db.commit.assert_called_once()


# 18. Result is immutable PlaidAccountSyncResult
def test_sync_accounts_result_immutability():
    res = PlaidAccountSyncResult(accounts_updated=5)
    assert is_dataclass(res)
    assert res.accounts_updated == 5
    with pytest.raises(AttributeError):
        res.accounts_updated = 10


# 19. No FastAPI / Pydantic / Plaid SDK types in Manager module
def test_sync_accounts_manager_has_no_framework_imports():
    import sys
    import backend.managers.plaid_account_sync_manager as mgr

    mgr_source = open(mgr.__file__).read()
    assert "fastapi" not in mgr_source
    assert "pydantic" not in mgr_source
    assert "plaid.model" not in mgr_source
    assert "plaid.api" not in mgr_source
    assert "AccountsGetRequest" not in mgr_source
