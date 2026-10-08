"""
Comprehensive contract and regression tests for Transaction.description data-integrity repair:
1. TransactionUpdate: explicit null rejected with 422 (DB unmutated), empty string accepted, omitted preserved.
2. TransactionCreate: explicit null and missing rejected with 422, empty string accepted.
3. CSV Ingestion: blank description normalized to '', duplicate matching operates on exact '' == ''.
4. Plaid Ingestion: provider name=None and name='' normalized to '' at staging boundary.
5. API Read Endpoints: transactions with description='' serialize cleanly across all response shapes.
"""

from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend import models, schemas
from backend.main import app
from backend.managers.plaid_transaction_sync_manager import _process_upsert_event


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Manual Update Contract
# ---------------------------------------------------------------------------

def test_manual_update_explicit_null_rejected_with_422_and_db_unmutated(client, db_session):
    """
    PUT /transactions/{id} with {"description": null}:
    - Must be rejected with HTTP 422 Unprocessable Entity.
    - Router / Manager must not mutate the record.
    - Persisted description must remain unchanged.
    """
    account = models.Account(
        name=f"Update Test Acc {uuid4().hex[:6]}",
        type="depository",
        subtype="checking",
        current_balance=Decimal("500.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        amount=Decimal("30.00"),
        date=date(2026, 6, 1),
        description="Original Description",
        merchant="Original Description",
    )
    db_session.add(tx)
    db_session.commit()
    tx_id = str(tx.transaction_id)

    # Attempt update with explicit null description
    resp = client.put(f"/transactions/{tx_id}", json={"description": None})
    assert resp.status_code == 422
    err_detail = resp.json()["detail"]
    assert any("description" in str(err["loc"]) for err in err_detail)

    # Verify database was NOT mutated
    db_session.expire_all()
    refreshed_tx = db_session.query(models.Transaction).filter_by(transaction_id=tx.transaction_id).one()
    assert refreshed_tx.description == "Original Description"
    assert refreshed_tx.merchant == "Original Description"


def test_manual_update_empty_string_clears_description(client, db_session):
    """
    PUT /transactions/{id} with {"description": ""}:
    - Must succeed with HTTP 200.
    - Stored description must be ''.
    - Response description must be ''.
    """
    account = models.Account(
        name=f"Update Empty Acc {uuid4().hex[:6]}",
        type="depository",
        subtype="checking",
        current_balance=Decimal("500.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        amount=Decimal("30.00"),
        date=date(2026, 6, 1),
        description="To Be Cleared",
        merchant="To Be Cleared",
    )
    db_session.add(tx)
    db_session.commit()
    tx_id = str(tx.transaction_id)

    resp = client.put(f"/transactions/{tx_id}", json={"description": ""})
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["description"] == ""

    # Verify persisted DB state
    db_session.expire_all()
    refreshed_tx = db_session.query(models.Transaction).filter_by(transaction_id=tx.transaction_id).one()
    assert refreshed_tx.description == ""


def test_manual_update_omitted_description_preserves_existing(client, db_session):
    """
    PUT /transactions/{id} with {"amount": "75.00"} (description omitted):
    - Must succeed with HTTP 200.
    - Amount is updated.
    - Description remains unchanged.
    """
    account = models.Account(
        name=f"Update Omit Acc {uuid4().hex[:6]}",
        type="depository",
        subtype="checking",
        current_balance=Decimal("500.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        amount=Decimal("30.00"),
        date=date(2026, 6, 1),
        description="Preserve Me",
        merchant="Preserve Me",
    )
    db_session.add(tx)
    db_session.commit()
    tx_id = str(tx.transaction_id)

    resp = client.put(f"/transactions/{tx_id}", json={"amount": "75.00"})
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["description"] == "Preserve Me"
    assert Decimal(str(res_data["amount"])) == Decimal("75.00")

    # Verify persisted DB state
    db_session.expire_all()
    refreshed_tx = db_session.query(models.Transaction).filter_by(transaction_id=tx.transaction_id).one()
    assert refreshed_tx.description == "Preserve Me"
    assert refreshed_tx.amount == Decimal("75.00")


def test_manual_update_whitespace_string_preserved_verbatim(client, db_session):
    """
    PUT /transactions/{id} with {"description": "   "}:
    - Must succeed with HTTP 200.
    - Preserves whitespace verbatim (no trimming in manual update).
    """
    account = models.Account(
        name=f"Update WS Acc {uuid4().hex[:6]}",
        type="depository",
        subtype="checking",
        current_balance=Decimal("500.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        amount=Decimal("30.00"),
        date=date(2026, 6, 1),
        description="Original",
    )
    db_session.add(tx)
    db_session.commit()
    tx_id = str(tx.transaction_id)

    resp = client.put(f"/transactions/{tx_id}", json={"description": "   "})
    assert resp.status_code == 200
    assert resp.json()["description"] == "   "

    db_session.expire_all()
    refreshed = db_session.query(models.Transaction).filter_by(transaction_id=tx.transaction_id).one()
    assert refreshed.description == "   "


# ---------------------------------------------------------------------------
# 2. Manual Create Contract
# ---------------------------------------------------------------------------

def test_manual_create_contract(client, db_session):
    """
    POST /transactions/:
    - description missing -> HTTP 422
    - description null -> HTTP 422
    - description '' -> HTTP 201, stored as ''
    - description 'text' -> HTTP 201, stored as 'text'
    """
    account = models.Account(
        name=f"Create Contract Acc {uuid4().hex[:6]}",
        type="depository",
        subtype="checking",
        current_balance=Decimal("500.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    base_payload = {
        "account_id": str(account.id),
        "amount": "25.00",
        "date": "2026-06-15",
    }

    # A. Missing description
    resp_missing = client.post("/transactions/", json=base_payload)
    assert resp_missing.status_code == 422

    # B. Explicit null description
    resp_null = client.post("/transactions/", json={**base_payload, "description": None})
    assert resp_null.status_code == 422

    # C. Empty string description
    resp_empty = client.post("/transactions/", json={**base_payload, "description": ""})
    assert resp_empty.status_code == 201
    assert resp_empty.json()["description"] == ""

    # D. Normal string description
    resp_str = client.post("/transactions/", json={**base_payload, "description": "Target Store"})
    assert resp_str.status_code == 201
    assert resp_str.json()["description"] == "Target Store"


# ---------------------------------------------------------------------------
# 3. CSV Ingestion & Deduplication
# ---------------------------------------------------------------------------

def test_csv_ingestion_blank_description_imports_as_empty_string_and_deduplicates(client, db_session):
    """
    CSV upload:
    - Row with empty Description cell imports as description=''.
    - Re-importing the same statement deduplicates using exact (account_id, date, amount, '') match.
    """
    account = models.Account(
        name=f"CSV Blank Acc {uuid4().hex[:6]}",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    # USAA format: Date,Description,Category,Amount,Status
    # Row 1 has blank description; Row 2 has whitespace-only description
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,,Food,-45.00,posted\n"
        "2026-06-02,   ,Utilities,-75.00,posted\n"
    )

    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data_form = {"account_id": str(account.id), "format": "usaa"}

    # 1. First upload -> 2 imported
    resp1 = client.post("/upload/confirm", data=data_form, files=files)
    assert resp1.status_code == 200
    res1 = resp1.json()
    assert res1["imported"] == 2
    assert res1["skipped"] == 0

    # Verify both transactions have description == '' in DB
    txs = db_session.query(models.Transaction).filter_by(account_id=account.id).order_by(models.Transaction.date).all()
    assert len(txs) == 2
    assert txs[0].description == ""
    assert txs[1].description == ""

    # 2. Second upload of exact same CSV -> 0 imported, 2 skipped (deduplicated on '' == '')
    files2 = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp2 = client.post("/upload/confirm", data=data_form, files=files2)
    assert resp2.status_code == 200
    res2 = resp2.json()
    assert res2["imported"] == 0
    assert res2["skipped"] == 2


# ---------------------------------------------------------------------------
# 4. Plaid Ingestion Staging Boundary
# ---------------------------------------------------------------------------

def test_plaid_ingestion_normalizes_none_name_to_empty_string(db_session):
    """
    _process_upsert_event in Plaid sync manager:
    When provider payload supplies name=None or name='', normalizes to ''
    and successfully persists to PostgreSQL without violating NOT NULL constraint.
    """
    account = models.Account(
        id=uuid4(),
        plaid_account_id="plaid_remote_acc_1",
        name="Plaid Sync Acc",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    # Event 1: name is None
    event_none = {
        "account_id": "plaid_remote_acc_1",
        "transaction_id": "plaid_tx_none_1",
        "date": "2026-06-10",
        "datetime": None,
        "amount": "50.00",
        "pending": False,
        "name": None,
        "merchant_name": None,
        "counterparties": [],
    }
    conflict = _process_upsert_event(db_session, event_none)
    assert conflict is None

    # Verify persisted in database
    tx1 = db_session.query(models.Transaction).filter_by(plaid_transaction_id="plaid_tx_none_1").one()
    assert tx1.description == ""
    assert tx1.merchant is None

    # Event 2: name is empty string ''
    event_empty = {
        "account_id": "plaid_remote_acc_1",
        "transaction_id": "plaid_tx_empty_2",
        "date": "2026-06-11",
        "datetime": None,
        "amount": "25.00",
        "pending": False,
        "name": "",
        "merchant_name": None,
        "counterparties": [],
    }
    conflict2 = _process_upsert_event(db_session, event_empty)
    assert conflict2 is None

    tx2 = db_session.query(models.Transaction).filter_by(plaid_transaction_id="plaid_tx_empty_2").one()
    assert tx2.description == ""


# ---------------------------------------------------------------------------
# 5. API Read Endpoints Serialization with description=""
# ---------------------------------------------------------------------------

def test_api_read_endpoints_serialize_empty_description_cleanly(client, db_session):
    """
    Verify all read response contracts correctly serialize transactions with description='':
    - GET /transactions/
    - GET /transactions/{id}
    - GET /dashboard/summary
    - GET /credit-cards/summary
    - GET /accounts/{id}/reconciliation
    """
    acct_chk = models.Account(
        name=f"Read Chk Acc {uuid4().hex[:6]}",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    acct_cc = models.Account(
        name=f"Read CC Acc {uuid4().hex[:6]}",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("-100.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add_all([acct_chk, acct_cc])
    db_session.flush()

    # Checking transaction with description = ''
    tx_chk = models.Transaction(
        account_id=acct_chk.id,
        amount=Decimal("50.00"),
        date=date(2026, 6, 1),
        description="",
    )
    # Credit card transaction with description = ''
    tx_cc = models.Transaction(
        account_id=acct_cc.id,
        amount=Decimal("100.00"),
        date=date(2026, 6, 5),
        description="",
    )
    db_session.add_all([tx_chk, tx_cc])
    db_session.commit()

    # 1. Transaction List endpoint
    resp_list = client.get(f"/transactions/?account_id={acct_chk.id}")
    assert resp_list.status_code == 200
    items = resp_list.json()["items"]
    assert len(items) == 1
    assert items[0]["description"] == ""

    # 2. Transaction Detail endpoint
    resp_detail = client.get(f"/transactions/{tx_chk.transaction_id}")
    assert resp_detail.status_code == 200
    assert resp_detail.json()["description"] == ""

    # 3. Dashboard summary endpoint
    resp_dash = client.get("/summary/dashboard?month=2026-06")
    assert resp_dash.status_code == 200
    recent = resp_dash.json()["recent_transactions"]
    matching_recent = [r for r in recent if r["transaction_id"] == str(tx_chk.transaction_id)]
    assert len(matching_recent) == 1
    assert matching_recent[0]["description"] == ""

    # 4. Credit cards summary endpoint
    resp_cc = client.get("/credit-cards/summary?month=2026-06")
    assert resp_cc.status_code == 200
    cards = resp_cc.json()["cards"]
    target_card = next(c for c in cards if c["account_id"] == str(acct_cc.id))
    assert len(target_card["transactions"]) == 1
    assert target_card["transactions"][0]["description"] == ""

    # 5. Account reconciliation endpoint
    resp_recon = client.get(f"/accounts/{acct_chk.id}/reconciliation")
    assert resp_recon.status_code == 200
    recon_txs = resp_recon.json()["transactions"]
    assert len(recon_txs) == 1
    assert recon_txs[0]["description"] == ""
