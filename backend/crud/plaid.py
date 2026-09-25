from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from .. import models
from backend.security import encrypt_token


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
