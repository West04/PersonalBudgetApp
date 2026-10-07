from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from .. import schemas
from ..access import plaid_access
from ..database import get_db
from ..managers import plaid_account_sync_manager
from ..managers import plaid_transaction_sync_manager

load_dotenv()

router = APIRouter(prefix="/plaid", tags=["Plaid"])


@router.post("/create_link_token", response_model=schemas.PlaidLinkTokenResponse)
def create_link_token():
    try:
        link_token = plaid_access.create_link_token()
        return {"link_token": link_token}
    except plaid_access.PlaidAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exchange_public_token", response_model=List[schemas.AccountRead])
def exchange_public_token(payload: schemas.PlaidPublicTokenRequest, db: Session = Depends(get_db)):
    """
    Exchange public_token for access_token, create PlaidItem if needed,
    and store accounts + balances immediately.
    """
    try:
        return plaid_account_sync_manager.exchange_public_token(db, payload.public_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync_accounts", response_model=Dict[str, Any])
def sync_accounts(payload: schemas.PlaidSyncRequest, db: Session = Depends(get_db)):
    """
    FAST: Refresh account balances only (best UX).
    """
    try:
        result = plaid_account_sync_manager.sync_plaid_accounts(
            db,
            item_id=payload.item_id,
            plaid_item_id=payload.plaid_item_id,
        )
        return {"status": "ok", "accounts_updated": result.accounts_updated}
    except plaid_account_sync_manager.PlaidAccountSyncMissingIdentifierError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except plaid_account_sync_manager.PlaidAccountSyncItemNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except plaid_account_sync_manager.PlaidAccountSyncDecryptionError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except plaid_account_sync_manager.PlaidAccountSyncExternalApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync_transactions", response_model=Dict[str, Any])
def sync_transactions(payload: schemas.PlaidSyncRequest, db: Session = Depends(get_db)):
    """
    HEAVY: Sync transaction updates from Plaid.
    Recommended: refresh balances first.
    """
    try:
        result = plaid_transaction_sync_manager.sync_plaid_transactions(
            db=db,
            item_id=payload.item_id,
            plaid_item_id=payload.plaid_item_id,
        )
        resp: Dict[str, Any] = {
            "message": result.message,
            "added": result.added,
            "modified": result.modified,
            "removed": result.removed,
            "next_cursor": result.next_cursor,
        }
        if result.warnings:
            resp["warnings"] = list(result.warnings)
        return resp
    except plaid_transaction_sync_manager.PlaidTransactionSyncMissingIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except plaid_transaction_sync_manager.PlaidTransactionSyncItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except plaid_transaction_sync_manager.PlaidTransactionSyncDecryptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except plaid_transaction_sync_manager.PlaidTransactionSyncAccountRefreshError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except plaid_transaction_sync_manager.PlaidTransactionSyncHttpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=f"Plaid Sync Error: {exc.detail}")
    except plaid_transaction_sync_manager.PlaidTransactionSyncNetworkError as exc:
        raise HTTPException(status_code=500, detail=exc.detail)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))

