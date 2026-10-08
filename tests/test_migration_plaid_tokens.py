"""
Integration tests for Plaid token storage, migration, and runtime sync workflows.
"""

import base64
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from sqlalchemy import text

from backend import models
from backend.access import plaid_item_access
from backend.database import migrate_plaid_token_encryption
from backend.managers.plaid_account_sync_manager import sync_plaid_accounts
from backend.managers.plaid_transaction_sync_manager import sync_plaid_transactions
from backend.security import ENCRYPTION_PREFIX_V1, decrypt_token, encrypt_token


# ===========================================================================
# 1. Real Storage Test (Section 21)
# ===========================================================================

def test_real_storage_path_encrypts_and_recovers_token(db_session):
    """
    Plaintext token -> create_plaid_item -> database:
    - Stored value starts with enc:v1:
    - Plaintext does not equal stored value
    - Decrypting stored value recovers exact plaintext
    """
    plaintext_token = "access-sandbox-live-storage-test-123"
    item = plaid_item_access.create_plaid_item(
        db=db_session,
        plaid_item_id="item_live_storage_01",
        access_token=plaintext_token,
    )
    db_session.commit()

    db_item = db_session.query(models.PlaidItem).filter_by(id=item.id).one()
    stored_val = db_item.plaid_access_token_encrypted

    assert stored_val.startswith(ENCRYPTION_PREFIX_V1)
    assert stored_val != plaintext_token
    assert decrypt_token(stored_val) == plaintext_token


# ===========================================================================
# 2. Migration Tests (Section 22)
# ===========================================================================

def test_migration_converts_legacy_base64_row(db_session, monkeypatch):
    raw_token = "access-sandbox-historical-row-1"
    legacy_base64 = base64.b64encode(raw_token.encode("utf-8")).decode("utf-8")

    item = models.PlaidItem(
        plaid_item_id="item_legacy_01",
        plaid_access_token_encrypted=legacy_base64,
    )
    db_session.add(item)
    db_session.commit()

    from backend.database import engine
    result = migrate_plaid_token_encryption(engine)
    assert result is True

    db_session.expire_all()
    migrated_item = db_session.query(models.PlaidItem).filter_by(id=item.id).one()
    stored = migrated_item.plaid_access_token_encrypted

    assert stored.startswith(ENCRYPTION_PREFIX_V1)
    assert decrypt_token(stored) == raw_token


def test_migration_converts_multiple_legacy_rows(db_session):
    tokens = {
        "item_multi_1": "access-token-111",
        "item_multi_2": "access-token-222",
        "item_multi_3": "access-token-333",
    }
    for item_id, tok in tokens.items():
        b64 = base64.b64encode(tok.encode("utf-8")).decode("utf-8")
        db_session.add(models.PlaidItem(plaid_item_id=item_id, plaid_access_token_encrypted=b64))
    db_session.commit()

    from backend.database import engine
    result = migrate_plaid_token_encryption(engine)
    assert result is True

    db_session.expire_all()
    for item_id, tok in tokens.items():
        row = db_session.query(models.PlaidItem).filter_by(plaid_item_id=item_id).one()
        assert row.plaid_access_token_encrypted.startswith(ENCRYPTION_PREFIX_V1)
        assert decrypt_token(row.plaid_access_token_encrypted) == tok


def test_migration_preserves_existing_encrypted_row_byte_for_byte(db_session):
    raw_token = "access-existing-enc"
    existing_ciphertext = encrypt_token(raw_token)

    item = models.PlaidItem(
        plaid_item_id="item_existing_enc",
        plaid_access_token_encrypted=existing_ciphertext,
    )
    db_session.add(item)
    db_session.commit()

    from backend.database import engine
    result = migrate_plaid_token_encryption(engine)
    assert result is False  # No legacy rows to migrate

    db_session.expire_all()
    row = db_session.query(models.PlaidItem).filter_by(id=item.id).one()
    assert row.plaid_access_token_encrypted == existing_ciphertext


def test_migration_mixed_current_and_legacy(db_session):
    existing_cipher = encrypt_token("access-already-enc")
    legacy_b64 = base64.b64encode(b"access-needs-mig").decode("utf-8")

    item1 = models.PlaidItem(plaid_item_id="item_mixed_1", plaid_access_token_encrypted=existing_cipher)
    item2 = models.PlaidItem(plaid_item_id="item_mixed_2", plaid_access_token_encrypted=legacy_b64)
    db_session.add_all([item1, item2])
    db_session.commit()

    from backend.database import engine
    result = migrate_plaid_token_encryption(engine)
    assert result is True

    db_session.expire_all()
    row1 = db_session.query(models.PlaidItem).filter_by(id=item1.id).one()
    row2 = db_session.query(models.PlaidItem).filter_by(id=item2.id).one()

    # row1 byte-for-byte identical
    assert row1.plaid_access_token_encrypted == existing_cipher
    # row2 converted to enc:v1:
    assert row2.plaid_access_token_encrypted.startswith(ENCRYPTION_PREFIX_V1)
    assert decrypt_token(row2.plaid_access_token_encrypted) == "access-needs-mig"


def test_migration_idempotent_second_run(db_session):
    legacy_b64 = base64.b64encode(b"access-idempotent").decode("utf-8")
    item = models.PlaidItem(plaid_item_id="item_idem", plaid_access_token_encrypted=legacy_b64)
    db_session.add(item)
    db_session.commit()

    from backend.database import engine
    res1 = migrate_plaid_token_encryption(engine)
    assert res1 is True

    db_session.expire_all()
    first_ciphertext = db_session.query(models.PlaidItem).filter_by(id=item.id).one().plaid_access_token_encrypted

    # Second run must return False and preserve ciphertext byte-for-byte
    res2 = migrate_plaid_token_encryption(engine)
    assert res2 is False

    db_session.expire_all()
    second_ciphertext = db_session.query(models.PlaidItem).filter_by(id=item.id).one().plaid_access_token_encrypted
    assert first_ciphertext == second_ciphertext


def test_migration_malformed_legacy_rolls_back_entirely(db_session):
    valid_b64 = base64.b64encode(b"access-valid-legacy").decode("utf-8")
    malformed_raw = "!!!NOT_VALID_BASE64_PADDING!!!"

    item1 = models.PlaidItem(plaid_item_id="item_rollback_valid", plaid_access_token_encrypted=valid_b64)
    item2 = models.PlaidItem(plaid_item_id="item_rollback_bad", plaid_access_token_encrypted=malformed_raw)
    db_session.add_all([item1, item2])
    db_session.commit()

    from backend.database import engine
    with pytest.raises(RuntimeError, match="contains malformed legacy token data. Entire migration rolled back"):
        migrate_plaid_token_encryption(engine)

    db_session.expire_all()
    row1 = db_session.query(models.PlaidItem).filter_by(id=item1.id).one()
    row2 = db_session.query(models.PlaidItem).filter_by(id=item2.id).one()

    # Valid row must remain strictly in its original legacy state (no partial update)
    assert row1.plaid_access_token_encrypted == valid_b64
    assert row2.plaid_access_token_encrypted == malformed_raw


def test_migration_unsupported_version_aborts_without_modification(db_session):
    unsupported = "enc:v2:future_version_token"
    item = models.PlaidItem(plaid_item_id="item_unsupported_v2", plaid_access_token_encrypted=unsupported)
    db_session.add(item)
    db_session.commit()

    from backend.database import engine
    with pytest.raises(RuntimeError, match="has unsupported encrypted format"):
        migrate_plaid_token_encryption(engine)

    db_session.expire_all()
    row = db_session.query(models.PlaidItem).filter_by(id=item.id).one()
    assert row.plaid_access_token_encrypted == unsupported


def test_migration_missing_key_raises_when_plaid_items_present(db_session, monkeypatch):
    b64 = base64.b64encode(b"access-no-key").decode("utf-8")
    item = models.PlaidItem(plaid_item_id="item_no_key", plaid_access_token_encrypted=b64)
    db_session.add(item)
    db_session.commit()

    monkeypatch.delenv("PLAID_TOKEN_ENCRYPTION_KEY", raising=False)

    from backend.database import engine
    with pytest.raises(RuntimeError, match="PLAID_TOKEN_ENCRYPTION_KEY environment variable is not configured"):
        migrate_plaid_token_encryption(engine)


def test_migration_missing_key_allowed_when_zero_plaid_items(db_session, monkeypatch):
    # Verify table is empty
    db_session.execute(text("TRUNCATE TABLE plaid_items CASCADE;"))
    db_session.commit()

    monkeypatch.delenv("PLAID_TOKEN_ENCRYPTION_KEY", raising=False)

    from backend.database import engine
    result = migrate_plaid_token_encryption(engine)
    assert result is False


# ===========================================================================
# 3. Runtime Sync Tests (Section 23)
# ===========================================================================

def test_runtime_account_sync_decrypts_before_plaid_sdk_call(db_session):
    raw_token = "access-sandbox-acct-sync-raw"
    item = plaid_item_access.create_plaid_item(
        db=db_session,
        plaid_item_id="item_acct_sync_rt",
        access_token=raw_token,
    )
    db_session.commit()

    with patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]) as mock_fetch:
        result = sync_plaid_accounts(db=db_session, item_id=item.id)

    mock_fetch.assert_called_once_with(raw_token)
    assert result.accounts_updated == 0


def test_runtime_transaction_sync_decrypts_before_api_calls(db_session):
    raw_token = "access-sandbox-tx-sync-raw"
    item = plaid_item_access.create_plaid_item(
        db=db_session,
        plaid_item_id="item_tx_sync_rt",
        access_token=raw_token,
    )
    db_session.commit()

    mock_page = MagicMock()
    mock_page.added = []
    mock_page.modified = []
    mock_page.removed = []
    mock_page.has_more = False
    mock_page.next_cursor = "cursor_end"

    with patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]) as mock_accts, \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=mock_page) as mock_txs:
        result = sync_plaid_transactions(db=db_session, item_id=item.id)

    mock_accts.assert_called_once_with(raw_token)
    mock_txs.assert_called_once_with(access_token=raw_token, cursor=None)
    assert result.next_cursor == "cursor_end"
