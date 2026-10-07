"""
Unit tests for Transaction ResourceAccess (backend/access/transaction_access.py)
focusing on Plaid transaction lookup, staging upsert, and staged deletion.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
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


def test_stage_or_update_sentinel_lookup_behavior():
    """
    Test Slice 2b sentinel semantics:
    1. Omitted existing_transaction / sentinel -> performs lookup via get_transaction_by_plaid_id.
    2. existing_transaction=None -> skips lookup (known absent) and stages new Transaction.
    3. existing_transaction=<Transaction> -> skips lookup and stages update on that Transaction.
    """
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    # Case 1: Sentinel (omitted) calls query
    result_omitted = transaction_access.stage_or_update_plaid_transaction(
        db=mock_db,
        plaid_transaction_id="tx_lookup_omitted",
        account_id=uuid4(),
        description="Lookup Omitted",
        amount=Decimal("10.00"),
        transaction_date=date(2026, 6, 15),
    )
    mock_db.query.assert_called()

    # Case 2: existing_transaction=None (Manager confirmed absent) -> does NOT query
    mock_db.reset_mock()
    result_none = transaction_access.stage_or_update_plaid_transaction(
        db=mock_db,
        plaid_transaction_id="tx_known_none",
        account_id=uuid4(),
        description="Known None",
        amount=Decimal("10.00"),
        transaction_date=date(2026, 6, 15),
        existing_transaction=None,
    )
    mock_db.query.assert_not_called()
    mock_db.add.assert_called_once_with(result_none)

    # Case 3: existing_transaction=<Transaction> -> does NOT query
    mock_db.reset_mock()
    existing_mock = MagicMock(spec=models.Transaction)
    existing_mock.is_reconciled = False
    existing_mock.transaction_id = uuid4()
    existing_mock.amount = Decimal("10.00")
    existing_mock.category_id = None
    existing_mock.is_merchant_overridden = False

    with patch("backend.access.split_access.transaction_has_splits", return_value=False):
        result_existing = transaction_access.stage_or_update_plaid_transaction(
            db=mock_db,
            plaid_transaction_id="tx_known_existing",
            account_id=uuid4(),
            description="Known Existing",
            amount=Decimal("10.00"),
            transaction_date=date(2026, 6, 15),
            existing_transaction=existing_mock,
        )
    mock_db.query.assert_not_called()
    assert result_existing is existing_mock


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


# ---------------------------------------------------------------------------
# 5. Manual CRUD Accessor Operations (Slice 10)
# ---------------------------------------------------------------------------

# 5.1 get_transaction_by_id
def test_get_transaction_by_id_found_and_eager_loads_account(db_session):
    account = models.Account(name="Access Acct", type="depository")
    db_session.add(account)
    db_session.flush()

    txn = models.Transaction(
        account_id=account.id,
        description="Access Target",
        amount=Decimal("15.50"),
        date=date(2026, 6, 10),
    )
    db_session.add(txn)
    db_session.commit()

    found = transaction_access.get_transaction_by_id(db_session, txn.transaction_id)
    assert found is not None
    assert found.transaction_id == txn.transaction_id
    assert found.description == "Access Target"
    # Account is eagerly loaded
    assert found.account is not None
    assert found.account.name == "Access Acct"


def test_get_transaction_by_id_missing(db_session):
    result = transaction_access.get_transaction_by_id(db_session, uuid4())
    assert result is None


def test_get_transaction_by_id_does_not_commit():
    mock_db = MagicMock()
    mock_existing = MagicMock(spec=models.Transaction)
    mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_existing

    res = transaction_access.get_transaction_by_id(mock_db, uuid4())
    assert res == mock_existing
    mock_db.commit.assert_not_called()
    mock_db.refresh.assert_not_called()


# 5.2 list_transactions
def test_list_transactions_filters_ordering_pagination(db_session):
    acc1 = models.Account(name="Acct 1", type="depository")
    acc2 = models.Account(name="Acct 2", type="depository")
    group = models.CategoryGroup(name="General")
    db_session.add_all([acc1, acc2, group])
    db_session.flush()

    cat1 = models.Category(name="Dining", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Gas", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2])
    db_session.commit()

    t1 = models.Transaction(account_id=acc1.id, category_id=cat1.category_id, description="Coffee", amount=Decimal("4.00"), date=date(2026, 6, 1))
    t2 = models.Transaction(account_id=acc1.id, category_id=cat2.category_id, description="Shell Gas", amount=Decimal("45.00"), date=date(2026, 6, 10))
    t3 = models.Transaction(account_id=acc2.id, category_id=None, description="Burger Bar", amount=Decimal("12.00"), date=date(2026, 6, 15))
    t4 = models.Transaction(account_id=acc2.id, category_id=cat1.category_id, description="Supermarket Coffee", amount=Decimal("18.00"), date=date(2026, 6, 20))
    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    # 1. Total before pagination & eager loaded account
    res_all = transaction_access.list_transactions(db_session, limit=2, offset=1)
    assert res_all["total"] == 4
    assert res_all["limit"] == 2
    assert res_all["offset"] == 1
    assert len(res_all["items"]) == 2
    # Eagerly loaded
    assert res_all["items"][0].account is not None

    # 2. Ordering: date DESC, transaction_id DESC
    res_ordered = transaction_access.list_transactions(db_session, limit=10, offset=0)
    items = res_ordered["items"]
    assert items[0].transaction_id == t4.transaction_id
    assert items[1].transaction_id == t3.transaction_id
    assert items[2].transaction_id == t2.transaction_id
    assert items[3].transaction_id == t1.transaction_id

    # 3. Filters: account_id, category_id, dates, uncategorized, q
    res_acc = transaction_access.list_transactions(db_session, account_id=acc1.id)
    assert res_acc["total"] == 2

    res_cat = transaction_access.list_transactions(db_session, category_id=cat1.category_id)
    assert res_cat["total"] == 2

    res_dates = transaction_access.list_transactions(db_session, start_date=date(2026, 6, 5), end_date=date(2026, 6, 16))
    assert res_dates["total"] == 2

    res_uncat = transaction_access.list_transactions(db_session, uncategorized=True)
    assert res_uncat["total"] == 1
    assert res_uncat["items"][0].transaction_id == t3.transaction_id

    res_q = transaction_access.list_transactions(db_session, q="coffee")
    assert res_q["total"] == 2


# 5.3 create_manual_transaction
def test_create_manual_transaction_commits_refreshes_and_preserves_defaults(db_session):
    account = models.Account(name="Create Acc", type="depository")
    db_session.add(account)
    db_session.commit()

    now_dt = datetime(2026, 6, 18, 14, 0, tzinfo=timezone.utc)
    new_tx = transaction_access.create_manual_transaction(
        db=db_session,
        account_id=account.id,
        category_id=None,
        description="Manual Stored",
        amount=Decimal("25.00"),
        transaction_date=date(2026, 6, 18),
        transaction_datetime=now_dt,
        pending=False,
        plaid_transaction_id="manual_plaid_tag",
    )

    # Invariants and fields
    assert new_tx.transaction_id is not None
    assert new_tx.account_id == account.id
    assert new_tx.category_id is None
    assert new_tx.description == "Manual Stored"
    assert new_tx.amount == Decimal("25.00")
    assert new_tx.date == date(2026, 6, 18)
    assert new_tx.datetime == now_dt
    assert new_tx.pending is False
    assert new_tx.is_transfer is False  # model default
    assert new_tx.plaid_transaction_id == "manual_plaid_tag"

    # Confirmed committed in DB
    db_session.expire_all()
    reloaded = db_session.query(models.Transaction).filter_by(transaction_id=new_tx.transaction_id).one()
    assert reloaded.description == "Manual Stored"


def test_create_manual_transaction_mock_commit_and_refresh():
    mock_db = MagicMock()
    account_id = uuid4()
    tx = transaction_access.create_manual_transaction(
        db=mock_db,
        account_id=account_id,
        category_id=None,
        description="Mock Create",
        amount=Decimal("10.00"),
        transaction_date=date(2026, 6, 1),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    mock_db.add.assert_called_once_with(tx)
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once_with(tx)


# 5.4 update_manual_transaction
def test_update_manual_transaction_mutations_and_preservation(db_session):
    account = models.Account(name="Update Acc", type="depository")
    group = models.CategoryGroup(name="Group")
    db_session.add_all([account, group])
    db_session.flush()

    cat1 = models.Category(name="Cat 1", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Cat 2", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2])
    db_session.commit()

    txn = models.Transaction(
        account_id=account.id,
        category_id=cat1.category_id,
        description="Original Tx",
        amount=Decimal("50.00"),
        date=date(2026, 6, 1),
        is_transfer=False,
    )
    db_session.add(txn)
    db_session.commit()

    # 1. Update category
    up1 = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=txn.transaction_id,
        update_data={"category_id": cat2.category_id},
    )
    assert up1 is not None
    assert up1.category_id == cat2.category_id
    assert up1.description == "Original Tx"  # preserved

    # 2. Clear category (None)
    up2 = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=txn.transaction_id,
        update_data={"category_id": None},
    )
    assert up2 is not None
    assert up2.category_id is None

    # 3. Update is_transfer and description
    up3 = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=txn.transaction_id,
        update_data={"is_transfer": True, "description": "New Tx Desc"},
    )
    assert up3 is not None
    assert up3.is_transfer is True
    assert up3.description == "New Tx Desc"

    # 4. Missing transaction -> None
    up_missing = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=uuid4(),
        update_data={"description": "Ghost"},
    )
    assert up_missing is None


def test_update_manual_transaction_mock_commit_and_refresh():
    mock_db = MagicMock()
    mock_tx = MagicMock(spec=models.Transaction)
    mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_tx

    res = transaction_access.update_manual_transaction(
        db=mock_db,
        transaction_id=uuid4(),
        update_data={"description": "Updated"},
    )
    assert res == mock_tx
    mock_db.add.assert_called_once_with(mock_tx)
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once_with(mock_tx)


# 5.5 delete_manual_transaction
def test_delete_manual_transaction_found_and_missing(db_session):
    account = models.Account(name="Delete Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    txn = models.Transaction(
        account_id=account.id,
        description="Delete Me",
        amount=Decimal("10.00"),
        date=date(2026, 6, 1),
    )
    db_session.add(txn)
    db_session.commit()

    # Found
    deleted = transaction_access.delete_manual_transaction(db_session, txn.transaction_id)
    assert deleted is not None
    assert deleted.transaction_id == txn.transaction_id

    # Verified removed from DB
    db_session.expire_all()
    assert db_session.query(models.Transaction).filter_by(transaction_id=txn.transaction_id).first() is None

    # Missing
    del_missing = transaction_access.delete_manual_transaction(db_session, uuid4())
    assert del_missing is None


def test_delete_manual_transaction_mock_commit():
    mock_db = MagicMock()
    mock_tx = MagicMock(spec=models.Transaction)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_tx

    res = transaction_access.delete_manual_transaction(mock_db, uuid4())
    assert res == mock_tx
    mock_db.delete.assert_called_once_with(mock_tx)
    mock_db.commit.assert_called_once()

    # Missing
    mock_db.reset_mock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    res_none = transaction_access.delete_manual_transaction(mock_db, uuid4())
    assert res_none is None
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()


# 8. Aggregation: get_transaction_net_by_account
def test_get_transaction_net_by_account_empty(db_session):
    # Empty account list returns empty dict without error
    result = transaction_access.get_transaction_net_by_account(db_session, [])
    assert result == {}


def test_get_transaction_net_by_account_aggregation(db_session):
    acc1 = models.Account(name="Acc 1", type="depository")
    acc2 = models.Account(name="Acc 2", type="depository")
    db_session.add_all([acc1, acc2])
    db_session.commit()

    tx1 = models.Transaction(account_id=acc1.id, amount=Decimal("50.00"), date=date(2026, 6, 1), description="T1")
    tx2 = models.Transaction(account_id=acc1.id, amount=Decimal("-20.00"), date=date(2026, 6, 2), description="T2")
    tx3 = models.Transaction(account_id=acc2.id, amount=Decimal("15.50"), date=date(2026, 6, 3), description="T3")
    db_session.add_all([tx1, tx2, tx3])
    db_session.commit()

    # Query all
    all_net = transaction_access.get_transaction_net_by_account(db_session)
    assert all_net[acc1.id] == Decimal("30.00")
    assert all_net[acc2.id] == Decimal("15.50")

    # Query filtered
    filtered_net = transaction_access.get_transaction_net_by_account(db_session, [acc1.id])
    assert acc1.id in filtered_net
    assert filtered_net[acc1.id] == Decimal("30.00")
    assert acc2.id not in filtered_net


