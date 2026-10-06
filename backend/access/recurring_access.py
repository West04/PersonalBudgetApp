"""
Resource access functions for RecurringItem PostgreSQL resources.
"""

from collections.abc import Sequence
from typing import Optional
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..domain.categorization_rules import clean_merchant_key
from ..domain.recurring_transactions import DetectedRecurringSeries


def list_recurring_items(
    db: Session,
    account_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> Sequence[models.RecurringItem]:
    """
    Retrieves all recurring items matching optional account_id and status filters,
    eagerly loading the associated account and ordering by merchant ASC, last_date DESC.
    """
    query = db.query(models.RecurringItem).options(joinedload(models.RecurringItem.account))
    if account_id is not None:
        query = query.filter(models.RecurringItem.account_id == account_id)
    if status is not None:
        query = query.filter(models.RecurringItem.status == status)
    return query.order_by(models.RecurringItem.merchant.asc(), models.RecurringItem.last_date.desc()).all()


def get_recurring_item_by_id(
    db: Session,
    item_id: UUID,
) -> Optional[models.RecurringItem]:
    """
    Retrieves a single RecurringItem by primary key UUID with account eagerly loaded.
    """
    return (
        db.query(models.RecurringItem)
        .options(joinedload(models.RecurringItem.account))
        .filter(models.RecurringItem.id == item_id)
        .first()
    )


def find_recurring_item_by_identity(
    db: Session,
    account_id: UUID,
    merchant: str,
    direction: str,
    cadence: str,
) -> Optional[models.RecurringItem]:
    """
    Finds a RecurringItem by its canonical uniqueness key:
    (account_id, LOWER(TRIM(merchant)), direction, cadence).
    Falls back to clean_merchant_key normalized matching if exact string differs in punctuation.
    """
    item = (
        db.query(models.RecurringItem)
        .filter(
            models.RecurringItem.account_id == account_id,
            func.lower(func.trim(models.RecurringItem.merchant)) == merchant.strip().lower(),
            models.RecurringItem.direction == direction,
            models.RecurringItem.cadence == cadence,
        )
        .first()
    )
    if item is not None:
        return item

    target_clean = clean_merchant_key(merchant) or ""
    candidates = (
        db.query(models.RecurringItem)
        .filter(
            models.RecurringItem.account_id == account_id,
            models.RecurringItem.direction == direction,
            models.RecurringItem.cadence == cadence,
        )
        .all()
    )
    for c in candidates:
        if (clean_merchant_key(c.merchant) or "") == target_clean:
            return c
    return None


def stage_upsert_detected_series(
    db: Session,
    detected: DetectedRecurringSeries,
) -> tuple[models.RecurringItem, bool]:
    """
    Stages an insert or update of a detected recurring series:
    - If already exists:
      updates facts (last_date, next_expected_date, occurrence_count, expected_amount, amount_type).
      Preserves user status ('confirmed' or 'dismissed' is never overwritten; 'detected' remains 'detected').
      Returns (item, False).
    - If new:
      stages a new models.RecurringItem with status='detected'.
      Returns (item, True).
    Flushes changes to the session without committing so calling Manager owns the transaction boundary.
    """
    existing = find_recurring_item_by_identity(
        db=db,
        account_id=detected.account_id,
        merchant=detected.merchant,
        direction=detected.direction,
        cadence=detected.cadence,
    )
    if existing is not None:
        existing.last_date = detected.last_date
        existing.next_expected_date = detected.next_expected_date
        existing.occurrence_count = detected.occurrence_count
        existing.expected_amount = detected.expected_amount
        existing.amount_type = detected.amount_type
        db.add(existing)
        db.flush()
        return (existing, False)

    new_item = models.RecurringItem(
        account_id=detected.account_id,
        merchant=detected.merchant,
        direction=detected.direction,
        cadence=detected.cadence,
        amount_type=detected.amount_type,
        expected_amount=detected.expected_amount,
        status="detected",
        last_date=detected.last_date,
        next_expected_date=detected.next_expected_date,
        occurrence_count=detected.occurrence_count,
    )
    db.add(new_item)
    db.flush()
    return (new_item, True)


def set_recurring_item_status(
    db: Session,
    item_id: UUID,
    status: str,
) -> Optional[models.RecurringItem]:
    """
    Updates the status ('detected', 'confirmed', 'dismissed') on a RecurringItem.
    Flushes to session without committing.
    """
    item = get_recurring_item_by_id(db, item_id)
    if item is None:
        return None
    item.status = status
    db.add(item)
    db.flush()
    return item


def delete_recurring_item(
    db: Session,
    item_id: UUID,
) -> bool:
    """
    Deletes a RecurringItem by ID. Flushes to session without committing.
    """
    item = get_recurring_item_by_id(db, item_id)
    if item is None:
        return False
    db.delete(item)
    db.flush()
    return True


def remove_stale_detected_items(
    db: Session,
    active_identity_keys: set[tuple[UUID, str, str, str]],
    account_id: Optional[UUID] = None,
) -> int:
    """
    Removes items with status='detected' whose identity keys are not in active_identity_keys.
    Preserves all items with status='confirmed' or status='dismissed'.
    Flushes changes to the session without committing so the calling Manager owns the transaction boundary.
    Returns the count of deleted stale items.
    """
    query = db.query(models.RecurringItem).filter(models.RecurringItem.status == "detected")
    if account_id is not None:
        query = query.filter(models.RecurringItem.account_id == account_id)
    candidates = query.all()
    deleted_count = 0
    for item in candidates:
        clean_key = clean_merchant_key(item.merchant) or ""
        key = (item.account_id, clean_key, item.direction, item.cadence)
        if key not in active_identity_keys:
            db.delete(item)
            deleted_count += 1
    if deleted_count > 0:
        db.flush()
    return deleted_count

