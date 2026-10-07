"""
Workflow Manager for Manual Transaction Mutations.

Coordinates:
1. Normalizing merchant or recording user override.
2. Resolving category (manual with ML revision bump vs merchant rule fallback).
3. Staging entity via transaction_access.stage_manual_transaction.
4. Owning atomic commit and refresh.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from .. import models
from ..access import categorization_rule_access, ml_model_access, transaction_access
from ..domain.merchant_normalization import normalize_merchant


def create_transaction(
    db: Session,
    account_id: UUID,
    category_id: Optional[UUID],
    description: str,
    amount: Decimal,
    transaction_date: date,
    transaction_datetime: Optional[datetime] = None,
    pending: bool = False,
    is_reviewed: bool = False,
    plaid_transaction_id: Optional[str] = None,
    merchant: Optional[str] = None,
) -> models.Transaction:
    """
    Coordinates manual transaction creation:
    1. Resolve merchant identity:
       - explicit nonblank merchant: strip and set is_merchant_overridden=True
       - omitted / blank merchant: normalize_merchant(description) and set is_merchant_overridden=False
    2. Resolve category and ML training revision:
       - category_id provided: assigned category_id=category_id, category_source="manual", increment ML revision
       - category_id omitted and merchant present: lookup rule, if match category_source="rule", no ML revision bump
       - otherwise: category_id=None, category_source=None, no ML revision bump
    3. Stage entity via transaction_access.stage_manual_transaction.
    4. Commit once and refresh transaction.
    """
    if merchant is not None and merchant.strip():
        resolved_merchant = merchant.strip()
        is_overridden = True
    else:
        resolved_merchant = normalize_merchant(description)
        is_overridden = False

    assigned_category_id = category_id
    category_source = None
    if assigned_category_id is not None:
        category_source = "manual"
        ml_model_access.increment_training_revision(db)
    elif resolved_merchant:
        rule = categorization_rule_access.get_rule_by_merchant(db, resolved_merchant)
        if rule:
            assigned_category_id = rule.category_id
            category_source = "rule"

    new_txn = transaction_access.stage_manual_transaction(
        db=db,
        account_id=account_id,
        amount=amount,
        transaction_date=transaction_date,
        description=description,
        merchant=resolved_merchant,
        is_merchant_overridden=is_overridden,
        category_id=assigned_category_id,
        category_source=category_source,
        transaction_datetime=transaction_datetime,
        pending=pending,
        is_reviewed=is_reviewed,
        plaid_transaction_id=plaid_transaction_id,
    )
    db.commit()
    db.refresh(new_txn)
    return new_txn
