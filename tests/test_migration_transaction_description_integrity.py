"""
Tests for Transaction Description Integrity schema migration and cleanup (migrate_transaction_description_integrity).

Invariants:
1. Backfills legacy NULL descriptions to empty string '' without deleting or modifying other transaction fields.
2. Preserves valid transactions and their persisted fields.
3. Enforces PostgreSQL NOT NULL on transactions.description.
4. Returns True when modifying schema or backfilling rows.
5. Second execution is completely idempotent, safe, and returns False.
6. Guarantees safe cleanup/isolation so subsequent tests are never impacted.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.database import migrate_transaction_description_integrity
from backend import models


def test_migrate_transaction_description_integrity_dirty_pre_migration_backfill_and_not_null(db_session):
    """
    Simulates legacy dirty pre-migration database state where transactions.description
    is nullable and contains legacy rows with description IS NULL.
    Proves that migrate_transaction_description_integrity:
    - Backfills only the NULL descriptions to ''.
    - Preserves all other transaction fields.
    - Preserves valid transactions.
    - Applies NOT NULL constraint to transactions.description.
    - Returns True on first run.
    - Returns False on second run (idempotent).
    """
    bind = db_session.get_bind()

    # 1. Setup valid Account
    account_id = uuid4()
    valid_tx_id = uuid4()
    legacy_tx_id = uuid4()
    tx_date = date(2026, 6, 1)
    amount = Decimal("42.50")

    db_session.execute(
        text(
            "INSERT INTO accounts (id, name, type, subtype, current_balance, starting_balance, currency, is_active) "
            "VALUES (:id, :name, 'depository', 'checking', 1000.00, 0.00, 'USD', true);"
        ),
        {"id": account_id, "name": f"Migration Account {uuid4().hex[:6]}"},
    )

    # Insert valid transaction
    db_session.execute(
        text(
            "INSERT INTO transactions (transaction_id, account_id, description, amount, date, pending, is_transfer, is_reviewed, is_cleared, is_reconciled) "
            "VALUES (:id, :account_id, 'Coffee Shop Valid', :amount, :date, false, false, false, false, false);"
        ),
        {"id": valid_tx_id, "account_id": account_id, "amount": amount, "date": tx_date},
    )
    db_session.commit()

    try:
        # 2. Reproduce historical dirty schema: drop NOT NULL on transactions.description
        db_session.execute(text("ALTER TABLE transactions ALTER COLUMN description DROP NOT NULL;"))
        db_session.commit()

        # Insert legacy transaction with description = NULL
        db_session.execute(
            text(
                "INSERT INTO transactions (transaction_id, account_id, description, amount, date, pending, is_transfer, is_reviewed, is_cleared, is_reconciled) "
                "VALUES (:id, :account_id, NULL, :amount, :date, false, false, false, false, false);"
            ),
            {"id": legacy_tx_id, "account_id": account_id, "amount": amount, "date": tx_date},
        )
        db_session.commit()

        # 3. Precondition assertions
        null_count_before = db_session.execute(
            text("SELECT COUNT(*) FROM transactions WHERE description IS NULL;")
        ).scalar()
        assert null_count_before == 1

        is_nullable_before = db_session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'transactions' AND column_name = 'description';"
            )
        ).scalar()
        assert is_nullable_before == "YES"

        # Commit read transaction on db_session so connection is not holding a shared lock
        db_session.commit()

        # 4. Execute migration (first run)
        changed = migrate_transaction_description_integrity(bind)
        assert changed is True

        # 5. Post-migration assertions
        # A. Backfill verification: no rows with description IS NULL
        null_count_after = db_session.execute(
            text("SELECT COUNT(*) FROM transactions WHERE description IS NULL;")
        ).scalar()
        assert null_count_after == 0

        # Legacy transaction now has description == ''
        legacy_row_after = db_session.execute(
            text("SELECT transaction_id, account_id, description, amount, date FROM transactions WHERE transaction_id = :id;"),
            {"id": legacy_tx_id},
        ).fetchone()
        assert legacy_row_after is not None
        assert legacy_row_after[0] == legacy_tx_id
        assert legacy_row_after[1] == account_id
        assert legacy_row_after[2] == ""
        assert Decimal(str(legacy_row_after[3])) == amount
        assert legacy_row_after[4] == tx_date

        # Valid transaction is completely preserved
        valid_row_after = db_session.execute(
            text("SELECT transaction_id, account_id, description, amount, date FROM transactions WHERE transaction_id = :id;"),
            {"id": valid_tx_id},
        ).fetchone()
        assert valid_row_after is not None
        assert valid_row_after[0] == valid_tx_id
        assert valid_row_after[2] == "Coffee Shop Valid"
        assert Decimal(str(valid_row_after[3])) == amount

        # B. Schema enforcement: is_nullable == 'NO'
        is_nullable_after = db_session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'transactions' AND column_name = 'description';"
            )
        ).scalar()
        assert is_nullable_after == "NO"

        # Commit read transaction on db_session before second migration call
        db_session.commit()

        # 6. Idempotency (second run)
        changed_again = migrate_transaction_description_integrity(bind)
        assert changed_again is False

        # Post-second-run stability
        assert db_session.execute(text("SELECT COUNT(*) FROM transactions WHERE description IS NULL;")).scalar() == 0

    finally:
        # Guaranteed cleanup: restore NOT NULL if dirty state somehow lingered
        try:
            with bind.begin() as conn:
                conn.execute(text("UPDATE transactions SET description = '' WHERE description IS NULL;"))
                is_null = conn.execute(
                    text(
                        "SELECT is_nullable FROM information_schema.columns "
                        "WHERE table_name = 'transactions' AND column_name = 'description';"
                    )
                ).scalar()
                if is_null == "YES":
                    conn.execute(text("ALTER TABLE transactions ALTER COLUMN description SET NOT NULL;"))
        except Exception:
            pass


def test_database_constraint_prohibits_null_description(db_session):
    """
    Directly proves that PostgreSQL enforces the NOT NULL constraint on
    Transaction.description when attempting to persist description = None,
    raising an IntegrityError.
    """
    account = models.Account(
        name=f"Constraint Test Account {uuid4().hex[:6]}",
        type="depository",
        subtype="checking",
        current_balance=Decimal("100.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    tx = models.Transaction(
        account_id=account.id,
        amount=Decimal("10.00"),
        date=date(2026, 6, 1),
        description=None,
    )
    db_session.add(tx)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
