"""
Regression and data integrity tests for single-category deletion:
DELETE /categories/{category_id}

Verifies the semantic contract:
1. Splits block deletion with HTTP 400 and zero database mutations.
2. Transactions are preserved with category_id = NULL (uncategorized), category_source intact.
3. Monthly budgets are cascade-deleted (no orphaned category_id=NULL rows).
4. Categorization rules are cascade-deleted.
5. GET /budget/ and GET /budget/{id} remain valid without ResponseValidationError (HTTP 500).
6. GET /summaries/budget reflects clean removal of planned dollars without ghost records.
7. Database NOT NULL constraint on Budget.category_id is strictly enforced.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend import models
from backend.access import category_access


def _setup_group_and_cat(db_session, name="Test Cat"):
    group = models.CategoryGroup(name=f"Group for {name} {uuid4().hex[:6]}")
    db_session.add(group)
    db_session.flush()

    category = models.Category(name=name, group_id=group.category_group_id, type="expense")
    db_session.add(category)
    db_session.commit()
    return group, category


def test_category_delete_preserves_transaction_history(client: TestClient, db_session):
    """Transactions survive when category is deleted; category_id becomes NULL, category_source preserved."""
    group, cat = _setup_group_and_cat(db_session, "Tx History Cat")
    account = models.Account(name="Checking Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        category_id=cat.category_id,
        category_source="manual",
        description="Coffee Shop",
        amount=Decimal("4.50"),
        date=date(2026, 6, 15),
    )
    db_session.add(tx)
    db_session.commit()

    tx_id = tx.transaction_id
    cat_id = cat.category_id

    resp = client.delete(f"/categories/{cat_id}")
    assert resp.status_code == 204

    db_session.expire_all()
    assert db_session.query(models.Category).filter_by(category_id=cat_id).first() is None

    db_tx = db_session.query(models.Transaction).filter_by(transaction_id=tx_id).first()
    assert db_tx is not None
    assert db_tx.category_id is None
    assert db_tx.category_source == "manual"
    assert db_tx.amount == Decimal("4.50")


def test_category_delete_cascades_budget_unloaded(client: TestClient, db_session):
    """When category.budgets is NOT loaded into the session, deleting category cascades and deletes budget."""
    group, cat = _setup_group_and_cat(db_session, "Budget Unloaded Cat")
    budget = models.Budget(
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("120.00"),
        category_id=cat.category_id,
    )
    db_session.add(budget)
    db_session.commit()

    budget_id = budget.budget_id
    cat_id = cat.category_id

    resp = client.delete(f"/categories/{cat_id}")
    assert resp.status_code == 204

    db_session.expire_all()
    assert db_session.query(models.Budget).filter_by(budget_id=budget_id).first() is None


def test_category_delete_cascades_budget_loaded(db_session):
    """When category.budgets IS loaded into the session, deleting category cascades and deletes budget."""
    group, cat = _setup_group_and_cat(db_session, "Budget Loaded Cat")
    budget = models.Budget(
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("150.00"),
        category_id=cat.category_id,
    )
    db_session.add(budget)
    db_session.commit()

    cat_id = cat.category_id
    budget_id = budget.budget_id

    # Access cat.budgets to ensure relationship is loaded in session
    cat_loaded = category_access.get_category_by_id(db_session, cat_id)
    assert len(cat_loaded.budgets) == 1

    deleted_cat = category_access.delete_category(db_session, cat_id)
    assert deleted_cat is not None

    db_session.expire_all()
    assert db_session.query(models.Budget).filter_by(budget_id=budget_id).first() is None


def test_category_delete_cascades_categorization_rule(client: TestClient, db_session):
    """Categorization rules pointing to deleted category are cascade-deleted."""
    group, cat = _setup_group_and_cat(db_session, "Rule Cascade Cat")
    rule = models.CategorizationRule(merchant="Target", category_id=cat.category_id)
    db_session.add(rule)
    db_session.commit()

    rule_id = rule.id
    cat_id = cat.category_id

    resp = client.delete(f"/categories/{cat_id}")
    assert resp.status_code == 204

    db_session.expire_all()
    assert db_session.query(models.CategorizationRule).filter_by(id=rule_id).first() is None


def test_category_delete_atomic_combined_referents(client: TestClient, db_session):
    """Category with transaction, budget, and rule: all cascade/nullify atomically."""
    group, cat = _setup_group_and_cat(db_session, "Combined Cat")
    account = models.Account(name="Combined Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        category_id=cat.category_id,
        category_source="rule",
        description="Target Store",
        amount=Decimal("50.00"),
        date=date(2026, 6, 10),
    )
    budget = models.Budget(
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("200.00"),
        category_id=cat.category_id,
    )
    rule = models.CategorizationRule(merchant="Target Store", category_id=cat.category_id)
    db_session.add_all([tx, budget, rule])
    db_session.commit()

    cat_id = cat.category_id
    tx_id = tx.transaction_id
    budget_id = budget.budget_id
    rule_id = rule.id

    resp = client.delete(f"/categories/{cat_id}")
    assert resp.status_code == 204

    db_session.expire_all()
    # Category deleted
    assert db_session.query(models.Category).filter_by(category_id=cat_id).first() is None
    # Transaction preserved and uncategorized
    db_tx = db_session.query(models.Transaction).filter_by(transaction_id=tx_id).first()
    assert db_tx is not None
    assert db_tx.category_id is None
    assert db_tx.category_source == "rule"
    # Budget deleted
    assert db_session.query(models.Budget).filter_by(budget_id=budget_id).first() is None
    # Rule deleted
    assert db_session.query(models.CategorizationRule).filter_by(id=rule_id).first() is None


def test_category_delete_blocked_when_split_referenced(client: TestClient, db_session):
    """Split reference blocks category deletion (HTTP 400) and preserves all data unmutated."""
    group, cat = _setup_group_and_cat(db_session, "Split Protected Cat")
    account = models.Account(name="Split Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        description="Grocery Split",
        amount=Decimal("80.00"),
        date=date(2026, 6, 12),
    )
    db_session.add(tx)
    db_session.flush()

    split = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat.category_id,
        amount=Decimal("80.00"),
    )
    budget = models.Budget(
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("100.00"),
        category_id=cat.category_id,
    )
    rule = models.CategorizationRule(merchant="Grocery Mart", category_id=cat.category_id)
    db_session.add_all([split, budget, rule])
    db_session.commit()

    cat_id = cat.category_id
    split_id = split.id
    budget_id = budget.budget_id
    rule_id = rule.id

    resp = client.delete(f"/categories/{cat_id}")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Cannot delete category referenced by split allocations. Reassign or remove splits first."

    db_session.expire_all()
    # Verify zero database mutation
    assert db_session.query(models.Category).filter_by(category_id=cat_id).first() is not None
    assert db_session.query(models.TransactionSplit).filter_by(id=split_id).first() is not None
    assert db_session.query(models.Budget).filter_by(budget_id=budget_id).first() is not None
    assert db_session.query(models.CategorizationRule).filter_by(id=rule_id).first() is not None


def test_budget_api_reads_post_category_deletion(client: TestClient, db_session):
    """After deleting a category with a budget, GET /budget/ and GET /budget/{id} return clean responses without 500."""
    group, cat = _setup_group_and_cat(db_session, "API Read Cat")
    budget = models.Budget(
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("300.00"),
        category_id=cat.category_id,
    )
    db_session.add(budget)
    db_session.commit()

    cat_id = cat.category_id
    budget_id = budget.budget_id

    # Verify budget exists before deletion
    resp_get_before = client.get(f"/budget/{budget_id}")
    assert resp_get_before.status_code == 200
    assert resp_get_before.json()["category_id"] == str(cat_id)

    # Delete category
    del_resp = client.delete(f"/categories/{cat_id}")
    assert del_resp.status_code == 204

    # GET /budget/ must succeed (200 OK) and not crash with ResponseValidationError (500)
    list_resp = client.get("/budget/?budget_month=2026-06-01")
    assert list_resp.status_code == 200
    budgets_data = list_resp.json()
    assert all(b["budget_id"] != str(budget_id) for b in budgets_data)

    # GET /budget/{budget_id} must return 404 (established not-found response) rather than 500
    get_resp = client.get(f"/budget/{budget_id}")
    assert get_resp.status_code == 404
    assert get_resp.json()["detail"] == "Category not found"


def test_budget_summary_post_category_deletion(client: TestClient, db_session):
    """Deleting a category removes its planned amount from monthly summary without leaving ghost records."""
    group = models.CategoryGroup(name=f"Summary Group {uuid4().hex[:6]}")
    db_session.add(group)
    db_session.flush()

    cat_keep = models.Category(name="Keep Cat", group_id=group.category_group_id, type="expense")
    cat_del = models.Category(name="Del Cat", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat_keep, cat_del])
    db_session.flush()

    b_keep = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat_keep.category_id)
    b_del = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("50.00"), category_id=cat_del.category_id)
    db_session.add_all([b_keep, b_del])
    db_session.commit()

    # Pre-delete summary: planned expenses = 150.00
    pre_resp = client.get("/summary/budget?month=2026-06")
    assert pre_resp.status_code == 200
    pre_data = pre_resp.json()
    assert Decimal(str(pre_data["total_expense_planned"])) == Decimal("150.00")

    # Delete cat_del
    del_resp = client.delete(f"/categories/{cat_del.category_id}")
    assert del_resp.status_code == 204

    # Post-delete summary: planned expenses = 100.00, cat_del absent, no None entries
    post_resp = client.get("/summary/budget?month=2026-06")
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert Decimal(str(post_data["total_expense_planned"])) == Decimal("100.00")

    # Check categories in group
    target_group = next(g for g in post_data["groups"] if g["group_id"] == str(group.category_group_id))
    cat_ids = [c["category_id"] for c in target_group["categories"]]
    assert str(cat_keep.category_id) in cat_ids
    assert str(cat_del.category_id) not in cat_ids


def test_budget_category_id_db_not_null_enforcement(db_session):
    """Direct database verification that budgets.category_id rejects NULL values."""
    with pytest.raises(IntegrityError):
        b = models.Budget(
            budget_month=date(2026, 6, 1),
            planned_amount=Decimal("50.00"),
            category_id=None,
        )
        db_session.add(b)
        db_session.commit()
    db_session.rollback()
