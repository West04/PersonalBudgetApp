"""
Workflow Manager for Split Transactions.

Coordinates:
1. Retrieval of parent transaction via Transaction ResourceAccess.
2. Validation of transaction eligibility (not pending, not transfer).
3. Invocation of pure Split Domain Policy (validate_split_allocations).
4. Validation of category existence via Category ResourceAccess.
5. Atomic replacement or deletion of split allocations via Split ResourceAccess.
6. Mutation of parent category state (category_id=NULL, category_source=NULL on split;
   explicit category and category_source='manual' on unsplit).
7. Advancement of ML training revision when an eligible single-category label is removed or restored.
8. Transaction boundary ownership (commit once on success, rollback on failure).
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from .. import models, schemas
from ..access import category_access, ml_model_access, split_access, transaction_access
from ..domain.transaction_splits import (
    SplitAllocationInput,
    validate_split_allocations,
)


class TransactionNotFoundError(Exception):
    """Raised when a parent transaction does not exist in persistence."""
    pass


class SplitValidationError(ValueError):
    """Raised when split allocations violate domain rules or invariant constraints."""
    pass


class SplitTransactionPendingError(ValueError):
    """Raised when attempting to split a provisional/pending transaction."""
    pass


class SplitTransactionTransferError(ValueError):
    """Raised when attempting to split a confirmed transfer transaction."""
    pass


def get_transaction_splits(
    db: Session,
    transaction_id: UUID,
) -> Sequence[models.TransactionSplit]:
    """
    Retrieves all split allocations for a transaction.
    Raises TransactionNotFoundError if transaction does not exist.
    """
    tx = transaction_access.get_transaction_by_id(db, transaction_id)
    if tx is None:
        raise TransactionNotFoundError(f"Transaction {transaction_id} not found.")

    return split_access.get_splits_for_transaction(db, transaction_id)


def create_or_replace_split(
    db: Session,
    transaction_id: UUID,
    allocations: Sequence[schemas.TransactionSplitLine],
) -> models.Transaction:
    """
    Coordinates atomic split allocation creation or replacement:
    1. Loads and verifies parent transaction eligibility.
    2. Runs pure domain allocation validator.
    3. Verifies each allocation's category exists.
    4. Stages parent category clearing and ML revision increment if human label existed.
    5. Stages split replacement.
    6. Commits transaction boundary atomically.
    """
    tx = transaction_access.get_transaction_by_id(db, transaction_id)
    if tx is None:
        raise TransactionNotFoundError(f"Transaction {transaction_id} not found.")

    if tx.pending:
        raise SplitTransactionPendingError("Pending transactions cannot be split.")

    if tx.is_transfer:
        raise SplitTransactionTransferError("Transfer transactions cannot be split.")

    # 1. Pure domain validation
    domain_inputs = [
        SplitAllocationInput(
            category_id=a.category_id,
            amount=Decimal(str(a.amount)),
        )
        for a in allocations
    ]
    validation = validate_split_allocations(
        parent_amount=tx.amount,
        allocations=domain_inputs,
    )
    if not validation.is_valid:
        raise SplitValidationError(validation.error or "Invalid split allocations.")

    # 2. Category persistence existence check
    for a in allocations:
        cat = category_access.get_category_by_id(db, a.category_id)
        if cat is None:
            raise SplitValidationError(f"Category {a.category_id} not found.")

    # 3. Transaction boundary
    try:
        had_ml_label = (
            tx.category_id is not None
            and tx.category_source in ("manual", "ml", "legacy")
        )

        tx.category_id = None
        tx.category_source = None
        db.add(tx)

        if had_ml_label:
            ml_model_access.increment_training_revision(db)

        split_access.stage_replace_splits(
            db=db,
            transaction_id=transaction_id,
            allocations=[(a.category_id, Decimal(str(a.amount))) for a in allocations],
        )

        db.expire(tx, ["splits"])
        db.commit()
        db.refresh(tx)
        return tx
    except Exception:
        db.rollback()
        raise


def unsplit_transaction(
    db: Session,
    transaction_id: UUID,
    target_category_id: Optional[UUID] = None,
) -> models.Transaction:
    """
    Coordinates returning a split transaction to a single authoritative category or uncategorized:
    1. Loads transaction and validates target category exists if provided.
    2. Verifies transaction currently has splits.
    3. Deletes split allocations.
    4. Sets parent.category_id = target_category_id and category_source = 'manual' (if category provided).
       If target_category_id is None, leaves parent uncategorized with category_source = None.
    5. Increments ML training revision if assigned to an explicit human category.
    6. Commits transaction boundary atomically.
    """
    tx = transaction_access.get_transaction_by_id(db, transaction_id)
    if tx is None:
        raise TransactionNotFoundError(f"Transaction {transaction_id} not found.")

    if target_category_id is not None:
        target_category = category_access.get_category_by_id(db, target_category_id)
        if target_category is None:
            raise SplitValidationError(f"Category {target_category_id} not found.")

    if not split_access.transaction_has_splits(db, transaction_id):
        raise SplitValidationError("Transaction is not split.")

    try:
        split_access.stage_delete_splits(db, transaction_id)

        if target_category_id is not None:
            tx.category_id = target_category_id
            tx.category_source = "manual"
            ml_model_access.increment_training_revision(db)
        else:
            tx.category_id = None
            tx.category_source = None

        db.expire(tx, ["splits"])
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx
    except Exception:
        db.rollback()
        raise
