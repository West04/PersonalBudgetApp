"""
Workflow manager for Recurring Transactions.

Coordinates:
1. Loading eligible historical transactions via Transaction ResourceAccess.
2. Invoking the pure Recurrence Engine (detect_recurring_series).
3. Staging and upserting detected patterns via Recurring ResourceAccess.
4. Preserving user confirmations and dismissals across re-detections.
5. Managing database commit/rollback transaction boundaries.
6. Assembling API-ready schemas with member transaction IDs.
"""

from typing import Optional, Sequence
from uuid import UUID
from sqlalchemy.orm import Session

from .. import models, schemas
from ..access import account_access, recurring_access, transaction_access
from ..domain.categorization_rules import clean_merchant_key
from ..domain.recurring_transactions import (
    DetectedRecurringSeries,
    RecurrenceTransactionInput,
    detect_recurring_series,
)


def _build_inputs_from_transactions(
    txns: Sequence[models.Transaction],
) -> list[RecurrenceTransactionInput]:
    inputs = []
    for t in txns:
        inputs.append(
            RecurrenceTransactionInput(
                transaction_id=t.transaction_id,
                account_id=t.account_id,
                date=t.date,
                amount=t.amount,
                merchant=t.merchant,
                description=t.description,
            )
        )
    return inputs


def _build_item_read_schema(
    item: models.RecurringItem,
    tx_ids: Sequence[UUID] = (),
    explanation: Optional[str] = None,
) -> schemas.RecurringItemRead:
    account_name = item.account.name if item.account else "Unknown Account"
    if not explanation:
        amt_str = f"${item.expected_amount:,.2f}"
        if item.amount_type == "variable":
            amt_str = f"typical ${item.expected_amount:,.2f}"
        explanation = f"{item.status.capitalize()}: {item.occurrence_count} {item.cadence} transactions with {amt_str}"

    return schemas.RecurringItemRead(
        id=item.id,
        account_id=item.account_id,
        account_name=account_name,
        merchant=item.merchant,
        direction=item.direction,  # type: ignore
        cadence=item.cadence,      # type: ignore
        amount_type=item.amount_type,  # type: ignore
        expected_amount=item.expected_amount,
        status=item.status,        # type: ignore
        last_date=item.last_date,
        next_expected_date=item.next_expected_date,
        occurrence_count=item.occurrence_count,
        explanation=explanation,
        created_at=item.created_at,
        updated_at=item.updated_at,
        transaction_ids=list(tx_ids),
    )


def detect_and_sync_recurring_items(
    db: Session,
    account_id: Optional[UUID] = None,
) -> list[schemas.RecurringItemRead]:
    """
    Executes detection over eligible posted historical transactions, syncs findings
    into persistence, commits once, and returns all recurring items with their transaction IDs.
    """
    # 1. Fetch eligible posted, non-transfer, non-future transactions
    eligible_txns = transaction_access.get_eligible_transactions_for_recurrence(db, account_id=account_id)
    inputs = _build_inputs_from_transactions(eligible_txns)

    # 2. Run pure engine
    detected_list = detect_recurring_series(inputs)

    # Map of (account_id, clean_merchant_key, direction, cadence) -> detected series
    detected_map: dict[tuple[UUID, str, str, str], DetectedRecurringSeries] = {}
    active_identity_keys: set[tuple[UUID, str, str, str]] = set()
    for d in detected_list:
        clean_key = clean_merchant_key(d.merchant) or ""
        key = (d.account_id, clean_key, d.direction, d.cadence)
        detected_map[key] = d
        active_identity_keys.add(key)

    try:
        # 3. Upsert detected series into database
        for d in detected_list:
            recurring_access.stage_upsert_detected_series(db, d)

        # 4. Remove stale auto-detected series absent from current detection (preserves confirmed and dismissed)
        recurring_access.remove_stale_detected_items(
            db=db,
            active_identity_keys=active_identity_keys,
            account_id=account_id,
        )

        # 5. Commit workflow transaction boundary
        db.commit()
    except Exception:
        db.rollback()
        raise

    # 6. Fetch current persisted items
    persisted_items = recurring_access.list_recurring_items(db, account_id=account_id)

    results: list[schemas.RecurringItemRead] = []
    for item in persisted_items:
        clean_key = clean_merchant_key(item.merchant) or ""
        match_key = (item.account_id, clean_key, item.direction, item.cadence)
        matched_detected = detected_map.get(match_key)
        if matched_detected:
            tx_ids = matched_detected.transaction_ids
            explanation = matched_detected.explanation
        else:
            tx_ids = tuple(
                t.transaction_id for t in eligible_txns
                if (clean_merchant_key(t.merchant or t.description or "") == clean_key)
                and (("outflow" if t.amount > 0 else "inflow") == item.direction)
            )
            amt_str = f"${item.expected_amount:,.2f}"
            explanation = f"{item.status.capitalize()}: {item.occurrence_count} {item.cadence} transactions with {amt_str}"

        results.append(_build_item_read_schema(item, tx_ids=tx_ids, explanation=explanation))

    return results


def list_recurring_items(
    db: Session,
    account_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> list[schemas.RecurringItemRead]:
    """
    Lists persisted recurring items, ensuring member transaction IDs are resolved.
    If no items have been detected yet, runs detection first.
    """
    items = recurring_access.list_recurring_items(db, account_id=account_id, status=status)
    if not items:
        # If no items exist in DB, run a detection pass to discover them
        return detect_and_sync_recurring_items(db, account_id=account_id)

    # Resolve member transaction IDs from eligible transactions
    eligible_txns = transaction_access.get_eligible_transactions_for_recurrence(db, account_id=account_id)
    inputs = _build_inputs_from_transactions(eligible_txns)
    detected_list = detect_recurring_series(inputs)

    detected_map: dict[tuple[UUID, str, str, str], DetectedRecurringSeries] = {}
    for d in detected_list:
        clean_key = clean_merchant_key(d.merchant) or ""
        detected_map[(d.account_id, clean_key, d.direction, d.cadence)] = d

    results: list[schemas.RecurringItemRead] = []
    for item in items:
        clean_key = clean_merchant_key(item.merchant) or ""
        match_key = (item.account_id, clean_key, item.direction, item.cadence)
        matched_detected = detected_map.get(match_key)
        tx_ids = matched_detected.transaction_ids if matched_detected else ()
        explanation = matched_detected.explanation if matched_detected else None

        results.append(_build_item_read_schema(item, tx_ids=tx_ids, explanation=explanation))

    return results


def get_recurring_item_detail(
    db: Session,
    item_id: UUID,
) -> Optional[schemas.RecurringItemDetailRead]:
    """
    Retrieves full detail of a single recurring item, including its matching transactions.
    """
    item = recurring_access.get_recurring_item_by_id(db, item_id)
    if not item:
        return None

    # Find matching transactions
    clean_key = clean_merchant_key(item.merchant) or ""
    all_eligible = transaction_access.get_eligible_transactions_for_recurrence(db, account_id=item.account_id)
    matched_txns: list[models.Transaction] = []

    for tx in all_eligible:
        tx_merchant = tx.merchant.strip() if tx.merchant and tx.merchant.strip() else (tx.description.strip() if tx.description else "")
        if clean_merchant_key(tx_merchant) == clean_key:
            direction = "outflow" if tx.amount > 0 else "inflow"
            if direction == item.direction:
                matched_txns.append(tx)

    base_schema = _build_item_read_schema(item, tx_ids=[t.transaction_id for t in matched_txns])
    return schemas.RecurringItemDetailRead(
        **base_schema.model_dump(),
        transactions=[schemas.TransactionRead.model_validate(t) for t in matched_txns],
    )


def confirm_recurring_item(
    db: Session,
    item_id: UUID,
) -> Optional[schemas.RecurringItemRead]:
    """
    Sets RecurringItem status to 'confirmed', commits, and returns updated schema.
    Rolls back on error.
    """
    try:
        updated = recurring_access.set_recurring_item_status(db, item_id=item_id, status="confirmed")
        if not updated:
            return None
        db.commit()
        return _build_item_read_schema(updated)
    except Exception:
        db.rollback()
        raise


def dismiss_recurring_item(
    db: Session,
    item_id: UUID,
) -> Optional[schemas.RecurringItemRead]:
    """
    Sets RecurringItem status to 'dismissed', commits, and returns updated schema.
    Rolls back on error.
    """
    try:
        updated = recurring_access.set_recurring_item_status(db, item_id=item_id, status="dismissed")
        if not updated:
            return None
        db.commit()
        return _build_item_read_schema(updated)
    except Exception:
        db.rollback()
        raise
