"""
Unit and characterization tests for ManualTransactionManager.create_transaction workflow.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from backend import models
from backend.access import categorization_rule_access, ml_model_access
from backend.managers import manual_transaction_manager


@pytest.fixture
def test_account(db_session: Session) -> models.Account:
    acc = models.Account(
        name="Test Checking",
        type="depository",
        subtype="checking",
    )
    db_session.add(acc)
    db_session.commit()
    db_session.refresh(acc)
    return acc


@pytest.fixture
def test_categories(db_session: Session) -> tuple[models.Category, models.Category]:
    group = models.CategoryGroup(name="Living")
    db_session.add(group)
    db_session.flush()

    cat1 = models.Category(name="Groceries", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Dining Out", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2])
    db_session.commit()
    db_session.refresh(cat1)
    db_session.refresh(cat2)
    return cat1, cat2


def test_create_transaction_explicit_category_sets_manual_and_bumps_revision(
    db_session: Session,
    test_account: models.Account,
    test_categories: tuple[models.Category, models.Category],
):
    cat_groceries, cat_dining = test_categories

    # Create a rule that would otherwise match
    categorization_rule_access.create_rule(db_session, "Trader Joes", cat_dining.category_id)

    meta_start = ml_model_access.get_model_metadata(db_session)
    rev_start = meta_start.current_training_revision

    # Explicit category provided: should win over rule and increment ML revision
    txn = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=cat_groceries.category_id,
        description="TRADER JOES #102",
        amount=Decimal("45.00"),
        transaction_date=date(2026, 7, 1),
    )

    assert txn.transaction_id is not None
    assert txn.category_id == cat_groceries.category_id
    assert txn.category_source == "manual"
    assert txn.merchant == "Trader Joes"
    assert txn.is_merchant_overridden is False

    # ML revision incremented exactly once
    meta_after = ml_model_access.get_model_metadata(db_session)
    assert meta_after.current_training_revision == rev_start + 1


def test_create_transaction_omitted_category_matching_rule_sets_rule_without_ml_bump(
    db_session: Session,
    test_account: models.Account,
    test_categories: tuple[models.Category, models.Category],
):
    _, cat_dining = test_categories
    categorization_rule_access.create_rule(db_session, "Starbucks", cat_dining.category_id)

    meta_start = ml_model_access.get_model_metadata(db_session)
    rev_start = meta_start.current_training_revision

    txn = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="STARBUCKS #1042",
        amount=Decimal("6.50"),
        transaction_date=date(2026, 7, 2),
    )

    assert txn.category_id == cat_dining.category_id
    assert txn.category_source == "rule"
    assert txn.merchant == "Starbucks"

    # ML revision must NOT increment for rule categorization
    meta_after = ml_model_access.get_model_metadata(db_session)
    assert meta_after.current_training_revision == rev_start


def test_create_transaction_omitted_category_no_matching_rule_remains_uncategorized(
    db_session: Session,
    test_account: models.Account,
):
    meta_start = ml_model_access.get_model_metadata(db_session)
    rev_start = meta_start.current_training_revision

    txn = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="UNKNOWN VENDOR XYZ",
        amount=Decimal("12.00"),
        transaction_date=date(2026, 7, 3),
    )

    assert txn.category_id is None
    assert txn.category_source is None
    assert txn.merchant == "Unknown Vendor Xyz"

    meta_after = ml_model_access.get_model_metadata(db_session)
    assert meta_after.current_training_revision == rev_start


def test_create_transaction_explicit_merchant_sets_override(
    db_session: Session,
    test_account: models.Account,
):
    txn = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="WHOLE FOODS #123",
        amount=Decimal("45.00"),
        transaction_date=date(2026, 7, 4),
        merchant="  Organic Market  ",
    )

    assert txn.description == "WHOLE FOODS #123"
    assert txn.merchant == "Organic Market"
    assert txn.is_merchant_overridden is True


def test_create_transaction_omitted_merchant_normalizes_from_description(
    db_session: Session,
    test_account: models.Account,
):
    txn = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="WHOLE FOODS #123",
        amount=Decimal("45.00"),
        transaction_date=date(2026, 7, 5),
        merchant=None,
    )

    assert txn.description == "WHOLE FOODS #123"
    assert txn.merchant == "Whole Foods"
    assert txn.is_merchant_overridden is False


def test_create_transaction_defaults_and_commit_refresh(
    db_session: Session,
    test_account: models.Account,
):
    now_dt = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    txn = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="Test Stored",
        amount=Decimal("25.00"),
        transaction_date=date(2026, 7, 6),
        transaction_datetime=now_dt,
        plaid_transaction_id="custom_plaid_tag",
    )

    assert txn.transaction_id is not None
    assert txn.account_id == test_account.id
    assert txn.pending is False
    assert txn.is_reviewed is False
    assert txn.is_transfer is False
    assert txn.datetime == now_dt
    assert txn.plaid_transaction_id == "custom_plaid_tag"

    # Confirmed committed in DB
    db_session.expire_all()
    reloaded = db_session.query(models.Transaction).filter_by(transaction_id=txn.transaction_id).one()
    assert reloaded.description == "Test Stored"


def test_create_transaction_mock_commit_and_refresh():
    mock_db = MagicMock()
    account_id = uuid4()
    tx = manual_transaction_manager.create_transaction(
        db=mock_db,
        account_id=account_id,
        category_id=None,
        description="Mock Create",
        amount=Decimal("10.00"),
        transaction_date=date(2026, 7, 7),
    )
    mock_db.add.assert_called_once_with(tx)
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once_with(tx)
