from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4
import pytest

from backend.bank_statement_loader import (
    BankStatementLoader,
    MappedCSVFormatConfig,
    MappedStatementLoader,
)


# ---------------------------------------------------------------------------
# Basic Mapped Parsing & Sign Conventions
# ---------------------------------------------------------------------------

def test_basic_mapped_parsing_positive_is_outflow():
    """
    Verify basic custom format mapping with positive_is_outflow sign convention
    and no status column (pending defaults to False).
    """
    account_id = uuid4()
    config = MappedCSVFormatConfig(
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Value",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
        status_column=None,
    )
    loader = MappedStatementLoader(account_id=account_id, config=config)

    csv_content = (
        "Posting Date,Memo,Value\n"
        "09/01/2026,Coffee Shop,6.25\n"
        "09/02/2026,Payroll,-2500.00\n"
    )

    transactions = loader.load_from_text(csv_content)
    assert len(transactions) == 2

    # Row 1: Coffee Shop purchase -> positive outflow
    t1 = transactions[0]
    assert t1.account_id == account_id
    assert t1.date == date(2026, 9, 1)
    assert t1.description == "Coffee Shop"
    assert t1.amount == Decimal("6.25")
    assert t1.pending is False

    # Row 2: Payroll credit -> negative inflow
    t2 = transactions[1]
    assert t2.account_id == account_id
    assert t2.date == date(2026, 9, 2)
    assert t2.description == "Payroll"
    assert t2.amount == Decimal("-2500.00")
    assert t2.pending is False


def test_mapped_parsing_positive_is_inflow_inversion():
    """
    Verify positive_is_inflow sign convention inverts amount signs
    so that charges (negative in source) become positive outflows,
    and deposits (positive in source) become negative inflows.
    """
    account_id = uuid4()
    config = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_inflow",
    )
    loader = MappedStatementLoader(account_id=account_id, config=config)

    csv_content = (
        "Date,Description,Amount\n"
        "2026-09-01,Groceries,-85.00\n"
        "2026-09-02,Payroll,2500.00\n"
    )

    transactions = loader.load_from_text(csv_content)
    assert len(transactions) == 2

    # Groceries: raw -85.00 -> inverted to +85.00 (outflow)
    assert transactions[0].amount == Decimal("85.00")

    # Payroll: raw +2500.00 -> inverted to -2500.00 (inflow)
    assert transactions[1].amount == Decimal("-2500.00")


# ---------------------------------------------------------------------------
# Status Mapping & Case-Insensitive Normalization
# ---------------------------------------------------------------------------

def test_status_mapping_case_insensitivity_and_trimming():
    """
    Verify status column comparison against status_posted_value:
    - Matches (case-insensitive, trimmed) -> pending = False
    - Non-matches -> pending = True
    """
    account_id = uuid4()
    config = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Desc",
        amount_column="Amt",
        status_column="State",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_posted_value="posted",
    )
    loader = MappedStatementLoader(account_id=account_id, config=config)

    csv_content = (
        "Date,Desc,Amt,State\n"
        "2026-09-01,EXACT POSTED,10.00,posted\n"
        "2026-09-02,UPPER POSTED,20.00,POSTED\n"
        "2026-09-03,WHITESPACE POSTED,30.00, Posted \n"
        "2026-09-04,PENDING TXN,40.00,pending\n"
        "2026-09-05,PROCESSING TXN,50.00,processing\n"
    )

    transactions = loader.load_from_text(csv_content)
    assert len(transactions) == 5

    assert transactions[0].pending is False
    assert transactions[1].pending is False
    assert transactions[2].pending is False
    assert transactions[3].pending is True
    assert transactions[4].pending is True


def test_status_mapping_custom_posted_value():
    """Verify custom status_posted_value (e.g. 'cleared') correctly resolves."""
    account_id = uuid4()
    config = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Desc",
        amount_column="Amt",
        status_column="Status",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_posted_value="cleared",
    )
    loader = MappedStatementLoader(account_id=account_id, config=config)

    csv_content = (
        "Date,Desc,Amt,Status\n"
        "2026-09-01,CLEARED TXN,10.00,Cleared\n"
        "2026-09-02,POSTED TXN,20.00,posted\n"
    )

    txns = loader.load_from_text(csv_content)
    assert txns[0].pending is False  # 'Cleared' matches 'cleared'
    assert txns[1].pending is True   # 'posted' != 'cleared'


# ---------------------------------------------------------------------------
# Custom Date Formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fmt,date_str,expected_date",
    [
        ("%Y-%m-%d", "2026-09-15", date(2026, 9, 15)),
        ("%m/%d/%Y", "09/15/2026", date(2026, 9, 15)),
        ("%d/%m/%Y", "15/09/2026", date(2026, 9, 15)),
    ],
)
def test_custom_date_formats(fmt, date_str, expected_date):
    """Verify separate MappedCSVFormatConfig instances parse their explicit date formats."""
    config = MappedCSVFormatConfig(
        date_column="TxDate",
        description_column="Desc",
        amount_column="Amount",
        date_format=fmt,
        amount_sign_convention="positive_is_outflow",
    )
    loader = MappedStatementLoader(account_id=uuid4(), config=config)
    csv_content = f"TxDate,Desc,Amount\n{date_str},STORE,12.34\n"

    txns = loader.load_from_text(csv_content)
    assert len(txns) == 1
    assert txns[0].date == expected_date


# ---------------------------------------------------------------------------
# Required Headers & Column Mapping Invariants
# ---------------------------------------------------------------------------

def test_mapped_loader_required_headers_derivation():
    """Verify required_headers derive from configured mapped columns."""
    # 1. Without status column
    cfg1 = MappedCSVFormatConfig(
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Value",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
    )
    loader1 = MappedStatementLoader(account_id=uuid4(), config=cfg1)
    assert cfg1.required_headers == frozenset({"Posting Date", "Memo", "Value"})
    assert loader1.column_map == {
        "Posting Date": "date",
        "Memo": "description",
        "Value": "amount",
    }

    # 2. With status column
    cfg2 = MappedCSVFormatConfig(
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Value",
        status_column="State",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
    )
    loader2 = MappedStatementLoader(account_id=uuid4(), config=cfg2)
    assert cfg2.required_headers == frozenset({"Posting Date", "Memo", "Value", "State"})
    assert loader2.column_map == {
        "Posting Date": "date",
        "Memo": "description",
        "Value": "amount",
        "State": "status",
    }


def test_invalid_sign_convention_rejected_at_construction():
    """Verify invalid sign convention raises ValueError at config construction time."""
    # Invalid values raise ValueError
    with pytest.raises(ValueError, match="Invalid amount_sign_convention"):
        MappedCSVFormatConfig(
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="invalid",
        )

    with pytest.raises(ValueError, match="Invalid amount_sign_convention"):
        MappedCSVFormatConfig(
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="typo",
        )

    # Valid values construct cleanly
    cfg_outflow = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    assert cfg_outflow.amount_sign_convention == "positive_is_outflow"

    cfg_inflow = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_inflow",
    )
    assert cfg_inflow.amount_sign_convention == "positive_is_inflow"


def test_duplicate_column_mappings_rejected_at_construction():
    """Verify duplicate column mappings raise ValueError at config construction time."""
    # 1. date_column == description_column
    with pytest.raises(ValueError, match="must be distinct"):
        MappedCSVFormatConfig(
            date_column="Date",
            description_column="Date",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )

    # 2. date_column == amount_column
    with pytest.raises(ValueError, match="must be distinct"):
        MappedCSVFormatConfig(
            date_column="Date",
            description_column="Description",
            amount_column="Date",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )

    # 3. description_column == amount_column
    with pytest.raises(ValueError, match="must be distinct"):
        MappedCSVFormatConfig(
            date_column="Date",
            description_column="Amount",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )

    # 4. status_column == date_column
    with pytest.raises(ValueError, match="status_column cannot be the same"):
        MappedCSVFormatConfig(
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            status_column="Date",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )

    # 5. status_column == description_column
    with pytest.raises(ValueError, match="status_column cannot be the same"):
        MappedCSVFormatConfig(
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            status_column="Description",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )

    # 6. status_column == amount_column
    with pytest.raises(ValueError, match="status_column cannot be the same"):
        MappedCSVFormatConfig(
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            status_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )


def test_missing_mapped_header_raises_value_error():
    """Verify loader raises missing-column ValueError when a configured mapped header is absent."""
    config = MappedCSVFormatConfig(
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Value",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
    )
    loader = MappedStatementLoader(account_id=uuid4(), config=config)

    # Missing 'Memo' (has 'Description' instead)
    csv_missing = (
        "Posting Date,Description,Value\n"
        "09/01/2026,Coffee Shop,6.25\n"
    )

    with pytest.raises(ValueError, match="Missing columns"):
        loader.load_from_text(csv_missing)

    with pytest.raises(ValueError, match="Missing columns"):
        loader.load_records_tolerant(csv_missing.encode("utf-8"))


def test_extra_headers_allowed():
    """Verify CSV files containing all required headers plus extra columns parse cleanly."""
    config = MappedCSVFormatConfig(
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Value",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
    )
    loader = MappedStatementLoader(account_id=uuid4(), config=config)

    csv_extra = (
        "Posting Date,Memo,Value,Reference,Branch,Balance\n"
        "09/01/2026,STORE,15.50,REF123,Main Branch,500.00\n"
    )

    txns = loader.load_from_text(csv_extra)
    assert len(txns) == 1
    assert txns[0].description == "STORE"
    assert txns[0].amount == Decimal("15.50")


def test_header_case_and_whitespace_exactness():
    """Verify mapped loader enforces exact header spelling without whitespace or case stripping."""
    config = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    loader = MappedStatementLoader(account_id=uuid4(), config=config)

    # 1. Whitespace mismatch
    csv_ws = " Date ,Description,Amount\n2026-09-01,STORE,10.00\n"
    with pytest.raises(ValueError, match=r"Missing columns: \['Date'\]"):
        loader.load_from_text(csv_ws)

    # 2. Case mismatch
    csv_case = "date,Description,Amount\n2026-09-01,STORE,10.00\n"
    with pytest.raises(ValueError, match=r"Missing columns: \['Date'\]"):
        loader.load_from_text(csv_case)


# ---------------------------------------------------------------------------
# Strict vs Tolerant Parsing & Error Isolation
# ---------------------------------------------------------------------------

def test_bad_date_strict_raises_tolerant_isolates():
    """Verify bad date raises ValueError in strict mode and is isolated in tolerant mode."""
    config = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    loader = MappedStatementLoader(account_id=uuid4(), config=config)

    csv_content = (
        "Date,Description,Amount\n"
        "2026-09-01,VALID ROW 1,10.00\n"
        "not-a-date,BAD DATE ROW,20.00\n"
        "2026-09-03,VALID ROW 2,30.00\n"
    )

    # Strict: raises ValueError
    with pytest.raises(ValueError, match="does not match format '%Y-%m-%d'"):
        loader.load_from_text(csv_content)

    # Tolerant: isolates row error, imports valid rows
    parsed = loader.load_records_tolerant(csv_content.encode("utf-8"))
    assert len(parsed.valid_transactions) == 2
    assert len(parsed.row_errors) == 1
    assert parsed.valid_transactions[0].description == "VALID ROW 1"
    assert parsed.valid_transactions[1].description == "VALID ROW 2"
    assert "Row 2: " in parsed.row_errors[0]


def test_bad_amount_strict_raises_tolerant_isolates():
    """Verify non-numeric amount raises InvalidOperation in strict mode and is isolated in tolerant mode."""
    config = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    loader = MappedStatementLoader(account_id=uuid4(), config=config)

    csv_content = (
        "Date,Description,Amount\n"
        "2026-09-01,VALID ROW 1,10.00\n"
        "2026-09-02,BAD AMOUNT,abcde\n"
        "2026-09-03,VALID ROW 2,30.00\n"
    )

    # Strict: raises InvalidOperation
    with pytest.raises(InvalidOperation):
        loader.load_from_text(csv_content)

    # Tolerant: isolates row error
    parsed = loader.load_records_tolerant(csv_content.encode("utf-8"))
    assert len(parsed.valid_transactions) == 2
    assert len(parsed.row_errors) == 1
    assert parsed.valid_transactions[0].description == "VALID ROW 1"
    assert parsed.valid_transactions[1].description == "VALID ROW 2"
    assert "Row 2: " in parsed.row_errors[0]


def test_ragged_row_tolerant_isolates():
    """Verify row missing mapped columns (ragged) is isolated in tolerant mode."""
    config = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        status_column="Status",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    loader = MappedStatementLoader(account_id=uuid4(), config=config)

    csv_bytes = (
        b"Date,Description,Amount,Status\n"
        b"2026-09-01,VALID ROW 1,10.00,posted\n"
        b"2026-09-02,RAGGED MISSING STATUS,20.00\n"
        b"2026-09-03,VALID ROW 2,30.00,posted\n"
    )

    # Strict: raises AttributeError from DictReader None value
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'strip'"):
        loader.load_from_text(csv_bytes.decode("utf-8"))

    # Tolerant: isolates row 2 error
    parsed = loader.load_records_tolerant(csv_bytes)
    assert len(parsed.valid_transactions) == 2
    assert len(parsed.row_errors) == 1
    assert parsed.valid_transactions[0].description == "VALID ROW 1"
    assert parsed.valid_transactions[1].description == "VALID ROW 2"
    assert "Row 2: " in parsed.row_errors[0]


# ---------------------------------------------------------------------------
# Account ID Propagation & Loader Method Reuse
# ---------------------------------------------------------------------------

def test_account_id_propagation_across_all_loading_helpers():
    """Verify load_from_text, load_from_bytes, and load_records_tolerant propagate account_id."""
    account_id = uuid4()
    config = MappedCSVFormatConfig(
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    loader = MappedStatementLoader(account_id=account_id, config=config)

    csv_text = "Date,Description,Amount\n2026-09-01,ITEM,15.00\n"
    csv_bytes = csv_text.encode("utf-8")

    # 1. load_from_text
    t_text = loader.load_from_text(csv_text)
    assert t_text[0].account_id == account_id

    # 2. load_from_bytes
    t_bytes = loader.load_from_bytes(csv_bytes)
    assert t_bytes[0].account_id == account_id

    # 3. load_records_tolerant
    parsed = loader.load_records_tolerant(csv_bytes)
    assert parsed.valid_transactions[0].account_id == account_id
