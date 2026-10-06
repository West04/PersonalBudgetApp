"""
Tests for ML Model ResourceAccess (ml_model_access.py).

Verifies:
1. File artifact atomic replacement, loading, and cleanup.
2. PostgreSQL model metadata queries and monotonic revision increments.
3. Training label dataset queries respect approved provenance and transfer exclusion.
"""

import os
import shutil
import tempfile
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.access import ml_model_access
from backend.domain.ml_categorization import create_ml_pipeline


@pytest.fixture
def temp_model_dir(monkeypatch):
    d = tempfile.mkdtemp(prefix="ml_test_models_")
    monkeypatch.setattr(ml_model_access, "DEFAULT_MODEL_DIR", d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_model_artifact_save_activate_and_load(temp_model_dir):
    assert not ml_model_access.artifact_exists()
    assert ml_model_access.load_active_model() is None

    pipeline = create_ml_pipeline()
    pipeline.fit(["MERCHANT: a DESCRIPTION: a", "MERCHANT: b DESCRIPTION: b"], ["cat-a", "cat-b"])

    # 1. Save candidate to temp file
    temp_path = ml_model_access.save_candidate_model(pipeline)
    assert os.path.isfile(temp_path)
    # Active model still does not exist before activation
    assert not ml_model_access.artifact_exists()

    # 2. Activate candidate
    ml_model_access.activate_candidate_model(temp_path)
    assert ml_model_access.artifact_exists()
    assert not os.path.exists(temp_path)  # moved atomically

    # 3. Load active model
    loaded = ml_model_access.load_active_model()
    assert loaded is not None
    assert list(loaded.classes_) == ["cat-a", "cat-b"]
    assert ml_model_access.get_model_artifact_size_bytes() > 0


def test_cleanup_temp_candidate(temp_model_dir):
    temp_path = ml_model_access.get_temp_candidate_path()
    with open(temp_path, "w") as f:
        f.write("temporary data")
    assert os.path.exists(temp_path)

    ml_model_access.cleanup_temp_candidate(temp_path)
    assert not os.path.exists(temp_path)


def test_metadata_accessor_lifecycle(in_memory_db):
    # 1. Default creation
    meta = ml_model_access.get_model_metadata(in_memory_db)
    assert meta.id == 1
    assert meta.current_training_revision == 0
    assert meta.trained_revision == 0
    assert not meta.model_available

    # 2. Monotonic revision increment
    rev1 = ml_model_access.increment_training_revision(in_memory_db)
    assert rev1 == 1
    rev2 = ml_model_access.increment_training_revision(in_memory_db)
    assert rev2 == 2

    # 3. Update after training
    updated_meta = ml_model_access.update_model_metadata_after_training(
        db=in_memory_db,
        trained_revision=2,
        training_example_count=50,
        model_available=True,
        accuracy=0.85,
        macro_f1=0.82,
        top2_accuracy=0.95,
        coverage=0.90,
        status_message="Trained successfully",
    )
    assert updated_meta.trained_revision == 2
    assert updated_meta.training_example_count == 50
    assert updated_meta.model_available is True
    assert float(updated_meta.accuracy) == 0.85


def test_get_ml_training_examples_enforces_label_policy(in_memory_db):
    # Setup account and category
    group = models.CategoryGroup(name="Food", sort_order=0)
    in_memory_db.add(group)
    in_memory_db.commit()

    cat1 = models.Category(name="Groceries", group_id=group.category_group_id)
    cat2 = models.Category(name="Coffee", group_id=group.category_group_id)
    in_memory_db.add_all([cat1, cat2])
    in_memory_db.commit()

    acc = models.Account(name="Checking", type="depository")
    in_memory_db.add(acc)
    in_memory_db.commit()

    import datetime
    d = datetime.date(2026, 10, 5)

    # 1. Eligible manual transaction
    tx_manual = models.Transaction(
        account_id=acc.id,
        category_id=cat1.category_id,
        category_source="manual",
        description="Trader Joes",
        merchant="Trader Joes",
        amount=Decimal("20.00"),
        date=d,
        is_transfer=False,
    )
    # 2. Eligible ML-accepted transaction
    tx_ml = models.Transaction(
        account_id=acc.id,
        category_id=cat2.category_id,
        category_source="ml",
        description="Starbucks #1",
        merchant="Starbucks",
        amount=Decimal("5.00"),
        date=d,
        is_transfer=False,
    )
    # 3. Eligible legacy transaction (seed label)
    tx_legacy = models.Transaction(
        account_id=acc.id,
        category_id=cat1.category_id,
        category_source="legacy",
        description="Safeway",
        merchant="Safeway",
        amount=Decimal("35.00"),
        date=d,
        is_transfer=False,
    )
    # 4. EXCLUDED: Rule-assigned category
    tx_rule = models.Transaction(
        account_id=acc.id,
        category_id=cat1.category_id,
        category_source="rule",
        description="Rule Target",
        merchant="Target",
        amount=Decimal("40.00"),
        date=d,
        is_transfer=False,
    )
    # 5. EXCLUDED: Confirmed transfer
    tx_transfer = models.Transaction(
        account_id=acc.id,
        category_id=cat1.category_id,
        category_source="manual",
        description="Transfer to savings",
        merchant="Transfer",
        amount=Decimal("100.00"),
        date=d,
        is_transfer=True,
    )
    # 6. EXCLUDED: Uncategorized transaction
    tx_uncat = models.Transaction(
        account_id=acc.id,
        category_id=None,
        category_source=None,
        description="Uncategorized Store",
        merchant="Unknown",
        amount=Decimal("10.00"),
        date=d,
        is_transfer=False,
    )

    in_memory_db.add_all([tx_manual, tx_ml, tx_legacy, tx_rule, tx_transfer, tx_uncat])
    in_memory_db.commit()

    examples = ml_model_access.get_ml_training_examples(in_memory_db)
    example_ids = {e.transaction_id for e in examples}

    assert tx_manual.transaction_id in example_ids
    assert tx_ml.transaction_id in example_ids
    assert tx_legacy.transaction_id in example_ids
    assert tx_rule.transaction_id not in example_ids
    assert tx_transfer.transaction_id not in example_ids
    assert tx_uncat.transaction_id not in example_ids
    assert len(examples) == 3
