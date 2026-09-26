from decimal import Decimal, InvalidOperation
from uuid import uuid4
from datetime import date
import pytest

from backend.bank_statement_loader import (
    USAALoader,
    DiscoverLoader,
    get_loader,
    LOADER_REGISTRY
)


def test_usaa_loader_parsing_and_sign_inversion():
    """
    USAA exports charges/purchases as negative amounts, deposits as positive amounts.
    The application convention requires outflows (purchases) to be POSITIVE.
    Verify USAALoader inverts signs accordingly.
    """
    account_id = uuid4()
    loader = USAALoader(account_id=account_id)

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-05-15,HEB GROCERY,Food,-85.42,posted\n"
        "2026-05-16,PAYCHECK,Income,2450.00,posted\n"
        "2026-05-17,PENDING COFFEE,Food,-4.75,pending\n"
        "2026-05-18,ZERO DOLLAR ADJUSTMENT,Misc,0.00,posted\n"
    )

    transactions = loader.load_from_text(csv_content)
    assert len(transactions) == 4

    # 1. Purchase: raw -85.42 -> converted to +85.42 (outflow > 0)
    t1 = transactions[0]
    assert t1.account_id == account_id
    assert t1.date == date(2026, 5, 15)
    assert t1.description == "HEB GROCERY"
    assert t1.amount == Decimal("85.42")
    assert t1.pending is False

    # 2. Deposit: raw +2450.00 -> converted to -2450.00 (inflow < 0)
    t2 = transactions[1]
    assert t2.date == date(2026, 5, 16)
    assert t2.description == "PAYCHECK"
    assert t2.amount == Decimal("-2450.00")
    assert t2.pending is False

    # 3. Pending: status is 'pending' -> pending is True
    t3 = transactions[2]
    assert t3.amount == Decimal("4.75")
    assert t3.pending is True

    # 4. Zero amount: -0.00 -> Decimal('0.00')
    t4 = transactions[3]
    assert t4.amount == Decimal("0.00")


def test_discover_loader_parsing_and_sign_preservation():
    """
    Discover exports credit card charges as positive amounts.
    The application convention requires outflows to be POSITIVE.
    Verify DiscoverLoader preserves positive amounts.
    """
    account_id = uuid4()
    loader = DiscoverLoader(account_id=account_id)

    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "05/20/2026,TARGET STORE,64.21,Merchandise\n"
        "05/21/2026,ONLINE PAYMENT - THANK YOU,-200.00,Payments\n"
        "05/22/2026,REBATE REWARD,-15.50,Rewards\n"
    )

    transactions = loader.load_from_text(csv_content)
    assert len(transactions) == 3

    # 1. Charge: raw 64.21 -> preserved as +64.21 (outflow > 0)
    t1 = transactions[0]
    assert t1.account_id == account_id
    assert t1.date == date(2026, 5, 20)
    assert t1.description == "TARGET STORE"
    assert t1.amount == Decimal("64.21")
    assert t1.pending is False

    # 2. Payment received: raw -200.00 -> preserved as -200.00 (inflow/payment < 0)
    t2 = transactions[1]
    assert t2.date == date(2026, 5, 21)
    assert t2.description == "ONLINE PAYMENT - THANK YOU"
    assert t2.amount == Decimal("-200.00")

    # 3. Credit / Rebate: raw -15.50 -> preserved as -15.50
    t3 = transactions[2]
    assert t3.amount == Decimal("-15.50")


def test_missing_column_raises_value_error():
    account_id = uuid4()
    loader = USAALoader(account_id=account_id)

    # Missing "Status" column
    csv_missing_col = (
        "Date,Description,Category,Amount\n"
        "2026-05-15,HEB GROCERY,Food,-85.42\n"
    )

    with pytest.raises(ValueError, match="Missing columns"):
        loader.load_from_text(csv_missing_col)


def test_get_loader_factory():
    account_id = uuid4()

    usaa = get_loader("usaa", account_id)
    assert isinstance(usaa, USAALoader)

    discover = get_loader("discover", account_id)
    assert isinstance(discover, DiscoverLoader)

    with pytest.raises(ValueError, match="Unknown format 'chase'"):
        get_loader("chase", account_id)


# ---------------------------------------------------------------------------
# Row Parse Error Characterization (Current Behavior)
# ---------------------------------------------------------------------------

def test_usaa_loader_malformed_date_raises_value_error():
    """
    Characterize current behavior: USAALoader.load_from_text raises ValueError
    when a row contains an invalid date, aborting before parsing subsequent rows.
    """
    loader = USAALoader(account_id=uuid4())
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        "2026-99-99,BAD DATE,Food,-20.00,posted\n"
        "2026-06-03,VALID ROW 2,Food,-30.00,posted\n"
    )
    with pytest.raises(ValueError, match="does not match format '%Y-%m-%d'"):
        loader.load_from_text(csv_content)


def test_usaa_loader_malformed_amount_raises_invalid_operation():
    """
    Characterize current behavior: USAALoader.load_from_text raises decimal.InvalidOperation
    when a row contains a non-numeric amount.
    """
    loader = USAALoader(account_id=uuid4())
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        "2026-06-02,BAD AMOUNT,Food,NOT_A_NUMBER,posted\n"
        "2026-06-03,VALID ROW 2,Food,-30.00,posted\n"
    )
    with pytest.raises(InvalidOperation):
        loader.load_from_text(csv_content)


def test_discover_loader_malformed_date_raises_value_error():
    """
    Characterize current behavior: DiscoverLoader.load_from_text raises ValueError
    when a row contains an invalid date format.
    """
    loader = DiscoverLoader(account_id=uuid4())
    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "06/01/2026,VALID ROW 1,15.00,Merchandise\n"
        "99/99/2026,BAD DATE,25.00,Merchandise\n"
        "06/03/2026,VALID ROW 2,35.00,Merchandise\n"
    )
    with pytest.raises(ValueError, match="does not match format '%m/%d/%Y'"):
        loader.load_from_text(csv_content)


def test_discover_loader_malformed_amount_raises_invalid_operation():
    """
    Characterize current behavior: DiscoverLoader.load_from_text raises decimal.InvalidOperation
    when a row contains a non-numeric amount.
    """
    loader = DiscoverLoader(account_id=uuid4())
    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "06/01/2026,VALID ROW 1,15.00,Merchandise\n"
        "06/02/2026,BAD AMOUNT,INVALID_AMT,Merchandise\n"
        "06/03/2026,VALID ROW 2,35.00,Merchandise\n"
    )
    with pytest.raises(InvalidOperation):
        loader.load_from_text(csv_content)


# ---------------------------------------------------------------------------
# Tolerant Loader Tests (load_records_tolerant)
# ---------------------------------------------------------------------------

def test_usaa_loader_tolerant_mixed_valid_and_errors():
    """Verify load_records_tolerant parses valid rows and isolates errors for USAA."""
    loader = USAALoader(account_id=uuid4())
    csv_bytes = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        b"2026-99-99,BAD DATE,Food,-20.00,posted\n"
        b"2026-06-03,VALID ROW 2,Food,-30.00,posted\n"
        b"2026-06-04,BAD AMOUNT,Food,NOT_NUM,posted\n"
    )
    parsed = loader.load_records_tolerant(csv_bytes)
    assert len(parsed.valid_transactions) == 2
    assert len(parsed.row_errors) == 2
    assert parsed.valid_transactions[0].description == "VALID ROW 1"
    assert parsed.valid_transactions[1].description == "VALID ROW 2"
    assert "Row 2: " in parsed.row_errors[0]
    assert "Row 4: " in parsed.row_errors[1]


def test_discover_loader_tolerant_mixed_valid_and_errors():
    """Verify load_records_tolerant parses valid rows and isolates errors for Discover."""
    loader = DiscoverLoader(account_id=uuid4())
    csv_bytes = (
        b"Trans. Date,Description,Amount,Category\n"
        b"06/01/2026,VALID ROW 1,15.00,Merchandise\n"
        b"99/99/2026,BAD DATE,25.00,Merchandise\n"
        b"06/03/2026,VALID ROW 2,35.00,Merchandise\n"
        b"06/04/2026,BAD AMOUNT,NOT_NUM,Merchandise\n"
    )
    parsed = loader.load_records_tolerant(csv_bytes)
    assert len(parsed.valid_transactions) == 2
    assert len(parsed.row_errors) == 2
    assert parsed.valid_transactions[0].description == "VALID ROW 1"
    assert parsed.valid_transactions[1].description == "VALID ROW 2"
    assert "Row 2: " in parsed.row_errors[0]
    assert "Row 4: " in parsed.row_errors[1]


def test_loader_tolerant_all_valid():
    """Verify load_records_tolerant returns empty row_errors when all rows are valid."""
    loader = USAALoader(account_id=uuid4())
    csv_bytes = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-06-01,ROW 1,Food,-10.00,posted\n"
        b"2026-06-02,ROW 2,Food,-20.00,posted\n"
    )
    parsed = loader.load_records_tolerant(csv_bytes)
    assert len(parsed.valid_transactions) == 2
    assert parsed.row_errors == ()


def test_loader_tolerant_all_malformed():
    """Verify load_records_tolerant returns empty valid_transactions when all rows are malformed."""
    loader = USAALoader(account_id=uuid4())
    csv_bytes = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-99-99,BAD DATE,Food,-10.00,posted\n"
        b"2026-06-02,BAD AMOUNT,Food,NOT_NUM,posted\n"
    )
    parsed = loader.load_records_tolerant(csv_bytes)
    assert parsed.valid_transactions == ()
    assert len(parsed.row_errors) == 2
    assert "Row 1: " in parsed.row_errors[0]
    assert "Row 2: " in parsed.row_errors[1]


def test_loader_tolerant_missing_headers_raises_value_error():
    """Verify load_records_tolerant raises ValueError upfront when required headers are missing."""
    loader = USAALoader(account_id=uuid4())
    csv_bytes = (
        b"Date,Description,Category,Amount\n"
        b"2026-06-01,ROW 1,Food,-10.00\n"
    )
    with pytest.raises(ValueError, match=r"Missing columns: \['Status'\]"):
        loader.load_records_tolerant(csv_bytes)


# ---------------------------------------------------------------------------
# Ragged / Short Row Characterization & Tolerant Tests
# ---------------------------------------------------------------------------

def test_usaa_loader_strict_ragged_row_raises_attribute_error():
    """
    Characterize strict behavior: USAALoader.load_from_text raises AttributeError
    when a row is ragged (missing columns causes DictReader to set values to None).
    """
    loader = USAALoader(account_id=uuid4())
    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,STORE,Food,-10.00\n"
    )
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'strip'"):
        loader.load_from_text(csv_content)


def test_discover_loader_strict_ragged_row_raises_attribute_error():
    """
    Characterize strict behavior: DiscoverLoader.load_from_text raises AttributeError
    when a row is ragged (missing columns causes DictReader to set values to None).
    """
    loader = DiscoverLoader(account_id=uuid4())
    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "06/01/2026,STORE,10.00\n"
    )
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'strip'"):
        loader.load_from_text(csv_content)


def test_usaa_loader_tolerant_ragged_rows():
    """Verify load_records_tolerant isolates ragged-row AttributeErrors and imports valid rows."""
    loader = USAALoader(account_id=uuid4())
    csv_bytes = (
        b"Date,Description,Category,Amount,Status\n"
        b"2026-06-01,VALID ROW 1,Food,-10.00,posted\n"
        b"2026-06-02,RAGGED MISSING STATUS,Food,-20.00\n"
        b"2026-06-03,RAGGED MISSING AMOUNT AND STATUS,Food\n"
        b"2026-06-04,VALID ROW 2,Food,-40.00,posted\n"
    )
    parsed = loader.load_records_tolerant(csv_bytes)
    assert len(parsed.valid_transactions) == 2
    assert len(parsed.row_errors) == 2
    assert parsed.valid_transactions[0].description == "VALID ROW 1"
    assert parsed.valid_transactions[1].description == "VALID ROW 2"
    assert "Row 2: " in parsed.row_errors[0]
    assert "Row 3: " in parsed.row_errors[1]


def test_discover_loader_tolerant_ragged_rows():
    """Verify load_records_tolerant isolates ragged-row AttributeErrors for Discover."""
    loader = DiscoverLoader(account_id=uuid4())
    csv_bytes = (
        b"Trans. Date,Description,Amount,Category\n"
        b"06/01/2026,VALID ROW 1,15.00,Merchandise\n"
        b"06/02/2026,RAGGED MISSING CATEGORY,25.00\n"
        b"06/03/2026,RAGGED MISSING AMOUNT AND CATEGORY\n"
        b"06/04/2026,VALID ROW 2,45.00,Merchandise\n"
    )
    parsed = loader.load_records_tolerant(csv_bytes)
    assert len(parsed.valid_transactions) == 2
    assert len(parsed.row_errors) == 2
    assert parsed.valid_transactions[0].description == "VALID ROW 1"
    assert parsed.valid_transactions[1].description == "VALID ROW 2"
    assert "Row 2: " in parsed.row_errors[0]
    assert "Row 3: " in parsed.row_errors[1]



