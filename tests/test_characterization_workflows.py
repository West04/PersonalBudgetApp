from decimal import Decimal
from datetime import date
from io import BytesIO
from uuid import uuid4
import pytest

from backend import models


def test_manual_transaction_creation(client, db_session):
    """
    Test manual transaction creation via POST /transactions/:
    - Outflow (+50.00)
    - Inflow (-100.00)
    - Uncategorized (category_id = None)
    - Categorized (category_id = valid UUID)
    """
    # Create account
    account = models.Account(
        name="Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD"
    )
    group = models.CategoryGroup(name="General", sort_order=0)
    db_session.add_all([account, group])
    db_session.flush()

    category = models.Category(name="Misc", group_id=group.category_group_id, type="expense", sort_order=0)
    db_session.add(category)
    db_session.commit()

    # 1. Create categorized outflow
    payload1 = {
        "account_id": str(account.id),
        "category_id": str(category.category_id),
        "description": "Hardware Store",
        "amount": "45.99",
        "date": "2026-06-10",
        "pending": False
    }
    resp1 = client.post("/transactions/", json=payload1)
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert data1["description"] == "Hardware Store"
    assert Decimal(str(data1["amount"])) == Decimal("45.99")
    assert data1["category_id"] == str(category.category_id)
    assert data1["account_id"] == str(account.id)
    assert data1["pending"] is False

    # 2. Create uncategorized inflow
    payload2 = {
        "account_id": str(account.id),
        "category_id": None,
        "description": "Gift Deposit",
        "amount": "-150.00",
        "date": "2026-06-11",
        "pending": True
    }
    resp2 = client.post("/transactions/", json=payload2)
    assert resp2.status_code == 201
    data2 = resp2.json()
    assert data2["description"] == "Gift Deposit"
    assert Decimal(str(data2["amount"])) == Decimal("-150.00")
    assert data2["category_id"] is None
    assert data2["pending"] is True


def test_csv_confirmation_and_duplicate_skipping(client, db_session):
    """
    Test CSV confirmation and idempotency via POST /upload/confirm:
    - First upload: valid rows imported (imported = N, skipped = 0)
    - Re-upload same file: duplicate rows skipped (imported = 0, skipped = N)
    - Upload with 1 new row: imported = 1, skipped = N
    """
    account = models.Account(
        name="USAA Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("2500.00"),
        starting_balance=Decimal("0.00"),
        currency="USD"
    )
    db_session.add(account)
    db_session.commit()

    csv_content_1 = (
        "Date,Description,Category,Amount,Status\n"
        "2026-06-01,GROCERY STORE,Food,-54.20,posted\n"
        "2026-06-02,GAS STATION,Auto,-35.00,posted\n"
        "2026-06-03,ELECTRIC BILL,Utilities,-110.50,posted\n"
    )

    # First upload
    files1 = {
        "file": ("statement.csv", BytesIO(csv_content_1.encode("utf-8")), "text/csv")
    }
    data_form1 = {
        "account_id": str(account.id),
        "format": "usaa"
    }
    resp1 = client.post("/upload/confirm", data=data_form1, files=files1)
    assert resp1.status_code == 200
    res1 = resp1.json()
    assert res1["imported"] == 3
    assert res1["skipped"] == 0
    assert len(res1["errors"]) == 0

    # Second upload: EXACT same file
    files2 = {
        "file": ("statement.csv", BytesIO(csv_content_1.encode("utf-8")), "text/csv")
    }
    resp2 = client.post("/upload/confirm", data=data_form1, files=files2)
    assert resp2.status_code == 200
    res2 = resp2.json()
    assert res2["imported"] == 0
    assert res2["skipped"] == 3
    assert len(res2["errors"]) == 0

    # Third upload: 3 existing rows + 1 brand new row
    csv_content_3 = csv_content_1 + "2026-06-04,BOOKSTORE,Misc,-19.99,posted\n"
    files3 = {
        "file": ("statement.csv", BytesIO(csv_content_3.encode("utf-8")), "text/csv")
    }
    resp3 = client.post("/upload/confirm", data=data_form1, files=files3)
    assert resp3.status_code == 200
    res3 = resp3.json()
    assert res3["imported"] == 1
    assert res3["skipped"] == 3


def test_transfer_confirmation(client, db_session):
    """
    Test confirming transfer pairs via POST /credit-cards/mark-transfers:
    - Submitting transaction UUIDs sets is_transfer = True in database
    """
    account1 = models.Account(name="Checking", type="depository", current_balance=Decimal("1000"), currency="USD")
    account2 = models.Account(name="Savings", type="depository", current_balance=Decimal("5000"), currency="USD")
    db_session.add_all([account1, account2])
    db_session.flush()

    t1 = models.Transaction(account_id=account1.id, amount=Decimal("200.00"), date=date(2026, 6, 1), is_transfer=False)
    t2 = models.Transaction(account_id=account2.id, amount=Decimal("-200.00"), date=date(2026, 6, 1), is_transfer=False)
    db_session.add_all([t1, t2])
    db_session.commit()

    resp = client.post("/credit-cards/mark-transfers", json={
        "transaction_ids": [str(t1.transaction_id), str(t2.transaction_id)]
    })
    assert resp.status_code == 204

    # Verify DB update
    db_session.refresh(t1)
    db_session.refresh(t2)
    assert t1.is_transfer is True
    assert t2.is_transfer is True


def test_category_and_group_reordering(client, db_session):
    """
    Test bulk reordering via:
    - POST /category-groups/reorder
    - POST /categories/reorder
    """
    g1 = models.CategoryGroup(name="Group A", sort_order=0)
    g2 = models.CategoryGroup(name="Group B", sort_order=1)
    g3 = models.CategoryGroup(name="Group C", sort_order=2)
    db_session.add_all([g1, g2, g3])
    db_session.flush()

    c1 = models.Category(name="Cat 1", group_id=g1.category_group_id, type="expense", sort_order=0)
    c2 = models.Category(name="Cat 2", group_id=g1.category_group_id, type="expense", sort_order=1)
    c3 = models.Category(name="Cat 3", group_id=g1.category_group_id, type="expense", sort_order=2)
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    # 1. Reverse groups order: C, B, A
    new_group_order = [str(g3.category_group_id), str(g2.category_group_id), str(g1.category_group_id)]
    resp_g = client.post("/category-groups/reorder", json={"order": new_group_order})
    assert resp_g.status_code == 200

    db_session.refresh(g1)
    db_session.refresh(g2)
    db_session.refresh(g3)
    assert g3.sort_order == 0
    assert g2.sort_order == 1
    assert g1.sort_order == 2

    # 2. Reverse categories order within Group A: Cat 3, Cat 1, Cat 2
    new_cat_order = [str(c3.category_id), str(c1.category_id), str(c2.category_id)]
    resp_c = client.post("/categories/reorder", json={
        "group_id": str(g1.category_group_id),
        "order": new_cat_order
    })
    assert resp_c.status_code == 200

    db_session.refresh(c1)
    db_session.refresh(c2)
    db_session.refresh(c3)
    assert c3.sort_order == 0
    assert c1.sort_order == 1
    assert c2.sort_order == 2


def test_transaction_description_nullability_mismatch_characterization(client, db_session):
    """
    Characterize Known Defect #1:
    Transaction.description database/schema nullability mismatch:
    - DB column 'description' is nullable (Column(Text) without nullable=False).
    - Pydantic schemas (TransactionCreate, TransactionRead) require 'description: str'.
    - POST /transactions/ with description=None is rejected with HTTP 422.
    - If a row with description=None exists in DB, querying GET /transactions/
      fails with ResponseValidationError (HTTP 500 equivalent) on TransactionRead.
    """
    from fastapi.exceptions import ResponseValidationError

    account = models.Account(
        name="Mismatch Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD"
    )
    db_session.add(account)
    db_session.commit()

    # 1. API creation rejects null description with 422
    payload_null_desc = {
        "account_id": str(account.id),
        "category_id": None,
        "description": None,
        "amount": "25.00",
        "date": "2026-06-15",
    }
    resp = client.post("/transactions/", json=payload_null_desc)
    assert resp.status_code == 422

    # 2. Database allows inserting description=None
    tx_null = models.Transaction(
        account_id=account.id,
        category_id=None,
        description=None,
        amount=Decimal("25.00"),
        date=date(2026, 6, 15),
    )
    db_session.add(tx_null)
    db_session.commit()

    # 3. But reading via TransactionRead raises ResponseValidationError (HTTP 500) due to schema mismatch
    with pytest.raises(ResponseValidationError):
        client.get(f"/transactions/?account_id={account.id}")


def test_backend_category_group_cascade_deletion_characterization(client, db_session):
    """
    Characterize Known Defect #2:
    Backend category-group deletion allows cascade deletion even though the frontend prohibits it:
    - In DB/backend, Category.group_id has ForeignKey ondelete="CASCADE" and CategoryGroup.categories has delete-orphan cascade.
    - Calling DELETE /category-groups/{group_id} deletes the group, child categories, and budgets.
    """
    group = models.CategoryGroup(name="Cascade Target Group", sort_order=99)
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Child Category", group_id=group.category_group_id, type="expense", sort_order=0)
    db_session.add(cat)
    db_session.flush()

    budget = models.Budget(budget_month=date(2026, 6, 1), planned_amount=Decimal("100.00"), category_id=cat.category_id)
    db_session.add(budget)
    db_session.commit()

    group_id = group.category_group_id
    cat_id = cat.category_id
    budget_id = budget.budget_id

    # Backend allows deletion of non-empty category group
    resp = client.delete(f"/category-groups/{group_id}")
    assert resp.status_code == 204

    # Expire session so identity map re-queries DB
    db_session.expire_all()

    # Confirm group and category are deleted via cascade; budget category_id is nulled out
    assert db_session.query(models.CategoryGroup).filter_by(category_group_id=group_id).first() is None
    assert db_session.query(models.Category).filter_by(category_id=cat_id).first() is None
    orphaned_budget = db_session.query(models.Budget).filter_by(budget_id=budget_id).first()
    assert orphaned_budget is not None
    assert orphaned_budget.category_id is None



