"""
Characterization and regression tests for authoritative Depository Current Balance derivation.

Covers:
1. starting balance only
2. expense only
3. income only
4. mixed expense + income (concrete prompt example: 500 opening, +50 grocery, -200 paycheck -> 650)
5. editing starting balance
6. transaction creation
7. transaction edit if supported
8. transaction deletion if supported
9. manual/CSV vs Plaid balance source distinction
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from starlette.testclient import TestClient

from backend import models


def test_depository_balance_starting_balance_only(client: TestClient, db_session):
    account = models.Account(
        name="Checking No Txns",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),  # Stale stored column
    )
    db_session.add(account)
    db_session.commit()

    response = client.get("/accounts/")
    assert response.status_code == 200
    items = {a["name"]: a for a in response.json()}
    acc_data = items["Checking No Txns"]

    assert Decimal(str(acc_data["starting_balance"])) == Decimal("500.00")
    # Derived balance with 0 transactions equals starting_balance
    assert Decimal(str(acc_data["current_balance"])) == Decimal("500.00")


def test_depository_balance_expense_only(client: TestClient, db_session):
    account = models.Account(
        name="Checking Expense Only",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    # Outflow expense of +50.00
    txn = models.Transaction(
        account_id=account.id,
        amount=Decimal("50.00"),
        date=date(2026, 3, 15),
        description="Grocery Store",
    )
    db_session.add(txn)
    db_session.commit()

    response = client.get("/accounts/")
    assert response.status_code == 200
    items = {a["name"]: a for a in response.json()}
    acc_data = items["Checking Expense Only"]

    # 500.00 - 50.00 = 450.00
    assert Decimal(str(acc_data["current_balance"])) == Decimal("450.00")


def test_depository_balance_income_only(client: TestClient, db_session):
    account = models.Account(
        name="Checking Income Only",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    # Inflow income of -200.00
    txn = models.Transaction(
        account_id=account.id,
        amount=Decimal("-200.00"),
        date=date(2026, 3, 15),
        description="Paycheck Deposit",
    )
    db_session.add(txn)
    db_session.commit()

    response = client.get("/accounts/")
    assert response.status_code == 200
    items = {a["name"]: a for a in response.json()}
    acc_data = items["Checking Income Only"]

    # 500.00 - (-200.00) = 700.00
    assert Decimal(str(acc_data["current_balance"])) == Decimal("700.00")


def test_depository_balance_mixed_expense_and_income_concrete_example(client: TestClient, db_session):
    """
    Concrete example from domain specification:
    opening balance:   $500
    grocery outflow:    +50
    paycheck inflow:   -200
    result:            $650
    """
    account = models.Account(
        name="Checking Concrete Spec",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    tx_grocery = models.Transaction(
        account_id=account.id,
        amount=Decimal("50.00"),
        date=date(2026, 3, 10),
        description="Groceries",
    )
    tx_paycheck = models.Transaction(
        account_id=account.id,
        amount=Decimal("-200.00"),
        date=date(2026, 3, 15),
        description="Paycheck",
    )
    db_session.add_all([tx_grocery, tx_paycheck])
    db_session.commit()

    response = client.get("/accounts/")
    assert response.status_code == 200
    items = {a["name"]: a for a in response.json()}
    acc_data = items["Checking Concrete Spec"]

    # net = 50.00 + (-200.00) = -150.00
    # balance = 500.00 - (-150.00) = 650.00
    assert Decimal(str(acc_data["current_balance"])) == Decimal("650.00")


def test_depository_balance_editing_starting_balance(client: TestClient, db_session):
    account = models.Account(
        name="Checking Edit Starting Balance",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    # Add transaction +50.00
    txn = models.Transaction(
        account_id=account.id,
        amount=Decimal("50.00"),
        date=date(2026, 3, 10),
        description="Groceries",
    )
    db_session.add(txn)
    db_session.commit()

    # Verify initial balance is 500 - 50 = 450
    res1 = client.get("/accounts/")
    items1 = {a["name"]: a for a in res1.json()}
    assert Decimal(str(items1["Checking Edit Starting Balance"]["current_balance"])) == Decimal("450.00")

    # Update starting_balance to 1000.00 via PUT /accounts/{id}
    put_res = client.put(f"/accounts/{account.id}", json={"starting_balance": 1000.00})
    assert put_res.status_code == 200

    # Verify GET /accounts/ recomputes balance from new starting_balance: 1000 - 50 = 950
    res2 = client.get("/accounts/")
    items2 = {a["name"]: a for a in res2.json()}
    acc_updated = items2["Checking Edit Starting Balance"]
    assert Decimal(str(acc_updated["starting_balance"])) == Decimal("1000.00")
    assert Decimal(str(acc_updated["current_balance"])) == Decimal("950.00")


def test_depository_balance_transaction_creation(client: TestClient, db_session):
    account = models.Account(
        name="Checking Txn Creation",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    # Check baseline balance = 500
    res1 = client.get("/accounts/")
    items1 = {a["name"]: a for a in res1.json()}
    assert Decimal(str(items1["Checking Txn Creation"]["current_balance"])) == Decimal("500.00")

    # Create transaction via POST /transactions/
    payload = {
        "account_id": str(account.id),
        "amount": 75.25,
        "date": "2026-03-20",
        "description": "Hardware Store",
    }
    create_res = client.post("/transactions/", json=payload)
    assert create_res.status_code == 201

    # Check that GET /accounts/ immediately reflects transaction: 500.00 - 75.25 = 424.75
    res2 = client.get("/accounts/")
    items2 = {a["name"]: a for a in res2.json()}
    assert Decimal(str(items2["Checking Txn Creation"]["current_balance"])) == Decimal("424.75")


def test_depository_balance_transaction_edit_supported(client: TestClient, db_session):
    account = models.Account(
        name="Checking Txn Edit",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    txn = models.Transaction(
        account_id=account.id,
        amount=Decimal("100.00"),
        date=date(2026, 3, 10),
        description="Original Desc",
    )
    db_session.add(txn)
    db_session.commit()

    # Baseline balance = 400.00
    res1 = client.get("/accounts/")
    items1 = {a["name"]: a for a in res1.json()}
    assert Decimal(str(items1["Checking Txn Edit"]["current_balance"])) == Decimal("400.00")

    # Edit transaction via PUT /transactions/{id} (description edit)
    edit_res = client.put(f"/transactions/{txn.transaction_id}", json={"description": "Updated Desc"})
    assert edit_res.status_code == 200

    # Balance remains correct
    res2 = client.get("/accounts/")
    items2 = {a["name"]: a for a in res2.json()}
    assert Decimal(str(items2["Checking Txn Edit"]["current_balance"])) == Decimal("400.00")


def test_depository_balance_transaction_deletion(client: TestClient, db_session):
    account = models.Account(
        name="Checking Txn Deletion",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),
    )
    db_session.add(account)
    db_session.commit()

    txn = models.Transaction(
        account_id=account.id,
        amount=Decimal("100.00"),
        date=date(2026, 3, 10),
        description="Pending Charge",
    )
    db_session.add(txn)
    db_session.commit()

    # Balance with transaction: 500 - 100 = 400
    res1 = client.get("/accounts/")
    items1 = {a["name"]: a for a in res1.json()}
    assert Decimal(str(items1["Checking Txn Deletion"]["current_balance"])) == Decimal("400.00")

    # Delete transaction via DELETE /transactions/{id}
    del_res = client.delete(f"/transactions/{txn.transaction_id}")
    assert del_res.status_code == 204

    # Balance after deletion reverts to starting_balance: 500.00
    res2 = client.get("/accounts/")
    items2 = {a["name"]: a for a in res2.json()}
    assert Decimal(str(items2["Checking Txn Deletion"]["current_balance"])) == Decimal("500.00")


def test_depository_balance_manual_vs_plaid_distinction(client: TestClient, db_session):
    # Setup Plaid item
    plaid_item = models.PlaidItem(
        plaid_item_id="plaid_item_test_balance",
        plaid_access_token_encrypted="test_tok_enc",
    )
    db_session.add(plaid_item)
    db_session.commit()

    # Plaid-linked account: has plaid_account_id and item_id
    # Provider supplied balance = 1234.56
    plaid_account = models.Account(
        name="Plaid Checking",
        type="depository",
        subtype="checking",
        item_id=plaid_item.id,
        plaid_account_id="plaid_acc_test_bal",
        starting_balance=Decimal("0.00"),
        current_balance=Decimal("1234.56"),
    )

    # Manual account: plaid_account_id is None
    # starting_balance = 1234.56, stored current_balance = 0.00 (stale)
    manual_account = models.Account(
        name="Manual Checking",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("1234.56"),
        current_balance=Decimal("0.00"),
    )
    db_session.add_all([plaid_account, manual_account])
    db_session.commit()

    # Add identical transactions to both accounts: amount = 100.00
    tx_plaid = models.Transaction(
        account_id=plaid_account.id,
        amount=Decimal("100.00"),
        date=date(2026, 3, 10),
        description="Store Purchase",
    )
    tx_manual = models.Transaction(
        account_id=manual_account.id,
        amount=Decimal("100.00"),
        date=date(2026, 3, 10),
        description="Store Purchase",
    )
    db_session.add_all([tx_plaid, tx_manual])
    db_session.commit()

    response = client.get("/accounts/")
    assert response.status_code == 200
    items = {a["name"]: a for a in response.json()}

    # Plaid account retains provider-supplied current_balance
    assert Decimal(str(items["Plaid Checking"]["current_balance"])) == Decimal("1234.56")

    # Manual account derives current_balance from ledger: 1234.56 - 100.00 = 1134.56
    assert Decimal(str(items["Manual Checking"]["current_balance"])) == Decimal("1134.56")


def test_depository_balance_get_does_not_mutate_persisted_account_column(client: TestClient, db_session):
    """
    Regression test:
    GET /api/accounts/
    -> returns derived manual depository balance
    -> persisted accounts.current_balance remains unchanged
    """
    account = models.Account(
        name="Checking Immutability Test",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("0.00"),  # Stored column explicitly 0.00
    )
    db_session.add(account)
    db_session.commit()

    txn = models.Transaction(
        account_id=account.id,
        amount=Decimal("50.00"),
        date=date(2026, 3, 10),
        description="Grocery",
    )
    db_session.add(txn)
    db_session.commit()

    # 1. GET /accounts/ returns derived balance: 500.00 - 50.00 = 450.00
    response = client.get("/accounts/")
    assert response.status_code == 200
    items = {a["name"]: a for a in response.json()}
    assert Decimal(str(items["Checking Immutability Test"]["current_balance"])) == Decimal("450.00")

    # 2. Persisted accounts.current_balance in database remains 0.00
    db_session.expire_all()
    persisted_acc = db_session.query(models.Account).filter_by(id=account.id).one()
    assert persisted_acc.current_balance == Decimal("0.00")
    assert not db_session.is_modified(persisted_acc)
    assert persisted_acc not in db_session.dirty

