import pytest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from backend import models, schemas
from backend.access import (
    account_access,
    categorization_rule_access,
    category_access,
    ml_model_access,
    transaction_access,
)
from backend.managers import ml_categorization_manager, manual_transaction_manager


def _setup_base_data(db_session):
    group = models.CategoryGroup(name="Living")
    db_session.add(group)
    db_session.flush()

    cat1 = models.Category(name="Groceries", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    cat3 = models.Category(name="Utilities", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2, cat3])

    acc = models.Account(name="Checking", type="checking", current_balance=Decimal("1000.00"))
    db_session.add(acc)
    db_session.commit()
    return acc, [cat1, cat2, cat3]


def test_manual_creation_and_update_provenance(db_session):
    acc, cats = _setup_base_data(db_session)
    groceries, coffee, _ = cats

    initial_meta = ml_model_access.get_model_metadata(db_session)
    rev_start = initial_meta.current_training_revision

    # 1. Manual creation with category sets category_source='manual' and increments revision
    tx1 = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=acc.id,
        category_id=groceries.category_id,
        description="Trader Joe's groceries",
        amount=Decimal("45.00"),
        transaction_date=date(2026, 7, 1),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    assert tx1.category_source == "manual"
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start + 1

    # 2. Manual creation without category has category_source=None and does NOT increment revision
    tx2 = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=acc.id,
        category_id=None,
        description="Unknown Store",
        amount=Decimal("15.00"),
        transaction_date=date(2026, 7, 2),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    assert tx2.category_source is None
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start + 1

    # 3. Manual update changing category sets category_source='manual' and increments revision
    tx2_updated = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=tx2.transaction_id,
        update_data={"category_id": coffee.category_id},
    )
    assert tx2_updated.category_source == "manual"
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start + 2

    # 4. Manual update not touching category does not change revision
    transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=tx2.transaction_id,
        update_data={"description": "Updated description"},
    )
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start + 2

    # 5. Manual update clearing category sets category_source=None and does not increment revision
    tx2_cleared = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=tx2.transaction_id,
        update_data={"category_id": None},
    )
    assert tx2_cleared.category_id is None
    assert tx2_cleared.category_source is None
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start + 2


def test_rule_application_provenance_isolation(db_session):
    acc, cats = _setup_base_data(db_session)
    _, coffee, _ = cats

    # Create rule for Starbucks -> Coffee
    categorization_rule_access.create_rule(db_session, "Starbucks", coffee.category_id)
    initial_meta = ml_model_access.get_model_metadata(db_session)
    rev_start = initial_meta.current_training_revision

    # Create transaction matching Starbucks without explicit category
    tx = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=acc.id,
        category_id=None,
        description="STARBUCKS STORE #104",
        amount=Decimal("5.50"),
        transaction_date=date(2026, 7, 3),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )

    # Category was assigned by rule
    assert tx.category_id == coffee.category_id
    assert tx.category_source == "rule"
    # Revision must NOT increment for rule categorization
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start

    # Retroactive batch rule apply must also set category_source='rule' and NOT increment revision
    tx_uncat = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 4),
        amount=Decimal("6.00"),
        description="PEETS COFFEE",
        merchant="Peet's",
        is_merchant_overridden=False,
        category_id=None,
        category_source=None,
    )
    db_session.add(tx_uncat)
    db_session.commit()

    count = transaction_access.apply_category_to_uncategorized_by_merchant_key(
        db_session, "peet's", coffee.category_id
    )
    assert count == 1
    db_session.refresh(tx_uncat)
    assert tx_uncat.category_id == coffee.category_id
    assert tx_uncat.category_source == "rule"
    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start


def test_training_examples_filtering(db_session):
    acc, cats = _setup_base_data(db_session)
    groceries, coffee, utils = cats

    # 1. Manual -> included
    t_manual = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 1),
        amount=Decimal("10.00"),
        description="STORE 1",
        merchant="Store 1",
        category_id=groceries.category_id,
        category_source="manual",
        is_transfer=False,
    )
    # 2. Legacy -> included
    t_legacy = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 2),
        amount=Decimal("20.00"),
        description="STORE 2",
        merchant="Store 2",
        category_id=coffee.category_id,
        category_source="legacy",
        is_transfer=False,
    )
    # 3. ML accepted -> included
    t_ml = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 3),
        amount=Decimal("30.00"),
        description="STORE 3",
        merchant="Store 3",
        category_id=utils.category_id,
        category_source="ml",
        is_transfer=False,
    )
    # 4. Rule -> EXCLUDED
    t_rule = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 4),
        amount=Decimal("40.00"),
        description="STORE 4",
        merchant="Store 4",
        category_id=groceries.category_id,
        category_source="rule",
        is_transfer=False,
    )
    # 5. Transfer -> EXCLUDED even if categorized
    t_transfer = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 5),
        amount=Decimal("50.00"),
        description="TRANSFER",
        merchant="Bank",
        category_id=groceries.category_id,
        category_source="manual",
        is_transfer=True,
    )
    # 6. Uncategorized -> EXCLUDED
    t_uncat = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 6),
        amount=Decimal("60.00"),
        description="STORE 6",
        merchant="Store 6",
        category_id=None,
        category_source=None,
        is_transfer=False,
    )

    db_session.add_all([t_manual, t_legacy, t_ml, t_rule, t_transfer, t_uncat])
    db_session.commit()

    examples = ml_model_access.get_ml_training_examples(db_session)
    assert len(examples) == 3
    merchants = {ex.merchant for ex in examples}
    assert merchants == {"Store 1", "Store 2", "Store 3"}


def test_suggestion_acceptance_workflow(db_session):
    acc, cats = _setup_base_data(db_session)
    groceries, _, _ = cats

    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 10),
        amount=Decimal("18.50"),
        description="LOCAL BAKER",
        merchant="Local Baker",
        category_id=None,
        category_source=None,
        is_transfer=False,
    )
    db_session.add(tx)
    db_session.commit()

    initial_meta = ml_model_access.get_model_metadata(db_session)
    rev_start = initial_meta.current_training_revision

    updated_tx = ml_categorization_manager.accept_suggestion(
        db_session, tx.transaction_id, groceries.category_id
    )
    assert updated_tx.category_id == groceries.category_id
    assert updated_tx.category_source == "ml"

    meta = ml_model_access.get_model_metadata(db_session)
    assert meta.current_training_revision == rev_start + 1


def test_categorization_precedence(db_session):
    acc, cats = _setup_base_data(db_session)
    groceries, coffee, _ = cats

    # 1. Existing category -> returns None with already categorized reason
    tx_cat = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 1),
        amount=Decimal("10.00"),
        description="ALREADY CATEGORIZED",
        category_id=groceries.category_id,
        is_transfer=False,
    )
    db_session.add(tx_cat)
    db_session.commit()

    sug = ml_categorization_manager.predict_category_for_transaction(db_session, tx_cat.transaction_id)
    assert sug.suggested_category_id is None
    assert "already has an explicit category" in sug.reason

    # 2. Transfer -> returns None with transfer excluded reason
    tx_trans = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 2),
        amount=Decimal("100.00"),
        description="TRANSFER FUNDS",
        category_id=None,
        is_transfer=True,
    )
    db_session.add(tx_trans)
    db_session.commit()

    sug_trans = ml_categorization_manager.predict_category_for_transaction(db_session, tx_trans.transaction_id)
    assert sug_trans.suggested_category_id is None
    assert "transfers are excluded" in sug_trans.reason

    # 3. Rule match -> ML does nothing and yields to rule
    categorization_rule_access.create_rule(db_session, "Target", groceries.category_id)
    tx_target = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 3),
        amount=Decimal("25.00"),
        description="TARGET STORE #1234",
        merchant="Target",
        category_id=None,
        is_transfer=False,
    )
    db_session.add(tx_target)
    db_session.commit()

    sug_rule = ml_categorization_manager.predict_category_for_transaction(db_session, tx_target.transaction_id)
    assert sug_rule.suggested_category_id is None
    assert "deterministic rule" in sug_rule.reason
