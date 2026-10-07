"""
Workflow Manager for Manual Transaction Mutations.

Coordinates:
1. Normalizing merchant or recording user override.
2. Resolving category (manual with ML revision bump vs merchant rule fallback).
3. Staging entity via transaction_access.stage_manual_transaction for create.
4. Enforcing split and reconciled invariants for update.
5. Owning atomic commit and refresh.
"""

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from .. import models
from ..access import (
    categorization_rule_access,
    ml_model_access,
    split_access,
    transaction_access,
)
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


def update_transaction(
    db: Session,
    transaction_id: UUID,
    update_data: Mapping[str, Any],
) -> Optional[models.Transaction]:
    """
    Coordinates manual transaction update workflow:
    1. Transaction lookup via transaction_access.get_transaction_by_id.
       If missing, returns None immediately.
    2. Split detection via split_access.transaction_has_splits.
    3. Split mutation guards (evaluated strictly in order if transaction has splits):
       a. Amount change: if "amount" in update_data and Decimal(str(update_data["amount"])) != Decimal(str(transaction.amount)):
          raises ValueError("Cannot modify amount of a split transaction. Remove or edit split allocations first.")
       b. Category assignment: if "category_id" in update_data:
          raises ValueError("Cannot directly assign a category to a split transaction. Use the unsplit workflow instead.")
       c. Transfer conversion: if update_data.get("is_transfer") is True:
          raises ValueError("Cannot mark a split transaction as a transfer.")
    4. Reconciled financial-field guard (if getattr(transaction, "is_reconciled", False) is True):
       prohibited_keys = {"amount", "date", "account_id"}
       for key in prohibited_keys:
           if key in update_data and update_data[key] is not None:
               current_val = getattr(transaction, key)
               if key == "amount":
                   if Decimal(str(update_data[key])) != Decimal(str(current_val)):
                       raise ValueError("Cannot modify financial fields (amount, date, account_id) of a reconciled transaction")
               elif update_data[key] != current_val:
                   raise ValueError("Cannot modify financial fields (amount, date, account_id) of a reconciled transaction")
    5. Merchant / description normalization:
       - If "merchant" in update_data:
           m_val = update_data["merchant"]
           if m_val is not None and isinstance(m_val, str) and m_val.strip():
               transaction.merchant = m_val.strip()
               transaction.is_merchant_overridden = True
           elif m_val is None or (isinstance(m_val, str) and not m_val.strip()):
               desc = update_data.get("description", transaction.description)
               transaction.merchant = normalize_merchant(desc)
               transaction.is_merchant_overridden = False
       - Elif "description" in update_data:
           if not getattr(transaction, "is_merchant_overridden", False):
               transaction.merchant = normalize_merchant(update_data["description"])
    6. Category mutation & ML training revision:
       if "category_id" in update_data:
           new_cat = update_data["category_id"]
           old_cat = transaction.category_id
           if new_cat != old_cat:
               if new_cat is not None:
                   transaction.category_id = new_cat
                   transaction.category_source = "manual"
                   ml_model_access.increment_training_revision(db)
               else:
                   transaction.category_id = None
                   transaction.category_source = None
    7. Generic field assignments:
       for key, value in update_data.items():
           if key not in ("merchant", "category_id"):
               setattr(transaction, key, value)
    8. Fallback merchant-rule categorization:
       if not is_split_tx and transaction.category_id is None and "category_id" not in update_data and transaction.merchant:
           rule = categorization_rule_access.get_rule_by_merchant(db, transaction.merchant)
           if rule:
               transaction.category_id = rule.category_id
               transaction.category_source = "rule"
    9. Persistence / single-commit:
       db.add(transaction)
       db.commit()
       db.refresh(transaction)
       return transaction
    """
    transaction = transaction_access.get_transaction_by_id(db, transaction_id)
    if transaction is None:
        return None

    is_split_tx = split_access.transaction_has_splits(db, transaction_id)

    if is_split_tx:
        if "amount" in update_data and update_data["amount"] is not None:
            if Decimal(str(update_data["amount"])) != Decimal(str(transaction.amount)):
                raise ValueError("Cannot modify amount of a split transaction. Remove or edit split allocations first.")
        if "category_id" in update_data:
            raise ValueError("Cannot directly assign a category to a split transaction. Use the unsplit workflow instead.")
        if update_data.get("is_transfer") is True:
            raise ValueError("Cannot mark a split transaction as a transfer.")

    if getattr(transaction, "is_reconciled", False) is True:
        prohibited_keys = {"amount", "date", "account_id"}
        for key in prohibited_keys:
            if key in update_data and update_data[key] is not None:
                current_val = getattr(transaction, key)
                if key == "amount":
                    if Decimal(str(update_data[key])) != Decimal(str(current_val)):
                        raise ValueError("Cannot modify financial fields (amount, date, account_id) of a reconciled transaction")
                elif update_data[key] != current_val:
                    raise ValueError("Cannot modify financial fields (amount, date, account_id) of a reconciled transaction")

    # Handle merchant / description interaction
    if "merchant" in update_data:
        m_val = update_data["merchant"]
        if m_val is not None and isinstance(m_val, str) and m_val.strip():
            transaction.merchant = m_val.strip()
            transaction.is_merchant_overridden = True
        elif m_val is None or (isinstance(m_val, str) and not m_val.strip()):
            desc = update_data.get("description", transaction.description)
            transaction.merchant = normalize_merchant(desc)
            transaction.is_merchant_overridden = False
    elif "description" in update_data:
        if not getattr(transaction, "is_merchant_overridden", False):
            transaction.merchant = normalize_merchant(update_data["description"])

    if "category_id" in update_data:
        new_cat = update_data["category_id"]
        old_cat = transaction.category_id
        if new_cat != old_cat:
            if new_cat is not None:
                transaction.category_id = new_cat
                transaction.category_source = "manual"
                ml_model_access.increment_training_revision(db)
            else:
                transaction.category_id = None
                transaction.category_source = None

    for key, value in update_data.items():
        if key not in ("merchant", "category_id"):
            setattr(transaction, key, value)

    # If uncategorized and category_id was not explicitly in update_data, check matching rule
    if not is_split_tx and transaction.category_id is None and "category_id" not in update_data and transaction.merchant:
        rule = categorization_rule_access.get_rule_by_merchant(db, transaction.merchant)
        if rule:
            transaction.category_id = rule.category_id
            transaction.category_source = "rule"

    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction

