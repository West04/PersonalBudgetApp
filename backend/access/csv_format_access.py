"""
Resource access functions for CSVFormat PostgreSQL resources.
"""

from collections.abc import Sequence
from typing import Any, Mapping, Optional, Union
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..bank_statement_loader import CSVFormatMatchDefinition, MappedCSVFormatConfig

RESERVED_FORMAT_NAMES: frozenset[str] = frozenset({"usaa", "discover"})


class CSVFormatAccessError(Exception):
    """Base exception for CSV format resource access errors."""
    pass


class CSVFormatNameConflictError(CSVFormatAccessError):
    """Raised when a format name is already in use or collides with a reserved built-in name."""
    pass


class CSVFormatDuplicateConfigurationError(CSVFormatAccessError):
    """Raised when an identical parsing configuration already exists under another name."""
    pass


def get_custom_format_by_id(
    db: Session,
    format_id: UUID,
) -> Optional[models.CSVFormat]:
    """
    Retrieves a single custom CSV format by UUID primary key.
    Does not commit or flush.
    """
    return (
        db.query(models.CSVFormat)
        .filter(models.CSVFormat.id == format_id)
        .first()
    )


def get_custom_format_by_name(
    db: Session,
    name: str,
) -> Optional[models.CSVFormat]:
    """
    Retrieves a custom CSV format by case-insensitive name match.
    Does not commit or flush.
    """
    cleaned_name = name.strip()
    return (
        db.query(models.CSVFormat)
        .filter(func.lower(models.CSVFormat.name) == cleaned_name.lower())
        .first()
    )


def list_custom_formats(
    db: Session,
) -> Sequence[models.CSVFormat]:
    """
    Lists all custom CSV formats ordered by name case-insensitively ascending.
    Does not commit or flush.
    """
    return (
        db.query(models.CSVFormat)
        .order_by(func.lower(models.CSVFormat.name).asc())
        .all()
    )


def create_custom_format(
    db: Session,
    format_data: Union[schemas.CSVFormatCreate, Mapping[str, Any], None] = None,
    *,
    name: Optional[str] = None,
    date_column: Optional[str] = None,
    description_column: Optional[str] = None,
    amount_column: Optional[str] = None,
    date_format: Optional[str] = None,
    amount_sign_convention: Optional[str] = None,
    status_column: Optional[str] = None,
    status_posted_value: Optional[str] = "posted",
) -> models.CSVFormat:
    """
    Creates and persists a new user-defined CSVFormat record:
    1. Validates input data through schemas.CSVFormatCreate.
    2. Rejects built-in reserved-name collisions ("usaa", "discover").
    3. Rejects case-insensitive custom-name collisions with existing formats.
    4. Rejects exact semantic duplicates (identical column mapping, date format,
       sign convention, and status configuration).
    5. Commits and refreshes the new models.CSVFormat record.
    """
    if isinstance(format_data, schemas.CSVFormatCreate):
        validated = format_data
    elif isinstance(format_data, Mapping):
        validated = schemas.CSVFormatCreate(**format_data)
    else:
        validated = schemas.CSVFormatCreate(
            name=name,  # type: ignore
            date_column=date_column,  # type: ignore
            description_column=description_column,  # type: ignore
            amount_column=amount_column,  # type: ignore
            date_format=date_format,  # type: ignore
            amount_sign_convention=amount_sign_convention,  # type: ignore
            status_column=status_column,
            status_posted_value=status_posted_value,
        )

    cleaned_name = validated.name.strip()

    # 1. Reject built-in reserved names
    if cleaned_name.lower() in RESERVED_FORMAT_NAMES:
        raise CSVFormatNameConflictError(
            f"Format name '{cleaned_name}' is reserved by built-in formats"
        )

    # 2. Reject case-insensitive custom name collision
    existing_by_name = get_custom_format_by_name(db, cleaned_name)
    if existing_by_name is not None:
        raise CSVFormatNameConflictError(
            f"Format with name '{cleaned_name}' already exists"
        )

    # 3. Reject exact semantic duplicate configuration
    sem_query = db.query(models.CSVFormat).filter(
        models.CSVFormat.date_column == validated.date_column,
        models.CSVFormat.description_column == validated.description_column,
        models.CSVFormat.amount_column == validated.amount_column,
        models.CSVFormat.date_format == validated.date_format,
        models.CSVFormat.amount_sign_convention == validated.amount_sign_convention,
    )
    if validated.status_column is None:
        sem_query = sem_query.filter(models.CSVFormat.status_column.is_(None))
    else:
        sem_query = sem_query.filter(
            models.CSVFormat.status_column == validated.status_column,
            func.lower(models.CSVFormat.status_posted_value) == validated.status_posted_value,
        )

    existing_dup = sem_query.first()
    if existing_dup is not None:
        raise CSVFormatDuplicateConfigurationError(
            f"An identical format configuration already exists with name '{existing_dup.name}'"
        )

    # 4. Instantiate model and persist
    csv_format = models.CSVFormat(
        name=cleaned_name,
        date_column=validated.date_column,
        description_column=validated.description_column,
        amount_column=validated.amount_column,
        status_column=validated.status_column,
        date_format=validated.date_format,
        amount_sign_convention=validated.amount_sign_convention,
        status_posted_value=validated.status_posted_value if validated.status_column else None,
    )

    db.add(csv_format)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CSVFormatNameConflictError(
            f"Format with name '{cleaned_name}' already exists"
        ) from exc

    db.refresh(csv_format)
    return csv_format


def csv_format_to_mapped_config(
    csv_format: models.CSVFormat,
) -> MappedCSVFormatConfig:
    """
    Converts a persisted models.CSVFormat ORM entity into an immutable
    MappedCSVFormatConfig parser configuration.
    Does not query, commit, flush, or mutate ORM state.
    """
    return MappedCSVFormatConfig(
        date_column=csv_format.date_column,
        description_column=csv_format.description_column,
        amount_column=csv_format.amount_column,
        status_column=csv_format.status_column,
        date_format=csv_format.date_format,
        amount_sign_convention=csv_format.amount_sign_convention,  # type: ignore[arg-type]
        status_posted_value=csv_format.status_posted_value,
    )


def csv_format_to_match_definition(
    csv_format: models.CSVFormat,
) -> CSVFormatMatchDefinition:
    """
    Converts a persisted models.CSVFormat ORM entity into an immutable
    CSVFormatMatchDefinition detection metadata object.
    Derives required_headers from the mapped parser configuration contract.
    Does not query, commit, flush, or mutate ORM state.
    """
    config = csv_format_to_mapped_config(csv_format)
    return CSVFormatMatchDefinition(
        identifier=str(csv_format.id),
        name=csv_format.name,
        required_headers=config.required_headers,
    )
