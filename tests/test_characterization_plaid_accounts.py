from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from plaid.exceptions import ApiException

from backend import models
from backend.crud.plaid import create_plaid_item


# ---------------------------------------------------------------------------
# Test Helpers for Mocking Plaid API Responses
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


def _make_mock_response(accounts):
    """Constructs a mock Plaid AccountsGetResponse object."""
    resp = MagicMock()
    resp.accounts = accounts
    return resp


# ---------------------------------------------------------------------------
# 1 & 2. Identifier Validation & Precedence
# ---------------------------------------------------------------------------

def test_sync_accounts_missing_both_identifiers_400(client):
    """
    Verify POST /plaid/sync_accounts returns HTTP 400 with exact detail
    when neither item_id nor plaid_item_id is provided in the JSON body.
    """
    resp = client.post("/plaid/sync_accounts", json={})
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Must provide item_id or plaid_item_id"}


def test_sync_accounts_missing_item_by_uuid_404(client):
    """
    Verify POST /plaid/sync_accounts returns HTTP 404 when item_id UUID does not exist.
    """
    non_existent_uuid = str(uuid4())
    resp = client.post("/plaid/sync_accounts", json={"item_id": non_existent_uuid})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Plaid Item not found"}


def test_sync_accounts_missing_item_by_plaid_item_id_404(client):
    """
    Verify POST /plaid/sync_accounts returns HTTP 404 when plaid_item_id string does not exist.
    """
    resp = client.post("/plaid/sync_accounts", json={"plaid_item_id": "nonexistent_plaid_item_id"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Plaid Item not found"}


def test_sync_accounts_item_id_takes_precedence_over_plaid_item_id(client, db_session):
    """
    Verify that when both item_id and plaid_item_id are supplied, item_id takes precedence:
    - Item Alpha has id_alpha and plaid_item_id="item_alpha" (access_token="token_alpha")
    - Item Beta has id_beta and plaid_item_id="item_beta" (access_token="token_beta")
    - Request sends item_id=id_alpha and plaid_item_id="item_beta"
    - Resulting sync uses Item Alpha's credentials and links accounts to Item Alpha's UUID.
    """
    item_alpha = create_plaid_item(db_session, plaid_item_id="item_alpha", access_token="token_alpha")
    item_beta = create_plaid_item(db_session, plaid_item_id="item_beta", access_token="token_beta")

    mock_acct = _make_mock_account(account_id="acc_precedence_test")
    mock_resp = _make_mock_response([mock_acct])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp) as mock_get:
        resp = client.post(
            "/plaid/sync_accounts",
            json={"item_id": str(item_alpha.id), "plaid_item_id": "item_beta"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "accounts_updated": 1}

    # Verify that Item Alpha's access token was passed to Plaid API
    mock_get.assert_called_once()
    called_req = mock_get.call_args[0][0]
    assert called_req.access_token == "token_alpha"

    # Verify that the created Account is associated with Item Alpha (not Item Beta)
    acc = db_session.query(models.Account).filter_by(plaid_account_id="acc_precedence_test").first()
    assert acc is not None
    assert acc.item_id == item_alpha.id


# ---------------------------------------------------------------------------
# 3 & 4. Real Token Decryption vs. Unhandled Decrypt Exception
# ---------------------------------------------------------------------------

def test_sync_accounts_real_malformed_token_returns_empty_string_and_invokes_plaid(client, db_session):
    """
    Characterize REAL decrypt_token behavior with malformed stored token:
    - decrypt_token catches the decode error internally and returns ""
    - sync_accounts does NOT raise HTTP 500 "Error decrypting access token"
    - Instead, AccountsGetRequest is constructed with access_token="" and Plaid API is invoked
    - Plaid API then returns its own error (e.g. 400 INVALID_ACCESS_TOKEN)
    """
    # Create item with corrupted non-base64 token
    item = models.PlaidItem(
        plaid_item_id="item_corrupt_token",
        plaid_access_token_encrypted="!!!NOT_VALID_BASE64_PADDING!!!",
    )
    db_session.add(item)
    db_session.commit()

    # When Plaid receives an empty token, it raises an ApiException
    api_exc = ApiException(status=400, reason="Bad Request")
    api_exc.body = '{"error_code": "INVALID_ACCESS_TOKEN", "error_message": "Provided access token is empty"}'

    with patch("backend.access.plaid_access.client.accounts_get", side_effect=api_exc) as mock_get:
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    # Verifies Plaid API WAS invoked with empty string access_token
    mock_get.assert_called_once()
    assert mock_get.call_args[0][0].access_token == ""

    # Resulting HTTP status and body comes from Plaid ApiException, NOT router decrypt catch
    assert resp.status_code == 400
    assert resp.json() == {"detail": '{"error_code": "INVALID_ACCESS_TOKEN", "error_message": "Provided access token is empty"}'}


def test_sync_accounts_unhandled_decrypt_exception_500(client, db_session):
    """
    Characterize the Router's explicit exception catch block when decrypt_token itself raises:
    - try: access_token = decrypt_token(...)
    - except Exception: raise HTTPException(500, "Error decrypting access token")
    """
    item = create_plaid_item(db_session, plaid_item_id="item_decrypt_crash", access_token="test_token")

    with patch("backend.managers.plaid_account_sync_manager.decrypt_token", side_effect=RuntimeError("Cryptographic engine failed")):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Error decrypting access token"}


# ---------------------------------------------------------------------------
# 5 & 6. External Plaid API Exception Handling
# ---------------------------------------------------------------------------

def test_sync_accounts_plaid_api_exception_propagates_status_and_body(client, db_session):
    """
    Verify that a Plaid ApiException maps directly:
    HTTP status = exc.status
    detail = exc.body (exact raw string from Plaid SDK)
    """
    item = create_plaid_item(db_session, plaid_item_id="item_api_err", access_token="test_token")

    api_exc = ApiException(status=402, reason="Payment Required")
    api_exc.body = '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "Login revoked by institution"}'

    with patch("backend.access.plaid_access.client.accounts_get", side_effect=api_exc):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 402
    assert resp.json() == {"detail": '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "Login revoked by institution"}'}


def test_sync_accounts_generic_external_exception_500(client, db_session):
    """
    Verify that unexpected non-ApiException errors (e.g. network disconnect)
    propagate as HTTP 500 with detail = str(e).
    """
    item = create_plaid_item(db_session, plaid_item_id="item_net_err", access_token="test_token")

    with patch("backend.access.plaid_access.client.accounts_get", side_effect=ConnectionError("DNS resolution failed for sandbox.plaid.com")):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "DNS resolution failed for sandbox.plaid.com"}


# ---------------------------------------------------------------------------
# 7, 8, & 9. New-Account Creation, Fallbacks, and Balance Signs
# ---------------------------------------------------------------------------

def test_sync_accounts_create_new_account_full_fields(client, db_session):
    """
    Verify full field persistence when a new Plaid account is synchronized:
    - is_active is set to True
    - starting_balance relies on ORM default 0.00
    - balance_last_updated is set to current UTC timestamp
    """
    item = create_plaid_item(db_session, plaid_item_id="item_create_test", access_token="test_token")

    mock_acct = _make_mock_account(
        account_id="plaid_acc_full_001",
        name="Primary Checking",
        mask="5432",
        account_type="depository",
        subtype="checking",
        current_balance=2450.75,
        available_balance=2400.00,
        iso_currency_code="USD",
    )
    mock_resp = _make_mock_response([mock_acct])

    before_sync = datetime.now(timezone.utc)

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    after_sync = datetime.now(timezone.utc)

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "accounts_updated": 1}

    db_acc = db_session.query(models.Account).filter_by(plaid_account_id="plaid_acc_full_001").first()
    assert db_acc is not None
    assert db_acc.item_id == item.id
    assert db_acc.plaid_account_id == "plaid_acc_full_001"
    assert db_acc.name == "Primary Checking"
    assert db_acc.mask == "5432"
    assert db_acc.type == "depository"
    assert db_acc.subtype == "checking"
    assert db_acc.is_active is True
    assert db_acc.starting_balance == Decimal("0.00")
    assert db_acc.current_balance == Decimal("2450.75")
    assert db_acc.available_balance == Decimal("2400.00")
    assert db_acc.currency == "USD"

    # Verify timestamp presence within execution window
    # SQLite/Postgres TIMESTAMP with timezone comparison
    assert db_acc.balance_last_updated is not None
    last_updated = db_acc.balance_last_updated.replace(tzinfo=timezone.utc) if db_acc.balance_last_updated.tzinfo is None else db_acc.balance_last_updated
    assert before_sync - timedelta(seconds=2) <= last_updated <= after_sync + timedelta(seconds=2)


def test_sync_accounts_creation_fallbacks(client, db_session):
    """
    Verify fallback semantics when Plaid fields are missing or empty on a new account:
    - missing/falsy name -> "Account"
    - missing/falsy type -> "unknown"
    - missing mask -> None
    - missing subtype -> None
    - missing currency -> "USD"
    - missing available balance -> None
    - missing/None current balance -> Decimal("0")
    """
    item = create_plaid_item(db_session, plaid_item_id="item_fallbacks", access_token="test_token")

    acct_raw = MagicMock()
    acct_raw.to_dict.return_value = {
        "account_id": "plaid_acc_empty_fields",
        "name": "",          # Falsy name -> should fall back to "Account"
        "mask": None,
        "type": None,        # Falsy type -> should fall back to "unknown"
        "subtype": None,
        "balances": {
            "current": None, # None current -> should fall back to Decimal("0")
            "available": None,
            "iso_currency_code": None, # Missing currency -> should fall back to "USD"
        },
    }
    mock_resp = _make_mock_response([acct_raw])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    db_acc = db_session.query(models.Account).filter_by(plaid_account_id="plaid_acc_empty_fields").first()
    assert db_acc is not None
    assert db_acc.name == "Account"
    assert db_acc.type == "unknown"
    assert db_acc.mask is None
    assert db_acc.subtype is None
    assert db_acc.currency == "USD"
    assert db_acc.available_balance is None
    assert db_acc.current_balance == Decimal("0")


def test_sync_accounts_no_balance_sign_inversion(client, db_session):
    """
    Explicitly verify that Account Sync performs NO sign inversion:
    - Positive credit card charge/balance in Plaid remains positive in models.Account
    - Positive depository balance remains positive
    (Account balance semantics differ from transaction sign conventions).
    """
    item = create_plaid_item(db_session, plaid_item_id="item_sign_test", access_token="test_token")

    credit_acct = _make_mock_account(
        account_id="plaid_card_001",
        name="Credit Card",
        account_type="credit",
        subtype="credit card",
        current_balance=450.75,
        available_balance=None,
    )
    checking_acct = _make_mock_account(
        account_id="plaid_chk_001",
        name="Checking",
        account_type="depository",
        subtype="checking",
        current_balance=1200.00,
        available_balance=1150.00,
    )
    mock_resp = _make_mock_response([credit_acct, checking_acct])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    db_card = db_session.query(models.Account).filter_by(plaid_account_id="plaid_card_001").first()
    assert db_card.current_balance == Decimal("450.75")
    assert db_card.available_balance is None

    db_chk = db_session.query(models.Account).filter_by(plaid_account_id="plaid_chk_001").first()
    assert db_chk.current_balance == Decimal("1200.00")
    assert db_chk.available_balance == Decimal("1150.00")


# ---------------------------------------------------------------------------
# 10, 11, 12, & 13. Existing-Account Update & Preserved Fields
# ---------------------------------------------------------------------------

def test_sync_accounts_update_existing_account_fields(client, db_session):
    """
    Verify fields updated when re-synchronizing an existing account:
    - name, mask, type, subtype, current_balance, available_balance, currency, balance_last_updated
    """
    item = create_plaid_item(db_session, plaid_item_id="item_update_test", access_token="test_token")

    # Seed existing account with older values
    old_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    existing_acc = models.Account(
        item_id=item.id,
        plaid_account_id="plaid_update_target",
        name="Old Name",
        mask="0000",
        type="depository",
        subtype="savings",
        current_balance=Decimal("100.00"),
        available_balance=Decimal("50.00"),
        currency="USD",
        balance_last_updated=old_time,
        is_active=True,
    )
    db_session.add(existing_acc)
    db_session.commit()

    # New values returned by Plaid
    updated_acct = _make_mock_account(
        account_id="plaid_update_target",
        name="Updated Name",
        mask="1111",
        account_type="depository",
        subtype="checking",
        current_balance=999.99,
        available_balance=888.88,
        iso_currency_code="USD",
    )
    mock_resp = _make_mock_response([updated_acct])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    db_session.refresh(existing_acc)
    assert existing_acc.name == "Updated Name"
    assert existing_acc.mask == "1111"
    assert existing_acc.type == "depository"
    assert existing_acc.subtype == "checking"
    assert existing_acc.current_balance == Decimal("999.99")
    assert existing_acc.available_balance == Decimal("888.88")
    assert existing_acc.currency == "USD"
    # balance_last_updated was refreshed
    last_updated = existing_acc.balance_last_updated.replace(tzinfo=timezone.utc) if existing_acc.balance_last_updated.tzinfo is None else existing_acc.balance_last_updated
    assert last_updated > old_time


def test_sync_accounts_preserves_starting_balance_and_inactive_status(client, db_session):
    """
    Verify that synchronization NEVER overwrites:
    - customized starting_balance
    - inactive status (is_active == False is NOT reactivated)
    - local primary key (id)
    """
    item = create_plaid_item(db_session, plaid_item_id="item_preserve_test", access_token="test_token")

    original_id = uuid4()
    existing_acc = models.Account(
        id=original_id,
        item_id=item.id,
        plaid_account_id="plaid_preserve_target",
        name="Deactivated Savings",
        type="depository",
        starting_balance=Decimal("350.00"),  # Customized starting balance
        current_balance=Decimal("100.00"),
        is_active=False,                     # User-deactivated account
        currency="USD",
    )
    db_session.add(existing_acc)
    db_session.commit()

    # Plaid returns new balance for this account
    remote_acct = _make_mock_account(
        account_id="plaid_preserve_target",
        name="Deactivated Savings",
        current_balance=500.00,
        available_balance=500.00,
    )
    mock_resp = _make_mock_response([remote_acct])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    db_session.refresh(existing_acc)
    # Preserved invariants
    assert existing_acc.id == original_id
    assert existing_acc.starting_balance == Decimal("350.00")
    assert existing_acc.is_active is False
    # Updated balance
    assert existing_acc.current_balance == Decimal("500.00")


def test_sync_accounts_update_fallback_asymmetry(client, db_session):
    """
    Characterize update fallback asymmetries:
    - Falsy remote name preserves existing local name (does not become 'Account')
    - Falsy remote type preserves existing local type (does not become 'unknown')
    - Remote mask None overwrites existing mask
    - Remote subtype None overwrites existing subtype
    - Missing ISO currency code falls back to 'USD'
    - Available balance None overwrites existing available balance
    """
    item = create_plaid_item(db_session, plaid_item_id="item_asymmetry", access_token="test_token")

    existing_acc = models.Account(
        item_id=item.id,
        plaid_account_id="plaid_asymmetry_target",
        name="Custom Local Name",
        mask="4321",
        type="depository",
        subtype="checking",
        current_balance=Decimal("100.00"),
        available_balance=Decimal("80.00"),
        currency="EUR",
    )
    db_session.add(existing_acc)
    db_session.commit()

    remote_raw = MagicMock()
    remote_raw.to_dict.return_value = {
        "account_id": "plaid_asymmetry_target",
        "name": "",        # Empty -> should preserve "Custom Local Name"
        "type": None,      # None -> should preserve "depository"
        "mask": None,      # None -> should overwrite "4321" with None
        "subtype": None,   # None -> should overwrite "checking" with None
        "balances": {
            "current": 150.00,
            "available": None,          # None -> should overwrite available_balance with None
            "iso_currency_code": None,  # None -> should overwrite currency with fallback "USD"
        },
    }
    mock_resp = _make_mock_response([remote_raw])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 200

    db_session.refresh(existing_acc)
    # Name and type preserved
    assert existing_acc.name == "Custom Local Name"
    assert existing_acc.type == "depository"
    # Mask, subtype, available set to None
    assert existing_acc.mask is None
    assert existing_acc.subtype is None
    assert existing_acc.available_balance is None
    # Currency falls back to "USD"
    assert existing_acc.currency == "USD"
    assert existing_acc.current_balance == Decimal("150.00")


def test_sync_accounts_matching_by_plaid_account_id_preserves_item_id_on_item_mismatch(client, db_session):
    """
    Characterize identity rule:
    Matching is by exact plaid_account_id alone.
    If an existing account is linked to Item 1, but is synchronized in a request
    for Item 2, the existing account is updated and its item_id remains Item 1.
    """
    item_1 = create_plaid_item(db_session, plaid_item_id="item_one", access_token="token_one")
    item_2 = create_plaid_item(db_session, plaid_item_id="item_two", access_token="token_two")

    existing_acc = models.Account(
        item_id=item_1.id,
        plaid_account_id="shared_plaid_acc_id",
        name="Item One Account",
        type="depository",
        current_balance=Decimal("50.00"),
        currency="USD",
    )
    db_session.add(existing_acc)
    db_session.commit()

    # Sync through Item 2
    remote_acct = _make_mock_account(
        account_id="shared_plaid_acc_id",
        name="Updated Across Items",
        current_balance=75.00,
    )
    mock_resp = _make_mock_response([remote_acct])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item_2.id)})

    assert resp.status_code == 200

    db_session.refresh(existing_acc)
    assert existing_acc.name == "Updated Across Items"
    assert existing_acc.current_balance == Decimal("75.00")
    # item_id is NOT reassigned to Item 2
    assert existing_acc.item_id == item_1.id


# ---------------------------------------------------------------------------
# 14, 15, & 16. Missing Remote Accounts and Count Semantics
# ---------------------------------------------------------------------------

def test_sync_accounts_missing_remote_account_remains_untouched(client, db_session):
    """
    Verify that local accounts belonging to the item that are NOT returned
    in the Plaid response remain completely untouched:
    - not deleted
    - not deactivated
    - balances not zeroed
    - balance_last_updated not modified
    """
    item = create_plaid_item(db_session, plaid_item_id="item_missing_remote", access_token="test_token")

    last_updated_time = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    acc_returned = models.Account(
        item_id=item.id,
        plaid_account_id="acc_will_be_returned",
        name="Returned Account",
        type="depository",
        current_balance=Decimal("100.00"),
        is_active=True,
    )
    acc_missing = models.Account(
        item_id=item.id,
        plaid_account_id="acc_missing_from_plaid",
        name="Missing Account",
        type="depository",
        current_balance=Decimal("500.00"),
        available_balance=Decimal("450.00"),
        balance_last_updated=last_updated_time,
        is_active=True,
    )
    db_session.add_all([acc_returned, acc_missing])
    db_session.commit()

    # Remote payload includes ONLY acc_will_be_returned
    remote_acct = _make_mock_account(
        account_id="acc_will_be_returned",
        name="Returned Account",
        current_balance=150.00,
    )
    mock_resp = _make_mock_response([remote_acct])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json()["accounts_updated"] == 1

    # Verify acc_missing is completely untouched
    db_session.refresh(acc_missing)
    assert acc_missing.current_balance == Decimal("500.00")
    assert acc_missing.available_balance == Decimal("450.00")
    assert acc_missing.is_active is True
    assert acc_missing.balance_last_updated == last_updated_time

    # Verify acc_returned was updated
    db_session.refresh(acc_returned)
    assert acc_returned.current_balance == Decimal("150.00")


def test_sync_accounts_multiple_accounts_count_semantics(client, db_session):
    """
    Verify that accounts_updated counts every account returned in the Plaid response,
    even when an account's data has not changed.
    """
    item = create_plaid_item(db_session, plaid_item_id="item_multi", access_token="test_token")

    # Seed an account with exact same values as remote
    existing_acc = models.Account(
        item_id=item.id,
        plaid_account_id="acc_identical",
        name="Checking",
        mask="1111",
        type="depository",
        subtype="checking",
        current_balance=Decimal("100.00"),
        available_balance=Decimal("100.00"),
        currency="USD",
        is_active=True,
    )
    db_session.add(existing_acc)
    db_session.commit()

    # Return 2 accounts: 1 existing identical, 1 brand new
    remote_1 = _make_mock_account("acc_identical", name="Checking", mask="1111", current_balance=100.0, available_balance=100.0)
    remote_2 = _make_mock_account("acc_new_brand", name="Savings", mask="2222", current_balance=500.0, available_balance=500.0)
    mock_resp = _make_mock_response([remote_1, remote_2])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    # Both are counted in accounts_updated (count = 2)
    assert resp.json() == {"status": "ok", "accounts_updated": 2}


# ---------------------------------------------------------------------------
# 17, 18, & 19. Flush, Commit, and API-Before-Write Ordering
# ---------------------------------------------------------------------------

def test_sync_accounts_api_failure_causes_no_account_writes(client, db_session):
    """
    Verify API-before-write ordering:
    When the external Plaid API call fails, no Account mutations occur in PostgreSQL.
    """
    item = create_plaid_item(db_session, plaid_item_id="item_api_atomic", access_token="test_token")

    initial_account_count = db_session.query(models.Account).count()

    api_exc = ApiException(status=500, reason="Plaid Internal Error")
    api_exc.body = '{"error_code": "INTERNAL_SERVER_ERROR"}'

    with patch("backend.access.plaid_access.client.accounts_get", side_effect=api_exc):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    # No new account was created or staged
    assert db_session.query(models.Account).count() == initial_account_count


def test_sync_accounts_flush_failure_bubbles_to_500(client, db_session):
    """
    Characterize flush behavior:
    sync_accounts_and_balances executes db.flush() at the conclusion of the loop.
    If db.flush() fails (e.g. database error), it is caught by the router's generic
    Exception handler and returned as HTTP 500.
    """
    item = create_plaid_item(db_session, plaid_item_id="item_flush_test", access_token="test_token")

    remote_acct = _make_mock_account("acc_flush_fail")
    mock_resp = _make_mock_response([remote_acct])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch.object(db_session, "flush", side_effect=RuntimeError("Flush DB Connection Severed")):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Flush DB Connection Severed"}
    # Verify account was not committed
    assert db_session.query(models.Account).filter_by(plaid_account_id="acc_flush_fail").first() is None


def test_sync_accounts_commit_failure_bubbles_to_500(client, db_session):
    """
    Characterize commit failure:
    - sync_accounts_and_balances flushes before commit
    - db.commit() raises an exception
    - Router catches Exception, prints traceback, and raises HTTP 500 with detail=str(e)
    - Router does NOT call db.rollback() internally (relying on get_db finally teardown)
    - In an independent session, uncommitted flushed rows are not persisted
    """
    item = create_plaid_item(db_session, plaid_item_id="item_commit_test", access_token="test_token")

    remote_acct = _make_mock_account("acc_commit_fail")
    mock_resp = _make_mock_response([remote_acct])

    with patch("backend.access.plaid_access.client.accounts_get", return_value=mock_resp), \
         patch.object(db_session, "commit", side_effect=RuntimeError("Commit Constraint Conflict")):
        resp = client.post("/plaid/sync_accounts", json={"item_id": str(item.id)})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Commit Constraint Conflict"}

    # An independent database session confirms the transaction was never committed to PostgreSQL
    from backend.database import SessionLocal
    independent_session = SessionLocal()
    try:
        assert independent_session.query(models.Account).filter_by(plaid_account_id="acc_commit_fail").first() is None
    finally:
        independent_session.close()

    # And rolling back the test session clears the uncommitted in-transaction changes
    db_session.rollback()
    assert db_session.query(models.Account).filter_by(plaid_account_id="acc_commit_fail").first() is None
