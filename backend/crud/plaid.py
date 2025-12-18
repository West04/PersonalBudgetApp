from uuid import UUID
from sqlalchemy.orm import Session
from .. import models, schemas
from backend.security import encrypt_token


# --- PlaidItem CRUD ---

def create_plaid_item(db: Session, plaid_item_id: str, access_token: str) -> models.PlaidItem:
    """
    Creates and saves a new PlaidItem, encrypting the access token.
    """

    # Encrypt the access token before storing it
    encrypted_access_token = encrypt_token(access_token)

    db_item = models.PlaidItem(
        plaid_item_id=plaid_item_id,
        plaid_access_token_encrypted=encrypted_access_token,
        transactions_cursor=None  # Cursor is null until first sync
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def get_plaid_item(db: Session, item_id: UUID) -> models.PlaidItem:
    """
    Gets a PlaidItem by its internal UUID.
    """
    return db.query(models.PlaidItem).filter(models.PlaidItem.id == item_id).first()


def get_plaid_item_by_plaid_item_id(db: Session, plaid_item_id: str) -> models.PlaidItem:
    """
    Gets a PlaidItem by its Plaid-provided item_id.
    """
    return db.query(models.PlaidItem).filter(models.PlaidItem.plaid_item_id == plaid_item_id).first()


def update_transactions_cursor(db: Session, plaid_item_id: str, new_cursor: str) -> models.PlaidItem:
    """
    Updates the transactions cursor for a given PlaidItem.
    """
    db_item = get_plaid_item_by_plaid_item_id(db, plaid_item_id)
    if db_item:
        db_item.transactions_cursor = new_cursor
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
    return db_item


# --- Account CRUD ---

def create_account(db: Session, account: dict, item_id: UUID) -> models.Account:
    """
    Creates and saves a new Account linked to a PlaidItem.
    'account' is a dictionary from the Plaid API /accounts/get response.
    """
    db_account = models.Account(
        item_id=item_id,
        plaid_account_id=account['account_id'],
        name=account['name'],
        mask=account['mask'],
        type=account['type'],
        subtype=account['subtype']
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def get_account_by_plaid_account_id(db: Session, plaid_account_id: str) -> models.Account:
    """
    Gets a local Account record by its Plaid-provided account_id.
    """
    return db.query(models.Account).filter(models.Account.plaid_account_id == plaid_account_id).first()


def list_accounts_by_item(db: Session, item_id: UUID) -> list[models.Account]:
    """
    Lists all local Account records for a given PlaidItem.
    """
    return db.query(models.Account).filter(models.Account.item_id == item_id).all()