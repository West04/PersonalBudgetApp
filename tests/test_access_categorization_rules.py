import pytest
from uuid import uuid4
from backend import models
from backend.access import categorization_rule_access


def test_create_and_get_rule(db_session):
    group = models.CategoryGroup(name="Daily Living")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.commit()

    rule = categorization_rule_access.create_rule(
        db=db_session,
        merchant="Starbucks",
        category_id=cat.category_id,
    )
    assert rule.id is not None
    assert rule.merchant == "Starbucks"
    assert rule.category_id == cat.category_id

    # Retrieve by ID
    fetched = categorization_rule_access.get_rule_by_id(db_session, rule.id)
    assert fetched is not None
    assert fetched.merchant == "Starbucks"
    assert fetched.category.name == "Coffee"

    # Retrieve by merchant (case-insensitive)
    assert categorization_rule_access.get_rule_by_merchant(db_session, "starbucks") is not None
    assert categorization_rule_access.get_rule_by_merchant(db_session, "  STARBUCKS  ") is not None
    assert categorization_rule_access.get_rule_by_merchant(db_session, "Peet's") is None


def test_create_rule_duplicate_refusal(db_session):
    group = models.CategoryGroup(name="Daily Living")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.commit()

    categorization_rule_access.create_rule(
        db=db_session,
        merchant="Starbucks",
        category_id=cat.category_id,
    )

    # Attempt to create duplicate with different casing/spaces
    with pytest.raises(ValueError, match="already exists"):
        categorization_rule_access.create_rule(
            db=db_session,
            merchant="  starbucks ",
            category_id=cat.category_id,
        )


def test_create_rule_validation(db_session):
    group = models.CategoryGroup(name="Daily Living")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.commit()

    # Blank merchant
    with pytest.raises(ValueError, match="cannot be blank"):
        categorization_rule_access.create_rule(
            db=db_session,
            merchant="   ",
            category_id=cat.category_id,
        )

    # Nonexistent category
    with pytest.raises(ValueError, match="not found"):
        categorization_rule_access.create_rule(
            db=db_session,
            merchant="Target",
            category_id=uuid4(),
        )


def test_update_and_delete_rule(db_session):
    group = models.CategoryGroup(name="Daily Living")
    db_session.add(group)
    db_session.flush()

    cat1 = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Groceries", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2])
    db_session.commit()

    rule = categorization_rule_access.create_rule(
        db=db_session,
        merchant="Starbucks",
        category_id=cat1.category_id,
    )

    # Update category
    updated = categorization_rule_access.update_rule(
        db=db_session,
        rule_id=rule.id,
        category_id=cat2.category_id,
    )
    assert updated.category_id == cat2.category_id

    # Update merchant
    updated2 = categorization_rule_access.update_rule(
        db=db_session,
        rule_id=rule.id,
        merchant="Starbucks Coffee",
    )
    assert updated2.merchant == "Starbucks Coffee"
    assert categorization_rule_access.get_rule_by_merchant(db_session, "starbucks") is None
    assert categorization_rule_access.get_rule_by_merchant(db_session, "Starbucks Coffee") is not None

    # Delete rule
    deleted = categorization_rule_access.delete_rule(db=db_session, rule_id=rule.id)
    assert deleted is not None
    assert categorization_rule_access.get_rule_by_id(db_session, rule.id) is None


def test_category_cascade_deletes_rule(db_session):
    group = models.CategoryGroup(name="Daily Living")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.commit()

    rule = categorization_rule_access.create_rule(
        db=db_session,
        merchant="Starbucks",
        category_id=cat.category_id,
    )
    rule_id = rule.id

    # Delete the category
    from backend.access import category_access
    category_access.delete_category(db_session, cat.category_id)

    # Dependent rule should be removed
    assert categorization_rule_access.get_rule_by_id(db_session, rule_id) is None


def test_canonical_uniqueness_create_and_edit_rejections(db_session):
    """
    Audit 1:
    create 'Starbucks'
    then create 'STARBUCKS' -> rejected
    then create ' Starbucks ' -> rejected
    edit another rule to '  STARBUCKS  ' -> rejected
    """
    group = models.CategoryGroup(name="Daily Living")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.commit()

    # 1. Create "Starbucks"
    r1 = categorization_rule_access.create_rule(db_session, "Starbucks", cat.category_id)
    assert r1.merchant == "Starbucks"

    # 2. Create "STARBUCKS" -> rejected
    with pytest.raises(ValueError, match="already exists"):
        categorization_rule_access.create_rule(db_session, "STARBUCKS", cat.category_id)

    # 3. Create " Starbucks " -> rejected
    with pytest.raises(ValueError, match="already exists"):
        categorization_rule_access.create_rule(db_session, " Starbucks ", cat.category_id)

    # 4. Create another rule "Peets"
    r2 = categorization_rule_access.create_rule(db_session, "Peets", cat.category_id)
    assert r2.merchant == "Peets"

    # 5. Edit "Peets" to "  STARBUCKS  " -> rejected
    with pytest.raises(ValueError, match="already exists"):
        categorization_rule_access.update_rule(db_session, r2.id, merchant="  STARBUCKS  ")


def test_database_constraint_canonical_uniqueness(db_session):
    """
    Audit 1:
    Verify direct persistence/database constraint behavior:
    PostgreSQL unique expression index uq_categorization_rules_merchant_canonical
    on lower(trim(merchant)) raises IntegrityError on duplicate bypass attempts.
    """
    from sqlalchemy.exc import IntegrityError

    group = models.CategoryGroup(name="Daily Living")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.commit()

    # Direct insert of "Starbucks"
    rule1 = models.CategorizationRule(merchant="Starbucks", category_id=cat.category_id)
    db_session.add(rule1)
    db_session.commit()

    # Direct insert of "STARBUCKS" (bypassing python validation)
    rule_dup_case = models.CategorizationRule(merchant="STARBUCKS", category_id=cat.category_id)
    db_session.add(rule_dup_case)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Direct insert of " Starbucks " (bypassing python validation)
    rule_dup_space = models.CategorizationRule(merchant=" Starbucks ", category_id=cat.category_id)
    db_session.add(rule_dup_space)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
