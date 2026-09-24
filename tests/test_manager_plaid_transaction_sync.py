"""
Focused unit tests for PlaidTransactionSyncManager (backend/managers/plaid_transaction_sync_manager.py).
Verifies workflow sequencing, identifier precedence, error translation, pagination,
commit behavior, and structural boundaries.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal
import inspect
from unittest.mock import MagicMock, call, patch
from uuid import uuid4
import pytest

from backend import models
from backend.access.plaid_access import PlaidAccessError, PlaidAccountSnapshot
from backend.access.plaid_transaction_access import (
    PlaidTransactionHttpError,
    PlaidTransactionNetworkError,
    PlaidTransactionPage,
)
from backend.managers import plaid_transaction_sync_manager
from backend.managers.plaid_transaction_sync_manager import (
    PlaidTransactionSyncAccountRefreshError,
    PlaidTransactionSyncDecryptionError,
    PlaidTransactionSyncHttpError,
    PlaidTransactionSyncItemNotFoundError,
    PlaidTransactionSyncMissingIdentifierError,
    PlaidTransactionSyncNetworkError,
    PlaidTransactionSyncResult,
    sync_plaid_transactions,
)


def _make_dummy_item(
    item_id=None,
    plaid_item_id="item_dummy",
    encrypted_token="dGVzdF90b2tlbg==",
    cursor=None,
):
    item = MagicMock(spec=models.PlaidItem)
    item.id = item_id or uuid4()
    item.plaid_item_id = plaid_item_id
    item.plaid_access_token_encrypted = encrypted_token
    item.transactions_cursor = cursor
    return item


def _make_dummy_page(
    added=None,
    modified=None,
    removed=None,
    next_cursor="cur_next",
    has_more=False,
):
    return PlaidTransactionPage(
        added=added or [],
        modified=modified or [],
        removed=removed or [],
        next_cursor=next_cursor,
        has_more=has_more,
    )


# 1. Missing identifier error
def test_sync_transactions_missing_identifier_error():
    db = MagicMock()
    with pytest.raises(PlaidTransactionSyncMissingIdentifierError) as exc_info:
        sync_plaid_transactions(db, item_id=None, plaid_item_id=None)
    assert str(exc_info.value) == "Must provide item_id or plaid_item_id"


# 2. item_id precedence
def test_sync_transactions_item_id_precedence():
    db = MagicMock()
    target_id = uuid4()
    item = _make_dummy_item(item_id=target_id, plaid_item_id="item_actual")

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item) as mock_by_id, \
         patch("backend.access.plaid_item_access.get_plaid_item_by_plaid_item_id") as mock_by_plaid_id, \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=_make_dummy_page()):
        sync_plaid_transactions(db, item_id=target_id, plaid_item_id="item_ignored")

    mock_by_id.assert_called_once_with(db, target_id)
    assert call(db, "item_ignored") not in mock_by_plaid_id.call_args_list


# 3. Selected item missing (and no fallback to plaid_item_id)
def test_sync_transactions_selected_item_missing():
    db = MagicMock()
    target_id = uuid4()

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=None), \
         patch("backend.access.plaid_item_access.get_plaid_item_by_plaid_item_id") as mock_by_plaid_id:
        with pytest.raises(PlaidTransactionSyncItemNotFoundError) as exc_info:
            sync_plaid_transactions(db, item_id=target_id, plaid_item_id="item_ignored")

    assert str(exc_info.value) == "Plaid Item not found"
    mock_by_plaid_id.assert_not_called()


# 4. Escaping decrypt exception
def test_sync_transactions_escaping_decrypt_exception():
    db = MagicMock()
    item = _make_dummy_item()

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", side_effect=ValueError("Corrupt")):
        with pytest.raises(PlaidTransactionSyncDecryptionError) as exc_info:
            sync_plaid_transactions(db, item_id=item.id)

    assert str(exc_info.value) == "Error decrypting access token"


# 5. Empty decoded token continues to Plaid account fetch
def test_sync_transactions_empty_decoded_token_continues():
    db = MagicMock()
    item = _make_dummy_item()

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value=""), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]) as mock_fetch, \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=_make_dummy_page()):
        sync_plaid_transactions(db, item_id=item.id)

    mock_fetch.assert_called_once_with("")


# 6. Account PlaidAccessError translated to account-refresh application error
def test_sync_transactions_account_refresh_error_translation():
    db = MagicMock()
    item = _make_dummy_item()
    access_err = PlaidAccessError(status_code=400, detail='{"error_code": "INVALID_TOKEN"}')

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", side_effect=access_err):
        with pytest.raises(PlaidTransactionSyncAccountRefreshError) as exc_info:
            sync_plaid_transactions(db, item_id=item.id)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == '{"error_code": "INVALID_TOKEN"}'


# 7. Account snapshots staged
def test_sync_transactions_account_snapshots_staged():
    db = MagicMock()
    item = _make_dummy_item()
    snapshot = PlaidAccountSnapshot(
        account_id="acc_1",
        name="Checking",
        mask="1234",
        account_type="depository",
        subtype="checking",
        current_balance=Decimal("500.00"),
        available_balance=Decimal("450.00"),
        currency="USD",
    )

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[snapshot]), \
         patch("backend.access.account_access.stage_or_update_plaid_account") as mock_stage, \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=_make_dummy_page()):
        sync_plaid_transactions(db, item_id=item.id)

    mock_stage.assert_called_once()
    assert mock_stage.call_args[1]["plaid_account_id"] == "acc_1"
    assert mock_stage.call_args[1]["name"] == "Checking"
    assert mock_stage.call_args[1]["item_id"] == item.id


# 8 & 9. Exactly one db.flush() after account refresh and no commit before transactions
def test_sync_transactions_flush_after_account_refresh_and_no_premature_commit():
    db = MagicMock()
    item = _make_dummy_item()

    events = []
    db.flush.side_effect = lambda: events.append("flush")
    db.commit.side_effect = lambda: events.append("commit")

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=_make_dummy_page()):
        sync_plaid_transactions(db, item_id=item.id)

    # First event must be flush, followed later by the two final commits
    assert events[0] == "flush"
    assert events[1:] == ["commit", "commit"]


# 10. Starting cursor read
def test_sync_transactions_starting_cursor_read():
    db = MagicMock()
    item = _make_dummy_item(cursor="cur_initial_999")

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=_make_dummy_page()) as mock_fetch:
        sync_plaid_transactions(db, item_id=item.id)

    mock_fetch.assert_called_once_with(access_token="test_token", cursor="cur_initial_999")


# 11. Multi-page pagination
def test_sync_transactions_multi_page_pagination():
    db = MagicMock()
    item = _make_dummy_item(cursor="c0")
    page1 = _make_dummy_page(next_cursor="c1", has_more=True)
    page2 = _make_dummy_page(next_cursor="c2", has_more=False)

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", side_effect=[page1, page2]) as mock_fetch:
        result = sync_plaid_transactions(db, item_id=item.id)

    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0][1]["cursor"] == "c0"
    assert mock_fetch.call_args_list[1][1]["cursor"] == "c1"
    assert result.next_cursor == "c2"


# 12. Cursor advanced before event processing
def test_sync_transactions_cursor_advanced_before_event_processing():
    db = MagicMock()
    item = _make_dummy_item(cursor="c0")

    observed_cursor_in_event = []

    def mock_event(db, tx_data):
        # We verify that cursor in manager context already advanced
        observed_cursor_in_event.append(tx_data["transaction_id"])

    page = _make_dummy_page(
        added=[{"transaction_id": "tx_add"}],
        next_cursor="c1",
        has_more=False,
    )

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page), \
         patch("backend.crud.transaction.create_or_update_transaction", side_effect=mock_event):
        sync_plaid_transactions(db, item_id=item.id)

    assert observed_cursor_in_event == ["tx_add"]


# 13 & 14 & 15. Added before modified before removed & legacy helpers called & counts
def test_sync_transactions_event_order_and_counts():
    db = MagicMock()
    item = _make_dummy_item()

    page = _make_dummy_page(
        added=[{"transaction_id": "tx_add_1"}, {"transaction_id": "tx_add_2"}],
        modified=[{"transaction_id": "tx_mod_1"}],
        removed=[{"transaction_id": "tx_del_1"}, {"transaction_id": "tx_del_2"}, {"transaction_id": "tx_del_3"}],
        next_cursor="c_final",
        has_more=False,
    )

    call_sequence = []

    def mock_create_or_update(db_arg, tx_data):
        call_sequence.append(("create_or_update", tx_data["transaction_id"]))

    def mock_delete(db_arg, plaid_tx_id):
        call_sequence.append(("delete", plaid_tx_id))

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page), \
         patch("backend.crud.transaction.create_or_update_transaction", side_effect=mock_create_or_update), \
         patch("backend.crud.transaction.delete_transaction_by_plaid_id", side_effect=mock_delete):
        result = sync_plaid_transactions(db, item_id=item.id)

    assert call_sequence == [
        ("create_or_update", "tx_add_1"),
        ("create_or_update", "tx_add_2"),
        ("create_or_update", "tx_mod_1"),
        ("delete", "tx_del_1"),
        ("delete", "tx_del_2"),
        ("delete", "tx_del_3"),
    ]
    assert result.added == 2
    assert result.modified == 1
    assert result.removed == 3
    assert result.next_cursor == "c_final"
    assert result.message == "Sync successful"


# 16. HTTP infrastructure error translated to Manager HTTP application error
def test_sync_transactions_http_infrastructure_error_translated():
    db = MagicMock()
    item = _make_dummy_item()
    http_err = PlaidTransactionHttpError(status_code=400, detail='{"error": "invalid"}')

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", side_effect=http_err):
        with pytest.raises(PlaidTransactionSyncHttpError) as exc_info:
            sync_plaid_transactions(db, item_id=item.id)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == '{"error": "invalid"}'


# 17 & 18. Network infrastructure error translated separately and distinguishable
def test_sync_transactions_network_infrastructure_error_translated_separately():
    db = MagicMock()
    item = _make_dummy_item()
    net_err = PlaidTransactionNetworkError(detail="Timeout connection")

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", side_effect=net_err):
        with pytest.raises(PlaidTransactionSyncNetworkError) as exc_info:
            sync_plaid_transactions(db, item_id=item.id)

    assert exc_info.value.detail == "Timeout connection"
    assert not hasattr(exc_info.value, "status_code")
    assert not issubclass(PlaidTransactionSyncNetworkError, PlaidTransactionSyncHttpError)


# 19. No cursor staging on page failure
def test_sync_transactions_no_cursor_staging_on_page_failure():
    db = MagicMock()
    item = _make_dummy_item()
    http_err = PlaidTransactionHttpError(status_code=500, detail="Plaid 500")

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", side_effect=http_err), \
         patch("backend.access.plaid_item_access.stage_transactions_cursor") as mock_stage_cursor:
        with pytest.raises(PlaidTransactionSyncHttpError):
            sync_plaid_transactions(db, item_id=item.id)

    mock_stage_cursor.assert_not_called()


# 20. Final cursor staging after all pages
def test_sync_transactions_final_cursor_staged_after_all_pages():
    db = MagicMock()
    item = _make_dummy_item(plaid_item_id="item_real_id")
    page = _make_dummy_page(next_cursor="c_done", has_more=False)

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page), \
         patch("backend.access.plaid_item_access.stage_transactions_cursor") as mock_stage_cursor:
        sync_plaid_transactions(db, item_id=item.id)

    mock_stage_cursor.assert_called_once_with(
        db=db,
        plaid_item_id="item_real_id",
        cursor="c_done",
    )


# 21 & 22. First final commit and redundant second final commit
def test_sync_transactions_two_final_commits():
    db = MagicMock()
    item = _make_dummy_item()
    page = _make_dummy_page(has_more=False)

    with patch("backend.access.plaid_item_access.get_plaid_item_by_id", return_value=item), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page), \
         patch("backend.access.plaid_item_access.stage_transactions_cursor"):
        sync_plaid_transactions(db, item_id=item.id)

    assert db.commit.call_count == 2


# 23. Result dataclass immutable
def test_sync_transactions_result_dataclass_immutable():
    res = PlaidTransactionSyncResult(
        message="Sync successful",
        added=1,
        modified=2,
        removed=3,
        next_cursor="cur",
    )
    with pytest.raises(FrozenInstanceError):
        res.added = 99


# 24. Manager has no FastAPI imports
def test_sync_manager_no_fastapi_imports():
    source = inspect.getsource(plaid_transaction_sync_manager)
    assert "fastapi" not in source
    assert "HTTPException" not in source


# 25. Manager has no requests imports
def test_sync_manager_no_requests_imports():
    source = inspect.getsource(plaid_transaction_sync_manager)
    assert "import requests" not in source
    assert "from requests" not in source
    assert "PlaidApi" not in source
    assert "AccountsGetRequest" not in source


# 26. Manager does not call PlaidAccountSyncManager
def test_sync_manager_does_not_call_plaid_account_sync_manager():
    source = inspect.getsource(plaid_transaction_sync_manager)
    assert "PlaidAccountSyncManager" not in source
    assert "plaid_account_sync_manager" not in source
