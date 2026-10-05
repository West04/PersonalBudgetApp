"""
FastAPI router for Categorization Rules management and retroactive execution.
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas
from ..access import categorization_rule_access
from ..database import get_db
from ..managers import categorization_rule_manager

router = APIRouter(
    prefix="/rules",
    tags=["Categorization Rules"],
)


@router.get("/", response_model=List[schemas.CategorizationRuleRead])
def list_rules(db: Session = Depends(get_db)):
    """
    Lists all active categorization rules ordered by merchant.
    """
    return categorization_rule_access.get_rules(db)


@router.post("/", response_model=schemas.CategorizationRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: schemas.CategorizationRuleCreate,
    db: Session = Depends(get_db),
):
    """
    Creates a new categorization rule.
    Refuses duplicate merchants (case-insensitive) and nonexistent categories.
    """
    try:
        return categorization_rule_access.create_rule(
            db=db,
            merchant=payload.merchant,
            category_id=payload.category_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/{rule_id}", response_model=schemas.CategorizationRuleRead)
def get_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Retrieves a single categorization rule by ID.
    """
    rule = categorization_rule_access.get_rule_by_id(db=db, rule_id=rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categorization rule not found.",
        )
    return rule


@router.put("/{rule_id}", response_model=schemas.CategorizationRuleRead)
def update_rule(
    rule_id: UUID,
    payload: schemas.CategorizationRuleUpdate,
    db: Session = Depends(get_db),
):
    """
    Updates an existing categorization rule.
    """
    try:
        updated = categorization_rule_access.update_rule(
            db=db,
            rule_id=rule_id,
            merchant=payload.merchant,
            category_id=payload.category_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categorization rule not found.",
        )
    return updated


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Deletes a categorization rule.
    Future transactions will no longer be categorized by this rule.
    Existing transactions remain unchanged.
    """
    deleted = categorization_rule_access.delete_rule(db=db, rule_id=rule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categorization rule not found.",
        )
    return None


@router.get("/{rule_id}/preview", response_model=schemas.CategorizationRulePreviewResponse)
def preview_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Counts uncategorized transactions that would be matched by this rule retroactively.
    """
    try:
        count = categorization_rule_manager.preview_rule_matches(db=db, rule_id=rule_id)
        rule = categorization_rule_access.get_rule_by_id(db=db, rule_id=rule_id)
        return schemas.CategorizationRulePreviewResponse(
            rule_id=rule.id,
            merchant=rule.merchant,
            category_id=rule.category_id,
            matching_count=count,
        )
    except categorization_rule_manager.CategorizationRuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post("/{rule_id}/apply", response_model=schemas.CategorizationRuleBatchApplyResponse)
def apply_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Applies a categorization rule retroactively to all matching uncategorized transactions.
    Transactions with existing categories are never modified.
    """
    try:
        count = categorization_rule_manager.apply_rule_to_uncategorized(db=db, rule_id=rule_id)
        return schemas.CategorizationRuleBatchApplyResponse(
            rule_id=rule_id,
            applied_count=count,
        )
    except categorization_rule_manager.CategorizationRuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
