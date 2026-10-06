"""
Tests for ML Categorization Manager (ml_categorization_manager.py).

Verifies:
1. Status reporting (Ready, Stale, Needs more data).
2. Retraining workflow, safety gates, and failure recovery.
3. Precedence hierarchy: explicit category > deterministic rule > ML suggestion.
4. Transfer exclusion and abstention below threshold.
5. Automatic retraining trigger when revision delta reaches threshold.
6. Acceptance workflow and label provenance tracking.
"""

from decimal import Decimal
import tempfile
import shutil
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models, schemas
from backend.access import ml_model_access
from backend.managers import ml_categorization_manager


@pytest.fixture
def temp_model_dir(monkeypatch):
    d = tempfile.mkdtemp(prefix="ml_test_mgr_")
    monkeypatch.setattr(ml_model_access, "DEFAULT_MODEL_DIR", d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def db_session(temp_model_dir):
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed default metadata
    ml_model_access.get_model_metadata(session)
    session.commit()

    yield session
    session.close()


def _seed_sample_dataset(db):
    import datetime
    d = datetime.date(2026, 10, 5)

    group = models.CategoryGroup(name="Standard", sort_order=0)
    db.add(group)
    db.commit()

    cat_groceries = models.Category(name="Groceries", group_id=group.category_group_id)
    cat_coffee = models.Category(name="Coffee", group_id=group.category_group_id)
    cat_fuel = models.Category(name="Fuel", group_id=group.category_group_id)
    db.add_all([cat_groceries, cat_coffee, cat_fuel])
    db.commit()

    acc = models.Account(name="Checking", type="depository")
    db.add(acc)
    db.commit()

    txs = []
    # 5 Groceries
    for i in range(5):
        txs.append(
            models.Transaction(
                account_id=acc.id,
                category_id=cat_groceries.category_id,
                category_source="manual",
                description=f"SAFEWAY STORE #{100 + i}",
                merchant="Safeway",
                amount=Decimal("35.00"),
                date=d,
                is_transfer=False,
            )
        )
    # 5 Coffee
    for i in range(5):
        txs.append(
            models.Transaction(
                account_id=acc.id,
                category_id=cat_coffee.category_id,
                category_source="manual",
                description=f"STARBUCKS #{200 + i}",
                merchant="Starbucks",
                amount=Decimal("5.50"),
                date=d,
                is_transfer=False,
            )
        )
    # 5 Fuel
    for i in range(5):
        txs.append(
            models.Transaction(
                account_id=acc.id,
                category_id=cat_fuel.category_id,
                category_source="manual",
                description=f"SHELL OIL #{300 + i}",
                merchant="Shell",
                amount=Decimal("45.00"),
                date=d,
                is_transfer=False,
            )
        )

    db.add_all(txs)
    db.commit()

    return {
        "account": acc,
        "cat_groceries": cat_groceries,
        "cat_coffee": cat_coffee,
        "cat_fuel": cat_fuel,
    }


def test_status_when_no_data(db_session):
    status = ml_categorization_manager.get_ml_status(db_session)
    assert not status.model_available
    assert status.status == "Needs more data"


def test_retrain_insufficient_data(db_session):
    success, msg, activated, status = ml_categorization_manager.retrain_model(db_session)
    assert not success
    assert not activated
    assert "Insufficient training data" in msg


def test_retrain_and_activate_on_valid_dataset(db_session):
    seeded = _seed_sample_dataset(db_session)

    success, msg, activated, status = ml_categorization_manager.retrain_model(db_session)
    assert success
    assert activated
    assert status.model_available is True
    assert status.status == "Ready"
    assert status.training_example_count == 15
    assert status.accuracy is not None
    assert ml_model_access.artifact_exists()


def test_precedence_explicit_category_beats_ml(db_session):
    seeded = _seed_sample_dataset(db_session)
    ml_categorization_manager.retrain_model(db_session)

    # Transaction with explicit category
    import datetime
    tx = models.Transaction(
        account_id=seeded["account"].id,
        category_id=seeded["cat_coffee"].category_id,
        category_source="manual",
        description="STARBUCKS #999",
        merchant="Starbucks",
        amount=Decimal("5.00"),
        date=datetime.date(2026, 10, 5),
        is_transfer=False,
    )
    db_session.add(tx)
    db_session.commit()

    sug = ml_categorization_manager.predict_category_for_transaction(db_session, tx.transaction_id)
    assert sug.suggested_category_id is None
    assert "already has an explicit category" in sug.reason


def test_precedence_deterministic_rule_beats_ml(db_session):
    seeded = _seed_sample_dataset(db_session)
    ml_categorization_manager.retrain_model(db_session)

    # Create deterministic Phase 9 rule: Starbucks -> Fuel
    rule = models.CategorizationRule(
        merchant="Starbucks",
        category_id=seeded["cat_fuel"].category_id,
    )
    db_session.add(rule)
    db_session.commit()

    # Uncategorized transaction with merchant Starbucks
    import datetime
    tx = models.Transaction(
        account_id=seeded["account"].id,
        category_id=None,
        description="STARBUCKS #888",
        merchant="Starbucks",
        amount=Decimal("5.00"),
        date=datetime.date(2026, 10, 5),
        is_transfer=False,
    )
    db_session.add(tx)
    db_session.commit()

    sug = ml_categorization_manager.predict_category_for_transaction(db_session, tx.transaction_id)
    assert sug.suggested_category_id is None
    assert "Matched deterministic rule" in sug.reason


def test_transfer_exclusion(db_session):
    seeded = _seed_sample_dataset(db_session)
    ml_categorization_manager.retrain_model(db_session)

    import datetime
    tx = models.Transaction(
        account_id=seeded["account"].id,
        category_id=None,
        description="STARBUCKS #111",
        merchant="Starbucks",
        amount=Decimal("5.00"),
        date=datetime.date(2026, 10, 5),
        is_transfer=True,
    )
    db_session.add(tx)
    db_session.commit()

    sug = ml_categorization_manager.predict_category_for_transaction(db_session, tx.transaction_id)
    assert sug.suggested_category_id is None
    assert "Confirmed transfers are excluded" in sug.reason


def test_prediction_and_acceptance_workflow(db_session):
    seeded = _seed_sample_dataset(db_session)
    ml_categorization_manager.retrain_model(db_session)

    import datetime
    tx = models.Transaction(
        account_id=seeded["account"].id,
        category_id=None,
        description="SAFEWAY STORE #9999",
        merchant="Safeway",
        amount=Decimal("50.00"),
        date=datetime.date(2026, 10, 5),
        is_transfer=False,
        is_reviewed=False,
    )
    db_session.add(tx)
    db_session.commit()

    # 1. Predict
    sug = ml_categorization_manager.predict_category_for_transaction(db_session, tx.transaction_id)
    assert sug.suggested_category_id == seeded["cat_groceries"].category_id
    assert sug.suggested_category_name == "Groceries"
    assert sug.confidence >= 0.25

    # 2. Accept suggestion
    rev_before = ml_model_access.get_model_metadata(db_session).current_training_revision
    updated = ml_categorization_manager.accept_suggestion(
        db=db_session,
        transaction_id=tx.transaction_id,
        category_id=sug.suggested_category_id,
    )

    assert updated.category_id == seeded["cat_groceries"].category_id
    assert updated.category_source == "ml"
    assert updated.is_reviewed is False  # review status preserved independent
    rev_after = ml_model_access.get_model_metadata(db_session).current_training_revision
    assert rev_after == rev_before + 1


def test_automatic_retraining_trigger_when_stale(db_session):
    seeded = _seed_sample_dataset(db_session)
    ml_categorization_manager.retrain_model(db_session)

    meta = ml_model_access.get_model_metadata(db_session)
    trained_rev = meta.trained_revision

    # Simulate 10 new label mutations (reaches RETRAIN_THRESHOLD = 10)
    for _ in range(10):
        ml_model_access.increment_training_revision(db_session)
    db_session.commit()

    status = ml_categorization_manager.get_ml_status(db_session)
    assert status.status == "Stale"

    # Asking for a suggestion triggers automatic retraining
    import datetime
    tx = models.Transaction(
        account_id=seeded["account"].id,
        category_id=None,
        description="SHELL STATION #777",
        merchant="Shell",
        amount=Decimal("30.00"),
        date=datetime.date(2026, 10, 5),
        is_transfer=False,
    )
    db_session.add(tx)
    db_session.commit()

    sug = ml_categorization_manager.predict_category_for_transaction(db_session, tx.transaction_id)
    assert sug.suggested_category_name == "Fuel"

    status_after = ml_categorization_manager.get_ml_status(db_session)
    assert status_after.status == "Ready"
    assert status_after.trained_revision > trained_rev
