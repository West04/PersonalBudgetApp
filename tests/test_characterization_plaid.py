from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
import requests_mock

from backend import models
from backend.crud.plaid import create_plaid_item
from backend.managers.plaid_transaction_sync_manager import sync_plaid_transactions


def test_plaid_sync_add_modify_remove_and_cursor(db_session):
    """
    Test Plaid synchronization characterization with mocked external Plaid API:
    - Added: inserts new transaction with inverted amount
    - Modified: updates existing transaction amount, name, date
    - Removed: deletes transaction by Plaid ID
    - Cursor: updates transactions_cursor on PlaidItem
    """
    # 1. Setup local PlaidItem and Account
    plaid_item_id = "item_sandbox_test_123"
    db_item = create_plaid_item(db_session, plaid_item_id=plaid_item_id, access_token="access-sandbox-token")

    plaid_acct_id = "plaid_account_test_abc"
    account = models.Account(
        item_id=db_item.id,
        plaid_account_id=plaid_acct_id,
        name="Plaid Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1500.00"),
        currency="USD"
    )
    db_session.add(account)
    db_session.flush()

    # Pre-populate 2 transactions in DB: one to be modified, one to be removed
    tx_to_modify = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_plaid_mod",
        description="Old Merchant Name",
        amount=Decimal("30.00"),
        date=date(2026, 6, 1),
        pending=True
    )
    tx_to_remove = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_plaid_del",
        description="Pending Charge Canceled",
        amount=Decimal("15.00"),
        date=date(2026, 6, 2),
        pending=True
    )
    db_session.add_all([tx_to_modify, tx_to_remove])
    db_session.commit()

    # 2. Mock Plaid API /transactions/sync response
    mock_payload = {
        "added": [
            {
                "transaction_id": "tx_plaid_new",
                "account_id": plaid_acct_id,
                "name": "New Coffee Shop",
                "amount": -5.50,  # Code inverts: -(-5.50) = 5.50
                "date": "2026-06-15",
                "datetime": None,
                "pending": False
            }
        ],
        "modified": [
            {
                "transaction_id": "tx_plaid_mod",
                "account_id": plaid_acct_id,
                "name": "Updated Merchant Name",
                "amount": -35.00,  # Code inverts: -(-35.00) = 35.00
                "date": "2026-06-03",
                "datetime": None,
                "pending": False
            }
        ],
        "removed": [
            {
                "transaction_id": "tx_plaid_del"
            }
        ],
        "has_more": False,
        "next_cursor": "cursor_token_page_2"
    }

    with requests_mock.Mocker() as m, \
         patch("backend.access.plaid_access.client.accounts_get") as mock_accts:
        mock_accts.return_value = MagicMock(accounts=[])
        m.post("https://sandbox.plaid.com/transactions/sync", json=mock_payload)

        # Call sync manager
        result = sync_plaid_transactions(
            db=db_session,
            plaid_item_id=plaid_item_id,
        )

    # 3. Assert Results Summary
    assert result.added == 1
    assert result.modified == 1
    assert result.removed == 1
    assert result.next_cursor == "cursor_token_page_2"

    # 4. Verify Database State
    # Check Added transaction
    new_tx = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_plaid_new").first()
    assert new_tx is not None
    assert new_tx.description == "New Coffee Shop"
    assert new_tx.amount == Decimal("5.50")
    assert new_tx.pending is False
    assert new_tx.date == date(2026, 6, 15)

    # Check Modified transaction
    db_session.refresh(tx_to_modify)
    assert tx_to_modify.description == "Updated Merchant Name"
    assert tx_to_modify.amount == Decimal("35.00")
    assert tx_to_modify.pending is False
    assert tx_to_modify.date == date(2026, 6, 3)

    # Check Removed transaction was deleted
    removed_tx = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_plaid_del").first()
    assert removed_tx is None

    # Check Cursor was persisted on PlaidItem
    db_session.refresh(db_item)
    assert db_item.transactions_cursor == "cursor_token_page_2"
