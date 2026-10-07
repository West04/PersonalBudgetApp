"""
Tests for ResourceAccess functions supporting account reconciliation:
- account_access.update_account_reconciliation_metadata
- transaction_access.get_unreconciled_transactions_for_account
- transaction_access.set_transaction_cleared
- transaction_access.mark_transactions_as_reconciled
- transaction_access.delete_manual_transaction protection for reconciled transactions
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest

from backend import models
from backend.access import account_access, transaction_access
from backend.managers import manual_transaction_manager


def test_update_account_reconciliation_metadata(db_session):
    account = models.Account(
        name="Checking",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("1000.00"),
    )
    db_session.add(account)
    db_session.commit()

    updated = account_access.update_account_reconciliation_metadata(
        db=db_session,
        account_id=account.id,
        last_reconciled_date=date(2026, 10, 31),
        last_reconciled_balance=Decimal("1450.50"),
    )

    assert updated is not None
    assert updated.last_reconciled_date == date(2026, 10, 31)
    assert updated.last_reconciled_balance == Decimal("1450.50")

    # Verify reload from DB
    reloaded = account_access.get_account_by_id(db_session, account.id)
    assert reloaded.last_reconciled_date == date(2026, 10, 31)
    assert reloaded.last_reconciled_balance == Decimal("1450.50")


def test_get_unreconciled_transactions_date_filtering(db_session):
    account = models.Account(name="Checking", type="depository")
    db_session.add(account)
    db_session.commit()

    # t1: before ending date, unreconciled -> included
    t1 = models.Transaction(
        account_id=account.id,
        description="Tx 1",
        amount=Decimal("10.00"),
        date=date(2026, 10, 15),
        is_reconciled=False,
    )
    # t2: on ending date, unreconciled -> included
    t2 = models.Transaction(
        account_id=account.id,
        description="Tx 2",
        amount=Decimal("20.00"),
        date=date(2026, 10, 31),
        is_reconciled=False,
    )
    # t3: after ending date -> excluded
    t3 = models.Transaction(
        account_id=account.id,
        description="Tx 3",
        amount=Decimal("30.00"),
        date=date(2026, 11, 1),
        is_reconciled=False,
    )
    # t4: on ending date, already reconciled -> excluded
    t4 = models.Transaction(
        account_id=account.id,
        description="Tx 4",
        amount=Decimal("40.00"),
        date=date(2026, 10, 20),
        is_reconciled=True,
    )

    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    txns = transaction_access.get_unreconciled_transactions_for_account(
        db=db_session,
        account_id=account.id,
        ending_date=date(2026, 10, 31),
    )

    txn_ids = [t.transaction_id for t in txns]
    assert txn_ids == [t1.transaction_id, t2.transaction_id]


def test_set_transaction_cleared_and_reconciled_lock(db_session):
    account = models.Account(name="Checking", type="depository")
    db_session.add(account)
    db_session.commit()

    t = models.Transaction(
        account_id=account.id,
        description="Coffee",
        amount=Decimal("5.00"),
        date=date(2026, 10, 1),
        is_cleared=False,
        is_reconciled=False,
    )
    db_session.add(t)
    db_session.commit()

    # Toggle cleared to True
    res = transaction_access.set_transaction_cleared(db_session, t.transaction_id, True)
    assert res.is_cleared is True

    # Toggle cleared to False
    res2 = transaction_access.set_transaction_cleared(db_session, t.transaction_id, False)
    assert res2.is_cleared is False

    # Mark reconciled
    t.is_reconciled = True
    db_session.commit()

    # Attempting to toggle cleared on reconciled transaction must raise ValueError
    with pytest.raises(ValueError, match="already reconciled"):
        transaction_access.set_transaction_cleared(db_session, t.transaction_id, True)


def test_delete_reconciled_transaction_blocked(db_session):
    account = models.Account(name="Checking", type="depository")
    db_session.add(account)
    db_session.commit()

    t = models.Transaction(
        account_id=account.id,
        description="Locked Tx",
        amount=Decimal("100.00"),
        date=date(2026, 10, 1),
        is_reconciled=True,
    )
    db_session.add(t)
    db_session.commit()

    with pytest.raises(ValueError, match="Cannot delete a reconciled transaction"):
        transaction_access.delete_manual_transaction(db_session, t.transaction_id)

    # Verify transaction still exists
    assert transaction_access.get_transaction_by_id(db_session, t.transaction_id) is not None


def test_get_unreconciled_transactions_excludes_pending(db_session):
    account = models.Account(name="Checking", type="depository")
    db_session.add(account)
    db_session.commit()

    posted = models.Transaction(
        account_id=account.id,
        description="Posted Tx",
        amount=Decimal("25.00"),
        date=date(2026, 10, 10),
        pending=False,
        is_reconciled=False,
    )
    pending_tx = models.Transaction(
        account_id=account.id,
        description="Pending Plaid Tx",
        amount=Decimal("35.00"),
        date=date(2026, 10, 10),
        pending=True,
        is_reconciled=False,
    )
    db_session.add_all([posted, pending_tx])
    db_session.commit()

    txns = transaction_access.get_unreconciled_transactions_for_account(
        db=db_session,
        account_id=account.id,
        ending_date=date(2026, 10, 31),
    )
    ids = [t.transaction_id for t in txns]
    assert posted.transaction_id in ids
    assert pending_tx.transaction_id not in ids


def test_set_transaction_cleared_rejects_pending(db_session):
    account = models.Account(name="Checking", type="depository")
    db_session.add(account)
    db_session.commit()

    pending_tx = models.Transaction(
        account_id=account.id,
        description="Pending Tx",
        amount=Decimal("50.00"),
        date=date(2026, 10, 10),
        pending=True,
        is_cleared=False,
        is_reconciled=False,
    )
    db_session.add(pending_tx)
    db_session.commit()

    # Attempting to mark pending transaction cleared must raise ValueError
    with pytest.raises(ValueError, match="Cannot mark a pending transaction as cleared"):
        transaction_access.set_transaction_cleared(db_session, pending_tx.transaction_id, True)

    assert pending_tx.is_cleared is False


def test_update_transaction_reconciled_financial_guard(db_session):
    account1 = models.Account(name="Checking 1", type="depository")
    account2 = models.Account(name="Checking 2", type="depository")
    group = models.CategoryGroup(name="General")
    db_session.add_all([account1, account2, group])
    db_session.flush()

    cat1 = models.Category(name="Food", group_id=group.category_group_id)
    cat2 = models.Category(name="Transport", group_id=group.category_group_id)
    db_session.add_all([cat1, cat2])
    db_session.flush()

    tx = models.Transaction(
        account_id=account1.id,
        category_id=cat1.category_id,
        description="Initial Coffee",
        amount=Decimal("5.00"),
        date=date(2026, 10, 5),
        is_reviewed=False,
        is_cleared=True,
        is_reconciled=True,
    )
    db_session.add(tx)
    db_session.commit()

    # 1. Prohibited: changing amount
    with pytest.raises(ValueError, match="Cannot modify financial fields"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"amount": Decimal("10.00")},
        )

    # 2. Prohibited: changing date
    with pytest.raises(ValueError, match="Cannot modify financial fields"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"date": date(2026, 10, 6)},
        )

    # 3. Prohibited: changing account_id
    with pytest.raises(ValueError, match="Cannot modify financial fields"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"account_id": account2.id},
        )

    # 4. Permitted: changing category_id
    up1 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"category_id": cat2.category_id},
    )
    assert up1.category_id == cat2.category_id

    # 5. Permitted: changing description
    up2 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"description": "Updated Coffee Note"},
    )
    assert up2.description == "Updated Coffee Note"

    # 6. Permitted: changing is_reviewed
    up3 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"is_reviewed": True},
    )
    assert up3.is_reviewed is True

    # 7. Permitted: passing same financial values (no mutation)
    up4 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"amount": Decimal("5.00"), "date": date(2026, 10, 5), "account_id": account1.id},
    )
    assert up4.amount == Decimal("5.00")


def test_schema_defaults_and_migration_idempotence(db_session):
    from backend.database import migrate_reconciliation_state, engine

    # Verify default values on newly constructed models without explicit values
    acc = models.Account(name="Fresh Account", type="depository")
    db_session.add(acc)
    db_session.commit()
    assert acc.last_reconciled_date is None
    assert acc.last_reconciled_balance is None

    tx = models.Transaction(
        account_id=acc.id,
        description="Fresh Tx",
        amount=Decimal("12.34"),
        date=date(2026, 10, 1),
    )
    db_session.add(tx)
    db_session.commit()
    assert tx.is_cleared is False
    assert tx.is_reconciled is False

    # Verify migration idempotence: re-running migration on existing database returns False
    # and does NOT alter or overwrite any data
    acc.last_reconciled_date = date(2026, 10, 20)
    acc.last_reconciled_balance = Decimal("500.00")
    tx.is_reconciled = True
    tx.is_cleared = True
    db_session.commit()

    applied = migrate_reconciliation_state(engine)
    # When already applied, returns False
    assert applied is False

    # State is preserved without overwrite
    db_session.refresh(acc)
    db_session.refresh(tx)
    assert acc.last_reconciled_date == date(2026, 10, 20)
    assert acc.last_reconciled_balance == Decimal("500.00")
    assert tx.is_reconciled is True
    assert tx.is_cleared is True
