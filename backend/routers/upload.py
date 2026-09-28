"""
CSV upload endpoints for manually importing bank transactions.

Flow:
  1. POST /upload/preview  — parse the file, return rows without saving
  2. POST /upload/confirm  — parse + save, with duplicate detection

Both endpoints accept multipart form data:
  - file       : the CSV file
  - account_id : UUID of the account to attach transactions to
  - format     : "usaa" | "discover"
"""

import csv
import io
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from .. import schemas
from ..access import account_access, csv_format_access
from ..database import get_db
from ..bank_statement_loader import (
    BUILTIN_FORMAT_MATCHES,
    BankStatementLoader,
    LOADER_REGISTRY,
    MappedStatementLoader,
    detect_csv_format,
    get_loader,
)
from ..managers import csv_import_manager

router = APIRouter(prefix="/upload", tags=["Upload"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _read_upload(file: UploadFile) -> bytes:
    raw = await file.read()
    await file.seek(0)  # reset so callers can re-read if needed
    return raw


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown format '{format_identifier}'. Available: {list(LOADER_REGISTRY.keys())}",
        )

    custom_format = csv_format_access.get_custom_format_by_id(db, format_uuid)
    if not custom_format:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Format {format_uuid} not found",
        )

    config = csv_format_access.csv_format_to_mapped_config(custom_format)
    return MappedStatementLoader(account_id=account_id, config=config)


# ---------------------------------------------------------------------------
# Inspect endpoint (upload-first detection)
# ---------------------------------------------------------------------------

@router.post("/inspect", response_model=schemas.CSVInspectResponse)
async def inspect_csv(
    file: UploadFile = File(..., description="CSV file to inspect"),
    db: Session = Depends(get_db),
):
    """
    Inspect an uploaded CSV file without importing or requiring an account:
    1. Read and decode bytes via utf-8-sig.
    2. Extract CSV headers and up to 3 bounded sample rows of raw source values.
    3. Load persisted custom formats and combine with built-in format candidates.
    4. Detect matching format candidates without requiring an account or importing data.
    """
    raw = await _read_upload(file)

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to decode CSV file as UTF-8: {exc}",
        )

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV file is empty or contains no header row",
        )

    stream = io.StringIO(text)
    reader = csv.reader(stream)
    try:
        raw_headers = next(reader, None)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Malformed CSV header row: {exc}",
        )

    if raw_headers is None or not any(h.strip() for h in raw_headers if h is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV file contains no valid headers",
        )

    headers = [str(h) for h in raw_headers]

    # Collect bounded sample (up to 3 rows) of raw source values as positional lists
    sample_rows: list[list[str]] = []
    for raw_row in reader:
        if not raw_row or not any(c.strip() for c in raw_row):
            continue
        sample_rows.append([str(c) for c in raw_row])
        if len(sample_rows) >= 3:
            break

    # Build candidates: built-in matches followed by persisted custom formats
    custom_formats = csv_format_access.list_custom_formats(db)
    custom_candidates = [
        csv_format_access.csv_format_to_match_definition(cf)
        for cf in custom_formats
    ]
    candidates = list(BUILTIN_FORMAT_MATCHES) + custom_candidates

    detection_result = detect_csv_format(headers=headers, formats=candidates)

    detected_format_read = None
    if detection_result.detected_format:
        detected_format_read = schemas.CSVFormatMatchRead(
            identifier=detection_result.detected_format.identifier,
            name=detection_result.detected_format.name,
        )

    matches_read = [
        schemas.CSVFormatMatchRead(
            identifier=m.identifier,
            name=m.name,
        )
        for m in detection_result.matches
    ]

    return schemas.CSVInspectResponse(
        headers=headers,
        sample_rows=sample_rows,
        status=detection_result.status,
        detected_format=detected_format_read,
        matches=matches_read,
    )


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

@router.post("/preview", response_model=schemas.CSVPreviewResponse)
async def preview_csv(
    file: UploadFile = File(..., description="CSV file to parse"),
    account_id: UUID = Form(..., description="Target account UUID"),
    format: str = Form(..., description="CSV format: usaa | discover | <custom_uuid>"),
    db: Session = Depends(get_db),
):
    """
    Parse a CSV file and return a preview of the transactions it contains.
    Nothing is written to the database.
    """
    account = account_access.get_account_by_id(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    loader = _resolve_statement_loader(db, account_id, format)

    raw = await _read_upload(file)

    # Parse row by row so we can capture per-row errors gracefully
    rows: list[schemas.CSVTransactionRow] = []
    import csv, io

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    for i, raw_row in enumerate(reader, start=1):
        try:
            normalized = loader.normalize_row(raw_row)
            txn = loader.transform_row(normalized)
            if txn is None:
                continue
            rows.append(
                schemas.CSVTransactionRow(
                    row_number=i,
                    transaction_date=txn.date.isoformat(),
                    description=txn.description,
                    amount=txn.amount,
                    pending=txn.pending,
                )
            )
        except Exception as exc:
            rows.append(
                schemas.CSVTransactionRow(
                    row_number=i,
                    parse_error=str(exc),
                )
            )

    valid_rows = [r for r in rows if r.parse_error is None]
    error_rows = [r for r in rows if r.parse_error is not None]

    return schemas.CSVPreviewResponse(
        rows=rows,
        total_rows=len(rows),
        valid_rows=len(valid_rows),
        error_rows=len(error_rows),
    )


# ---------------------------------------------------------------------------
# Confirm / import endpoint
# ---------------------------------------------------------------------------

@router.post("/confirm", response_model=schemas.CSVImportResult)
async def confirm_csv(
    file: UploadFile = File(..., description="CSV file to import"),
    account_id: UUID = Form(..., description="Target account UUID"),
    format: str = Form(..., description="CSV format: usaa | discover | <custom_uuid>"),
    db: Session = Depends(get_db),
):
    """
    Parse a CSV file and save valid transactions to the database.

    Duplicate detection: a row is skipped (not errored) if a transaction with the
    same account_id, date, amount, and description already exists.
    """
    account = account_access.get_account_by_id(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    loader = _resolve_statement_loader(db, account_id, format)

    raw = await _read_upload(file)

    try:
        summary = csv_import_manager.confirm_csv_import(
            db=db,
            raw_bytes=raw,
            loader=loader,
        )
    except csv_import_manager.CSVImportAccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except csv_import_manager.CSVImportParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    return schemas.CSVImportResult(
        imported=summary.imported,
        skipped=summary.skipped,
        errors=list(summary.errors),
    )
