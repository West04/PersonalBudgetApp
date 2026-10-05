"""
Resource access functions for Transaction PostgreSQL resources.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .. import models

ZERO = Decimal("0.00")
DASHBOARD_RECENT_TRANSACTIONS_LIMIT = 10


def get_actuals_by_category(
    db: Session,
    start_date: date,
    end_date: date,
) -> dict[UUID, Decimal]:
    """
    Aggregates transaction amount sums grouped by category_id for transactions
    within [start_date, end_date), ignoring uncategorized transactions.
    """
    trx_stats = (
        db.query(
            models.Transaction.category_id,
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(
            models.Transaction.date >= start_date,
            models.Transaction.date < end_date,
            models.Transaction.category_id.isnot(None),
        )
        .group_by(models.Transaction.category_id)
        .all()
    )
    return {t.category_id: (t.total or ZERO) for t in trx_stats}


def get_recent_transactions_for_month(
    db: Session,
    start_date: date,
    end_date: date,
) -> Sequence[models.Transaction]:
    """
    Retrieves the 10 most recent transactions within [start_date, end_date),
    ordered by date descending, with associated account eagerly loaded.
    """
    return (
        db.query(models.Transaction)
        .options(joinedload(models.Transaction.account))
        .filter(
            models.Transaction.date >= start_date,
            models.Transaction.date < end_date,
        )
        .order_by(models.Transaction.date.desc())
        .limit(DASHBOARD_RECENT_TRANSACTIONS_LIMIT)
        .all()
    )


def get_transactions_for_account(
    db: Session,
    account_id: UUID,
) -> Sequence[models.Transaction]:
    """
    Retrieves all historical transactions for a specific account ordered by date descending.
    """
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.account_id == account_id)
        .order_by(models.Transaction.date.desc())
        .all()
    )


def get_unmatched_inflow_transactions(
    db: Session,
) -> Sequence[models.Transaction]:
    """
    Retrieves all unmatched negative transactions (amount < 0, is_transfer == False)
    across all accounts, preserving current query shape and introducing no explicit ordering.
    """
    return (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Transaction.amount < 0,
            models.Transaction.is_transfer == False,
        )
        .all()
    )


def get_unmatched_outflow_transactions(
    db: Session,
) -> Sequence[models.Transaction]:
    """
    Retrieves all unmatched positive transactions (amount > 0, is_transfer == False)
    across all accounts, preserving current query shape and introducing no explicit ordering.
    """
    return (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Transaction.amount > 0,
            models.Transaction.is_transfer == False,
        )
        .all()
    )


def get_account_for_transaction(
    transaction: models.Transaction,
) -> Optional[models.Account]:
    """
    Resolves the Account relationship associated with a Transaction.

    Accessing transaction.account may trigger SQLAlchemy lazy loading.
    Relationship loading remains a concrete persistence concern owned by
    Transaction ResourceAccess.
    """
    return transaction.account


def csv_import_transaction_exists(
    db: Session,
    account_id: UUID,
    transaction_date: date,
    amount: Decimal,
    description: str,
) -> bool:
    """
    Checks if an identical transaction exists for the given account.
    Matches exact account_id, date, amount, and description (case-sensitive).
    """
    return (
        db.query(models.Transaction)
        .filter(
            models.Transaction.account_id == account_id,
            models.Transaction.date == transaction_date,
            models.Transaction.amount == amount,
            models.Transaction.description == description,
        )
        .first()
    ) is not None


def stage_csv_import_transaction(
    db: Session,
    account_id: UUID,
    transaction_date: date,
    amount: Decimal,
    description: str,
    pending: bool = False,
    category_id: Optional[UUID] = None,
    transaction_datetime: Optional[datetime] = None,
    merchant: Optional[str] = None,
    rules_lookup: Optional[Mapping[str, UUID]] = None,
) -> models.Transaction:
    """
    Instantiates and stages a new manual CSV import Transaction in the session.
    Explicitly sets plaid_transaction_id = None.
    If merchant is omitted, normalizes merchant from description.
    Sets is_merchant_overridden = False.
    Evaluates matching categorization rule if category_id is None.
    Does not flush or commit.
    """
    from ..domain.merchant_normalization import normalize_merchant
    from ..domain.categorization_rules import clean_merchant_key

    resolved_merchant = merchant if merchant is not None else normalize_merchant(description)

    assigned_category_id = category_id
    if assigned_category_id is None and resolved_merchant:
        if rules_lookup is not None:
            clean_key = clean_merchant_key(resolved_merchant)
            if clean_key and clean_key in rules_lookup:
                assigned_category_id = rules_lookup[clean_key]
        else:
            from . import categorization_rule_access
            rule = categorization_rule_access.get_rule_by_merchant(db, resolved_merchant)
            if rule:
                assigned_category_id = rule.category_id

    txn = models.Transaction(
        account_id=account_id,
        category_id=assigned_category_id,
        description=description,
        merchant=resolved_merchant,
        is_merchant_overridden=False,
        amount=amount,
        date=transaction_date,
        datetime=transaction_datetime,
        pending=pending,
        plaid_transaction_id=None,
    )
    db.add(txn)
    return txn


def get_transaction_by_plaid_id(
    db: Session,
    plaid_transaction_id: str,
) -> Optional[models.Transaction]:
    """
    Retrieves a single Transaction by its Plaid transaction ID.
    Does not eager load Account or commit/refresh.
    """
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.plaid_transaction_id == plaid_transaction_id)
        .first()
    )


def stage_or_update_plaid_transaction(
    db: Session,
    plaid_transaction_id: str,
    account_id: UUID,
    description: str,
    amount: Decimal,
    transaction_date: date,
    transaction_datetime: Optional[datetime] = None,
    pending: bool = False,
    merchant: Optional[str] = None,
    rules_lookup: Optional[Mapping[str, UUID]] = None,
) -> models.Transaction:
    """
    Stages an insert or update of a Plaid transaction:
    - If no existing transaction matches plaid_transaction_id:
      stages a new models.Transaction record with normalized merchant with is_merchant_overridden=False.
      Evaluates matching categorization rule if category_id is None.
    - If existing transaction matches:
      updates description, amount, date, datetime, pending while preserving
      transaction_id, plaid_transaction_id, account_id, and is_transfer.
      If existing category_id is None and merchant matches a rule, assigns category.
      If existing category_id is NOT None, preserves existing category.
      If is_merchant_overridden is True: preserves existing user-corrected merchant.
      If is_merchant_overridden is False: updates merchant to new normalized merchant.
    Calls db.add(txn). Does not commit or refresh.
    """
    from ..domain.merchant_normalization import normalize_merchant
    from ..domain.categorization_rules import clean_merchant_key

    resolved_merchant = merchant if merchant is not None else normalize_merchant(description)

    txn = get_transaction_by_plaid_id(db, plaid_transaction_id)
    if txn is None:
        matched_category_id = None
        if resolved_merchant:
            if rules_lookup is not None:
                clean_key = clean_merchant_key(resolved_merchant)
                if clean_key and clean_key in rules_lookup:
                    matched_category_id = rules_lookup[clean_key]
            else:
                from . import categorization_rule_access
                rule = categorization_rule_access.get_rule_by_merchant(db, resolved_merchant)
                if rule:
                    matched_category_id = rule.category_id

        txn = models.Transaction(
            plaid_transaction_id=plaid_transaction_id,
            account_id=account_id,
            category_id=matched_category_id,
            description=description,
            merchant=resolved_merchant,
            is_merchant_overridden=False,
            amount=amount,
            date=transaction_date,
            datetime=transaction_datetime,
            pending=pending,
            is_transfer=False,
        )
        db.add(txn)
        return txn

    txn.description = description
    if not getattr(txn, "is_merchant_overridden", False):
        txn.merchant = resolved_merchant
    txn.amount = amount
    txn.date = transaction_date
    txn.datetime = transaction_datetime
    txn.pending = pending

    # If the transaction is currently uncategorized and merchant matches a rule, assign it
    if txn.category_id is None and txn.merchant:
        if rules_lookup is not None:
            clean_key = clean_merchant_key(txn.merchant)
            if clean_key and clean_key in rules_lookup:
                txn.category_id = rules_lookup[clean_key]
        else:
            from . import categorization_rule_access
            rule = categorization_rule_access.get_rule_by_merchant(db, txn.merchant)
            if rule:
                txn.category_id = rule.category_id

    db.add(txn)
    return txn


def stage_delete_transaction_by_plaid_id(
    db: Session,
    plaid_transaction_id: str,
) -> bool:
    """
    Deletes a transaction from the database given a Plaid transaction ID.
    Stages the deletion via db.delete(txn) and returns True if found, or False if missing.
    Does not commit.
    """
    txn = get_transaction_by_plaid_id(db, plaid_transaction_id)
    if txn:
        db.delete(txn)
        return True
    return False


def get_transaction_by_id(
    db: Session,
    transaction_id: UUID,
) -> Optional[models.Transaction]:
    """
    Retrieves a single transaction by primary key UUID with associated account eagerly loaded.
    Does not commit or refresh.
    """
    return (
        db.query(models.Transaction)
        .options(joinedload(models.Transaction.account))
        .filter(models.Transaction.transaction_id == transaction_id)
        .first()
    )


def list_transactions(
    db: Session,
    account_id: Optional[UUID] = None,
    category_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    uncategorized: Optional[bool] = None,
    is_reviewed: Optional[bool] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Lists transactions with optional filters for account, category,
    date range, uncategorized status, review status, and description search text.
    Preserves eager-loaded account, total count before pagination,
    ordering by date DESC then transaction_id DESC, and pagination offset/limit.
    Does not commit or refresh.
    """
    query = db.query(models.Transaction).options(joinedload(models.Transaction.account))

    if account_id is not None:
        query = query.filter(models.Transaction.account_id == account_id)
    if category_id is not None:
        query = query.filter(models.Transaction.category_id == category_id)
    if start_date is not None:
        query = query.filter(models.Transaction.date >= start_date)
    if end_date is not None:
        query = query.filter(models.Transaction.date <= end_date)
    if uncategorized is True:
        query = query.filter(models.Transaction.category_id == None)
    if is_reviewed is True:
        query = query.filter(models.Transaction.is_reviewed == True)
    elif is_reviewed is False:
        query = query.filter(models.Transaction.is_reviewed == False)
    if q:
        query = query.filter(
            or_(
                models.Transaction.description.ilike(f"%{q}%"),
                models.Transaction.merchant.ilike(f"%{q}%"),
            )
        )

    total = query.count()
    query = query.order_by(models.Transaction.date.desc(), models.Transaction.transaction_id.desc())
    items = query.offset(offset).limit(limit).all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def create_manual_transaction(
    db: Session,
    account_id: UUID,
    category_id: Optional[UUID],
    description: str,
    amount: Decimal,
    transaction_date: date,
    transaction_datetime: Optional[datetime],
    pending: bool,
    plaid_transaction_id: Optional[str],
    is_reviewed: bool = False,
    merchant: Optional[str] = None,
) -> models.Transaction:
    """
    Creates, commits, and refreshes a new manual Transaction from scalar values.
    Preserves model defaults for transaction_id (uuid4) and is_transfer (False).
    If merchant is explicitly provided: sets merchant and is_merchant_overridden = True.
    If merchant is omitted/None: normalizes merchant from description and sets is_merchant_overridden = False.
    Owns the standalone CRUD transaction boundary.
    """
    from ..domain.merchant_normalization import normalize_merchant

    if merchant is not None and merchant.strip():
        resolved_merchant = merchant.strip()
        is_overridden = True
    else:
        resolved_merchant = normalize_merchant(description)
        is_overridden = False

    assigned_category_id = category_id
    if assigned_category_id is None and resolved_merchant:
        from . import categorization_rule_access
        rule = categorization_rule_access.get_rule_by_merchant(db, resolved_merchant)
        if rule:
            assigned_category_id = rule.category_id

    new_txn = models.Transaction(
        account_id=account_id,
        category_id=assigned_category_id,
        description=description,
        merchant=resolved_merchant,
        is_merchant_overridden=is_overridden,
        amount=amount,
        date=transaction_date,
        datetime=transaction_datetime,
        pending=pending,
        is_reviewed=is_reviewed,
        plaid_transaction_id=plaid_transaction_id,
    )
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)
    return new_txn


def update_manual_transaction(
    db: Session,
    transaction_id: UUID,
    update_data: Mapping[str, Any],
) -> Optional[models.Transaction]:
    """
    Updates mutable fields on a Transaction using an exclude_unset mapping from presentation.
    Preserves eager-loaded account via get_transaction_by_id.
    Commits, refreshes, and returns updated Transaction, or None if not found.
    Owns the standalone CRUD transaction boundary.
    Guards reconciled transactions against changes to financial facts (amount, date, account_id).
    Handles merchant updates:
    - If 'merchant' is in update_data: updates merchant and marks is_merchant_overridden = True.
    - If 'description' is updated without 'merchant', and is_merchant_overridden is False:
      renormalizes merchant from the updated description.
    - If is_merchant_overridden is True, unrelated description edits preserve existing merchant.
    - If transaction.category_id is None and 'category_id' was not in update_data, evaluates
      matching rule for the resulting merchant.
    """
    from ..domain.merchant_normalization import normalize_merchant

    transaction = get_transaction_by_id(db, transaction_id)
    if transaction is None:
        return None

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

    for key, value in update_data.items():
        if key != "merchant":
            setattr(transaction, key, value)

    # If uncategorized and category_id was not explicitly in update_data, check matching rule
    if transaction.category_id is None and "category_id" not in update_data and transaction.merchant:
        from . import categorization_rule_access
        rule = categorization_rule_access.get_rule_by_merchant(db, transaction.merchant)
        if rule:
            transaction.category_id = rule.category_id

    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def delete_manual_transaction(
    db: Session,
    transaction_id: UUID,
) -> Optional[models.Transaction]:
    """
    Deletes a transaction by primary key UUID, commits, and returns the deleted Transaction,
    or None if not found.
    Owns the standalone CRUD transaction boundary.
    """
    deleted = (
        db.query(models.Transaction)
        .filter(models.Transaction.transaction_id == transaction_id)
        .first()
    )
    if deleted is None:
        return None
    if getattr(deleted, "is_reconciled", False) is True:
        raise ValueError("Cannot delete a reconciled transaction")
    db.delete(deleted)
    db.commit()
    return deleted


def mark_transactions_as_transfers(
    db: Session,
    transaction_ids: Sequence[UUID],
) -> int:
    """
    Marks transactions with IDs in transaction_ids as transfers (is_transfer = True).
    Executes a bulk update against models.Transaction with synchronize_session=False.
    Owns the standalone CRUD transaction boundary by calling db.commit() unconditionally.
    Returns the count of updated rows.
    """
    updated_count = (
        db.query(models.Transaction)
        .filter(models.Transaction.transaction_id.in_(transaction_ids))
        .update({models.Transaction.is_transfer: True}, synchronize_session=False)
    )
    db.commit()
    return updated_count


def get_transaction_net_by_account(
    db: Session,
    account_ids: Optional[Sequence[UUID]] = None,
) -> dict[UUID, Decimal]:
    """
    Aggregates transaction amount sums grouped by account_id.
    Positive amounts represent outflows/spending, negative amounts represent inflows/income.
    If account_ids is provided, limits aggregation to the specified accounts.
    """
    if account_ids is not None and len(account_ids) == 0:
        return {}

    query = db.query(
        models.Transaction.account_id,
        func.coalesce(func.sum(models.Transaction.amount), ZERO).label("net_amount"),
    ).group_by(models.Transaction.account_id)

    if account_ids is not None:
        query = query.filter(models.Transaction.account_id.in_(account_ids))

    return {row[0]: Decimal(str(row[1])) for row in query.all()}


def get_unreconciled_transactions_for_account(
    db: Session,
    account_id: UUID,
    ending_date: date,
) -> Sequence[models.Transaction]:
    """
    Retrieves all unreconciled, posted transactions for a specific account
    dated on or before ending_date, ordered by date ASC, then transaction_id ASC.
    Pending transactions are excluded.
    """
    return (
        db.query(models.Transaction)
        .filter(
            models.Transaction.account_id == account_id,
            models.Transaction.date <= ending_date,
            models.Transaction.is_reconciled == False,
            models.Transaction.pending == False,
        )
        .order_by(models.Transaction.date.asc(), models.Transaction.transaction_id.asc())
        .all()
    )


def set_transaction_cleared(
    db: Session,
    transaction_id: UUID,
    is_cleared: bool,
) -> Optional[models.Transaction]:
    """
    Updates the is_cleared flag on a transaction.
    Raises ValueError if the transaction is already reconciled.
    Raises ValueError if attempting to mark a pending transaction as cleared.
    Owns the standalone CRUD transaction boundary.
    """
    txn = get_transaction_by_id(db, transaction_id)
    if txn is None:
        return None
    if txn.is_reconciled:
        raise ValueError("Cannot modify cleared status of an already reconciled transaction")
    if is_cleared and txn.pending:
        raise ValueError("Cannot mark a pending transaction as cleared")
    txn.is_cleared = is_cleared
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def mark_transactions_as_reconciled(
    db: Session,
    account_id: UUID,
    ending_date: date,
    transaction_ids: Sequence[UUID],
) -> int:
    """
    Marks specified transactions for an account dated on or before ending_date
    as reconciled (is_reconciled = True, is_cleared = True).
    Excludes pending transactions.
    Flushes changes to the session without committing so the calling Manager owns the transaction boundary.
    Returns the count of updated rows.
    """
    if not transaction_ids:
        return 0
    updated_count = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.account_id == account_id,
            models.Transaction.date <= ending_date,
            models.Transaction.transaction_id.in_(transaction_ids),
            models.Transaction.pending == False,
        )
        .update(
            {
                models.Transaction.is_reconciled: True,
                models.Transaction.is_cleared: True,
            },
            synchronize_session=False,
        )
    )
    db.flush()
    return updated_count


def count_uncategorized_transactions_by_merchant_key(
    db: Session,
    clean_merchant_key: str,
) -> int:
    """
    Counts uncategorized transactions (category_id IS NULL) whose merchant matches clean_merchant_key.
    Read-only inspection query.
    """
    return (
        db.query(models.Transaction)
        .filter(
            models.Transaction.category_id.is_(None),
            models.Transaction.merchant.isnot(None),
            func.lower(func.trim(models.Transaction.merchant)) == clean_merchant_key,
        )
        .count()
    )


def apply_category_to_uncategorized_by_merchant_key(
    db: Session,
    clean_merchant_key: str,
    category_id: UUID,
) -> int:
    """
    Finds and updates uncategorized transactions matching clean_merchant_key to target category_id.
    Flushes changes to the session without committing so the calling Manager owns the transaction boundary.
    Returns count of updated rows.
    """
    matching_txs = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.category_id.is_(None),
            models.Transaction.merchant.isnot(None),
            func.lower(func.trim(models.Transaction.merchant)) == clean_merchant_key,
        )
        .all()
    )
    for tx in matching_txs:
        tx.category_id = category_id
        db.add(tx)
    db.flush()
    return len(matching_txs)





