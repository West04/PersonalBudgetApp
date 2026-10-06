"""
Resource access functions for TransactionSplit PostgreSQL resources.
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy.orm import Session, joinedload

from .. import models


def get_splits_for_transaction(
    db: Session,
    transaction_id: UUID,
) -> Sequence[models.TransactionSplit]:
    """
    Retrieves all split allocations for a specific transaction,
    ordered by created_at ASC with category eagerly loaded.
    Does not commit or refresh.
    """
    return (
        db.query(models.TransactionSplit)
        .options(joinedload(models.TransactionSplit.category))
        .filter(models.TransactionSplit.transaction_id == transaction_id)
        .order_by(models.TransactionSplit.created_at.asc())
        .all()
    )


def get_splits_for_transactions(
    db: Session,
    transaction_ids: Sequence[UUID],
) -> dict[UUID, list[models.TransactionSplit]]:
    """
    Batch loads split allocations for multiple transactions to avoid N+1 queries.
    Returns mapping from transaction_id to list of TransactionSplit records.
    """
    if not transaction_ids:
        return {}

    rows = (
        db.query(models.TransactionSplit)
        .options(joinedload(models.TransactionSplit.category))
        .filter(models.TransactionSplit.transaction_id.in_(transaction_ids))
        .order_by(models.TransactionSplit.created_at.asc())
        .all()
    )

    result: dict[UUID, list[models.TransactionSplit]] = {tx_id: [] for tx_id in transaction_ids}
    for row in rows:
        result.setdefault(row.transaction_id, []).append(row)
    return result


def transaction_has_splits(
    db: Session,
    transaction_id: UUID,
) -> bool:
    """
    Checks whether a transaction has any existing split allocations.
    """
    return (
        db.query(models.TransactionSplit.id)
        .filter(models.TransactionSplit.transaction_id == transaction_id)
        .first()
    ) is not None


def count_splits_by_category(
    db: Session,
    category_id: UUID,
) -> int:
    """
    Counts how many split allocation rows reference a specific category.
    Used for safe category-deletion blocking.
    """
    return (
        db.query(models.TransactionSplit)
        .filter(models.TransactionSplit.category_id == category_id)
        .count()
    )


def stage_replace_splits(
    db: Session,
    transaction_id: UUID,
    allocations: Sequence[tuple[UUID, Decimal]],
) -> list[models.TransactionSplit]:
    """
    Atomically removes existing splits for transaction_id and stages new allocations.
    Calls db.flush() but does NOT commit, allowing the calling Manager to own
    the transaction boundary.
    Returns newly staged TransactionSplit rows.
    """
    existing = (
        db.query(models.TransactionSplit)
        .filter(models.TransactionSplit.transaction_id == transaction_id)
        .all()
    )
    for row in existing:
        db.delete(row)
    db.flush()

    new_splits: list[models.TransactionSplit] = []
    for category_id, amount in allocations:
        split_row = models.TransactionSplit(
            id=uuid4(),
            transaction_id=transaction_id,
            category_id=category_id,
            amount=amount,
        )
        db.add(split_row)
        new_splits.append(split_row)

    db.flush()
    return new_splits


def stage_delete_splits(
    db: Session,
    transaction_id: UUID,
) -> int:
    """
    Deletes all split allocations for a transaction.
    Calls db.flush() but does NOT commit, allowing the calling Manager to own
    the transaction boundary.
    Returns count of deleted split rows.
    """
    existing = (
        db.query(models.TransactionSplit)
        .filter(models.TransactionSplit.transaction_id == transaction_id)
        .all()
    )
    count = len(existing)
    for row in existing:
        db.delete(row)
    db.flush()
    return count
