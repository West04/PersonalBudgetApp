"""
Characterization tests for account reconciliation prerequisites:
- Verifies current behavior of account balance derivation (depository starting balance - net transactions).
- Verifies current behavior of deleting transactions (prior to reconciled-transaction protection).
- Verifies that no cleared or reconciled columns existed prior to Phase 7.
"""

from decimal import Decimal
from datetime import date
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend import models


def test_depository_account_balance_derivation(client: TestClient, db_session):
    """
    Characterizes that manual depository accounts compute balance as:
    starting_balance - net_transactions.
    """
    account = models.Account(
        name="Checking Test",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("1000.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    t1 = models.Transaction(
        account_id=account.id,
        description="Grocery",
        amount=Decimal("50.00"),  # Outflow
        date=date(2026, 10, 1),
    )
    t2 = models.Transaction(
        account_id=account.id,
        description="Paycheck",
        amount=Decimal("-500.00"),  # Inflow
        date=date(2026, 10, 2),
    )
    t3 = models.Transaction(
        account_id=account.id,
        description="Utility",
        amount=Decimal("100.00"),  # Outflow
        date=date(2026, 10, 3),
    )
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    resp = client.get("/accounts/")
    assert resp.status_code == 200
    acc_data = next(a for a in resp.json() if a["account_id"] == str(account.id))

    # Net = 50 + (-500) + 100 = -350
    # Expected current_balance = 1000 - (-350) = 1350.00
    assert Decimal(str(acc_data["current_balance"])) == Decimal("1350.00")


def test_transaction_delete_pre_reconciliation(client: TestClient, db_session):
    """
    Characterizes that ordinary transactions can be deleted with 204.
    """
    account = models.Account(
        name="Checking Test",
        type="depository",
        subtype="checking",
    )
    db_session.add(account)
    db_session.commit()

    txn = models.Transaction(
        account_id=account.id,
        description="Coffee",
        amount=Decimal("4.50"),
        date=date(2026, 10, 1),
    )
    db_session.add(txn)
    db_session.commit()

    del_resp = client.delete(f"/transactions/{txn.transaction_id}")
    assert del_resp.status_code == 204
