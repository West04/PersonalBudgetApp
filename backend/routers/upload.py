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

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from .. import schemas
from ..access import account_access
from ..database import get_db
from ..bank_statement_loader import get_loader
from ..managers import csv_import_manager

router = APIRouter(prefix="/upload", tags=["Upload"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _read_upload(file: UploadFile) -> bytes:
    raw = await file.read()
    await file.seek(0)  # reset so callers can re-read if needed
    return raw


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

@router.post("/preview", response_model=schemas.CSVPreviewResponse)
async def preview_csv(
    file: UploadFile = File(..., description="CSV file to parse"),
    account_id: UUID = Form(..., description="Target account UUID"),
    format: str = Form(..., description="CSV format: usaa | discover"),
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

    raw = await _read_upload(file)

    try:
        loader = get_loader(format, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

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
    format: str = Form(..., description="CSV format: usaa | discover"),
    db: Session = Depends(get_db),
):
    """
    Parse a CSV file and save valid transactions to the database.

    Duplicate detection: a row is skipped (not errored) if a transaction with the
    same account_id, date, amount, and description already exists.
    """
    raw = await _read_upload(file)

    try:
        summary = csv_import_manager.confirm_csv_import(
            db=db,
            raw_bytes=raw,
            account_id=account_id,
            format_name=format,
        )
    except csv_import_manager.CSVImportAccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except csv_import_manager.CSVImportUnknownFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
