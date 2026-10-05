"""
Workflow manager for Plaid Transaction Sync.
Coordinates token decryption, account balance refresh staging,
cursor-based transaction pagination loop, legacy per-event persistence,
and final cursor commitment.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from ..access import (
    account_access,
    plaid_access,
    plaid_item_access,
    plaid_transaction_access,
    transaction_access,
)
from ..domain.merchant_normalization import normalize_merchant
from ..security import decrypt_token


@dataclass(frozen=True)
class PlaidTransactionSyncResult:
    message: str
    added: int
    modified: int
    removed: int
    next_cursor: str


class PlaidTransactionSyncMissingIdentifierError(Exception):
    """Raised when neither item_id nor plaid_item_id is provided."""
    pass


class PlaidTransactionSyncItemNotFoundError(Exception):
    """Raised when the requested PlaidItem does not exist in persistence."""
    pass


class PlaidTransactionSyncDecryptionError(Exception):
    """Raised when token decryption raises an unexpected exception."""
    pass


class PlaidTransactionSyncAccountRefreshError(Exception):
    """Raised when external Plaid /accounts/get fails during pre-sync balance refresh."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PlaidTransactionSyncHttpError(Exception):
    """Raised when external raw HTTP /transactions/sync returns an HTTP error status."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PlaidTransactionSyncNetworkError(Exception):
    """Raised when external raw HTTP /transactions/sync encounters a network/connection/timeout error."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def _process_upsert_event(db: Session, tx_data: dict[str, Any]) -> None:
    remote_account_id = tx_data["account_id"]
    account = account_access.get_account_by_plaid_account_id(db, remote_account_id)
    if not account:
        raise Exception(f"Account {remote_account_id} not found in database.")

    raw_date = tx_data["date"]
    tx_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date

    raw_datetime = tx_data.get("datetime")
    tx_datetime = datetime.fromisoformat(raw_datetime) if isinstance(raw_datetime, str) else raw_datetime

    amount_for_budget = -Decimal(str(tx_data["amount"]))

    provider_merchant = tx_data.get("merchant_name")
    if not provider_merchant and tx_data.get("counterparties"):
        cps = tx_data["counterparties"]
        if isinstance(cps, list) and len(cps) > 0 and isinstance(cps[0], dict):
            provider_merchant = cps[0].get("name")

    normalized_merchant = normalize_merchant(
        raw_description=tx_data["name"],
        provider_merchant=provider_merchant,
    )

    transaction_access.stage_or_update_plaid_transaction(
        db=db,
        plaid_transaction_id=tx_data["transaction_id"],
        account_id=account.id,
        description=tx_data["name"],
        amount=amount_for_budget,
        transaction_date=tx_date,
        transaction_datetime=tx_datetime,
        pending=tx_data["pending"],
        merchant=normalized_merchant,
    )
    db.commit()


def sync_plaid_transactions(
    db: Session,
    item_id: Optional[UUID] = None,
    plaid_item_id: Optional[str] = None,
) -> PlaidTransactionSyncResult:
    """
    Coordinates the Plaid transaction synchronization workflow:
    1. Validates presence of at least one identifier.
    2. Resolves PlaidItem using item_id precedence.
    3. Decrypts access token via security helper.
    4. Stages account balance updates:
       - Calls plaid_access.fetch_accounts_for_token(access_token).
         Catches PlaidAccessError -> raises PlaidTransactionSyncAccountRefreshError.
       - Stages account records via account_access.stage_or_update_plaid_account.
       - Executes db.flush() (staged in session, NOT committed).
    5. Reads starting cursor from PlaidItem.transactions_cursor.
    6. Executes pagination loop against PlaidTransactionAccess:
       - Calls plaid_transaction_access.fetch_transactions_page(access_token, cursor).
         Catches PlaidTransactionHttpError -> raises PlaidTransactionSyncHttpError.
         Catches PlaidTransactionNetworkError -> raises PlaidTransactionSyncNetworkError.
       - Advances in-memory cursor to page.next_cursor before event iteration.
       - For added events: resolves account via account_access, stages upsert via transaction_access, executes db.commit().
       - For modified events: resolves account via account_access, stages upsert via transaction_access, executes db.commit().
       - For removed events: stages deletion via transaction_access; if record found, executes db.commit().
    7. Stages final cursor via plaid_item_access.stage_transactions_cursor(db, plaid_item_id, cursor).
    8. Executes two-stage final commits:
       - db.commit()  # Equivalent to legacy cursor helper commit
       - db.commit()  # Redundant final commit preserved for compatibility
    9. Returns PlaidTransactionSyncResult.
    """
    if item_id:
        plaid_item = plaid_item_access.get_plaid_item_by_id(db, item_id)
    elif plaid_item_id:
        plaid_item = plaid_item_access.get_plaid_item_by_plaid_item_id(db, plaid_item_id)
    else:
        raise PlaidTransactionSyncMissingIdentifierError("Must provide item_id or plaid_item_id")

    if not plaid_item:
        raise PlaidTransactionSyncItemNotFoundError("Plaid Item not found")

    try:
        access_token = decrypt_token(plaid_item.plaid_access_token_encrypted)
    except Exception as exc:
        raise PlaidTransactionSyncDecryptionError("Error decrypting access token") from exc

    try:
        snapshots = plaid_access.fetch_accounts_for_token(access_token)
    except plaid_access.PlaidAccessError as exc:
        raise PlaidTransactionSyncAccountRefreshError(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    for snapshot in snapshots:
        account_access.stage_or_update_plaid_account(
            db=db,
            item_id=plaid_item.id,
            plaid_account_id=snapshot.account_id,
            name=snapshot.name,
            mask=snapshot.mask,
            account_type=snapshot.account_type,
            subtype=snapshot.subtype,
            current_balance=snapshot.current_balance,
            available_balance=snapshot.available_balance,
            currency=snapshot.currency,
            balance_last_updated=datetime.utcnow(),
        )

    db.flush()

    cursor = plaid_item.transactions_cursor

    has_more = True
    added_count = 0
    modified_count = 0
    removed_count = 0

    while has_more:
        try:
            page = plaid_transaction_access.fetch_transactions_page(
                access_token=access_token,
                cursor=cursor,
            )
        except plaid_transaction_access.PlaidTransactionHttpError as exc:
            raise PlaidTransactionSyncHttpError(
                status_code=exc.status_code,
                detail=exc.detail,
            ) from exc
        except plaid_transaction_access.PlaidTransactionNetworkError as exc:
            raise PlaidTransactionSyncNetworkError(
                detail=exc.detail,
            ) from exc

        has_more = page.has_more
        cursor = page.next_cursor

        for tx_data in page.added:
            _process_upsert_event(db, tx_data)
            added_count += 1

        for tx_data in page.modified:
            _process_upsert_event(db, tx_data)
            modified_count += 1

        for tx_data in page.removed:
            deleted = transaction_access.stage_delete_transaction_by_plaid_id(
                db=db,
                plaid_transaction_id=tx_data["transaction_id"],
            )
            if deleted:
                db.commit()
            removed_count += 1

    plaid_item_access.stage_transactions_cursor(
        db=db,
        plaid_item_id=plaid_item.plaid_item_id,
        cursor=cursor,
    )

    db.commit()  # Behavioral equivalent of legacy cursor helper commit
    # Preserves redundant final commit from legacy crud_plaid implementation (compatibility artifact)
    db.commit()

    return PlaidTransactionSyncResult(
        message="Sync successful",
        added=added_count,
        modified=modified_count,
        removed=removed_count,
        next_cursor=cursor,
    )
