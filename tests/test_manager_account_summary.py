"""
Unit tests for account_summary_manager (backend/managers/account_summary_manager.py).
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest

from backend import models
from backend.managers import account_summary_manager


def test_get_accounts_summary_empty(db_session):
    result = account_summary_manager.get_accounts_summary(db_session)
    assert result == []


def test_get_accounts_summary_manual_depository_derivation(db_session):
    account = models.Account(
        name="Checking Mgr",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    # Outflow: +50.00, Inflow: -200.00
    tx1 = models.Transaction(account_id=account.id, amount=Decimal("50.00"), date=date(2026, 6, 1), description="Grocery")
    tx2 = models.Transaction(account_id=account.id, amount=Decimal("-200.00"), date=date(2026, 6, 2), description="Salary")
    db_session.add_all([tx1, tx2])
    db_session.commit()

    results = account_summary_manager.get_accounts_summary(db_session)
    assert len(results) == 1
    acc_read = results[0]
    assert acc_read.account_id == account.id
    assert acc_read.name == "Checking Mgr"
    # Derived: 500 - (50 - 200) = 650.00
    assert acc_read.current_balance == Decimal("650.00")
    assert acc_read.starting_balance == Decimal("500.00")


def test_get_accounts_summary_plaid_and_credit_accounts_preserved(db_session):
    plaid_item = models.PlaidItem(
        plaid_item_id="item_mgr_test",
        plaid_access_token_encrypted="enc_tok",
    )
    db_session.add(plaid_item)
    db_session.commit()

    plaid_acc = models.Account(
        name="Plaid Checking Mgr",
        type="depository",
        subtype="checking",
        item_id=plaid_item.id,
        plaid_account_id="plaid_mgr_acc_1",
        current_balance=Decimal("1234.56"),
        starting_balance=Decimal("0.00"),
    )
    credit_acc = models.Account(
        name="Credit Card Mgr",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("456.78"),
        starting_balance=Decimal("100.00"),
    )
    db_session.add_all([plaid_acc, credit_acc])
    db_session.commit()

    # Add transaction to Plaid account (should NOT affect its balance)
    tx = models.Transaction(account_id=plaid_acc.id, amount=Decimal("100.00"), date=date(2026, 6, 1), description="Store")
    db_session.add(tx)
    db_session.commit()

    results = account_summary_manager.get_accounts_summary(db_session)
    by_name = {a.name: a for a in results}

    assert by_name["Plaid Checking Mgr"].current_balance == Decimal("1234.56")
    assert by_name["Credit Card Mgr"].current_balance == Decimal("456.78")


def test_get_accounts_summary_does_not_mutate_orm_entities(db_session):
    account = models.Account(
        name="No Mutation Check",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    tx = models.Transaction(account_id=account.id, amount=Decimal("75.00"), date=date(2026, 6, 1), description="Dinner")
    db_session.add(tx)
    db_session.commit()

    results = account_summary_manager.get_accounts_summary(db_session)
    assert results[0].current_balance == Decimal("425.00")

    # Verify session dirty state
    assert account not in db_session.dirty
    assert not db_session.is_modified(account)

    # Re-fetch raw persisted row from DB to confirm persisted current_balance remains 0.00
    db_session.expire_all()
    persisted = db_session.query(models.Account).filter_by(id=account.id).one()
    assert persisted.current_balance == Decimal("0.00")
