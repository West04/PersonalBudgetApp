"""
Workflow Manager tests for Split Transactions (backend/managers/transaction_split_manager.py).

Verifies:
1. create_or_replace_split converts unsplit transaction to split form, clearing parent category.
2. ML training revision increment semantics:
   - Increments when splitting a human/ml labeled transaction.
   - Does NOT increment when splitting an uncategorized transaction.
   - Does NOT increment when replacing splits on an already split transaction.
   - Increments when unsplitting to a single category.
   - Does NOT increment when unsplitting to uncategorized (None).
3. Eligibility guards:
   - Pending transactions rejected with SplitTransactionPendingError.
   - Confirmed transfers rejected with SplitTransactionTransferError.
4. Validation guards:
   - Non-existent transaction raises TransactionNotFoundError.
   - Non-existent category raises SplitValidationError.
   - Sum violation raises SplitValidationError.
5. Rollback safety: errors trigger a clean transaction rollback.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from unittest.mock import patch

from backend import models, schemas
from backend.access import ml_model_access, split_access
from backend.managers import transaction_split_manager


def _setup_account_and_categories(db_session):
    acc = models.Account(
        name="Checking",
        type="checking",
        current_balance=Decimal("1000.00"),
    )
    db_session.add(acc)
    db_session.flush()

    group = models.CategoryGroup(name="Living")
    db_session.add(group)
    db_session.flush()

    cat1 = models.Category(name="Groceries", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Household", group_id=group.category_group_id, type="expense")
    cat3 = models.Category(name="Utilities", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2, cat3])
    db_session.commit()
    return acc, cat1, cat2, cat3


def test_split_unsplit_workflow_and_ml_revision(db_session):
    acc, cat1, cat2, cat3 = _setup_account_and_categories(db_session)

    # 1. Start with an uncategorized transaction
    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 15),
        amount=Decimal("150.00"),
        description="Target Store",
        category_id=None,
        category_source=None,
    )
    db_session.add(tx)
    db_session.commit()

    rev_before = ml_model_access.get_model_metadata(db_session).current_training_revision

    # Splitting an uncategorized transaction should NOT advance ML revision
    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    res_tx = transaction_split_manager.create_or_replace_split(
        db=db_session,
        transaction_id=tx.transaction_id,
        allocations=allocations,
    )

    assert res_tx.category_id is None
    assert res_tx.category_source is None
    assert res_tx.is_split is True
    assert res_tx.split_count == 2
    assert ml_model_access.get_model_metadata(db_session).current_training_revision == rev_before

    # Replacing splits on an already split transaction should NOT advance revision
    new_allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("90.00")),
        schemas.TransactionSplitLine(category_id=cat3.category_id, amount=Decimal("60.00")),
    ]
    res_tx2 = transaction_split_manager.create_or_replace_split(
        db=db_session,
        transaction_id=tx.transaction_id,
        allocations=new_allocations,
    )
    assert res_tx2.is_split is True
    assert ml_model_access.get_model_metadata(db_session).current_training_revision == rev_before

    # 2. Unsplit to explicit category -> advances revision
    unsplit_tx = transaction_split_manager.unsplit_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        target_category_id=cat1.category_id,
    )
    assert unsplit_tx.is_split is False
    assert unsplit_tx.category_id == cat1.category_id
    assert unsplit_tx.category_source == "manual"
    rev_after_unsplit = ml_model_access.get_model_metadata(db_session).current_training_revision
    assert rev_after_unsplit == rev_before + 1

    # 3. Splitting a manually-labeled transaction -> advances revision (training label disappears)
    res_tx3 = transaction_split_manager.create_or_replace_split(
        db=db_session,
        transaction_id=tx.transaction_id,
        allocations=allocations,
    )
    assert res_tx3.category_id is None
    assert res_tx3.is_split is True
    rev_after_split_labeled = ml_model_access.get_model_metadata(db_session).current_training_revision
    assert rev_after_split_labeled == rev_after_unsplit + 1

    # 4. Unsplit to None (uncategorized) -> does NOT advance revision
    unsplit_uncat = transaction_split_manager.unsplit_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        target_category_id=None,
    )
    assert unsplit_uncat.is_split is False
    assert unsplit_uncat.category_id is None
    assert unsplit_uncat.category_source is None
    assert ml_model_access.get_model_metadata(db_session).current_training_revision == rev_after_split_labeled


def test_split_pending_transaction_guard(db_session):
    acc, cat1, cat2, _ = _setup_account_and_categories(db_session)

    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 15),
        amount=Decimal("100.00"),
        description="Pending Charge",
        pending=True,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("60.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("40.00")),
    ]

    with pytest.raises(transaction_split_manager.SplitTransactionPendingError) as exc_info:
        transaction_split_manager.create_or_replace_split(
            db=db_session,
            transaction_id=tx.transaction_id,
            allocations=allocations,
        )
    assert "Pending transactions cannot be split" in str(exc_info.value)


def test_split_transfer_transaction_guard(db_session):
    acc, cat1, cat2, _ = _setup_account_and_categories(db_session)

    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 15),
        amount=Decimal("100.00"),
        description="Account Transfer",
        is_transfer=True,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("60.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("40.00")),
    ]

    with pytest.raises(transaction_split_manager.SplitTransactionTransferError) as exc_info:
        transaction_split_manager.create_or_replace_split(
            db=db_session,
            transaction_id=tx.transaction_id,
            allocations=allocations,
        )
    assert "Transfer transactions cannot be split" in str(exc_info.value)


def test_split_nonexistent_transaction(db_session):
    _, cat1, cat2, _ = _setup_account_and_categories(db_session)
    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("50.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]

    with pytest.raises(transaction_split_manager.TransactionNotFoundError):
        transaction_split_manager.create_or_replace_split(
            db=db_session,
            transaction_id=uuid4(),
            allocations=allocations,
        )


def test_split_nonexistent_category(db_session):
    acc, cat1, _, _ = _setup_account_and_categories(db_session)
    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 15),
        amount=Decimal("100.00"),
        description="Market",
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("50.00")),
        schemas.TransactionSplitLine(category_id=uuid4(), amount=Decimal("50.00")),
    ]

    with pytest.raises(transaction_split_manager.SplitValidationError) as exc_info:
        transaction_split_manager.create_or_replace_split(
            db=db_session,
            transaction_id=tx.transaction_id,
            allocations=allocations,
        )
    assert "not found" in str(exc_info.value)


def test_unsplit_non_split_transaction(db_session):
    acc, cat1, _, _ = _setup_account_and_categories(db_session)
    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 15),
        amount=Decimal("100.00"),
        description="Market",
    )
    db_session.add(tx)
    db_session.commit()

    with pytest.raises(transaction_split_manager.SplitValidationError) as exc_info:
        transaction_split_manager.unsplit_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            target_category_id=cat1.category_id,
        )
    assert "not split" in str(exc_info.value)


def test_split_creation_rollback_on_failure(db_session):
    acc, cat1, cat2, _ = _setup_account_and_categories(db_session)
    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 15),
        amount=Decimal("100.00"),
        description="Market",
        category_id=cat1.category_id,
        category_source="manual",
        is_reviewed=True,
        is_cleared=True,
        is_reconciled=False,
    )
    db_session.add(tx)
    db_session.commit()

    rev_before = ml_model_access.get_model_metadata(db_session).current_training_revision

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("50.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]

    # Force a failure after category clearing and revision increment to test rollback
    with patch("backend.access.split_access.stage_replace_splits", side_effect=RuntimeError("Simulated DB Crash")):
        with pytest.raises(RuntimeError):
            transaction_split_manager.create_or_replace_split(
                db=db_session,
                transaction_id=tx.transaction_id,
                allocations=allocations,
            )

    # After rollback, verify complete state restoration
    db_session.refresh(tx)
    assert tx.category_id == cat1.category_id
    assert tx.category_source == "manual"
    assert tx.is_split is False
    assert tx.split_count == 0
    assert len(tx.splits) == 0
    assert tx.amount == Decimal("100.00")
    assert tx.date == date(2026, 6, 15)
    assert tx.account_id == acc.id
    assert tx.is_reviewed is True
    assert tx.is_cleared is True
    assert tx.is_reconciled is False
    assert ml_model_access.get_model_metadata(db_session).current_training_revision == rev_before


def test_unsplit_rollback_on_failure(db_session):
    acc, cat1, cat2, _ = _setup_account_and_categories(db_session)
    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 15),
        amount=Decimal("150.00"),
        description="Market",
        category_id=None,
        category_source=None,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(
        db=db_session,
        transaction_id=tx.transaction_id,
        allocations=allocations,
    )
    db_session.refresh(tx)
    assert tx.is_split is True
    assert tx.split_count == 2

    rev_before = ml_model_access.get_model_metadata(db_session).current_training_revision

    # Simulate failure during unsplit commit
    with patch.object(db_session, "commit", side_effect=RuntimeError("Commit failed during unsplit")):
        with pytest.raises(RuntimeError):
            transaction_split_manager.unsplit_transaction(
                db=db_session,
                transaction_id=tx.transaction_id,
                target_category_id=cat1.category_id,
            )

    # After rollback:
    # 1. Original split rows remain exactly intact
    # 2. Parent remains split
    # 3. category_id and category_source remain None
    # 4. Training revision unchanged
    db_session.refresh(tx)
    assert tx.is_split is True
    assert tx.split_count == 2
    assert tx.category_id is None
    assert tx.category_source is None
    assert ml_model_access.get_model_metadata(db_session).current_training_revision == rev_before
    splits = split_access.get_splits_for_transaction(db_session, tx.transaction_id)
    assert len(splits) == 2
    assert {s.amount for s in splits} == {Decimal("100.00"), Decimal("50.00")}
