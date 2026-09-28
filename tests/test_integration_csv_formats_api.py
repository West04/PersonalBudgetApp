import io
from decimal import Decimal
from io import BytesIO
from uuid import UUID, uuid4
import pytest
from sqlalchemy import text

from backend import models, schemas
from backend.access import account_access, csv_format_access


@pytest.fixture(autouse=True)
def clean_database(db_session):
    """Ensure custom formats, transactions, and accounts are clean before and after each test."""
    db_session.execute(text("TRUNCATE TABLE transactions CASCADE;"))
    db_session.execute(text("TRUNCATE TABLE csv_formats CASCADE;"))
    db_session.execute(text("TRUNCATE TABLE accounts CASCADE;"))
    db_session.commit()
    yield
    db_session.execute(text("TRUNCATE TABLE transactions CASCADE;"))
    db_session.execute(text("TRUNCATE TABLE csv_formats CASCADE;"))
    db_session.execute(text("TRUNCATE TABLE accounts CASCADE;"))
    db_session.commit()


# ---------------------------------------------------------------------------
# 1. GET /upload/formats: Empty Collection & Ordering
# ---------------------------------------------------------------------------

def test_get_formats_empty_returns_200_empty_list(client):
    """Verify GET /upload/formats returns 200 with an empty list when no custom formats exist."""
    resp = client.get("/upload/formats")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_formats_returns_persisted_custom_formats_ordered_by_name_lower(client, db_session):
    """
    Verify GET /upload/formats returns only custom formats ordered by lower(name) ascending.
    Does not include built-in USAA or Discover.
    """
    csv_format_access.create_custom_format(
        db=db_session,
        name="Zeta Checking",
        date_column="TxDate",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    csv_format_access.create_custom_format(
        db=db_session,
        name="alpha savings",
        date_column="Date",
        description_column="Payee",
        amount_column="Total",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_inflow",
    )
    csv_format_access.create_custom_format(
        db=db_session,
        name="Beta Credit",
        date_column="PostDate",
        description_column="Memo",
        amount_column="Net",
        date_format="%d/%m/%Y",
        amount_sign_convention="positive_is_outflow",
    )

    resp = client.get("/upload/formats")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3

    names = [f["name"] for f in data]
    assert names == ["alpha savings", "Beta Credit", "Zeta Checking"]


# ---------------------------------------------------------------------------
# 2. POST /upload/formats: Success & Response Shape
# ---------------------------------------------------------------------------

def test_post_format_success_returns_201_with_valid_uuid(client, db_session):
    """
    Verify POST /upload/formats persists the format and returns 201 Created
    with full CSVFormatRead fields including UUID and timestamps.
    """
    payload = {
        "name": "Community Credit Union",
        "date_column": "Posting Date",
        "description_column": "Merchant Name",
        "amount_column": "Debit / Credit",
        "date_format": "%m/%d/%Y",
        "amount_sign_convention": "positive_is_outflow",
    }

    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    # Validate returned fields
    assert "id" in data
    format_id = UUID(data["id"])
    assert data["name"] == "Community Credit Union"
    assert data["date_column"] == "Posting Date"
    assert data["description_column"] == "Merchant Name"
    assert data["amount_column"] == "Debit / Credit"
    assert data["status_column"] is None
    assert data["date_format"] == "%m/%d/%Y"
    assert data["amount_sign_convention"] == "positive_is_outflow"
    assert data["status_posted_value"] is None
    assert "created_at" in data

    # Verify directly in database
    db_format = csv_format_access.get_custom_format_by_id(db_session, format_id)
    assert db_format is not None
    assert db_format.name == "Community Credit Union"
    assert db_format.status_column is None
    assert db_format.status_posted_value is None


def test_post_format_no_status_column_omitted_posted_value_returns_none(client, db_session):
    """
    Verify when status_column is omitted, status_posted_value is returned as None
    and persisted as None in the database.
    """
    payload = {
        "name": "Omitted Status Bank",
        "date_column": "Date",
        "description_column": "Desc",
        "amount_column": "Amt",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status_column"] is None
    assert data["status_posted_value"] is None

    # Check GET /upload/formats matches
    get_resp = client.get("/upload/formats")
    assert get_resp.status_code == 200
    formats = get_resp.json()
    assert len(formats) == 1
    assert formats[0]["status_column"] is None
    assert formats[0]["status_posted_value"] is None

    db_format = csv_format_access.get_custom_format_by_id(db_session, UUID(data["id"]))
    assert db_format is not None
    assert db_format.status_column is None
    assert db_format.status_posted_value is None


def test_post_format_no_status_column_explicit_posted_value_canonicalizes_to_none(client, db_session):
    """
    Verify when status_column is null/absent, any explicit status_posted_value in the request
    is canonicalized to None and persisted as None.
    """
    payload = {
        "name": "Explicit Posted Value But No Status Column",
        "date_column": "Date",
        "description_column": "Desc",
        "amount_column": "Amt",
        "status_column": None,
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
        "status_posted_value": "CLEARED",
    }
    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status_column"] is None
    assert data["status_posted_value"] is None

    # Check GET /upload/formats matches
    get_resp = client.get("/upload/formats")
    assert get_resp.status_code == 200
    assert get_resp.json()[0]["status_posted_value"] is None

    db_format = csv_format_access.get_custom_format_by_id(db_session, UUID(data["id"]))
    assert db_format is not None
    assert db_format.status_column is None
    assert db_format.status_posted_value is None


def test_post_format_with_status_column_omitted_posted_value_defaults_to_posted(client, db_session):
    """
    Verify when status_column is present and status_posted_value is omitted,
    status_posted_value defaults to 'posted'.
    """
    payload = {
        "name": "Status With Default Posted",
        "date_column": "Date",
        "description_column": "Desc",
        "amount_column": "Amt",
        "status_column": "Status",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status_column"] == "Status"
    assert data["status_posted_value"] == "posted"

    get_resp = client.get("/upload/formats")
    assert get_resp.status_code == 200
    assert get_resp.json()[0]["status_posted_value"] == "posted"

    db_format = csv_format_access.get_custom_format_by_id(db_session, UUID(data["id"]))
    assert db_format is not None
    assert db_format.status_column == "Status"
    assert db_format.status_posted_value == "posted"


def test_post_format_with_status_column_canonicalizes_posted_value(client, db_session):
    """
    Verify status_column and custom status_posted_value are canonicalized and serialized properly.
    status_posted_value is stripped and lowercased.
    """
    payload = {
        "name": "Bank With Status",
        "date_column": "Date",
        "description_column": "Payee",
        "amount_column": "Amount",
        "status_column": "State",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
        "status_posted_value": "  CLEARED  ",
    }

    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["status_column"] == "State"
    assert data["status_posted_value"] == "cleared"

    get_resp = client.get("/upload/formats")
    assert get_resp.status_code == 200
    assert get_resp.json()[0]["status_posted_value"] == "cleared"

    db_format = csv_format_access.get_custom_format_by_id(db_session, UUID(data["id"]))
    assert db_format is not None
    assert db_format.status_posted_value == "cleared"


def test_post_format_canonicalizes_name_whitespace(client, db_session):
    """Verify name whitespace is trimmed during creation."""
    payload = {
        "name": "   Trimmed Bank Name   ",
        "date_column": "Date",
        "description_column": "Desc",
        "amount_column": "Amt",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }

    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Trimmed Bank Name"


# ---------------------------------------------------------------------------
# 3. GET /upload/formats after POST
# ---------------------------------------------------------------------------

def test_get_after_post_contains_new_format(client):
    """Verify a format created via POST immediately appears in GET /upload/formats."""
    payload = {
        "name": "First National",
        "date_column": "TxDate",
        "description_column": "TxDesc",
        "amount_column": "TxAmt",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    create_resp = client.post("/upload/formats", json=payload)
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    get_resp = client.get("/upload/formats")
    assert get_resp.status_code == 200
    formats = get_resp.json()
    assert len(formats) == 1
    assert formats[0]["id"] == created_id
    assert formats[0]["name"] == "First National"


# ---------------------------------------------------------------------------
# 4. Error Handling: Reserved Names, Name Conflicts & Semantic Duplicates (HTTP 409)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reserved_name", ["usaa", "USAA", "discover", "Discover", "DISCOVER"])
def test_post_format_reserved_name_returns_409(client, db_session, reserved_name):
    """Verify using a reserved built-in name returns HTTP 409 Conflict without persisting a row."""
    payload = {
        "name": reserved_name,
        "date_column": "Date",
        "description_column": "Description",
        "amount_column": "Amount",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }

    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 409
    assert "reserved" in resp.json()["detail"].lower()
    assert db_session.query(models.CSVFormat).count() == 0


def test_post_format_case_insensitive_name_conflict_returns_409(client, db_session):
    """Verify attempting to create a format with an existing name (case-insensitive) returns 409."""
    payload1 = {
        "name": "Metro Credit Union",
        "date_column": "Date1",
        "description_column": "Desc1",
        "amount_column": "Amt1",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    resp1 = client.post("/upload/formats", json=payload1)
    assert resp1.status_code == 201

    payload2 = {
        "name": "  metro credit union  ",
        "date_column": "Date2",
        "description_column": "Desc2",
        "amount_column": "Amt2",
        "date_format": "%m/%d/%Y",
        "amount_sign_convention": "positive_is_inflow",
    }
    resp2 = client.post("/upload/formats", json=payload2)
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"].lower()
    assert db_session.query(models.CSVFormat).count() == 1


def test_post_format_semantic_duplicate_returns_409(client, db_session):
    """
    Verify creating a format with a distinct name but identical parsing configuration
    returns HTTP 409 Conflict.
    """
    payload1 = {
        "name": "Regional Checking",
        "date_column": "TxDate",
        "description_column": "Memo",
        "amount_column": "Value",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    resp1 = client.post("/upload/formats", json=payload1)
    assert resp1.status_code == 201

    payload2 = {
        "name": "Regional Savings",
        "date_column": "TxDate",
        "description_column": "Memo",
        "amount_column": "Value",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    resp2 = client.post("/upload/formats", json=payload2)
    assert resp2.status_code == 409
    assert "identical format configuration already exists" in resp2.json()["detail"].lower()
    assert db_session.query(models.CSVFormat).count() == 1


def test_post_format_same_headers_different_semantics_allowed(client, db_session):
    """
    Verify formats sharing the same column header names but differing in parser properties
    (such as date_format or sign convention) are NOT considered duplicates and succeed.
    """
    payload1 = {
        "name": "Bank Standard Format",
        "date_column": "Date",
        "description_column": "Memo",
        "amount_column": "Amount",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    resp1 = client.post("/upload/formats", json=payload1)
    assert resp1.status_code == 201

    payload2 = {
        "name": "Bank Alternate Date Format",
        "date_column": "Date",
        "description_column": "Memo",
        "amount_column": "Amount",
        "date_format": "%m/%d/%Y",
        "amount_sign_convention": "positive_is_outflow",
    }
    resp2 = client.post("/upload/formats", json=payload2)
    assert resp2.status_code == 201

    assert db_session.query(models.CSVFormat).count() == 2


# ---------------------------------------------------------------------------
# 5. Error Handling: Pydantic Transport Validation (HTTP 422)
# ---------------------------------------------------------------------------

def test_post_format_invalid_amount_sign_convention_returns_422(client, db_session):
    """Verify invalid amount_sign_convention is rejected with HTTP 422."""
    payload = {
        "name": "Invalid Sign Bank",
        "date_column": "Date",
        "description_column": "Desc",
        "amount_column": "Amt",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "invalid_convention",
    }
    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 422
    assert db_session.query(models.CSVFormat).count() == 0


def test_post_format_duplicate_mapped_columns_returns_422(client, db_session):
    """Verify duplicate column names among date, description, and amount return HTTP 422."""
    payload = {
        "name": "Dup Columns Bank",
        "date_column": "ColA",
        "description_column": "ColA",
        "amount_column": "Amt",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 422
    assert "distinct" in str(resp.json()).lower()
    assert db_session.query(models.CSVFormat).count() == 0


def test_post_format_empty_field_returns_422(client, db_session):
    """Verify empty/whitespace strings for required fields return HTTP 422."""
    payload = {
        "name": "   ",
        "date_column": "Date",
        "description_column": "Desc",
        "amount_column": "Amt",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    resp = client.post("/upload/formats", json=payload)
    assert resp.status_code == 422
    assert db_session.query(models.CSVFormat).count() == 0


# ---------------------------------------------------------------------------
# 6. End-to-End Workflow: Create -> Inspect -> Preview -> Confirm
# ---------------------------------------------------------------------------

def test_create_format_then_inspect_detects_returned_uuid(client):
    """
    Product contract:
    1. POST a new custom format.
    2. Capture returned UUID.
    3. Upload matching CSV to POST /upload/inspect.
    4. Verify Inspect returns status='detected' with detected_format.identifier equal to the UUID.
    """
    create_payload = {
        "name": "E2E Credit Union",
        "date_column": "TxDate",
        "description_column": "Merchant",
        "amount_column": "TotalSpent",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    create_resp = client.post("/upload/formats", json=create_payload)
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    # Upload matching CSV
    csv_content = (
        "TxDate,Merchant,TotalSpent\n"
        "2026-09-15,Grocery Mart,42.50\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    inspect_resp = client.post("/upload/inspect", files=files)
    assert inspect_resp.status_code == 200
    inspect_data = inspect_resp.json()

    assert inspect_data["status"] == "detected"
    assert inspect_data["detected_format"]["identifier"] == created_id
    assert inspect_data["detected_format"]["name"] == "E2E Credit Union"
    assert inspect_data["headers"] == ["TxDate", "Merchant", "TotalSpent"]
    assert inspect_data["sample_rows"] == [["2026-09-15", "Grocery Mart", "42.50"]]


def test_create_format_then_preview_uses_returned_uuid(client, db_session):
    """
    Product contract:
    1. POST a new custom format.
    2. Capture returned UUID.
    3. Call POST /upload/preview with format=<returned_uuid>.
    4. Verify transactions are parsed according to custom format rules.
    """
    # Create test account
    account = models.Account(
        name="Checking Account",
        type="depository",
        is_active=True,
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("1000.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    create_payload = {
        "name": "Preview Bank",
        "date_column": "Posting Date",
        "description_column": "Memo",
        "amount_column": "Amount",
        "date_format": "%m/%d/%Y",
        "amount_sign_convention": "positive_is_inflow",  # inverts sign: positive -> negative in app domain
    }
    create_resp = client.post("/upload/formats", json=create_payload)
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    csv_content = (
        "Posting Date,Memo,Amount\n"
        "09/20/2026,Payroll Direct Dep,1500.00\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    form_data = {
        "account_id": str(account.id),
        "format": created_id,
    }

    preview_resp = client.post("/upload/preview", files=files, data=form_data)
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()

    assert preview_data["total_rows"] == 1
    assert preview_data["valid_rows"] == 1
    assert preview_data["error_rows"] == 0

    row = preview_data["rows"][0]
    assert row["transaction_date"] == "2026-09-20"
    assert row["description"] == "Payroll Direct Dep"
    # positive_is_inflow: 1500.00 in CSV becomes -1500.00 (inflow) in domain
    assert Decimal(str(row["amount"])) == Decimal("-1500.00")


def test_create_format_then_confirm_imports_transactions(client, db_session):
    """
    Product contract:
    1. POST a new custom format.
    2. Capture returned UUID.
    3. Call POST /upload/confirm with format=<returned_uuid>.
    4. Verify transaction is persisted to database.
    """
    account = models.Account(
        name="Credit Card",
        type="credit",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    create_payload = {
        "name": "Confirm Card",
        "date_column": "TxDate",
        "description_column": "Vendor",
        "amount_column": "NetValue",
        "status_column": "Status",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
        "status_posted_value": "posted",
    }
    create_resp = client.post("/upload/formats", json=create_payload)
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    csv_content = (
        "TxDate,Vendor,NetValue,Status\n"
        "2026-09-22,Hardware Store,85.50,posted\n"
        "2026-09-23,Coffee Shop,4.50,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    form_data = {
        "account_id": str(account.id),
        "format": created_id,
    }

    confirm_resp = client.post("/upload/confirm", files=files, data=form_data)
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()

    assert confirm_data["imported"] == 2
    assert confirm_data["skipped"] == 0
    assert confirm_data["errors"] == []

    # Verify persisted in database
    txs = (
        db_session.query(models.Transaction)
        .filter_by(account_id=account.id)
        .order_by(models.Transaction.date.asc())
        .all()
    )
    assert len(txs) == 2
    assert txs[0].description == "Hardware Store"
    assert txs[0].amount == Decimal("85.50")
    assert txs[0].date.isoformat() == "2026-09-22"
    assert txs[1].description == "Coffee Shop"
    assert txs[1].amount == Decimal("4.50")
    assert txs[1].date.isoformat() == "2026-09-23"
