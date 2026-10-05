"""
Integration tests for Phase 7 Account Reconciliation HTTP endpoints:
- GET /accounts/{id}/reconciliation
- PATCH /transactions/{id}/cleared
- POST /accounts/{id}/reconciliation/complete
- DELETE /transactions/{id} protection for reconciled transactions
- Independence of Phase 6 review state and transfer status
- Verification that depository current balance formula is not regressed
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend import models


def test_reconciliation_http_lifecycle(client: TestClient, db_session):
    # 1. Create a checking account
    account = models.Account(
        name="Main Checking",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("1000.00"),
    )
    db_session.add(account)
    db_session.commit()

    # 2. Add transactions
    t1 = models.Transaction(
        account_id=account.id,
        description="Grocery",
        amount=Decimal("50.00"),
        date=date(2026, 10, 5),
        is_cleared=False,
    )
    t2 = models.Transaction(
        account_id=account.id,
        description="Paycheck",
        amount=Decimal("-500.00"),
        date=date(2026, 10, 15),
        is_cleared=False,
    )
    t3 = models.Transaction(
        account_id=account.id,
        description="Utility",
        amount=Decimal("100.00"),
        date=date(2026, 10, 20),
        is_cleared=False,
    )
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # 3. GET initial reconciliation workspace
    resp = client.get(
        f"/accounts/{account.id}/reconciliation",
        params={"ending_date": "2026-10-31", "ending_balance": "1350.00"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["account_name"] == "Main Checking"
    assert data["prior_reconciled_balance"] == "1000.00"
    assert data["statement_ending_balance"] == "1350.00"
    assert data["cleared_balance"] == "1000.00"  # No cleared transactions yet
    assert data["difference"] == "350.00"  # 1350 - 1000 = 350
    assert data["is_balanced"] is False
    assert len(data["transactions"]) == 3

    # 4. Clear transactions one by one via PATCH /transactions/{id}/cleared
    for tx in [t1, t2, t3]:
        patch_resp = client.patch(
            f"/transactions/{tx.transaction_id}/cleared",
            json={"is_cleared": True},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["is_cleared"] is True

    # 5. GET reconciliation workspace again - should now be balanced
    resp2 = client.get(
        f"/accounts/{account.id}/reconciliation",
        params={"ending_date": "2026-10-31", "ending_balance": "1350.00"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cleared_balance"] == "1350.00"
    assert data2["difference"] == "0.00"
    assert data2["is_balanced"] is True

    # 6. Attempting completion with wrong ending balance must return 400
    bad_comp = client.post(
        f"/accounts/{account.id}/reconciliation/complete",
        json={"statement_ending_date": "2026-10-31", "statement_ending_balance": "1300.00"},
    )
    assert bad_comp.status_code == 400
    assert "does not match cleared balance" in bad_comp.json()["detail"]

    # 7. Complete reconciliation with correct balance 1350.00
    comp_resp = client.post(
        f"/accounts/{account.id}/reconciliation/complete",
        json={"statement_ending_date": "2026-10-31", "statement_ending_balance": "1350.00"},
    )
    assert comp_resp.status_code == 200
    comp_data = comp_resp.json()
    assert comp_data["last_reconciled_date"] == "2026-10-31"
    assert comp_data["last_reconciled_balance"] == "1350.00"
    # Unreconciled transactions list is now empty!
    assert len(comp_data["transactions"]) == 0

    # 8. Deleting a reconciled transaction must be blocked with 400
    del_resp = client.delete(f"/transactions/{t1.transaction_id}")
    assert del_resp.status_code == 400
    assert "Cannot delete a reconciled transaction" in del_resp.json()["detail"]

    # 9. Modifying cleared status of a reconciled transaction must be blocked with 400
    patch_blocked = client.patch(
        f"/transactions/{t1.transaction_id}/cleared",
        json={"is_cleared": False},
    )
    assert patch_blocked.status_code == 400
    assert "already reconciled" in patch_blocked.json()["detail"]

    # 10. Check account listing to ensure current_balance formula remains exact
    # current_balance = 1000 - (50 - 500 + 100) = 1350.00
    acc_resp = client.get("/accounts/")
    acc_match = next(a for a in acc_resp.json() if a["account_id"] == str(account.id))
    assert Decimal(str(acc_match["current_balance"])) == Decimal("1350.00")
    assert acc_match["last_reconciled_date"] == "2026-10-31"
    assert Decimal(str(acc_match["last_reconciled_balance"])) == Decimal("1350.00")


def test_review_and_transfer_independence_during_reconciliation(client: TestClient, db_session):
    account = models.Account(
        name="Savings",
        type="depository",
        subtype="savings",
        starting_balance=Decimal("2000.00"),
    )
    db_session.add(account)
    db_session.commit()

    # Transaction with is_reviewed=False and is_transfer=True
    t_transfer = models.Transaction(
        account_id=account.id,
        description="Transfer from Checking",
        amount=Decimal("-300.00"),  # Inflow
        date=date(2026, 10, 10),
        is_transfer=True,
        is_reviewed=False,
        is_cleared=True,
    )
    db_session.add(t_transfer)
    db_session.commit()

    # Reconcile: prior 2000.00 - (-300.00) = 2300.00
    comp_resp = client.post(
        f"/accounts/{account.id}/reconciliation/complete",
        json={"statement_ending_date": "2026-10-31", "statement_ending_balance": "2300.00"},
    )
    assert comp_resp.status_code == 200

    # Verify transaction in DB:
    db_session.refresh(t_transfer)
    assert t_transfer.is_reconciled is True
    # Review state remains False (unaffected)
    assert t_transfer.is_reviewed is False
    # Transfer status remains True (unaffected)
    assert t_transfer.is_transfer is True


def test_api_reconciled_transaction_financial_guards_and_permitted_edits(client: TestClient, db_session):
    acc1 = models.Account(name="Acct 1", type="depository")
    acc2 = models.Account(name="Acct 2", type="depository")
    group = models.CategoryGroup(name="Expenses")
    db_session.add_all([acc1, acc2, group])
    db_session.flush()

    cat1 = models.Category(name="Dining", group_id=group.category_group_id)
    cat2 = models.Category(name="Groceries", group_id=group.category_group_id)
    db_session.add_all([cat1, cat2])
    db_session.flush()

    tx = models.Transaction(
        account_id=acc1.id,
        category_id=cat1.category_id,
        description="Reconciled Dinner",
        amount=Decimal("75.00"),
        date=date(2026, 10, 8),
        is_cleared=True,
        is_reconciled=True,
        is_reviewed=False,
    )
    db_session.add(tx)
    db_session.commit()
    tx_id = str(tx.transaction_id)

    # 1. Prohibited: updating amount on reconciled transaction -> 400 Bad Request
    r_amt = client.put(f"/transactions/{tx_id}", json={"amount": "100.00"})
    assert r_amt.status_code == 400
    assert "Cannot modify financial fields" in r_amt.json()["detail"]

    # 2. Prohibited: updating date on reconciled transaction -> 400 Bad Request
    r_date = client.put(f"/transactions/{tx_id}", json={"date": "2026-10-09"})
    assert r_date.status_code == 400
    assert "Cannot modify financial fields" in r_date.json()["detail"]

    # 3. Prohibited: updating account_id on reconciled transaction -> 400 Bad Request
    r_acc = client.put(f"/transactions/{tx_id}", json={"account_id": str(acc2.id)})
    assert r_acc.status_code == 400
    assert "Cannot modify financial fields" in r_acc.json()["detail"]

    # 4. Prohibited: deleting reconciled transaction -> 400 Bad Request
    r_del = client.delete(f"/transactions/{tx_id}")
    assert r_del.status_code == 400
    assert "Cannot delete a reconciled transaction" in r_del.json()["detail"]

    # 5. Permitted: updating category_id on reconciled transaction -> 200 OK
    r_cat = client.put(f"/transactions/{tx_id}", json={"category_id": str(cat2.category_id)})
    assert r_cat.status_code == 200
    assert r_cat.json()["category_id"] == str(cat2.category_id)

    # 6. Permitted: updating description/note on reconciled transaction -> 200 OK
    r_desc = client.put(f"/transactions/{tx_id}", json={"description": "Business Dinner with Client"})
    assert r_desc.status_code == 200
    assert r_desc.json()["description"] == "Business Dinner with Client"

    # 7. Permitted: updating is_reviewed on reconciled transaction -> 200 OK
    r_rev = client.put(f"/transactions/{tx_id}", json={"is_reviewed": True})
    assert r_rev.status_code == 200
    assert r_rev.json()["is_reviewed"] is True

    # 8. Verify DB state integrity
    db_session.refresh(tx)
    assert tx.amount == Decimal("75.00")
    assert tx.date == date(2026, 10, 8)
    assert tx.account_id == acc1.id
    assert tx.category_id == cat2.category_id
    assert tx.description == "Business Dinner with Client"
    assert tx.is_reviewed is True
    assert tx.is_reconciled is True


def test_api_pending_transaction_reconciliation_exclusion_and_clearing_block(client: TestClient, db_session):
    account = models.Account(
        name="Plaid Checking",
        type="depository",
        subtype="checking",
        starting_balance=Decimal("500.00"),
    )
    db_session.add(account)
    db_session.commit()

    # Create one posted Plaid transaction and one pending Plaid transaction
    posted_tx = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="plaid_posted_1",
        description="Posted Target Store",
        amount=Decimal("45.00"),
        date=date(2026, 10, 12),
        pending=False,
        is_cleared=False,
        is_reconciled=False,
    )
    pending_tx = models.Transaction(
        account_id=account.id,
        plaid_transaction_id="plaid_pending_2",
        description="Pending Gas Station",
        amount=Decimal("30.00"),
        date=date(2026, 10, 14),
        pending=True,
        is_cleared=False,
        is_reconciled=False,
    )
    db_session.add_all([posted_tx, pending_tx])
    db_session.commit()

    # 1. GET reconciliation workspace -> pending transaction MUST NOT be included
    recon_resp = client.get(
        f"/accounts/{account.id}/reconciliation",
        params={"ending_date": "2026-10-31", "ending_balance": "455.00"},
    )
    assert recon_resp.status_code == 200
    recon_data = recon_resp.json()
    recon_tx_ids = [t["transaction_id"] for t in recon_data["transactions"]]
    assert str(posted_tx.transaction_id) in recon_tx_ids
    assert str(pending_tx.transaction_id) not in recon_tx_ids

    # 2. Attempting to mark pending transaction as cleared via PATCH -> 400 Bad Request
    patch_pend = client.patch(
        f"/transactions/{pending_tx.transaction_id}/cleared",
        json={"is_cleared": True},
    )
    assert patch_pend.status_code == 400
    assert "Cannot mark a pending transaction as cleared" in patch_pend.json()["detail"]

    # 3. Marking posted transaction as cleared -> 200 OK
    patch_post = client.patch(
        f"/transactions/{posted_tx.transaction_id}/cleared",
        json={"is_cleared": True},
    )
    assert patch_post.status_code == 200
    assert patch_post.json()["is_cleared"] is True
