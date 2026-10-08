"""
Tests for Budget Category Integrity schema migration and cleanup (migrate_budget_category_integrity).

Invariants:
1. Deletes only orphaned NULL-category budget rows (produced by historical defect).
2. Preserves valid budget rows and their persisted fields.
3. Restores and enforces PostgreSQL NOT NULL on budgets.category_id.
4. Returns True when modifying schema or deleting orphan rows.
5. Second execution is completely idempotent, safe, and returns False.
6. Guarantees safe cleanup/isolation so subsequent tests are never impacted.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import text

from backend.database import migrate_budget_category_integrity


def test_migrate_budget_category_integrity_dirty_pre_migration_cleanup_and_not_null(db_session):
    """
    Simulates legacy dirty pre-migration database state where budgets.category_id
    is nullable and contains orphaned rows with category_id IS NULL.
    Proves that migrate_budget_category_integrity:
    - Purges only the NULL-category rows.
    - Preserves valid budget rows.
    - Applies NOT NULL constraint to budgets.category_id.
    - Returns True on first run.
    - Returns False on second run (idempotent).
    """
    bind = db_session.get_bind()

    # 1. Setup valid Category and valid Budget
    group_id = uuid4()
    cat_id = uuid4()
    valid_budget_id = uuid4()
    orphan_budget_id = uuid4()
    budget_date = date(2026, 6, 1)
    planned_amount = Decimal("250.00")

    # Insert valid group & category
    db_session.execute(
        text("INSERT INTO category_groups (category_group_id, name, sort_order) VALUES (:id, :name, 0);"),
        {"id": group_id, "name": f"Migration Test Group {uuid4().hex[:6]}"},
    )
    db_session.execute(
        text(
            "INSERT INTO categories (category_id, group_id, name, sort_order, type, is_active) "
            "VALUES (:id, :group_id, 'Valid Migration Cat', 0, 'expense', true);"
        ),
        {"id": cat_id, "group_id": group_id},
    )
    db_session.execute(
        text(
            "INSERT INTO budgets (budget_id, budget_month, planned_amount, category_id) "
            "VALUES (:id, :month, :amount, :cat_id);"
        ),
        {"id": valid_budget_id, "month": budget_date, "amount": planned_amount, "cat_id": cat_id},
    )
    db_session.commit()

    try:
        # 2. Reproduce historical dirty schema: drop NOT NULL on budgets.category_id
        db_session.execute(text("ALTER TABLE budgets ALTER COLUMN category_id DROP NOT NULL;"))
        db_session.commit()

        # Insert legacy orphan budget with category_id = NULL
        db_session.execute(
            text(
                "INSERT INTO budgets (budget_id, budget_month, planned_amount, category_id) "
                "VALUES (:id, :month, 50.00, NULL);"
            ),
            {"id": orphan_budget_id, "month": budget_date},
        )
        db_session.commit()

        # 3. Precondition assertions
        # A. Prove one or more budgets have category_id IS NULL
        null_count_before = db_session.execute(
            text("SELECT COUNT(*) FROM budgets WHERE category_id IS NULL;")
        ).scalar()
        assert null_count_before == 1

        # B. Prove valid budget exists
        valid_b_before = db_session.execute(
            text("SELECT budget_id, category_id, planned_amount FROM budgets WHERE budget_id = :id;"),
            {"id": valid_budget_id},
        ).fetchone()
        assert valid_b_before is not None
        assert valid_b_before[0] == valid_budget_id
        assert valid_b_before[1] == cat_id

        # C. Prove information_schema reports is_nullable == 'YES'
        is_nullable_before = db_session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'budgets' AND column_name = 'category_id';"
            )
        ).scalar()
        assert is_nullable_before == "YES"

        # Commit read transaction on db_session so connection is not holding a shared lock on budgets
        db_session.commit()

        # 4. Execute migration (first run)
        changed = migrate_budget_category_integrity(bind)
        assert changed is True

        # 5. Post-migration assertions
        # A. Orphan cleanup: no rows with category_id IS NULL
        null_count_after = db_session.execute(
            text("SELECT COUNT(*) FROM budgets WHERE category_id IS NULL;")
        ).scalar()
        assert null_count_after == 0

        # Prove specifically the orphan_budget_id row was deleted
        orphan_row_after = db_session.execute(
            text("SELECT 1 FROM budgets WHERE budget_id = :id;"),
            {"id": orphan_budget_id},
        ).fetchone()
        assert orphan_row_after is None

        # B. Valid data preservation: valid row still exists with all fields intact
        valid_b_after = db_session.execute(
            text("SELECT budget_id, category_id, budget_month, planned_amount FROM budgets WHERE budget_id = :id;"),
            {"id": valid_budget_id},
        ).fetchone()
        assert valid_b_after is not None
        assert valid_b_after[0] == valid_budget_id
        assert valid_b_after[1] == cat_id
        assert valid_b_after[2] == budget_date
        assert Decimal(str(valid_b_after[3])) == planned_amount

        # C. Schema enforcement: is_nullable == 'NO'
        is_nullable_after = db_session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'budgets' AND column_name = 'category_id';"
            )
        ).scalar()
        assert is_nullable_after == "NO"

        # Commit read transaction on db_session before second migration call
        db_session.commit()

        # 6. Idempotency (second run)
        changed_again = migrate_budget_category_integrity(bind)
        assert changed_again is False

        # Verify post-second-run stability
        assert db_session.execute(text("SELECT COUNT(*) FROM budgets WHERE category_id IS NULL;")).scalar() == 0
        valid_b_again = db_session.execute(
            text("SELECT budget_id FROM budgets WHERE budget_id = :id;"),
            {"id": valid_budget_id},
        ).fetchone()
        assert valid_b_again is not None
        assert db_session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'budgets' AND column_name = 'category_id';"
            )
        ).scalar() == "NO"

    finally:
        # 7. Guaranteed isolation & cleanup: ensure NOT NULL is restored if test failed midway
        try:
            db_session.rollback()
            db_session.execute(text("DELETE FROM budgets WHERE category_id IS NULL;"))
            db_session.execute(text("ALTER TABLE budgets ALTER COLUMN category_id SET NOT NULL;"))
            db_session.commit()
        except Exception:
            db_session.rollback()
