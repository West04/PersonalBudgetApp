from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend import models, schemas
from backend.access import csv_format_access
from backend.access.csv_format_access import (
    CSVFormatNameConflictError,
    CSVFormatDuplicateConfigurationError,
)


@pytest.fixture(autouse=True)
def clean_csv_formats(db_session):
    """Ensure csv_formats table is truncated before and after each test."""
    db_session.execute(text("TRUNCATE TABLE csv_formats CASCADE;"))
    db_session.commit()
    yield
    db_session.execute(text("TRUNCATE TABLE csv_formats CASCADE;"))
    db_session.commit()


# ---------------------------------------------------------------------------
# Schema Validation Tests
# ---------------------------------------------------------------------------

def test_schema_valid_custom_format_accepted():
    data = schemas.CSVFormatCreate(
        name="Chase Checking",
        date_column="Posting Date",
        description_column="Description",
        amount_column="Amount",
        status_column="Status",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_inflow",
        status_posted_value="cleared",
    )
    assert data.name == "Chase Checking"
    assert data.date_column == "Posting Date"
    assert data.description_column == "Description"
    assert data.amount_column == "Amount"
    assert data.status_column == "Status"
    assert data.date_format == "%m/%d/%Y"
    assert data.amount_sign_convention == "positive_is_inflow"
    assert data.status_posted_value == "cleared"


def test_schema_status_column_optional_and_normalized():
    # Explicit None
    data1 = schemas.CSVFormatCreate(
        name="Discover Custom",
        date_column="Trans. Date",
        description_column="Description",
        amount_column="Amount",
        status_column=None,
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
    )
    assert data1.status_column is None
    assert data1.status_posted_value is None

    # Whitespace normalized to None
    data2 = schemas.CSVFormatCreate(
        name="Discover Custom 2",
        date_column="Trans. Date",
        description_column="Description",
        amount_column="Amount",
        status_column="   ",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
    )
    assert data2.status_column is None
    assert data2.status_posted_value is None


def test_schema_no_status_column_canonicalizes_posted_value_to_none():
    """Verify status_posted_value is always canonicalized to None when status_column is absent."""
    # When omitted (default was "posted")
    c1 = schemas.CSVFormatCreate(
        name="Format Omitted",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column=None,
    )
    assert c1.status_posted_value is None

    # When explicitly passed as "posted"
    c2 = schemas.CSVFormatCreate(
        name="Format Explicit Posted",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column=None,
        status_posted_value="posted",
    )
    assert c2.status_posted_value is None

    # When explicitly passed as arbitrary token
    c3 = schemas.CSVFormatCreate(
        name="Format Arbitrary Token",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column=None,
        status_posted_value="anything_goes",
    )
    assert c3.status_posted_value is None


def test_schema_status_column_present_normalizes_posted_value():
    """Verify status_posted_value is normalized to trimmed lowercase, defaulting to 'posted'."""
    # Uppercase
    c1 = schemas.CSVFormatCreate(
        name="Format Uppercase",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column="Status",
        status_posted_value="  POSTED  ",
    )
    assert c1.status_posted_value == "posted"

    # Custom token trimmed and lowercased
    c2 = schemas.CSVFormatCreate(
        name="Format Custom Token",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column="Status",
        status_posted_value="  Cleared  ",
    )
    assert c2.status_posted_value == "cleared"

    # None or whitespace defaults to "posted"
    c3 = schemas.CSVFormatCreate(
        name="Format None Token",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column="Status",
        status_posted_value=None,
    )
    assert c3.status_posted_value == "posted"

    c4 = schemas.CSVFormatCreate(
        name="Format Whitespace Token",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column="Status",
        status_posted_value="   ",
    )
    assert c4.status_posted_value == "posted"


def test_schema_invalid_amount_sign_convention_rejected():
    with pytest.raises(ValidationError):
        schemas.CSVFormatCreate(
            name="Bad Format",
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="invalid_convention",  # type: ignore
        )


@pytest.mark.parametrize("blank_field", ["name", "date_column", "description_column", "amount_column", "date_format"])
def test_schema_blank_required_mappings_rejected(blank_field):
    valid_payload = {
        "name": "Valid Name",
        "date_column": "Date",
        "description_column": "Description",
        "amount_column": "Amount",
        "date_format": "%Y-%m-%d",
        "amount_sign_convention": "positive_is_outflow",
    }
    valid_payload[blank_field] = "   "
    with pytest.raises(ValidationError):
        schemas.CSVFormatCreate(**valid_payload)


def test_schema_duplicate_required_columns_rejected():
    with pytest.raises(ValidationError, match="must be distinct source columns"):
        schemas.CSVFormatCreate(
            name="Collision Format",
            date_column="Date",
            description_column="Date",  # Duplicate of date_column
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )


def test_schema_status_column_must_be_distinct():
    with pytest.raises(ValidationError, match="status_column must be distinct"):
        schemas.CSVFormatCreate(
            name="Collision Format",
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            status_column="Amount",  # Duplicate of amount_column
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )


# ---------------------------------------------------------------------------
# ResourceAccess Create / Read Tests
# ---------------------------------------------------------------------------

def test_create_and_get_by_id(db_session):
    created = csv_format_access.create_custom_format(
        db_session,
        name="Chase Sapphire",
        date_column="Transaction Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_outflow",
        status_column=None,
    )
    assert created.id is not None
    assert created.name == "Chase Sapphire"
    assert created.created_at is not None

    fetched = csv_format_access.get_custom_format_by_id(db_session, created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Chase Sapphire"
    assert fetched.date_column == "Transaction Date"
    assert fetched.description_column == "Description"
    assert fetched.amount_column == "Amount"
    assert fetched.status_column is None
    assert fetched.date_format == "%m/%d/%Y"
    assert fetched.amount_sign_convention == "positive_is_outflow"


def test_get_by_id_nonexistent_returns_none(db_session):
    assert csv_format_access.get_custom_format_by_id(db_session, uuid4()) is None


def test_get_by_name_case_insensitive(db_session):
    csv_format_access.create_custom_format(
        db_session,
        name="Navy Federal Checking",
        date_column="Date",
        description_column="Memo",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_inflow",
        status_column="Status",
        status_posted_value="Posted",
    )

    exact = csv_format_access.get_custom_format_by_name(db_session, "Navy Federal Checking")
    assert exact is not None
    assert exact.name == "Navy Federal Checking"

    lower = csv_format_access.get_custom_format_by_name(db_session, "navy federal checking")
    assert lower is not None
    assert lower.id == exact.id

    upper = csv_format_access.get_custom_format_by_name(db_session, "NAVY FEDERAL CHECKING")
    assert upper is not None
    assert upper.id == exact.id

    padded = csv_format_access.get_custom_format_by_name(db_session, "  navy federal checking  ")
    assert padded is not None
    assert padded.id == exact.id


def test_get_by_name_nonexistent_returns_none(db_session):
    assert csv_format_access.get_custom_format_by_name(db_session, "Nonexistent Bank") is None


def test_list_custom_formats_deterministic_ordering(db_session):
    names = ["Wells Fargo", "apple card", "Capital One", "barclays"]
    for i, name in enumerate(names):
        csv_format_access.create_custom_format(
            db_session,
            name=name,
            date_column=f"Date_{i}",
            description_column=f"Desc_{i}",
            amount_column=f"Amt_{i}",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )

    formats = csv_format_access.list_custom_formats(db_session)
    result_names = [f.name for f in formats]
    # Expected case-insensitive ordering: apple card, barclays, Capital One, Wells Fargo
    assert result_names == ["apple card", "barclays", "Capital One", "Wells Fargo"]


# ---------------------------------------------------------------------------
# Name Uniqueness & Reservation Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ["Chase Checking", "chase checking", "CHASE CHECKING", "  Chase Checking  "])
def test_create_rejects_duplicate_name_case_insensitively(db_session, variant):
    csv_format_access.create_custom_format(
        db_session,
        name="Chase Checking",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )

    with pytest.raises(CSVFormatNameConflictError, match="already exists"):
        csv_format_access.create_custom_format(
            db_session,
            name=variant,
            date_column="Posting Date",
            description_column="Memo",
            amount_column="Net Amount",
            date_format="%m/%d/%Y",
            amount_sign_convention="positive_is_inflow",
        )


@pytest.mark.parametrize("reserved_name", ["USAA", "usaa", "UsAa", "Discover", "discover", "DISCOVER", "  usaa  "])
def test_create_rejects_builtin_reserved_names(db_session, reserved_name):
    with pytest.raises(CSVFormatNameConflictError, match="reserved by built-in formats"):
        csv_format_access.create_custom_format(
            db_session,
            name=reserved_name,
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
        )


# ---------------------------------------------------------------------------
# Semantic Duplicate vs. Same-Headers Different-Semantics Tests
# ---------------------------------------------------------------------------

def test_create_rejects_exact_semantic_duplicate(db_session):
    # First format
    csv_format_access.create_custom_format(
        db_session,
        name="Bank A",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_inflow",
        status_column="Status",
        status_posted_value="posted",
    )

    # Second format with different name, but identical mapping configuration
    with pytest.raises(CSVFormatDuplicateConfigurationError, match="identical format configuration already exists"):
        csv_format_access.create_custom_format(
            db_session,
            name="Bank A Alternate Name",
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_inflow",
            status_column="Status",
            status_posted_value="posted",
        )


def test_create_rejects_duplicate_when_status_column_is_none_regardless_of_posted_value(db_session):
    """
    When status_column is None, status_posted_value is irrelevant.
    Formats with status_posted_value=None vs 'posted' vs 'anything' must be recognized as duplicate.
    """
    csv_format_access.create_custom_format(
        db_session,
        name="No Status Format Base",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column=None,
        status_posted_value=None,
    )

    # Attempt to create identical format with explicit 'posted'
    with pytest.raises(CSVFormatDuplicateConfigurationError, match="identical format configuration already exists"):
        csv_format_access.create_custom_format(
            db_session,
            name="No Status Format With Posted",
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
            status_column=None,
            status_posted_value="posted",
        )

    # Attempt to create identical format with arbitrary token
    with pytest.raises(CSVFormatDuplicateConfigurationError, match="identical format configuration already exists"):
        csv_format_access.create_custom_format(
            db_session,
            name="No Status Format With Arbitrary",
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
            status_column=None,
            status_posted_value="arbitrary_token",
        )


@pytest.mark.parametrize("case_variant", ["POSTED", "  Posted  ", "posted"])
def test_create_rejects_duplicate_with_case_variant_posted_value(db_session, case_variant):
    """
    When status_column is present, status_posted_value comparison is case-insensitive and trimmed.
    """
    csv_format_access.create_custom_format(
        db_session,
        name="Base Status Format",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column="Status",
        status_posted_value="posted",
    )

    with pytest.raises(CSVFormatDuplicateConfigurationError, match="identical format configuration already exists"):
        csv_format_access.create_custom_format(
            db_session,
            name=f"Variant Status Format {case_variant.strip()}",
            date_column="Date",
            description_column="Description",
            amount_column="Amount",
            date_format="%Y-%m-%d",
            amount_sign_convention="positive_is_outflow",
            status_column="Status",
            status_posted_value=case_variant,
        )


def test_create_permits_different_effective_posted_value(db_session):
    """
    When status_column is present, distinct posted values (e.g. 'posted' vs 'cleared')
    represent distinct parsing semantics and are both permitted.
    """
    fmt1 = csv_format_access.create_custom_format(
        db_session,
        name="Format Posted",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column="Status",
        status_posted_value="posted",
    )

    fmt2 = csv_format_access.create_custom_format(
        db_session,
        name="Format Cleared",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column="Status",
        status_posted_value="cleared",
    )

    assert fmt1.id != fmt2.id
    formats = csv_format_access.list_custom_formats(db_session)
    assert len(formats) == 2



def test_create_permits_same_headers_with_different_date_format(db_session):
    fmt1 = csv_format_access.create_custom_format(
        db_session,
        name="Format ISO Date",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )

    fmt2 = csv_format_access.create_custom_format(
        db_session,
        name="Format US Date",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%m/%d/%Y",  # Different date format
        amount_sign_convention="positive_is_outflow",
    )

    assert fmt1.id != fmt2.id
    formats = csv_format_access.list_custom_formats(db_session)
    assert len(formats) == 2


def test_create_permits_same_headers_with_different_amount_sign(db_session):
    fmt1 = csv_format_access.create_custom_format(
        db_session,
        name="Checking Account Format",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_inflow",  # Checking: purchases negative
    )

    fmt2 = csv_format_access.create_custom_format(
        db_session,
        name="Credit Card Format",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",  # Card: purchases positive
    )

    assert fmt1.id != fmt2.id
    formats = csv_format_access.list_custom_formats(db_session)
    assert len(formats) == 2


def test_create_permits_same_headers_with_different_status_configuration(db_session):
    fmt1 = csv_format_access.create_custom_format(
        db_session,
        name="Format Without Status",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column=None,
    )

    fmt2 = csv_format_access.create_custom_format(
        db_session,
        name="Format With Status",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
        status_column="Status",
        status_posted_value="posted",
    )

    assert fmt1.id != fmt2.id
    formats = csv_format_access.list_custom_formats(db_session)
    assert len(formats) == 2


# ---------------------------------------------------------------------------
# Database Invariant Enforcement Tests (Direct Model Level)
# ---------------------------------------------------------------------------

def test_db_level_case_insensitive_unique_index_enforced(db_session):
    """Verify PostgreSQL unique functional index on lower(name) blocks duplicates."""
    fmt1 = models.CSVFormat(
        name="Unique Name Card",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="positive_is_outflow",
    )
    db_session.add(fmt1)
    db_session.commit()

    fmt2 = models.CSVFormat(
        name="UNIQUE NAME CARD",  # Direct uppercase duplicate bypassing access check
        date_column="Posting Date",
        description_column="Memo",
        amount_column="Net",
        date_format="%m/%d/%Y",
        amount_sign_convention="positive_is_inflow",
    )
    db_session.add(fmt2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_db_level_amount_sign_check_constraint_enforced(db_session):
    """Verify database CheckConstraint blocks invalid amount_sign_convention."""
    fmt = models.CSVFormat(
        name="Invalid Sign Card",
        date_column="Date",
        description_column="Description",
        amount_column="Amount",
        date_format="%Y-%m-%d",
        amount_sign_convention="not_a_valid_sign",
    )
    db_session.add(fmt)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
