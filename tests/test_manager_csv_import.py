from dataclasses import FrozenInstanceError, is_dataclass
from decimal import Decimal
from unittest.mock import MagicMock, call, patch
from uuid import uuid4
import pytest

from backend import models
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
    1. Account lookup occurs before loader resolution.
    2. Missing account raises CSVImportAccountNotFoundError before get_loader is called.
    """
    db_mock = MagicMock()
    account_id = uuid4()
    raw_bytes = b"sample,csv,data"

    with patch("backend.access.account_access.get_account_by_id", return_value=None) as mock_get_account, \
         patch("backend.managers.csv_import_manager.get_loader") as mock_get_loader:

        with pytest.raises(CSVImportAccountNotFoundError, match=f"Account {account_id} not found"):
            confirm_csv_import(
                db=db_mock,
                raw_bytes=raw_bytes,
                account_id=account_id,
                format_name="invalid_format",
            )

        mock_get_account.assert_called_once_with(db_mock, account_id)
        mock_get_loader.assert_not_called()


def test_manager_unknown_format_raises_unknown_format_error(db_session):
    """
    Verify valid account + unknown format raises CSVImportUnknownFormatError
    with exact message from loader registry ValueError.
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

    with pytest.raises(CSVImportUnknownFormatError, match="Unknown format 'nonexistent'"):
        confirm_csv_import(
            db=db_session,
            raw_bytes=b"dummy bytes",
            account_id=account.id,
            format_name="nonexistent",
        )


def test_manager_parse_failure_raises_parse_error(db_session):
    """
    Verify valid account + valid format + invalid CSV bytes raises CSVImportParseError.
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
            raw_bytes=malformed_csv,
            account_id=account.id,
            format_name="usaa",
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
        raw_bytes=csv_data,
        account_id=account.id,
        format_name="usaa",
    )
    assert res1.imported == 2
    assert res1.skipped == 0
    assert res1.errors == ()

    # Re-import identical file: 0 imported, 2 skipped
    res2 = confirm_csv_import(
        db=db_session,
        raw_bytes=csv_data,
        account_id=account.id,
        format_name="usaa",
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
        raw_bytes=csv_data,
        account_id=account.id,
        format_name="usaa",
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
            raw_bytes=csv_data,
            account_id=account.id,
            format_name="usaa",
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
            raw_bytes=csv_data,
            account_id=account.id,
            format_name="usaa",
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
                raw_bytes=csv_data,
                account_id=account.id,
                format_name="usaa",
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
