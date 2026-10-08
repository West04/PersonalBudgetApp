"""
Unit tests for Category ResourceAccess (backend/access/category_access.py).
Verifies concrete persistence contracts for Category and CategoryGroup operations.
"""

from uuid import uuid4
import pytest
from backend import models
from backend.access import category_access


def test_get_category_groups_ordering_and_eager_loading(db_session):
    g2 = models.CategoryGroup(name="Utilities", sort_order=2)
    g1 = models.CategoryGroup(name="Housing", sort_order=1)
    db_session.add_all([g2, g1])
    db_session.flush()

    c2 = models.Category(name="Water", group_id=g2.category_group_id, sort_order=2)
    c1 = models.Category(name="Electricity", group_id=g2.category_group_id, sort_order=1)
    c3 = models.Category(name="Rent", group_id=g1.category_group_id, sort_order=1)
    db_session.add_all([c2, c1, c3])
    db_session.commit()

    # Query via category_access
    groups = category_access.get_category_groups(db_session)
    assert len(groups) == 2

    # Group ordering by sort_order
    assert groups[0].name == "Housing"
    assert groups[0].sort_order == 1
    assert groups[1].name == "Utilities"
    assert groups[1].sort_order == 2

    # Eagerly loaded categories and their ordering by sort_order
    assert len(groups[0].categories) == 1
    assert groups[0].categories[0].name == "Rent"

    assert len(groups[1].categories) == 2
    assert [c.name for c in groups[1].categories] == ["Electricity", "Water"]


def test_get_category_groups_empty(db_session):
    groups = category_access.get_category_groups(db_session)
    assert list(groups) == []


def test_category_group_crud_lifecycle(db_session):
    # 1. Create
    created = category_access.create_category_group(db_session, name="Life Expenses", sort_order=3)
    assert created.category_group_id is not None
    assert created.name == "Life Expenses"
    assert created.sort_order == 3

    # 2. Get by ID
    fetched = category_access.get_category_group_by_id(db_session, created.category_group_id)
    assert fetched is not None
    assert fetched.name == "Life Expenses"

    # Nonexistent ID
    assert category_access.get_category_group_by_id(db_session, uuid4()) is None

    # 3. Update
    updated = category_access.update_category_group(
        db_session,
        created.category_group_id,
        {"name": "Living Expenses", "sort_order": 10},
    )
    assert updated is not None
    assert updated.name == "Living Expenses"
    assert updated.sort_order == 10

    # Nonexistent update
    assert category_access.update_category_group(db_session, uuid4(), {"name": "Ghost"}) is None

    # 4. Delete
    deleted = category_access.delete_category_group(db_session, created.category_group_id)
    assert deleted is not None
    assert category_access.get_category_group_by_id(db_session, created.category_group_id) is None

    # Nonexistent delete
    assert category_access.delete_category_group(db_session, uuid4()) is None


def test_delete_category_group_with_categories_raises_value_error(db_session):
    group = category_access.create_category_group(db_session, name="Group With Child")
    category_access.create_category(db_session, name="Child Cat", group_id=group.category_group_id)

    with pytest.raises(ValueError, match="Cannot delete category group containing categories"):
        category_access.delete_category_group(db_session, group.category_group_id)

    # Verify group and category remain in database
    assert category_access.get_category_group_by_id(db_session, group.category_group_id) is not None
    assert len(category_access.list_categories(db_session, group_id=group.category_group_id)) == 1


def test_reorder_category_groups_persistence(db_session):
    g1 = category_access.create_category_group(db_session, name="G1", sort_order=10)
    g2 = category_access.create_category_group(db_session, name="G2", sort_order=20)
    g3 = category_access.create_category_group(db_session, name="G3", sort_order=30)

    # 1. Duplicate IDs (last occurrence wins), unknown ID ignored, unlisted retained
    # Order: [g3, unknown, g1, g3] -> g1 gets 2, g3 gets 3, unknown ignored; g2 retained at 20
    unknown = uuid4()
    result = category_access.reorder_category_groups(
        db_session,
        [g3.category_group_id, unknown, g1.category_group_id, g3.category_group_id],
    )
    assert len(result) == 3
    db_session.refresh(g1)
    db_session.refresh(g2)
    db_session.refresh(g3)
    assert g1.sort_order == 2
    assert g3.sort_order == 3
    assert g2.sort_order == 20

    # 2. Empty list no-op
    res_empty = category_access.reorder_category_groups(db_session, [])
    assert len(res_empty) == 3
    db_session.refresh(g1)
    assert g1.sort_order == 2


def test_category_crud_lifecycle(db_session):
    group = category_access.create_category_group(db_session, name="Cat Parent")

    # 1. Create with defaults
    c1 = category_access.create_category(
        db_session,
        name="Coffee",
        group_id=group.category_group_id,
    )
    assert c1.category_id is not None
    assert c1.name == "Coffee"
    assert c1.group_id == group.category_group_id
    assert c1.sort_order == 0
    assert c1.type == "expense"
    assert c1.is_active is True

    # 2. Get by ID
    fetched = category_access.get_category_by_id(db_session, c1.category_id)
    assert fetched is not None
    assert fetched.name == "Coffee"
    assert category_access.get_category_by_id(db_session, uuid4()) is None

    # 3. Update
    updated = category_access.update_category(
        db_session,
        c1.category_id,
        {"name": "Specialty Coffee", "type": "income", "is_active": False},
    )
    assert updated is not None
    assert updated.name == "Specialty Coffee"
    assert updated.type == "income"
    assert updated.is_active is False
    assert category_access.update_category(db_session, uuid4(), {"name": "Ghost"}) is None

    # 4. Delete
    deleted = category_access.delete_category(db_session, c1.category_id)
    assert deleted is not None
    assert category_access.get_category_by_id(db_session, c1.category_id) is None
    assert category_access.delete_category(db_session, uuid4()) is None


def test_list_categories_all_and_filtered(db_session):
    g1 = category_access.create_category_group(db_session, name="Group 1")
    g2 = category_access.create_category_group(db_session, name="Group 2")

    c1 = category_access.create_category(db_session, name="C1", group_id=g1.category_group_id, sort_order=20)
    c2 = category_access.create_category(db_session, name="C2", group_id=g1.category_group_id, sort_order=10)
    c3 = category_access.create_category(db_session, name="C3", group_id=g2.category_group_id, sort_order=5)

    # All categories ordered by sort_order
    all_cats = category_access.list_categories(db_session)
    assert len(all_cats) == 3
    assert [c.name for c in all_cats] == ["C3", "C2", "C1"]

    # Filtered by group_id
    g1_cats = category_access.list_categories(db_session, group_id=g1.category_group_id)
    assert len(g1_cats) == 2
    assert [c.name for c in g1_cats] == ["C2", "C1"]


def test_reorder_categories_persistence(db_session):
    g1 = category_access.create_category_group(db_session, name="Group 1")
    g2 = category_access.create_category_group(db_session, name="Group 2")

    c1 = category_access.create_category(db_session, name="C1", group_id=g1.category_group_id, sort_order=10)
    c2 = category_access.create_category(db_session, name="C2", group_id=g1.category_group_id, sort_order=20)
    c3 = category_access.create_category(db_session, name="C3", group_id=g1.category_group_id, sort_order=30)
    c_other = category_access.create_category(db_session, name="C Other", group_id=g2.category_group_id, sort_order=40)

    # Reorder g1 with:
    # - duplicate ID c3: index 0 and index 2 -> last occurrence wins (2)
    # - c1: index 1
    # - c_other (cross-group): ignored -> retains 40
    # - unknown ID: ignored
    # - unlisted c2: retained at 20
    unknown = uuid4()
    ordered_ids = [c3.category_id, c1.category_id, c3.category_id, c_other.category_id, unknown]
    res = category_access.reorder_categories(db_session, group_id=g1.category_group_id, ordered_ids=ordered_ids)

    db_session.refresh(c1)
    db_session.refresh(c2)
    db_session.refresh(c3)
    db_session.refresh(c_other)

    assert c1.sort_order == 1
    assert c3.sort_order == 2
    assert c2.sort_order == 20
    assert c_other.sort_order == 40

    # Returned categories are only those for g1, ordered by sort_order: c1 (1), c3 (2), c2 (20)
    assert [c.name for c in res] == ["C1", "C3", "C2"]

    # Empty list no-op
    res_empty = category_access.reorder_categories(db_session, group_id=g1.category_group_id, ordered_ids=[])
    assert len(res_empty) == 3
