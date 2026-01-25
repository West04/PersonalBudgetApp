from datetime import datetime
from decimal import Decimal
from uuid import UUID
from os import getenv
import requests

from sqlalchemy.orm import Session

from .. import models
from backend.security import encrypt_token
from ..crud import transaction as crud_transaction


# --- PlaidItem CRUD ---

def create_plaid_item(db: Session, plaid_item_id: str, access_token: str) -> models.PlaidItem:
    encrypted_access_token = encrypt_token(access_token)

    db_item = models.PlaidItem(
        plaid_item_id=plaid_item_id,
        plaid_access_token_encrypted=encrypted_access_token,
        transactions_cursor=None,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def get_plaid_item_by_plaid_item_id(db: Session, plaid_item_id: str) -> models.PlaidItem:
    return db.query(models.PlaidItem).filter(models.PlaidItem.plaid_item_id == plaid_item_id).first()


def get_plaid_item_by_id(db: Session, id: UUID) -> models.PlaidItem:
    return db.query(models.PlaidItem).filter(models.PlaidItem.id == id).first()


def update_transactions_cursor(db: Session, plaid_item_id: str, new_cursor: str) -> models.PlaidItem:
    db_item = get_plaid_item_by_plaid_item_id(db, plaid_item_id)
    if db_item:
        db_item.transactions_cursor = new_cursor
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
    return db_item


# --- Accounts CRUD ---

def get_account_by_plaid_account_id(db: Session, plaid_account_id: str) -> models.Account:
    return db.query(models.Account).filter(models.Account.plaid_account_id == plaid_account_id).first()


def list_accounts_by_item(db: Session, item_id: UUID) -> list[models.Account]:
    return db.query(models.Account).filter(models.Account.item_id == item_id).all()


def create_account(db: Session, account: dict, item_id: UUID) -> models.Account:
    db_account = models.Account(
        item_id=item_id,
        plaid_account_id=account["account_id"],
        name=account["name"],
        mask=account.get("mask"),
        type=account["type"],
        subtype=account.get("subtype"),
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def sync_accounts_and_balances(db: Session, client, access_token: str, item_id: UUID) -> int:
    """
    FAST, safe to call often.
    - fetch /accounts/get
    - upsert account rows
    - update persisted balances + last_updated
    """
    # Plaid SDK request object
    from plaid.model.accounts_get_request import AccountsGetRequest

    req = AccountsGetRequest(access_token=access_token)
    resp = client.accounts_get(req)

    now = datetime.utcnow()
    updated = 0

    for acct in resp.accounts:
        data = acct.to_dict()
        balances = data.get("balances") or {}

        db_account = get_account_by_plaid_account_id(db, data["account_id"])

        if db_account is None:
            db_account = models.Account(
                item_id=item_id,
                plaid_account_id=data["account_id"],
                name=data.get("name") or "Account",
                mask=data.get("mask"),
                type=data.get("type") or "unknown",
                subtype=data.get("subtype"),
                is_active=True,
            )
            db.add(db_account)

        # identity fields
        db_account.name = data.get("name") or db_account.name
        db_account.mask = data.get("mask")
        db_account.type = data.get("type") or db_account.type
        db_account.subtype = data.get("subtype")

        # balances
        db_account.current_balance = Decimal(str(balances.get("current") or 0))
        available = balances.get("available")
        db_account.available_balance = Decimal(str(available)) if available is not None else None
        db_account.currency = balances.get("iso_currency_code") or "USD"
        db_account.balance_last_updated = now

        db.add(db_account)
        updated += 1

    db.flush()
    return updated


def sync_transactions_from_plaid(db: Session, access_token: str, plaid_item_id: str, cursor: str) -> dict:
    """
    Syncs transactions from Plaid using raw HTTP requests (requests lib)
    to avoid SDK type validation issues with cursors.
    """
    PLAID_ENVIRONMENT = getenv("PLAID_ENVIRONMENT", "Sandbox")
    PLAID_BASE_URLS = {
        "Sandbox": "https://sandbox.plaid.com",
        "Development": "https://development.plaid.com",
        "Production": "https://production.plaid.com"
    }
    PLAID_BASE = PLAID_BASE_URLS.get(PLAID_ENVIRONMENT, "https://sandbox.plaid.com")

    headers = {
        "Content-Type": "application/json",
        "PLAID-CLIENT-ID": getenv("PLAID_CLIENT_ID"),
        "PLAID-SECRET": getenv("PLAID_SECRET"),
    }

    added_count = 0
    modified_count = 0
    removed_count = 0
    has_more = True

    while has_more:
        body = {
            "access_token": access_token,
            "count": 500  # Max per page
        }
        if cursor:
            body["cursor"] = cursor

        print(f"DEBUG: calling {PLAID_BASE}/transactions/sync with cursor='{cursor}'")
        resp = requests.post(f"{PLAID_BASE}/transactions/sync", json=body, headers=headers, timeout=60)
        resp.raise_for_status()

        data = resp.json()

        added = data["added"]
        modified = data["modified"]
        removed = data["removed"]

        has_more = data["has_more"]
        cursor = data["next_cursor"]

        for tx_data in added:
            crud_transaction.create_or_update_transaction(db, tx_data)
            added_count += 1

        for tx_data in modified:
            crud_transaction.create_or_update_transaction(db, tx_data)
            modified_count += 1

        for tx_data in removed:
            # 'removed' usually contains dicts with 'transaction_id'
            crud_transaction.delete_transaction_by_plaid_id(db, tx_data["transaction_id"])
            removed_count += 1

    update_transactions_cursor(db, plaid_item_id, cursor)
    db.commit()

    return {
        "message": "Sync successful",
        "added": added_count,
        "modified": modified_count,
        "removed": removed_count,
        "next_cursor": cursor,
    }
