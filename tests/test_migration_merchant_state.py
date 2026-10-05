"""
Tests for Phase 8 merchant schema migration and idempotent backfill (migrate_merchant_state).

Invariants:
1. Adds 'merchant' and 'is_merchant_overridden' columns to transactions table if missing.
2. Backfills pre-existing transactions where merchant is NULL using normalize_merchant.
3. Second execution is completely idempotent and safe.
4. Never overwrites manual merchant corrections (is_merchant_overridden=True) or existing merchant values.
"""

from decimal import Decimal
from datetime import date
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text

from backend.database import migrate_merchant_state
from backend.domain.merchant_normalization import normalize_merchant


def test_migrate_merchant_state_idempotency_and_backfill(db_session):
    """
    Verifies that migrate_merchant_state:
    - Populates NULL merchant columns for existing transactions.
    - Preserves existing merchant values and overrides on a second run.
    """
    bind = db_session.get_bind()

    # Run migration first to ensure columns exist in DB
    migrate_merchant_state(bind)

    # Create dummy account
    acc_id = uuid4()
    db_session.execute(
        text(
            "INSERT INTO accounts (id, name, type, current_balance, starting_balance, currency, is_active) "
            "VALUES (:id, 'Test Acct', 'depository', 0, 0, 'USD', true);"
        ),
        {"id": acc_id},
    )

    # Insert transactions with various states
    tx1_id = uuid4()
    tx2_id = uuid4()
    tx3_id = uuid4()

    db_session.execute(
        text(
            "INSERT INTO transactions (transaction_id, account_id, description, amount, date, pending, is_transfer, merchant, is_merchant_overridden) "
            "VALUES "
            "(:id1, :acc, 'SQ *BLUE BOTTLE 12345 SAN FRANCISCO CA', 5.50, '2026-06-01', false, false, NULL, false), "
            "(:id2, :acc, 'TST* CHIPOTLE 1234', 12.00, '2026-06-02', false, false, 'My Custom Chipotle', true), "
            "(:id3, :acc, 'PAYPAL *NETFLIX', 15.99, '2026-06-03', false, false, 'Netflix Pre-existing', false);"
        ),
        {"id1": tx1_id, "id2": tx2_id, "id3": tx3_id, "acc": acc_id},
    )
    db_session.commit()

    # Run migration
    migrate_merchant_state(bind)

    # Check tx1: was NULL -> now backfilled to 'Blue Bottle'
    row1 = db_session.execute(
        text("SELECT merchant, is_merchant_overridden FROM transactions WHERE transaction_id = :id;"),
        {"id": tx1_id},
    ).fetchone()
    assert row1[0] == "Blue Bottle"
    assert row1[1] is False

    # Check tx2: had manual override 'My Custom Chipotle' -> preserved!
    row2 = db_session.execute(
        text("SELECT merchant, is_merchant_overridden FROM transactions WHERE transaction_id = :id;"),
        {"id": tx2_id},
    ).fetchone()
    assert row2[0] == "My Custom Chipotle"
    assert row2[1] is True

    # Check tx3: had pre-existing merchant -> preserved!
    row3 = db_session.execute(
        text("SELECT merchant, is_merchant_overridden FROM transactions WHERE transaction_id = :id;"),
        {"id": tx3_id},
    ).fetchone()
    assert row3[0] == "Netflix Pre-existing"
    assert row3[1] is False

    # Second run of migration: must be idempotent and preserve everything
    migrate_merchant_state(bind)

    row1_again = db_session.execute(
        text("SELECT merchant, is_merchant_overridden FROM transactions WHERE transaction_id = :id;"),
        {"id": tx1_id},
    ).fetchone()
    assert row1_again[0] == "Blue Bottle"
    assert row1_again[1] is False

    row2_again = db_session.execute(
        text("SELECT merchant, is_merchant_overridden FROM transactions WHERE transaction_id = :id;"),
        {"id": tx2_id},
    ).fetchone()
    assert row2_again[0] == "My Custom Chipotle"
    assert row2_again[1] is True
