from os import getenv
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from plaid.api import plaid_api
import plaid
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.exceptions import ApiException
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
from .. import schemas
from ..crud import plaid as crud_plaid
from ..database import get_db
from ..managers import plaid_account_sync_manager
from ..managers import plaid_transaction_sync_manager

load_dotenv()

router = APIRouter(prefix="/plaid", tags=["Plaid"])

PLAID_ENVIRONMENT = getenv("PLAID_ENVIRONMENT", "Sandbox")

if PLAID_ENVIRONMENT == "Sandbox":
    host = plaid.Environment.Sandbox
elif PLAID_ENVIRONMENT == "Development":
    host = plaid.Environment.Development
elif PLAID_ENVIRONMENT == "Production":
    host = plaid.Environment.Production
else:
    raise ValueError("PLAID_ENVIRONMENT environment variable not set correctly")

config = Configuration(
    host=host,
    api_key={
        "clientId": getenv("PLAID_CLIENT_ID"),
        "secret": getenv("PLAID_SECRET"),
    },
)

api_client = ApiClient(config)
client = plaid_api.PlaidApi(api_client)


@router.post("/create_link_token", response_model=schemas.PlaidLinkTokenResponse)
def create_link_token():
    try:
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="static-user-id-for-now"),
            client_name="My Personal Budget App",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        response = client.link_token_create(request)
        return {"link_token": response.link_token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exchange_public_token", response_model=List[schemas.AccountRead])
def exchange_public_token(payload: schemas.PlaidPublicTokenRequest, db: Session = Depends(get_db)):
    """
    Exchange public_token for access_token, create PlaidItem if needed,
    and store accounts + balances immediately.
    """
    try:
        request = ItemPublicTokenExchangeRequest(public_token=payload.public_token)
        response = client.item_public_token_exchange(request)

        access_token = response.access_token
        plaid_item_id = response.item_id

        db_item = crud_plaid.get_plaid_item_by_plaid_item_id(db, plaid_item_id)
        if not db_item:
            db_item = crud_plaid.create_plaid_item(db=db, plaid_item_id=plaid_item_id, access_token=access_token)

        # ✅ Upsert accounts + balances
        crud_plaid.sync_accounts_and_balances(
            db=db,
            client=client,
            access_token=access_token,
            item_id=db_item.id,
        )

        db.commit()
        return crud_plaid.list_accounts_by_item(db, db_item.id)

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
        return {
            "message": result.message,
            "added": result.added,
            "modified": result.modified,
            "removed": result.removed,
            "next_cursor": result.next_cursor,
        }
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

