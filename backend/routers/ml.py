"""
FastAPI router for ML Categorization status and manual retraining control.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..managers import ml_categorization_manager

router = APIRouter(
    prefix="/ml",
    tags=["ML Categorization"],
)


@router.get("/status", response_model=schemas.MLModelStatusRead)
def get_ml_status(
    db: Session = Depends(get_db),
):
    """
    Returns current ML categorization model status, training example count,
    revisions, and recent evaluation metrics.
    """
    return ml_categorization_manager.get_ml_status(db)


@router.post("/retrain", response_model=schemas.MLRetrainResponse)
def retrain_model(
    force: bool = False,
    db: Session = Depends(get_db),
):
    """
    Triggers local supervised retraining of the TF-IDF + Logistic Regression candidate model.
    Evaluates against test split and simple merchant baseline.
    Replaces active model only if candidate meets quality gates.
    """
    success, message, activated, model_status = ml_categorization_manager.retrain_model(
        db=db,
        force=force,
    )
    return schemas.MLRetrainResponse(
        success=success,
        message=message,
        model_activated=activated,
        status=model_status,
    )
