"""
Manager for the Account Reconciliation workflow.

Coordinates:
1. Account validation and prior-reconciliation baseline retrieval via Account ResourceAccess.
2. Depository account scope enforcement (deferring credit cards per Phase 7 specification).
3. Retrieval of eligible unreconciled transactions through statement ending date via Transaction ResourceAccess.
4. Invocation of the pure domain reconciliation calculation (compute_reconciliation_state).
5. State transitions on completion:
   - marking participating cleared transactions as reconciled;
   - updating account-level reconciliation metadata (last_reconciled_date, last_reconciled_balance).
6. Preserving zero-based budgeting, review state, transfer state, and account balance formulas without mutation.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from .. import models, schemas
from ..access import account_access, transaction_access
from ..domain.account_reconciliation import (
    ReconciliationTx,
    compute_reconciliation_state,
)

SUPPORTED_ACCOUNT_TYPES = {"depository"}


class AccountNotFoundError(Exception):
    """Raised when the target account cannot be found in persistence."""
    pass


class UnsupportedAccountTypeError(Exception):
    """Raised when reconciliation is attempted for an unsupported account type."""
    pass


class UnbalancedReconciliationError(Exception):
    """Raised when completing a reconciliation with a non-zero difference."""
    pass


def get_reconciliation_summary(
    db: Session,
    account_id: UUID,
    statement_ending_date: date,
    statement_ending_balance: Decimal,
) -> schemas.AccountReconciliationSummary:
    """
    Coordinates building the reconciliation view for an account as of a statement ending date.
    - Validates account existence and depository type.
    - Resolves baseline balance: last_reconciled_balance if present, otherwise starting_balance.
    - Queries unreconciled transactions with date <= statement_ending_date.
    - Invokes pure domain engine to calculate cleared balance and difference.
    - Assembles and returns schemas.AccountReconciliationSummary.
    """
    account = account_access.get_account_by_id(db, account_id)
    if account is None:
        raise AccountNotFoundError("Account not found")

    if account.type not in SUPPORTED_ACCOUNT_TYPES:
        raise UnsupportedAccountTypeError(
            f"Account reconciliation is currently supported for depository accounts only. "
            f"Account '{account.name}' has type '{account.type}'."
        )

    prior_balance = (
        Decimal(str(account.last_reconciled_balance))
        if account.last_reconciled_balance is not None
        else (Decimal(str(account.starting_balance)) if account.starting_balance is not None else Decimal("0.00"))
    )

    db_txns = transaction_access.get_unreconciled_transactions_for_account(
        db=db,
        account_id=account_id,
        ending_date=statement_ending_date,
    )

    domain_txns = [
        ReconciliationTx(
            transaction_id=t.transaction_id,
            account_id=t.account_id,
            amount=Decimal(str(t.amount)),
            date=t.date,
            is_cleared=bool(t.is_cleared),
            is_reconciled=bool(t.is_reconciled),
            pending=bool(t.pending),
            is_transfer=bool(t.is_transfer),
        )
        for t in db_txns
    ]

    calc = compute_reconciliation_state(
        prior_reconciled_balance=prior_balance,
        statement_ending_date=statement_ending_date,
        statement_ending_balance=Decimal(str(statement_ending_balance)),
        transactions=domain_txns,
    )

    read_txns = [
        schemas.ReconciliationTransactionRead(
            transaction_id=t.transaction_id,
            account_id=t.account_id,
            date=t.date,
            description=t.description or "",
            amount=Decimal(str(t.amount)),
            pending=bool(t.pending),
            is_transfer=bool(t.is_transfer),
            is_reviewed=bool(t.is_reviewed),
            is_cleared=bool(t.is_cleared),
            is_reconciled=bool(t.is_reconciled),
        )
        for t in db_txns
    ]

    return schemas.AccountReconciliationSummary(
        account_id=account.id,
        account_name=account.name,
        account_type=account.type,
        starting_balance=Decimal(str(account.starting_balance or "0.00")),
        last_reconciled_date=account.last_reconciled_date,
        last_reconciled_balance=account.last_reconciled_balance,
        prior_reconciled_balance=calc.prior_reconciled_balance,
        statement_ending_date=calc.statement_ending_date,
        statement_ending_balance=calc.statement_ending_balance,
        cleared_balance=calc.cleared_balance,
        difference=calc.difference,
        cleared_count=calc.cleared_count,
        uncleared_count=calc.uncleared_count,
        is_balanced=calc.is_balanced,
        transactions=read_txns,
    )


def complete_reconciliation(
    db: Session,
    account_id: UUID,
    statement_ending_date: date,
    statement_ending_balance: Decimal,
) -> schemas.AccountReconciliationSummary:
    """
    Coordinates finalization of an account reconciliation atomically within one SQLAlchemy transaction:
    1. Computes active reconciliation summary.
    2. Validates that difference == 0.00 (rejects with 400 if unbalanced).
    3. Flushes is_reconciled = True (and is_cleared = True) on all participating cleared transactions.
    4. Flushes account last_reconciled_date and last_reconciled_balance.
    5. Commits once atomically on success; rolls back on failure.
    6. Returns the updated summary reflecting newly reconciled state.
    """
    summary = get_reconciliation_summary(
        db=db,
        account_id=account_id,
        statement_ending_date=statement_ending_date,
        statement_ending_balance=statement_ending_balance,
    )

    if not summary.is_balanced:
        raise UnbalancedReconciliationError(
            f"Cannot complete reconciliation: statement ending balance ({statement_ending_balance}) "
            f"does not match cleared balance ({summary.cleared_balance}). "
            f"Difference: {summary.difference}."
        )

    cleared_tx_ids = [
        t.transaction_id
        for t in summary.transactions
        if t.is_cleared
    ]

    try:
        transaction_access.mark_transactions_as_reconciled(
            db=db,
            account_id=account_id,
            ending_date=statement_ending_date,
            transaction_ids=cleared_tx_ids,
        )

        account_access.update_account_reconciliation_metadata(
            db=db,
            account_id=account_id,
            last_reconciled_date=statement_ending_date,
            last_reconciled_balance=Decimal(str(statement_ending_balance)),
        )

        db.commit()
    except Exception:
        db.rollback()
        raise

    # Return refreshed summary
    return get_reconciliation_summary(
        db=db,
        account_id=account_id,
        statement_ending_date=statement_ending_date,
        statement_ending_balance=statement_ending_balance,
    )
