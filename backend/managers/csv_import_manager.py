"""
Manager for the CSV Confirmation & Deduplication workflow.

Coordinates:
1. Destination account verification via Account ResourceAccess.
2. CSV byte parsing into normalized transaction records via BankStatementLoader.
3. Duplicate checking and transaction staging loop via Transaction ResourceAccess.
4. Per-row error capture and non-fatal aggregation.
5. Single final database commit.
6. Returning an immutable CSVImportSummary application dataclass.
"""

from dataclasses import dataclass
from uuid import UUID
from sqlalchemy.orm import Session

from ..access import account_access, transaction_access, categorization_rule_access
from ..bank_statement_loader import BankStatementLoader
from ..domain.merchant_normalization import normalize_merchant


@dataclass(frozen=True)
class CSVImportSummary:
    imported: int
    skipped: int
    errors: tuple[str, ...]


class CSVImportAccountNotFoundError(Exception):
    """Raised when the target account cannot be found in persistence."""
    pass


class CSVImportUnknownFormatError(Exception):
    """Raised when a requested format string is unknown (legacy / compatibility)."""
    pass


class CSVImportParseError(Exception):
    """Raised when the statement loader fails to parse the CSV bytes."""
    pass


def confirm_csv_import(
    db: Session,
    raw_bytes: bytes,
    loader: BankStatementLoader,
) -> CSVImportSummary:
    """
    Coordinates the CSV confirmation and import workflow:
    1. Verifies destination account exists via get_account_by_id(db, loader.account_id).
    2. Parses CSV bytes into normalized transactions via loader.load_records_tolerant.
    3. Iterates parsed transactions:
       - Checks duplicate existence via csv_import_transaction_exists.
       - If duplicate, increments skipped counter.
       - If new, stages transaction via stage_csv_import_transaction and increments imported.
       - Evaluates categorization rules for uncategorized rows.
       - Catches per-row exceptions and formats row error strings.
    4. Commits the transaction batch via db.commit().
    5. Returns CSVImportSummary.
    """
    # 1. Account existence
    account = account_access.get_account_by_id(db, loader.account_id)
    if not account:
        raise CSVImportAccountNotFoundError(f"Account {loader.account_id} not found")

    # 2. Statement parsing
    try:
        parsed = loader.load_records_tolerant(raw_bytes)
    except ValueError as exc:
        raise CSVImportParseError(str(exc)) from exc

    # 3. Rules lookup for O(1) matching during import
    rules_lookup = categorization_rule_access.get_rules_lookup_dict(db)

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

            merchant = normalize_merchant(txn.description)
            transaction_access.stage_csv_import_transaction(
                db,
                account_id=txn.account_id,
                transaction_date=txn.date,
                amount=txn.amount,
                description=txn.description,
                pending=txn.pending,
                category_id=txn.category_id,
                transaction_datetime=txn.datetime,
                merchant=merchant,
                rules_lookup=rules_lookup,
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
