from decimal import Decimal
from datetime import date
from uuid import uuid4
from backend import models


def test_rules_api_crud(client, db_session):
    group = models.CategoryGroup(name="Everyday")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Dining Out", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.commit()

    # 1. Create rule
    resp = client.post(
        "/rules/",
        json={"merchant": "Starbucks", "category_id": str(cat.category_id)},
    )
    assert resp.status_code == 201
    rule_data = resp.json()
    assert rule_data["merchant"] == "Starbucks"
    assert rule_data["category_id"] == str(cat.category_id)
    assert rule_data["category"]["name"] == "Dining Out"
    rule_id = rule_data["id"]

    # 2. List rules
    list_resp = client.get("/rules/")
    assert list_resp.status_code == 200
    rules = list_resp.json()
    assert len(rules) == 1
    assert rules[0]["id"] == rule_id

    # 3. Duplicate creation rejected (400)
    dup_resp = client.post(
        "/rules/",
        json={"merchant": " starbucks ", "category_id": str(cat.category_id)},
    )
    assert dup_resp.status_code == 400
    assert "already exists" in dup_resp.json()["detail"]

    # 4. Get by ID
    get_resp = client.get(f"/rules/{rule_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["merchant"] == "Starbucks"

    # 5. Update rule
    upd_resp = client.put(
        f"/rules/{rule_id}",
        json={"merchant": "Starbucks Coffee"},
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["merchant"] == "Starbucks Coffee"

    # 6. Delete rule
    del_resp = client.delete(f"/rules/{rule_id}")
    assert del_resp.status_code == 204

    # 7. Confirm deleted
    assert client.get(f"/rules/{rule_id}").status_code == 404


def test_rules_api_preview_and_apply(client, db_session):
    acc = models.Account(name="Checking", type="depository")
    group = models.CategoryGroup(name="Everyday")
    db_session.add_all([acc, group])
    db_session.flush()

    cat_dining = models.Category(name="Dining", group_id=group.category_group_id, type="expense")
    cat_shopping = models.Category(name="Shopping", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat_dining, cat_shopping])
    db_session.commit()

    # Create 3 transactions:
    # tx1: Starbucks, category_id = None (uncategorized)
    # tx2: Starbucks, category_id = None (uncategorized)
    # tx3: Starbucks, category_id = Shopping (already categorized)
    tx1 = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #1234",
        merchant="Starbucks",
        amount=Decimal("5.50"),
        date=date(2026, 6, 1),
        category_id=None,
    )
    tx2 = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #5678",
        merchant="Starbucks",
        amount=Decimal("4.25"),
        date=date(2026, 6, 2),
        category_id=None,
    )
    tx3 = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS STORE",
        merchant="Starbucks",
        amount=Decimal("25.00"),
        date=date(2026, 6, 3),
        category_id=cat_shopping.category_id,
    )
    db_session.add_all([tx1, tx2, tx3])
    db_session.commit()

    # Create rule Starbucks -> Dining
    create_resp = client.post(
        "/rules/",
        json={"merchant": "Starbucks", "category_id": str(cat_dining.category_id)},
    )
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    # Preview retroactive matches
    prev_resp = client.get(f"/rules/{rule_id}/preview")
    assert prev_resp.status_code == 200
    assert prev_resp.json()["matching_count"] == 2  # Only tx1 and tx2; tx3 already has category

    # Apply rule retroactively
    apply_resp = client.post(f"/rules/{rule_id}/apply")
    assert apply_resp.status_code == 200
    assert apply_resp.json()["applied_count"] == 2

    # Verify transactions in DB
    db_session.expire_all()
    t1 = db_session.query(models.Transaction).filter_by(transaction_id=tx1.transaction_id).one()
    t2 = db_session.query(models.Transaction).filter_by(transaction_id=tx2.transaction_id).one()
    t3 = db_session.query(models.Transaction).filter_by(transaction_id=tx3.transaction_id).one()

    assert t1.category_id == cat_dining.category_id
    assert t2.category_id == cat_dining.category_id
    assert t3.category_id == cat_shopping.category_id  # Untouched!


def test_rules_api_canonical_uniqueness(client, db_session):
    """
    Audit 1:
    create 'Starbucks'
    then create 'STARBUCKS' -> rejected
    then create ' Starbucks ' -> rejected
    edit another rule to '  STARBUCKS  ' -> rejected
    """
    group = models.CategoryGroup(name="Everyday")
    db_session.add(group)
    db_session.flush()

    cat = models.Category(name="Dining Out", group_id=group.category_group_id, type="expense")
    db_session.add(cat)
    db_session.commit()

    # 1. Create "Starbucks"
    resp1 = client.post(
        "/rules/",
        json={"merchant": "Starbucks", "category_id": str(cat.category_id)},
    )
    assert resp1.status_code == 201
    assert resp1.json()["merchant"] == "Starbucks"

    # 2. Create "STARBUCKS" -> rejected
    resp2 = client.post(
        "/rules/",
        json={"merchant": "STARBUCKS", "category_id": str(cat.category_id)},
    )
    assert resp2.status_code in (400, 409)
    assert "already exists" in resp2.json()["detail"]

    # 3. Create " Starbucks " -> rejected
    resp3 = client.post(
        "/rules/",
        json={"merchant": " Starbucks ", "category_id": str(cat.category_id)},
    )
    assert resp3.status_code in (400, 409)
    assert "already exists" in resp3.json()["detail"]

    # 4. Create "Peets"
    resp4 = client.post(
        "/rules/",
        json={"merchant": "Peets", "category_id": str(cat.category_id)},
    )
    assert resp4.status_code == 201
    peets_id = resp4.json()["id"]

    # 5. Edit "Peets" to "  STARBUCKS  " -> rejected
    resp5 = client.put(
        f"/rules/{peets_id}",
        json={"merchant": "  STARBUCKS  "},
    )
    assert resp5.status_code in (400, 409)
    assert "already exists" in resp5.json()["detail"]
