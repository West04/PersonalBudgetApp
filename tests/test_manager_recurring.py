"""
Tests for Recurring Transaction Workflow Manager (backend/managers/recurring_transaction_manager.py).
"""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4
import pytest
from sqlalchemy.orm import Session

from backend import models
from backend.access import transaction_access
from backend.managers import recurring_transaction_manager


def _create_account(db: Session, name="Checking Account") -> models.Account:
    acc = models.Account(
        id=uuid4(),
        name=name,
        type="depository",
        subtype="checking",
        current_balance=Decimal("2000.00"),
        starting_balance=Decimal("2000.00"),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def _create_transaction(
    db: Session,
    account_id: UUID,
    amount: Decimal,
    transaction_date: date,
    description: str,
    merchant: Optional[str] = None,
    pending: bool = False,
) -> models.Transaction:
    from backend.domain.merchant_normalization import normalize_merchant

    resolved_merchant = merchant if merchant is not None else normalize_merchant(description)
    txn = transaction_access.stage_manual_transaction(
        db=db,
        account_id=account_id,
        amount=amount,
        transaction_date=transaction_date,
        description=description,
        merchant=resolved_merchant,
        pending=pending,
    )
    db.commit()
    db.refresh(txn)
    return txn


def test_detect_and_sync_orchestration(db_session: Session):
    acc = _create_account(db_session)

    # 1. Eligible posted transactions for Netflix
    t1 = _create_transaction(
        db=db_session,
        account_id=acc.id,
        amount=Decimal("15.49"),
        transaction_date=date(2026, 6, 15),
        description="NETFLIX.COM",
    )
    t2 = _create_transaction(
        db=db_session,
        account_id=acc.id,
        amount=Decimal("15.49"),
        transaction_date=date(2026, 7, 15),
        description="NETFLIX.COM",
    )
    t3 = _create_transaction(
        db=db_session,
        account_id=acc.id,
        amount=Decimal("15.49"),
        transaction_date=date(2026, 8, 15),
        description="NETFLIX.COM",
    )

    # 2. Ineligible: Pending transaction for Gym
    for dt in [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]:
        _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("20.00"),
            transaction_date=dt,
            description="Planet Fitness",
            pending=True,  # pending!
        )

    # 3. Ineligible: Transfer transaction
    for dt in [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]:
        tx = _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("100.00"),
            transaction_date=dt,
            description="Savings Transfer",
            pending=False,
        )
        tx.is_transfer = True
        db_session.add(tx)
        db_session.commit()

    # 4. Ineligible: Future-dated transactions
    for dt in [date(2027, 1, 1), date(2027, 2, 1), date(2027, 3, 1)]:
        _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("9.99"),
            transaction_date=dt,
            description="Future Sub",
            pending=False,
        )

    # Run detection
    results = recurring_transaction_manager.detect_and_sync_recurring_items(db_session)

    # Only Netflix should be detected
    assert len(results) == 1
    netflix_item = results[0]
    assert netflix_item.merchant == "Netflix"
    assert netflix_item.cadence == "monthly"
    assert netflix_item.status == "detected"
    assert netflix_item.occurrence_count == 3
    assert set(netflix_item.transaction_ids) == {t1.transaction_id, t2.transaction_id, t3.transaction_id}


def test_confirm_and_dismiss_persistence(db_session: Session):
    acc = _create_account(db_session)

    for dt in [date(2026, 6, 10), date(2026, 7, 10), date(2026, 8, 10)]:
        _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("70.00"),
            transaction_date=dt,
            description="Internet Bill",
        )

    results = recurring_transaction_manager.detect_and_sync_recurring_items(db_session)
    assert len(results) == 1
    item_id = results[0].id
    assert results[0].status == "detected"

    # User confirms the item
    confirmed = recurring_transaction_manager.confirm_recurring_item(db_session, item_id)
    assert confirmed.status == "confirmed"

    # Re-run detection -> status remains "confirmed", does not duplicate
    reloaded = recurring_transaction_manager.detect_and_sync_recurring_items(db_session)
    assert len(reloaded) == 1
    assert reloaded[0].id == item_id
    assert reloaded[0].status == "confirmed"

    # User dismisses the item
    dismissed = recurring_transaction_manager.dismiss_recurring_item(db_session, item_id)
    assert dismissed.status == "dismissed"

    # Re-run detection -> status remains "dismissed", does not re-suggest
    reloaded2 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session)
    assert len(reloaded2) == 1
    assert reloaded2[0].id == item_id
    assert reloaded2[0].status == "dismissed"


def test_get_recurring_item_detail(db_session: Session):
    acc = _create_account(db_session)
    tx_ids = []
    for dt in [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]:
        tx = _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("9.99"),
            transaction_date=dt,
            description="Music Stream",
        )
        tx_ids.append(tx.transaction_id)

    results = recurring_transaction_manager.detect_and_sync_recurring_items(db_session)
    assert len(results) == 1
    item_id = results[0].id

    detail = recurring_transaction_manager.get_recurring_item_detail(db_session, item_id)
    assert detail is not None
    assert detail.id == item_id
    assert len(detail.transactions) == 3
    assert {t.transaction_id for t in detail.transactions} == set(tx_ids)


def test_synchronization_idempotency(db_session: Session):
    """A. Idempotency: run detection twice -> no duplicate RecurringItem rows."""
    acc = _create_account(db_session, name="Idempotency Acc")
    for dt in [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]:
        _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("29.00"),
            transaction_date=dt,
            description="SaaS Subscription",
        )

    # Run 1
    res1 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res1) == 1
    total_db_items_run1 = db_session.query(models.RecurringItem).filter(models.RecurringItem.account_id == acc.id).count()
    assert total_db_items_run1 == 1

    # Run 2
    res2 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res2) == 1
    total_db_items_run2 = db_session.query(models.RecurringItem).filter(models.RecurringItem.account_id == acc.id).count()
    assert total_db_items_run2 == 1
    assert res1[0].id == res2[0].id


def test_synchronization_stale_detected_removed(db_session: Session):
    """
    B. Stale detected series: detect monthly series -> change underlying synthetic evidence
    so it no longer qualifies -> rerun -> old status='detected' item removed.
    """
    acc = _create_account(db_session, name="Stale Detected Acc")
    txs = []
    for dt in [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]:
        t = _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("19.99"),
            transaction_date=dt,
            description="Temporary Service",
        )
        txs.append(t)

    # Initial detection -> detected item exists
    res1 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res1) == 1
    assert res1[0].status == "detected"
    assert db_session.query(models.RecurringItem).filter(models.RecurringItem.account_id == acc.id).count() == 1

    # Remove 1 transaction so count is 2 (below minimum evidence threshold of 3)
    db_session.delete(txs[-1])
    db_session.commit()

    # Rerun detection
    res2 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res2) == 0
    # The stale status='detected' row must have been removed
    total_in_db = db_session.query(models.RecurringItem).filter(models.RecurringItem.account_id == acc.id).count()
    assert total_in_db == 0


def test_synchronization_cadence_change(db_session: Session):
    """
    C. Cadence change: monthly series persisted as detected -> evidence changes to a different
    supported cadence (e.g. weekly) -> rerun -> stale monthly detected row does not coexist with replacement.
    """
    acc = _create_account(db_session, name="Cadence Change Acc")
    txs = []
    # Start as monthly (June 1, July 1, August 1)
    for dt in [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]:
        t = _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("45.00"),
            transaction_date=dt,
            description="Cadence Shift Gym",
        )
        txs.append(t)

    # Run 1: monthly detected
    res1 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res1) == 1
    assert res1[0].cadence == "monthly"
    assert res1[0].status == "detected"

    # Shift dates to weekly cadence (June 1, June 8, June 15)
    txs[1].date = date(2026, 6, 8)
    txs[2].date = date(2026, 6, 15)
    db_session.commit()

    # Run 2: weekly detected, stale monthly detected must NOT coexist
    res2 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res2) == 1
    assert res2[0].cadence == "weekly"
    assert res2[0].status == "detected"

    # Verify directly in DB that only 1 row exists
    all_rows = db_session.query(models.RecurringItem).filter(models.RecurringItem.account_id == acc.id).all()
    assert len(all_rows) == 1
    assert all_rows[0].cadence == "weekly"


def test_synchronization_confirmed_preservation(db_session: Session):
    """
    D. Confirmed preservation: confirmed series -> rerun detection -> confirmation persists
    (even if underlying pattern changed or dropped below threshold).
    """
    acc = _create_account(db_session, name="Confirmed Preserve Acc")
    txs = []
    for dt in [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]:
        t = _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("120.00"),
            transaction_date=dt,
            description="Verified Insurance",
        )
        txs.append(t)

    res1 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res1) == 1
    item_id = res1[0].id

    # User confirms the item
    confirmed = recurring_transaction_manager.confirm_recurring_item(db_session, item_id)
    assert confirmed.status == "confirmed"

    # Rerun detection with evidence intact -> confirmation preserved
    res2 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res2) == 1
    assert res2[0].id == item_id
    assert res2[0].status == "confirmed"

    # Now delete one transaction so evidence is below 3
    db_session.delete(txs[-1])
    db_session.commit()

    # Rerun detection: confirmed decision MUST BE PRESERVED and not deleted
    res3 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res3) == 1
    assert res3[0].id == item_id
    assert res3[0].status == "confirmed"


def test_synchronization_dismissed_preservation(db_session: Session):
    """
    E. Dismissed preservation: dismissed series -> rerun detection -> dismissal persists
    and candidate does not reappear as a new detected row.
    """
    acc = _create_account(db_session, name="Dismissed Preserve Acc")
    for dt in [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]:
        _create_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("35.00"),
            transaction_date=dt,
            description="Dismissed OneOff",
        )

    res1 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res1) == 1
    item_id = res1[0].id

    # User dismisses the item
    dismissed = recurring_transaction_manager.dismiss_recurring_item(db_session, item_id)
    assert dismissed.status == "dismissed"

    # Rerun detection
    res2 = recurring_transaction_manager.detect_and_sync_recurring_items(db_session, account_id=acc.id)
    assert len(res2) == 1
    assert res2[0].id == item_id
    assert res2[0].status == "dismissed"

    # Verify no second detected row was created
    all_rows = db_session.query(models.RecurringItem).filter(models.RecurringItem.account_id == acc.id).all()
    assert len(all_rows) == 1
    assert all_rows[0].status == "dismissed"

