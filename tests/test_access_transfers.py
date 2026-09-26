from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
import pytest

from backend import models
from backend.access.transaction_access import (
    get_account_for_transaction,
    get_unmatched_inflow_transactions,
    get_unmatched_outflow_transactions,
    mark_transactions_as_transfers,
)


def test_access_get_unmatched_inflow_transactions(db_session):
    """
    Verify get_unmatched_inflow_transactions:
    - Filters to amount < 0 and is_transfer == False.
    - Excludes positive transactions (outflows).
    - Excludes transactions already marked is_transfer == True.
    - Retrieves across all accounts.
    - Does not enforce a specific ordering.
    """
    acct_a = models.Account(name="Acct A", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    acct_b = models.Account(name="Acct B", type="credit", current_balance=Decimal("-500.00"), currency="USD")
    db_session.add_all([acct_a, acct_b])
    db_session.flush()

    # Qualifying inflows
    tx_in_1 = models.Transaction(account_id=acct_a.id, amount=Decimal("-100.00"), date=date(2026, 6, 1), is_transfer=False)
    tx_in_2 = models.Transaction(account_id=acct_b.id, amount=Decimal("-50.00"), date=date(2026, 6, 2), is_transfer=False)

    # Excluded: positive (outflow)
    tx_out = models.Transaction(account_id=acct_a.id, amount=Decimal("100.00"), date=date(2026, 6, 1), is_transfer=False)
    # Excluded: is_transfer == True
    tx_in_marked = models.Transaction(account_id=acct_b.id, amount=Decimal("-75.00"), date=date(2026, 6, 3), is_transfer=True)
    # Excluded: zero amount
    tx_zero = models.Transaction(account_id=acct_a.id, amount=Decimal("0.00"), date=date(2026, 6, 4), is_transfer=False)

    db_session.add_all([tx_in_1, tx_in_2, tx_out, tx_in_marked, tx_zero])
    db_session.commit()

    inflows = get_unmatched_inflow_transactions(db_session)

    # Exactly 2 qualifying inflows across both accounts
    assert len(inflows) == 2
    inflow_ids = {t.transaction_id for t in inflows}
    assert inflow_ids == {tx_in_1.transaction_id, tx_in_2.transaction_id}
    assert all(t.amount < Decimal("0.00") for t in inflows)
    assert all(t.is_transfer is False for t in inflows)


def test_access_get_unmatched_outflow_transactions(db_session):
    """
    Verify get_unmatched_outflow_transactions:
    - Filters to amount > 0 and is_transfer == False.
    - Excludes negative transactions (inflows).
    - Excludes transactions already marked is_transfer == True.
    - Retrieves across all accounts.
    - Does not enforce a specific ordering.
    """
    acct_a = models.Account(name="Acct A", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    acct_b = models.Account(name="Acct B", type="credit", current_balance=Decimal("-500.00"), currency="USD")
    db_session.add_all([acct_a, acct_b])
    db_session.flush()

    # Qualifying outflows
    tx_out_1 = models.Transaction(account_id=acct_a.id, amount=Decimal("150.00"), date=date(2026, 6, 5), is_transfer=False)
    tx_out_2 = models.Transaction(account_id=acct_b.id, amount=Decimal("200.00"), date=date(2026, 6, 6), is_transfer=False)

    # Excluded: negative (inflow)
    tx_in = models.Transaction(account_id=acct_a.id, amount=Decimal("-150.00"), date=date(2026, 6, 5), is_transfer=False)
    # Excluded: is_transfer == True
    tx_out_marked = models.Transaction(account_id=acct_b.id, amount=Decimal("80.00"), date=date(2026, 6, 7), is_transfer=True)
    # Excluded: zero amount
    tx_zero = models.Transaction(account_id=acct_a.id, amount=Decimal("0.00"), date=date(2026, 6, 8), is_transfer=False)

    db_session.add_all([tx_out_1, tx_out_2, tx_in, tx_out_marked, tx_zero])
    db_session.commit()

    outflows = get_unmatched_outflow_transactions(db_session)

    # Exactly 2 qualifying outflows across both accounts
    assert len(outflows) == 2
    outflow_ids = {t.transaction_id for t in outflows}
    assert outflow_ids == {tx_out_1.transaction_id, tx_out_2.transaction_id}
    assert all(t.amount > Decimal("0.00") for t in outflows)
    assert all(t.is_transfer is False for t in outflows)


def test_access_get_account_for_transaction(db_session):
    """
    Verify get_account_for_transaction:
    - Resolves the related Account instance from a Transaction.
    - Encapsulates relationship resolution inside Transaction ResourceAccess.
    """
    acct = models.Account(name="My Account", type="depository", current_balance=Decimal("500.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    tx = models.Transaction(account_id=acct.id, amount=Decimal("50.00"), date=date(2026, 6, 10), is_transfer=False)
    db_session.add(tx)
    db_session.commit()

    resolved_account = get_account_for_transaction(tx)
    assert resolved_account is not None
    assert resolved_account.id == acct.id
    assert resolved_account.name == "My Account"


def test_access_mark_transactions_as_transfers_normal_and_cardinality(db_session):
    """
    Verify mark_transactions_as_transfers bulk updates rows across cardinalities:
    - Mutates matching records to is_transfer = True.
    - Leaves unreferenced records untouched (is_transfer = False).
    - Unconditionally commits changes to the database.
    - Returns exact count of updated rows.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t1 = models.Transaction(account_id=acct.id, amount=Decimal("10.00"), date=date(2026, 6, 1), description="T1", is_transfer=False)
    t2 = models.Transaction(account_id=acct.id, amount=Decimal("20.00"), date=date(2026, 6, 2), description="T2", is_transfer=False)
    t3 = models.Transaction(account_id=acct.id, amount=Decimal("30.00"), date=date(2026, 6, 3), description="T3", is_transfer=False)
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # 1. Single ID
    count_1 = mark_transactions_as_transfers(db_session, [t1.transaction_id])
    assert count_1 == 1
    db_session.refresh(t1)
    assert t1.is_transfer is True

    # 2. Pair of IDs (t2 and t3)
    count_2 = mark_transactions_as_transfers(db_session, [t2.transaction_id, t3.transaction_id])
    assert count_2 == 2
    db_session.refresh(t2)
    db_session.refresh(t3)
    assert t2.is_transfer is True
    assert t3.is_transfer is True


def test_access_mark_transactions_as_transfers_empty_list(db_session):
    """
    Verify mark_transactions_as_transfers with empty list:
    - Returns 0.
    - Executes single db.commit() unconditionally.
    - Does not modify any existing transactions.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t = models.Transaction(account_id=acct.id, amount=Decimal("50.00"), date=date(2026, 6, 1), description="T", is_transfer=False)
    db_session.add(t)
    db_session.commit()

    with patch.object(db_session, "commit", wraps=db_session.commit) as spy_commit:
        count = mark_transactions_as_transfers(db_session, [])
        assert count == 0
        assert spy_commit.call_count == 1

    db_session.refresh(t)
    assert t.is_transfer is False


def test_access_mark_transactions_as_transfers_nonexistent_ids(db_session):
    """
    Verify mark_transactions_as_transfers with nonexistent IDs:
    - Returns 0.
    - Executes single db.commit() cleanly without raising exceptions.
    """
    fake_ids = [uuid4(), uuid4()]

    with patch.object(db_session, "commit", wraps=db_session.commit) as spy_commit:
        count = mark_transactions_as_transfers(db_session, fake_ids)
        assert count == 0
        assert spy_commit.call_count == 1


def test_access_mark_transactions_as_transfers_mixed_existing_and_nonexistent(db_session):
    """
    Verify mark_transactions_as_transfers with mixed existing and nonexistent IDs:
    - Updates only existing transaction rows.
    - Silently ignores nonexistent IDs.
    - Returns count of actually updated rows (1).
    - Unconditionally commits.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t_real = models.Transaction(account_id=acct.id, amount=Decimal("60.00"), date=date(2026, 6, 1), description="Real", is_transfer=False)
    db_session.add(t_real)
    db_session.commit()

    fake_id = uuid4()
    count = mark_transactions_as_transfers(db_session, [t_real.transaction_id, fake_id])
    assert count == 1

    db_session.refresh(t_real)
    assert t_real.is_transfer is True


def test_access_mark_transactions_as_transfers_duplicate_ids(db_session):
    """
    Verify mark_transactions_as_transfers with duplicate IDs in the sequence:
    - Updates single matched record to is_transfer = True.
    - Returns 1 (count of matched/updated rows in SQL).
    - Commits cleanly.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t = models.Transaction(account_id=acct.id, amount=Decimal("70.00"), date=date(2026, 6, 1), description="Dup", is_transfer=False)
    db_session.add(t)
    db_session.commit()

    count = mark_transactions_as_transfers(db_session, [t.transaction_id, t.transaction_id])
    assert count == 1

    db_session.refresh(t)
    assert t.is_transfer is True


def test_access_mark_transactions_as_transfers_already_marked_idempotence(db_session):
    """
    Verify mark_transactions_as_transfers is idempotent for already-marked rows:
    - Re-running against an already-true record updates it idempotently without error.
    - Returns 1 (SQLAlchemy reports rows matched by update).
    - Record remains is_transfer = True.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    t = models.Transaction(account_id=acct.id, amount=Decimal("80.00"), date=date(2026, 6, 1), description="Already", is_transfer=True)
    db_session.add(t)
    db_session.commit()

    count = mark_transactions_as_transfers(db_session, [t.transaction_id])
    assert count == 1

    db_session.refresh(t)
    assert t.is_transfer is True

