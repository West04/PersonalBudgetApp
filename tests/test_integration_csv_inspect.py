import io
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4
import pytest
from sqlalchemy import text

from backend import models, schemas
from backend.access import csv_format_access


@pytest.fixture(autouse=True)
def clean_database(db_session):
    """Ensure custom formats and transactions are wiped clean before and after each test."""
    db_session.execute(text("TRUNCATE TABLE transactions CASCADE;"))
    db_session.execute(text("TRUNCATE TABLE csv_formats CASCADE;"))
    db_session.commit()
    yield
    db_session.execute(text("TRUNCATE TABLE transactions CASCADE;"))
    db_session.execute(text("TRUNCATE TABLE csv_formats CASCADE;"))
    db_session.commit()


# ---------------------------------------------------------------------------
# 1. Unknown Format & Sample Rows
# ---------------------------------------------------------------------------

def test_inspect_unknown_format_returns_200_with_samples(client):
    """
    Verify upload of a CSV with unrecognized headers returns:
    - HTTP 200
    - status = 'unknown'
    - detected_format = None
    - matches = []
    - headers and sample rows returned faithfully
    """
    csv_content = (
        "When,Merchant,Value\n"
        "2026-09-01,Coffee Shop,  4.50\n"
        "2026-09-02,Bookstore,25.00\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "unknown"
    assert data["detected_format"] is None
    assert data["matches"] == []
    assert data["headers"] == ["When", "Merchant", "Value"]
    assert len(data["sample_rows"]) == 2
    assert data["sample_rows"][0] == ["2026-09-01", "Coffee Shop", "  4.50"]
    assert data["sample_rows"][1] == ["2026-09-02", "Bookstore", "25.00"]


def test_inspect_sample_rows_capped_at_three(client):
    """Verify sample_rows is bounded to at most 3 data rows even if the file contains more."""
    csv_content = (
        "When,Merchant,Value\n"
        "2026-09-01,Row 1,1.00\n"
        "2026-09-02,Row 2,2.00\n"
        "2026-09-03,Row 3,3.00\n"
        "2026-09-04,Row 4,4.00\n"
        "2026-09-05,Row 5,5.00\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sample_rows"]) == 3
    assert data["sample_rows"][0] == ["2026-09-01", "Row 1", "1.00"]
    assert data["sample_rows"][1] == ["2026-09-02", "Row 2", "2.00"]
    assert data["sample_rows"][2] == ["2026-09-03", "Row 3", "3.00"]


# ---------------------------------------------------------------------------
# 2. Built-in Format Detection: USAA & Discover
# ---------------------------------------------------------------------------

def test_inspect_detects_usaa(client):
    """Verify exact USAA headers detect USAA format."""
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,GROCERY STORE,Food,-54.20,posted\n"
    )
    files = {"file": ("usaa.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "detected"
    assert data["detected_format"] == {"identifier": "usaa", "name": "USAA"}
    assert len(data["matches"]) == 1
    assert data["matches"][0] == {"identifier": "usaa", "name": "USAA"}
    assert data["headers"] == ["Date", "Description", "Category", "Amount", "Status"]


def test_inspect_detects_discover(client):
    """Verify exact Discover headers detect Discover format."""
    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "06/01/2026,ONLINE PURCHASE,45.00,Merchandise\n"
    )
    files = {"file": ("discover.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "detected"
    assert data["detected_format"] == {"identifier": "discover", "name": "Discover"}
    assert len(data["matches"]) == 1
    assert data["matches"][0] == {"identifier": "discover", "name": "Discover"}


# ---------------------------------------------------------------------------
# 3. Persisted Custom Format Detection
# ---------------------------------------------------------------------------

def test_inspect_detects_persisted_custom_format(client, db_session):
    """Verify uploaded file matching a persisted custom format detects it by UUID."""
    custom = csv_format_access.create_custom_format(
        db=db_session,
        name="Credit Union Checking",
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Value",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_inflow",
    )

    csv_content = (
        "Posting Date,Memo,Value\n"
        "09/01/2026,Coffee,6.25\n"
    )
    files = {"file": ("cu.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "detected"
    assert data["detected_format"] == {
        "identifier": str(custom.id),
        "name": "Credit Union Checking",
    }
    assert len(data["matches"]) == 1
    assert data["matches"][0] == {
        "identifier": str(custom.id),
        "name": "Credit Union Checking",
    }


def test_inspect_custom_format_with_status_column_requirement(client, db_session):
    """
    Verify a custom format with a status column requires that status column in headers:
    - Without status column: does not match (unknown)
    - With status column: matches (detected)
    """
    custom = csv_format_access.create_custom_format(
        db=db_session,
        name="Format With Status",
        date_column="Date",
        description_column="Memo",
        amount_column="Amount",
        status_column="State",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_posted_value="cleared",
    )

    # Missing 'State' header
    csv_no_status = "Date,Memo,Amount\n2026-09-01,Test,10.00\n"
    resp1 = client.post(
        "/upload/inspect",
        files={"file": ("no_status.csv", BytesIO(csv_no_status.encode("utf-8")), "text/csv")},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "unknown"

    # Including 'State' header
    csv_with_status = "Date,Memo,Amount,State\n2026-09-01,Test,10.00,cleared\n"
    resp2 = client.post(
        "/upload/inspect",
        files={"file": ("with_status.csv", BytesIO(csv_with_status.encode("utf-8")), "text/csv")},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "detected"
    assert resp2.json()["detected_format"]["identifier"] == str(custom.id)


# ---------------------------------------------------------------------------
# 4. Extra Columns (Subset Matching)
# ---------------------------------------------------------------------------

def test_inspect_allows_extra_columns_for_builtin_and_custom(client, db_session):
    """
    Verify format detection is subset-based: files with extra unmapped columns
    still detect the matching format.
    """
    custom = csv_format_access.create_custom_format(
        db=db_session,
        name="Simple Bank",
        date_column="TxDate",
        description_column="Payee",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )

    # Extra columns: 'CheckNumber', 'Balance'
    csv_content = (
        "TxDate,CheckNumber,Payee,Amount,Balance\n"
        "2026-09-01,101,Electric Co,85.20,1200.50\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "detected"
    assert data["detected_format"]["identifier"] == str(custom.id)


# ---------------------------------------------------------------------------
# 5. Ambiguity Handling: Built-in vs Custom & Custom vs Custom
# ---------------------------------------------------------------------------

def test_inspect_ambiguous_builtin_and_custom_no_ranking(client, db_session):
    """
    Verify when an uploaded CSV satisfies both a built-in format and a custom format,
    status is 'ambiguous', detected_format is None, and both matches are returned
    without ranking or preferring built-in.
    """
    # Create custom format whose required headers are a subset of USAA's headers
    custom = csv_format_access.create_custom_format(
        db=db_session,
        name="Subset USAA Custom",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )

    # Full USAA headers satisfy both USAA and custom
    usaa_csv = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE,Food,-10.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(usaa_csv.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ambiguous"
    assert data["detected_format"] is None
    # BUILTIN_FORMAT_MATCHES comes first, then custom
    match_ids = [m["identifier"] for m in data["matches"]]
    assert "usaa" in match_ids
    assert str(custom.id) in match_ids
    assert match_ids.index("usaa") < match_ids.index(str(custom.id))


def test_inspect_ambiguous_two_custom_formats_preserves_order(client, db_session):
    """
    Verify when an uploaded CSV satisfies two custom formats,
    status is 'ambiguous' and candidates are ordered deterministically by list_custom_formats.
    """
    custom_b = csv_format_access.create_custom_format(
        db=db_session,
        name="Beta Format",
        date_column="TxDate",
        description_column="TxDesc",
        amount_column="TxAmt",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    custom_a = csv_format_access.create_custom_format(
        db=db_session,
        name="Alpha Format",
        date_column="TxDate",
        description_column="TxDesc",
        amount_column="TxAmt",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
    )

    csv_content = (
        "TxDate,TxDesc,TxAmt\n"
        "2026-09-01,Test,15.00\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ambiguous"
    assert data["detected_format"] is None
    # list_custom_formats orders by lower(name) asc: Alpha Format then Beta Format
    assert len(data["matches"]) == 2
    assert data["matches"][0]["identifier"] == str(custom_a.id)
    assert data["matches"][1]["identifier"] == str(custom_b.id)


# ---------------------------------------------------------------------------
# 6. Header Normalization: Case, Whitespace, Punctuation & BOM
# ---------------------------------------------------------------------------

def test_inspect_header_case_sensitivity(client):
    """Verify header detection is case-sensitive: lowercase 'date' does not match USAA 'Date'."""
    csv_content = (
        "date,description,category,amount,status\n"
        "2026-06-01,STORE,Food,-10.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    assert resp.json()["status"] == "unknown"


def test_inspect_header_whitespace_sensitivity(client):
    """Verify header detection is whitespace-sensitive: padded ' Date ' does not match USAA 'Date'."""
    csv_content = (
        " Date , Description , Category , Amount , Status \n"
        "2026-06-01,STORE,Food,-10.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    assert resp.json()["status"] == "unknown"


def test_inspect_utf8_bom_stripped_and_matches_first_header(client):
    """
    Verify UTF-8 BOM is transparently decoded by utf-8-sig so the first column
    matches without corruption.
    """
    csv_text = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE,Food,-10.00,posted\n"
    )
    bom_bytes = b"\xef\xbb\xbf" + csv_text.encode("utf-8")
    files = {"file": ("bom.csv", BytesIO(bom_bytes), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "detected"
    assert data["detected_format"]["identifier"] == "usaa"
    assert data["headers"][0] == "Date"


# ---------------------------------------------------------------------------
# 7. Structural Edge Cases: Header-Only, Empty, Invalid UTF-8
# ---------------------------------------------------------------------------

def test_inspect_header_only_csv_runs_detection_with_empty_samples(client):
    """
    Verify valid CSV with headers but no data rows runs detection normally
    and returns empty sample_rows.
    """
    csv_content = "Date,Description,Category,Amount,Status\n"
    files = {"file": ("header_only.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "detected"
    assert data["detected_format"]["identifier"] == "usaa"
    assert data["headers"] == ["Date", "Description", "Category", "Amount", "Status"]
    assert data["sample_rows"] == []


def test_inspect_empty_file_returns_422(client):
    """Verify zero-byte upload returns HTTP 422 client error."""
    files = {"file": ("empty.csv", BytesIO(b""), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 422
    assert "empty" in resp.json()["detail"].lower()


def test_inspect_whitespace_only_file_returns_422(client):
    """Verify whitespace-only CSV returns HTTP 422 client error."""
    files = {"file": ("blank.csv", BytesIO(b"   \n\n\t  \n"), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 422
    assert "empty" in resp.json()["detail"].lower() or "header" in resp.json()["detail"].lower()


def test_inspect_invalid_utf8_returns_422(client):
    """Verify invalid UTF-8 bytes return HTTP 422 rather than leaking a 500 error."""
    invalid_bytes = b"\xff\xfe\x00\x00Date,Amount\n2026-01-01,10\n"
    files = {"file": ("binary.csv", BytesIO(invalid_bytes), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 422
    assert "decode" in resp.json()["detail"].lower() or "utf-8" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 8. Boundary Invariants: No Account, No Loader Resolution, No Writes
# ---------------------------------------------------------------------------

def test_inspect_does_not_require_account_or_query_accounts(client, db_session):
    """
    Verify /upload/inspect functions with zero accounts in the database
    and does not accept or query account_id.
    """
    # Ensure zero accounts exist
    assert db_session.query(models.Account).count() == 0

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE,Food,-10.00,posted\n"
    )
    files = {"file": ("usaa.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    with patch("backend.access.account_access.get_account_by_id") as mock_get_account:
        resp = client.post("/upload/inspect", files=files)
        assert resp.status_code == 200
        mock_get_account.assert_not_called()


def test_inspect_does_not_invoke_parsers_managers_or_loaders(client):
    """
    Architectural invariant: Verify /upload/inspect does NOT invoke:
    - _resolve_statement_loader
    - MappedStatementLoader
    - USAALoader.transform_row
    - DiscoverLoader.transform_row
    - CSVImportManager.confirm_csv_import
    """
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE,Food,-10.00,posted\n"
    )
    files = {"file": ("usaa.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    with patch("backend.routers.upload._resolve_statement_loader") as mock_resolve, \
         patch("backend.bank_statement_loader.USAALoader.transform_row") as mock_usaa_transform, \
         patch("backend.bank_statement_loader.DiscoverLoader.transform_row") as mock_disc_transform, \
         patch("backend.bank_statement_loader.MappedStatementLoader.transform_row") as mock_mapped_transform, \
         patch("backend.managers.csv_import_manager.confirm_csv_import") as mock_confirm:

        resp = client.post("/upload/inspect", files=files)
        assert resp.status_code == 200

        mock_resolve.assert_not_called()
        mock_usaa_transform.assert_not_called()
        mock_disc_transform.assert_not_called()
        mock_mapped_transform.assert_not_called()
        mock_confirm.assert_not_called()


def test_inspect_performs_zero_database_mutations(client, db_session):
    """
    Verify /upload/inspect creates no transactions, stages no rows,
    and commits no records to the database.
    """
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE,Food,-10.00,posted\n"
    )
    files = {"file": ("usaa.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200

    assert db_session.query(models.Transaction).count() == 0
    assert db_session.query(models.CSVFormat).count() == 0


# ---------------------------------------------------------------------------
# 9. Positional Sample Representation: Duplicate Headers & Ragged Rows
# ---------------------------------------------------------------------------

def test_inspect_duplicate_headers_preserves_all_cells(client):
    """
    Verify when a CSV contains duplicate header names,
    all cells across all columns are preserved positionally
    and no cells are lost to dictionary key collisions.
    """
    csv_content = (
        "Amount,Amount,Description\n"
        "10.00,20.00,Coffee\n"
    )
    files = {"file": ("dup.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["headers"] == ["Amount", "Amount", "Description"]
    assert data["sample_rows"] == [["10.00", "20.00", "Coffee"]]
    assert data["status"] == "unknown"


def test_inspect_ragged_rows_preserved_without_truncation_or_padding(client):
    """
    Verify short and long rows in a ragged CSV are preserved exactly
    as yielded by csv.reader without synthetic padding or truncation.
    """
    # Short row (2 cells for 3 headers) followed by long row (4 cells for 3 headers)
    csv_content = (
        "A,B,C\n"
        "1,2\n"
        "1,2,3,4\n"
    )
    files = {"file": ("ragged.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    resp = client.post("/upload/inspect", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["headers"] == ["A", "B", "C"]
    assert data["sample_rows"] == [
        ["1", "2"],
        ["1", "2", "3", "4"],
    ]
