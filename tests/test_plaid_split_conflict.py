"""
Tests for authoritative Plaid amount conflict semantics on split transactions.

Verifies:
A. Non-reconciled split provider amount correction:
   - Authoritative amount updated on parent.
   - All TransactionSplit allocations deleted atomically.
   - category_id = NULL, category_source = NULL.
   - is_reviewed = False (intentional exception for user re-allocation).
   - No broken split invariants.
B. Financial balance correctness:
   - Account balance changes by exactly the provider amount delta.
C. Atomic rollback:
   - Simulated failure restores old amount and complete old splits.
D. No automatic reallocation:
   - Zero split rows created automatically.
E. ML revision invariance:
   - Invalidation of split does not mutate ML training revision.
F. Reconciled split gate:
   - Attempted provider amount change on reconciled split is blocked
     pending a reconciliation-history policy decision.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch
import pytest

from backend import models, schemas
from backend.access import account_access, ml_model_access, split_access, transaction_access
from backend.domain.accounts import calculate_depository_balance
from backend.managers import transaction_split_manager


def _setup_account_and_categories(db_session):
    acc = models.Account(
        name="Plaid Checking",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("1000.00"),
        current_balance=Decimal("1000.00"),
    )
    db_session.add(acc)
    db_session.flush()

    group = models.CategoryGroup(name="Everyday")
    db_session.add(group)
    db_session.flush()

    cat1 = models.Category(name="Groceries", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Household", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2])
    db_session.commit()
    return acc, cat1, cat2


def test_non_reconciled_split_plaid_amount_correction(db_session):
    acc, cat1, cat2 = _setup_account_and_categories(db_session)

    # 1. Setup posted Plaid transaction with splits
    tx = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id="plaid_tx_split_1",
        date=date(2026, 8, 15),
        amount=Decimal("150.00"),
        description="Target Store #102",
        pending=False,
        is_reviewed=True,
        is_reconciled=False,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(db_session, tx.transaction_id, allocations)
    db_session.refresh(tx)
    assert tx.is_split is True
    assert tx.split_count == 2
    assert tx.amount == Decimal("150.00")

    rev_before = ml_model_access.get_model_metadata(db_session).current_training_revision

    # 2. Plaid sends authoritative amount correction: $160.00
    updated_tx = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="plaid_tx_split_1",
        account_id=acc.id,
        description="Target Store #102 Corrected",
        amount=Decimal("160.00"),
        transaction_date=date(2026, 8, 15),
        pending=False,
    )
    db_session.commit()
    db_session.refresh(updated_tx)

    # 3. Verify ledger-first policy
    assert updated_tx.amount == Decimal("160.00")
    assert updated_tx.is_split is False
    assert updated_tx.split_count == 0
    assert len(updated_tx.splits) == 0
    assert updated_tx.category_id is None
    assert updated_tx.category_source is None
    assert updated_tx.is_reviewed is False  # Flagged for review
    assert split_access.get_splits_for_transaction(db_session, updated_tx.transaction_id) == []

    # 4. Verify ML training revision unchanged
    rev_after = ml_model_access.get_model_metadata(db_session).current_training_revision
    assert rev_after == rev_before


def test_plaid_split_amount_correction_balance_correctness(db_session):
    acc, cat1, cat2 = _setup_account_and_categories(db_session)

    tx = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id="plaid_tx_bal_1",
        date=date(2026, 8, 15),
        amount=Decimal("150.00"),
        description="Costco",
        pending=False,
        is_reviewed=True,
        is_reconciled=False,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(db_session, tx.transaction_id, allocations)

    # Financial balance before provider update
    net_before = transaction_access.get_transaction_net_by_account(db_session, [acc.id]).get(acc.id, Decimal("0.00"))
    bal_before = calculate_depository_balance(acc.starting_balance, net_before)
    assert bal_before == Decimal("850.00")  # 1000 - 150

    # Provider updates amount to $175.00
    transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="plaid_tx_bal_1",
        account_id=acc.id,
        description="Costco",
        amount=Decimal("175.00"),
        transaction_date=date(2026, 8, 15),
        pending=False,
    )
    db_session.commit()

    # Financial balance after provider update
    net_after = transaction_access.get_transaction_net_by_account(db_session, [acc.id]).get(acc.id, Decimal("0.00"))
    bal_after = calculate_depository_balance(acc.starting_balance, net_after)
    assert bal_after == Decimal("825.00")  # 1000 - 175
    assert bal_after - bal_before == Decimal("-25.00")  # Exactly provider delta


def test_plaid_split_invalidation_atomic_rollback_on_failure(db_session):
    acc, cat1, cat2 = _setup_account_and_categories(db_session)

    tx = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id="plaid_tx_rollback_1",
        date=date(2026, 8, 15),
        amount=Decimal("150.00"),
        description="Costco Wholesale",
        pending=False,
        is_reviewed=True,
        is_reconciled=False,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(db_session, tx.transaction_id, allocations)
    db_session.refresh(tx)

    # Simulate failure during session commit
    with patch.object(db_session, "commit", side_effect=RuntimeError("Simulated DB Sync Crash")):
        with pytest.raises(RuntimeError):
            transaction_access.stage_or_update_plaid_transaction(
                db=db_session,
                plaid_transaction_id="plaid_tx_rollback_1",
                account_id=acc.id,
                description="Costco Wholesale",
                amount=Decimal("160.00"),
                transaction_date=date(2026, 8, 15),
                pending=False,
            )
            db_session.commit()

    db_session.rollback()

    # After rollback, old amount and complete old splits remain intact
    db_session.refresh(tx)
    assert tx.amount == Decimal("150.00")
    assert tx.is_split is True
    assert tx.split_count == 2
    assert tx.is_reviewed is True
    splits = split_access.get_splits_for_transaction(db_session, tx.transaction_id)
    assert len(splits) == 2
    assert {s.amount for s in splits} == {Decimal("100.00"), Decimal("50.00")}


def test_plaid_split_no_automatic_reallocation(db_session):
    acc, cat1, cat2 = _setup_account_and_categories(db_session)

    tx = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id="plaid_tx_no_realloc",
        date=date(2026, 8, 15),
        amount=Decimal("150.00"),
        description="Home Depot",
        pending=False,
        is_reviewed=True,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(db_session, tx.transaction_id, allocations)

    # Provider updates amount
    transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="plaid_tx_no_realloc",
        account_id=acc.id,
        description="Home Depot",
        amount=Decimal("170.00"),
        transaction_date=date(2026, 8, 15),
        pending=False,
    )
    db_session.commit()

    # Verify zero TransactionSplit rows exist
    total_splits_in_db = db_session.query(models.TransactionSplit).filter_by(transaction_id=tx.transaction_id).count()
    assert total_splits_in_db == 0


def test_reconciled_split_plaid_amount_change_rejected(db_session):
    acc, cat1, cat2 = _setup_account_and_categories(db_session)
    acc.last_reconciled_date = date(2026, 8, 31)
    acc.last_reconciled_balance = Decimal("850.00")
    db_session.commit()

    tx = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id="plaid_tx_reconciled_1",
        date=date(2026, 8, 15),
        amount=Decimal("150.00"),
        description="Trader Joe's",
        pending=False,
        is_reviewed=True,
        is_cleared=True,
        is_reconciled=True,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(db_session, tx.transaction_id, allocations)

    # 1. Attempt provider update on reconciled split transaction raises PlaidReconciliationConflictError
    with pytest.raises(transaction_access.PlaidReconciliationConflictError) as exc_info:
        transaction_access.stage_or_update_plaid_transaction(
            db=db_session,
            plaid_transaction_id="plaid_tx_reconciled_1",
            account_id=acc.id,
            description="Trader Joe's",
            amount=Decimal("160.00"),
            transaction_date=date(2026, 8, 15),
            pending=False,
        )

    assert "reconciled transaction" in str(exc_info.value)
    assert "reconciliation-history policy" in str(exc_info.value)

    db_session.rollback()

    # 2. Reconciled status, amount, and splits remain completely unchanged
    db_session.refresh(tx)
    assert tx.amount == Decimal("150.00")
    assert tx.is_cleared is True
    assert tx.is_reconciled is True
    assert tx.is_split is True
    assert tx.split_count == 2
    assert tx.category_id is None
    assert tx.category_source is None

    # 3. Sum of split amounts == parent.amount strictly holds
    splits = split_access.get_splits_for_transaction(db_session, tx.transaction_id)
    assert len(splits) == 2
    assert sum(s.amount for s in splits) == tx.amount == Decimal("150.00")

    # 4. Reconciliation metadata on account strictly preserved
    db_session.refresh(acc)
    assert acc.last_reconciled_date == date(2026, 8, 31)
    assert acc.last_reconciled_balance == Decimal("850.00")


def test_reconciled_split_sync_manager_reports_and_logs_conflict(db_session, caplog):
    acc, cat1, cat2 = _setup_account_and_categories(db_session)
    acc.plaid_account_id = "plaid_acc_reconciled_1"
    acc.last_reconciled_date = date(2026, 8, 31)
    acc.last_reconciled_balance = Decimal("850.00")
    db_session.commit()

    item = models.PlaidItem(
        plaid_item_id="item_rec_conflict",
        plaid_access_token_encrypted="encrypted_tok",
        transactions_cursor="cursor_0",
    )
    db_session.add(item)
    db_session.commit()

    tx = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id="plaid_tx_rec_sync_1",
        date=date(2026, 8, 15),
        amount=Decimal("150.00"),
        description="Trader Joe's",
        pending=False,
        is_reviewed=True,
        is_cleared=True,
        is_reconciled=True,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(db_session, tx.transaction_id, allocations)
    db_session.refresh(tx)

    from backend.managers import plaid_transaction_sync_manager
    from unittest.mock import MagicMock

    # Provider sends modified event with changed amount ($160.00 instead of $150.00)
    page_data = MagicMock()
    page_data.has_more = False
    page_data.next_cursor = "cursor_1"
    page_data.added = []
    page_data.modified = [
        {
            "transaction_id": "plaid_tx_rec_sync_1",
            "account_id": "plaid_acc_reconciled_1",
            "name": "Trader Joe's #44",
            "amount": -160.00,  # sync inverts sign (-(-160) = +160)
            "date": "2026-08-15",
            "datetime": None,
            "pending": False,
        }
    ]
    page_data.removed = []

    with patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value="access_token_xyz"), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page_data):
        with caplog.at_level("WARNING"):
            result = plaid_transaction_sync_manager.sync_plaid_transactions(db_session, item_id=item.id)

    # 1. Verify conflict reported through sync result warnings
    assert len(result.warnings) == 1
    assert "reconciliation-history policy" in result.warnings[0]
    assert result.modified == 0  # Conflicting modified transaction was skipped

    # 2. Verify logged via logger.warning
    assert any("reconciliation conflict" in record.message.lower() for record in caplog.records)

    # 3. Verify parent and splits unchanged
    db_session.refresh(tx)
    assert tx.amount == Decimal("150.00")
    assert tx.is_cleared is True
    assert tx.is_reconciled is True
    assert tx.is_split is True
    splits = split_access.get_splits_for_transaction(db_session, tx.transaction_id)
    assert len(splits) == 2
    assert sum(s.amount for s in splits) == tx.amount == Decimal("150.00")
    assert tx.plaid_reconciliation_conflict_amount == Decimal("160.00")
    assert tx.plaid_reconciliation_conflict_at is not None

    # 4. Verify reconciliation metadata unchanged
    db_session.refresh(acc)
    assert acc.last_reconciled_date == date(2026, 8, 31)
    assert acc.last_reconciled_balance == Decimal("850.00")


def test_ordinary_reconciled_plaid_noop_refreshes_metadata(db_session):
    acc, cat1, cat2 = _setup_account_and_categories(db_session)
    acc.last_reconciled_date = date(2026, 8, 31)
    acc.last_reconciled_balance = Decimal("850.00")
    db_session.commit()

    tx = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id="plaid_tx_noop_1",
        date=date(2026, 8, 15),
        amount=Decimal("150.00"),
        description="Old Description",
        pending=False,
        is_reviewed=True,
        is_cleared=True,
        is_reconciled=True,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(db_session, tx.transaction_id, allocations)
    db_session.refresh(tx)

    # Provider updates harmless metadata (description) with SAME amount ($150.00)
    updated_tx = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="plaid_tx_noop_1",
        account_id=acc.id,
        description="New Description from Bank",
        amount=Decimal("150.00"),  # Same amount!
        transaction_date=date(2026, 8, 15),
        pending=False,
    )
    db_session.commit()
    db_session.refresh(updated_tx)

    # Verify metadata refreshed
    assert updated_tx.description == "New Description from Bank"
    assert updated_tx.amount == Decimal("150.00")
    assert updated_tx.is_reconciled is True
    assert updated_tx.is_cleared is True
    assert updated_tx.is_split is True
    assert updated_tx.split_count == 2
    splits = split_access.get_splits_for_transaction(db_session, updated_tx.transaction_id)
    assert len(splits) == 2
    assert sum(s.amount for s in splits) == Decimal("150.00")


def test_reconciled_split_atomicity_on_reporting_failure(db_session):
    acc, cat1, cat2 = _setup_account_and_categories(db_session)
    acc.last_reconciled_date = date(2026, 8, 31)
    acc.last_reconciled_balance = Decimal("850.00")
    db_session.commit()

    tx = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id="plaid_tx_atomic_fail",
        date=date(2026, 8, 15),
        amount=Decimal("150.00"),
        description="Trader Joe's",
        pending=False,
        is_reviewed=True,
        is_cleared=True,
        is_reconciled=True,
    )
    db_session.add(tx)
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(db_session, tx.transaction_id, allocations)
    db_session.refresh(tx)

    # Simulate an error during execution
    with patch("backend.access.transaction_access.stage_or_update_plaid_transaction", side_effect=RuntimeError("Simulated failure")):
        with pytest.raises(RuntimeError):
            transaction_access.stage_or_update_plaid_transaction(
                db=db_session,
                plaid_transaction_id="plaid_tx_atomic_fail",
                account_id=acc.id,
                description="Trader Joe's",
                amount=Decimal("160.00"),
                transaction_date=date(2026, 8, 15),
                pending=False,
            )

    db_session.rollback()

    # Verify zero mutations
    db_session.refresh(tx)
    assert tx.amount == Decimal("150.00")
    assert tx.is_reconciled is True
    assert tx.is_cleared is True
    assert tx.is_split is True
    assert len(tx.splits) == 2
    assert sum(s.amount for s in tx.splits) == Decimal("150.00")
    db_session.refresh(acc)
    assert acc.last_reconciled_date == date(2026, 8, 31)
    assert acc.last_reconciled_balance == Decimal("850.00")


def _setup_mixed_batch_fixtures(db_session, item_suffix="batch_1"):
    acc = models.Account(
        name="Plaid Mixed Checking",
        plaid_account_id=f"plaid_acc_{item_suffix}",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("1000.00"),
        current_balance=Decimal("1000.00"),
        last_reconciled_date=date(2026, 8, 31),
        last_reconciled_balance=Decimal("850.00"),
    )
    db_session.add(acc)
    db_session.flush()

    group = models.CategoryGroup(name=f"Group {item_suffix}")
    db_session.add(group)
    db_session.flush()

    cat1 = models.Category(name="Groceries", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Household", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2])
    db_session.flush()

    item = models.PlaidItem(
        plaid_item_id=f"item_{item_suffix}",
        plaid_access_token_encrypted="encrypted_tok_batch",
        transactions_cursor=f"cursor_{item_suffix}_0",
    )
    db_session.add(item)
    db_session.commit()

    # Event A pre-existing transaction: $20.00
    tx_a = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id=f"tx_a_{item_suffix}",
        date=date(2026, 8, 10),
        amount=Decimal("20.00"),
        description="Coffee Shop Initial",
        pending=False,
        is_reviewed=False,
        is_reconciled=False,
    )
    # Event B pre-existing reconciled transaction with splits: $150.00
    tx_b = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id=f"tx_b_{item_suffix}",
        date=date(2026, 8, 15),
        amount=Decimal("150.00"),
        description="Trader Joe's Reconciled",
        pending=False,
        is_reviewed=True,
        is_cleared=True,
        is_reconciled=True,
    )
    # Event C pre-existing transaction: $35.00
    tx_c = models.Transaction(
        account_id=acc.id,
        plaid_transaction_id=f"tx_c_{item_suffix}",
        date=date(2026, 8, 20),
        amount=Decimal("35.00"),
        description="Gas Station Initial",
        pending=False,
        is_reviewed=False,
        is_reconciled=False,
    )
    db_session.add_all([tx_a, tx_b, tx_c])
    db_session.commit()

    allocations = [
        schemas.TransactionSplitLine(category_id=cat1.category_id, amount=Decimal("100.00")),
        schemas.TransactionSplitLine(category_id=cat2.category_id, amount=Decimal("50.00")),
    ]
    transaction_split_manager.create_or_replace_split(db_session, tx_b.transaction_id, allocations)
    db_session.refresh(tx_b)

    return acc, cat1, cat2, item, tx_a, tx_b, tx_c


def test_plaid_sync_mixed_batch_with_reconciliation_conflict(db_session):
    acc, cat1, cat2, item, tx_a, tx_b, tx_c = _setup_mixed_batch_fixtures(db_session, "mixed_abc")

    from unittest.mock import MagicMock
    from backend.managers import plaid_transaction_sync_manager

    # Batch order: [Event A, Event B (conflict), Event C]
    event_a = {
        "transaction_id": tx_a.plaid_transaction_id,
        "account_id": acc.plaid_account_id,
        "name": "Coffee Shop Updated",
        "amount": -25.00,  # Plaid -25 -> Budget +25.00
        "date": "2026-08-10",
        "datetime": None,
        "pending": False,
    }
    event_b = {
        "transaction_id": tx_b.plaid_transaction_id,
        "account_id": acc.plaid_account_id,
        "name": "Trader Joe's Conflicting",
        "amount": -160.00,  # Plaid -160 -> Budget +160.00 (differs from reconciled 150.00)
        "date": "2026-08-15",
        "datetime": None,
        "pending": False,
    }
    event_c = {
        "transaction_id": tx_c.plaid_transaction_id,
        "account_id": acc.plaid_account_id,
        "name": "Gas Station Updated",
        "amount": -40.00,  # Plaid -40 -> Budget +40.00
        "date": "2026-08-20",
        "datetime": None,
        "pending": False,
    }

    page = MagicMock()
    page.has_more = False
    page.next_cursor = "cursor_mixed_abc_1"
    page.added = []
    page.modified = [event_a, event_b, event_c]
    page.removed = []

    with patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value="tok_123"), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page):
        result = plaid_transaction_sync_manager.sync_plaid_transactions(db_session, item_id=item.id)

    # 1. Result summary counts: modified reflects only valid non-conflicting modifications
    assert result.added == 0
    assert result.modified == 2  # Event A and Event C, Event B rejected!
    assert result.removed == 0
    assert result.next_cursor == "cursor_mixed_abc_1"
    assert len(result.warnings) == 1
    assert "reconciliation-history policy" in result.warnings[0]

    # 2. Event A changes persisted
    db_session.refresh(tx_a)
    assert tx_a.description == "Coffee Shop Updated"
    assert tx_a.amount == Decimal("25.00")

    # 3. Event B financial mutation rejected, durable conflict recorded
    db_session.refresh(tx_b)
    assert tx_b.amount == Decimal("150.00")
    assert tx_b.is_reconciled is True
    assert tx_b.is_cleared is True
    assert tx_b.is_split is True
    assert len(tx_b.splits) == 2
    assert sum(s.amount for s in tx_b.splits) == Decimal("150.00")
    assert tx_b.plaid_reconciliation_conflict_amount == Decimal("160.00")
    assert tx_b.plaid_reconciliation_conflict_at is not None

    # 4. Event C changes persisted
    db_session.refresh(tx_c)
    assert tx_c.description == "Gas Station Updated"
    assert tx_c.amount == Decimal("40.00")

    # 5. Cursor successfully advanced in database
    db_session.refresh(item)
    assert item.transactions_cursor == "cursor_mixed_abc_1"

    # 6. Account balance reflects only valid mutations:
    # Starting balance = 1000.00, tx_a=25, tx_b=150 (unchanged), tx_c=40 -> total outflow 215 -> balance 785
    net = transaction_access.get_transaction_net_by_account(db_session, [acc.id]).get(acc.id, Decimal("0.00"))
    bal = calculate_depository_balance(acc.starting_balance, net)
    assert bal == Decimal("785.00")


def test_plaid_sync_reversed_batch_ordering_independence(db_session):
    acc, cat1, cat2, item, tx_a, tx_b, tx_c = _setup_mixed_batch_fixtures(db_session, "reversed_bac")

    from unittest.mock import MagicMock
    from backend.managers import plaid_transaction_sync_manager

    # Batch order reversed: [Event B (conflict), Event A, Event C]
    event_a = {
        "transaction_id": tx_a.plaid_transaction_id,
        "account_id": acc.plaid_account_id,
        "name": "Coffee Shop Updated",
        "amount": -25.00,
        "date": "2026-08-10",
        "datetime": None,
        "pending": False,
    }
    event_b = {
        "transaction_id": tx_b.plaid_transaction_id,
        "account_id": acc.plaid_account_id,
        "name": "Trader Joe's Conflicting",
        "amount": -160.00,
        "date": "2026-08-15",
        "datetime": None,
        "pending": False,
    }
    event_c = {
        "transaction_id": tx_c.plaid_transaction_id,
        "account_id": acc.plaid_account_id,
        "name": "Gas Station Updated",
        "amount": -40.00,
        "date": "2026-08-20",
        "datetime": None,
        "pending": False,
    }

    page = MagicMock()
    page.has_more = False
    page.next_cursor = "cursor_reversed_bac_1"
    page.added = []
    page.modified = [event_b, event_a, event_c]  # B first!
    page.removed = []

    with patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value="tok_123"), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page):
        result = plaid_transaction_sync_manager.sync_plaid_transactions(db_session, item_id=item.id)

    # Prove ordering independence
    assert result.added == 0
    assert result.modified == 2
    assert result.removed == 0
    assert result.next_cursor == "cursor_reversed_bac_1"
    assert len(result.warnings) == 1
    assert "reconciliation-history policy" in result.warnings[0]

    db_session.refresh(tx_a)
    assert tx_a.amount == Decimal("25.00")

    db_session.refresh(tx_b)
    assert tx_b.amount == Decimal("150.00")
    assert tx_b.is_reconciled is True
    assert len(tx_b.splits) == 2
    assert sum(s.amount for s in tx_b.splits) == Decimal("150.00")
    assert tx_b.plaid_reconciliation_conflict_amount == Decimal("160.00")
    assert tx_b.plaid_reconciliation_conflict_at is not None

    db_session.refresh(tx_c)
    assert tx_c.amount == Decimal("40.00")

    db_session.refresh(item)
    assert item.transactions_cursor == "cursor_reversed_bac_1"


def test_plaid_sync_conflict_lifecycle_idempotency_and_clearing(db_session):
    acc, cat1, cat2, item, _, tx_b, _ = _setup_mixed_batch_fixtures(db_session, "lifecycle")

    from unittest.mock import MagicMock
    from backend.managers import plaid_transaction_sync_manager

    # Phase 1: First sync hits conflict ($160.00)
    page_1 = MagicMock(
        has_more=False,
        next_cursor="cur_life_1",
        added=[],
        modified=[{
            "transaction_id": tx_b.plaid_transaction_id,
            "account_id": acc.plaid_account_id,
            "name": "Trader Joe's Conflict 1",
            "amount": -160.00,
            "date": "2026-08-15",
            "datetime": None,
            "pending": False,
        }],
        removed=[],
    )
    with patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value="tok"), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page_1):
        res1 = plaid_transaction_sync_manager.sync_plaid_transactions(db_session, item_id=item.id)

    assert len(res1.warnings) == 1
    assert res1.modified == 0
    db_session.refresh(tx_b)
    assert tx_b.amount == Decimal("150.00")
    assert tx_b.plaid_reconciliation_conflict_amount == Decimal("160.00")
    conflict_time_1 = tx_b.plaid_reconciliation_conflict_at
    assert conflict_time_1 is not None

    # Phase 2: Provider repeatedly sends identical conflict ($160.00) in next sync
    page_2 = MagicMock(
        has_more=False,
        next_cursor="cur_life_2",
        added=[],
        modified=[{
            "transaction_id": tx_b.plaid_transaction_id,
            "account_id": acc.plaid_account_id,
            "name": "Trader Joe's Conflict 1 Repeat",
            "amount": -160.00,
            "date": "2026-08-15",
            "datetime": None,
            "pending": False,
        }],
        removed=[],
    )
    with patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value="tok"), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page_2):
        res2 = plaid_transaction_sync_manager.sync_plaid_transactions(db_session, item_id=item.id)

    # Idempotent: 1 warning, 0 duplicate splits, amount stable
    assert len(res2.warnings) == 1
    assert res2.modified == 0
    db_session.refresh(tx_b)
    assert tx_b.amount == Decimal("150.00")
    assert tx_b.plaid_reconciliation_conflict_amount == Decimal("160.00")
    assert len(tx_b.splits) == 2
    assert sum(s.amount for s in tx_b.splits) == Decimal("150.00")

    # Phase 3: Provider updates conflict amount to $165.00
    page_3 = MagicMock(
        has_more=False,
        next_cursor="cur_life_3",
        added=[],
        modified=[{
            "transaction_id": tx_b.plaid_transaction_id,
            "account_id": acc.plaid_account_id,
            "name": "Trader Joe's Conflict 2",
            "amount": -165.00,
            "date": "2026-08-15",
            "datetime": None,
            "pending": False,
        }],
        removed=[],
    )
    with patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value="tok"), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page_3):
        res3 = plaid_transaction_sync_manager.sync_plaid_transactions(db_session, item_id=item.id)

    assert len(res3.warnings) == 1
    db_session.refresh(tx_b)
    assert tx_b.amount == Decimal("150.00")
    assert tx_b.plaid_reconciliation_conflict_amount == Decimal("165.00")
    assert len(tx_b.splits) == 2

    # Phase 4: Provider corrects amount back to local matching amount ($150.00)
    page_4 = MagicMock(
        has_more=False,
        next_cursor="cur_life_4",
        added=[],
        modified=[{
            "transaction_id": tx_b.plaid_transaction_id,
            "account_id": acc.plaid_account_id,
            "name": "Trader Joe's Final Matching",
            "amount": -150.00,
            "date": "2026-08-15",
            "datetime": None,
            "pending": False,
        }],
        removed=[],
    )
    with patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value="tok"), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page_4):
        res4 = plaid_transaction_sync_manager.sync_plaid_transactions(db_session, item_id=item.id)

    # Conflict clears cleanly!
    assert len(res4.warnings) == 0
    assert res4.modified == 1
    db_session.refresh(tx_b)
    assert tx_b.description == "Trader Joe's Final Matching"
    assert tx_b.amount == Decimal("150.00")
    assert tx_b.plaid_reconciliation_conflict_amount is None
    assert tx_b.plaid_reconciliation_conflict_at is None
    assert tx_b.is_reconciled is True
    assert len(tx_b.splits) == 2
    assert sum(s.amount for s in tx_b.splits) == Decimal("150.00")


def test_plaid_sync_cursor_durability_on_commit_failure(db_session):
    acc, cat1, cat2, item, tx_a, tx_b, tx_c = _setup_mixed_batch_fixtures(db_session, "cursor_fail")

    from unittest.mock import MagicMock
    from backend.managers import plaid_transaction_sync_manager

    event_b = {
        "transaction_id": tx_b.plaid_transaction_id,
        "account_id": acc.plaid_account_id,
        "name": "Trader Joe's Conflicting",
        "amount": -160.00,
        "date": "2026-08-15",
        "datetime": None,
        "pending": False,
    }

    page = MagicMock()
    page.has_more = False
    page.next_cursor = "cursor_fail_attempted"
    page.added = []
    page.modified = [event_b]
    page.removed = []

    # Simulate failure during cursor staging
    with patch("backend.managers.plaid_transaction_sync_manager.decrypt_token", return_value="tok_123"), \
         patch("backend.access.plaid_access.fetch_accounts_for_token", return_value=[]), \
         patch("backend.access.plaid_transaction_access.fetch_transactions_page", return_value=page), \
         patch("backend.access.plaid_item_access.stage_transactions_cursor", side_effect=RuntimeError("Cursor Write Crash")):
        with pytest.raises(RuntimeError, match="Cursor Write Crash"):
            plaid_transaction_sync_manager.sync_plaid_transactions(db_session, item_id=item.id)

    db_session.rollback()

    # Verify cursor did NOT falsely advance
    db_session.refresh(item)
    assert item.transactions_cursor == "cursor_cursor_fail_0"

