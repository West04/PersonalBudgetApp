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
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.exceptions import ApiException
from plaid.configuration import Configuration
from plaid.api_client import ApiClient

from .. import schemas
from ..crud import plaid as crud_plaid
from ..crud import transaction as crud_transaction
from ..database import get_db
from backend.security import decrypt_token

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
    plaid_item = crud_plaid.get_plaid_item_by_plaid_item_id(db, payload.plaid_item_id)
    if not plaid_item:
        raise HTTPException(status_code=404, detail="Plaid Item not found")

    try:
        access_token = decrypt_token(plaid_item.plaid_access_token_encrypted)
    except Exception:
        raise HTTPException(status_code=500, detail="Error decrypting access token")

    try:
        updated = crud_plaid.sync_accounts_and_balances(
            db=db,
            client=client,
            access_token=access_token,
            item_id=plaid_item.id,
        )
        db.commit()
        return {"status": "ok", "accounts_updated": updated}
    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=e.body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync_transactions", response_model=Dict[str, Any])
def sync_transactions(payload: schemas.PlaidSyncRequest, db: Session = Depends(get_db)):
    """
    HEAVY: Sync transaction updates from Plaid.
    Recommended: refresh balances first.
    """
    plaid_item = crud_plaid.get_plaid_item_by_plaid_item_id(db, payload.plaid_item_id)
    if not plaid_item:
        raise HTTPException(status_code=404, detail="Plaid Item not found")

    try:
        access_token = decrypt_token(plaid_item.plaid_access_token_encrypted)
    except Exception:
        raise HTTPException(status_code=500, detail="Error decrypting access token")

    cursor = plaid_item.transactions_cursor

    added_count = 0
    modified_count = 0
    removed_count = 0

    try:
        # ✅ Best UX: refresh balances before doing heavy sync
        crud_plaid.sync_accounts_and_balances(
            db=db,
            client=client,
            access_token=access_token,
            item_id=plaid_item.id,
        )

        has_more = True
        while has_more:
            request = TransactionsSyncRequest(access_token=access_token, cursor=cursor)
            response = client.transactions_sync(request).to_dict()

            added = response["added"]
            modified = response["modified"]
            removed = response["removed"]

            has_more = response["has_more"]
            cursor = response["next_cursor"]

            for tx_data in added:
                crud_transaction.create_or_update_transaction(db, tx_data)
                added_count += 1

            for tx_data in modified:
                crud_transaction.create_or_update_transaction(db, tx_data)
                modified_count += 1

            for tx_data in removed:
                crud_transaction.delete_transaction_by_plaid_id(db, tx_data["transaction_id"])
                removed_count += 1

        crud_plaid.update_transactions_cursor(db, plaid_item.plaid_item_id, cursor)

        db.commit()
        return {
            "message": "Sync successful",
            "added": added_count,
            "modified": modified_count,
            "removed": removed_count,
            "next_cursor": cursor,
        }

    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=e.body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
