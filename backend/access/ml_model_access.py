"""
Resource access functions for ML model persistence, metadata, and training datasets.

Coordinates:
1. Querying eligible training examples from PostgreSQL models.Transaction.
2. Managing PostgreSQL models.MLModelMetadata single-row state and revisions.
3. Managing local joblib model artifact serialization, atomic replacement, and file I/O.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import logging
import os
from typing import Any, Optional, Sequence
from uuid import UUID
import joblib
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)

# Base directory for local model artifacts. Defaults to data/models in current working directory.
DEFAULT_MODEL_DIR = os.getenv(
    "MODEL_DIR",
    os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data", "models"),
)
ACTIVE_MODEL_FILENAME = "active_model.joblib"
TEMP_CANDIDATE_FILENAME = "candidate_model_temp.joblib"


@dataclass(frozen=True)
class MLTrainingExample:
    transaction_id: UUID
    merchant: Optional[str]
    description: Optional[str]
    category_id: UUID
    category_source: Optional[str]


def get_model_storage_dir() -> str:
    """Returns absolute path to the local model storage directory, creating it if needed."""
    model_dir = os.path.abspath(DEFAULT_MODEL_DIR)
    os.makedirs(model_dir, exist_ok=True)
    return model_dir


def get_active_model_path() -> str:
    return os.path.join(get_model_storage_dir(), ACTIVE_MODEL_FILENAME)


def get_temp_candidate_path() -> str:
    return os.path.join(get_model_storage_dir(), TEMP_CANDIDATE_FILENAME)


def artifact_exists() -> bool:
    """Checks whether the active serialized model artifact exists on disk."""
    return os.path.isfile(get_active_model_path())


def get_model_artifact_size_bytes() -> int:
    """Returns size of active model artifact in bytes, or 0 if missing."""
    p = get_active_model_path()
    return os.path.getsize(p) if os.path.isfile(p) else 0


def load_active_model() -> Optional[Any]:
    """
    Loads and deserializes the active model pipeline from disk using joblib.
    Returns None if the artifact does not exist or fails to load.
    """
    path = get_active_model_path()
    if not os.path.isfile(path):
        return None
    try:
        return joblib.load(path)
    except Exception as exc:
        logger.warning("Failed to load active ML model from %s: %s", path, exc)
        return None


def save_candidate_model(pipeline: Any) -> str:
    """
    Serializes a candidate pipeline to a temporary artifact file and validates load.
    Returns the path to the validated temporary file.
    """
    temp_path = get_temp_candidate_path()
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass

    joblib.dump(pipeline, temp_path)
    # Validate deserialization
    loaded = joblib.load(temp_path)
    if loaded is None:
        raise ValueError("Candidate model failed round-trip validation.")
    return temp_path


def activate_candidate_model(temp_path: str) -> None:
    """
    Atomically activates the candidate model by replacing the active model file.
    POSIX os.replace guarantees atomic replacement.
    """
    active_path = get_active_model_path()
    os.replace(temp_path, active_path)


def cleanup_temp_candidate(temp_path: Optional[str] = None) -> None:
    """Safely removes candidate temporary file if it exists."""
    p = temp_path or get_temp_candidate_path()
    if p and os.path.isfile(p):
        try:
            os.remove(p)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# PostgreSQL Training Data & Metadata Queries
# ---------------------------------------------------------------------------

def get_ml_training_examples(
    db: Session,
    eligible_sources: Sequence[str] = ("manual", "ml", "legacy"),
) -> list[MLTrainingExample]:
    """
    Queries all transactions eligible for supervised ML training:
    - Must have category_id IS NOT NULL.
    - Must NOT be confirmed transfers (is_transfer == False).
    - Category source must be in approved eligible sources (manual, ml, legacy).
      Rule-generated categories ('rule') and unassigned categories are strictly excluded.
    - Associated Category must currently exist in categories table.
    Returns plain Python MLTrainingExample dataclass instances.
    """
    rows = (
        db.query(
            models.Transaction.transaction_id,
            models.Transaction.merchant,
            models.Transaction.description,
            models.Transaction.category_id,
            models.Transaction.category_source,
        )
        .join(models.Category, models.Category.category_id == models.Transaction.category_id)
        .filter(
            models.Transaction.category_id.isnot(None),
            models.Transaction.is_transfer == False,
            models.Transaction.category_source.in_(eligible_sources),
        )
        .all()
    )

    return [
        MLTrainingExample(
            transaction_id=r.transaction_id,
            merchant=r.merchant,
            description=r.description,
            category_id=r.category_id,
            category_source=r.category_source,
        )
        for r in rows
    ]


def get_model_metadata(db: Session) -> models.MLModelMetadata:
    """
    Retrieves the single-row ML model metadata record (id=1).
    Creates and flushes default row if missing.
    """
    meta = db.query(models.MLModelMetadata).filter(models.MLModelMetadata.id == 1).first()
    if meta is None:
        meta = models.MLModelMetadata(
            id=1,
            current_training_revision=0,
            trained_revision=0,
            training_example_count=0,
            model_available=False,
            status_message="Needs more data",
        )
        db.add(meta)
        db.flush()
    return meta


def increment_training_revision(db: Session) -> int:
    """
    Increments the current_training_revision counter when a human provides or corrects
    an eligible category label. Flushes to session without committing so caller controls boundary.
    Returns updated revision integer.
    """
    meta = get_model_metadata(db)
    meta.current_training_revision += 1
    db.add(meta)
    db.flush()
    return meta.current_training_revision


def update_model_metadata_after_training(
    db: Session,
    trained_revision: int,
    training_example_count: int,
    model_available: bool,
    accuracy: Optional[float] = None,
    macro_f1: Optional[float] = None,
    top2_accuracy: Optional[float] = None,
    coverage: Optional[float] = None,
    status_message: Optional[str] = None,
) -> models.MLModelMetadata:
    """
    Updates the MLModelMetadata record with newly trained model properties.
    Flushes to session without committing.
    """
    meta = get_model_metadata(db)
    meta.trained_revision = trained_revision
    meta.trained_at = datetime.now(timezone.utc)
    meta.training_example_count = training_example_count
    meta.model_available = model_available
    meta.accuracy = Decimal(str(accuracy)) if accuracy is not None else None
    meta.macro_f1 = Decimal(str(macro_f1)) if macro_f1 is not None else None
    meta.top2_accuracy = Decimal(str(top2_accuracy)) if top2_accuracy is not None else None
    meta.coverage = Decimal(str(coverage)) if coverage is not None else None
    meta.status_message = status_message
    db.add(meta)
    db.flush()
    return meta
