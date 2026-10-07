"""
Resource access functions for Transaction PostgreSQL resources.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from .. import models

ZERO = Decimal("0.00")
DASHBOARD_RECENT_TRANSACTIONS_LIMIT = 10


class PlaidReconciliationConflictError(ValueError):
    """Raised when an incoming Plaid amount update conflicts with an already-reconciled transaction."""
    pass


def get_actuals_by_category(
    db: Session,
    start_date: date,
    end_date: date,
) -> dict[UUID, Decimal]:
    """
    Aggregates transaction amount sums grouped by category_id for transactions
    within [start_date, end_date).
    - Unsplit transactions: parent amount contributes to parent.category_id.
    - Split transactions: each TransactionSplit amount contributes to its category_id.
    Uncategorized transactions contribute zero.
    """
    has_splits_subq = db.query(models.TransactionSplit.id).filter(
        models.TransactionSplit.transaction_id == models.Transaction.transaction_id
    ).exists()

    unsplit_stats = (
        db.query(
            models.Transaction.category_id,
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(
            models.Transaction.date >= start_date,
            models.Transaction.date < end_date,
            models.Transaction.category_id.isnot(None),
            ~has_splits_subq,
        )
        .group_by(models.Transaction.category_id)
        .all()
    )

    split_stats = (
        db.query(
            models.TransactionSplit.category_id,
            func.sum(models.TransactionSplit.amount).label("total"),
        )
        .join(
            models.Transaction,
            models.Transaction.transaction_id == models.TransactionSplit.transaction_id,
        )
        .filter(
            models.Transaction.date >= start_date,
            models.Transaction.date < end_date,
        )
        .group_by(models.TransactionSplit.category_id)
        .all()
    )

    actuals: dict[UUID, Decimal] = {}
    for row in unsplit_stats:
        cat_id = row.category_id
        actuals[cat_id] = actuals.get(cat_id, ZERO) + Decimal(str(row.total or ZERO))

    for row in split_stats:
        cat_id = row.category_id
        actuals[cat_id] = actuals.get(cat_id, ZERO) + Decimal(str(row.total or ZERO))

    return actuals


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
        .options(
            joinedload(models.Transaction.account),
            selectinload(models.Transaction.splits).joinedload(models.TransactionSplit.category),
        )
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
    across all accounts, excluding split transactions, preserving current query shape
    and introducing no explicit ordering.
    """
    has_splits_subq = db.query(models.TransactionSplit.id).filter(
        models.TransactionSplit.transaction_id == models.Transaction.transaction_id
    ).exists()
    return (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Transaction.amount < 0,
            models.Transaction.is_transfer == False,
            ~has_splits_subq,
        )
        .all()
    )


def get_unmatched_outflow_transactions(
    db: Session,
) -> Sequence[models.Transaction]:
    """
    Retrieves all unmatched positive transactions (amount > 0, is_transfer == False)
    across all accounts, excluding split transactions, preserving current query shape
    and introducing no explicit ordering.
    """
    has_splits_subq = db.query(models.TransactionSplit.id).filter(
        models.TransactionSplit.transaction_id == models.Transaction.transaction_id
    ).exists()
    return (
        db.query(models.Transaction)
        .join(models.Account, models.Account.id == models.Transaction.account_id)
        .filter(
            models.Transaction.amount > 0,
            models.Transaction.is_transfer == False,
            ~has_splits_subq,
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
    category_source: Optional[str] = None,
    transaction_datetime: Optional[datetime] = None,
    merchant: Optional[str] = None,
) -> models.Transaction:
    """
    Instantiates and stages a new manual CSV import Transaction in the session.
    Explicitly sets plaid_transaction_id = None.
    If merchant is omitted, normalizes merchant from description.
    Sets is_merchant_overridden = False.
    Does not flush or commit.
    """
    from ..domain.merchant_normalization import normalize_merchant

    resolved_merchant = merchant if merchant is not None else normalize_merchant(description)

    txn = models.Transaction(
        account_id=account_id,
        category_id=category_id,
        category_source=category_source,
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


_EXISTING_TRANSACTION_NOT_PROVIDED: Any = object()


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
    category_id: Optional[UUID] = None,
    category_source: Optional[str] = None,
    existing_transaction: Any = _EXISTING_TRANSACTION_NOT_PROVIDED,
) -> models.Transaction:
    """
    Stages an insert or update of a Plaid transaction:
    - If txn does not exist: stages new models.Transaction record with normalized merchant,
      is_merchant_overridden=False, and assigns category_id and category_source provided by caller.
    - If txn exists:
      validates reconciliation conflicts against provider amount.
      updates description, amount, date, datetime, pending while preserving
      transaction_id, plaid_transaction_id, account_id, and is_transfer.
      If existing category_id is None: assigns category_id and category_source provided by caller.
      If existing category_id is NOT None: preserves existing category.
      If is_merchant_overridden is True: preserves existing user-corrected merchant.
      If is_merchant_overridden is False: updates merchant to new normalized merchant.
    - Sentinel semantics:
      If existing_transaction is omitted / sentinel: performs get_transaction_by_plaid_id lookup.
      If existing_transaction is None: record is known absent, skips lookup and performs insert.
      If existing_transaction is Transaction: record exists, skips lookup and performs update.
    Calls db.add(txn). Does not commit or refresh.
    """
    from ..domain.merchant_normalization import normalize_merchant

    resolved_merchant = merchant if merchant is not None else normalize_merchant(description)

    if existing_transaction is _EXISTING_TRANSACTION_NOT_PROVIDED:
        txn = get_transaction_by_plaid_id(db, plaid_transaction_id)
    else:
        txn = existing_transaction

    if txn is None:
        txn = models.Transaction(
            plaid_transaction_id=plaid_transaction_id,
            account_id=account_id,
            category_id=category_id,
            category_source=category_source,
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

    # Check if existing transaction is reconciled and provider amount differs
    if getattr(txn, "is_reconciled", False) is True:
        if isinstance(txn.amount, (Decimal, int, float, str)) and Decimal(str(amount)) != Decimal(str(txn.amount)):
            txn.plaid_reconciliation_conflict_amount = amount
            txn.plaid_reconciliation_conflict_at = datetime.now(timezone.utc)
            db.add(txn)
            raise PlaidReconciliationConflictError(
                f"Cannot modify amount of reconciled transaction {txn.transaction_id} from {txn.amount} to {amount} via provider sync: "
                "authoritative Plaid amount change on a reconciled transaction requires a reconciliation-history policy."
            )
        elif Decimal(str(amount)) == Decimal(str(txn.amount)):
            txn.plaid_reconciliation_conflict_amount = None
            txn.plaid_reconciliation_conflict_at = None

    txn.description = description
    if not getattr(txn, "is_merchant_overridden", False):
        txn.merchant = resolved_merchant
    txn.amount = amount
    txn.date = transaction_date
    txn.datetime = transaction_datetime
    txn.pending = pending

    # If the transaction was uncategorized and caller provided category, assign it
    if txn.category_id is None and category_id is not None:
        txn.category_id = category_id
        txn.category_source = category_source

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
    Retrieves a single transaction by primary key UUID with associated account
    and split allocations eagerly loaded.
    Does not commit or refresh.
    """
    return (
        db.query(models.Transaction)
        .options(
            joinedload(models.Transaction.account),
            selectinload(models.Transaction.splits).joinedload(models.TransactionSplit.category),
        )
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
    Preserves eager-loaded account and splits, total count before pagination,
    ordering by date DESC then transaction_id DESC, and pagination offset/limit.
    Does not commit or refresh.
    """
    query = db.query(models.Transaction).options(
        joinedload(models.Transaction.account),
        selectinload(models.Transaction.splits).joinedload(models.TransactionSplit.category),
    )

    if account_id is not None:
        query = query.filter(models.Transaction.account_id == account_id)
    if category_id is not None:
        split_exists = db.query(models.TransactionSplit.id).filter(
            models.TransactionSplit.transaction_id == models.Transaction.transaction_id,
            models.TransactionSplit.category_id == category_id,
        ).exists()
        query = query.filter(
            or_(
                models.Transaction.category_id == category_id,
                split_exists,
            )
        )
    if start_date is not None:
        query = query.filter(models.Transaction.date >= start_date)
    if end_date is not None:
        query = query.filter(models.Transaction.date <= end_date)
    if uncategorized is True:
        has_splits = db.query(models.TransactionSplit.id).filter(
            models.TransactionSplit.transaction_id == models.Transaction.transaction_id,
        ).exists()
        query = query.filter(
            models.Transaction.category_id == None,
            ~has_splits,
        )
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


def stage_manual_transaction(
    db: Session,
    account_id: UUID,
    amount: Decimal,
    transaction_date: date,
    description: str,
    merchant: Optional[str] = None,
    is_merchant_overridden: bool = False,
    category_id: Optional[UUID] = None,
    category_source: Optional[str] = None,
    transaction_datetime: Optional[datetime] = None,
    pending: bool = False,
    is_reviewed: bool = False,
    is_transfer: bool = False,
    plaid_transaction_id: Optional[str] = None,
    transaction_id: Optional[UUID] = None,
) -> models.Transaction:
    """
    Instantiates and stages a new manual Transaction in the session.
    Pure atomic ResourceAccess. Does not flush, commit, refresh, or call other Accessors.
    """
    model_kwargs = {}
    if transaction_id is not None:
        model_kwargs["transaction_id"] = transaction_id

    new_txn = models.Transaction(
        account_id=account_id,
        category_id=category_id,
        category_source=category_source,
        description=description,
        merchant=merchant,
        is_merchant_overridden=is_merchant_overridden,
        amount=amount,
        date=transaction_date,
        datetime=transaction_datetime,
        pending=pending,
        is_reviewed=is_reviewed,
        is_transfer=is_transfer,
        plaid_transaction_id=plaid_transaction_id,
        **model_kwargs,
    )
    db.add(new_txn)
    return new_txn


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
    Guards against split transactions: raises ValueError if any transaction has split allocations.
    Owns the standalone CRUD transaction boundary by calling db.commit() unconditionally.
    Returns the count of updated rows.
    """
    if not transaction_ids:
        db.commit()
        return 0

    from . import split_access
    split_exists = db.query(models.TransactionSplit.transaction_id).filter(
        models.TransactionSplit.transaction_id.in_(transaction_ids)
    ).first()
    if split_exists:
        raise ValueError("Cannot mark split transactions as transfers. Remove splits first.")

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
    Counts uncategorized transactions (category_id IS NULL and no split allocations)
    whose merchant matches clean_merchant_key.
    Read-only inspection query.
    """
    has_splits_subq = db.query(models.TransactionSplit.id).filter(
        models.TransactionSplit.transaction_id == models.Transaction.transaction_id
    ).exists()
    return (
        db.query(models.Transaction)
        .filter(
            models.Transaction.category_id.is_(None),
            ~has_splits_subq,
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
    Finds and updates uncategorized transactions (category_id IS NULL and no split allocations)
    matching clean_merchant_key to target category_id.
    Flushes changes to the session without committing so the calling Manager owns the transaction boundary.
    Returns count of updated rows.
    """
    has_splits_subq = db.query(models.TransactionSplit.id).filter(
        models.TransactionSplit.transaction_id == models.Transaction.transaction_id
    ).exists()
    matching_txs = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.category_id.is_(None),
            ~has_splits_subq,
            models.Transaction.merchant.isnot(None),
            func.lower(func.trim(models.Transaction.merchant)) == clean_merchant_key,
        )
        .all()
    )
    for tx in matching_txs:
        tx.category_id = category_id
        tx.category_source = "rule"
        db.add(tx)
    db.flush()
    return len(matching_txs)


def get_eligible_transactions_for_recurrence(
    db: Session,
    account_id: Optional[UUID] = None,
    as_of_date: Optional[date] = None,
) -> Sequence[models.Transaction]:
    """
    Retrieves posted, non-transfer transactions dated on or before as_of_date (default today),
    with non-zero amounts, ordered deterministically by date ASC, then transaction_id ASC.
    """
    if as_of_date is None:
        as_of_date = date.today()

    query = (
        db.query(models.Transaction)
        .options(joinedload(models.Transaction.account))
        .filter(
            models.Transaction.pending == False,
            models.Transaction.is_transfer == False,
            models.Transaction.date <= as_of_date,
            models.Transaction.amount != 0,
        )
    )
    if account_id is not None:
        query = query.filter(models.Transaction.account_id == account_id)

    return query.order_by(models.Transaction.date.asc(), models.Transaction.transaction_id.asc()).all()





