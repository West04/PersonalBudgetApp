"""
Characterization tests for Phase 11 — Recurring Transactions baseline.
Pinning current state before adding recurring transaction models and endpoints.
"""

import pytest
from uuid import uuid4
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend import models, schemas
from backend.access import transaction_access, account_access
from backend.managers import manual_transaction_manager

client = TestClient(app)


def test_characterization_recurring_endpoint_registered():
    """Confirms /recurring routes exist and return 200."""
    response = client.get("/recurring/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_characterization_transaction_model_has_no_recurring_column():
    """Confirms models.Transaction schema does not have a recurring column."""
    columns = [c.name for c in models.Transaction.__table__.columns]
    assert "recurring_series_id" not in columns
    assert "recurring_id" not in columns
    assert "is_recurring" not in columns


def test_characterization_existing_transaction_invariants_preserved(db_session: Session):
    """
    Confirms existing transaction CRUD, merchant normalization, review,
    and reconciliation invariants operate without recurring interference.
    """
    account = models.Account(
        id=uuid4(),
        name="Checking Test Account",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("1000.00"),
    )
    db_session.add(account)
    db_session.commit()

    txn = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=account.id,
        category_id=None,
        description="NETFLIX.COM",
        amount=Decimal("15.49"),
        transaction_date=date(2026, 10, 1),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )

    assert txn.merchant == "Netflix"
    assert txn.is_merchant_overridden is False
    assert txn.is_reviewed is False
    assert txn.is_cleared is False
    assert txn.is_reconciled is False
    assert txn.is_transfer is False
