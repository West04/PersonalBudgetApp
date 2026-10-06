"""
Tests for Recurring ResourceAccess (backend/access/recurring_access.py).
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import models
from backend.access import recurring_access
from backend.domain.recurring_transactions import DetectedRecurringSeries


def _create_account(db: Session, name="Test Account") -> models.Account:
    acc = models.Account(
        id=uuid4(),
        name=name,
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("1000.00"),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def test_stage_upsert_new_and_update(db_session: Session):
    acc = _create_account(db_session)
    series = DetectedRecurringSeries(
        account_id=acc.id,
        merchant="Spotify",
        direction="outflow",
        cadence="monthly",
        amount_type="fixed",
        expected_amount=Decimal("10.99"),
        last_date=date(2026, 8, 1),
        next_expected_date=date(2026, 9, 1),
        occurrence_count=3,
        transaction_ids=(),
        explanation="Detected from 3 monthly transactions",
    )

    # 1. First upsert -> insert
    item, is_new = recurring_access.stage_upsert_detected_series(db_session, series)
    db_session.commit()

    assert is_new is True
    assert item.merchant == "Spotify"
    assert item.status == "detected"
    assert item.expected_amount == Decimal("10.99")
    assert item.occurrence_count == 3

    # Confirm user status manually
    item.status = "confirmed"
    db_session.add(item)
    db_session.commit()

    # 2. Second upsert with updated occurrence count and last date
    updated_series = DetectedRecurringSeries(
        account_id=acc.id,
        merchant="Spotify",
        direction="outflow",
        cadence="monthly",
        amount_type="fixed",
        expected_amount=Decimal("10.99"),
        last_date=date(2026, 9, 1),
        next_expected_date=date(2026, 10, 1),
        occurrence_count=4,
        transaction_ids=(),
        explanation="Detected from 4 monthly transactions",
    )

    item2, is_new2 = recurring_access.stage_upsert_detected_series(db_session, updated_series)
    db_session.commit()

    assert is_new2 is False
    assert item2.id == item.id
    assert item2.occurrence_count == 4
    assert item2.last_date == date(2026, 9, 1)
    # Status MUST remain confirmed!
    assert item2.status == "confirmed"


def test_list_and_filter_recurring_items(db_session: Session):
    acc1 = _create_account(db_session, "Acc 1")
    acc2 = _create_account(db_session, "Acc 2")

    s1 = DetectedRecurringSeries(
        account_id=acc1.id,
        merchant="Netflix",
        direction="outflow",
        cadence="monthly",
        amount_type="fixed",
        expected_amount=Decimal("15.49"),
        last_date=date(2026, 8, 15),
        next_expected_date=date(2026, 9, 15),
        occurrence_count=3,
        transaction_ids=(),
        explanation="Monthly",
    )
    s2 = DetectedRecurringSeries(
        account_id=acc2.id,
        merchant="Gym",
        direction="outflow",
        cadence="monthly",
        amount_type="fixed",
        expected_amount=Decimal("50.00"),
        last_date=date(2026, 8, 1),
        next_expected_date=date(2026, 9, 1),
        occurrence_count=3,
        transaction_ids=(),
        explanation="Monthly",
    )

    recurring_access.stage_upsert_detected_series(db_session, s1)
    recurring_access.stage_upsert_detected_series(db_session, s2)
    db_session.commit()

    # Filter by account_id
    items_acc1 = recurring_access.list_recurring_items(db_session, account_id=acc1.id)
    assert len(items_acc1) == 1
    assert items_acc1[0].merchant == "Netflix"

    # Filter by status
    items_detected = recurring_access.list_recurring_items(db_session, status="detected")
    assert len(items_detected) == 2


def test_set_status_and_delete(db_session: Session):
    acc = _create_account(db_session)
    s = DetectedRecurringSeries(
        account_id=acc.id,
        merchant="Water Bill",
        direction="outflow",
        cadence="monthly",
        amount_type="variable",
        expected_amount=Decimal("45.00"),
        last_date=date(2026, 8, 1),
        next_expected_date=date(2026, 9, 1),
        occurrence_count=3,
        transaction_ids=(),
        explanation="Monthly",
    )
    item, _ = recurring_access.stage_upsert_detected_series(db_session, s)
    db_session.commit()

    # Update status to dismissed
    updated = recurring_access.set_recurring_item_status(db_session, item.id, "dismissed")
    db_session.commit()
    assert updated.status == "dismissed"

    # Delete
    deleted = recurring_access.delete_recurring_item(db_session, item.id)
    db_session.commit()
    assert deleted is True

    # Confirm gone
    assert recurring_access.get_recurring_item_by_id(db_session, item.id) is None


def test_remove_stale_detected_items(db_session: Session):
    acc = _create_account(db_session)
    s1 = DetectedRecurringSeries(
        account_id=acc.id,
        merchant="Stale Service",
        direction="outflow",
        cadence="monthly",
        amount_type="fixed",
        expected_amount=Decimal("15.00"),
        last_date=date(2026, 8, 1),
        next_expected_date=date(2026, 9, 1),
        occurrence_count=3,
        transaction_ids=(),
        explanation="Monthly",
    )
    s2 = DetectedRecurringSeries(
        account_id=acc.id,
        merchant="Kept Service",
        direction="outflow",
        cadence="monthly",
        amount_type="fixed",
        expected_amount=Decimal("25.00"),
        last_date=date(2026, 8, 1),
        next_expected_date=date(2026, 9, 1),
        occurrence_count=3,
        transaction_ids=(),
        explanation="Monthly",
    )
    item1, _ = recurring_access.stage_upsert_detected_series(db_session, s1)
    item2, _ = recurring_access.stage_upsert_detected_series(db_session, s2)
    db_session.flush()

    # Active keys only include "kept service"
    active_keys = {(acc.id, "kept service", "outflow", "monthly")}
    removed_count = recurring_access.remove_stale_detected_items(db_session, active_keys, account_id=acc.id)
    db_session.commit()

    assert removed_count == 1
    assert recurring_access.get_recurring_item_by_id(db_session, item1.id) is None
    assert recurring_access.get_recurring_item_by_id(db_session, item2.id) is not None

