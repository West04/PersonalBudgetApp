"""
Characterization tests for Budget Allocation CRUD HTTP endpoints and persistence behavior.

Captures existing behavior of backend/routers/budgets.py prior to VBD extraction:
- POST /budget/ creates a new budget allocation (201 Created).
  Enforces uniqueness of (budget_month, category_id) at DB level (_budget_month_category_uc).
  Duplicate creation triggers database IntegrityError.
  Nonexistent category_id triggers database IntegrityError (foreign key constraint).
- GET /budget/ lists budget allocations (200 OK), optionally filtered by budget_month query parameter.
  Returns empty list [] when no budgets match.
  Ordering is unspecified in SQL query.
- GET /budget/{budget_id} retrieves a budget by UUID (200 OK).
  404 Not Found with detail 'Category not found' if nonexistent.
- PUT /budget/{budget_id} updates planned_amount and/or budget_month (202 Accepted).
  Preserves omitted fields (exclude_unset=True).
  Explicit nulls for non-nullable columns trigger database IntegrityError.
  Updating to a conflicting (budget_month, category_id) triggers database IntegrityError.
  404 Not Found with detail 'Category not found or invalid update' if nonexistent.
- DELETE /budget/{budget_id} deletes a budget (204 No Content).
  404 Not Found with detail 'Category not found' if nonexistent.
  Deleting a budget has no cascade effect on other resources.
  Deleting a parent category cascade-deletes associated budgets (ondelete="CASCADE").
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_category(db_session, name: str = "Test Category") -> models.Category:
    group = models.CategoryGroup(name=f"Group for {name} {uuid4().hex[:6]}")
    db_session.add(group)
    db_session.flush()

    category = models.Category(name=name, group_id=group.category_group_id)
    db_session.add(category)
    db_session.commit()
    return category


# ---------------------------------------------------------------------------
# 1. Route Path & Trailing Slash Conventions
# ---------------------------------------------------------------------------

def test_budget_trailing_slash_redirect(client: TestClient):
    """
    FastAPI router prefix '/budget' with route '/' defaults to 307 Temporary Redirect
    when accessed without trailing slash.
    """
    response = client.get("/budget", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers.get("location") == "http://testserver/budget/"

    post_resp = client.post("/budget", json={}, follow_redirects=False)
    assert post_resp.status_code == 307
    assert post_resp.headers.get("location") == "http://testserver/budget/"


# ---------------------------------------------------------------------------
# 2. Budget Creation (POST /budget/)
# ---------------------------------------------------------------------------

def test_create_budget_success(client: TestClient, db_session):
    cat = _create_category(db_session, "Groceries")
    payload = {
        "budget_month": "2026-06-01",
        "planned_amount": "500.00",
        "category_id": str(cat.category_id),
    }

    response = client.post("/budget/", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "budget_id" in data
    assert data["budget_month"] == "2026-06-01"
    assert Decimal(str(data["planned_amount"])) == Decimal("500.00")
    assert data["category_id"] == str(cat.category_id)

    # Verify persisted in database
    db_record = db_session.query(models.Budget).filter_by(budget_id=data["budget_id"]).first()
    assert db_record is not None
    assert db_record.budget_month == date(2026, 6, 1)
    assert db_record.planned_amount == Decimal("500.00")
    assert db_record.category_id == cat.category_id


def test_create_budget_zero_amount(client: TestClient, db_session):
    cat = _create_category(db_session, "Zero Planned")
    payload = {
        "budget_month": "2026-06-01",
        "planned_amount": "0.00",
        "category_id": str(cat.category_id),
    }

    response = client.post("/budget/", json=payload)
    assert response.status_code == 201
    assert Decimal(str(response.json()["planned_amount"])) == Decimal("0.00")


def test_create_budget_negative_amount(client: TestClient, db_session):
    cat = _create_category(db_session, "Negative Planned")
    payload = {
        "budget_month": "2026-06-01",
        "planned_amount": "-150.00",
        "category_id": str(cat.category_id),
    }

    response = client.post("/budget/", json=payload)
    assert response.status_code == 201
    assert Decimal(str(response.json()["planned_amount"])) == Decimal("-150.00")


def test_create_budget_more_than_two_decimals_validation_error(client: TestClient, db_session):
    cat = _create_category(db_session, "Decimals")
    payload = {
        "budget_month": "2026-06-01",
        "planned_amount": "100.555",
        "category_id": str(cat.category_id),
    }

    response = client.post("/budget/", json=payload)
    assert response.status_code == 422


def test_create_budget_missing_required_fields_validation_error(client: TestClient, db_session):
    cat = _create_category(db_session, "Fields")

    # Missing planned_amount
    r1 = client.post("/budget/", json={"budget_month": "2026-06-01", "category_id": str(cat.category_id)})
    assert r1.status_code == 422

    # Missing budget_month
    r2 = client.post("/budget/", json={"planned_amount": "100.00", "category_id": str(cat.category_id)})
    assert r2.status_code == 422

    # Missing category_id
    r3 = client.post("/budget/", json={"budget_month": "2026-06-01", "planned_amount": "100.00"})
    assert r3.status_code == 422


def test_create_budget_nonexistent_category_integrity_error(client: TestClient):
    payload = {
        "budget_month": "2026-06-01",
        "planned_amount": "100.00",
        "category_id": str(uuid4()),
    }
    with pytest.raises(IntegrityError):
        client.post("/budget/", json=payload)


# ---------------------------------------------------------------------------
# 3. Persistence Identity & Duplicate Behavior
# ---------------------------------------------------------------------------

def test_create_duplicate_budget_integrity_error(client: TestClient, db_session):
    """
    Creating a budget with an identical (budget_month, category_id) violates
    _budget_month_category_uc and triggers an IntegrityError on commit.
    Database retains exactly 1 row with original value.
    """
    cat = _create_category(db_session, "Dup Cat")
    payload1 = {
        "budget_month": "2026-06-01",
        "planned_amount": "100.00",
        "category_id": str(cat.category_id),
    }

    r1 = client.post("/budget/", json=payload1)
    assert r1.status_code == 201

    payload2 = {
        "budget_month": "2026-06-01",
        "planned_amount": "999.00",
        "category_id": str(cat.category_id),
    }

    with pytest.raises(IntegrityError):
        client.post("/budget/", json=payload2)

    db_session.rollback()
    records = db_session.query(models.Budget).filter_by(category_id=cat.category_id).all()
    assert len(records) == 1
    assert records[0].planned_amount == Decimal("100.00")


def test_create_same_category_different_months_allowed(client: TestClient, db_session):
    cat = _create_category(db_session, "Multi Month")

    r1 = client.post("/budget/", json={
        "budget_month": "2026-06-01",
        "planned_amount": "100.00",
        "category_id": str(cat.category_id),
    })
    assert r1.status_code == 201

    r2 = client.post("/budget/", json={
        "budget_month": "2026-07-01",
        "planned_amount": "150.00",
        "category_id": str(cat.category_id),
    })
    assert r2.status_code == 201

    records = db_session.query(models.Budget).filter_by(category_id=cat.category_id).all()
    assert len(records) == 2


def test_create_different_categories_same_month_allowed(client: TestClient, db_session):
    c1 = _create_category(db_session, "Cat Alpha")
    c2 = _create_category(db_session, "Cat Beta")

    r1 = client.post("/budget/", json={
        "budget_month": "2026-06-01",
        "planned_amount": "100.00",
        "category_id": str(c1.category_id),
    })
    assert r1.status_code == 201

    r2 = client.post("/budget/", json={
        "budget_month": "2026-06-01",
        "planned_amount": "200.00",
        "category_id": str(c2.category_id),
    })
    assert r2.status_code == 201

    records = db_session.query(models.Budget).filter_by(budget_month=date(2026, 6, 1)).all()
    assert len(records) == 2


# ---------------------------------------------------------------------------
# 4. Read / List Endpoints (GET /budget/ and GET /budget/{budget_id})
# ---------------------------------------------------------------------------

def test_list_budgets_empty(client: TestClient):
    response = client.get("/budget/")
    assert response.status_code == 200
    assert response.json() == []


def test_list_budgets_unfiltered(client: TestClient, db_session):
    c1 = _create_category(db_session, "Cat 1")
    c2 = _create_category(db_session, "Cat 2")

    b1 = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=c1.category_id)
    b2 = models.Budget(budget_month=date(2026, 7, 1), planned_amount=Decimal("200.00"), category_id=c2.category_id)
    db_session.add_all([b1, b2])
    db_session.commit()

    response = client.get("/budget/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    ids = {item["budget_id"] for item in data}
    assert ids == {str(b1.budget_id), str(b2.budget_id)}


def test_list_budgets_filtered_by_month(client: TestClient, db_session):
    c1 = _create_category(db_session, "Cat June")
    c2 = _create_category(db_session, "Cat July")

    b1 = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=c1.category_id)
    b2 = models.Budget(budget_month=date(2026, 7, 1), planned_amount=Decimal("200.00"), category_id=c2.category_id)
    db_session.add_all([b1, b2])
    db_session.commit()

    response = client.get("/budget/?budget_month=2026-06-01")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["budget_id"] == str(b1.budget_id)
    assert data[0]["budget_month"] == "2026-06-01"


def test_list_budgets_filtered_by_month_no_matches(client: TestClient, db_session):
    c1 = _create_category(db_session, "Cat June")
    b1 = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=c1.category_id)
    db_session.add(b1)
    db_session.commit()

    response = client.get("/budget/?budget_month=2026-01-01")
    assert response.status_code == 200
    assert response.json() == []


def test_list_budgets_invalid_month_format_422(client: TestClient):
    response = client.get("/budget/?budget_month=not-a-date")
    assert response.status_code == 422


def test_get_budget_by_id_success(client: TestClient, db_session):
    cat = _create_category(db_session, "Detail Cat")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("350.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    response = client.get(f"/budget/{b.budget_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["budget_id"] == str(b.budget_id)
    assert data["budget_month"] == "2026-06-01"
    assert Decimal(str(data["planned_amount"])) == Decimal("350.00")
    assert data["category_id"] == str(cat.category_id)


def test_get_budget_by_id_not_found(client: TestClient):
    """
    Missing budget returns 404 with exact detail 'Category not found'.
    """
    response = client.get(f"/budget/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Category not found"}


def test_get_budget_by_id_invalid_uuid_422(client: TestClient):
    response = client.get("/budget/not-a-uuid")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 5. Budget Update (PUT /budget/{budget_id})
# ---------------------------------------------------------------------------

def test_update_budget_planned_amount_only(client: TestClient, db_session):
    cat = _create_category(db_session, "Update Amount")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    response = client.put(f"/budget/{b.budget_id}", json={"planned_amount": "250.00"})
    assert response.status_code == 202
    data = response.json()
    assert Decimal(str(data["planned_amount"])) == Decimal("250.00")
    assert data["budget_month"] == "2026-06-01"
    assert data["category_id"] == str(cat.category_id)

    db_session.refresh(b)
    assert b.planned_amount == Decimal("250.00")


def test_update_budget_budget_month_only(client: TestClient, db_session):
    cat = _create_category(db_session, "Update Month")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    response = client.put(f"/budget/{b.budget_id}", json={"budget_month": "2026-08-01"})
    assert response.status_code == 202
    data = response.json()
    assert data["budget_month"] == "2026-08-01"
    assert Decimal(str(data["planned_amount"])) == Decimal("100.00")

    db_session.refresh(b)
    assert b.budget_month == date(2026, 8, 1)


def test_update_budget_both_fields(client: TestClient, db_session):
    cat = _create_category(db_session, "Update Both")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    response = client.put(f"/budget/{b.budget_id}", json={
        "planned_amount": "400.00",
        "budget_month": "2026-09-01",
    })
    assert response.status_code == 202
    data = response.json()
    assert Decimal(str(data["planned_amount"])) == Decimal("400.00")
    assert data["budget_month"] == "2026-09-01"


def test_update_budget_empty_payload_preserves_all_fields(client: TestClient, db_session):
    cat = _create_category(db_session, "Empty Payload")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    response = client.put(f"/budget/{b.budget_id}", json={})
    assert response.status_code == 202
    data = response.json()
    assert Decimal(str(data["planned_amount"])) == Decimal("100.00")
    assert data["budget_month"] == "2026-06-01"
    assert data["category_id"] == str(cat.category_id)


def test_update_budget_explicit_null_planned_amount_integrity_error(client: TestClient, db_session):
    cat = _create_category(db_session, "Null Amount")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/budget/{b.budget_id}", json={"planned_amount": None})

    db_session.rollback()
    db_session.refresh(b)
    assert b.planned_amount == Decimal("100.00")


def test_update_budget_explicit_null_budget_month_integrity_error(client: TestClient, db_session):
    cat = _create_category(db_session, "Null Month")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/budget/{b.budget_id}", json={"budget_month": None})

    db_session.rollback()
    db_session.refresh(b)
    assert b.budget_month == date(2026, 6, 1)


def test_update_budget_duplicate_month_collision_integrity_error(client: TestClient, db_session):
    """
    Updating b2's month to match b1's month for the same category triggers
    _budget_month_category_uc violation and database IntegrityError.
    """
    cat = _create_category(db_session, "Collision Cat")
    b1 = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    b2 = models.Budget(budget_month=date(2026, 7, 1), planned_amount=Decimal("200.00"), category_id=cat.category_id)
    db_session.add_all([b1, b2])
    db_session.commit()

    with pytest.raises(IntegrityError):
        client.put(f"/budget/{b2.budget_id}", json={"budget_month": "2026-06-01"})

    db_session.rollback()
    db_session.refresh(b2)
    assert b2.budget_month == date(2026, 7, 1)


def test_update_budget_not_found(client: TestClient):
    """
    Updating nonexistent budget returns 404 with exact detail
    'Category not found or invalid update'.
    """
    response = client.put(f"/budget/{uuid4()}", json={"planned_amount": "100.00"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Category not found or invalid update"}


def test_update_budget_ignores_extra_category_id_field(client: TestClient, db_session):
    c1 = _create_category(db_session, "Cat 1")
    c2 = _create_category(db_session, "Cat 2")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=c1.category_id)
    db_session.add(b)
    db_session.commit()

    # Attempt to change category_id via PUT payload (extra field ignored by Pydantic)
    response = client.put(f"/budget/{b.budget_id}", json={"category_id": str(c2.category_id)})
    assert response.status_code == 202

    db_session.refresh(b)
    assert b.category_id == c1.category_id


# ---------------------------------------------------------------------------
# 6. Budget Deletion (DELETE /budget/{budget_id})
# ---------------------------------------------------------------------------

def test_delete_budget_success(client: TestClient, db_session):
    cat = _create_category(db_session, "Delete Cat")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    response = client.delete(f"/budget/{b.budget_id}")
    assert response.status_code == 204
    assert response.text == ""

    db_record = db_session.query(models.Budget).filter_by(budget_id=b.budget_id).first()
    assert db_record is None


def test_delete_budget_not_found(client: TestClient):
    """
    Deleting nonexistent budget returns 404 with exact detail 'Category not found'.
    """
    response = client.delete(f"/budget/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Category not found"}


def test_delete_budget_leaves_parent_category_intact(client: TestClient, db_session):
    cat = _create_category(db_session, "Surviving Cat")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    client.delete(f"/budget/{b.budget_id}")

    # Category still exists
    db_cat = db_session.query(models.Category).filter_by(category_id=cat.category_id).first()
    assert db_cat is not None


def test_delete_category_nullifies_budget_category_id(db_session):
    """
    Because Category.budgets relationship does not specify passive_deletes=True
    or cascade delete-orphan, and Budget.category_id is nullable, deleting a
    Category causes SQLAlchemy to set Budget.category_id to NULL.
    """
    cat = _create_category(db_session, "Cascade Cat")
    b = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(b)
    db_session.commit()

    db_session.delete(cat)
    db_session.commit()

    db_session.expire_all()
    db_b = db_session.query(models.Budget).filter_by(budget_id=b.budget_id).first()
    assert db_b is not None
    assert db_b.category_id is None


