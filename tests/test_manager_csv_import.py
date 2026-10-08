from dataclasses import FrozenInstanceError, is_dataclass
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest

from backend import models
from backend.access import csv_format_access
from backend.bank_statement_loader import BankStatementLoader, ParsedStatement, USAALoader, MappedStatementLoader
from backend.managers.csv_import_manager import (
    CSVImportAccountNotFoundError,
    CSVImportFormatNotFoundError,
    CSVImportParseError,
    CSVImportSummary,
    CSVImportUnknownFormatError,
    CSVInspectError,
    CSVPreviewRow,
    CSVPreviewSummary,
    _resolve_statement_loader,
    confirm_csv_import,
    inspect_csv_upload,
    preview_csv_import,
)
from sqlalchemy import text
from backend.schemas import TransactionCreate


@pytest.fixture(autouse=True)
def clean_csv_formats(db_session):
    """Ensure csv_formats table is clean before and after each test."""
    db_session.execute(text("TRUNCATE TABLE csv_formats CASCADE;"))
    db_session.commit()
    yield
    db_session.execute(text("TRUNCATE TABLE csv_formats CASCADE;"))
    db_session.commit()



# ---------------------------------------------------------------------------
# Account Validation Precedence
# ---------------------------------------------------------------------------

def test_manager_validation_order_mocked():
    """
    Verify validation precedence using controlled mocks:
    1. Account lookup occurs before format resolution and statement parsing.
    2. Missing account raises CSVImportAccountNotFoundError before loader resolution.
    """
    db_mock = MagicMock()
    account_id = uuid4()
    raw_bytes = b"sample,csv,data"

    with patch("backend.access.account_access.get_account_by_id", return_value=None) as mock_get_account, \
         patch("backend.managers.csv_import_manager._resolve_statement_loader") as mock_resolve:
        with pytest.raises(CSVImportAccountNotFoundError, match=f"Account {account_id} not found"):
            confirm_csv_import(
                db=db_mock,
                account_id=account_id,
                format_identifier="usaa",
                raw_bytes=raw_bytes,
            )

        mock_get_account.assert_called_once_with(db_mock, account_id)
        mock_resolve.assert_not_called()


def test_manager_preview_validation_order_mocked():
    """
    Verify preview validation precedence:
    Account check precedes format resolution in preview_csv_import.
    """
    db_mock = MagicMock()
    account_id = uuid4()
    raw_bytes = b"sample,csv,data"

    with patch("backend.access.account_access.get_account_by_id", return_value=None) as mock_get_account, \
         patch("backend.managers.csv_import_manager._resolve_statement_loader") as mock_resolve:
        with pytest.raises(CSVImportAccountNotFoundError, match=f"Account {account_id} not found"):
            preview_csv_import(
                db=db_mock,
                account_id=account_id,
                format_identifier="invalid_format",
                raw_bytes=raw_bytes,
            )

        mock_get_account.assert_called_once_with(db_mock, account_id)
        mock_resolve.assert_not_called()


# ---------------------------------------------------------------------------
# Format Resolution
# ---------------------------------------------------------------------------

def test_manager_builtin_format_resolution(db_session):
    """
    Verify _resolve_statement_loader resolves built-in formats case-insensitively.
    """
    account_id = uuid4()
    loader_usaa = _resolve_statement_loader(db_session, account_id, "usaa")
    assert isinstance(loader_usaa, USAALoader)
    assert loader_usaa.account_id == account_id

    loader_usaa_upper = _resolve_statement_loader(db_session, account_id, "  USAA  ")
    assert isinstance(loader_usaa_upper, USAALoader)

    loader_discover = _resolve_statement_loader(db_session, account_id, "Discover")
    assert loader_discover.account_id == account_id


def test_manager_custom_format_resolution(db_session):
    """
    Verify _resolve_statement_loader resolves custom format UUIDs via csv_format_access.
    """
    account_id = uuid4()
    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="My Bank",
        date_column="Date",
        description_column="Desc",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )

    loader = _resolve_statement_loader(db_session, account_id, str(custom_format.id))
    assert isinstance(loader, MappedStatementLoader)
    assert loader.account_id == account_id
    assert loader.config.date_column == "Date"
    assert loader.config.description_column == "Desc"


def test_manager_missing_custom_format_raises_error(db_session):
    """
    Verify _resolve_statement_loader raises CSVImportFormatNotFoundError
    when a valid UUID is not found in csv_formats.
    """
    account_id = uuid4()
    missing_format_uuid = uuid4()

    with pytest.raises(CSVImportFormatNotFoundError, match=f"Format {missing_format_uuid} not found"):
        _resolve_statement_loader(db_session, account_id, str(missing_format_uuid))


def test_manager_unknown_format_string_raises_error(db_session):
    """
    Verify _resolve_statement_loader raises CSVImportUnknownFormatError
    when format string is neither built-in nor a valid UUID.
    """
    account_id = uuid4()

    with pytest.raises(CSVImportUnknownFormatError, match="Unknown format 'chase'. Available: \\['usaa', 'discover'\\]"):
        _resolve_statement_loader(db_session, account_id, "chase")


# ---------------------------------------------------------------------------
# Preview Workflow
# ---------------------------------------------------------------------------

def test_manager_preview_success_utf8_sig(db_session):
    """
    Verify preview_csv_import parses UTF-8-SIG encoded bytes, produces 1-indexed rows,
    counts valid and error rows, and performs zero database mutations.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_data = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,COFFEE SHOP,Food,-4.50,posted\n"
        "2026-06-02,PAYROLL,Income,2500.00,posted\n"
    ).encode("utf-8-sig")

    preview = preview_csv_import(
        db=db_session,
        account_id=account.id,
        format_identifier="usaa",
        raw_bytes=csv_data,
    )

    assert preview.total_rows == 2
    assert preview.valid_rows == 2
    assert preview.error_rows == 0
    assert len(preview.rows) == 2

    # Row 1
    assert preview.rows[0].row_number == 1
    assert preview.rows[0].transaction_date == "2026-06-01"
    assert preview.rows[0].description == "COFFEE SHOP"
    assert preview.rows[0].amount == Decimal("4.50")
    assert preview.rows[0].pending is False
    assert preview.rows[0].parse_error is None

    # Row 2
    assert preview.rows[1].row_number == 2
    assert preview.rows[1].transaction_date == "2026-06-02"
    assert preview.rows[1].description == "PAYROLL"
    assert preview.rows[1].amount == Decimal("-2500.00")
    assert preview.rows[1].pending is False
    assert preview.rows[1].parse_error is None

    # Zero transactions created in DB
    tx_count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert tx_count == 0


def test_manager_preview_latin1_fallback(db_session):
    """
    Verify preview_csv_import falls back to latin-1 when utf-8-sig decoding fails.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    # 'Caf\xe9' is valid latin-1 but invalid utf-8
    csv_bytes = b"Date,Description,Category,Amount,Status\n2026-06-01,Caf\xe9,Food,-5.00,posted\n"

    preview = preview_csv_import(
        db=db_session,
        account_id=account.id,
        format_identifier="usaa",
        raw_bytes=csv_bytes,
    )

    assert preview.total_rows == 1
    assert preview.valid_rows == 1
    assert preview.rows[0].description == "Café"


def test_manager_preview_row_numbering_and_tolerant_errors(db_session):
    """
    Verify preview collects row errors without failing the batch, preserves 1-based
    row numbering, and correctly counts valid and error rows.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_data = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        "invalid-date,BAD ROW 2,Food,-20.00,posted\n"
        "2026-06-03,VALID ROW 3,Food,-30.00,posted\n"
    ).encode("utf-8")

    preview = preview_csv_import(
        db=db_session,
        account_id=account.id,
        format_identifier="usaa",
        raw_bytes=csv_data,
    )

    assert preview.total_rows == 3
    assert preview.valid_rows == 2
    assert preview.error_rows == 1

    assert preview.rows[0].row_number == 1
    assert preview.rows[0].parse_error is None

    assert preview.rows[1].row_number == 2
    assert preview.rows[1].parse_error is not None
    assert "invalid-date" in preview.rows[1].parse_error

    assert preview.rows[2].row_number == 3
    assert preview.rows[2].parse_error is None


# ---------------------------------------------------------------------------
# Confirm Workflow
# ---------------------------------------------------------------------------

def test_manager_parse_failure_raises_parse_error(db_session):
    """
    Verify valid account + invalid CSV bytes raises CSVImportParseError from loader in confirm.
    """
    account = models.Account(
        name="Test Acct",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    malformed_csv = b"BadHeader1,BadHeader2\n123,456\n"
    with pytest.raises(CSVImportParseError, match="Missing columns"):
        confirm_csv_import(
            db=db_session,
            account_id=account.id,
            format_identifier="usaa",
            raw_bytes=malformed_csv,
        )


def test_manager_successful_import_and_duplicate_skipping(db_session):
    """
    Verify confirm_csv_import end-to-end:
    - Normal import stages rows, increments imported, commits once.
    - Subsequent identical import increments skipped.
    """
    account = models.Account(
        name="USAA Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_data = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE A,Food,-15.00,posted\n"
        "2026-06-02,STORE B,Food,-25.00,posted\n"
    ).encode("utf-8")

    # Initial import: 2 imported, 0 skipped
    res1 = confirm_csv_import(
        db=db_session,
        account_id=account.id,
        format_identifier="usaa",
        raw_bytes=csv_data,
    )
    assert res1.imported == 2
    assert res1.skipped == 0
    assert res1.errors == ()

    # Re-import identical file: 0 imported, 2 skipped
    res2 = confirm_csv_import(
        db=db_session,
        account_id=account.id,
        format_identifier="usaa",
        raw_bytes=csv_data,
    )
    assert res2.imported == 0
    assert res2.skipped == 2
    assert res2.errors == ()


def test_manager_same_request_duplicates_both_imported(db_session):
    """
    Verify preserved invariant:
    Two identical rows in the same file are both imported (imported = 2, skipped = 0).
    """
    account = models.Account(
        name="Duplicate Acct",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_data = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,COFFEE,Food,-4.50,posted\n"
        "2026-06-01,COFFEE,Food,-4.50,posted\n"
    ).encode("utf-8")

    res = confirm_csv_import(
        db=db_session,
        account_id=account.id,
        format_identifier="usaa",
        raw_bytes=csv_data,
    )
    assert res.imported == 2
    assert res.skipped == 0
    assert res.errors == ()


def test_manager_row_level_exception_formatting_and_continuation(db_session):
    """
    Verify row-level exception handling:
    - Exceptions inside the row loop do not abort processing of subsequent rows.
    - Errors are formatted as: Row <date> '<description>': <exception>
    - Successfully staged rows are committed.
    """
    account = models.Account(
        name="Row Error Acct",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_data = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,FAIL_ME,Food,-10.00,posted\n"
        "2026-06-02,SUCCESS_ME,Food,-20.00,posted\n"
    ).encode("utf-8")

    from backend.access.transaction_access import stage_csv_import_transaction as real_stage

    def mock_stage(db, account_id, transaction_date, amount, description, **kwargs):
        if description == "FAIL_ME":
            raise ValueError("Staging exploded")
        return real_stage(db, account_id, transaction_date, amount, description, **kwargs)

    with patch("backend.access.transaction_access.stage_csv_import_transaction", side_effect=mock_stage):
        res = confirm_csv_import(
            db=db_session,
            account_id=account.id,
            format_identifier="usaa",
            raw_bytes=csv_data,
        )

    assert res.imported == 1
    assert res.skipped == 0
    assert len(res.errors) == 1
    assert res.errors[0] == "Row 2026-06-01 'FAIL_ME': Staging exploded"

    # Confirm the successful transaction was committed
    committed_txns = db_session.query(models.Transaction).filter(models.Transaction.account_id == account.id).all()
    assert len(committed_txns) == 1
    assert committed_txns[0].description == "SUCCESS_ME"


def test_manager_single_final_commit_after_all_rows(db_session):
    """
    Verify the manager performs exactly one final commit after all rows are processed,
    and not per-row.
    """
    account = models.Account(
        name="Commit Acct",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_data = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,ROW 1,Food,-10.00,posted\n"
        "2026-06-02,ROW 2,Food,-20.00,posted\n"
        "2026-06-03,ROW 3,Food,-30.00,posted\n"
    ).encode("utf-8")

    with patch.object(db_session, "commit", wraps=db_session.commit) as mock_commit:
        res = confirm_csv_import(
            db=db_session,
            account_id=account.id,
            format_identifier="usaa",
            raw_bytes=csv_data,
        )
        assert res.imported == 3
        # Exactly one commit for the entire 3-row import
        assert mock_commit.call_count == 1


def test_manager_commit_failure_propagates(db_session):
    """
    Verify commit failure propagates as an unhandled exception rather than
    being swallowed into the row errors list.
    """
    account = models.Account(
        name="Commit Fail Acct",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_data = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,ROW 1,Food,-10.00,posted\n"
    ).encode("utf-8")

    with patch.object(db_session, "commit", side_effect=RuntimeError("DB Commit Crash")):
        with pytest.raises(RuntimeError, match="DB Commit Crash"):
            confirm_csv_import(
                db=db_session,
                account_id=account.id,
                format_identifier="usaa",
                raw_bytes=csv_data,
            )


def test_manager_summary_dataclass_contract():
    """
    Verify CSVImportSummary, CSVPreviewSummary, CSVPreviewRow:
    - Are immutable frozen dataclasses.
    """
    summary = CSVImportSummary(imported=5, skipped=2, errors=("err1", "err2"))
    assert is_dataclass(summary)
    assert summary.imported == 5
    assert summary.skipped == 2
    assert summary.errors == ("err1", "err2")
    assert isinstance(summary.errors, tuple)

    with pytest.raises(FrozenInstanceError):
        summary.imported = 10  # type: ignore

    row = CSVPreviewRow(row_number=1, description="Test", amount=Decimal("10.00"))
    assert is_dataclass(row)
    with pytest.raises(FrozenInstanceError):
        row.description = "Changed"  # type: ignore

    prev = CSVPreviewSummary(rows=(row,), total_rows=1, valid_rows=1, error_rows=0)
    assert is_dataclass(prev)
    with pytest.raises(FrozenInstanceError):
        prev.total_rows = 5  # type: ignore


def test_manager_has_no_fastapi_or_pydantic_dependencies():
    """
    Architectural invariant:
    The manager must have no dependencies on FastAPI or Pydantic schemas.
    """
    import sys
    import backend.managers.csv_import_manager as mgr

    mgr_source = open(mgr.__file__).read()
    assert "fastapi" not in mgr_source.lower()
    assert "pydantic" not in mgr_source.lower()
    assert "HTTPException" not in mgr_source


def test_manager_confirm_invalid_date_tolerates_and_imports_valid_rows(db_session):
    """
    Verify tolerant behavior: When a statement contains a malformed date row,
    confirm_csv_import imports valid rows, records row errors, and commits the batch.
    """
    account = models.Account(
        name="USAA Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_bad_date = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        b"2026-99-99,BAD DATE ROW,Food,-20.00,posted\n"
        b"2026-06-03,VALID ROW 2,Food,-30.00,posted\n"
    )

    summary = confirm_csv_import(
        db=db_session,
        account_id=account.id,
        format_identifier="usaa",
        raw_bytes=csv_bad_date,
    )

    assert summary.imported == 2
    assert summary.skipped == 0
    assert len(summary.errors) == 1
    assert "Row 2: " in summary.errors[0]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


def test_manager_confirm_invalid_amount_tolerates_and_imports_valid_rows(db_session):
    """
    Verify tolerant behavior: When a statement contains a non-numeric amount row,
    confirm_csv_import imports valid rows, records row errors, and commits the batch.
    """
    account = models.Account(
        name="USAA Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_bad_amount = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        b"2026-06-02,BAD AMOUNT ROW,Food,NOT_A_NUMBER,posted\n"
        b"2026-06-03,VALID ROW 2,Food,-30.00,posted\n"
    )

    summary = confirm_csv_import(
        db=db_session,
        account_id=account.id,
        format_identifier="usaa",
        raw_bytes=csv_bad_amount,
    )

    assert summary.imported == 2
    assert summary.skipped == 0
    assert len(summary.errors) == 1
    assert "Row 2: " in summary.errors[0]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


def test_manager_confirm_custom_format(db_session):
    """
    Verify confirm_csv_import executes workflow with custom format UUID.
    """
    account = models.Account(
        name="Credit Union Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    custom_format = csv_format_access.create_custom_format(
        db=db_session,
        name="Credit Union",
        date_column="TxDate",
        description_column="Payee",
        amount_column="Value",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )

    csv_bytes = (
        b"TxDate,Payee,Value\n"
        b"2026-09-01,Groceries,45.50\n"
        b"2026-09-02,Salary,-2000.00\n"
    )

    summary = confirm_csv_import(
        db=db_session,
        account_id=account.id,
        format_identifier=str(custom_format.id),
        raw_bytes=csv_bytes,
    )

    assert summary.imported == 2
    assert summary.skipped == 0
    assert len(summary.errors) == 0

    txns = db_session.query(models.Transaction).filter_by(account_id=account.id).order_by(models.Transaction.date.asc()).all()
    assert len(txns) == 2
    assert txns[0].description == "Groceries"
    assert txns[0].amount == Decimal("45.50")
    assert txns[1].description == "Salary"
    assert txns[1].amount == Decimal("-2000.00")


# ---------------------------------------------------------------------------
# CSV Inspection Workflow
# ---------------------------------------------------------------------------

def test_manager_inspect_detects_usaa(db_session):
    """Verify inspect_csv_upload detects USAA format from exact headers."""
    csv_bytes = b"Date,Description,Category,Amount,Status\n2026-06-01,GROCERY,Food,-54.20,posted\n"
    res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert res.status == "detected"
    assert res.detected_format is not None
    assert res.detected_format.identifier == "usaa"
    assert res.detected_format.name == "USAA"
    assert len(res.matches) == 1
    assert res.matches[0].identifier == "usaa"
    assert res.headers == ["Date", "Description", "Category", "Amount", "Status"]
    assert len(res.sample_rows) == 1
    assert res.sample_rows[0] == ["2026-06-01", "GROCERY", "Food", "-54.20", "posted"]


def test_manager_inspect_detects_discover(db_session):
    """Verify inspect_csv_upload detects Discover format from exact headers."""
    csv_bytes = b"Trans. Date,Description,Amount,Category\n06/01/2026,PURCHASE,45.00,Merchandise\n"
    res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert res.status == "detected"
    assert res.detected_format is not None
    assert res.detected_format.identifier == "discover"
    assert res.detected_format.name == "Discover"
    assert len(res.matches) == 1


def test_manager_inspect_detects_custom_format(db_session):
    """Verify inspect_csv_upload detects a persisted custom format."""
    custom = csv_format_access.create_custom_format(
        db=db_session,
        name="Credit Union Checking",
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Value",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_inflow",
    )
    csv_bytes = b"Posting Date,Memo,Value\n09/01/2026,Coffee,6.25\n"
    res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert res.status == "detected"
    assert res.detected_format is not None
    assert res.detected_format.identifier == str(custom.id)
    assert res.detected_format.name == "Credit Union Checking"
    assert len(res.matches) == 1


def test_manager_inspect_unknown_format_returns_samples(db_session):
    """Verify unrecognized headers return status='unknown' with sample rows."""
    csv_bytes = b"When,Merchant,Value\n2026-09-01,Coffee Shop,4.50\n2026-09-02,Bookstore,25.00\n"
    res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert res.status == "unknown"
    assert res.detected_format is None
    assert res.matches == []
    assert res.headers == ["When", "Merchant", "Value"]
    assert len(res.sample_rows) == 2
    assert res.sample_rows[0] == ["2026-09-01", "Coffee Shop", "4.50"]
    assert res.sample_rows[1] == ["2026-09-02", "Bookstore", "25.00"]


def test_manager_inspect_ambiguous_format(db_session):
    """Verify headers matching multiple formats return status='ambiguous'."""
    custom = csv_format_access.create_custom_format(
        db=db_session,
        name="Subset USAA Custom",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    csv_bytes = b"Date,Description,Category,Amount,Status\n2026-06-01,STORE,Food,-10.00,posted\n"
    res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert res.status == "ambiguous"
    assert res.detected_format is None
    match_ids = [m.identifier for m in res.matches]
    assert "usaa" in match_ids
    assert str(custom.id) in match_ids
    # USAA (built-in) precedes custom format in candidate sequence
    assert match_ids.index("usaa") < match_ids.index(str(custom.id))


def test_manager_inspect_invalid_utf8_raises():
    """Verify invalid UTF-8 bytes raise CSVInspectError with exact detail prefix."""
    db_mock = MagicMock()
    invalid_bytes = b"\xff\xfe\x00\x00Date,Amount\n2026-01-01,10\n"
    with pytest.raises(CSVInspectError) as exc_info:
        inspect_csv_upload(db=db_mock, raw_bytes=invalid_bytes)
    assert "Unable to decode CSV file as UTF-8:" in str(exc_info.value)


def test_manager_inspect_empty_file_raises():
    """Verify empty bytes raise CSVInspectError with exact detail."""
    db_mock = MagicMock()
    with pytest.raises(CSVInspectError, match="CSV file is empty or contains no header row"):
        inspect_csv_upload(db=db_mock, raw_bytes=b"")


def test_manager_inspect_whitespace_file_raises():
    """Verify whitespace-only bytes raise CSVInspectError with exact detail."""
    db_mock = MagicMock()
    with pytest.raises(CSVInspectError, match="CSV file is empty or contains no header row"):
        inspect_csv_upload(db=db_mock, raw_bytes=b"   \n\n\t  \n")


def test_manager_inspect_no_valid_headers_raises():
    """Verify CSV with empty headers raises CSVInspectError with exact detail."""
    db_mock = MagicMock()
    with pytest.raises(CSVInspectError, match="CSV file contains no valid headers"):
        inspect_csv_upload(db=db_mock, raw_bytes=b",,\n1,2,3\n")


def test_manager_inspect_sample_rows_capped_at_three(db_session):
    """Verify sample rows are strictly bounded to at most 3 rows."""
    csv_bytes = (
        b"When,Merchant,Value\n"
        b"2026-09-01,R1,1\n"
        b"2026-09-02,R2,2\n"
        b"2026-09-03,R3,3\n"
        b"2026-09-04,R4,4\n"
        b"2026-09-05,R5,5\n"
    )
    res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert len(res.sample_rows) == 3
    assert res.sample_rows[0] == ["2026-09-01", "R1", "1"]
    assert res.sample_rows[1] == ["2026-09-02", "R2", "2"]
    assert res.sample_rows[2] == ["2026-09-03", "R3", "3"]


def test_manager_inspect_blank_rows_skipped_in_samples(db_session):
    """Verify blank rows are ignored when capturing sample rows."""
    csv_bytes = (
        b"When,Merchant,Value\n"
        b"  ,  ,  \n"
        b"2026-09-01,R1,1\n"
        b"\n"
        b"2026-09-02,R2,2\n"
    )
    res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert len(res.sample_rows) == 2
    assert res.sample_rows[0] == ["2026-09-01", "R1", "1"]
    assert res.sample_rows[1] == ["2026-09-02", "R2", "2"]


def test_manager_inspect_duplicate_headers_preserves_positional_values(db_session):
    """Verify duplicate column names retain all cells positionally."""
    csv_bytes = b"Amount,Amount,Description\n10.00,20.00,Coffee\n"
    res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert res.headers == ["Amount", "Amount", "Description"]
    assert res.sample_rows == [["10.00", "20.00", "Coffee"]]


def test_manager_inspect_ragged_rows_preserved(db_session):
    """Verify short and long ragged rows are preserved exactly."""
    csv_bytes = b"A,B,C\n1,2\n1,2,3,4\n"
    res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert res.headers == ["A", "B", "C"]
    assert res.sample_rows == [["1", "2"], ["1", "2", "3", "4"]]


def test_manager_inspect_zero_database_mutations(db_session):
    """Verify inspect_csv_upload performs zero database mutations."""
    csv_bytes = b"Date,Description,Category,Amount,Status\n2026-06-01,STORE,Food,-10.00,posted\n"
    inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
    assert db_session.query(models.Transaction).count() == 0
    assert db_session.query(models.CSVFormat).count() == 0


def test_manager_inspect_does_not_query_accounts(db_session):
    """Verify inspect_csv_upload does not query account_access."""
    csv_bytes = b"Date,Description,Category,Amount,Status\n2026-06-01,STORE,Food,-10.00,posted\n"
    with patch("backend.access.account_access.get_account_by_id") as mock_get_account:
        res = inspect_csv_upload(db=db_session, raw_bytes=csv_bytes)
        assert res.status == "detected"
        mock_get_account.assert_not_called()
