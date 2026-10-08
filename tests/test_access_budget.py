"""
Unit tests for Budget ResourceAccess (backend/access/budget_access.py).
Verifies concrete persistence contracts for Budget allocation CRUD operations.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy.exc import IntegrityError

from backend import models
from backend.access import budget_access


def _create_category(db_session, name: str = "Test Category") -> models.Category:
    group = models.CategoryGroup(name=f"Group for {name} {uuid4().hex[:6]}")
    db_session.add(group)
    db_session.flush()

    category = models.Category(name=name, group_id=group.category_group_id)
    db_session.add(category)
    db_session.commit()
    return category


def test_budget_access_create_and_get_by_id(db_session):
    cat = _create_category(db_session, "Access Create")
    b = budget_access.create_budget(
        db=db_session,
        budget_month=date(2026, 6, 1),
        planned_amount=Decimal("250.00"),
        category_id=cat.category_id,
    )
    assert b.budget_id is not None
    assert b.budget_month == date(2026, 6, 1)
    assert b.planned_amount == Decimal("250.00")
    assert b.category_id == cat.category_id

    fetched = budget_access.get_budget_by_id(db_session, b.budget_id)
    assert fetched is not None
    assert fetched.budget_id == b.budget_id
    assert fetched.planned_amount == Decimal("250.00")


def test_budget_access_get_by_id_nonexistent_returns_none(db_session):
    assert budget_access.get_budget_by_id(db_session, uuid4()) is None


def test_budget_access_list_budgets_unfiltered(db_session):
    c1 = _create_category(db_session, "Cat A")
    c2 = _create_category(db_session, "Cat B")

    b1 = budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("100.00"), c1.category_id)
    b2 = budget_access.create_budget(db_session, date(2026, 7, 1), Decimal("200.00"), c2.category_id)

    all_budgets = budget_access.list_budgets(db_session)
    assert len(all_budgets) == 2
    ids = {b.budget_id for b in all_budgets}
    assert ids == {b1.budget_id, b2.budget_id}


def test_budget_access_list_budgets_filtered_by_month(db_session):
    c1 = _create_category(db_session, "Cat June")
    c2 = _create_category(db_session, "Cat July")

    b1 = budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("100.00"), c1.category_id)
    budget_access.create_budget(db_session, date(2026, 7, 1), Decimal("200.00"), c2.category_id)

    june_budgets = budget_access.list_budgets(db_session, budget_month=date(2026, 6, 1))
    assert len(june_budgets) == 1
    assert june_budgets[0].budget_id == b1.budget_id

    empty_budgets = budget_access.list_budgets(db_session, budget_month=date(2026, 1, 1))
    assert len(empty_budgets) == 0


def test_budget_access_update_budget_partial(db_session):
    cat = _create_category(db_session, "Cat Update")
    b = budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("100.00"), cat.category_id)

    updated = budget_access.update_budget(
        db=db_session,
        budget_id=b.budget_id,
        update_data={"planned_amount": Decimal("350.00")},
    )
    assert updated is not None
    assert updated.planned_amount == Decimal("350.00")
    assert updated.budget_month == date(2026, 6, 1)


def test_budget_access_update_budget_empty_mapping_noop(db_session):
    cat = _create_category(db_session, "Cat Noop")
    b = budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("100.00"), cat.category_id)

    updated = budget_access.update_budget(
        db=db_session,
        budget_id=b.budget_id,
        update_data={},
    )
    assert updated is not None
    assert updated.planned_amount == Decimal("100.00")
    assert updated.budget_month == date(2026, 6, 1)


def test_budget_access_update_budget_nonexistent_returns_none(db_session):
    assert budget_access.update_budget(db_session, uuid4(), {"planned_amount": Decimal("10.00")}) is None


def test_budget_access_update_explicit_none_triggers_integrity_error(db_session):
    cat = _create_category(db_session, "Cat None")
    b = budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("100.00"), cat.category_id)

    with pytest.raises(IntegrityError):
        budget_access.update_budget(db_session, b.budget_id, {"planned_amount": None})
    db_session.rollback()

    with pytest.raises(IntegrityError):
        budget_access.update_budget(db_session, b.budget_id, {"budget_month": None})
    db_session.rollback()


def test_budget_access_delete_budget_existing(db_session):
    cat = _create_category(db_session, "Cat Delete")
    b = budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("100.00"), cat.category_id)

    deleted = budget_access.delete_budget(db_session, b.budget_id)
    assert deleted is not None
    assert deleted.budget_id == b.budget_id
    assert budget_access.get_budget_by_id(db_session, b.budget_id) is None


def test_budget_access_delete_budget_nonexistent_returns_none(db_session):
    assert budget_access.delete_budget(db_session, uuid4()) is None


def test_budget_access_create_duplicate_triggers_integrity_error(db_session):
    cat = _create_category(db_session, "Cat Dup")
    budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("100.00"), cat.category_id)

    with pytest.raises(IntegrityError):
        budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("200.00"), cat.category_id)
    db_session.rollback()


def test_budget_access_update_duplicate_collision_triggers_integrity_error(db_session):
    cat = _create_category(db_session, "Cat Collision")
    b1 = budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("100.00"), cat.category_id)
    b2 = budget_access.create_budget(db_session, date(2026, 7, 1), Decimal("200.00"), cat.category_id)

    with pytest.raises(IntegrityError):
        budget_access.update_budget(db_session, b2.budget_id, {"budget_month": date(2026, 6, 1)})
    db_session.rollback()


def test_budget_access_create_invalid_fk_triggers_integrity_error(db_session):
    with pytest.raises(IntegrityError):
        budget_access.create_budget(db_session, date(2026, 6, 1), Decimal("100.00"), uuid4())
    db_session.rollback()


def test_budget_access_create_null_category_triggers_integrity_error(db_session):
    """Verifies that the database enforces NOT NULL constraint on Budget.category_id."""
    with pytest.raises(IntegrityError):
        b = models.Budget(
            budget_month=date(2026, 6, 1),
            planned_amount=Decimal("100.00"),
            category_id=None,
        )
        db_session.add(b)
        db_session.commit()
    db_session.rollback()

