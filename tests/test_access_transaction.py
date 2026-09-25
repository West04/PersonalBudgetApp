"""
Unit tests for Transaction ResourceAccess (backend/access/transaction_access.py)
focusing on Plaid transaction lookup, staging upsert, and staged deletion.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4
import pytest

from backend import models
from backend.access import transaction_access


# 1. Lookup: get_transaction_by_plaid_id
def test_get_transaction_by_plaid_id_found(db_session):
    account = models.Account(name="Test Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    txn = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="plaid_tx_find_me",
        description="Lookup Test",
        amount=Decimal("12.34"),
        date=date(2026, 6, 1),
    )
    db_session.add(txn)
    db_session.commit()

    found = transaction_access.get_transaction_by_plaid_id(db_session, "plaid_tx_find_me")
    assert found is not None
    assert found.transaction_id == txn.transaction_id
    assert found.plaid_transaction_id == "plaid_tx_find_me"


def test_get_transaction_by_plaid_id_missing(db_session):
    result = transaction_access.get_transaction_by_plaid_id(db_session, "non_existent_plaid_tx")
    assert result is None


# 2. Insert: stage_or_update_plaid_transaction (new record)
def test_stage_or_update_insert_semantics(db_session):
    account = models.Account(name="Insert Acc", type="depository")
    db_session.add(account)
    db_session.commit()

    dt_now = datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)
    staged = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="tx_new_plaid_123",
        account_id=account.id,
        description="Coffee Shop",
        amount=Decimal("4.50"),
        transaction_date=date(2026, 6, 15),
        transaction_datetime=dt_now,
        pending=True,
    )

    # Invariants and fields
    assert staged.plaid_transaction_id == "tx_new_plaid_123"
    assert staged.account_id == account.id
    assert staged.category_id is None
    assert staged.is_transfer is False
    assert staged.description == "Coffee Shop"
    assert staged.amount == Decimal("4.50")
    assert staged.date == date(2026, 6, 15)
    assert staged.datetime == dt_now
    assert staged.pending is True

    # Staged only (not committed)
    assert staged in db_session.new


def test_stage_or_update_insert_does_not_commit_or_refresh():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    result = transaction_access.stage_or_update_plaid_transaction(
        db=mock_db,
        plaid_transaction_id="tx_no_commit",
        account_id=uuid4(),
        description="No Commit",
        amount=Decimal("10.00"),
        transaction_date=date(2026, 6, 15),
    )

    mock_db.add.assert_called_once_with(result)
    mock_db.commit.assert_not_called()
    mock_db.refresh.assert_not_called()


# 3. Update: stage_or_update_plaid_transaction (existing record)
def test_stage_or_update_update_semantics_and_preservation(db_session):
    account1 = models.Account(name="Acc 1", type="depository")
    account2 = models.Account(name="Acc 2", type="depository")
    cat_group = models.CategoryGroup(name="Food")
    db_session.add_all([account1, account2, cat_group])
    db_session.flush()

    category = models.Category(name="Dining Out", group_id=cat_group.category_group_id)
    db_session.add(category)
    db_session.flush()

    existing = models.Transaction(
        account_id=account1.id,
        category_id=category.category_id,
        plaid_transaction_id="tx_existing_plaid",
        description="Original Desc",
        amount=Decimal("20.00"),
        date=date(2026, 6, 1),
        datetime=None,
        pending=True,
        is_transfer=True,
    )
    db_session.add(existing)
    db_session.commit()

    original_tx_id = existing.transaction_id

    # Call update with account2 (different account), new description, amount, date, datetime, pending
    new_dt = datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc)
    updated = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="tx_existing_plaid",
        account_id=account2.id,  # Supplying a different account_id
        description="Updated Desc",
        amount=Decimal("25.00"),
        transaction_date=date(2026, 6, 2),
        transaction_datetime=new_dt,
        pending=False,
    )

    # Mutable fields updated
    assert updated.description == "Updated Desc"
    assert updated.amount == Decimal("25.00")
    assert updated.date == date(2026, 6, 2)
    assert updated.datetime == new_dt
    assert updated.pending is False

    # Strictly preserved fields
    assert updated.transaction_id == original_tx_id
    assert updated.plaid_transaction_id == "tx_existing_plaid"
    assert updated.account_id == account1.id  # NOT account2.id!
    assert updated.category_id == category.category_id  # preserved!
    assert updated.is_transfer is True  # preserved!


def test_stage_or_update_update_does_not_commit_or_refresh():
    mock_db = MagicMock()
    mock_existing = MagicMock(spec=models.Transaction)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_existing

    result = transaction_access.stage_or_update_plaid_transaction(
        db=mock_db,
        plaid_transaction_id="tx_existing",
        account_id=uuid4(),
        description="Update Check",
        amount=Decimal("30.00"),
        transaction_date=date(2026, 6, 2),
    )

    assert result == mock_existing
    mock_db.add.assert_called_once_with(mock_existing)
    mock_db.commit.assert_not_called()
    mock_db.refresh.assert_not_called()


# 4. Deletion: stage_delete_transaction_by_plaid_id
def test_stage_delete_found(db_session):
    account = models.Account(name="Delete Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    txn = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_to_delete",
        description="Delete Me",
        amount=Decimal("10.00"),
        date=date(2026, 6, 1),
    )
    db_session.add(txn)
    db_session.commit()

    deleted = transaction_access.stage_delete_transaction_by_plaid_id(db_session, "tx_to_delete")
    assert deleted is True
    assert txn in db_session.deleted


def test_stage_delete_missing(db_session):
    deleted = transaction_access.stage_delete_transaction_by_plaid_id(db_session, "tx_not_there")
    assert deleted is False


def test_stage_delete_does_not_commit():
    mock_db = MagicMock()
    mock_existing = MagicMock(spec=models.Transaction)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_existing

    result = transaction_access.stage_delete_transaction_by_plaid_id(mock_db, "tx_del_no_commit")
    assert result is True
    mock_db.delete.assert_called_once_with(mock_existing)
    mock_db.commit.assert_not_called()

    # When missing
    mock_db.reset_mock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    result_missing = transaction_access.stage_delete_transaction_by_plaid_id(mock_db, "tx_del_missing")
    assert result_missing is False
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()
