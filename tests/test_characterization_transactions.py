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


# ---------------------------------------------------------------------------
# 8. Manual Transaction CRUD Endpoints Characterization (Slice 10)
# ---------------------------------------------------------------------------

def test_list_transactions_default_ordering_and_pagination(client, db_session):
    """
    Characterize GET /transactions/ default ordering, eager-loaded account, and pagination:
    - Sorting: date DESC, tie-broken by transaction_id DESC.
    - Eager loading: account relationship is loaded and serialized as AccountRead.
    - Limit capping: limit > 200 is clamped to 200.
    - Pagination metadata: items, total, limit, offset.
    """
    account = models.Account(name="List Acct", type="depository")
    db_session.add(account)
    db_session.commit()

    # Create 3 transactions with different dates and 2 with the same date
    tx1 = models.Transaction(account_id=account.id, description="Tx Early", amount=Decimal("10.00"), date=date(2026, 6, 1))
    tx2 = models.Transaction(account_id=account.id, description="Tx Mid 1", amount=Decimal("20.00"), date=date(2026, 6, 15))
    tx3 = models.Transaction(account_id=account.id, description="Tx Mid 2", amount=Decimal("30.00"), date=date(2026, 6, 15))
    tx4 = models.Transaction(account_id=account.id, description="Tx Late", amount=Decimal("40.00"), date=date(2026, 6, 30))
    db_session.add_all([tx1, tx2, tx3, tx4])
    db_session.commit()

    # Query with default limit and offset
    resp = client.get("/transactions/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert data["limit"] == 50
    assert data["offset"] == 0
    items = data["items"]
    assert len(items) == 4

    # Verify order: Tx Late (2026-06-30) first, Tx Early (2026-06-01) last
    assert items[0]["transaction_id"] == str(tx4.transaction_id)
    assert items[3]["transaction_id"] == str(tx1.transaction_id)

    # For equal dates (tx2 and tx3), tie-breaker is transaction_id DESC
    expected_mid_first = tx2 if tx2.transaction_id > tx3.transaction_id else tx3
    expected_mid_second = tx3 if tx2.transaction_id > tx3.transaction_id else tx2
    assert items[1]["transaction_id"] == str(expected_mid_first.transaction_id)
    assert items[2]["transaction_id"] == str(expected_mid_second.transaction_id)

    # Verify eager-loaded account structure
    assert items[0]["account"]["name"] == "List Acct"
    assert items[0]["account"]["account_id"] == str(account.id)

    # Pagination: limit=2, offset=1
    resp_page = client.get("/transactions/?limit=2&offset=1")
    assert resp_page.status_code == 200
    data_page = resp_page.json()
    assert data_page["total"] == 4
    assert data_page["limit"] == 2
    assert data_page["offset"] == 1
    assert len(data_page["items"]) == 2
    assert data_page["items"][0]["transaction_id"] == str(expected_mid_first.transaction_id)
    assert data_page["items"][1]["transaction_id"] == str(expected_mid_second.transaction_id)

    # Limit capped at 200 when limit=250
    resp_capped = client.get("/transactions/?limit=250")
    assert resp_capped.status_code == 200
    assert resp_capped.json()["limit"] == 200


def test_list_transactions_filters(client, db_session):
    """
    Characterize GET /transactions/ query filters:
    - account_id: filters by account
    - category_id: filters by category
    - start_date / end_date: date range filters
    - uncategorized=True: returns only category_id is None
    - q: case-insensitive description search
    """
    acc1 = models.Account(name="Acct 1", type="depository")
    acc2 = models.Account(name="Acct 2", type="depository")
    group = models.CategoryGroup(name="Expenses")
    db_session.add_all([acc1, acc2, group])
    db_session.flush()

    cat1 = models.Category(name="Groceries", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Utilities", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2])
    db_session.commit()

    t1 = models.Transaction(account_id=acc1.id, category_id=cat1.category_id, description="Whole Foods Market", amount=Decimal("50.00"), date=date(2026, 6, 5))
    t2 = models.Transaction(account_id=acc1.id, category_id=cat2.category_id, description="Electric Power Utility", amount=Decimal("80.00"), date=date(2026, 6, 10))
    t3 = models.Transaction(account_id=acc2.id, category_id=None, description="Coffee Shop Corner", amount=Decimal("4.50"), date=date(2026, 6, 15))
    t4 = models.Transaction(account_id=acc2.id, category_id=cat1.category_id, description="Trader Joe's", amount=Decimal("35.00"), date=date(2026, 6, 20))
    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    # Filter account_id
    r_acc = client.get(f"/transactions/?account_id={acc1.id}")
    assert r_acc.status_code == 200
    assert r_acc.json()["total"] == 2
    assert {it["transaction_id"] for it in r_acc.json()["items"]} == {str(t1.transaction_id), str(t2.transaction_id)}

    # Filter category_id
    r_cat = client.get(f"/transactions/?category_id={cat1.category_id}")
    assert r_cat.status_code == 200
    assert r_cat.json()["total"] == 2
    assert {it["transaction_id"] for it in r_cat.json()["items"]} == {str(t1.transaction_id), str(t4.transaction_id)}

    # Filter start_date and end_date
    r_date = client.get("/transactions/?start_date=2026-06-08&end_date=2026-06-18")
    assert r_date.status_code == 200
    assert r_date.json()["total"] == 2
    assert {it["transaction_id"] for it in r_date.json()["items"]} == {str(t2.transaction_id), str(t3.transaction_id)}

    # Filter uncategorized=True
    r_uncat = client.get("/transactions/?uncategorized=true")
    assert r_uncat.status_code == 200
    assert r_uncat.json()["total"] == 1
    assert r_uncat.json()["items"][0]["transaction_id"] == str(t3.transaction_id)

    # Filter q (case-insensitive description search)
    r_q = client.get("/transactions/?q=foods")
    assert r_q.status_code == 200
    assert r_q.json()["total"] == 1
    assert r_q.json()["items"][0]["transaction_id"] == str(t1.transaction_id)

    # Combined filters
    r_combo = client.get(f"/transactions/?account_id={acc2.id}&category_id={cat1.category_id}")
    assert r_combo.status_code == 200
    assert r_combo.json()["total"] == 1
    assert r_combo.json()["items"][0]["transaction_id"] == str(t4.transaction_id)


def test_list_transactions_boundary_cases(client, db_session):
    """
    Characterize GET /transactions/ boundary cases:
    - Empty database: items empty, total 0
    - Nonexistent account filter: empty
    - Nonexistent category filter: empty
    - start_date > end_date: empty
    - offset beyond total: empty items, total preserved
    """
    # Empty DB
    resp_empty = client.get("/transactions/")
    assert resp_empty.status_code == 200
    assert resp_empty.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}

    # Populate 1 row
    acc = models.Account(name="Boundary Acct", type="depository")
    db_session.add(acc)
    db_session.commit()
    t = models.Transaction(account_id=acc.id, description="Tx 1", amount=Decimal("10.00"), date=date(2026, 6, 1))
    db_session.add(t)
    db_session.commit()

    # Nonexistent account_id
    r_non_acc = client.get(f"/transactions/?account_id={uuid4()}")
    assert r_non_acc.status_code == 200
    assert r_non_acc.json()["total"] == 0
    assert r_non_acc.json()["items"] == []

    # Nonexistent category_id
    r_non_cat = client.get(f"/transactions/?category_id={uuid4()}")
    assert r_non_cat.status_code == 200
    assert r_non_cat.json()["total"] == 0
    assert r_non_cat.json()["items"] == []

    # start_date > end_date
    r_inverted_date = client.get("/transactions/?start_date=2026-06-10&end_date=2026-06-01")
    assert r_inverted_date.status_code == 200
    assert r_inverted_date.json()["total"] == 0
    assert r_inverted_date.json()["items"] == []

    # Offset beyond total
    r_offset = client.get("/transactions/?offset=10")
    assert r_offset.status_code == 200
    assert r_offset.json()["total"] == 1
    assert r_offset.json()["offset"] == 10
    assert r_offset.json()["items"] == []


def test_get_transaction_detail_found_and_not_found(client, db_session):
    """
    Characterize GET /transactions/{transaction_id}:
    - Found: 200 OK, TransactionRead serialized with eager-loaded account
    - Not found: 404 Not Found, exact detail 'Transaction not found'
    """
    account = models.Account(name="Detail Acct", type="depository")
    db_session.add(account)
    db_session.commit()

    txn = models.Transaction(
        account_id=account.id,
        description="Detail Target",
        amount=Decimal("42.50"),
        date=date(2026, 6, 12),
        pending=False,
    )
    db_session.add(txn)
    db_session.commit()

    # Found
    resp_found = client.get(f"/transactions/{txn.transaction_id}")
    assert resp_found.status_code == 200
    data = resp_found.json()
    assert data["transaction_id"] == str(txn.transaction_id)
    assert data["description"] == "Detail Target"
    assert Decimal(str(data["amount"])) == Decimal("42.50")
    assert data["date"] == "2026-06-12"
    assert data["pending"] is False
    assert data["is_transfer"] is False
    assert data["account"]["name"] == "Detail Acct"
    assert data["account"]["account_id"] == str(account.id)

    # Not found
    missing_id = uuid4()
    resp_missing = client.get(f"/transactions/{missing_id}")
    assert resp_missing.status_code == 404
    assert resp_missing.json() == {"detail": "Transaction not found"}


def test_manual_create_transaction_fields_and_validation(client, db_session):
    """
    Characterize POST /transactions/ full contract:
    - Normal creation with all fields
    - Defaults: pending defaults to False, is_transfer defaults to False in DB
    - Nonexistent account_id -> database foreign-key failure (IntegrityError)
    - Nonexistent category_id -> database foreign-key failure (IntegrityError)
    - Missing required fields (amount, description, date) -> HTTP 422
    """
    from sqlalchemy.exc import IntegrityError

    account = models.Account(name="Create Acct", type="depository")
    group = models.CategoryGroup(name="Living")
    db_session.add_all([account, group])
    db_session.flush()

    category = models.Category(name="Rent", group_id=group.category_group_id, type="expense")
    db_session.add(category)
    db_session.commit()

    # Valid creation with all fields
    payload = {
        "account_id": str(account.id),
        "category_id": str(category.category_id),
        "description": "Monthly Rent",
        "amount": "1200.00",
        "date": "2026-06-01",
        "pending": False,
        "plaid_transaction_id": "custom_plaid_123",
    }
    resp = client.post("/transactions/", json=payload)
    assert resp.status_code == 201
    created_id = resp.json()["transaction_id"]

    db_row = db_session.query(models.Transaction).filter_by(transaction_id=created_id).one()
    assert db_row.account_id == account.id
    assert db_row.category_id == category.category_id
    assert db_row.description == "Monthly Rent"
    assert db_row.amount == Decimal("1200.00")
    assert db_row.date == date(2026, 6, 1)
    assert db_row.pending is False
    assert db_row.is_transfer is False
    assert db_row.plaid_transaction_id == "custom_plaid_123"

    # Default pending=False when omitted
    payload_no_pending = {
        "account_id": str(account.id),
        "description": "No Pending Omitted",
        "amount": "10.00",
        "date": "2026-06-02",
    }
    resp_np = client.post("/transactions/", json=payload_no_pending)
    assert resp_np.status_code == 201
    assert resp_np.json()["pending"] is False

    # Nonexistent account_id -> DB IntegrityError
    payload_bad_acc = {
        "account_id": str(uuid4()),
        "description": "Bad Account",
        "amount": "10.00",
        "date": "2026-06-02",
    }
    with pytest.raises(IntegrityError):
        client.post("/transactions/", json=payload_bad_acc)
    db_session.rollback()

    # Nonexistent category_id -> DB IntegrityError
    payload_bad_cat = {
        "account_id": str(account.id),
        "category_id": str(uuid4()),
        "description": "Bad Category",
        "amount": "10.00",
        "date": "2026-06-02",
    }
    with pytest.raises(IntegrityError):
        client.post("/transactions/", json=payload_bad_cat)
    db_session.rollback()

    # Missing required field (e.g. amount) -> HTTP 422
    payload_missing_amount = {
        "account_id": str(account.id),
        "description": "Missing Amount",
        "date": "2026-06-02",
    }
    resp_422 = client.post("/transactions/", json=payload_missing_amount)
    assert resp_422.status_code == 422


def test_manual_update_transaction_fields_and_preservation(client, db_session):
    """
    Characterize PUT /transactions/{transaction_id}:
    - Updating category_id to new category
    - Clearing category_id with null
    - Updating is_transfer to True
    - Updating description
    - Preserving omitted fields (exclude_unset=True semantics)
    - Empty payload {} preserves all existing fields
    - Missing transaction ID -> 404 Not Found, exact detail 'Transaction not found or invalid update'
    - Nonexistent category_id -> DB IntegrityError
    """
    from sqlalchemy.exc import IntegrityError

    account = models.Account(name="Update Acct", type="depository")
    group = models.CategoryGroup(name="Life")
    db_session.add_all([account, group])
    db_session.flush()

    cat1 = models.Category(name="Dining", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Travel", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2])
    db_session.commit()

    txn = models.Transaction(
        account_id=account.id,
        category_id=cat1.category_id,
        description="Original Dinner",
        amount=Decimal("50.00"),
        date=date(2026, 6, 10),
        pending=False,
        is_transfer=False,
    )
    db_session.add(txn)
    db_session.commit()
    tx_id = str(txn.transaction_id)

    # 1. Update category_id to cat2
    resp1 = client.put(f"/transactions/{tx_id}", json={"category_id": str(cat2.category_id)})
    assert resp1.status_code == 200
    assert resp1.json()["category_id"] == str(cat2.category_id)
    assert resp1.json()["description"] == "Original Dinner"  # preserved
    assert resp1.json()["is_transfer"] is False             # preserved

    # 2. Clear category_id with null
    resp2 = client.put(f"/transactions/{tx_id}", json={"category_id": None})
    assert resp2.status_code == 200
    assert resp2.json()["category_id"] is None
    assert resp2.json()["description"] == "Original Dinner"

    # 3. Update is_transfer to True
    resp3 = client.put(f"/transactions/{tx_id}", json={"is_transfer": True})
    assert resp3.status_code == 200
    assert resp3.json()["is_transfer"] is True
    assert resp3.json()["description"] == "Original Dinner"

    # 4. Update description only
    resp4 = client.put(f"/transactions/{tx_id}", json={"description": "Updated Dinner"})
    assert resp4.status_code == 200
    assert resp4.json()["description"] == "Updated Dinner"
    assert resp4.json()["is_transfer"] is True  # preserved from prior update

    # 5. Empty payload {} preserves all existing fields
    resp5 = client.put(f"/transactions/{tx_id}", json={})
    assert resp5.status_code == 200
    assert resp5.json()["description"] == "Updated Dinner"
    assert resp5.json()["is_transfer"] is True

    # 6. Missing transaction ID -> 404 with exact detail
    missing_id = uuid4()
    resp_missing = client.put(f"/transactions/{missing_id}", json={"description": "Ghost"})
    assert resp_missing.status_code == 404
    assert resp_missing.json() == {"detail": "Transaction not found or invalid update"}

    # 7. Updating with nonexistent category_id -> DB IntegrityError
    with pytest.raises(IntegrityError):
        client.put(f"/transactions/{tx_id}", json={"category_id": str(uuid4())})
    db_session.rollback()


def test_manual_delete_transaction_found_and_not_found(client, db_session):
    """
    Characterize DELETE /transactions/{transaction_id}:
    - Found: 204 No Content, empty body, row completely removed from database
    - Not found: 404 Not Found, exact detail 'Transaction not found'
    """
    account = models.Account(name="Delete Acct", type="depository")
    db_session.add(account)
    db_session.commit()

    txn = models.Transaction(
        account_id=account.id,
        description="Delete Target",
        amount=Decimal("15.00"),
        date=date(2026, 6, 14),
    )
    db_session.add(txn)
    db_session.commit()
    tx_id = str(txn.transaction_id)

    # Delete existing transaction
    resp = client.delete(f"/transactions/{tx_id}")
    assert resp.status_code == 204
    assert resp.content == b""

    # Verify row is removed from DB
    db_session.expire_all()
    assert db_session.query(models.Transaction).filter_by(transaction_id=txn.transaction_id).first() is None

    # Delete missing transaction -> 404 with exact detail
    missing_id = uuid4()
    resp_missing = client.delete(f"/transactions/{missing_id}")
    assert resp_missing.status_code == 404
    assert resp_missing.json() == {"detail": "Transaction not found"}

