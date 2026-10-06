"""
Persistence Access tests for Split Resource Access (backend/access/split_access.py).

Verifies:
1. stage_replace_splits persists splits and replaces existing ones.
2. get_splits_for_transaction loads splits ordered by ID.
3. get_splits_for_transactions batch loads across multiple transactions.
4. transaction_has_splits returns accurate boolean.
5. count_splits_by_category counts splits referencing category.
6. stage_delete_splits deletes all splits for a transaction.
7. Cascade deletion: deleting parent transaction removes child splits via ON DELETE CASCADE.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest

from backend import models
from backend.access import split_access


def _create_account_and_tx(db_session, amount=Decimal("150.00")):
    acc = models.Account(
        name="Checking",
        type="checking",
        current_balance=Decimal("1000.00"),
    )
    db_session.add(acc)
    db_session.flush()

    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 15),
        amount=amount,
        description="Costco",
        merchant="Costco",
    )
    db_session.add(tx)
    db_session.flush()
    return acc, tx


def _get_or_create_group(db_session, name="General"):
    group = db_session.query(models.CategoryGroup).filter_by(name=name).first()
    if not group:
        group = models.CategoryGroup(name=name)
        db_session.add(group)
        db_session.flush()
    return group


def _create_category(db_session, name="Groceries"):
    group = _get_or_create_group(db_session)
    cat = models.Category(
        name=name,
        group_id=group.category_group_id,
        type="expense",
    )
    db_session.add(cat)
    db_session.flush()
    return cat


def test_split_access_crud(db_session):
    acc, tx = _create_account_and_tx(db_session)
    cat1 = _create_category(db_session, "Groceries")
    cat2 = _create_category(db_session, "Household")

    assert split_access.transaction_has_splits(db_session, tx.transaction_id) is False
    assert split_access.get_splits_for_transaction(db_session, tx.transaction_id) == []

    # 1. Stage replace splits
    created = split_access.stage_replace_splits(
        db_session,
        tx.transaction_id,
        [
            (cat1.category_id, Decimal("100.00")),
            (cat2.category_id, Decimal("50.00")),
        ],
    )
    db_session.commit()

    assert len(created) == 2
    assert split_access.transaction_has_splits(db_session, tx.transaction_id) is True

    # 2. Get splits for transaction
    splits = split_access.get_splits_for_transaction(db_session, tx.transaction_id)
    assert len(splits) == 2
    assert splits[0].amount == Decimal("100.00")
    assert splits[0].category_id == cat1.category_id
    assert splits[1].amount == Decimal("50.00")
    assert splits[1].category_id == cat2.category_id

    # 3. Count splits by category
    assert split_access.count_splits_by_category(db_session, cat1.category_id) == 1
    assert split_access.count_splits_by_category(db_session, cat2.category_id) == 1

    # 4. Replace with new allocations
    cat3 = _create_category(db_session, "Electronics")
    split_access.stage_replace_splits(
        db_session,
        tx.transaction_id,
        [
            (cat1.category_id, Decimal("70.00")),
            (cat3.category_id, Decimal("80.00")),
        ],
    )
    db_session.commit()

    updated_splits = split_access.get_splits_for_transaction(db_session, tx.transaction_id)
    assert len(updated_splits) == 2
    assert split_access.count_splits_by_category(db_session, cat2.category_id) == 0
    assert split_access.count_splits_by_category(db_session, cat3.category_id) == 1

    # 5. Delete splits
    deleted_count = split_access.stage_delete_splits(db_session, tx.transaction_id)
    db_session.commit()
    assert deleted_count == 2
    assert split_access.transaction_has_splits(db_session, tx.transaction_id) is False


def test_batch_get_splits_for_transactions(db_session):
    acc, tx1 = _create_account_and_tx(db_session, Decimal("100.00"))
    tx2 = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 16),
        amount=Decimal("80.00"),
        description="Target",
    )
    db_session.add(tx2)
    db_session.flush()

    cat1 = _create_category(db_session, "Food")
    cat2 = _create_category(db_session, "Clothing")

    split_access.stage_replace_splits(
        db_session,
        tx1.transaction_id,
        [(cat1.category_id, Decimal("60.00")), (cat2.category_id, Decimal("40.00"))],
    )
    split_access.stage_replace_splits(
        db_session,
        tx2.transaction_id,
        [(cat1.category_id, Decimal("30.00")), (cat2.category_id, Decimal("50.00"))],
    )
    db_session.commit()

    batch = split_access.get_splits_for_transactions(
        db_session, [tx1.transaction_id, tx2.transaction_id]
    )
    assert len(batch[tx1.transaction_id]) == 2
    assert len(batch[tx2.transaction_id]) == 2


def test_cascade_delete_on_parent_transaction(db_session):
    acc, tx = _create_account_and_tx(db_session)
    cat1 = _create_category(db_session, "Groceries")
    cat2 = _create_category(db_session, "Household")

    split_access.stage_replace_splits(
        db_session,
        tx.transaction_id,
        [
            (cat1.category_id, Decimal("100.00")),
            (cat2.category_id, Decimal("50.00")),
        ],
    )
    db_session.commit()

    assert split_access.transaction_has_splits(db_session, tx.transaction_id) is True

    # Delete parent transaction directly
    db_session.delete(tx)
    db_session.commit()

    # Child splits should have been cascade deleted
    splits = db_session.query(models.TransactionSplit).filter_by(transaction_id=tx.transaction_id).all()
    assert len(splits) == 0


def test_database_duplicate_category_constraint_enforced(db_session):
    """
    Directly exercises database-level UNIQUE(transaction_id, category_id) constraint,
    bypassing all Manager/API/domain validation.
    """
    from sqlalchemy.exc import IntegrityError

    acc, tx = _create_account_and_tx(db_session)
    cat = _create_category(db_session, "Groceries")

    split1 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat.category_id,
        amount=Decimal("50.00"),
    )
    split2 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat.category_id,
        amount=Decimal("100.00"),
    )

    db_session.add(split1)
    db_session.commit()

    db_session.add(split2)
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
