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
from backend.access import (
    categorization_rule_access,
    ml_model_access,
    split_access,
    transaction_access,
)
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


# ===========================================================================
# Characterization Tests for ManualTransactionManager.update_transaction
# ===========================================================================


def test_update_transaction_missing_returns_none(db_session: Session):
    result = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=uuid4(),
        update_data={"description": "Ghost Transaction"},
    )
    assert result is None


def test_update_transaction_empty_payload_preserves_all_fields(
    db_session: Session,
    test_account: models.Account,
    test_categories: tuple[models.Category, models.Category],
):
    cat_groceries, _ = test_categories
    tx = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=cat_groceries.category_id,
        description="ORIGINAL GROCERY",
        amount=Decimal("50.00"),
        transaction_date=date(2026, 8, 1),
    )

    updated = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={},
    )
    assert updated is not None
    assert updated.description == "ORIGINAL GROCERY"
    assert updated.amount == Decimal("50.00")
    assert updated.date == date(2026, 8, 1)
    assert updated.category_id == cat_groceries.category_id
    assert updated.category_source == "manual"
    assert updated.merchant == "Original Grocery"
    assert updated.is_merchant_overridden is False
    assert updated.is_transfer is False
    assert updated.is_reviewed is False


def test_update_transaction_merchant_resolution_and_overrides(
    db_session: Session,
    test_account: models.Account,
):
    tx = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="SAFEWAY #123",
        amount=Decimal("30.00"),
        transaction_date=date(2026, 8, 2),
    )
    assert tx.merchant == "Safeway"
    assert tx.is_merchant_overridden is False

    # 1. Update description while not overridden renormalizes merchant
    up1 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"description": "TRADER JOES #456"},
    )
    assert up1.description == "TRADER JOES #456"
    assert up1.merchant == "Trader Joes"
    assert up1.is_merchant_overridden is False

    # 2. Explicit merchant sets override
    up2 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"merchant": "Neighborhood TJ"},
    )
    assert up2.merchant == "Neighborhood TJ"
    assert up2.is_merchant_overridden is True

    # 3. Update description when overridden preserves existing merchant
    up3 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"description": "TRADER JOES STORE #999"},
    )
    assert up3.description == "TRADER JOES STORE #999"
    assert up3.merchant == "Neighborhood TJ"
    assert up3.is_merchant_overridden is True

    # 4. Explicit blank / None merchant resets override and renormalizes from description
    up4 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"merchant": "   "},
    )
    assert up4.merchant == "Trader Joes"
    assert up4.is_merchant_overridden is False


def test_update_transaction_category_mutations_and_ml_revision(
    db_session: Session,
    test_account: models.Account,
    test_categories: tuple[models.Category, models.Category],
):
    cat_groceries, cat_dining = test_categories
    tx = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=cat_groceries.category_id,
        description="MARKET PURCHASE",
        amount=Decimal("40.00"),
        transaction_date=date(2026, 8, 3),
    )
    meta_start = ml_model_access.get_model_metadata(db_session)
    rev_start = meta_start.current_training_revision

    # 1. Changing to a different category sets source="manual" and increments ML revision
    up1 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"category_id": cat_dining.category_id},
    )
    assert up1.category_id == cat_dining.category_id
    assert up1.category_source == "manual"
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start + 1

    # 2. Supplying the same category does NOT increment ML revision
    up2 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"category_id": cat_dining.category_id},
    )
    assert up2.category_id == cat_dining.category_id
    assert up2.category_source == "manual"
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start + 1

    # 3. Explicitly clearing category (category_id=None) sets source=None, does NOT increment revision, and suppresses rule fallback
    # First create a rule matching the transaction's merchant
    categorization_rule_access.create_rule(db_session, tx.merchant, cat_groceries.category_id)

    up3 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"category_id": None},
    )
    assert up3.category_id is None
    assert up3.category_source is None
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start + 1


def test_update_transaction_rule_fallback_for_uncategorized(
    db_session: Session,
    test_account: models.Account,
    test_categories: tuple[models.Category, models.Category],
):
    cat_groceries, _ = test_categories
    categorization_rule_access.create_rule(db_session, "Target", cat_groceries.category_id)

    meta_start = ml_model_access.get_model_metadata(db_session)
    rev_start = meta_start.current_training_revision

    # Create an uncategorized transaction with an unmatched merchant
    tx = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="UNKNOWN STORE",
        amount=Decimal("25.00"),
        transaction_date=date(2026, 8, 4),
    )
    assert tx.category_id is None

    # Update description without matching rule and without category_id in payload
    up1 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"description": "SOME OTHER UNKNOWN #101"},
    )
    assert up1.merchant == "Some Other Unknown"
    assert up1.category_id is None

    # Now update merchant to "Target"
    up2 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"merchant": "Target"},
    )
    assert up2.category_id == cat_groceries.category_id
    assert up2.category_source == "rule"
    # ML revision must NOT increment for rule categorization
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start

    # When transaction is already categorized, merchant update preserves existing category (rule not applied)
    cat_other = test_categories[1]
    categorization_rule_access.create_rule(db_session, "Costco", cat_other.category_id)
    up3 = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"merchant": "Costco"},
    )
    # Target rule category preserved
    assert up3.category_id == cat_groceries.category_id
    assert up3.merchant == "Costco"


def test_update_transaction_normal_financial_and_metadata_fields(
    db_session: Session,
    test_account: models.Account,
):
    acc2 = models.Account(name="Savings Acc", type="depository")
    db_session.add(acc2)
    db_session.commit()

    tx = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="Initial Desc",
        amount=Decimal("15.00"),
        transaction_date=date(2026, 8, 5),
    )

    updated = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={
            "amount": Decimal("35.00"),
            "date": date(2026, 8, 10),
            "account_id": acc2.id,
            "is_transfer": True,
            "is_reviewed": True,
            "description": "Mutated Desc",
        },
    )
    assert updated.amount == Decimal("35.00")
    assert updated.date == date(2026, 8, 10)
    assert updated.account_id == acc2.id
    assert updated.is_transfer is True
    assert updated.is_reviewed is True
    assert updated.description == "Mutated Desc"


def test_update_transaction_split_guards(
    db_session: Session,
    test_account: models.Account,
    test_categories: tuple[models.Category, models.Category],
):
    cat1, cat2 = test_categories
    tx = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="Split Parent",
        amount=Decimal("100.00"),
        transaction_date=date(2026, 8, 6),
    )

    # Attach split rows
    split_access.stage_replace_splits(
        db=db_session,
        transaction_id=tx.transaction_id,
        allocations=[(cat1.category_id, Decimal("60.00")), (cat2.category_id, Decimal("40.00"))],
    )
    db_session.commit()
    assert split_access.transaction_has_splits(db_session, tx.transaction_id) is True

    # 1. Same amount is allowed
    up_same_amt = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"amount": Decimal("100.00")},
    )
    assert up_same_amt.amount == Decimal("100.00")

    # 2. Changed amount is rejected with exact string
    with pytest.raises(ValueError, match="^Cannot modify amount of a split transaction. Remove or edit split allocations first.$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"amount": Decimal("120.00")},
        )

    # 3. Category UUID is rejected with exact string
    with pytest.raises(ValueError, match="^Cannot directly assign a category to a split transaction. Use the unsplit workflow instead.$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"category_id": cat1.category_id},
        )

    # 4. Category None is rejected with exact string
    with pytest.raises(ValueError, match="^Cannot directly assign a category to a split transaction. Use the unsplit workflow instead.$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"category_id": None},
        )

    # 5. is_transfer=True is rejected with exact string
    with pytest.raises(ValueError, match="^Cannot mark a split transaction as a transfer.$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"is_transfer": True},
        )

    # 6. is_transfer=False is allowed
    up_tf = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"is_transfer": False},
    )
    assert up_tf.is_transfer is False

    # 7. Permitted metadata edits (description, merchant, date, is_reviewed)
    up_meta = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={
            "description": "Renamed Split Parent",
            "merchant": "New Merchant",
            "date": date(2026, 8, 7),
            "is_reviewed": True,
        },
    )
    assert up_meta.description == "Renamed Split Parent"
    assert up_meta.merchant == "New Merchant"
    assert up_meta.date == date(2026, 8, 7)
    assert up_meta.is_reviewed is True

    # 8. Rule fallback is suppressed for split transactions even if category_id is None and rule matches
    categorization_rule_access.create_rule(db_session, "New Merchant", cat1.category_id)
    up_rule = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={"description": "Another Note"},
    )
    assert up_rule.category_id is None


def test_update_transaction_reconciled_financial_guards(
    db_session: Session,
    test_account: models.Account,
    test_categories: tuple[models.Category, models.Category],
):
    acc2 = models.Account(name="Checking Reconciled 2", type="depository")
    db_session.add(acc2)
    db_session.commit()

    cat1, _ = test_categories
    tx = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=cat1.category_id,
        description="Reconciled Tx",
        amount=Decimal("75.00"),
        transaction_date=date(2026, 8, 8),
    )
    tx.is_cleared = True
    tx.is_reconciled = True
    db_session.commit()

    # 1. Identical amount, date, account_id allowed
    up_same = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={
            "amount": Decimal("75.00"),
            "date": date(2026, 8, 8),
            "account_id": test_account.id,
        },
    )
    assert up_same.amount == Decimal("75.00")

    # 2. Changed amount rejected with exact string
    with pytest.raises(ValueError, match="^Cannot modify financial fields \\(amount, date, account_id\\) of a reconciled transaction$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"amount": Decimal("80.00")},
        )

    # 3. Changed date rejected with exact string
    with pytest.raises(ValueError, match="^Cannot modify financial fields \\(amount, date, account_id\\) of a reconciled transaction$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"date": date(2026, 8, 9)},
        )

    # 4. Changed account_id rejected with exact string
    with pytest.raises(ValueError, match="^Cannot modify financial fields \\(amount, date, account_id\\) of a reconciled transaction$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"account_id": acc2.id},
        )

    # 5. Non-financial fields remain permitted
    up_nonfin = manual_transaction_manager.update_transaction(
        db=db_session,
        transaction_id=tx.transaction_id,
        update_data={
            "merchant": "Custom Reconciled Merchant",
            "description": "Edited Note",
            "is_reviewed": True,
        },
    )
    assert up_nonfin.merchant == "Custom Reconciled Merchant"
    assert up_nonfin.description == "Edited Note"
    assert up_nonfin.is_reviewed is True
    assert up_nonfin.is_reconciled is True


def test_update_transaction_combined_guard_precedence(
    db_session: Session,
    test_account: models.Account,
    test_categories: tuple[models.Category, models.Category],
):
    cat1, cat2 = test_categories
    tx = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="Combo Guard Tx",
        amount=Decimal("150.00"),
        transaction_date=date(2026, 8, 12),
    )
    split_access.stage_replace_splits(
        db=db_session,
        transaction_id=tx.transaction_id,
        allocations=[(cat1.category_id, Decimal("100.00")), (cat2.category_id, Decimal("50.00"))],
    )
    tx.is_reconciled = True
    db_session.commit()

    # A. Split + changed amount + reconciled -> split amount error takes precedence
    with pytest.raises(ValueError, match="^Cannot modify amount of a split transaction. Remove or edit split allocations first.$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"amount": Decimal("160.00")},
        )

    # B. Split + category presence + reconciled -> split category error takes precedence
    with pytest.raises(ValueError, match="^Cannot directly assign a category to a split transaction. Use the unsplit workflow instead.$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"category_id": cat1.category_id},
        )

    # C. Split + transfer True + reconciled -> split transfer error takes precedence
    with pytest.raises(ValueError, match="^Cannot mark a split transaction as a transfer.$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"is_transfer": True},
        )

    # D. Split with same amount + reconciled with changed date -> reconciled financial error
    with pytest.raises(ValueError, match="^Cannot modify financial fields \\(amount, date, account_id\\) of a reconciled transaction$"):
        manual_transaction_manager.update_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"amount": Decimal("150.00"), "date": date(2026, 8, 15)},
        )


def test_update_transaction_mock_commit_and_refresh():
    mock_db = MagicMock()
    mock_tx = MagicMock(spec=models.Transaction)
    mock_tx.amount = Decimal("50.00")
    mock_tx.is_reconciled = False
    mock_tx.is_merchant_overridden = False
    mock_tx.category_id = None
    mock_tx.merchant = "Test"

    # Mock get_transaction_by_id
    with MagicMock() as mock_ta:
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_tx

        # Mock split check to False
        mock_db.query.return_value.filter.return_value.first.return_value = None

        res = manual_transaction_manager.update_transaction(
            db=mock_db,
            transaction_id=uuid4(),
            update_data={"description": "Mock Update"},
        )
        assert res == mock_tx
        mock_db.add.assert_called_once_with(mock_tx)
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_tx)

