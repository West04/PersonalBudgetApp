from io import BytesIO
from decimal import Decimal
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
