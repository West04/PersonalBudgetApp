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

from .. import models, schemas
from ..database import get_db
from ..bank_statement_loader import get_loader

router = APIRouter(prefix="/upload", tags=["Upload"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_account(account_id: UUID, db: Session) -> models.Account:
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )
    return account


def _is_duplicate(db: Session, txn: schemas.TransactionCreate) -> bool:
    """
    Returns True if an identical transaction already exists for this account.
    Match criteria: same account_id + date + amount + description (case-insensitive).
    """
    existing = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.account_id == txn.account_id,
            models.Transaction.date == txn.date,
            models.Transaction.amount == txn.amount,
            models.Transaction.description == txn.description,
        )
        .first()
    )
    return existing is not None


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
    _verify_account(account_id, db)

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
    _verify_account(account_id, db)

    raw = await _read_upload(file)

    try:
        loader = get_loader(format, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    try:
        transactions = loader.load_from_bytes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    imported = 0
    skipped = 0
    errors: list[str] = []

    for txn in transactions:
        try:
            if _is_duplicate(db, txn):
                skipped += 1
                continue

            db_txn = models.Transaction(
                account_id=txn.account_id,
                category_id=txn.category_id,
                description=txn.description,
                amount=txn.amount,
                date=txn.date,
                datetime=txn.datetime,
                pending=txn.pending,
                plaid_transaction_id=None,  # manual import — no Plaid ID
            )
            db.add(db_txn)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {txn.date} '{txn.description}': {exc}")

    db.commit()

    return schemas.CSVImportResult(
        imported=imported,
        skipped=skipped,
        errors=errors,
    )
