from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
import pytest

from backend import models
from backend.access.account_access import get_account_by_id
from backend.access.transaction_access import (
    csv_import_transaction_exists,
    stage_csv_import_transaction,
)


# ---------------------------------------------------------------------------
# Account ResourceAccess: get_account_by_id
# ---------------------------------------------------------------------------

def test_get_account_by_id_active(db_session):
    """Verify get_account_by_id retrieves an active account by primary key."""
    account = models.Account(
        name="Active Checking",
        type="depository",
        is_active=True,
        current_balance=Decimal("100.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    retrieved = get_account_by_id(db_session, account.id)
    assert retrieved is not None
    assert retrieved.id == account.id
    assert retrieved.name == "Active Checking"
    assert retrieved.is_active is True


def test_get_account_by_id_inactive(db_session):
    """
    Verify get_account_by_id does NOT filter out inactive accounts;
    inactive accounts remain eligible for CSV import.
    """
    account = models.Account(
        name="Inactive Savings",
        type="depository",
        is_active=False,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    retrieved = get_account_by_id(db_session, account.id)
    assert retrieved is not None
    assert retrieved.id == account.id
    assert retrieved.name == "Inactive Savings"
    assert retrieved.is_active is False


def test_get_account_by_id_missing(db_session):
    """Verify get_account_by_id returns None when UUID does not exist."""
    missing_id = uuid4()
    assert get_account_by_id(db_session, missing_id) is None


def test_get_account_by_id_no_type_filtering(db_session):
    """Verify get_account_by_id works for credit, depository, investment, and loan types."""
    types = ["depository", "credit", "investment", "loan"]
    for acct_type in types:
        acct = models.Account(
            name=f"Test {acct_type}",
            type=acct_type,
            current_balance=Decimal("0.00"),
            starting_balance=Decimal("0.00"),
            currency="USD",
        )
        db_session.add(acct)
        db_session.commit()

        retrieved = get_account_by_id(db_session, acct.id)
        assert retrieved is not None
        assert retrieved.id == acct.id
        assert retrieved.type == acct_type


# ---------------------------------------------------------------------------
# Transaction ResourceAccess: csv_import_transaction_exists
# ---------------------------------------------------------------------------

def test_csv_import_transaction_exists_exact_match(db_session):
    """Verify exact 4-field match returns True."""
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("0"), currency="USD")
    db_session.add(acct)
    db_session.flush()

    txn = models.Transaction(
        account_id=acct.id,
        date=date(2026, 6, 1),
        amount=Decimal("42.50"),
        description="Target Store",
        pending=False,
    )
    db_session.add(txn)
    db_session.commit()

    assert csv_import_transaction_exists(
        db_session,
        account_id=acct.id,
        transaction_date=date(2026, 6, 1),
        amount=Decimal("42.50"),
        description="Target Store",
    ) is True


def test_csv_import_transaction_exists_field_mismatches(db_session):
    """Verify mismatch in any of the 4 identity fields returns False."""
    acct1 = models.Account(name="Acct 1", type="depository", current_balance=Decimal("0"), currency="USD")
    acct2 = models.Account(name="Acct 2", type="depository", current_balance=Decimal("0"), currency="USD")
    db_session.add_all([acct1, acct2])
    db_session.flush()

    txn = models.Transaction(
        account_id=acct1.id,
        date=date(2026, 6, 1),
        amount=Decimal("42.50"),
        description="Target Store",
        pending=False,
    )
    db_session.add(txn)
    db_session.commit()

    # Different account
    assert csv_import_transaction_exists(
        db_session,
        account_id=acct2.id,
        transaction_date=date(2026, 6, 1),
        amount=Decimal("42.50"),
        description="Target Store",
    ) is False

    # Different date
    assert csv_import_transaction_exists(
        db_session,
        account_id=acct1.id,
        transaction_date=date(2026, 6, 2),
        amount=Decimal("42.50"),
        description="Target Store",
    ) is False

    # Different amount
    assert csv_import_transaction_exists(
        db_session,
        account_id=acct1.id,
        transaction_date=date(2026, 6, 1),
        amount=Decimal("42.51"),
        description="Target Store",
    ) is False

    # Case-sensitive description mismatch
    assert csv_import_transaction_exists(
        db_session,
        account_id=acct1.id,
        transaction_date=date(2026, 6, 1),
        amount=Decimal("42.50"),
        description="target store",
    ) is False


def test_csv_import_transaction_exists_ignored_fields_do_not_affect_match(db_session):
    """
    Verify ignored fields (pending, category_id, datetime, plaid_transaction_id, is_transfer)
    do not participate in the duplicate existence check.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("0"), currency="USD")
    grp = models.CategoryGroup(name="Grp", sort_order=0)
    db_session.add_all([acct, grp])
    db_session.flush()

    cat = models.Category(name="Shopping", group_id=grp.category_group_id, type="expense", sort_order=0)
    db_session.add(cat)
    db_session.flush()

    txn = models.Transaction(
        account_id=acct.id,
        category_id=cat.category_id,
        date=date(2026, 6, 1),
        amount=Decimal("50.00"),
        description="Grocery Store",
        datetime=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        pending=True,
        is_transfer=True,
        plaid_transaction_id="plaid_xyz_123",
    )
    db_session.add(txn)
    db_session.commit()

    # Query with exact 4 fields matches even though pending/category/etc. are not part of query
    assert csv_import_transaction_exists(
        db_session,
        account_id=acct.id,
        transaction_date=date(2026, 6, 1),
        amount=Decimal("50.00"),
        description="Grocery Store",
    ) is True


# ---------------------------------------------------------------------------
# Transaction ResourceAccess: stage_csv_import_transaction
# ---------------------------------------------------------------------------

def test_stage_csv_import_transaction_staged_in_session(db_session):
    """
    Verify stage_csv_import_transaction:
    - Instantiates models.Transaction with exact scalars.
    - plaid_transaction_id is explicitly None.
    - Adds to session (object in db_session.new).
    - Does NOT flush or commit.
    """
    acct = models.Account(name="Acct", type="depository", current_balance=Decimal("0"), currency="USD")
    db_session.add(acct)
    db_session.commit()

    txn_datetime = datetime(2026, 6, 1, 10, 30, tzinfo=timezone.utc)
    staged = stage_csv_import_transaction(
        db=db_session,
        account_id=acct.id,
        transaction_date=date(2026, 6, 1),
        amount=Decimal("19.99"),
        description="Bookstore",
        pending=False,
        category_id=None,
        transaction_datetime=txn_datetime,
    )

    # Verification of returned ORM model attributes
    assert isinstance(staged, models.Transaction)
    assert staged.account_id == acct.id
    assert staged.date == date(2026, 6, 1)
    assert staged.amount == Decimal("19.99")
    assert staged.description == "Bookstore"
    assert staged.pending is False
    assert staged.category_id is None
    assert staged.datetime == txn_datetime
    assert staged.plaid_transaction_id is None

    # Object is staged in Session.new
    assert staged in db_session.new
