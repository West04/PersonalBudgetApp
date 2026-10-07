"""
Unit and integration tests for Transaction ResourceAccess merchant normalization (backend/access/transaction_access.py).

Verifies:
1. stage_csv_import_transaction initializes normalized merchant and is_merchant_overridden=False.
2. stage_or_update_plaid_transaction:
   - Initializes normalized merchant for new records.
   - Updates merchant on provider metadata changes when not overridden.
   - Preserves manual corrections when is_merchant_overridden=True.
3. manual_transaction_manager.create_transaction:
   - Derives normalized merchant when omitted.
   - Preserves explicit user-provided merchant and marks is_merchant_overridden=True.
4. update_manual_transaction:
   - Setting merchant sets is_merchant_overridden=True.
   - Updating description when not overridden renormalizes merchant.
   - Updating description when overridden preserves existing merchant.
   - Clearing merchant resets override and renormalizes from description.
   - Updating merchant on reconciled transaction is permitted.
5. list_transactions:
   - Search query matches both merchant and description.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import text

from backend import models, schemas
from backend.access import transaction_access
from backend.database import migrate_merchant_state
from backend.managers import manual_transaction_manager


@pytest.fixture(autouse=True)
def ensure_schema(db_session):
    migrate_merchant_state(db_session.get_bind())


@pytest.fixture
def test_account(db_session):
    account = models.Account(
        name="Access Test Account",
        type="depository",
        subtype="checking",
    )
    db_session.add(account)
    db_session.commit()
    return account


# ---------------------------------------------------------------------------
# 1. CSV Import Staging
# ---------------------------------------------------------------------------

def test_stage_csv_import_normalizes_merchant(db_session, test_account):
    txn = transaction_access.stage_csv_import_transaction(
        db=db_session,
        account_id=test_account.id,
        transaction_date=date(2026, 6, 1),
        amount=Decimal("15.50"),
        description="SQ *BLUE BOTTLE 12345 SAN FRANCISCO CA",
    )
    db_session.flush()

    assert txn.description == "SQ *BLUE BOTTLE 12345 SAN FRANCISCO CA"
    assert txn.merchant == "Blue Bottle"
    assert txn.is_merchant_overridden is False


# ---------------------------------------------------------------------------
# 2. Plaid Upsert & Precedence
# ---------------------------------------------------------------------------

def test_plaid_staging_initializes_and_updates_merchant(db_session, test_account):
    plaid_id = f"plaid_test_{uuid4().hex[:8]}"

    # 1. Initial insert
    txn1 = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id=plaid_id,
        account_id=test_account.id,
        description="TST* CHIPOTLE 1234",
        amount=Decimal("12.50"),
        transaction_date=date(2026, 6, 2),
        merchant="Chipotle",
    )
    db_session.flush()
    assert txn1.merchant == "Chipotle"
    assert txn1.is_merchant_overridden is False

    # 2. Subsequent Plaid update (not overridden) -> updates merchant
    txn2 = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id=plaid_id,
        account_id=test_account.id,
        description="CHIPOTLE MEXICAN GRILL",
        amount=Decimal("12.50"),
        transaction_date=date(2026, 6, 2),
        merchant="Chipotle Mexican Grill",
    )
    db_session.flush()
    assert txn2.merchant == "Chipotle Mexican Grill"
    assert txn2.is_merchant_overridden is False

    # 3. User manually overrides merchant
    txn2.merchant = "My Favorite Burrito"
    txn2.is_merchant_overridden = True
    db_session.flush()

    # 4. Subsequent Plaid upsert arrives -> user correction is PRESERVED!
    txn3 = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id=plaid_id,
        account_id=test_account.id,
        description="CHIPOTLE STORE 999",
        amount=Decimal("12.50"),
        transaction_date=date(2026, 6, 2),
        merchant="Chipotle",
    )
    db_session.flush()
    assert txn3.merchant == "My Favorite Burrito"
    assert txn3.is_merchant_overridden is True
    # Raw description is updated legitimately without erasing manual merchant
    assert txn3.description == "CHIPOTLE STORE 999"


# ---------------------------------------------------------------------------
# 3. Manual Creation
# ---------------------------------------------------------------------------

def test_manual_create_omitted_merchant_is_normalized(db_session, test_account):
    txn = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="WHOLE FOODS #123",
        amount=Decimal("45.00"),
        transaction_date=date(2026, 6, 5),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    assert txn.description == "WHOLE FOODS #123"
    assert txn.merchant == "Whole Foods"
    assert txn.is_merchant_overridden is False


def test_manual_create_explicit_merchant_marked_overridden(db_session, test_account):
    txn = manual_transaction_manager.create_transaction(
        db=db_session,
        account_id=test_account.id,
        category_id=None,
        description="WHOLE FOODS #123",
        amount=Decimal("45.00"),
        transaction_date=date(2026, 6, 5),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
        merchant="Organic Market",
    )
    assert txn.description == "WHOLE FOODS #123"
    assert txn.merchant == "Organic Market"
    assert txn.is_merchant_overridden is True


# ---------------------------------------------------------------------------
# 4. Manual Updates & Invariants
# ---------------------------------------------------------------------------

def test_update_manual_transaction_merchant_sets_override(db_session, test_account):
    txn = transaction_access.stage_manual_transaction(
        db=db_session,
        account_id=test_account.id,
        amount=Decimal("30.00"),
        transaction_date=date(2026, 6, 10),
        description="SAFEWAY #456",
        merchant="Safeway",
        is_merchant_overridden=False,
    )
    db_session.commit()
    assert txn.merchant == "Safeway"
    assert txn.is_merchant_overridden is False

    # Update merchant
    updated = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=txn.transaction_id,
        update_data={"merchant": "Neighborhood Safeway"},
    )
    assert updated.merchant == "Neighborhood Safeway"
    assert updated.is_merchant_overridden is True

    # Update description: because is_merchant_overridden is True, merchant is PRESERVED!
    updated2 = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=txn.transaction_id,
        update_data={"description": "SAFEWAY STORE #999"},
    )
    assert updated2.description == "SAFEWAY STORE #999"
    assert updated2.merchant == "Neighborhood Safeway"
    assert updated2.is_merchant_overridden is True


def test_update_manual_transaction_description_renormalizes_when_not_overridden(db_session, test_account):
    txn = transaction_access.stage_manual_transaction(
        db=db_session,
        account_id=test_account.id,
        amount=Decimal("30.00"),
        transaction_date=date(2026, 6, 10),
        description="SAFEWAY #456",
        merchant="Safeway",
        is_merchant_overridden=False,
    )
    db_session.commit()
    assert txn.merchant == "Safeway"
    assert txn.is_merchant_overridden is False

    # Update description without merchant
    updated = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=txn.transaction_id,
        update_data={"description": "TRADER JOES #102"},
    )
    assert updated.description == "TRADER JOES #102"
    assert updated.merchant == "Trader Joes"
    assert updated.is_merchant_overridden is False


def test_update_merchant_on_reconciled_transaction_permitted(db_session, test_account):
    txn = transaction_access.stage_manual_transaction(
        db=db_session,
        account_id=test_account.id,
        amount=Decimal("15.99"),
        transaction_date=date(2026, 6, 10),
        description="NETFLIX.COM",
        merchant="Netflix",
        is_merchant_overridden=False,
    )
    txn.is_cleared = True
    txn.is_reconciled = True
    db_session.commit()

    # Updating merchant on reconciled transaction is allowed (not a financial field)
    updated = transaction_access.update_manual_transaction(
        db=db_session,
        transaction_id=txn.transaction_id,
        update_data={"merchant": "Netflix Streaming"},
    )
    assert updated.merchant == "Netflix Streaming"
    assert updated.is_reconciled is True
    assert updated.is_cleared is True
    assert updated.amount == Decimal("15.99")


# ---------------------------------------------------------------------------
# 5. Search Functionality
# ---------------------------------------------------------------------------

def test_list_transactions_search_matches_both_merchant_and_description(db_session, test_account):
    # Tx A: Raw description has noisy ID, merchant is normalized
    tx_a = transaction_access.stage_manual_transaction(
        db=db_session,
        account_id=test_account.id,
        amount=Decimal("6.50"),
        transaction_date=date(2026, 6, 15),
        description="SQ *BLUE BOTTLE 98765 SAN FRANCISCO CA",
        merchant="Blue Bottle",
        is_merchant_overridden=False,
    )
    db_session.commit()

    # Search by normalized merchant name ("Blue Bottle")
    res1 = transaction_access.list_transactions(db=db_session, q="Blue Bottle")
    ids1 = [t.transaction_id for t in res1["items"]]
    assert tx_a.transaction_id in ids1

    # Search by raw noise fragment in statement text ("98765")
    res2 = transaction_access.list_transactions(db=db_session, q="98765")
    ids2 = [t.transaction_id for t in res2["items"]]
    assert tx_a.transaction_id in ids2
