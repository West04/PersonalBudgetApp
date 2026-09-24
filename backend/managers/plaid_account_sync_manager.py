"""
Workflow manager coordinating Plaid account synchronization.
Encapsulates identifier validation, token decryption, external API fetch,
relational staging, flush, and transaction commit.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.access import account_access, plaid_access, plaid_item_access
from backend.security import decrypt_token


@dataclass(frozen=True)
class PlaidAccountSyncResult:
    accounts_updated: int


class PlaidAccountSyncMissingIdentifierError(Exception):
    """Raised when neither item_id nor plaid_item_id is provided."""
    pass


class PlaidAccountSyncItemNotFoundError(Exception):
    """Raised when the requested PlaidItem does not exist in persistence."""
    pass


class PlaidAccountSyncDecryptionError(Exception):
    """Raised when token decryption raises an unexpected exception."""
    pass


class PlaidAccountSyncExternalApiError(Exception):
    """Raised when the external Plaid API call fails."""

    def __init__(
        self,
        status_code: int,
        detail: str,
    ):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def sync_plaid_accounts(
    db: Session,
    item_id: Optional[UUID] = None,
    plaid_item_id: Optional[str] = None,
) -> PlaidAccountSyncResult:
    """
    Coordinates the Plaid account synchronization workflow:
    1. Validates presence of at least one identifier with item_id precedence.
    2. Resolves PlaidItem from persistence.
    3. Decrypts stored access token via security helper.
    4. Fetches account snapshots via Plaid External ResourceAccess.
    5. Stages/updates each account via Account ResourceAccess with per-account timestamp.
    6. Flushes changes to persistence via db.flush().
    7. Commits transaction via db.commit().
    8. Returns PlaidAccountSyncResult.
    """
    if item_id:
        plaid_item = plaid_item_access.get_plaid_item_by_id(db, item_id)
    elif plaid_item_id:
        plaid_item = plaid_item_access.get_plaid_item_by_plaid_item_id(db, plaid_item_id)
    else:
        raise PlaidAccountSyncMissingIdentifierError("Must provide item_id or plaid_item_id")

    if not plaid_item:
        raise PlaidAccountSyncItemNotFoundError("Plaid Item not found")

    try:
        access_token = decrypt_token(plaid_item.plaid_access_token_encrypted)
    except Exception as exc:
        raise PlaidAccountSyncDecryptionError("Error decrypting access token") from exc

    try:
        snapshots = plaid_access.fetch_accounts_for_token(access_token)
    except plaid_access.PlaidAccessError as exc:
        raise PlaidAccountSyncExternalApiError(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    accounts_updated = 0
    for snapshot in snapshots:
        account_access.stage_or_update_plaid_account(
            db,
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
        accounts_updated += 1

    db.flush()
    db.commit()

    return PlaidAccountSyncResult(accounts_updated=accounts_updated)
