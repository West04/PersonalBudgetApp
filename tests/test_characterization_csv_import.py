from io import BytesIO
from decimal import Decimal, InvalidOperation
from datetime import date
from uuid import uuid4
import pytest

from backend import models


def test_csv_confirm_missing_account_404(client):
    """
    Verify POST /upload/confirm returns HTTP 404 with exact detail
    when the target account UUID does not exist.
    """
    non_existent_id = uuid4()
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE,Food,-25.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(non_existent_id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 404
    assert resp.json() == {"detail": f"Account {non_existent_id} not found"}


def test_csv_confirm_inactive_account_allowed(client, db_session):
    """
    Verify POST /upload/confirm currently permits importing into an inactive account
    (models.Account.is_active == False is not restricted).
    """
    account = models.Account(
        name="Inactive Account",
        type="depository",
        is_active=False,
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,LEGACY CHARGE,Bills,-50.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["imported"] == 1
    assert res["skipped"] == 0
    assert len(res["errors"]) == 0

    txns = db_session.query(models.Transaction).filter(models.Transaction.account_id == account.id).all()
    assert len(txns) == 1
    assert txns[0].amount == Decimal("50.00")
    assert txns[0].description == "LEGACY CHARGE"


def test_csv_confirm_unknown_format_400(client, db_session):
    """
    Verify POST /upload/confirm returns HTTP 400 with exact detail
    when the format is not in LOADER_REGISTRY.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE,Food,-25.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "chase"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Unknown format 'chase'. Available: ['usaa', 'discover']"}


def test_csv_confirm_malformed_csv_missing_column_422(client, db_session):
    """
    Verify POST /upload/confirm returns HTTP 422 with parser detail
    when required columns are missing from the CSV.
    """
    account = models.Account(
        name="Test Account",
        type="depository",
        current_balance=Decimal("0.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    # USAA format requires: Date, Description, Category, Amount, Status. Here 'Status' is missing.
    csv_missing_status = (
        "Date,Description,Category,Amount\n"
        "2026-06-01,STORE,Food,-25.00\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_missing_status.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 422
    assert resp.json() == {"detail": "Missing columns: ['Status']"}


def test_csv_confirm_validation_precedence(client, db_session):
    """
    Verify the exact validation precedence among invalid inputs:
    1. Missing Account (404) takes precedence over Unknown Format (400) and Malformed CSV (422).
    2. Unknown Format (400) takes precedence over Malformed CSV (422).
    """
    missing_id = uuid4()
    malformed_csv = "BadHeader1,BadHeader2\n123,456\n"
    files = {"file": ("statement.csv", BytesIO(malformed_csv.encode("utf-8")), "text/csv")}

    # Case A: Missing Account + Unknown Format -> 404 wins
    resp_a = client.post("/upload/confirm", data={"account_id": str(missing_id), "format": "invalid_fmt"}, files=files)
    assert resp_a.status_code == 404
    assert resp_a.json() == {"detail": f"Account {missing_id} not found"}

    # Case B: Missing Account + Malformed CSV + Valid Format -> 404 wins
    resp_b = client.post("/upload/confirm", data={"account_id": str(missing_id), "format": "usaa"}, files=files)
    assert resp_b.status_code == 404
    assert resp_b.json() == {"detail": f"Account {missing_id} not found"}

    # Case C: Valid Account + Unknown Format + Malformed CSV -> 400 wins
    account = models.Account(name="Valid Acct", type="depository", current_balance=Decimal("0.00"), starting_balance=Decimal("0.00"), currency="USD")
    db_session.add(account)
    db_session.commit()

    resp_c = client.post("/upload/confirm", data={"account_id": str(account.id), "format": "invalid_fmt"}, files=files)
    assert resp_c.status_code == 400
    assert resp_c.json() == {"detail": "Unknown format 'invalid_fmt'. Available: ['usaa', 'discover']"}


def test_csv_confirm_intra_request_duplicates_both_imported(client, db_session):
    """
    Characterize intra-request duplicate behavior:
    When two identical rows appear in the same CSV upload and neither existed before,
    both rows are imported (autoflush=False and no explicit flush during loop).
    Result: imported == 2, skipped == 0.
    """
    account = models.Account(
        name="Duplicate Test Account",
        type="depository",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    # Two IDENTICAL rows in the same CSV file
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,COFFEE SHOP,Food,-4.50,posted\n"
        "2026-06-01,COFFEE SHOP,Food,-4.50,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["imported"] == 2
    assert res["skipped"] == 0
    assert len(res["errors"]) == 0

    # Verify both transactions exist in the database
    txns = (
        db_session.query(models.Transaction)
        .filter(models.Transaction.account_id == account.id)
        .all()
    )
    assert len(txns) == 2
    for t in txns:
        assert t.amount == Decimal("4.50")  # USAA inverted to positive
        assert t.description == "COFFEE SHOP"
        assert t.date == date(2026, 6, 1)


def test_csv_confirm_cross_account_duplicate_isolation(client, db_session):
    """
    Verify duplicate detection is strictly scoped to the destination account:
    An identical transaction (same date, amount, description) existing on Account A
    does NOT trigger a duplicate skip when imported into Account B.
    """
    acct_a = models.Account(name="Acct Alpha", type="depository", current_balance=Decimal("0"), starting_balance=Decimal("0"), currency="USD")
    acct_b = models.Account(name="Acct Beta", type="depository", current_balance=Decimal("0"), starting_balance=Decimal("0"), currency="USD")
    db_session.add_all([acct_a, acct_b])
    db_session.flush()

    # Pre-existing transaction on Account A
    existing_tx = models.Transaction(
        account_id=acct_a.id,
        date=date(2026, 6, 1),
        amount=Decimal("35.00"),
        description="SHELL OIL",
        pending=False,
    )
    db_session.add(existing_tx)
    db_session.commit()

    # Upload identical transaction to Account B
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,SHELL OIL,Auto,-35.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(acct_b.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["imported"] == 1
    assert res["skipped"] == 0


def test_csv_confirm_description_case_sensitivity(client, db_session):
    """
    Verify duplicate detection description matching is case-sensitive:
    An existing transaction with description 'GROCERY STORE' does NOT cause
    'grocery store' to be skipped (it is treated as a distinct, new transaction).
    """
    account = models.Account(name="Checking", type="depository", current_balance=Decimal("0"), starting_balance=Decimal("0"), currency="USD")
    db_session.add(account)
    db_session.flush()

    # Pre-existing transaction with UPPERCASE description
    existing_tx = models.Transaction(
        account_id=account.id,
        date=date(2026, 6, 1),
        amount=Decimal("75.00"),
        description="GROCERY STORE",
        pending=False,
    )
    db_session.add(existing_tx)
    db_session.commit()

    # Upload with lowercase description
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,grocery store,Food,-75.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    # Not skipped because description comparison is case-sensitive in PostgreSQL
    assert res["imported"] == 1
    assert res["skipped"] == 0

    txns = db_session.query(models.Transaction).filter(models.Transaction.account_id == account.id).all()
    assert len(txns) == 2


def test_csv_confirm_header_only_csv(client, db_session):
    """
    Verify uploading a valid CSV containing only headers and zero transaction rows
    succeeds with imported=0, skipped=0, errors=[].
    """
    account = models.Account(name="Checking", type="depository", current_balance=Decimal("0"), starting_balance=Decimal("0"), currency="USD")
    db_session.add(account)
    db_session.commit()

    header_only_csv = "Date,Description,Category,Amount,Status\n"
    files = {"file": ("statement.csv", BytesIO(header_only_csv.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["imported"] == 0
    assert res["skipped"] == 0
    assert res["errors"] == []


def test_csv_confirm_discover_format_end_to_end(client, db_session):
    """
    Verify POST /upload/confirm with Discover format end-to-end:
    - Parses Discover columns (Trans. Date, Description, Amount, Category)
    - Parses %m/%d/%Y date format
    - Charges are already positive (outflow) in Discover and preserved as positive
    - Credits/payments are negative in Discover and preserved as negative
    """
    account = models.Account(name="Discover Card", type="credit", current_balance=Decimal("0"), starting_balance=Decimal("0"), currency="USD")
    db_session.add(account)
    db_session.commit()

    csv_discover = (
        "Trans. Date,Description,Amount,Category\n"
        "06/15/2026,AMAZON.COM,89.99,Merchandise\n"
        "06/16/2026,DIRECTPAY FULL BALANCE,-500.00,Payments\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_discover.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "discover"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["imported"] == 2
    assert res["skipped"] == 0
    assert len(res["errors"]) == 0

    txns = (
        db_session.query(models.Transaction)
        .filter(models.Transaction.account_id == account.id)
        .order_by(models.Transaction.date.asc())
        .all()
    )
    assert len(txns) == 2

    # Charge: 89.99 positive
    assert txns[0].date == date(2026, 6, 15)
    assert txns[0].description == "AMAZON.COM"
    assert txns[0].amount == Decimal("89.99")
    assert txns[0].pending is False
    assert txns[0].is_transfer is False
    assert txns[0].plaid_transaction_id is None

    # Payment: -500.00 negative
    assert txns[1].date == date(2026, 6, 16)
    assert txns[1].description == "DIRECTPAY FULL BALANCE"
    assert txns[1].amount == Decimal("-500.00")


def test_csv_confirm_zero_amount_transaction(client, db_session):
    """
    Verify confirmation of a 0.00 amount transaction succeeds and imports correctly.
    """
    account = models.Account(name="Checking", type="depository", current_balance=Decimal("0"), starting_balance=Decimal("0"), currency="USD")
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,FEE REVERSAL OFFSET,Fee,0.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1

    tx = db_session.query(models.Transaction).filter(models.Transaction.account_id == account.id).first()
    assert tx.amount == Decimal("0.00")


# ---------------------------------------------------------------------------
# Confirm Row Parse Error Tolerant Tests
# ---------------------------------------------------------------------------


def test_csv_confirm_mixed_valid_and_invalid_date_persists_valid_rows(client, db_session):
    """
    Verify tolerant behavior: USAA statement with valid rows and an invalid date row
    imports the valid rows, records the row error, and commits the batch.
    """
    account = models.Account(
        name="Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,VALID ROW 1,Food,-15.00,posted\n"
        "2026-99-99,BROKEN DATE ROW,Food,-20.00,posted\n"
        "2026-06-03,VALID ROW 2,Auto,-35.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert len(body["errors"]) == 1
    assert "Row 2: " in body["errors"][0]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


def test_csv_confirm_mixed_valid_and_invalid_amount_persists_valid_rows(client, db_session):
    """
    Verify tolerant behavior: USAA statement with valid rows and a non-numeric amount row
    imports the valid rows, records the row error, and commits the batch.
    """
    account = models.Account(
        name="Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,VALID ROW 1,Food,-15.00,posted\n"
        "2026-06-02,BROKEN AMOUNT ROW,Food,NOT_A_NUMBER,posted\n"
        "2026-06-03,VALID ROW 2,Auto,-35.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert len(body["errors"]) == 1
    assert "Row 2: " in body["errors"][0]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


def test_csv_confirm_all_malformed_dates_returns_200_with_errors_persists_zero(client, db_session):
    """
    Verify tolerant behavior: When all data rows in a CSV have malformed dates,
    POST /upload/confirm returns HTTP 200 with imported=0 and all errors recorded.
    """
    account = models.Account(
        name="Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "bad-date-1,ROW 1,Food,-10.00,posted\n"
        "bad-date-2,ROW 2,Food,-20.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 0
    assert body["skipped"] == 0
    assert len(body["errors"]) == 2
    assert "Row 1: " in body["errors"][0]
    assert "Row 2: " in body["errors"][1]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 0


def test_csv_confirm_valid_duplicate_and_malformed_skips_duplicate_persists_new_valid(client, db_session):
    """
    Verify tolerant behavior: A file with a duplicate valid row, a malformed row,
    and a new valid row skips the duplicate, records the error, and persists the new valid row.
    """
    account = models.Account(
        name="Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    # Pre-existing transaction
    existing = models.Transaction(
        account_id=account.id,
        date=date(2026, 6, 1),
        amount=Decimal("15.00"),
        description="EXISTING COFFEE",
        pending=False,
    )
    db_session.add(existing)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,EXISTING COFFEE,Food,-15.00,posted\n"
        "2026-99-99,BROKEN ROW,Food,-20.00,posted\n"
        "2026-06-03,NEW VALID ROW,Auto,-35.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 1
    assert body["skipped"] == 1
    assert len(body["errors"]) == 1
    assert "Row 2: " in body["errors"][0]

    txns = db_session.query(models.Transaction).filter_by(account_id=account.id).all()
    assert len(txns) == 2


def test_csv_confirm_discover_mixed_valid_and_invalid_date_persists_valid_rows(client, db_session):
    """
    Verify tolerant behavior: Discover statement with an invalid date row
    imports valid rows, records row errors, and commits the batch.
    """
    account = models.Account(
        name="Discover Card",
        type="credit",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "06/01/2026,TARGET STORE,50.00,Merchandise\n"
        "99/99/2026,BAD DATE ROW,25.00,Merchandise\n"
        "06/03/2026,WHOLE FOODS,75.00,Supermarkets\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "discover"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert len(body["errors"]) == 1
    assert "Row 2: " in body["errors"][0]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


def test_csv_confirm_discover_mixed_valid_and_invalid_amount_persists_valid_rows(client, db_session):
    """
    Verify tolerant behavior: Discover statement with a non-numeric amount row
    imports valid rows, records row errors, and commits the batch.
    """
    account = models.Account(
        name="Discover Card",
        type="credit",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "06/01/2026,TARGET STORE,50.00,Merchandise\n"
        "06/02/2026,BAD AMOUNT ROW,NOT_NUM,Merchandise\n"
        "06/03/2026,WHOLE FOODS,75.00,Supermarkets\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "discover"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert len(body["errors"]) == 1
    assert "Row 2: " in body["errors"][0]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


def test_csv_confirm_usaa_ragged_rows_persists_valid(client, db_session):
    """
    Verify tolerant behavior: USAA statement with a short/ragged row missing columns
    imports valid rows, records the ragged row error, and commits the batch.
    """
    account = models.Account(
        name="Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        "2026-06-02,RAGGED ROW,Food,-20.00\n"
        "2026-06-03,VALID ROW 2,Auto,-30.00,posted\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert len(body["errors"]) == 1
    assert "Row 2: " in body["errors"][0]
    assert "'NoneType' object has no attribute 'strip'" in body["errors"][0]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


def test_csv_confirm_discover_ragged_rows_persists_valid(client, db_session):
    """
    Verify tolerant behavior: Discover statement with a short/ragged row missing columns
    imports valid rows, records the ragged row error, and commits the batch.
    """
    account = models.Account(
        name="Discover Card",
        type="credit",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "06/01/2026,TARGET STORE,50.00,Merchandise\n"
        "06/02/2026,RAGGED DISCOVER ROW\n"
        "06/03/2026,WHOLE FOODS,75.00,Supermarkets\n"
    )
    files = {"file": ("statement.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account.id), "format": "discover"}

    resp = client.post("/upload/confirm", data=data, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert len(body["errors"]) == 1
    assert "Row 2: " in body["errors"][0]
    assert "'NoneType' object has no attribute 'strip'" in body["errors"][0]

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


def test_csv_confirm_ragged_rows_preview_consistency(client, db_session):
    """
    Verify Preview and Confirm identify the exact same row errors on ragged CSV inputs.
    """
    account = models.Account(
        name="Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_bytes = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        b"2026-06-02,RAGGED MISSING STATUS,Food,-20.00\n"
        b"2026-06-03,VALID ROW 2,Auto,-30.00,posted\n"
    )
    files_preview = {"file": ("statement.csv", BytesIO(csv_bytes), "text/csv")}
    files_confirm = {"file": ("statement.csv", BytesIO(csv_bytes), "text/csv")}
    data = {"account_id": str(account.id), "format": "usaa"}

    prev_resp = client.post("/upload/preview", data=data, files=files_preview)
    assert prev_resp.status_code == 200
    prev_json = prev_resp.json()
    assert prev_json["total_rows"] == 3
    assert prev_json["valid_rows"] == 2
    assert prev_json["error_rows"] == 1
    assert prev_json["rows"][1]["row_number"] == 2
    assert "'NoneType' object has no attribute 'strip'" in prev_json["rows"][1]["parse_error"]

    conf_resp = client.post("/upload/confirm", data=data, files=files_confirm)
    assert conf_resp.status_code == 200
    conf_json = conf_resp.json()
    assert conf_json["imported"] == 2
    assert conf_json["skipped"] == 0
    assert len(conf_json["errors"]) == 1
    assert "Row 2: " in conf_json["errors"][0]
    assert "'NoneType' object has no attribute 'strip'" in conf_json["errors"][0]


def test_csv_confirm_ragged_rows_duplicate_reimport_preserves_count(client, db_session):
    """
    Verify re-importing a file containing ragged rows skips valid duplicates and preserves count.
    """
    account = models.Account(
        name="Checking",
        type="depository",
        current_balance=Decimal("0"),
        starting_balance=Decimal("0"),
        currency="USD",
    )
    db_session.add(account)
    db_session.commit()

    csv_bytes = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        b"2026-06-02,RAGGED MISSING STATUS,Food,-20.00\n"
        b"2026-06-03,VALID ROW 2,Auto,-30.00,posted\n"
    )
    data = {"account_id": str(account.id), "format": "usaa"}

    # First import: 2 imported, 1 error
    resp1 = client.post(
        "/upload/confirm",
        data=data,
        files={"file": ("statement.csv", BytesIO(csv_bytes), "text/csv")},
    )
    assert resp1.status_code == 200
    b1 = resp1.json()
    assert b1["imported"] == 2
    assert b1["skipped"] == 0
    assert len(b1["errors"]) == 1

    # Second import: 0 imported, 2 skipped, 1 error
    resp2 = client.post(
        "/upload/confirm",
        data=data,
        files={"file": ("statement.csv", BytesIO(csv_bytes), "text/csv")},
    )
    assert resp2.status_code == 200
    b2 = resp2.json()
    assert b2["imported"] == 0
    assert b2["skipped"] == 2
    assert len(b2["errors"]) == 1

    count = db_session.query(models.Transaction).filter_by(account_id=account.id).count()
    assert count == 2


