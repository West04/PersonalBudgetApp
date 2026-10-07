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
from backend.access.plaid_item_access import create_plaid_item


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


def test_get_account_by_id_found(db_session):
    account = models.Account(
        name="Target Account",
        type="depository",
    )
    db_session.add(account)
    db_session.commit()

    retrieved = account_access.get_account_by_id(db_session, account.id)
    assert retrieved is not None
    assert retrieved.id == account.id
    assert retrieved.name == "Target Account"


def test_get_account_by_id_missing(db_session):
    retrieved = account_access.get_account_by_id(db_session, uuid4())
    assert retrieved is None


def test_get_active_accounts_filters_inactive_and_orders_by_name(db_session):
    acc_active_b = models.Account(name="Bravo Account", type="depository", is_active=True)
    acc_active_a = models.Account(name="Alpha Account", type="credit", is_active=True)
    acc_inactive = models.Account(name="AAA Inactive Account", type="depository", is_active=False)

    db_session.add_all([acc_active_b, acc_active_a, acc_inactive])
    db_session.commit()

    results = account_access.get_active_accounts(db_session)
    assert len(results) == 2
    assert [a.name for a in results] == ["Alpha Account", "Bravo Account"]


def test_get_active_credit_accounts_filters_type_and_inactive(db_session):
    credit_active_b = models.Account(name="Bravo Card", type="credit", is_active=True)
    credit_active_a = models.Account(name="Alpha Card", type="credit", is_active=True)
    credit_inactive = models.Account(name="Inactive Card", type="credit", is_active=False)
    depository_active = models.Account(name="Checking Account", type="depository", is_active=True)

    db_session.add_all([credit_active_b, credit_active_a, credit_inactive, depository_active])
    db_session.commit()

    results = account_access.get_active_credit_accounts(db_session)
    assert len(results) == 2
    assert [a.name for a in results] == ["Alpha Card", "Bravo Card"]


def test_get_all_accounts_ordered_semantics(db_session):
    item = create_plaid_item(db_session, plaid_item_id="item_ord", access_token="tok")
    plaid_cred_b = models.Account(name="Bravo Credit", type="credit", item_id=item.id, plaid_account_id="p_cred")
    plaid_cred_a = models.Account(name="Alpha Credit", type="credit", item_id=item.id, plaid_account_id="p_cred_a")
    manual_dep_b = models.Account(name="Bravo Depository", type="depository", is_active=False)
    manual_dep_a = models.Account(name="Alpha Depository", type="depository", is_active=True)

    db_session.add_all([plaid_cred_b, plaid_cred_a, manual_dep_b, manual_dep_a])
    db_session.commit()

    results = account_access.get_all_accounts_ordered(db_session)
    assert len(results) == 4
    names = [a.name for a in results]
    assert names == [
        "Alpha Credit",
        "Bravo Credit",
        "Alpha Depository",
        "Bravo Depository",
    ]


def test_get_all_accounts_ordered_no_commit():
    mock_db = MagicMock()
    mock_db.query.return_value.order_by.return_value.all.return_value = []

    res = account_access.get_all_accounts_ordered(mock_db)
    assert res == []
    mock_db.commit.assert_not_called()
    mock_db.flush.assert_not_called()


def test_create_manual_account_defaults(db_session):
    acc = account_access.create_manual_account(
        db=db_session,
        name="Checking 1",
        account_type="depository",
    )

    assert acc.id is not None
    assert acc.name == "Checking 1"
    assert acc.type == "depository"
    assert acc.subtype is None
    assert acc.current_balance == Decimal("0.00")
    assert acc.starting_balance == Decimal("0.00")
    assert acc.currency == "USD"
    assert acc.is_active is True
    assert acc.plaid_account_id is None
    assert acc.item_id is None

    # Verify persisted in database
    retrieved = db_session.query(models.Account).filter(models.Account.id == acc.id).first()
    assert retrieved is not None
    assert retrieved.name == "Checking 1"


def test_create_manual_account_all_fields(db_session):
    acc = account_access.create_manual_account(
        db=db_session,
        name="Custom Account",
        account_type="investment",
        subtype="brokerage",
        current_balance=Decimal("1500.25"),
        starting_balance=Decimal("1000.00"),
        currency="USD",
        is_active=False,
    )

    assert acc.name == "Custom Account"
    assert acc.type == "investment"
    assert acc.subtype == "brokerage"
    assert acc.current_balance == Decimal("1500.25")
    assert acc.starting_balance == Decimal("1000.00")
    assert acc.currency == "USD"
    assert acc.is_active is False
    assert acc.plaid_account_id is None
    assert acc.item_id is None


def test_update_manual_account_found_and_whitelisted_fields(db_session):
    acc = models.Account(
        name="Original Name",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("10.00"),
        current_balance=Decimal("50.00"),
        is_active=True,
    )
    db_session.add(acc)
    db_session.commit()

    updated = account_access.update_manual_account(
        db=db_session,
        account_id=acc.id,
        update_data={
            "name": "Updated Name",
            "type": "credit",
            "subtype": "credit card",
            "starting_balance": Decimal("100.00"),
            "current_balance": Decimal("200.00"),
            "is_active": False,
        },
    )

    assert updated is not None
    assert updated.id == acc.id
    assert updated.name == "Updated Name"
    assert updated.type == "credit"
    assert updated.subtype == "credit card"
    assert updated.starting_balance == Decimal("100.00")
    assert updated.current_balance == Decimal("200.00")
    assert updated.is_active is False

    db_session.refresh(acc)
    assert acc.name == "Updated Name"


def test_update_manual_account_omitted_and_none_values_preserved(db_session):
    acc = models.Account(
        name="Persistent Name",
        type="depository",
        subtype="savings",
        starting_balance=Decimal("50.00"),
        current_balance=Decimal("150.00"),
        is_active=True,
    )
    db_session.add(acc)
    db_session.commit()

    # Pass explicit None for subtype and omit name/balances
    updated = account_access.update_manual_account(
        db=db_session,
        account_id=acc.id,
        update_data={"subtype": None, "is_active": False},
    )

    assert updated is not None
    assert updated.name == "Persistent Name"
    assert updated.subtype == "savings"  # None did not clear!
    assert updated.starting_balance == Decimal("50.00")
    assert updated.current_balance == Decimal("150.00")
    assert updated.is_active is False


def test_update_manual_account_preserves_plaid_fields(db_session):
    item = create_plaid_item(db_session, plaid_item_id="plaid_pres", access_token="tok")
    acc = models.Account(
        name="Plaid CC",
        type="credit",
        item_id=item.id,
        plaid_account_id="plaid_cc_persisted",
        mask="1234",
    )
    db_session.add(acc)
    db_session.commit()

    updated = account_access.update_manual_account(
        db=db_session,
        account_id=acc.id,
        update_data={"name": "Renamed Plaid CC", "plaid_account_id": "attempted_hack"},
    )

    assert updated is not None
    assert updated.name == "Renamed Plaid CC"
    assert updated.plaid_account_id == "plaid_cc_persisted"  # Not editable
    assert updated.item_id == item.id
    assert updated.mask == "1234"


def test_update_manual_account_empty_mapping(db_session):
    acc = models.Account(name="Static", type="depository")
    db_session.add(acc)
    db_session.commit()

    updated = account_access.update_manual_account(db_session, acc.id, {})
    assert updated is not None
    assert updated.name == "Static"


def test_update_manual_account_missing_returns_none(db_session):
    res = account_access.update_manual_account(db_session, uuid4(), {"name": "Ghost"})
    assert res is None


def test_delete_account_found(db_session):
    acc = models.Account(name="Dead Account", type="depository")
    db_session.add(acc)
    db_session.commit()

    success = account_access.delete_account(db_session, acc.id)
    assert success is True
    assert db_session.query(models.Account).filter(models.Account.id == acc.id).first() is None


def test_delete_account_missing_returns_false(db_session):
    success = account_access.delete_account(db_session, uuid4())
    assert success is False


