"""
Resource access functions for CategorizationRule PostgreSQL resources.
"""

from collections.abc import Sequence
from typing import Optional
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..domain.categorization_rules import clean_merchant_key
from . import category_access


def get_rules(db: Session) -> Sequence[models.CategorizationRule]:
    """
    Retrieves all categorization rules ordered by canonical merchant (lower(trim(merchant))),
    eagerly loading the target Category.
    """
    return (
        db.query(models.CategorizationRule)
        .options(joinedload(models.CategorizationRule.category))
        .order_by(func.lower(func.trim(models.CategorizationRule.merchant)).asc())
        .all()
    )


def get_rule_by_id(
    db: Session,
    rule_id: UUID,
) -> Optional[models.CategorizationRule]:
    """
    Retrieves a single categorization rule by primary key UUID,
    eagerly loading the target Category.
    """
    return (
        db.query(models.CategorizationRule)
        .options(joinedload(models.CategorizationRule.category))
        .filter(models.CategorizationRule.id == rule_id)
        .first()
    )


def get_rule_by_merchant(
    db: Session,
    merchant: Optional[str],
) -> Optional[models.CategorizationRule]:
    """
    Retrieves a rule by exact canonical merchant key (lower(trim(merchant))).
    Returns None if merchant is None, empty, or no rule matches.
    """
    clean_key = clean_merchant_key(merchant)
    if not clean_key:
        return None

    return (
        db.query(models.CategorizationRule)
        .options(joinedload(models.CategorizationRule.category))
        .filter(func.lower(func.trim(models.CategorizationRule.merchant)) == clean_key)
        .first()
    )


def get_rules_lookup_dict(db: Session) -> dict[str, UUID]:
    """
    Loads all active rules and returns an in-memory dictionary mapping
    clean_merchant_key -> category_id.
    Enables O(1) matching during batch imports (CSV / Plaid sync).
    """
    rules = db.query(models.CategorizationRule.merchant, models.CategorizationRule.category_id).all()
    result: dict[str, UUID] = {}
    for r_merchant, r_cat_id in rules:
        k = clean_merchant_key(r_merchant)
        if k:
            result[k] = r_cat_id
    return result


def create_rule(
    db: Session,
    merchant: str,
    category_id: UUID,
) -> models.CategorizationRule:
    """
    Creates and persists a new categorization rule.
    Validates:
    - Merchant cannot be empty or whitespace.
    - Category must exist.
    - No existing rule with the same case-insensitive merchant.
    Owns the standalone CRUD transaction boundary.
    """
    clean_key = clean_merchant_key(merchant)
    if not clean_key:
        raise ValueError("Merchant cannot be blank.")

    cat = category_access.get_category_by_id(db, category_id)
    if not cat:
        raise ValueError(f"Category {category_id} not found.")

    existing = get_rule_by_merchant(db, merchant)
    if existing:
        raise ValueError(f"A categorization rule for merchant '{existing.merchant}' already exists.")

    normalized_merchant_str = " ".join(merchant.split()).strip()

    rule = models.CategorizationRule(
        merchant=normalized_merchant_str,
        category_id=category_id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(
    db: Session,
    rule_id: UUID,
    merchant: Optional[str] = None,
    category_id: Optional[UUID] = None,
) -> Optional[models.CategorizationRule]:
    """
    Updates an existing categorization rule.
    Validates:
    - If merchant provided: cannot be blank, and must not collide with another rule.
    - If category_id provided: target category must exist.
    Owns the standalone CRUD transaction boundary.
    """
    rule = get_rule_by_id(db, rule_id)
    if rule is None:
        return None

    if merchant is not None:
        clean_key = clean_merchant_key(merchant)
        if not clean_key:
            raise ValueError("Merchant cannot be blank.")
        existing = get_rule_by_merchant(db, merchant)
        if existing and existing.id != rule_id:
            raise ValueError(f"A categorization rule for merchant '{existing.merchant}' already exists.")
        rule.merchant = " ".join(merchant.split()).strip()

    if category_id is not None:
        cat = category_access.get_category_by_id(db, category_id)
        if not cat:
            raise ValueError(f"Category {category_id} not found.")
        rule.category_id = category_id

    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(
    db: Session,
    rule_id: UUID,
) -> Optional[models.CategorizationRule]:
    """
    Deletes a categorization rule by primary key.
    Future transactions will no longer match this rule.
    Previously categorized transactions remain completely untouched.
    Owns the standalone CRUD transaction boundary.
    """
    rule = get_rule_by_id(db, rule_id)
    if rule is None:
        return None

    db.delete(rule)
    db.commit()
    return rule
