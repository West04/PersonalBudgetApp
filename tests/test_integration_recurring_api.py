"""
Integration tests for Recurring Transactions API endpoints (/recurring/).
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend import models
from backend.access import transaction_access

client = TestClient(app)


def _create_account(db: Session, name="Checking Account") -> models.Account:
    acc = models.Account(
        id=uuid4(),
        name=name,
        type="depository",
        subtype="checking",
        current_balance=Decimal("2000.00"),
        starting_balance=Decimal("2000.00"),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def test_list_and_detect_recurring_api(db_session: Session):
    acc = _create_account(db_session)

    # Seed 3 monthly transactions for Netflix
    for dt in [date(2026, 6, 15), date(2026, 7, 15), date(2026, 8, 15)]:
        transaction_access.stage_manual_transaction(
            db=db_session,
            account_id=acc.id,
            amount=Decimal("15.49"),
            transaction_date=dt,
            description="NETFLIX.COM",
            merchant="Netflix",
            is_merchant_overridden=False,
        )
    db_session.commit()

    # 1. GET /recurring/ triggers initial detection
    res = client.get("/recurring/")
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    netflix = next(i for i in items if i["merchant"] == "Netflix")
    assert netflix["cadence"] == "monthly"
    assert netflix["status"] == "detected"
    assert Decimal(str(netflix["expected_amount"])) == Decimal("15.49")
    assert len(netflix["transaction_ids"]) == 3
    netflix_id = netflix["id"]

    # 2. GET /recurring/{id}
    res_detail = client.get(f"/recurring/{netflix_id}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["id"] == netflix_id
    assert len(detail["transactions"]) == 3

    # 3. POST /recurring/{id}/confirm
    res_confirm = client.post(f"/recurring/{netflix_id}/confirm")
    assert res_confirm.status_code == 200
    assert res_confirm.json()["status"] == "confirmed"

    # Verify confirmed via GET
    res_get = client.get(f"/recurring/{netflix_id}")
    assert res_get.json()["status"] == "confirmed"

    # 4. POST /recurring/{id}/dismiss
    res_dismiss = client.post(f"/recurring/{netflix_id}/dismiss")
    assert res_dismiss.status_code == 200
    assert res_dismiss.json()["status"] == "dismissed"

    # 5. POST /recurring/detect (re-sync) preserves dismissed status
    res_sync = client.post("/recurring/detect")
    assert res_sync.status_code == 200
    items_after = res_sync.json()
    netflix_after = next(i for i in items_after if i["id"] == netflix_id)
    assert netflix_after["status"] == "dismissed"


def test_recurring_api_not_found():
    random_id = str(uuid4())
    res = client.get(f"/recurring/{random_id}")
    assert res.status_code == 404

    res_conf = client.post(f"/recurring/{random_id}/confirm")
    assert res_conf.status_code == 404

    res_dism = client.post(f"/recurring/{random_id}/dismiss")
    assert res_dism.status_code == 404
