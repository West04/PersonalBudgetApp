"""
Characterization tests for POST /upload/preview.

Freezes existing behavior of:
- backend/routers/upload.py::preview_csv
- backend/routers/upload.py::_verify_account
- Interactions with BankStatementLoader and schemas.CSVPreviewResponse
"""

from decimal import Decimal
from io import BytesIO
from uuid import uuid4
import pytest

from backend import models


# ---------------------------------------------------------------------------
# Account Verification & Routing Characterization
# ---------------------------------------------------------------------------

def test_upload_preview_nonexistent_account_404(client):
    """
    Verify POST /upload/preview returns HTTP 404 with exact detail
    when the target account UUID does not exist.
    """
    non_existent_id = uuid4()
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,GROCERY STORE,Food,-45.50,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(non_existent_id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 404
    assert resp.json() == {"detail": f"Account {non_existent_id} not found"}


def test_upload_preview_nonexistent_account_precedes_format_validation(client):
    """
    Verify account verification executes before format registry lookup:
    When both the account is nonexistent and the format is invalid,
    the endpoint returns HTTP 404 (not HTTP 400).
    """
    non_existent_id = uuid4()
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,GROCERY STORE,Food,-45.50,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(non_existent_id), "format": "invalid_format"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 404
    assert resp.json() == {"detail": f"Account {non_existent_id} not found"}


def test_upload_preview_inactive_account_allowed(client, db_session):
    """
    Verify POST /upload/preview permits previewing for an inactive account
    (is_active == False is not restricted).
    """
    account = models.Account(
        name="Old Inactive Checking",
        type="depository",
        is_active=False,
        current_balance=Decimal("100.00"),
        starting_balance=Decimal("100.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,OLD STORE,Shopping,-12.34,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["total_rows"] == 1
    assert res["valid_rows"] == 1
    assert res["error_rows"] == 0
    assert len(res["rows"]) == 1
    assert res["rows"][0]["description"] == "OLD STORE"
    assert res["rows"][0]["amount"] == "12.34"


@pytest.mark.parametrize("account_type", ["depository", "credit", "investment", "loan"])
def test_upload_preview_account_types_allowed(client, db_session, account_type):
    """
    Verify POST /upload/preview permits any valid account type;
    no type-filtering restrictions are applied.
    """
    account = models.Account(
        name=f"Test {account_type.capitalize()}",
        type=account_type,
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,PAYMENT,Finance,-50.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    assert resp.json()["valid_rows"] == 1


def test_upload_preview_invalid_account_uuid_422(client):
    """
    Verify FastAPI request validation blocks non-UUID account_id values with HTTP 422.
    """
    csv_content = "Date,Description,Category,Amount,Status\n"
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": "not-a-valid-uuid", "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 422


def test_upload_preview_missing_account_id_422(client):
    """
    Verify missing account_id field returns HTTP 422.
    """
    csv_content = "Date,Description,Category,Amount,Status\n"
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Format Handling Characterization
# ---------------------------------------------------------------------------

def test_upload_preview_unknown_format_400(client, db_session):
    """
    Verify POST /upload/preview returns HTTP 400 with exact detail
    when format string is not in LOADER_REGISTRY.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = "Date,Description,Category,Amount,Status\n"
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "chase"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Unknown format 'chase'. Available: ['usaa', 'discover']"}


def test_upload_preview_format_case_insensitive_success(client, db_session):
    """
    Verify loader selection is case-insensitive (e.g. 'USAA' and 'Discover').
    """
    account = models.Account(
        name="Test Checking",
        type="depository",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,COFFEE,Food,-4.50,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "USAA"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    assert resp.json()["valid_rows"] == 1


def test_upload_preview_missing_format_422(client, db_session):
    """
    Verify missing format form parameter returns HTTP 422.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = "Date,Description,Category,Amount,Status\n"
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id)}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 422


def test_upload_preview_missing_file_422(client, db_session):
    """
    Verify request with missing file returns HTTP 422.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    data = {"account_id": str(account.id), "format": "usaa"}
    resp = client.post("/upload/preview", data=data)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Valid Parsing Characterization (USAA & Discover)
# ---------------------------------------------------------------------------

def test_upload_preview_valid_usaa_success(client, db_session):
    """
    Verify valid USAA statement preview:
    - Negates negative purchase amounts to positive outflows (+X).
    - Preserves positive deposit amounts as negative inflows (-X).
    - Maps 'posted' status to pending=False; other status to pending=True.
    - Sets ISO transaction_date string (YYYY-MM-DD).
    - Sets 1-indexed row_number.
    """
    account = models.Account(
        name="USAA Checking",
        type="depository",
        is_active=True,
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("1000.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,GROCERY STORE,Food,-54.25,posted\n"
        "2026-06-02,PAYROLL DIRECT DEP,Income,1200.00,posted\n"
        "2026-06-03,GAS STATION,Auto,-30.00,pending\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()

    assert res["total_rows"] == 3
    assert res["valid_rows"] == 3
    assert res["error_rows"] == 0

    rows = res["rows"]
    assert len(rows) == 3

    # Row 1: Purchase (-54.25 inverted to 54.25, posted -> pending=False)
    assert rows[0]["row_number"] == 1
    assert rows[0]["transaction_date"] == "2026-06-01"
    assert rows[0]["description"] == "GROCERY STORE"
    assert rows[0]["amount"] == "54.25"
    assert rows[0]["pending"] is False
    assert rows[0]["parse_error"] is None

    # Row 2: Deposit (1200.00 inverted to -1200.00, posted -> pending=False)
    assert rows[1]["row_number"] == 2
    assert rows[1]["transaction_date"] == "2026-06-02"
    assert rows[1]["description"] == "PAYROLL DIRECT DEP"
    assert rows[1]["amount"] == "-1200.00"
    assert rows[1]["pending"] is False
    assert rows[1]["parse_error"] is None

    # Row 3: Pending purchase (-30.00 inverted to 30.00, pending status -> pending=True)
    assert rows[2]["row_number"] == 3
    assert rows[2]["transaction_date"] == "2026-06-03"
    assert rows[2]["description"] == "GAS STATION"
    assert rows[2]["amount"] == "30.00"
    assert rows[2]["pending"] is True
    assert rows[2]["parse_error"] is None


def test_upload_preview_valid_discover_success(client, db_session):
    """
    Verify valid Discover statement preview:
    - Parses date from %m/%d/%Y to ISO format %Y-%m-%d.
    - Preserves positive charges as positive outflows (+X).
    - Preserves negative payments/credits as negative inflows (-X).
    - Always sets pending=False.
    """
    account = models.Account(
        name="Discover Card",
        type="credit",
        is_active=True,
        current_balance=Decimal("500.00"),
        starting_balance=Decimal("500.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "06/01/2026,TARGET STORE,78.90,Merchandise\n"
        "06/02/2026,DIRECTPAY FULL,-200.00,Payments\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "discover"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()

    assert res["total_rows"] == 2
    assert res["valid_rows"] == 2
    assert res["error_rows"] == 0

    rows = res["rows"]
    # Row 1: Charge
    assert rows[0]["row_number"] == 1
    assert rows[0]["transaction_date"] == "2026-06-01"
    assert rows[0]["description"] == "TARGET STORE"
    assert rows[0]["amount"] == "78.90"
    assert rows[0]["pending"] is False
    assert rows[0]["parse_error"] is None

    # Row 2: Payment
    assert rows[1]["row_number"] == 2
    assert rows[1]["transaction_date"] == "2026-06-02"
    assert rows[1]["description"] == "DIRECTPAY FULL"
    assert rows[1]["amount"] == "-200.00"
    assert rows[1]["pending"] is False
    assert rows[1]["parse_error"] is None


# ---------------------------------------------------------------------------
# Empty & Malformed CSV Characterization
# ---------------------------------------------------------------------------

def test_upload_preview_empty_file_200(client, db_session):
    """
    Verify 0-byte CSV upload returns HTTP 200 with zero rows.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    files = {"file": ("empty.csv", BytesIO(b""), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    assert resp.json() == {
        "rows": [],
        "total_rows": 0,
        "valid_rows": 0,
        "error_rows": 0,
    }


def test_upload_preview_headers_only_file_200(client, db_session):
    """
    Verify valid CSV with headers but no transaction rows returns HTTP 200 with zero rows.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = "Date,Description,Category,Amount,Status\n"
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    assert resp.json() == {
        "rows": [],
        "total_rows": 0,
        "valid_rows": 0,
        "error_rows": 0,
    }


def test_upload_preview_missing_headers_row_errors_200(client, db_session):
    """
    Verify CSV with wrong/missing header columns does NOT raise an HTTP error in Preview;
    instead, rows fail column normalization and are reported in error_rows with HTTP 200.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    # Missing Category and Status headers for USAA
    csv_content = (
        "Date,Description,Amount\n"
        "2026-06-01,SOME STORE,-10.00\n"
    )
    files = {"file": ("bad_headers.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["total_rows"] == 1
    assert res["valid_rows"] == 0
    assert res["error_rows"] == 1

    err_row = res["rows"][0]
    assert err_row["row_number"] == 1
    assert "Missing columns" in err_row["parse_error"]
    assert err_row["amount"] is None
    assert err_row["transaction_date"] is None


def test_upload_preview_mixed_valid_and_invalid_rows_200(client, db_session):
    """
    Verify per-row error capture in Preview:
    When some rows are valid and some fail parsing, HTTP 200 is returned,
    valid rows populate transaction fields, and invalid rows populate parse_error.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,VALID ROW 1,Food,-15.00,posted\n"
        "invalid-date,BROKEN ROW,Food,-20.00,posted\n"
        "2026-06-03,VALID ROW 2,Auto,-35.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()

    assert res["total_rows"] == 3
    assert res["valid_rows"] == 2
    assert res["error_rows"] == 1

    rows = res["rows"]
    # Row 1: Valid
    assert rows[0]["row_number"] == 1
    assert rows[0]["description"] == "VALID ROW 1"
    assert rows[0]["parse_error"] is None

    # Row 2: Failed date parsing
    assert rows[1]["row_number"] == 2
    assert rows[1]["parse_error"] is not None
    assert "time data 'invalid-date' does not match format '%Y-%m-%d'" in rows[1]["parse_error"]
    assert rows[1]["amount"] is None

    # Row 3: Valid
    assert rows[2]["row_number"] == 3
    assert rows[2]["description"] == "VALID ROW 2"
    assert rows[2]["parse_error"] is None


def test_upload_preview_all_rows_invalid_200(client, db_session):
    """
    Verify structurally readable CSV where all data rows fail parsing
    returns HTTP 200 with total_rows == error_rows and valid_rows == 0.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        is_active=True,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,BAD ROW 1,Food,NOT_AN_AMOUNT,posted\n"
        "2026-06-02,BAD ROW 2,Food,ALSO_BAD,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()

    assert res["total_rows"] == 2
    assert res["valid_rows"] == 0
    assert res["error_rows"] == 2
    assert res["rows"][0]["parse_error"] is not None
    assert res["rows"][1]["parse_error"] is not None


# ---------------------------------------------------------------------------
# Side Effect & Confirm Isolation Characterization
# ---------------------------------------------------------------------------

def test_upload_preview_read_only_no_db_side_effects(client, db_session):
    """
    Verify POST /upload/preview is strictly read-only:
    - Zero transactions are written to the database.
    - Target account balances and fields are untouched.
    - No changes persist.
    """
    account = models.Account(
        name="Isolated Checking",
        type="depository",
        is_active=True,
        current_balance=Decimal("500.00"),
        starting_balance=Decimal("500.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    initial_tx_count = db_session.query(models.Transaction).count()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE 1,Food,-10.00,posted\n"
        "2026-06-02,STORE 2,Food,-20.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/preview", data=data, files=files)
    assert resp.status_code == 200
    assert resp.json()["valid_rows"] == 2

    # Assert no DB writes occurred
    final_tx_count = db_session.query(models.Transaction).count()
    assert final_tx_count == initial_tx_count

    refreshed_account = db_session.query(models.Account).filter(models.Account.id == account.id).first()
    assert refreshed_account.current_balance == Decimal("500.00")
    assert refreshed_account.starting_balance == Decimal("500.00")
