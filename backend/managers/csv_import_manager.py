"""
Manager for the CSV Upload & Import workflows.

Coordinates:
1. Authoritative destination account verification via Account ResourceAccess.
2. Statement loader resolution (built-in registry vs. persisted custom format configuration).
3. Preview workflow: byte decoding, row normalization/transformation, error aggregation,
   returning an immutable CSVPreviewSummary application dataclass without database mutations.
4. Confirm import workflow: tolerant parsing, duplicate detection, merchant normalization,
   rule categorization, transaction staging, and atomic batch commit,
   returning an immutable CSVImportSummary application dataclass.
"""

from dataclasses import dataclass
from decimal import Decimal
import csv
import io
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from ..access import account_access, csv_format_access, transaction_access, categorization_rule_access
from ..bank_statement_loader import BankStatementLoader, LOADER_REGISTRY, MappedStatementLoader, get_loader
from ..domain.categorization_rules import match_merchant_rule
from ..domain.merchant_normalization import normalize_merchant


@dataclass(frozen=True)
class CSVPreviewRow:
    row_number: int
    transaction_date: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    pending: Optional[bool] = None
    parse_error: Optional[str] = None


@dataclass(frozen=True)
class CSVPreviewSummary:
    rows: tuple[CSVPreviewRow, ...]
    total_rows: int
    valid_rows: int
    error_rows: int


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


class CSVImportFormatNotFoundError(Exception):
    """Raised when a requested custom CSV format UUID is not found in persistence."""
    pass


class CSVImportParseError(Exception):
    """Raised when the statement loader fails to parse the CSV bytes."""
    pass


def _resolve_statement_loader(
    db: Session,
    account_id: UUID,
    format_identifier: str,
) -> BankStatementLoader:
    clean_fmt = format_identifier.strip()

    # 1. Built-in format?
    if clean_fmt.lower() in LOADER_REGISTRY:
        return get_loader(clean_fmt, account_id)

    # 2. Custom format UUID?
    try:
        format_uuid = UUID(clean_fmt)
    except ValueError:
        raise CSVImportUnknownFormatError(
            f"Unknown format '{format_identifier}'. Available: {list(LOADER_REGISTRY.keys())}"
        )

    custom_format = csv_format_access.get_custom_format_by_id(db, format_uuid)
    if not custom_format:
        raise CSVImportFormatNotFoundError(f"Format {format_uuid} not found")

    config = csv_format_access.csv_format_to_mapped_config(custom_format)
    return MappedStatementLoader(account_id=account_id, config=config)


def preview_csv_import(
    db: Session,
    account_id: UUID,
    format_identifier: str,
    raw_bytes: bytes,
) -> CSVPreviewSummary:
    """
    Coordinates the CSV preview workflow:
    1. Verifies destination account exists via account_access.get_account_by_id.
    2. Resolves statement loader via _resolve_statement_loader.
    3. Decodes raw bytes using utf-8-sig (with latin-1 fallback).
    4. Iterates rows with 1-based indexing, transforming records via loader.
    5. Captures per-row parse errors non-fatally.
    6. Assembles and returns CSVPreviewSummary without mutating the database.
    """
    account = account_access.get_account_by_id(db, account_id)
    if not account:
        raise CSVImportAccountNotFoundError(f"Account {account_id} not found")

    loader = _resolve_statement_loader(db, account_id, format_identifier)

    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")

    rows: list[CSVPreviewRow] = []
    reader = csv.DictReader(io.StringIO(text))
    for i, raw_row in enumerate(reader, start=1):
        try:
            normalized = loader.normalize_row(raw_row)
            txn = loader.transform_row(normalized)
            if txn is None:
                continue
            rows.append(
                CSVPreviewRow(
                    row_number=i,
                    transaction_date=txn.date.isoformat(),
                    description=txn.description,
                    amount=txn.amount,
                    pending=txn.pending,
                )
            )
        except Exception as exc:
            rows.append(
                CSVPreviewRow(
                    row_number=i,
                    parse_error=str(exc),
                )
            )

    valid_rows = [r for r in rows if r.parse_error is None]
    error_rows = [r for r in rows if r.parse_error is not None]

    return CSVPreviewSummary(
        rows=tuple(rows),
        total_rows=len(rows),
        valid_rows=len(valid_rows),
        error_rows=len(error_rows),
    )


def confirm_csv_import(
    db: Session,
    account_id: UUID,
    format_identifier: str,
    raw_bytes: bytes,
) -> CSVImportSummary:
    """
    Coordinates the CSV confirmation and import workflow:
    1. Verifies destination account exists via account_access.get_account_by_id.
    2. Resolves statement loader via _resolve_statement_loader.
    3. Parses CSV bytes into normalized transactions via loader.load_records_tolerant.
    4. Iterates parsed transactions:
       - Checks duplicate existence via csv_import_transaction_exists.
       - If duplicate, increments skipped counter.
       - If new, stages transaction via stage_csv_import_transaction and increments imported.
       - Evaluates categorization rules for uncategorized rows via match_merchant_rule.
       - Catches per-row exceptions and formats row error strings.
    5. Commits the transaction batch via db.commit().
    6. Returns CSVImportSummary.
    """
    # 1. Account existence
    account = account_access.get_account_by_id(db, account_id)
    if not account:
        raise CSVImportAccountNotFoundError(f"Account {account_id} not found")

    # 2. Loader resolution
    loader = _resolve_statement_loader(db, account_id, format_identifier)

    # 3. Statement parsing
    try:
        parsed = loader.load_records_tolerant(raw_bytes)
    except ValueError as exc:
        raise CSVImportParseError(str(exc)) from exc

    # 4. Rules lookup for O(1) matching during import
    rules_lookup = categorization_rule_access.get_rules_lookup_dict(db)

    # 5. Import loop
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
            if txn.category_id is not None:
                assigned_category_id = txn.category_id
                category_source = "legacy"
            else:
                matched_category_id = match_merchant_rule(merchant, rules_lookup)
                if matched_category_id is not None:
                    assigned_category_id = matched_category_id
                    category_source = "rule"
                else:
                    assigned_category_id = None
                    category_source = None

            transaction_access.stage_csv_import_transaction(
                db,
                account_id=txn.account_id,
                transaction_date=txn.date,
                amount=txn.amount,
                description=txn.description,
                pending=txn.pending,
                category_id=assigned_category_id,
                category_source=category_source,
                transaction_datetime=txn.datetime,
                merchant=merchant,
            )

            imported += 1

        except Exception as exc:
            errors.append(f"Row {txn.date} '{txn.description}': {exc}")

    # 6. Commit
    db.commit()

    return CSVImportSummary(
        imported=imported,
        skipped=skipped,
        errors=tuple(errors),
    )
