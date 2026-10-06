import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from backend import models, schemas
from backend.access import ml_model_access


def _seed_db_with_labeled_data(db_session):
    acc = models.Account(name="Checking", type="checking", current_balance=Decimal("1000.00"))
    group = models.CategoryGroup(name="Everyday")
    db_session.add_all([acc, group])
    db_session.flush()

    cat_dining = models.Category(name="Dining", group_id=group.category_group_id, type="expense")
    cat_groceries = models.Category(name="Groceries", group_id=group.category_group_id, type="expense")
    cat_coffee = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat_dining, cat_groceries, cat_coffee])
    db_session.commit()

    # Create 12 labeled transactions (4 per category) with category_source='manual'
    dining_merchants = ["Chipotle", "Sweetgreen", "In-N-Out", "Shake Shack"]
    grocery_merchants = ["Whole Foods", "Trader Joe's", "Safeway", "Kroger"]
    coffee_merchants = ["Starbucks", "Peet's", "Blue Bottle", "Philz"]

    txs = []
    for m in dining_merchants:
        txs.append(
            models.Transaction(
                account_id=acc.id,
                date=date(2026, 7, 1),
                amount=Decimal("15.00"),
                description=f"{m.upper()} #123",
                merchant=m,
                category_id=cat_dining.category_id,
                category_source="manual",
                is_transfer=False,
            )
        )
    for m in grocery_merchants:
        txs.append(
            models.Transaction(
                account_id=acc.id,
                date=date(2026, 7, 2),
                amount=Decimal("50.00"),
                description=f"{m.upper()} STORE",
                merchant=m,
                category_id=cat_groceries.category_id,
                category_source="manual",
                is_transfer=False,
            )
        )
    for m in coffee_merchants:
        txs.append(
            models.Transaction(
                account_id=acc.id,
                date=date(2026, 7, 3),
                amount=Decimal("6.00"),
                description=f"{m.upper()} CAFE",
                merchant=m,
                category_id=cat_coffee.category_id,
                category_source="manual",
                is_transfer=False,
            )
        )

    db_session.add_all(txs)
    meta = ml_model_access.get_model_metadata(db_session)
    meta.current_training_revision = 12
    db_session.commit()

    return acc, [cat_dining, cat_groceries, cat_coffee]


def test_ml_status_api(client, db_session):
    resp = client.get("/ml/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in ["Ready", "Needs more data", "Stale"]
    assert "current_training_revision" in data
    assert "trained_revision" in data
    assert "training_example_count" in data
    assert "model_available" in data


def test_ml_retrain_insufficient_data(client, db_session):
    # Empty DB has 0 examples
    resp = client.post("/ml/retrain")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "Insufficient training data" in data["message"]


def test_ml_retrain_and_prediction_pipeline(client, db_session, monkeypatch, tmp_path):
    # Direct model artifact path to tmp_path for test isolation
    test_model_dir = str(tmp_path / "models")
    monkeypatch.setattr(ml_model_access, "DEFAULT_MODEL_DIR", test_model_dir)

    acc, cats = _seed_db_with_labeled_data(db_session)
    cat_dining, cat_groceries, cat_coffee = cats

    # 1. Retrain model
    retrain_resp = client.post("/ml/retrain")
    assert retrain_resp.status_code == 200
    retrain_data = retrain_resp.json()
    assert retrain_data["success"] is True
    assert retrain_data["model_activated"] is True
    assert retrain_data["status"]["training_example_count"] == 12
    assert retrain_data["status"]["model_available"] is True

    # 2. Check status reflects trained state
    status_resp = client.get("/ml/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["model_available"] is True
    assert status_data["status"] == "Ready"
    assert status_data["trained_revision"] == 12

    # 3. Create uncategorized transaction resembling Whole Foods
    tx_uncat = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 10),
        amount=Decimal("42.00"),
        description="WHOLE FOODS MARKET #10892",
        merchant="Whole Foods",
        category_id=None,
        category_source=None,
        is_transfer=False,
    )
    db_session.add(tx_uncat)
    db_session.commit()

    # 4. Request suggestion via single GET
    sug_resp = client.get(f"/transactions/{tx_uncat.transaction_id}/category-suggestion")
    assert sug_resp.status_code == 200
    sug = sug_resp.json()
    assert sug["suggested_category_id"] == str(cat_groceries.category_id)
    assert sug["suggested_category_name"] == "Groceries"
    assert sug["confidence"] is not None
    assert sug["confidence"] > 0.25

    # 5. Request batch suggestions via POST
    batch_resp = client.post(
        "/transactions/category-suggestions",
        json={"transaction_ids": [str(tx_uncat.transaction_id)]},
    )
    assert batch_resp.status_code == 200
    batch_data = batch_resp.json()
    assert str(tx_uncat.transaction_id) in batch_data["suggestions"]
    batch_sug = batch_data["suggestions"][str(tx_uncat.transaction_id)]
    assert batch_sug["suggested_category_id"] == str(cat_groceries.category_id)

    # 6. Accept suggestion
    accept_resp = client.post(
        f"/transactions/{tx_uncat.transaction_id}/accept-suggestion",
        json={"category_id": str(cat_groceries.category_id)},
    )
    assert accept_resp.status_code == 200
    accepted_data = accept_resp.json()
    assert accepted_data["category_id"] == str(cat_groceries.category_id)
    assert accepted_data["category_source"] == "ml"

    # Confirm revision incremented and status reflects 1 new label
    status_after = client.get("/ml/status").json()
    assert status_after["current_training_revision"] == 13
    assert status_after["new_labels_since_training"] == 1


def test_accept_suggestion_validations(client, db_session):
    acc, cats = _seed_db_with_labeled_data(db_session)
    groceries = cats[1]

    # Non-existent transaction returns 404
    fake_id = uuid4()
    resp_404 = client.post(
        f"/transactions/{fake_id}/accept-suggestion",
        json={"category_id": str(groceries.category_id)},
    )
    assert resp_404.status_code == 404

    # Non-existent category returns 404
    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 10),
        amount=Decimal("12.00"),
        description="TEST",
        category_id=None,
        is_transfer=False,
    )
    db_session.add(tx)
    db_session.commit()

    resp_bad_cat = client.post(
        f"/transactions/{tx.transaction_id}/accept-suggestion",
        json={"category_id": str(uuid4())},
    )
    assert resp_bad_cat.status_code == 404
