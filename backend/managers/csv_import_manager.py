"""
Manager for the CSV Confirmation & Deduplication workflow.

Coordinates:
1. Destination account verification via Account ResourceAccess.
2. Statement loader resolution via BankStatementLoader registry.
3. CSV byte parsing into normalized transaction records via BankStatementLoader.
4. Duplicate checking and transaction staging loop via Transaction ResourceAccess.
5. Per-row error capture and non-fatal aggregation.
6. Single final database commit.
7. Returning an immutable CSVImportSummary application dataclass.
"""

from dataclasses import dataclass
from uuid import UUID
from sqlalchemy.orm import Session

from ..access import account_access, transaction_access
from ..bank_statement_loader import get_loader


@dataclass(frozen=True)
class CSVImportSummary:
    imported: int
    skipped: int
    errors: tuple[str, ...]


class CSVImportAccountNotFoundError(Exception):
    """Raised when the target account cannot be found in persistence."""
    pass


class CSVImportUnknownFormatError(Exception):
    """Raised when the requested format string is not in the loader registry."""
    pass


class CSVImportParseError(Exception):
    """Raised when the statement loader fails to parse the CSV bytes."""
    pass


def confirm_csv_import(
    db: Session,
    raw_bytes: bytes,
    account_id: UUID,
    format_name: str,
) -> CSVImportSummary:
    """
    Coordinates the CSV confirmation and import workflow:
    1. Verifies destination account exists via get_account_by_id.
    2. Instantiates statement loader via get_loader.
    3. Parses CSV bytes into normalized transactions via loader.load_from_bytes.
    4. Iterates parsed transactions:
       - Checks duplicate existence via csv_import_transaction_exists.
       - If duplicate, increments skipped counter.
       - If new, stages transaction via stage_csv_import_transaction and increments imported.
       - Catches per-row exceptions and formats row error strings.
    5. Commits the transaction batch via db.commit().
    6. Returns CSVImportSummary.
    """
    # 1. Account existence
    account = account_access.get_account_by_id(db, account_id)
    if not account:
        raise CSVImportAccountNotFoundError(f"Account {account_id} not found")

    # 2. Format / loader resolution
    try:
        loader = get_loader(format_name, account_id)
    except ValueError as exc:
        raise CSVImportUnknownFormatError(str(exc)) from exc

    # 3. Statement parsing
    try:
        parsed = loader.load_records_tolerant(raw_bytes)
    except ValueError as exc:
        raise CSVImportParseError(str(exc)) from exc

    # 4. Import loop
    imported = 0
    skipped = 0
    errors: list[str] = list(parsed.row_errors)

    for txn in parsed.valid_transactions:
        try:
            if transaction_access.csv_import_transaction_exists(
                db,
                account_id=txn.account_id,
                transaction_date=txn.date,
                amount=txn.amount,
                description=txn.description,
            ):
                skipped += 1
                continue

            transaction_access.stage_csv_import_transaction(
                db,
                account_id=txn.account_id,
                transaction_date=txn.date,
                amount=txn.amount,
                description=txn.description,
                pending=txn.pending,
                category_id=txn.category_id,
                transaction_datetime=txn.datetime,
            )

            imported += 1

        except Exception as exc:
            errors.append(f"Row {txn.date} '{txn.description}': {exc}")

    # 5. Commit
    db.commit()

    return CSVImportSummary(
        imported=imported,
        skipped=skipped,
        errors=tuple(errors),
    )
