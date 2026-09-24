from datetime import date
from decimal import Decimal
import pytest

from backend import models
from backend.access.transaction_access import (
    get_account_for_transaction,
    get_unmatched_inflow_transactions,
    get_unmatched_outflow_transactions,
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
