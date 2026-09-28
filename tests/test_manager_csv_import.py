from dataclasses import FrozenInstanceError, is_dataclass
from decimal import Decimal, InvalidOperation
from unittest.mock import MagicMock, call, patch
from uuid import uuid4
import pytest

from backend import models
from backend.bank_statement_loader import BankStatementLoader, ParsedStatement, USAALoader
from backend.managers.csv_import_manager import (
    CSVImportAccountNotFoundError,
    CSVImportParseError,
    CSVImportSummary,
    CSVImportUnknownFormatError,
    confirm_csv_import,
)
from backend.schemas import TransactionCreate


def test_manager_validation_order_mocked():
    """
    Verify validation precedence using controlled mocks:
    1. Account lookup occurs before statement parsing.
    2. Missing account raises CSVImportAccountNotFoundError before loader is invoked.
    """
    db_mock = MagicMock()
    account_id = uuid4()
    raw_bytes = b"sample,csv,data"
    loader_mock = MagicMock(spec=BankStatementLoader)
    loader_mock.account_id = account_id

    with patch("backend.access.account_access.get_account_by_id", return_value=None) as mock_get_account:
        with pytest.raises(CSVImportAccountNotFoundError, match=f"Account {account_id} not found"):
            confirm_csv_import(
                db=db_mock,
                raw_bytes=raw_bytes,
                loader=loader_mock,
            )

        mock_get_account.assert_called_once_with(db_mock, account_id)
        loader_mock.load_records_tolerant.assert_not_called()


def test_manager_delegates_parsing_to_provided_loader(db_session):
    """
    Verify confirm_csv_import delegates CSV parsing to the provided BankStatementLoader.
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

    raw_bytes = b"dummy,csv,bytes"
    mock_loader = MagicMock(spec=BankStatementLoader)
    mock_loader.account_id = account.id
    mock_loader.load_records_tolerant.return_value = ParsedStatement(
        valid_transactions=(),
        row_errors=(),
    )

    summary = confirm_csv_import(
        db=db_session,
        raw_bytes=raw_bytes,
        loader=mock_loader,
    )
    mock_loader.load_records_tolerant.assert_called_once_with(raw_bytes)
    assert summary.imported == 0
    assert summary.skipped == 0


def test_manager_parse_failure_raises_parse_error(db_session):
    """
    Verify valid account + invalid CSV bytes raises CSVImportParseError from loader.
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
    loader = USAALoader(account_id=account.id)
    with pytest.raises(CSVImportParseError, match="Missing columns"):
        confirm_csv_import(
            db=db_session,
            raw_bytes=malformed_csv,
            loader=loader,
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
    loader = USAALoader(account_id=account.id)
    res1 = confirm_csv_import(
        db=db_session,
        raw_bytes=csv_data,
        loader=loader,
    )
    assert res1.imported == 2
    assert res1.skipped == 0
    assert res1.errors == ()

    # Re-import identical file: 0 imported, 2 skipped
    res2 = confirm_csv_import(
        db=db_session,
        raw_bytes=csv_data,
        loader=loader,
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

    loader = USAALoader(account_id=account.id)
    res = confirm_csv_import(
        db=db_session,
        raw_bytes=csv_data,
        loader=loader,
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

    loader = USAALoader(account_id=account.id)
    with patch("backend.access.transaction_access.stage_csv_import_transaction", side_effect=mock_stage):
        res = confirm_csv_import(
            db=db_session,
            raw_bytes=csv_data,
            loader=loader,
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

    loader = USAALoader(account_id=account.id)
    with patch.object(db_session, "commit", wraps=db_session.commit) as mock_commit:
        res = confirm_csv_import(
            db=db_session,
            raw_bytes=csv_data,
            loader=loader,
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

    loader = USAALoader(account_id=account.id)
    with patch.object(db_session, "commit", side_effect=RuntimeError("DB Commit Crash")):
        with pytest.raises(RuntimeError, match="DB Commit Crash"):
            confirm_csv_import(
                db=db_session,
                raw_bytes=csv_data,
                loader=loader,
            )


def test_manager_summary_dataclass_contract():
    """
    Verify CSVImportSummary:
    - Is an immutable frozen dataclass.
    - errors is a tuple.
    """
    summary = CSVImportSummary(imported=5, skipped=2, errors=("err1", "err2"))
    assert is_dataclass(summary)
    assert summary.imported == 5
    assert summary.skipped == 2
    assert summary.errors == ("err1", "err2")
    assert isinstance(summary.errors, tuple)

    with pytest.raises(FrozenInstanceError):
        summary.imported = 10  # type: ignore


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


# ---------------------------------------------------------------------------
# Row Error Tolerant Behavior
# ---------------------------------------------------------------------------

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

    loader = USAALoader(account_id=account.id)
    summary = confirm_csv_import(
        db=db_session,
        raw_bytes=csv_bad_date,
        loader=loader,
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

    loader = USAALoader(account_id=account.id)
    summary = confirm_csv_import(
        db=db_session,
        raw_bytes=csv_bad_amount,
        loader=loader,
    )

    assert summary.imported == 2
    assert summary.skipped == 0
    assert len(summary.errors) == 1
    assert "Row 2: " in summary.errors[0]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


def test_manager_confirm_with_explicit_loader_instance(db_session):
    """
    Verify confirm_csv_import executes workflow when passed an explicit
    BankStatementLoader instance (e.g. MappedStatementLoader) rather than a format name string.
    """
    from backend.bank_statement_loader import MappedCSVFormatConfig, MappedStatementLoader

    account = models.Account(
        name="Credit Union Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    config = MappedCSVFormatConfig(
        date_column="TxDate",
        description_column="Payee",
        amount_column="Value",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    loader = MappedStatementLoader(account_id=account.id, config=config)

    csv_bytes = (
        b"TxDate,Payee,Value\n"
        b"2026-09-01,Groceries,45.50\n"
        b"2026-09-02,Salary,-2000.00\n"
    )

    summary = confirm_csv_import(
        db=db_session,
        raw_bytes=csv_bytes,
        loader=loader,
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


def test_manager_derives_account_id_from_loader(db_session):
    """
    Verify the Manager derives account context exclusively from loader.account_id:
    - Validates loader.account_id exists in persistence.
    - Persists imported transactions to that exact account.
    """
    account_a = models.Account(
        name="Account Alpha",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    account_b = models.Account(
        name="Account Beta",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add_all([account_a, account_b])
    db_session.commit()

    csv_data = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-06-01,STORE ON ALPHA,Food,-10.00,posted\n"
    )

    loader = USAALoader(account_id=account_a.id)
    summary = confirm_csv_import(
        db=db_session,
        raw_bytes=csv_data,
        loader=loader,
    )

    assert summary.imported == 1
    assert summary.skipped == 0

    # Ensure transaction was persisted under Account Alpha, NOT Account Beta
    txns_a = db_session.query(models.Transaction).filter_by(account_id=account_a.id).all()
    txns_b = db_session.query(models.Transaction).filter_by(account_id=account_b.id).all()
    assert len(txns_a) == 1
    assert len(txns_b) == 0
    assert txns_a[0].description == "STORE ON ALPHA"


def test_manager_fails_when_loader_account_id_does_not_exist(db_session):
    """
    Verify the Manager validates loader.account_id and fails cleanly
    outside of the HTTP router if the loader's account_id does not exist in persistence.
    """
    nonexistent_id = uuid4()
    loader = USAALoader(account_id=nonexistent_id)

    csv_data = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-06-01,SOME STORE,Food,-10.00,posted\n"
    )

    with pytest.raises(CSVImportAccountNotFoundError, match=f"Account {nonexistent_id} not found"):
        confirm_csv_import(
            db=db_session,
            raw_bytes=csv_data,
            loader=loader,
        )

