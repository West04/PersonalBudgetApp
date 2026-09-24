from datetime import date
from decimal import Decimal
import pytest

from backend import models
from backend.access.account_access import get_active_accounts
from backend.access.transaction_access import (
    DASHBOARD_RECENT_TRANSACTIONS_LIMIT,
    get_recent_transactions_for_month,
)


def test_account_access_get_active_accounts_ordering_and_filtering(db_session):
    """
    Verify get_active_accounts:
    - Filters to is_active == True (excludes inactive).
    - Orders accounts by name ascending.
    """
    a_gamma = models.Account(name="Gamma Checking", type="depository", is_active=True, current_balance=Decimal("100.00"))
    a_alpha = models.Account(name="Alpha Savings", type="depository", is_active=True, current_balance=Decimal("200.00"))
    a_beta = models.Account(name="Beta Card", type="credit", is_active=True, current_balance=Decimal("300.00"))
    a_inactive = models.Account(name="AAA Inactive", type="depository", is_active=False, current_balance=Decimal("999.00"))
    db_session.add_all([a_gamma, a_alpha, a_beta, a_inactive])
    db_session.commit()

    accounts = get_active_accounts(db_session)

    assert len(accounts) == 3
    # Order: Alpha Savings, Beta Card, Gamma Checking
    assert [a.name for a in accounts] == ["Alpha Savings", "Beta Card", "Gamma Checking"]
    # Verify inactive account excluded
    assert "AAA Inactive" not in [a.name for a in accounts]


def test_transaction_access_get_recent_transactions_for_month(db_session):
    """
    Verify get_recent_transactions_for_month:
    - Restricts to [start_date, end_date) interval.
    - Orders by date descending.
    - Limits to exactly DASHBOARD_RECENT_TRANSACTIONS_LIMIT (10).
    - Eager-loads the associated account relationship.
    """
    account = models.Account(name="Main Checking", type="depository", is_active=True)
    db_session.add(account)
    db_session.flush()

    # Create 14 transactions: 2 in May, 11 in June, 1 in July
    # May (excluded)
    db_session.add(models.Transaction(account_id=account.id, description="May 25", amount=Decimal("1.00"), date=date(2026, 5, 25)))
    db_session.add(models.Transaction(account_id=account.id, description="May 31", amount=Decimal("2.00"), date=date(2026, 5, 31)))

    # June (11 transactions from June 1 to June 11)
    for i in range(1, 12):
        db_session.add(
            models.Transaction(
                account_id=account.id,
                description=f"June {i:02d}",
                amount=Decimal(f"{i}.00"),
                date=date(2026, 6, i),
            )
        )

    # July (excluded)
    db_session.add(models.Transaction(account_id=account.id, description="July 01", amount=Decimal("99.00"), date=date(2026, 7, 1)))
    db_session.commit()

    # Query June interval [2026-06-01, 2026-07-01)
    recent = get_recent_transactions_for_month(db_session, date(2026, 6, 1), date(2026, 7, 1))

    # Exactly 10 records returned
    assert len(recent) == DASHBOARD_RECENT_TRANSACTIONS_LIMIT
    assert len(recent) == 10

    # Ordered date descending (June 11 down to June 2)
    assert recent[0].description == "June 11"
    assert recent[0].date == date(2026, 6, 11)
    assert recent[9].description == "June 02"
    assert recent[9].date == date(2026, 6, 2)

    # Verify associated account is eagerly loaded and matches
    for tx in recent:
        assert tx.account is not None
        assert tx.account.name == "Main Checking"
