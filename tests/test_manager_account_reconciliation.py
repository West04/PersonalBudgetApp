"""
Tests for AccountReconciliationManager workflow orchestration:
- Account type validation (only depository supported in Phase 7)
- Prior balance baseline resolution (starting_balance vs last_reconciled_balance)
- Calculation sequencing
- Completion rejection on non-zero difference
- Successful completion state transitions
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException

from backend import models
from backend.managers import account_reconciliation_manager


def test_manager_rejects_non_depository_account(db_session):
    account = models.Account(
        name="Credit Card",
        type="credit",
        subtype="credit card",
    )
    db_session.add(account)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        account_reconciliation_manager.get_reconciliation_summary(
            db=db_session,
            account_id=account.id,
            statement_ending_date=date(2026, 10, 31),
            statement_ending_balance=Decimal("500.00"),
        )
    assert exc.value.status_code == 400
    assert "depository accounts only" in exc.value.detail


def test_manager_first_reconciliation_uses_starting_balance(db_session):
    account = models.Account(
        name="Checking",
        type="depository",
        starting_balance=Decimal("1000.00"),
        last_reconciled_balance=None,
        last_reconciled_date=None,
    )
    db_session.add(account)
    db_session.commit()

    t1 = models.Transaction(
        account_id=account.id,
        description="Grocery",
        amount=Decimal("50.00"),
        date=date(2026, 10, 5),
        is_cleared=True,
    )
    t2 = models.Transaction(
        account_id=account.id,
        description="Paycheck",
        amount=Decimal("-500.00"),
        date=date(2026, 10, 15),
        is_cleared=True,
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    summary = account_reconciliation_manager.get_reconciliation_summary(
        db=db_session,
        account_id=account.id,
        statement_ending_date=date(2026, 10, 31),
        statement_ending_balance=Decimal("1450.00"),
    )

    # 1000 - (50 + -500) = 1000 - (-450) = 1450.00
    assert summary.prior_reconciled_balance == Decimal("1000.00")
    assert summary.cleared_balance == Decimal("1450.00")
    assert summary.difference == Decimal("0.00")
    assert summary.is_balanced is True
    assert summary.cleared_count == 2
    assert summary.uncleared_count == 0


def test_manager_subsequent_reconciliation_uses_last_reconciled_balance(db_session):
    account = models.Account(
        name="Checking",
        type="depository",
        starting_balance=Decimal("1000.00"),
        last_reconciled_date=date(2026, 9, 30),
        last_reconciled_balance=Decimal("1450.00"),
    )
    db_session.add(account)
    db_session.commit()

    # Old already reconciled tx from month 1
    t_old = models.Transaction(
        account_id=account.id,
        description="Old Reconciled",
        amount=Decimal("100.00"),
        date=date(2026, 9, 20),
        is_cleared=True,
        is_reconciled=True,
    )
    # New tx in month 2
    t_new = models.Transaction(
        account_id=account.id,
        description="Electric Bill",
        amount=Decimal("120.00"),
        date=date(2026, 10, 10),
        is_cleared=True,
        is_reconciled=False,
    )
    db_session.add_all([t_old, t_new])
    db_session.commit()

    summary = account_reconciliation_manager.get_reconciliation_summary(
        db=db_session,
        account_id=account.id,
        statement_ending_date=date(2026, 10, 31),
        statement_ending_balance=Decimal("1330.00"),
    )

    # Prior balance is last_reconciled_balance (1450.00), not starting_balance (1000.00)
    assert summary.prior_reconciled_balance == Decimal("1450.00")
    # Cleared net is ONLY t_new (+120.00)
    # Cleared balance = 1450.00 - 120.00 = 1330.00
    assert summary.cleared_balance == Decimal("1330.00")
    assert summary.difference == Decimal("0.00")
    assert summary.is_balanced is True
    # Old reconciled transaction is excluded from the list
    assert len(summary.transactions) == 1
    assert summary.transactions[0].transaction_id == t_new.transaction_id


def test_manager_complete_reconciliation_blocks_unbalanced(db_session):
    account = models.Account(
        name="Checking",
        type="depository",
        starting_balance=Decimal("500.00"),
    )
    db_session.add(account)
    db_session.commit()

    t = models.Transaction(
        account_id=account.id,
        description="Tx",
        amount=Decimal("50.00"),
        date=date(2026, 10, 10),
        is_cleared=True,
    )
    db_session.add(t)
    db_session.commit()

    # Cleared balance is 500 - 50 = 450.00. Statement is 400.00 -> diff = -50.00
    with pytest.raises(HTTPException) as exc:
        account_reconciliation_manager.complete_reconciliation(
            db=db_session,
            account_id=account.id,
            statement_ending_date=date(2026, 10, 31),
            statement_ending_balance=Decimal("400.00"),
        )
    assert exc.value.status_code == 400
    assert "does not match cleared balance" in exc.value.detail


def test_manager_complete_reconciliation_success_state_transitions(db_session):
    account = models.Account(
        name="Checking",
        type="depository",
        starting_balance=Decimal("1000.00"),
    )
    db_session.add(account)
    db_session.commit()

    t1 = models.Transaction(
        account_id=account.id,
        description="Tx 1",
        amount=Decimal("100.00"),
        date=date(2026, 10, 5),
        is_cleared=True,
        is_reviewed=False,  # Phase 6 review state
    )
    t2 = models.Transaction(
        account_id=account.id,
        description="Tx 2 (Uncleared)",
        amount=Decimal("25.00"),
        date=date(2026, 10, 8),
        is_cleared=False,  # Will remain uncleared and unreconciled
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    # Cleared balance: 1000 - 100 = 900.00
    ending_date = date(2026, 10, 31)
    ending_balance = Decimal("900.00")

    result = account_reconciliation_manager.complete_reconciliation(
        db=db_session,
        account_id=account.id,
        statement_ending_date=ending_date,
        statement_ending_balance=ending_balance,
    )

    # 1. Account metadata is updated
    db_session.refresh(account)
    assert account.last_reconciled_date == ending_date
    assert account.last_reconciled_balance == ending_balance

    # 2. t1 became reconciled
    db_session.refresh(t1)
    assert t1.is_reconciled is True
    assert t1.is_cleared is True
    # 3. Phase 6 review state remains untouched!
    assert t1.is_reviewed is False

    # 4. t2 remains uncleared and unreconciled
    db_session.refresh(t2)
    assert t2.is_reconciled is False
    assert t2.is_cleared is False

    # 5. Returned active reconciliation summary now only shows t2 as unreconciled
    assert len(result.transactions) == 1
    assert result.transactions[0].transaction_id == t2.transaction_id


def test_manager_complete_reconciliation_atomic_rollback_on_failure(db_session, monkeypatch):
    """
    Proves that if an error occurs during the second mutation of completion
    (account metadata update) after transactions have been marked reconciled in session,
    the Manager rolls back the entire transaction.
    Neither transaction.is_reconciled nor account.last_reconciled_* metadata is persisted.
    """
    from backend.access import account_access

    account = models.Account(
        name="Atomicity Test Checking",
        type="depository",
        starting_balance=Decimal("1000.00"),
        last_reconciled_date=None,
        last_reconciled_balance=None,
    )
    db_session.add(account)
    db_session.commit()

    t1 = models.Transaction(
        account_id=account.id,
        description="Grocery",
        amount=Decimal("150.00"),
        date=date(2026, 10, 5),
        is_cleared=True,
        is_reconciled=False,
    )
    db_session.add(t1)
    db_session.commit()

    # Simulate unexpected failure during account metadata update step
    def failing_update_account_reconciliation_metadata(db, account_id, last_reconciled_date, last_reconciled_balance):
        raise RuntimeError("Simulated failure during account reconciliation metadata persistence")

    monkeypatch.setattr(
        account_access,
        "update_account_reconciliation_metadata",
        failing_update_account_reconciliation_metadata,
    )

    ending_date = date(2026, 10, 31)
    ending_balance = Decimal("850.00")  # 1000 - 150 = 850 (balanced)

    with pytest.raises(RuntimeError, match="Simulated failure"):
        account_reconciliation_manager.complete_reconciliation(
            db=db_session,
            account_id=account.id,
            statement_ending_date=ending_date,
            statement_ending_balance=ending_balance,
        )

    # Verify atomic rollback: neither transaction nor account state was mutated
    db_session.refresh(account)
    db_session.refresh(t1)

    assert t1.is_reconciled is False
    assert account.last_reconciled_date is None
    assert account.last_reconciled_balance is None


def test_manager_complete_reconciliation_atomic_success_path(db_session):
    """
    Proves that upon successful completion, both participating transactions and
    account reconciliation metadata are committed together in one atomic transaction.
    """
    account = models.Account(
        name="Success Atomicity Checking",
        type="depository",
        starting_balance=Decimal("2000.00"),
        last_reconciled_date=None,
        last_reconciled_balance=None,
    )
    db_session.add(account)
    db_session.commit()

    t1 = models.Transaction(
        account_id=account.id,
        description="Salary",
        amount=Decimal("-1000.00"),
        date=date(2026, 10, 1),
        is_cleared=True,
        is_reconciled=False,
    )
    t2 = models.Transaction(
        account_id=account.id,
        description="Rent",
        amount=Decimal("1200.00"),
        date=date(2026, 10, 2),
        is_cleared=True,
        is_reconciled=False,
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    # 2000 - (-1000 + 1200) = 2000 - 200 = 1800.00
    ending_date = date(2026, 10, 31)
    ending_balance = Decimal("1800.00")

    result = account_reconciliation_manager.complete_reconciliation(
        db=db_session,
        account_id=account.id,
        statement_ending_date=ending_date,
        statement_ending_balance=ending_balance,
    )

    # Verify both transactions and account metadata persisted together
    db_session.refresh(account)
    db_session.refresh(t1)
    db_session.refresh(t2)

    assert t1.is_reconciled is True
    assert t2.is_reconciled is True
    assert account.last_reconciled_date == ending_date
    assert account.last_reconciled_balance == ending_balance
    assert result.is_balanced is True
    assert result.prior_reconciled_balance == ending_balance
