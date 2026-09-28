"""
Integration tests for Preview and Confirm CSV workflows with user-defined custom formats.

Validates:
- Explicit format resolution for custom format UUIDs
- Preserved built-in resolution (usaa, discover)
- Persistence-to-parser configuration conversion
- Sign inversion (positive_is_inflow vs positive_is_outflow)
- Status mapping (case-insensitive, trimmed, custom posted token)
- Error handling (missing custom format 404, invalid format string 400)
- Validation precedence (account 404 before format errors)
- Missing required custom headers (422 in Confirm, error row in Preview)
- Tolerant parsing during Confirm with per-row errors
- Duplicate transaction skipping on re-import
- Proof that detect_csv_format is NOT called during Preview or Confirm
"""

from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from sqlalchemy import text

from backend import models
from backend.access import csv_format_access


@pytest.fixture(autouse=True)
def clean_database(db_session):
    """Ensure clean accounts, transactions, and custom formats before each test."""
    db_session.execute(text("TRUNCATE TABLE transactions, accounts, csv_formats CASCADE;"))
    db_session.commit()
    yield
    db_session.execute(text("TRUNCATE TABLE transactions, accounts, csv_formats CASCADE;"))
    db_session.commit()


@pytest.fixture
def test_account(db_session) -> models.Account:
    """Helper fixture to create a valid test account."""
    account = models.Account(
        name="Primary Checking",
        type="depository",
        is_active=True,
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("1000.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


# ---------------------------------------------------------------------------
# 1. Custom Format Preview Integration
# ---------------------------------------------------------------------------

def test_custom_format_preview_success(client, db_session, test_account):
    """Verify POST /upload/preview parses and normalizes rows using a persisted custom format UUID."""
    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="Credit Union Statement",
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Value",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
        status_column=None,
    )

    csv_content = (
        "Posting Date,Memo,Value\n"
        "09/01/2026,Coffee Shop,6.25\n"
        "09/02/2026,Payroll Direct Dep,-2500.00\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": str(custom_format.id)}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()

    assert res["total_rows"] == 2
    assert res["valid_rows"] == 2
    assert res["error_rows"] == 0

    rows = res["rows"]
    assert rows[0]["row_number"] == 1
    assert rows[0]["transaction_date"] == "2026-09-01"
    assert rows[0]["description"] == "Coffee Shop"
    assert Decimal(str(rows[0]["amount"])) == Decimal("6.25")
    assert rows[0]["pending"] is False
    assert rows[0]["parse_error"] is None

    assert rows[1]["row_number"] == 2
    assert rows[1]["transaction_date"] == "2026-09-02"
    assert rows[1]["description"] == "Payroll Direct Dep"
    assert Decimal(str(rows[1]["amount"])) == Decimal("-2500.00")
    assert rows[1]["pending"] is False
    assert rows[1]["parse_error"] is None


# ---------------------------------------------------------------------------
# 2. Custom Format Confirm Integration
# ---------------------------------------------------------------------------

def test_custom_format_confirm_success(client, db_session, test_account):
    """Verify POST /upload/confirm persists normalized transactions using a custom format UUID."""
    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="Custom Bank Export",
        date_column="TxDate",
        description_column="Payee",
        amount_column="NetAmt",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column=None,
    )

    csv_content = (
        "TxDate,Payee,NetAmt\n"
        "2026-09-10,Grocery Store,85.20\n"
        "2026-09-11,Gas Station,42.00\n"
    )
    files = {"file": ("bank.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": str(custom_format.id)}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()

    assert res["imported"] == 2
    assert res["skipped"] == 0
    assert res["errors"] == []

    txns = (
        db_session.query(models.Transaction)
        .filter(models.Transaction.account_id == test_account.id)
        .order_by(models.Transaction.date.asc())
        .all()
    )
    assert len(txns) == 2
    assert txns[0].description == "Grocery Store"
    assert txns[0].amount == Decimal("85.20")
    assert txns[0].pending is False
    assert txns[1].description == "Gas Station"
    assert txns[1].amount == Decimal("42.00")
    assert txns[1].pending is False


# ---------------------------------------------------------------------------
# 3. Custom Sign Inversion Integration
# ---------------------------------------------------------------------------

def test_custom_format_sign_inversion_persisted(client, db_session, test_account):
    """
    Verify positive_is_inflow convention inverts signs in database persistence:
    Purchases (negative in source) become positive outflows.
    Deposits (positive in source) become negative inflows.
    """
    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="Credit Card Activity",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_inflow",
    )

    csv_content = (
        "Date,Description,Amount\n"
        "2026-09-01,Groceries,-85.00\n"
        "2026-09-02,Payroll,2500.00\n"
    )
    files = {"file": ("activity.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": str(custom_format.id)}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200

    txns = (
        db_session.query(models.Transaction)
        .filter(models.Transaction.account_id == test_account.id)
        .order_by(models.Transaction.date.asc())
        .all()
    )
    assert len(txns) == 2
    # Groceries: source -85.00 -> inverted to +85.00 (outflow)
    assert txns[0].description == "Groceries"
    assert txns[0].amount == Decimal("85.00")

    # Payroll: source +2500.00 -> inverted to -2500.00 (inflow)
    assert txns[1].description == "Payroll"
    assert txns[1].amount == Decimal("-2500.00")


# ---------------------------------------------------------------------------
# 4. Custom Status Mapping Integration
# ---------------------------------------------------------------------------

def test_custom_format_status_mapping(client, db_session, test_account):
    """
    Verify configured status column and posted token:
    - 'Cleared' matches status_posted_value 'cleared' (case-insensitive) -> pending=False
    - 'Pending' does not match -> pending=True
    """
    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="Status Aware Format",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        status_column="State",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_posted_value="cleared",
    )

    csv_content = (
        "Date,Description,Amount,State\n"
        "2026-09-01,One,10.00,Cleared\n"
        "2026-09-02,Two,20.00,Pending\n"
    )
    files = {"file": ("status.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": str(custom_format.id)}

    # Verify Preview
    resp_prev = client.post("/upload/preview", data=data, files=files)
    assert resp_prev.status_code == 200
    rows = resp_prev.json()["rows"]
    assert rows[0]["pending"] is False
    assert rows[1]["pending"] is True

    # Verify Confirm
    files["file"][1].seek(0)
    resp_conf = client.post("/upload/confirm", data=data, files=files)
    assert resp_conf.status_code == 200

    txns = (
        db_session.query(models.Transaction)
        .filter(models.Transaction.account_id == test_account.id)
        .order_by(models.Transaction.date.asc())
        .all()
    )
    assert txns[0].description == "One"
    assert txns[0].pending is False
    assert txns[1].description == "Two"
    assert txns[1].pending is True


# ---------------------------------------------------------------------------
# 5. Missing Custom Format UUID (404)
# ---------------------------------------------------------------------------

def test_missing_custom_uuid_returns_404(client, test_account):
    """Verify syntactically valid UUID that is absent from csv_formats returns HTTP 404."""
    nonexistent_format_id = uuid4()
    csv_content = "Date,Description,Amount\n2026-09-01,Test,10.00\n"
    files = {"file": ("data.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": str(nonexistent_format_id)}

    # Preview
    resp_prev = client.post("/upload/preview", data=data, files=files)
    assert resp_prev.status_code == 404
    assert resp_prev.json() == {"detail": f"Format {nonexistent_format_id} not found"}

    # Confirm
    files["file"][1].seek(0)
    resp_conf = client.post("/upload/confirm", data=data, files=files)
    assert resp_conf.status_code == 404
    assert resp_conf.json() == {"detail": f"Format {nonexistent_format_id} not found"}


# ---------------------------------------------------------------------------
# 6. Invalid Non-UUID Format String (400)
# ---------------------------------------------------------------------------

def test_invalid_non_uuid_format_returns_400(client, test_account):
    """Verify non-UUID unknown format string returns HTTP 400 with existing detail message."""
    csv_content = "Date,Description,Amount\n2026-09-01,Test,10.00\n"
    files = {"file": ("data.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": "not-a-real-format"}

    resp_prev = client.post("/upload/preview", data=data, files=files)
    assert resp_prev.status_code == 400
    assert resp_prev.json() == {"detail": "Unknown format 'not-a-real-format'. Available: ['usaa', 'discover']"}

    files["file"][1].seek(0)
    resp_conf = client.post("/upload/confirm", data=data, files=files)
    assert resp_conf.status_code == 400
    assert resp_conf.json() == {"detail": "Unknown format 'not-a-real-format'. Available: ['usaa', 'discover']"}


# ---------------------------------------------------------------------------
# 7. Missing Required Custom Header
# ---------------------------------------------------------------------------

def test_missing_required_custom_header(client, db_session, test_account):
    """
    Verify missing required custom header returns:
    - HTTP 422 in Confirm with 'Missing columns: ...'
    - HTTP 200 in Preview with row-level parse_error
    """
    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="Rigid Format",
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Value",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
    )

    # Missing 'Memo' column
    csv_missing = (
        "Posting Date,Description,Value\n"
        "09/01/2026,Store,10.00\n"
    )
    files = {"file": ("bad_headers.csv", BytesIO(csv_missing.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": str(custom_format.id)}

    # Preview: captured in row parse_error
    resp_prev = client.post("/upload/preview", data=data, files=files)
    assert resp_prev.status_code == 200
    res_prev = resp_prev.json()
    assert res_prev["valid_rows"] == 0
    assert res_prev["error_rows"] == 1
    assert "Missing columns: ['Memo']" in res_prev["rows"][0]["parse_error"]

    # Confirm: rejected as 422
    files["file"][1].seek(0)
    resp_conf = client.post("/upload/confirm", data=data, files=files)
    assert resp_conf.status_code == 422
    assert resp_conf.json() == {"detail": "Missing columns: ['Memo']"}


# ---------------------------------------------------------------------------
# 8. Malformed Row Tolerant Ingestion in Confirm
# ---------------------------------------------------------------------------

def test_malformed_row_tolerant_confirm(client, db_session, test_account):
    """
    Verify tolerant parsing during Confirm:
    Valid rows are imported, malformed row is captured in errors, file is not wholly aborted.
    """
    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="Tolerant Format",
        date_column="Date",
        description_column="Desc",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )

    csv_content = (
        "Date,Desc,Amount\n"
        "2026-09-01,Valid Row 1,15.00\n"
        "not-a-date,Bad Date Row,25.00\n"
        "2026-09-03,Valid Row 2,35.00\n"
    )
    files = {"file": ("data.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": str(custom_format.id)}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()

    assert res["imported"] == 2
    assert res["skipped"] == 0
    assert len(res["errors"]) == 1
    assert "Row 2: " in res["errors"][0]

    # Verify only the 2 valid transactions exist in DB
    txns = db_session.query(models.Transaction).filter_by(account_id=test_account.id).all()
    assert len(txns) == 2


# ---------------------------------------------------------------------------
# 9. Duplicate Transaction Skipping on Custom Format Re-Import
# ---------------------------------------------------------------------------

def test_duplicate_import_deduplication(client, db_session, test_account):
    """Verify second import of same custom-format statement skips existing identical transactions."""
    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="Dedupe Format",
        date_column="Date",
        description_column="Desc",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )

    csv_content = (
        "Date,Desc,Amount\n"
        "2026-09-01,STORE A,12.00\n"
        "2026-09-02,STORE B,18.00\n"
    )
    files1 = {"file": ("data.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": str(custom_format.id)}

    # Pass 1: imports both rows
    resp1 = client.post("/upload/confirm", data=data, files=files1)
    assert resp1.status_code == 200
    res1 = resp1.json()
    assert res1["imported"] == 2
    assert res1["skipped"] == 0

    # Pass 2: skips both rows as duplicates
    files2 = {"file": ("data.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp2 = client.post("/upload/confirm", data=data, files=files2)
    assert resp2.status_code == 200
    res2 = resp2.json()
    assert res2["imported"] == 0
    assert res2["skipped"] == 2
    assert res2["errors"] == []


# ---------------------------------------------------------------------------
# 10. Validation Precedence (Account Check Precedes Format Resolution)
# ---------------------------------------------------------------------------

def test_validation_precedence_account_before_format(client):
    """
    Verify account verification executes before format resolution:
    Missing Account (404) takes precedence over invalid format or missing custom format.
    """
    missing_account_id = uuid4()
    missing_format_uuid = uuid4()

    csv_content = "Date,Description,Amount\n2026-09-01,Test,10.00\n"
    files = {"file": ("data.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    # Case A: Missing Account + Missing Custom UUID -> Account 404 wins
    data_a = {"account_id": str(missing_account_id), "format": str(missing_format_uuid)}
    resp_a_prev = client.post("/upload/preview", data=data_a, files=files)
    assert resp_a_prev.status_code == 404
    assert resp_a_prev.json() == {"detail": f"Account {missing_account_id} not found"}

    files["file"][1].seek(0)
    resp_a_conf = client.post("/upload/confirm", data=data_a, files=files)
    assert resp_a_conf.status_code == 404
    assert resp_a_conf.json() == {"detail": f"Account {missing_account_id} not found"}

    # Case B: Missing Account + Invalid String Format -> Account 404 wins
    data_b = {"account_id": str(missing_account_id), "format": "invalid_string_format"}
    files["file"][1].seek(0)
    resp_b_prev = client.post("/upload/preview", data=data_b, files=files)
    assert resp_b_prev.status_code == 404
    assert resp_b_prev.json() == {"detail": f"Account {missing_account_id} not found"}

    files["file"][1].seek(0)
    resp_b_conf = client.post("/upload/confirm", data=data_b, files=files)
    assert resp_b_conf.status_code == 404
    assert resp_b_conf.json() == {"detail": f"Account {missing_account_id} not found"}


# ---------------------------------------------------------------------------
# 11. No Auto-Detection in Preview or Confirm
# ---------------------------------------------------------------------------

def test_preview_and_confirm_do_not_call_detect_csv_format(client, db_session, test_account, monkeypatch):
    """
    Verify that Preview and Confirm use the explicit format identifier directly
    and do NOT invoke detect_csv_format.
    """
    mock_detect = MagicMock(side_effect=AssertionError("detect_csv_format should not be called!"))
    monkeypatch.setattr("backend.bank_statement_loader.detect_csv_format", mock_detect)

    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="Explicit Format",
        date_column="Date",
        description_column="Desc",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )

    csv_content = "Date,Desc,Amount\n2026-09-01,Item,10.00\n"
    files = {"file": ("data.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(test_account.id), "format": str(custom_format.id)}

    # Preview succeeds without calling detect_csv_format
    resp_prev = client.post("/upload/preview", data=data, files=files)
    assert resp_prev.status_code == 200

    # Confirm succeeds without calling detect_csv_format
    files["file"][1].seek(0)
    resp_conf = client.post("/upload/confirm", data=data, files=files)
    assert resp_conf.status_code == 200

    # Built-in format also succeeds without calling detect_csv_format
    files["file"][1].seek(0)
    usaa_csv = "Date,Description,Category,Amount,Status\n2026-09-01,Item,Food,-10.00,posted\n"
    files_usaa = {"file": ("usaa.csv", BytesIO(usaa_csv.encode("utf-8")), "text/csv")}
    data_usaa = {"account_id": str(test_account.id), "format": "usaa"}

    resp_usaa_prev = client.post("/upload/preview", data=data_usaa, files=files_usaa)
    assert resp_usaa_prev.status_code == 200

    files_usaa["file"][1].seek(0)
    resp_usaa_conf = client.post("/upload/confirm", data=data_usaa, files=files_usaa)
    assert resp_usaa_conf.status_code == 200

    mock_detect.assert_not_called()
