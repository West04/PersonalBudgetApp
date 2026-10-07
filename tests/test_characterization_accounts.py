"""
Characterization tests for Account CRUD HTTP endpoints and persistence behavior.

Captures existing behavior of backend/routers/accounts.py prior to VBD extraction:
- GET /accounts/types returns canonical schemas.ACCOUNT_SUBTYPES
- GET /accounts/ returns all accounts (active and inactive, manual and Plaid-linked)
  ordered by type ASC, then name ASC.
- POST /accounts/ creates manual accounts (plaid_account_id=None, item_id=None) with 201.
- PUT /accounts/{account_id} updates whitelisted fields and preserves omitted fields.
  404 on missing account.
- DELETE /accounts/{account_id} hard-deletes accounts with 204.
  404 on missing account.
  500 (IntegrityError) if foreign-key constraint prevents deletion when transactions exist.
- No GET /accounts/{account_id} detail endpoint exists.
"""

from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend import models, schemas
from backend.access.plaid_item_access import create_plaid_item


# ---------------------------------------------------------------------------
# 1. Account Types Endpoint (GET /accounts/types)
# ---------------------------------------------------------------------------

def test_get_account_types_returns_canonical_subtypes(client: TestClient):
    response = client.get("/accounts/types")
    assert response.status_code == 200
    data = response.json()
    assert data == schemas.ACCOUNT_SUBTYPES
    assert "depository" in data
    assert "credit" in data
    assert "checking" in data["depository"]
    assert "credit card" in data["credit"]


# ---------------------------------------------------------------------------
# 2. Account Detail Endpoint Absence Check
# ---------------------------------------------------------------------------

def test_account_detail_endpoint_does_not_exist(client: TestClient, db_session):
    account = models.Account(
        name="Existing Account",
        type="depository",
        subtype="checking",
    )
    db_session.add(account)
    db_session.commit()

    # GET /accounts/{account_id} does not exist (FastAPI returns 405 Method Not Allowed
    # because PUT and DELETE exist for /{account_id})
    response = client.get(f"/accounts/{account.id}")
    assert response.status_code == 405


# ---------------------------------------------------------------------------
# 3. Account List Endpoint (GET /accounts/)
# ---------------------------------------------------------------------------

def test_list_accounts_empty(client: TestClient):
    response = client.get("/accounts/")
    assert response.status_code == 200
    assert response.json() == []


def test_list_accounts_single_manual_account_shape(client: TestClient, db_session):
    account = models.Account(
        name="Checking Alpha",
        type="depository",
        subtype="checking",
        current_balance=Decimal("123.45"),
        starting_balance=Decimal("100.00"),
        currency="USD",
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()

    response = client.get("/accounts/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    item = data[0]
    assert item["account_id"] == str(account.id)
    assert item["name"] == "Checking Alpha"
    assert item["type"] == "depository"
    assert item["subtype"] == "checking"
    # Derived from starting_balance (100.00) - net_transactions (0.00) = 100.00
    assert Decimal(str(item["current_balance"])) == Decimal("100.00")
    assert Decimal(str(item["starting_balance"])) == Decimal("100.00")
    assert item["currency"] == "USD"
    assert item["is_active"] is True
    assert item["status"] == "connected"
    assert item["plaid_account_id"] is None
    assert item["item_id"] is None


def test_list_accounts_ordering_by_type_asc_then_name_asc(client: TestClient, db_session):
    # type "credit" comes before "depository" alphabetically
    acc_dep_b = models.Account(name="Bravo Depository", type="depository")
    acc_dep_a = models.Account(name="Alpha Depository", type="depository")
    acc_cred_b = models.Account(name="Bravo Credit", type="credit")
    acc_cred_a = models.Account(name="Alpha Credit", type="credit")

    db_session.add_all([acc_dep_b, acc_dep_a, acc_cred_b, acc_cred_a])
    db_session.commit()

    response = client.get("/accounts/")
    assert response.status_code == 200
    data = response.json()
    names = [a["name"] for a in data]
    assert names == [
        "Alpha Credit",
        "Bravo Credit",
        "Alpha Depository",
        "Bravo Depository",
    ]


def test_list_accounts_includes_inactive_accounts(client: TestClient, db_session):
    acc_active = models.Account(name="Active Account", type="depository", is_active=True)
    acc_inactive = models.Account(name="Inactive Account", type="depository", is_active=False)

    db_session.add_all([acc_active, acc_inactive])
    db_session.commit()

    response = client.get("/accounts/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    active_statuses = {a["name"]: a["is_active"] for a in data}
    assert active_statuses["Active Account"] is True
    assert active_statuses["Inactive Account"] is False


def test_list_accounts_includes_plaid_linked_accounts(client: TestClient, db_session):
    item = create_plaid_item(db_session, plaid_item_id="plaid_it_1", access_token="tok")
    plaid_acc = models.Account(
        name="Plaid Account",
        type="depository",
        item_id=item.id,
        plaid_account_id="plaid_acc_123",
        mask="4321",
    )
    manual_acc = models.Account(name="Manual Account", type="depository")

    db_session.add_all([plaid_acc, manual_acc])
    db_session.commit()

    response = client.get("/accounts/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    by_name = {a["name"]: a for a in data}
    assert by_name["Plaid Account"]["plaid_account_id"] == "plaid_acc_123"
    assert by_name["Plaid Account"]["item_id"] == str(item.id)
    assert by_name["Plaid Account"]["mask"] == "4321"
    assert by_name["Manual Account"]["plaid_account_id"] is None
    assert by_name["Manual Account"]["item_id"] is None


# ---------------------------------------------------------------------------
# 4. Account Creation Endpoint (POST /accounts/)
# ---------------------------------------------------------------------------

def test_create_manual_account_success_with_all_fields(client: TestClient, db_session):
    payload = {
        "name": "My New Checking",
        "type": "depository",
        "subtype": "checking",
        "current_balance": 500.50,
        "starting_balance": 250.00,
        "currency": "USD",
        "is_active": True,
    }

    response = client.post("/accounts/", json=payload)
    assert response.status_code == 201
    data = response.json()
    account_id = data["account_id"]

    assert data["name"] == "My New Checking"
    assert data["type"] == "depository"
    assert data["subtype"] == "checking"
    assert Decimal(str(data["current_balance"])) == Decimal("500.50")
    assert Decimal(str(data["starting_balance"])) == Decimal("250.00")
    assert data["currency"] == "USD"
    assert data["is_active"] is True
    assert data["plaid_account_id"] is None
    assert data["item_id"] is None

    # Verify persisted DB record
    db_acc = db_session.query(models.Account).filter(models.Account.id == account_id).first()
    assert db_acc is not None
    assert db_acc.name == "My New Checking"
    assert db_acc.plaid_account_id is None
    assert db_acc.item_id is None


def test_create_manual_account_defaults(client: TestClient, db_session):
    # Only name and type provided
    payload = {
        "name": "Minimal Account",
        "type": "credit",
    }

    response = client.post("/accounts/", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "Minimal Account"
    assert data["type"] == "credit"
    assert data["subtype"] is None
    assert Decimal(str(data["current_balance"])) == Decimal("0.00")
    assert Decimal(str(data["starting_balance"])) == Decimal("0.00")
    assert data["currency"] == "USD"
    assert data["is_active"] is True
    assert data["plaid_account_id"] is None
    assert data["item_id"] is None


def test_create_manual_account_invalid_type_422(client: TestClient):
    payload = {
        "name": "Bad Account",
        "type": "nonexistent_type",
    }
    response = client.post("/accounts/", json=payload)
    assert response.status_code == 422


def test_create_manual_account_missing_name_422(client: TestClient):
    payload = {
        "type": "depository",
    }
    response = client.post("/accounts/", json=payload)
    assert response.status_code == 422


def test_create_manual_account_ignores_plaid_fields_in_payload(client: TestClient, db_session):
    # Even if client sends plaid_account_id or item_id, the router hardcodes None
    payload = {
        "name": "Ignored Plaid Account",
        "type": "depository",
        "plaid_account_id": "malicious_plaid_id",
        "item_id": str(uuid4()),
    }
    response = client.post("/accounts/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["plaid_account_id"] is None
    assert data["item_id"] is None

    db_acc = db_session.query(models.Account).filter(models.Account.id == data["account_id"]).first()
    assert db_acc.plaid_account_id is None
    assert db_acc.item_id is None


# ---------------------------------------------------------------------------
# 5. Account Update Endpoint (PUT /accounts/{account_id})
# ---------------------------------------------------------------------------

def test_update_account_all_fields(client: TestClient, db_session):
    account = models.Account(
        name="Old Name",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("10.00"),
        current_balance=Decimal("50.00"),
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()

    update_payload = {
        "name": "New Name",
        "type": "credit",
        "subtype": "credit card",
        "is_active": False,
        "starting_balance": 150.00,
        "current_balance": 200.00,
    }

    response = client.put(f"/accounts/{account.id}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["type"] == "credit"
    assert data["subtype"] == "credit card"
    assert data["is_active"] is False
    assert Decimal(str(data["starting_balance"])) == Decimal("150.00")
    assert Decimal(str(data["current_balance"])) == Decimal("200.00")

    # Verify DB persistence
    db_session.refresh(account)
    assert account.name == "New Name"
    assert account.type == "credit"
    assert account.subtype == "credit card"
    assert account.is_active is False
    assert account.starting_balance == Decimal("150.00")
    assert account.current_balance == Decimal("200.00")


def test_update_account_partial_omitted_fields_preserved(client: TestClient, db_session):
    account = models.Account(
        name="Preserved Name",
        type="depository",
        subtype="savings",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("1000.00"),
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()

    # Only update starting_balance (like credit-cards.vue does)
    response = client.put(f"/accounts/{account.id}", json={"starting_balance": 750.00})
    assert response.status_code == 200
    data = response.json()
    assert Decimal(str(data["starting_balance"])) == Decimal("750.00")
    assert data["name"] == "Preserved Name"
    assert data["type"] == "depository"
    assert data["subtype"] == "savings"
    assert Decimal(str(data["current_balance"])) == Decimal("1000.00")
    assert data["is_active"] is True


def test_update_account_explicit_null_does_not_overwrite(client: TestClient, db_session):
    account = models.Account(
        name="Existing Name",
        type="depository",
        subtype="checking",
    )
    db_session.add(account)
    db_session.commit()

    # In router: for field in ...: if val is not None: setattr(...)
    # When explicit null is passed, val is None, so existing subtype is preserved!
    response = client.put(f"/accounts/{account.id}", json={"subtype": None})
    assert response.status_code == 200
    data = response.json()
    assert data["subtype"] == "checking"


def test_update_account_empty_body_succeeds(client: TestClient, db_session):
    account = models.Account(
        name="Unchanged",
        type="depository",
        subtype="checking",
    )
    db_session.add(account)
    db_session.commit()

    response = client.put(f"/accounts/{account.id}", json={})
    assert response.status_code == 200
    assert response.json()["name"] == "Unchanged"


def test_update_account_not_found_404(client: TestClient):
    random_id = uuid4()
    response = client.put(f"/accounts/{random_id}", json={"name": "Ghost"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Account not found"


def test_update_account_invalid_uuid_422(client: TestClient):
    response = client.put("/accounts/not-a-uuid", json={"name": "Ghost"})
    assert response.status_code == 422


def test_update_account_plaid_linked_account_preserves_plaid_fields(client: TestClient, db_session):
    item = create_plaid_item(db_session, plaid_item_id="plaid_up_it", access_token="tok")
    account = models.Account(
        name="Plaid CC",
        type="credit",
        item_id=item.id,
        plaid_account_id="plaid_cc_123",
        mask="9999",
        starting_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    response = client.put(f"/accounts/{account.id}", json={"starting_balance": 350.00})
    assert response.status_code == 200
    data = response.json()
    assert Decimal(str(data["starting_balance"])) == Decimal("350.00")
    assert data["plaid_account_id"] == "plaid_cc_123"
    assert data["item_id"] == str(item.id)
    assert data["mask"] == "9999"


# ---------------------------------------------------------------------------
# 6. Account Delete Endpoint (DELETE /accounts/{account_id})
# ---------------------------------------------------------------------------

def test_delete_account_success(client: TestClient, db_session):
    account = models.Account(
        name="To Be Deleted",
        type="depository",
    )
    db_session.add(account)
    db_session.commit()

    response = client.delete(f"/accounts/{account.id}")
    assert response.status_code == 204
    assert response.content == b""

    # Verify deleted from DB
    db_acc = db_session.query(models.Account).filter(models.Account.id == account.id).first()
    assert db_acc is None


def test_delete_account_not_found_404(client: TestClient):
    random_id = uuid4()
    response = client.delete(f"/accounts/{random_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Account not found"


def test_delete_account_invalid_uuid_422(client: TestClient):
    response = client.delete("/accounts/not-a-uuid")
    assert response.status_code == 422


def test_delete_plaid_linked_account_leaves_item_intact(client: TestClient, db_session):
    item = create_plaid_item(db_session, plaid_item_id="item_survive", access_token="tok")
    account = models.Account(
        name="Plaid Account",
        type="depository",
        item_id=item.id,
        plaid_account_id="plaid_survive_acc",
    )
    db_session.add(account)
    db_session.commit()

    response = client.delete(f"/accounts/{account.id}")
    assert response.status_code == 204

    # Account is gone
    assert db_session.query(models.Account).filter(models.Account.id == account.id).first() is None
    # PlaidItem remains
    assert db_session.query(models.PlaidItem).filter(models.PlaidItem.id == item.id).first() is not None


def test_delete_account_with_transactions_blocked_by_fk(client: TestClient, db_session):
    """
    Transaction has ForeignKey('accounts.id') without ON DELETE CASCADE.
    Attempting to delete the parent account triggers a database IntegrityError (500).
    The account and its transaction remain in the database.
    """
    from datetime import date

    account = models.Account(
        name="Account With Tx",
        type="depository",
    )
    db_session.add(account)
    db_session.commit()

    tx = models.Transaction(
        account_id=account.id,
        description="Coffee",
        amount=Decimal("4.50"),
        date=date(2026, 6, 1),
    )
    db_session.add(tx)
    db_session.commit()

    # The router does not catch IntegrityError, so FastAPI raises 500 Internal Server Error
    # Note: Depending on whether TestClient re-raises server exceptions (raise_server_exceptions),
    # let's verify what response status code or exception occurs.
    with pytest.raises(IntegrityError):
        client.delete(f"/accounts/{account.id}")

    # Roll back the failed transaction session to inspect state
    db_session.rollback()
    assert db_session.query(models.Account).filter(models.Account.id == account.id).first() is not None
    assert db_session.query(models.Transaction).filter(models.Transaction.transaction_id == tx.transaction_id).first() is not None
