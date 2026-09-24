from datetime import date
from decimal import Decimal
import pytest

from backend import models
from backend.access.account_access import get_active_credit_accounts
from backend.access.transaction_access import get_transactions_for_account


def test_account_access_get_active_credit_accounts(db_session):
    """
    Verify get_active_credit_accounts:
    - Filters to type == 'credit' and is_active == True.
    - Excludes inactive credit accounts.
    - Excludes active non-credit accounts.
    - Orders accounts by name ascending (no secondary sort).
    """
    card_zeta = models.Account(
        name="Zeta Card",
        type="credit",
        is_active=True,
        starting_balance=Decimal("100.00"),
    )
    card_alpha = models.Account(
        name="Alpha Visa",
        type="credit",
        is_active=True,
        starting_balance=Decimal("200.00"),
    )
    inactive_card = models.Account(
        name="AAA Inactive Card",
        type="credit",
        is_active=False,
        starting_balance=Decimal("50.00"),
    )
    checking = models.Account(
        name="AAA Checking",
        type="depository",
        is_active=True,
        starting_balance=Decimal("500.00"),
    )
    brokerage = models.Account(
        name="AAA Brokerage",
        type="investment",
        is_active=True,
        starting_balance=Decimal("1000.00"),
    )
    db_session.add_all([card_zeta, card_alpha, inactive_card, checking, brokerage])
    db_session.commit()

    accounts = get_active_credit_accounts(db_session)

    assert len(accounts) == 2
    # Verify name ascending ordering
    assert [a.name for a in accounts] == ["Alpha Visa", "Zeta Card"]
    # Verify exclusions
    returned_names = {a.name for a in accounts}
    assert "AAA Inactive Card" not in returned_names
    assert "AAA Checking" not in returned_names
    assert "AAA Brokerage" not in returned_names


def test_transaction_access_get_transactions_for_account(db_session):
    """
    Verify get_transactions_for_account:
    - Returns only transactions for the requested account_id.
    - Returns all historical transactions (past, present, future).
    - Orders transactions strictly by date descending.
    - Imposes no artificial limit or pagination.
    """
    card_a = models.Account(name="Card A", type="credit", is_active=True)
    card_b = models.Account(name="Card B", type="credit", is_active=True)
    db_session.add_all([card_a, card_b])
    db_session.flush()

    # Seed 15 transactions on card_a spanning past, current, and future dates
    txs_a = [
        models.Transaction(
            account_id=card_a.id,
            description=f"Tx A {day:02d}",
            amount=Decimal(f"{day}.00"),
            date=date(2026, 5 if day <= 5 else (6 if day <= 12 else 8), day),
        )
        for day in range(1, 16)
    ]
    # Seed transactions on card_b to verify isolation
    txs_b = [
        models.Transaction(
            account_id=card_b.id,
            description="Tx B",
            amount=Decimal("99.00"),
            date=date(2026, 6, 15),
        )
    ]
    db_session.add_all(txs_a + txs_b)
    db_session.commit()

    retrieved = get_transactions_for_account(db_session, card_a.id)

    # 1. Isolation & No limit: exactly 15 records for card_a, zero for card_b
    assert len(retrieved) == 15
    assert all(t.account_id == card_a.id for t in retrieved)

    # 2. Ordering: strictly date descending
    dates = [t.date for t in retrieved]
    assert dates == sorted(dates, reverse=True)

    # 3. All historical: future (August) and past (May) transactions present
    assert any(t.date > date(2026, 7, 1) for t in retrieved)
    assert any(t.date < date(2026, 6, 1) for t in retrieved)
