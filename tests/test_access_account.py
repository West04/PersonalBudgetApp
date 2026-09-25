"""
Unit tests for Account ResourceAccess (backend/access/account_access.py)
focusing on stage_or_update_plaid_account.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4
import pytest

from backend import models
from backend.access import account_access
from backend.crud.plaid import create_plaid_item


def test_stage_or_update_new_account_creation_and_defaults(db_session):
    item = create_plaid_item(db_session, plaid_item_id="item_acc_test", access_token="tok")
    now = datetime.now(timezone.utc)

    account = account_access.stage_or_update_plaid_account(
        db=db_session,
        item_id=item.id,
        plaid_account_id="new_plaid_acc_1",
        name="New Account",
        mask="1234",
        account_type="depository",
        subtype="checking",
        current_balance=Decimal("150.00"),
        available_balance=Decimal("140.00"),
        currency="USD",
        balance_last_updated=now,
    )

    # In-memory staged account
    assert account.item_id == item.id
    assert account.plaid_account_id == "new_plaid_acc_1"
    assert account.name == "New Account"
    assert account.mask == "1234"
    assert account.type == "depository"
    assert account.subtype == "checking"
    assert account.is_active is True
    assert account.current_balance == Decimal("150.00")
    assert account.available_balance == Decimal("140.00")
    assert account.currency == "USD"
    assert account.balance_last_updated == now

    # Flush so ORM default column evaluation happens
    db_session.flush()
    assert account.starting_balance == Decimal("0.00")


def test_stage_or_update_new_account_fallbacks(db_session):
    item = create_plaid_item(db_session, plaid_item_id="item_acc_fb", access_token="tok")
    now = datetime.now(timezone.utc)

    account = account_access.stage_or_update_plaid_account(
        db=db_session,
        item_id=item.id,
        plaid_account_id="new_plaid_acc_empty",
        name="",  # falsy -> "Account"
        mask=None,
        account_type=None,  # falsy -> "unknown"
        subtype=None,
        current_balance=Decimal("0.00"),
        available_balance=None,
        currency="USD",
        balance_last_updated=now,
    )

    assert account.name == "Account"
    assert account.type == "unknown"
    assert account.mask is None
    assert account.subtype is None
    assert account.available_balance is None


def test_stage_or_update_exact_identity_and_preservation_of_mismatched_item_id(db_session):
    item1 = create_plaid_item(db_session, plaid_item_id="item_1", access_token="tok1")
    item2 = create_plaid_item(db_session, plaid_item_id="item_2", access_token="tok2")

    existing = models.Account(
        item_id=item1.id,
        plaid_account_id="shared_acc_id",
        name="Item 1 Name",
        type="depository",
        starting_balance=Decimal("200.00"),
        is_active=False,
        current_balance=Decimal("50.00"),
    )
    db_session.add(existing)
    db_session.commit()

    now = datetime.now(timezone.utc)
    updated = account_access.stage_or_update_plaid_account(
        db=db_session,
        item_id=item2.id,  # Supplying item2
        plaid_account_id="shared_acc_id",
        name="Updated Name",
        mask="9999",
        account_type="credit",
        subtype="credit card",
        current_balance=Decimal("75.00"),
        available_balance=Decimal("25.00"),
        currency="USD",
        balance_last_updated=now,
    )

    # Updated returned account is the same record
    assert updated.id == existing.id
    # Mismatched item_id is preserved!
    assert updated.item_id == item1.id
    # Preserved invariant fields
    assert updated.starting_balance == Decimal("200.00")
    assert updated.is_active is False
    # Updated fields
    assert updated.name == "Updated Name"
    assert updated.type == "credit"
    assert updated.mask == "9999"
    assert updated.current_balance == Decimal("75.00")


def test_stage_or_update_existing_account_fallbacks_and_none_overwrites(db_session):
    item = create_plaid_item(db_session, plaid_item_id="item_asym", access_token="tok")

    existing = models.Account(
        item_id=item.id,
        plaid_account_id="asym_acc_id",
        name="Persistent Local Name",
        mask="5555",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("10.00"),
        current_balance=Decimal("100.00"),
        available_balance=Decimal("90.00"),
        is_active=True,
    )
    db_session.add(existing)
    db_session.commit()

    now = datetime.now(timezone.utc)
    updated = account_access.stage_or_update_plaid_account(
        db=db_session,
        item_id=item.id,
        plaid_account_id="asym_acc_id",
        name="",   # falsy -> preserve existing local name
        mask=None, # None -> overwrite local mask with None
        account_type=None,  # falsy -> preserve existing local type
        subtype=None,       # None -> overwrite local subtype with None
        current_balance=Decimal("120.00"),
        available_balance=None,  # None -> overwrite available_balance with None
        currency="USD",
        balance_last_updated=now,
    )

    assert updated.name == "Persistent Local Name"
    assert updated.type == "depository"
    assert updated.mask is None
    assert updated.subtype is None
    assert updated.available_balance is None
    assert updated.current_balance == Decimal("120.00")
    assert updated.balance_last_updated == now


def test_stage_or_update_does_not_flush_or_commit(db_session):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    now = datetime.now(timezone.utc)
    account = account_access.stage_or_update_plaid_account(
        db=mock_db,
        item_id=uuid4(),
        plaid_account_id="mock_acc",
        name="Mock Account",
        mask="1111",
        account_type="depository",
        subtype="checking",
        current_balance=Decimal("10.00"),
        available_balance=Decimal("10.00"),
        currency="USD",
        balance_last_updated=now,
    )

    mock_db.add.assert_called_once_with(account)
    mock_db.flush.assert_not_called()
    mock_db.commit.assert_not_called()


def test_get_account_by_plaid_account_id_found(db_session):
    account = models.Account(
        name="Plaid Target Account",
        type="depository",
        plaid_account_id="plaid_target_123",
        current_balance=Decimal("250.00"),
    )
    db_session.add(account)
    db_session.commit()

    retrieved = account_access.get_account_by_plaid_account_id(db_session, "plaid_target_123")
    assert retrieved is not None
    assert retrieved.id == account.id
    assert retrieved.name == "Plaid Target Account"
    assert retrieved.plaid_account_id == "plaid_target_123"


def test_get_account_by_plaid_account_id_missing(db_session):
    retrieved = account_access.get_account_by_plaid_account_id(db_session, "non_existent_plaid_id")
    assert retrieved is None


def test_get_account_by_plaid_account_id_exact_match(db_session):
    account1 = models.Account(
        name="Account 1",
        type="depository",
        plaid_account_id="acc_prefix",
    )
    account2 = models.Account(
        name="Account 2",
        type="depository",
        plaid_account_id="acc_prefix_suffix",
    )
    db_session.add_all([account1, account2])
    db_session.commit()

    match1 = account_access.get_account_by_plaid_account_id(db_session, "acc_prefix")
    assert match1 is not None
    assert match1.id == account1.id

    match2 = account_access.get_account_by_plaid_account_id(db_session, "acc_prefix_suffix")
    assert match2 is not None
    assert match2.id == account2.id


def test_get_account_by_plaid_account_id_no_commit():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    result = account_access.get_account_by_plaid_account_id(mock_db, "mock_plaid_id")
    assert result is None
    mock_db.commit.assert_not_called()
    mock_db.flush.assert_not_called()
