"""
Characterization tests for Transaction datetime behavior across schemas,
persistence, endpoints, and background Plaid sync workflows.

Reflects Slice 8 behavior:
- TransactionCreate and TransactionRead datetime annotations resolve to Optional[datetime].
- Manual creation and Plaid new/modified-missing transactions accept and persist timestamps.
- Reads serialize populated timestamps as ISO strings without raising errors.
- Manual updates preserve the existing TransactionUpdate contract (datetime not editable).
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pydantic
import pytest
from fastapi.testclient import TestClient

from backend import models, schemas
from backend.access import transaction_access
from backend.main import app


# ---------------------------------------------------------------------------
# 1. Pydantic Schema Annotations & Direct Validation
# ---------------------------------------------------------------------------

def test_schema_transaction_create_datetime_annotation_is_proper_datetime():
    """
    In backend/schemas.py, TransactionCreate defines:
        datetime: Optional[DateTime] = None
    Disambiguated via alias DateTime so the annotation resolves to Optional[datetime.datetime].
    """
    field = schemas.TransactionCreate.model_fields["datetime"]
    assert field.annotation == Optional[datetime]
    assert field.annotation is not type(None)
    assert field.default is None

    base_kwargs = {
        "account_id": uuid4(),
        "description": "Schema test",
        "amount": Decimal("25.00"),
        "date": date(2026, 6, 15),
    }

    # 1. datetime=None succeeds
    tx_none = schemas.TransactionCreate(**base_kwargs, datetime=None)
    assert tx_none.datetime is None

    # 2. datetime omitted succeeds (defaults to None)
    tx_omitted = schemas.TransactionCreate(**base_kwargs)
    assert tx_omitted.datetime is None

    # 3. datetime=<valid datetime object> succeeds
    now_dt = datetime.now(timezone.utc)
    tx_dt = schemas.TransactionCreate(**base_kwargs, datetime=now_dt)
    assert tx_dt.datetime == now_dt

    # 4. datetime=<ISO string> succeeds and parses to datetime
    tx_iso = schemas.TransactionCreate(**base_kwargs, datetime="2026-06-15T10:30:00Z")
    assert tx_iso.datetime == datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)


def test_schema_transaction_read_datetime_annotation_is_proper_datetime():
    """
    Similarly, TransactionRead defines:
        datetime: Optional[DateTime] = None
    Resolving to Optional[datetime.datetime]. Populated timestamps validate
    and serialize to ISO strings.
    """
    field = schemas.TransactionRead.model_fields["datetime"]
    assert field.annotation == Optional[datetime]
    assert field.annotation is not type(None)
    assert field.default is None

    base_kwargs = {
        "transaction_id": uuid4(),
        "account_id": uuid4(),
        "description": "Read test",
        "amount": Decimal("10.00"),
        "date": date(2026, 6, 15),
        "pending": False,
    }

    # datetime=None succeeds
    read_none = schemas.TransactionRead(**base_kwargs, datetime=None)
    assert read_none.datetime is None
    assert '"datetime":null' in read_none.model_dump_json()

    # non-null datetime succeeds and serializes
    now_dt = datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)
    read_pop = schemas.TransactionRead(**base_kwargs, datetime=now_dt)
    assert read_pop.datetime == now_dt
    assert "2026-06-15T10:30:00Z" in read_pop.model_dump_json()


# ---------------------------------------------------------------------------
# 2. Manual Transaction Creation (POST /transactions/)
# ---------------------------------------------------------------------------

def test_manual_transaction_creation_datetime_cases(client, db_session):
    """
    Characterize POST /transactions/ after Slice 8 fix:
    - Case A: {"datetime": null} -> 201 Created, stored as None
    - Case B: datetime omitted -> 201 Created, stored as None
    - Case C: {"datetime": "2026-06-17T10:30:00Z"} -> 201 Created, timestamp persisted in DB
    """
    account = models.Account(
        name="Manual Test Account",
        type="depository",
        subtype="checking",
    )
    db_session.add(account)
    db_session.commit()

    # Case A: datetime is explicitly null
    payload_a = {
        "account_id": str(account.id),
        "description": "Manual Tx Case A",
        "amount": "15.50",
        "date": "2026-06-15",
        "datetime": None,
    }
    resp_a = client.post("/transactions/", json=payload_a)
    assert resp_a.status_code == 201
    data_a = resp_a.json()
    assert data_a["datetime"] is None

    db_tx_a = db_session.query(models.Transaction).filter_by(transaction_id=data_a["transaction_id"]).one()
    assert db_tx_a.datetime is None

    # Case B: datetime omitted
    payload_b = {
        "account_id": str(account.id),
        "description": "Manual Tx Case B",
        "amount": "25.00",
        "date": "2026-06-16",
    }
    resp_b = client.post("/transactions/", json=payload_b)
    assert resp_b.status_code == 201
    data_b = resp_b.json()
    assert data_b["datetime"] is None

    db_tx_b = db_session.query(models.Transaction).filter_by(transaction_id=data_b["transaction_id"]).one()
    assert db_tx_b.datetime is None

    # Case C: datetime is populated ISO string -> 201 Created (Approved behavior change in Slice 8)
    payload_c = {
        "account_id": str(account.id),
        "description": "Manual Tx Case C",
        "amount": "35.00",
        "date": "2026-06-17",
        "datetime": "2026-06-17T10:30:00Z",
    }
    resp_c = client.post("/transactions/", json=payload_c)
    assert resp_c.status_code == 201
    data_c = resp_c.json()
    assert data_c["datetime"] is not None
    assert "2026-06-17T10:30:00" in data_c["datetime"]

    db_tx_c = db_session.query(models.Transaction).filter_by(transaction_id=data_c["transaction_id"]).one()
    assert db_tx_c.datetime == datetime(2026, 6, 17, 10, 30, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 3. Manual Transaction Update (PUT /transactions/{id})
# ---------------------------------------------------------------------------

def test_manual_transaction_update_datetime_behavior(client, db_session):
    """
    Characterize PUT /transactions/{id}:
    - Uses TransactionUpdate schema (category_id, description, is_transfer).
    - Extra fields like datetime are ignored by Pydantic; datetime is NOT editable.
    - If existing row has datetime=None, update succeeds (200 OK), datetime remains None.
    - If existing row has a populated datetime, updating description succeeds (200 OK),
      persisting existing datetime and serializing response cleanly without 500 error.
    """
    account = models.Account(name="Update Acct", type="depository")
    db_session.add(account)
    db_session.commit()

    # 1. Row with datetime=None
    tx_null = models.Transaction(
        account_id=account.id,
        description="Original null dt",
        amount=Decimal("10.00"),
        date=date(2026, 6, 15),
        datetime=None,
    )
    db_session.add(tx_null)
    db_session.commit()

    # Updating description while leaving datetime unchanged
    resp1 = client.put(f"/transactions/{tx_null.transaction_id}", json={
        "description": "Updated null dt",
    })
    assert resp1.status_code == 200
    assert resp1.json()["description"] == "Updated null dt"
    assert resp1.json()["datetime"] is None

    # Sending datetime in PUT payload is ignored by TransactionUpdate (not editable)
    resp2 = client.put(f"/transactions/{tx_null.transaction_id}", json={
        "description": "Attempt dt in PUT",
        "datetime": "2026-06-15T12:00:00Z",
    })
    assert resp2.status_code == 200
    db_session.refresh(tx_null)
    assert tx_null.datetime is None

    # 2. Row with populated datetime
    populated_dt = datetime(2026, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    tx_pop = models.Transaction(
        account_id=account.id,
        description="Original pop dt",
        amount=Decimal("20.00"),
        date=date(2026, 6, 15),
        datetime=populated_dt,
    )
    db_session.add(tx_pop)
    db_session.commit()

    # Updating a row with populated datetime now serializes successfully (Slice 8 fix)
    resp3 = client.put(f"/transactions/{tx_pop.transaction_id}", json={
        "description": "New description on pop dt",
    })
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["description"] == "New description on pop dt"
    assert data3["datetime"] is not None
    assert "2026-06-15T10:30:00" in data3["datetime"]

    db_session.refresh(tx_pop)
    assert tx_pop.datetime == populated_dt


# ---------------------------------------------------------------------------
# 4. Plaid Sync Workflow Datetime Matrix (POST /plaid/sync_transactions)
# ---------------------------------------------------------------------------

def _setup_plaid_test(db_session, plaid_item_id="item_sync_matrix"):
    item = models.PlaidItem(
        plaid_item_id=plaid_item_id,
        plaid_access_token_encrypted="encrypted_tok",
        transactions_cursor=None,
    )
    account = models.Account(
        plaid_account_id=f"acc_{plaid_item_id}",
        name="Plaid Checking",
        type="depository",
        subtype="checking",
    )
    db_session.add_all([item, account])
    db_session.commit()
    return item, account


def _mock_accounts_resp():
    mock_resp = MagicMock()
    mock_resp.accounts = []
    return mock_resp


def test_plaid_sync_added_existing_row_with_non_null_datetime_succeeds(client, db_session):
    """
    Plaid added event + existing local row + non-null datetime:
    Bypasses TransactionCreate and updates the ORM model directly.
    Succeeds with HTTP 200, storing the non-null datetime in DB.
    """
    item, account = _setup_plaid_test(db_session, "item_add_existing_dt")

    existing_tx = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="tx_add_exist_1",
        description="Original Exist Desc",
        amount=Decimal("-15.00"),
        date=date(2026, 6, 1),
        datetime=None,
        pending=True,
    )
    db_session.add(existing_tx)
    db_session.commit()

    tx_page = {
        "added": [
            {
                "transaction_id": "tx_add_exist_1",
                "account_id": account.plaid_account_id,
                "name": "Updated via Added Event",
                "amount": -20.00,  # inverts to +20.00
                "date": "2026-06-02",
                "datetime": "2026-06-02T15:45:00Z",
                "pending": False,
            }
        ],
        "modified": [],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_add_exist",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_mock_accounts_resp()), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json()["added"] == 1

    db_session.refresh(existing_tx)
    assert existing_tx.description == "Updated via Added Event"
    assert existing_tx.amount == Decimal("20.00")
    assert existing_tx.datetime == datetime(2026, 6, 2, 15, 45, tzinfo=timezone.utc)


def test_plaid_sync_modified_missing_row_datetime_null_succeeds(client, db_session):
    """
    Plaid modified event + NO local row + datetime=None:
    Falls back to the create path, constructs TransactionCreate(datetime=None),
    and succeeds with HTTP 200.
    """
    item, account = _setup_plaid_test(db_session, "item_mod_missing_null")

    tx_page = {
        "added": [],
        "modified": [
            {
                "transaction_id": "tx_mod_missing_1",
                "account_id": account.plaid_account_id,
                "name": "Modified Missing Null DT",
                "amount": 40.00,  # inverts to -40.00
                "date": "2026-06-10",
                "datetime": None,
                "pending": False,
            }
        ],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_mod_missing_null",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_mock_accounts_resp()), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json()["modified"] == 1

    created_tx = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_mod_missing_1").one()
    assert created_tx.description == "Modified Missing Null DT"
    assert created_tx.amount == Decimal("-40.00")
    assert created_tx.datetime is None


def test_plaid_sync_modified_missing_row_datetime_populated_succeeds(client, db_session):
    """
    Plaid modified event + NO local row + non-null datetime:
    Falls back to the create path, constructs TransactionCreate(datetime=...),
    validates successfully after Slice 8 fix, and commits the transaction to DB.
    """
    item, account = _setup_plaid_test(db_session, "item_mod_missing_pop")

    tx_page = {
        "added": [],
        "modified": [
            {
                "transaction_id": "tx_mod_missing_pop_1",
                "account_id": account.plaid_account_id,
                "name": "Modified Missing Pop DT",
                "amount": 40.00,
                "date": "2026-06-10",
                "datetime": "2026-06-10T14:30:00Z",
                "pending": False,
            }
        ],
        "removed": [],
        "has_more": False,
        "next_cursor": "cur_mod_missing_pop",
    }

    mock_http_resp = MagicMock()
    mock_http_resp.json.return_value = tx_page
    mock_http_resp.raise_for_status.return_value = None

    with patch("backend.access.plaid_access.client.accounts_get", return_value=_mock_accounts_resp()), \
         patch("backend.access.plaid_transaction_access.requests.post", return_value=mock_http_resp):
        resp = client.post("/plaid/sync_transactions", json={"item_id": str(item.id)})

    assert resp.status_code == 200
    assert resp.json()["modified"] == 1

    created_tx = db_session.query(models.Transaction).filter_by(plaid_transaction_id="tx_mod_missing_pop_1").one()
    assert created_tx.description == "Modified Missing Pop DT"
    assert created_tx.amount == Decimal("-40.00")
    assert created_tx.datetime == datetime(2026, 6, 10, 14, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 5. Direct Helper Behavior Matrix (transaction_access.stage_or_update_plaid_transaction)
# ---------------------------------------------------------------------------

def test_stage_or_update_plaid_transaction_direct_behavior_matrix(db_session):
    """
    Directly exercises transaction_access.stage_or_update_plaid_transaction(...)
    for all 5 branches of the behavior matrix:
    1. Plaid added / No local row / datetime=None -> create path -> succeeds
    2. Plaid added / No local row / datetime=non-null -> create path -> succeeds (Slice 8)
    3. Plaid added / Local row exists / datetime=non-null -> update path -> succeeds
    4. Plaid modified / No local row / datetime=non-null -> create fallback -> succeeds (Slice 8)
    5. Plaid modified / Local row exists / datetime=non-null -> update path -> succeeds
    """
    account = models.Account(
        name="Direct Matrix Acct",
        type="depository",
        plaid_account_id="direct_plaid_acc",
    )
    db_session.add(account)
    db_session.commit()

    # 1. Added / No local / datetime=None
    tx1 = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="direct_tx_1",
        account_id=account.id,
        description="Tx 1 Added Null DT",
        amount=Decimal("-10.00"),
        transaction_date=date(2026, 6, 15),
        transaction_datetime=None,
        pending=False,
    )
    db_session.commit()
    assert tx1.datetime is None
    assert tx1.amount == Decimal("-10.00")

    # 2. Added / No local / datetime=non-null (Succeeds in Slice 8)
    tx2 = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="direct_tx_2",
        account_id=account.id,
        description="Tx 2 Added Pop DT",
        amount=Decimal("-15.00"),
        transaction_date=date(2026, 6, 15),
        transaction_datetime=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
        pending=False,
    )
    db_session.commit()
    assert tx2.datetime == datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    assert tx2.amount == Decimal("-15.00")

    # 3. Added / Local row exists / datetime=non-null
    tx3 = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="direct_tx_1",
        account_id=account.id,
        description="Tx 1 Updated Via Added",
        amount=Decimal("-20.00"),
        transaction_date=date(2026, 6, 16),
        transaction_datetime=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
        pending=False,
    )
    db_session.commit()
    assert tx3.datetime == datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    assert tx3.amount == Decimal("-20.00")

    # 4. Modified / No local / datetime=non-null (Succeeds in Slice 8)
    tx4 = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="direct_tx_missing",
        account_id=account.id,
        description="Tx Missing Modified Pop DT",
        amount=Decimal("-25.00"),
        transaction_date=date(2026, 6, 15),
        transaction_datetime=datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc),
        pending=False,
    )
    db_session.commit()
    assert tx4.datetime == datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
    assert tx4.amount == Decimal("-25.00")

    # 5. Modified / Local row exists / datetime=non-null
    tx5 = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="direct_tx_1",
        account_id=account.id,
        description="Tx 1 Updated Via Modified",
        amount=Decimal("-30.00"),
        transaction_date=date(2026, 6, 17),
        transaction_datetime=datetime(2026, 6, 17, 16, 0, tzinfo=timezone.utc),
        pending=False,
    )
    db_session.commit()
    assert tx5.datetime == datetime(2026, 6, 17, 16, 0, tzinfo=timezone.utc)
    assert tx5.amount == Decimal("-30.00")


# ---------------------------------------------------------------------------
# 6. Read & Serialization of Populated Datetime Rows
# ---------------------------------------------------------------------------

def test_read_endpoints_behavior_with_populated_datetime_row(client, db_session):
    """
    When a database row contains a non-null datetime:
    - GET /transactions/{id} succeeds with 200 OK and serializes ISO timestamp
    - GET /transactions/ succeeds with 200 OK and serializes ISO timestamp
    - GET /summary/dashboard succeeds with 200 OK and serializes recent transactions with ISO timestamp
    - GET /summary/budget succeeds with 200 OK
    - GET /credit-cards/summary succeeds with 200 OK
    """
    account = models.Account(
        name="Credit Card",
        type="credit",
        subtype="credit card",
        starting_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    dt_val = datetime(2026, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    tx_pop = models.Transaction(
        account_id=account.id,
        description="Populated DT row",
        amount=Decimal("50.00"),
        date=date(2026, 6, 15),
        datetime=dt_val,
        pending=False,
    )
    db_session.add(tx_pop)
    db_session.commit()
    tx_id = str(tx_pop.transaction_id)

    # 1. GET /transactions/{id} succeeds (Slice 8)
    resp1 = client.get(f"/transactions/{tx_id}")
    assert resp1.status_code == 200
    assert resp1.json()["datetime"] is not None
    assert "2026-06-15T10:30:00" in resp1.json()["datetime"]

    # 2. GET /transactions/ succeeds (Slice 8)
    resp2 = client.get("/transactions/")
    assert resp2.status_code == 200
    items = resp2.json()["items"]
    assert len(items) >= 1
    matched = [it for it in items if it["transaction_id"] == tx_id]
    assert len(matched) == 1
    assert "2026-06-15T10:30:00" in matched[0]["datetime"]

    # 3. GET /summary/dashboard succeeds (Slice 8)
    resp3 = client.get("/summary/dashboard?month=2026-06")
    assert resp3.status_code == 200
    recent = resp3.json()["recent_transactions"]
    assert len(recent) >= 1
    matched_recent = [it for it in recent if it["transaction_id"] == tx_id]
    assert len(matched_recent) == 1
    assert "2026-06-15T10:30:00" in matched_recent[0]["datetime"]

    # 4. GET /summary/budget is unaffected
    resp_budget = client.get("/summary/budget?month=2026-06")
    assert resp_budget.status_code == 200

    # 5. GET /credit-cards/summary is unaffected
    resp_cc = client.get("/credit-cards/summary?month=2026-06")
    assert resp_cc.status_code == 200


# ---------------------------------------------------------------------------
# 7. Database Timezone & Date Invariants
# ---------------------------------------------------------------------------

def test_database_timezone_normalization_and_date_invariants(db_session):
    """
    Characterize PostgreSQL storage semantics:
    1. Timezone offset storage: PostgreSQL column TIMESTAMP WITH TIME ZONE
       normalizes input timestamps to UTC (+00:00).
    2. Date vs datetime invariant: No application validation or DB constraint
       enforces that Transaction.date matches Transaction.datetime.date().
    """
    account = models.Account(name="DB Invariant Acct", type="depository")
    db_session.add(account)
    db_session.commit()

    # Explicit offset -07:00
    tz_minus_7 = timezone(timedelta(hours=-7))
    dt_with_offset = datetime(2026, 6, 15, 10, 30, 0, tzinfo=tz_minus_7)

    # Mismatched date and datetime
    tx = models.Transaction(
        account_id=account.id,
        description="Offset & Mismatched Test",
        amount=Decimal("12.34"),
        date=date(2026, 6, 20),  # Intentionally different from datetime date (2026-06-15)
        datetime=dt_with_offset,
        pending=False,
    )
    db_session.add(tx)
    db_session.commit()

    # Expire and reload to verify actual PostgreSQL returned types
    db_session.expire_all()
    reloaded = db_session.query(models.Transaction).filter_by(transaction_id=tx.transaction_id).one()

    # Verified: normalized to UTC, tzinfo is datetime.timezone.utc
    assert reloaded.datetime.tzinfo == timezone.utc
    assert reloaded.datetime == datetime(2026, 6, 15, 17, 30, 0, tzinfo=timezone.utc)

    # Verified: Mismatched date succeeds; no invariant currently enforced
    assert reloaded.date == date(2026, 6, 20)
