"""
Characterization tests for CategoryGroup and Category CRUD + Reorder endpoints.

Captures existing behavior of backend/routers/categories.py and backend/crud/category.py
prior to VBD extraction:
- CategoryGroup endpoints:
  - POST /category-groups (201, unique name, default sort_order=0)
  - GET /category-groups (200, nested categories, ordered by sort_order)
  - GET /category-groups/{group_id} (200 / 404 'Category Group not found')
  - PUT /category-groups/{group_id} (200 / 404 'Category Group not found', exclude_unset)
  - DELETE /category-groups/{group_id} (204 / 404 'Category Group not found', cascades to categories)
  - POST /category-groups/reorder (200, updates sort_order, ignores unknown IDs)
- Category endpoints:
  - POST /categories (201, requires group_id, uq on group_id+name, default type='expense', sort_order=0, is_active=True)
  - GET /categories (200, optional group_id filter, ordered by sort_order)
  - GET /categories/{category_id} (200 / 404 'Category not found')
  - PUT /categories/{category_id} (200 / 404 'Category not found', exclude_unset, supports moving groups)
  - DELETE /categories/{category_id} (204 / 404 'Category not found', sets Transaction.category_id=NULL, sets Budget.category_id=NULL)
  - POST /categories/reorder (200, updates sort_order within group, ignores categories of other groups)
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend import models, schemas
from sqlalchemy import text


@pytest.fixture(autouse=True)
def clean_categories(client: TestClient, db_session):
    """
    Ensure each test starts with an empty category/group table,
    clearing the default seed data inserted by the FastAPI lifespan hook.
    """
    db_session.execute(text("TRUNCATE TABLE transactions, budgets, categories, category_groups CASCADE;"))
    db_session.commit()



# ---------------------------------------------------------------------------
# 1. Category Group Endpoints
# ---------------------------------------------------------------------------

def test_list_category_groups_empty(client: TestClient):
    response = client.get("/category-groups")
    assert response.status_code == 200
    assert response.json() == []


def test_list_category_groups_ordering_and_nested_categories(client: TestClient, db_session):
    g2 = models.CategoryGroup(name="Personal", sort_order=20)
    g1 = models.CategoryGroup(name="Essentials", sort_order=10)
    db_session.add_all([g2, g1])
    db_session.flush()

    c2 = models.Category(name="Groceries", group_id=g1.category_group_id, sort_order=2)
    c1 = models.Category(name="Rent", group_id=g1.category_group_id, sort_order=1)
    c3 = models.Category(name="Hobbies", group_id=g2.category_group_id, sort_order=1)
    db_session.add_all([c2, c1, c3])
    db_session.commit()

    response = client.get("/category-groups")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Group ordering
    assert data[0]["name"] == "Essentials"
    assert data[0]["sort_order"] == 10
    assert data[1]["name"] == "Personal"
    assert data[1]["sort_order"] == 20

    # Nested category ordering
    assert [c["name"] for c in data[0]["categories"]] == ["Rent", "Groceries"]
    assert [c["name"] for c in data[1]["categories"]] == ["Hobbies"]


def test_read_category_group_found(client: TestClient, db_session):
    group = models.CategoryGroup(name="Subscriptions", sort_order=5)
    db_session.add(group)
    db_session.commit()

    response = client.get(f"/category-groups/{group.category_group_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["category_group_id"] == str(group.category_group_id)
    assert data["name"] == "Subscriptions"
    assert data["sort_order"] == 5


def test_read_category_group_missing_404(client: TestClient):
    response = client.get(f"/category-groups/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Category Group not found"


def test_create_category_group_success_and_defaults(client: TestClient, db_session):
    payload = {"name": "New Group"}
    response = client.post("/category-groups", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Group"
    assert data["sort_order"] == 0  # Default
    assert "category_group_id" in data

    # Verify persisted
    db_g = db_session.query(models.CategoryGroup).filter_by(name="New Group").first()
    assert db_g is not None
    assert db_g.sort_order == 0


def test_create_category_group_with_explicit_sort_order(client: TestClient, db_session):
    payload = {"name": "Custom Order Group", "sort_order": 42}
    response = client.post("/category-groups", json=payload)
    assert response.status_code == 201
    assert response.json()["sort_order"] == 42


def test_create_category_group_duplicate_name_integrity_error(client: TestClient, db_session):
    group = models.CategoryGroup(name="Existing Group")
    db_session.add(group)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.post("/category-groups", json={"name": "Existing Group"})


def test_create_category_group_missing_name_422(client: TestClient):
    response = client.post("/category-groups", json={})
    assert response.status_code == 422


def test_update_category_group_all_fields(client: TestClient, db_session):
    group = models.CategoryGroup(name="Old Name", sort_order=1)
    db_session.add(group)
    db_session.commit()

    response = client.put(
        f"/category-groups/{group.category_group_id}",
        json={"name": "Updated Name", "sort_order": 99}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["sort_order"] == 99

    db_session.refresh(group)
    assert group.name == "Updated Name"
    assert group.sort_order == 99


def test_update_category_group_partial_omitted_preserved(client: TestClient, db_session):
    group = models.CategoryGroup(name="Keep My Name", sort_order=5)
    db_session.add(group)
    db_session.commit()

    response = client.put(
        f"/category-groups/{group.category_group_id}",
        json={"sort_order": 12}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Keep My Name"
    assert data["sort_order"] == 12


def test_update_category_group_missing_404(client: TestClient):
    response = client.put(
        f"/category-groups/{uuid4()}",
        json={"name": "Ghost"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Category Group not found"


def test_delete_empty_category_group_success(client: TestClient, db_session):
    group = models.CategoryGroup(name="Empty Group")
    db_session.add(group)
    db_session.commit()

    response = client.delete(f"/category-groups/{group.category_group_id}")
    assert response.status_code == 204
    assert response.content == b""

    assert db_session.query(models.CategoryGroup).filter_by(category_group_id=group.category_group_id).first() is None


def test_delete_missing_category_group_404(client: TestClient):
    response = client.delete(f"/category-groups/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Category Group not found"


def test_delete_non_empty_category_group_rejected_and_all_data_preserved(client: TestClient, db_session):
    """
    Contract: Non-empty category-group deletion is rejected:
    - Non-empty group deletion fails with 400 Bad Request.
    - Error detail explains categories must be moved or deleted first.
    - Category group and child categories remain in DB.
    - Associated transactions retain original category_id (not nullified).
    - Associated budgets retain original category_id (not nullified).
    """
    group = models.CategoryGroup(name="Populated Group", sort_order=1)
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Populated Cat", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.flush()

    account = models.Account(name="Bank", type="depository")
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        category_id=cat.category_id,
        description="Dinner",
        amount=Decimal("35.00"),
        date=date(2026, 6, 1),
    )
    budget = models.Budget(
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("150.00"),
        category_id=cat.category_id,
    )
    db_session.add_all([tx, budget])
    db_session.commit()

    group_id = group.category_group_id
    cat_id = cat.category_id
    tx_id = tx.transaction_id
    budget_id = budget.budget_id

    response = client.delete(f"/category-groups/{group_id}")
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot delete category group containing categories. Move or delete categories first."

    db_session.expire_all()
    # Group and category preserved
    assert db_session.query(models.CategoryGroup).filter_by(category_group_id=group_id).first() is not None
    preserved_cat = db_session.query(models.Category).filter_by(category_id=cat_id).first()
    assert preserved_cat is not None
    assert preserved_cat.group_id == group_id

    # Transaction preserved with category_id unchanged
    db_tx = db_session.query(models.Transaction).filter_by(transaction_id=tx_id).first()
    assert db_tx is not None
    assert db_tx.category_id == cat_id

    # Budget preserved with category_id unchanged
    db_b = db_session.query(models.Budget).filter_by(budget_id=budget_id).first()
    assert db_b is not None
    assert db_b.category_id == cat_id


def test_delete_category_group_with_rules_and_splits_rejected_400(client: TestClient, db_session):
    """
    Regression test:
    When a category group has child categories referenced by categorization rules
    and transaction splits (which previously caused silent rule deletion or unhandled 500 RestrictViolation),
    the endpoint cleanly returns 400 Bad Request and leaves all data completely unmutated.
    """
    group = models.CategoryGroup(name="Complex Ref Group", sort_order=2)
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Complex Ref Cat", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.flush()

    rule = models.CategorizationRule(merchant="Target", category_id=cat.category_id)
    db_session.add(rule)

    account = models.Account(name="Split Checking", type="depository")
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        description="Target Store Split",
        amount=Decimal("100.00"),
        date=date(2026, 6, 2),
    )
    db_session.add(tx)
    db_session.flush()

    split = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat.category_id,
        amount=Decimal("100.00"),
    )
    db_session.add(split)
    db_session.commit()

    group_id = group.category_group_id
    cat_id = cat.category_id
    rule_id = rule.id
    split_id = split.id

    # Endpoint returns clean 400 without 500 IntegrityError
    response = client.delete(f"/category-groups/{group_id}")
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot delete category group containing categories. Move or delete categories first."

    db_session.expire_all()
    # Verify complete data preservation
    assert db_session.query(models.CategoryGroup).filter_by(category_group_id=group_id).first() is not None
    assert db_session.query(models.Category).filter_by(category_id=cat_id).first() is not None
    assert db_session.query(models.CategorizationRule).filter_by(id=rule_id).first() is not None
    assert db_session.query(models.TransactionSplit).filter_by(id=split_id).first() is not None


def test_reorder_category_groups_normal(client: TestClient, db_session):
    g1 = models.CategoryGroup(name="G1", sort_order=0)
    g2 = models.CategoryGroup(name="G2", sort_order=1)
    g3 = models.CategoryGroup(name="G3", sort_order=2)
    db_session.add_all([g1, g2, g3])
    db_session.commit()

    # Reorder to G3, G1, G2
    new_order = [str(g3.category_group_id), str(g1.category_group_id), str(g2.category_group_id)]
    response = client.post("/category-groups/reorder", json={"order": new_order})
    assert response.status_code == 200
    data = response.json()
    assert [g["name"] for g in data] == ["G3", "G1", "G2"]

    db_session.refresh(g1)
    db_session.refresh(g2)
    db_session.refresh(g3)
    assert g3.sort_order == 0
    assert g1.sort_order == 1
    assert g2.sort_order == 2


def test_reorder_category_groups_with_unknown_and_unlisted_ids(client: TestClient, db_session):
    g1 = models.CategoryGroup(name="Listed G1", sort_order=10)
    g2 = models.CategoryGroup(name="Unlisted G2", sort_order=50)
    db_session.add_all([g1, g2])
    db_session.commit()

    # Unknown ID is ignored; unlisted g2 retains sort_order=50
    response = client.post("/category-groups/reorder", json={"order": [str(uuid4()), str(g1.category_group_id)]})
    assert response.status_code == 200

    db_session.refresh(g1)
    db_session.refresh(g2)
    assert g1.sort_order == 1  # Index 1 in payload
    assert g2.sort_order == 50  # Unchanged


# ---------------------------------------------------------------------------
# 2. Category Endpoints
# ---------------------------------------------------------------------------

def test_list_categories_all_and_filtered_by_group(client: TestClient, db_session):
    g1 = models.CategoryGroup(name="Group 1")
    g2 = models.CategoryGroup(name="Group 2")
    db_session.add_all([g1, g2])
    db_session.flush()

    c1 = models.Category(name="C1", group_id=g1.category_group_id, sort_order=1)
    c2 = models.Category(name="C2", group_id=g1.category_group_id, sort_order=2)
    c3 = models.Category(name="C3", group_id=g2.category_group_id, sort_order=1)
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    # 1. Unfiltered list
    res_all = client.get("/categories")
    assert res_all.status_code == 200
    assert len(res_all.json()) == 3

    # 2. Filtered by group_id
    res_filtered = client.get(f"/categories?group_id={g1.category_group_id}")
    assert res_filtered.status_code == 200
    data = res_filtered.json()
    assert len(data) == 2
    assert [c["name"] for c in data] == ["C1", "C2"]


def test_read_category_found(client: TestClient, db_session):
    group = models.CategoryGroup(name="Parent Group")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Specific Cat", group_id=group.category_group_id, type="income", sort_order=3)
    db_session.add(cat)
    db_session.commit()

    response = client.get(f"/categories/{cat.category_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["category_id"] == str(cat.category_id)
    assert data["name"] == "Specific Cat"
    assert data["group_id"] == str(group.category_group_id)
    assert data["type"] == "income"
    assert data["sort_order"] == 3
    assert data["is_active"] is True


def test_read_category_missing_404(client: TestClient):
    response = client.get(f"/categories/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


def test_create_category_success_and_defaults(client: TestClient, db_session):
    group = models.CategoryGroup(name="Target Group")
    db_session.add(group)
    db_session.commit()

    payload = {
        "name": "Coffee",
        "group_id": str(group.category_group_id),
    }
    response = client.post("/categories", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Coffee"
    assert data["group_id"] == str(group.category_group_id)
    assert data["type"] == "expense"  # Default
    assert data["sort_order"] == 0   # Default
    assert data["is_active"] is True  # Default


def test_create_category_nonexistent_group_integrity_error(client: TestClient):
    payload = {
        "name": "Orphan",
        "group_id": str(uuid4()),
    }
    with pytest.raises(IntegrityError):
        client.post("/categories", json=payload)


def test_create_category_duplicate_name_in_same_group_integrity_error(client: TestClient, db_session):
    group = models.CategoryGroup(name="Same Group")
    db_session.add(group)
    db_session.flush()

    c1 = models.Category(name="Duplicates", group_id=group.category_group_id)
    db_session.add(c1)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.post("/categories", json={"name": "Duplicates", "group_id": str(group.category_group_id)})


def test_create_category_same_name_in_different_group_allowed(client: TestClient, db_session):
    g1 = models.CategoryGroup(name="Group A")
    g2 = models.CategoryGroup(name="Group B")
    db_session.add_all([g1, g2])
    db_session.flush()

    c1 = models.Category(name="Shared Name", group_id=g1.category_group_id)
    db_session.add(c1)
    db_session.commit()

    response = client.post("/categories", json={"name": "Shared Name", "group_id": str(g2.category_group_id)})
    assert response.status_code == 201
    assert response.json()["name"] == "Shared Name"
    assert response.json()["group_id"] == str(g2.category_group_id)


def test_update_category_fields_and_move_group(client: TestClient, db_session):
    g1 = models.CategoryGroup(name="Orig Group")
    g2 = models.CategoryGroup(name="New Group")
    db_session.add_all([g1, g2])
    db_session.flush()

    cat = models.Category(name="Moveable", group_id=g1.category_group_id, type="expense", sort_order=1, is_active=True)
    db_session.add(cat)
    db_session.commit()

    update_payload = {
        "name": "Moved & Renamed",
        "group_id": str(g2.category_group_id),
        "type": "transfer",
        "sort_order": 9,
        "is_active": False,
    }
    response = client.put(f"/categories/{cat.category_id}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Moved & Renamed"
    assert data["group_id"] == str(g2.category_group_id)
    assert data["type"] == "transfer"
    assert data["sort_order"] == 9
    assert data["is_active"] is False

    db_session.refresh(cat)
    assert cat.group_id == g2.category_group_id
    assert cat.is_active is False


def test_update_category_partial_omitted_preserved(client: TestClient, db_session):
    group = models.CategoryGroup(name="Stable Group")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Stable Cat", group_id=group.category_group_id, type="income", sort_order=4)
    db_session.add(cat)
    db_session.commit()

    response = client.put(f"/categories/{cat.category_id}", json={"is_active": False})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Stable Cat"
    assert data["type"] == "income"
    assert data["sort_order"] == 4
    assert data["is_active"] is False


def test_update_category_missing_404(client: TestClient):
    response = client.put(f"/categories/{uuid4()}", json={"name": "Ghost"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


def test_delete_category_success_and_referential_effects(client: TestClient, db_session):
    """
    Deleting a category:
    - Returns 204
    - Category deleted from DB
    - Transaction.category_id set to NULL
    - Budget.category_id set to NULL
    """
    group = models.CategoryGroup(name="Del Group")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Target Cat", group_id=group.category_group_id)
    db_session.add(cat)
    db_session.flush()

    account = models.Account(name="Bank Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        category_id=cat.category_id,
        description="Lunch",
        amount=Decimal("15.00"),
        date=date(2026, 6, 2),
    )
    budget = models.Budget(
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("50.00"),
        category_id=cat.category_id,
    )
    db_session.add_all([tx, budget])
    db_session.commit()

    cat_id = cat.category_id
    tx_id = tx.transaction_id
    budget_id = budget.budget_id

    response = client.delete(f"/categories/{cat_id}")
    assert response.status_code == 204
    assert response.content == b""

    db_session.expire_all()
    assert db_session.query(models.Category).filter_by(category_id=cat_id).first() is None

    db_tx = db_session.query(models.Transaction).filter_by(transaction_id=tx_id).first()
    assert db_tx is not None
    assert db_tx.category_id is None

    db_b = db_session.query(models.Budget).filter_by(budget_id=budget_id).first()
    assert db_b is not None
    assert db_b.category_id is None


def test_delete_category_missing_404(client: TestClient):
    response = client.delete(f"/categories/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


def test_reorder_categories_normal(client: TestClient, db_session):
    group = models.CategoryGroup(name="Group For Reorder")
    db_session.add(group)
    db_session.flush()

    c1 = models.Category(name="Cat 1", group_id=group.category_group_id, sort_order=0)
    c2 = models.Category(name="Cat 2", group_id=group.category_group_id, sort_order=1)
    c3 = models.Category(name="Cat 3", group_id=group.category_group_id, sort_order=2)
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    # Reverse: c3, c2, c1
    new_order = [str(c3.category_id), str(c2.category_id), str(c1.category_id)]
    response = client.post(
        "/categories/reorder",
        json={"group_id": str(group.category_group_id), "order": new_order}
    )
    assert response.status_code == 200
    data = response.json()
    assert [c["name"] for c in data] == ["Cat 3", "Cat 2", "Cat 1"]

    db_session.refresh(c1)
    db_session.refresh(c2)
    db_session.refresh(c3)
    assert c3.sort_order == 0
    assert c2.sort_order == 1
    assert c1.sort_order == 2


def test_reorder_categories_ignores_categories_from_other_groups(client: TestClient, db_session):
    g1 = models.CategoryGroup(name="Group 1")
    g2 = models.CategoryGroup(name="Group 2")
    db_session.add_all([g1, g2])
    db_session.flush()

    c1 = models.Category(name="Cat G1", group_id=g1.category_group_id, sort_order=10)
    c2 = models.Category(name="Cat G2", group_id=g2.category_group_id, sort_order=20)
    db_session.add_all([c1, c2])
    db_session.commit()

    # Attempt to reorder g1 including c2 from g2
    response = client.post(
        "/categories/reorder",
        json={"group_id": str(g1.category_group_id), "order": [str(c2.category_id), str(c1.category_id)]}
    )
    assert response.status_code == 200

    db_session.refresh(c1)
    db_session.refresh(c2)
    # c1 is index 1
    assert c1.sort_order == 1
    # c2 belongs to g2 so it was ignored and kept sort_order=20!
    assert c2.sort_order == 20


def test_reorder_categories_with_unknown_and_unlisted_ids(client: TestClient, db_session):
    """
    Category reorder:
    - Unknown IDs (UUIDs not in the database) are ignored without error.
    - Unlisted categories in the same group retain their existing sort_order.
    """
    group = models.CategoryGroup(name="Group For Unknown/Unlisted Cats")
    db_session.add(group)
    db_session.flush()

    c_listed = models.Category(name="Listed Cat", group_id=group.category_group_id, sort_order=10)
    c_unlisted = models.Category(name="Unlisted Cat", group_id=group.category_group_id, sort_order=50)
    db_session.add_all([c_listed, c_unlisted])
    db_session.commit()

    unknown_id = str(uuid4())
    payload = {
        "group_id": str(group.category_group_id),
        "order": [unknown_id, str(c_listed.category_id)],
    }
    response = client.post("/categories/reorder", json=payload)
    assert response.status_code == 200

    db_session.refresh(c_listed)
    db_session.refresh(c_unlisted)
    # c_listed was at payload index 1
    assert c_listed.sort_order == 1
    # c_unlisted was not in payload; sort_order=50 is retained
    assert c_unlisted.sort_order == 50



# ---------------------------------------------------------------------------
# 3. Edge Behavior: Explicit Null Updates
# ---------------------------------------------------------------------------

def test_update_category_group_explicit_null_name_integrity_error(client: TestClient, db_session):
    """
    Sending {"name": null} passes Pydantic validation (name: Optional[str] = None)
    and is included via exclude_unset=True. Mutating CategoryGroup.name to None
    violates nullable=False, raising IntegrityError on db.commit().
    The original name survives after rollback.
    """
    group = models.CategoryGroup(name="Surviving Group Name", sort_order=5)
    db_session.add(group)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/category-groups/{group.category_group_id}", json={"name": None})

    db_session.rollback()
    refreshed = db_session.query(models.CategoryGroup).filter_by(category_group_id=group.category_group_id).first()
    assert refreshed is not None
    assert refreshed.name == "Surviving Group Name"
    assert refreshed.sort_order == 5


def test_update_category_group_explicit_null_sort_order_integrity_error(client: TestClient, db_session):
    """
    Sending {"sort_order": null} passes Pydantic validation (sort_order: Optional[int] = None)
    and is included via exclude_unset=True. Mutating CategoryGroup.sort_order to None
    violates nullable=False, raising IntegrityError on db.commit().
    The original sort_order survives after rollback.
    """
    group = models.CategoryGroup(name="Fixed Order Group", sort_order=42)
    db_session.add(group)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/category-groups/{group.category_group_id}", json={"sort_order": None})

    db_session.rollback()
    refreshed = db_session.query(models.CategoryGroup).filter_by(category_group_id=group.category_group_id).first()
    assert refreshed is not None
    assert refreshed.name == "Fixed Order Group"
    assert refreshed.sort_order == 42


def test_update_category_group_distinguish_omission_from_explicit_null(client: TestClient, db_session):
    """
    Demonstrates the difference between omitted fields and explicit null:
    - Omission ({}) preserves fields and succeeds with 200 OK.
    - Explicit null ({"name": null} or {"sort_order": null}) triggers IntegrityError.
    """
    group = models.CategoryGroup(name="Omission Test Group", sort_order=10)
    db_session.add(group)
    db_session.commit()

    # Omission: {}
    response = client.put(f"/category-groups/{group.category_group_id}", json={})
    assert response.status_code == 200
    assert response.json()["name"] == "Omission Test Group"
    assert response.json()["sort_order"] == 10

    # Explicit null name
    with pytest.raises(IntegrityError):
        client.put(f"/category-groups/{group.category_group_id}", json={"name": None})
    db_session.rollback()

    # Explicit null sort_order
    with pytest.raises(IntegrityError):
        client.put(f"/category-groups/{group.category_group_id}", json={"sort_order": None})
    db_session.rollback()


def test_update_category_explicit_null_name_integrity_error(client: TestClient, db_session):
    """
    Sending {"name": null} to PUT /categories/{id} passes Pydantic validation and triggers
    IntegrityError at the DB level (Category.name nullable=False). Original name survives.
    """
    group = models.CategoryGroup(name="Parent G1")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Original Cat Name", group_id=group.category_group_id, sort_order=1)
    db_session.add(cat)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/categories/{cat.category_id}", json={"name": None})

    db_session.rollback()
    refreshed = db_session.query(models.Category).filter_by(category_id=cat.category_id).first()
    assert refreshed is not None
    assert refreshed.name == "Original Cat Name"


def test_update_category_explicit_null_group_id_integrity_error(client: TestClient, db_session):
    """
    Sending {"group_id": null} passes Pydantic validation (group_id: Optional[UUID] = None)
    and fails at the database level with IntegrityError (Category.group_id nullable=False).
    Original group_id survives.
    """
    group = models.CategoryGroup(name="Parent G2")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Cat With Group", group_id=group.category_group_id)
    db_session.add(cat)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/categories/{cat.category_id}", json={"group_id": None})

    db_session.rollback()
    refreshed = db_session.query(models.Category).filter_by(category_id=cat.category_id).first()
    assert refreshed is not None
    assert refreshed.group_id == group.category_group_id


def test_update_category_explicit_null_sort_order_integrity_error(client: TestClient, db_session):
    """
    Sending {"sort_order": null} passes Pydantic validation and triggers IntegrityError
    (Category.sort_order nullable=False). Original sort_order survives.
    """
    group = models.CategoryGroup(name="Parent G3")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Ordered Cat", group_id=group.category_group_id, sort_order=7)
    db_session.add(cat)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/categories/{cat.category_id}", json={"sort_order": None})

    db_session.rollback()
    refreshed = db_session.query(models.Category).filter_by(category_id=cat.category_id).first()
    assert refreshed is not None
    assert refreshed.sort_order == 7


def test_update_category_explicit_null_type_integrity_error(client: TestClient, db_session):
    """
    Sending {"type": null} passes Pydantic validation (type: Optional[CategoryType] = None)
    and triggers IntegrityError at the DB level (Category.type nullable=False).
    Original type survives.
    """
    group = models.CategoryGroup(name="Parent G4")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Typed Cat", group_id=group.category_group_id, type="income")
    db_session.add(cat)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/categories/{cat.category_id}", json={"type": None})

    db_session.rollback()
    refreshed = db_session.query(models.Category).filter_by(category_id=cat.category_id).first()
    assert refreshed is not None
    assert refreshed.type == "income"


def test_update_category_explicit_null_is_active_integrity_error(client: TestClient, db_session):
    """
    Sending {"is_active": null} passes Pydantic validation (is_active: Optional[bool] = None)
    and triggers IntegrityError at the DB level (Category.is_active nullable=False).
    Original is_active survives.
    """
    group = models.CategoryGroup(name="Parent G5")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Active Cat", group_id=group.category_group_id, is_active=True)
    db_session.add(cat)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/categories/{cat.category_id}", json={"is_active": None})

    db_session.rollback()
    refreshed = db_session.query(models.Category).filter_by(category_id=cat.category_id).first()
    assert refreshed is not None
    assert refreshed.is_active is True


def test_update_category_distinguish_omission_from_explicit_null(client: TestClient, db_session):
    """
    Demonstrates the difference between omitted fields and explicit null for categories:
    - Omission ({}) preserves all fields and succeeds with 200 OK.
    - Explicit null on any non-nullable column triggers IntegrityError.
    """
    group = models.CategoryGroup(name="Parent G6")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Stable Cat", group_id=group.category_group_id, type="expense", sort_order=3, is_active=True)
    db_session.add(cat)
    db_session.commit()

    # Omission: {}
    response = client.put(f"/categories/{cat.category_id}", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Stable Cat"
    assert data["group_id"] == str(group.category_group_id)
    assert data["type"] == "expense"
    assert data["sort_order"] == 3
    assert data["is_active"] is True


# ---------------------------------------------------------------------------
# 4. Edge Behavior: Reorder Empty and Duplicate Lists
# ---------------------------------------------------------------------------

def test_reorder_category_groups_empty_list(client: TestClient, db_session):
    """
    Sending {"order": []} to POST /category-groups/reorder:
    - Loop does not execute.
    - db.commit() runs.
    - Returns 200 OK with all category groups in their existing sort_order.
    - Existing database sort_orders remain unchanged.
    """
    g1 = models.CategoryGroup(name="Group 10", sort_order=10)
    g2 = models.CategoryGroup(name="Group 20", sort_order=20)
    db_session.add_all([g1, g2])
    db_session.commit()

    response = client.post("/category-groups/reorder", json={"order": []})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert [g["name"] for g in data] == ["Group 10", "Group 20"]
    assert [g["sort_order"] for g in data] == [10, 20]

    db_session.refresh(g1)
    db_session.refresh(g2)
    assert g1.sort_order == 10
    assert g2.sort_order == 20


def test_reorder_category_groups_duplicate_ids_last_occurrence_wins(client: TestClient, db_session):
    """
    Sending {"order": [A, B, A]} to POST /category-groups/reorder:
    - Loop updates sort_order = index sequentially.
    - Index 0 sets A.sort_order = 0.
    - Index 1 sets B.sort_order = 1.
    - Index 2 sets A.sort_order = 2 (overwrites index 0).
    - Last occurrence wins: A gets sort_order 2, B gets sort_order 1.
    - Returned list is ordered by sort_order: B, then A.
    """
    gA = models.CategoryGroup(name="Group A", sort_order=0)
    gB = models.CategoryGroup(name="Group B", sort_order=1)
    db_session.add_all([gA, gB])
    db_session.commit()

    payload = {"order": [str(gA.category_group_id), str(gB.category_group_id), str(gA.category_group_id)]}
    response = client.post("/category-groups/reorder", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert [g["name"] for g in data] == ["Group B", "Group A"]
    assert [g["sort_order"] for g in data] == [1, 2]

    db_session.refresh(gA)
    db_session.refresh(gB)
    assert gA.sort_order == 2
    assert gB.sort_order == 1


def test_reorder_categories_empty_list(client: TestClient, db_session):
    """
    Sending {"group_id": group_id, "order": []} to POST /categories/reorder:
    - Loop does not execute.
    - db.commit() runs.
    - Returns 200 OK with all categories in that group with their existing sort_orders.
    - Existing database sort_orders remain unchanged.
    """
    group = models.CategoryGroup(name="Parent Group Reorder Empty")
    db_session.add(group)
    db_session.flush()

    c1 = models.Category(name="C 5", group_id=group.category_group_id, sort_order=5)
    c2 = models.Category(name="C 15", group_id=group.category_group_id, sort_order=15)
    db_session.add_all([c1, c2])
    db_session.commit()

    payload = {"group_id": str(group.category_group_id), "order": []}
    response = client.post("/categories/reorder", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert [c["name"] for c in data] == ["C 5", "C 15"]
    assert [c["sort_order"] for c in data] == [5, 15]

    db_session.refresh(c1)
    db_session.refresh(c2)
    assert c1.sort_order == 5
    assert c2.sort_order == 15


def test_reorder_categories_duplicate_ids_last_occurrence_wins(client: TestClient, db_session):
    """
    Sending {"group_id": group_id, "order": [X, Y, X]} to POST /categories/reorder:
    - Loop updates sort_order = index sequentially.
    - Index 0 sets X.sort_order = 0.
    - Index 1 sets Y.sort_order = 1.
    - Index 2 sets X.sort_order = 2 (overwrites index 0).
    - Last occurrence wins: X gets sort_order 2, Y gets sort_order 1.
    - Returned list is ordered by sort_order: Y, then X.
    """
    group = models.CategoryGroup(name="Parent Group Reorder Dups")
    db_session.add(group)
    db_session.flush()

    cX = models.Category(name="Cat X", group_id=group.category_group_id, sort_order=0)
    cY = models.Category(name="Cat Y", group_id=group.category_group_id, sort_order=1)
    db_session.add_all([cX, cY])
    db_session.commit()

    payload = {
        "group_id": str(group.category_group_id),
        "order": [str(cX.category_id), str(cY.category_id), str(cX.category_id)],
    }
    response = client.post("/categories/reorder", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert [c["name"] for c in data] == ["Cat Y", "Cat X"]
    assert [c["sort_order"] for c in data] == [1, 2]

    db_session.refresh(cX)
    db_session.refresh(cY)
    assert cX.sort_order == 2
    assert cY.sort_order == 1

