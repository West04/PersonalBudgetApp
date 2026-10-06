"""
Integration tests for Split Transactions (Phase 12).

Verifies cross-cutting behavior across:
1. REST API endpoints (GET/PUT /splits, POST /unsplit).
2. Zero financial movement invariant (account balances & credit card balances unaffected).
3. Budget Actuals aggregation (combines unsplit transactions and split allocations cleanly).
4. Category filtering (matches parent category OR split allocations without row duplication).
5. Uncategorized filtering (splits are NOT treated as uncategorized).
6. Categorization rules exclusion (Phase 9 rules cannot mutate split transactions).
7. Transfer candidates & matching exclusion (splits cannot be paired as transfers).
8. ML suggestion inference exclusion (Phase 10 suggestions exclude split transactions).
9. Category deletion protection (cannot delete a category referenced by a split allocation).
10. Reconciled transaction split editing (splits can be adjusted without violating parent ledger immutability).
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest

from backend import models
from backend.access import category_access, transaction_access
from backend.managers import account_summary_manager, credit_card_summary_manager, ml_categorization_manager


def _setup_environment(db_session):
    acc = models.Account(
        name="Main Checking",
        type="depository",
        starting_balance=Decimal("2000.00"),
        current_balance=Decimal("2000.00"),
    )
    db_session.add(acc)
    db_session.flush()

    group = models.CategoryGroup(name="Living")
    db_session.add(group)
    db_session.flush()

    cat1 = models.Category(name="Groceries", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Household", group_id=group.category_group_id, type="expense")
    cat3 = models.Category(name="Clothing", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2, cat3])
    db_session.commit()
    return acc, cat1, cat2, cat3


def test_zero_financial_effect_on_account_balance(db_session):
    """Account balance uses parent transaction amount exactly once, before and after splitting."""
    acc, cat1, cat2, _ = _setup_environment(db_session)

    # 1. Create a parent transaction of $150.00 (outflow)
    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 15),
        amount=Decimal("150.00"),
        description="Costco Wholesale",
    )
    db_session.add(tx)
    db_session.commit()

    # Balance with parent transaction only: 2000 - 150 = 1850
    summaries_before = account_summary_manager.get_accounts_summary(db_session)
    acc_summary_before = next(s for s in summaries_before if s.account_id == acc.id)
    assert acc_summary_before.current_balance == Decimal("1850.00")

    # 2. Split transaction into $100 Groceries + $50 Household
    split1 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat1.category_id,
        amount=Decimal("100.00"),
    )
    split2 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat2.category_id,
        amount=Decimal("50.00"),
    )
    tx.category_id = None
    tx.category_source = None
    db_session.add_all([tx, split1, split2])
    db_session.commit()

    # Balance must remain exactly 1850.00 (split amounts are NOT added to financial movement)
    summaries_after = account_summary_manager.get_accounts_summary(db_session)
    acc_summary_after = next(s for s in summaries_after if s.account_id == acc.id)
    assert acc_summary_after.current_balance == Decimal("1850.00")


def test_credit_card_balance_invariance(db_session):
    """Credit card balance owed is completely unaffected by splitting transactions."""
    cc_acc = models.Account(
        name="Sapphire Card",
        type="credit",
        starting_balance=Decimal("500.00"),
    )
    db_session.add(cc_acc)
    db_session.flush()

    group = models.CategoryGroup(name="Living")
    db_session.add(group)
    db_session.flush()

    cat1 = models.Category(name="Dining", group_id=group.category_group_id, type="expense")
    cat2 = models.Category(name="Entertainment", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat1, cat2])
    db_session.commit()

    tx = models.Transaction(
        account_id=cc_acc.id,
        date=date(2026, 6, 10),
        amount=Decimal("80.00"),
        description="Dinner & Movie",
    )
    db_session.add(tx)
    db_session.commit()

    summary_before = credit_card_summary_manager.get_credit_card_summary(db_session, date(2026, 6, 1))
    assert summary_before.cards[0].state.balance_owed == Decimal("580.00")

    # Split charge
    split1 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat1.category_id,
        amount=Decimal("50.00"),
    )
    split2 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat2.category_id,
        amount=Decimal("30.00"),
    )
    tx.category_id = None
    db_session.add_all([tx, split1, split2])
    db_session.commit()

    summary_after = credit_card_summary_manager.get_credit_card_summary(db_session, date(2026, 6, 1))
    assert summary_after.cards[0].state.balance_owed == Decimal("580.00")


def test_budget_actuals_aggregation(db_session):
    """get_actuals_by_category correctly combines unsplit transactions and split allocations."""
    acc, cat1, cat2, cat3 = _setup_environment(db_session)

    # 1. Unsplit transaction in cat1: $40.00
    tx1 = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 5),
        amount=Decimal("40.00"),
        description="Trader Joes",
        category_id=cat1.category_id,
    )
    db_session.add(tx1)

    # 2. Split transaction: $150.00 -> $100.00 cat1 + $50.00 cat2
    tx2 = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 12),
        amount=Decimal("150.00"),
        description="Target",
        category_id=None,
    )
    db_session.add(tx2)
    db_session.flush()

    s1 = models.TransactionSplit(
        transaction_id=tx2.transaction_id,
        category_id=cat1.category_id,
        amount=Decimal("100.00"),
    )
    s2 = models.TransactionSplit(
        transaction_id=tx2.transaction_id,
        category_id=cat2.category_id,
        amount=Decimal("50.00"),
    )
    db_session.add_all([s1, s2])

    # 3. Inflow split (refund): -$30.00 -> -$20.00 cat1 + -$10.00 cat2
    tx3 = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 20),
        amount=Decimal("-30.00"),
        description="Target Return",
        category_id=None,
    )
    db_session.add(tx3)
    db_session.flush()

    s3 = models.TransactionSplit(
        transaction_id=tx3.transaction_id,
        category_id=cat1.category_id,
        amount=Decimal("-20.00"),
    )
    s4 = models.TransactionSplit(
        transaction_id=tx3.transaction_id,
        category_id=cat2.category_id,
        amount=Decimal("-10.00"),
    )
    db_session.add_all([s3, s4])

    # 4. Out of month transaction (should not be in June 2026 actuals)
    tx_july = models.Transaction(
        account_id=acc.id,
        date=date(2026, 7, 1),
        amount=Decimal("60.00"),
        description="July groceries",
        category_id=cat1.category_id,
    )
    db_session.add(tx_july)
    db_session.commit()

    # Query actuals for 2026-06
    actuals = transaction_access.get_actuals_by_category(
        db=db_session,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
    )

    # cat1: 40 (unsplit) + 100 (split) - 20 (refund split) = 120.00
    assert actuals[cat1.category_id] == Decimal("120.00")
    # cat2: 50 (split) - 10 (refund split) = 40.00
    assert actuals[cat2.category_id] == Decimal("40.00")
    # cat3: no transactions
    assert cat3.category_id not in actuals


def test_category_and_uncategorized_filters(db_session):
    """Category filter matches parent or split allocations; uncategorized filter excludes splits."""
    acc, cat1, cat2, cat3 = _setup_environment(db_session)

    # Tx1: Normal cat1
    tx1 = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 1),
        amount=Decimal("50.00"),
        description="Unsplit Groceries",
        category_id=cat1.category_id,
    )
    # Tx2: Truly uncategorized
    tx2 = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 2),
        amount=Decimal("60.00"),
        description="Needs Categorization",
        category_id=None,
    )
    # Tx3: Split between cat1 and cat2
    tx3 = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 3),
        amount=Decimal("100.00"),
        description="Split Tx",
        category_id=None,
    )
    db_session.add_all([tx1, tx2, tx3])
    db_session.flush()

    s1 = models.TransactionSplit(
        transaction_id=tx3.transaction_id,
        category_id=cat1.category_id,
        amount=Decimal("70.00"),
    )
    s2 = models.TransactionSplit(
        transaction_id=tx3.transaction_id,
        category_id=cat2.category_id,
        amount=Decimal("30.00"),
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    # 1. Filter by category_id = cat1
    # Must match Tx1 (direct) and Tx3 (split line), but each transaction returned ONCE
    res_cat1 = transaction_access.list_transactions(
        db=db_session,
        category_id=cat1.category_id,
    )
    assert res_cat1["total"] == 2
    matched_ids = [t.transaction_id for t in res_cat1["items"]]
    assert tx1.transaction_id in matched_ids
    assert tx3.transaction_id in matched_ids
    assert tx2.transaction_id not in matched_ids

    # 2. Filter by category_id = cat2
    # Matches only Tx3
    res_cat2 = transaction_access.list_transactions(
        db=db_session,
        category_id=cat2.category_id,
    )
    assert res_cat2["total"] == 1
    assert res_cat2["items"][0].transaction_id == tx3.transaction_id

    # 3. Filter by uncategorized = True
    # MUST return only Tx2. Tx3 is split, so it is NOT uncategorized!
    res_uncat = transaction_access.list_transactions(
        db=db_session,
        uncategorized=True,
    )
    assert res_uncat["total"] == 1
    assert res_uncat["items"][0].transaction_id == tx2.transaction_id


def test_rules_exclusion_and_direct_update_guards(db_session):
    """Categorization rules and direct updates cannot mutate split transactions."""
    acc, cat1, cat2, _ = _setup_environment(db_session)

    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 1),
        amount=Decimal("100.00"),
        description="Walmart Supercenter",
        merchant="Walmart",
        category_id=None,
    )
    db_session.add(tx)
    db_session.flush()

    s1 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat1.category_id,
        amount=Decimal("60.00"),
    )
    s2 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat2.category_id,
        amount=Decimal("40.00"),
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    # 1. Rule preview count excludes split transaction
    rule_count = transaction_access.count_uncategorized_transactions_by_merchant_key(
        db=db_session,
        clean_merchant_key="walmart",
    )
    assert rule_count == 0

    # 2. Retroactive rule apply does not touch split transaction
    applied_count = transaction_access.apply_category_to_uncategorized_by_merchant_key(
        db=db_session,
        clean_merchant_key="walmart",
        category_id=cat1.category_id,
    )
    assert applied_count == 0
    db_session.refresh(tx)
    assert tx.category_id is None

    # 3. Direct amount modification on split transaction is rejected
    with pytest.raises(ValueError) as exc1:
        transaction_access.update_manual_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"amount": Decimal("120.00")},
        )
    assert "Cannot modify amount of a split transaction" in str(exc1.value)

    # 4. Direct category assignment on split transaction is rejected
    with pytest.raises(ValueError) as exc2:
        transaction_access.update_manual_transaction(
            db=db_session,
            transaction_id=tx.transaction_id,
            update_data={"category_id": cat1.category_id},
        )
    assert "Cannot directly assign a category" in str(exc2.value)

    # 5. Direct mark as transfer on split transaction is rejected
    with pytest.raises(ValueError) as exc3:
        transaction_access.mark_transactions_as_transfers(
            db=db_session,
            transaction_ids=[tx.transaction_id],
        )
    assert "Cannot mark split transactions as transfers" in str(exc3.value)


def test_transfer_candidates_exclude_splits(db_session):
    """Transfer matching pools exclude split transactions."""
    acc, cat1, cat2, _ = _setup_environment(db_session)

    tx_out = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 1),
        amount=Decimal("100.00"),
        description="Transfer Out",
    )
    db_session.add(tx_out)
    db_session.flush()

    s1 = models.TransactionSplit(
        transaction_id=tx_out.transaction_id,
        category_id=cat1.category_id,
        amount=Decimal("50.00"),
    )
    s2 = models.TransactionSplit(
        transaction_id=tx_out.transaction_id,
        category_id=cat2.category_id,
        amount=Decimal("50.00"),
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    candidates = transaction_access.get_unmatched_outflow_transactions(db_session)
    candidate_ids = [t.transaction_id for t in candidates]
    assert tx_out.transaction_id not in candidate_ids


def test_ml_suggestion_excludes_splits(db_session):
    """ML suggestion inference explicitly excludes split transactions."""
    acc, cat1, cat2, _ = _setup_environment(db_session)

    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 1),
        amount=Decimal("100.00"),
        description="Target Store",
        category_id=None,
    )
    db_session.add(tx)
    db_session.flush()

    s1 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat1.category_id,
        amount=Decimal("50.00"),
    )
    s2 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat2.category_id,
        amount=Decimal("50.00"),
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    # Single suggestion returns no suggestion for split
    res = ml_categorization_manager.predict_category_for_transaction(db_session, tx.transaction_id)
    assert res.suggested_category_id is None
    assert res.reason == "Split transactions are excluded from ML categorization"

    # Batch suggestion excludes split
    batch_res = ml_categorization_manager.batch_predict_suggestions(db_session, [tx.transaction_id])
    assert tx.transaction_id in batch_res
    assert batch_res[tx.transaction_id].suggested_category_id is None
    assert batch_res[tx.transaction_id].reason == "Split transactions are excluded from ML categorization"


def test_category_deletion_blocked_when_split_referenced(client, db_session):
    """Category deletion is blocked if referenced by any split allocation."""
    acc, cat1, cat2, _ = _setup_environment(db_session)

    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 1),
        amount=Decimal("100.00"),
        description="Grocery Trip",
    )
    db_session.add(tx)
    db_session.flush()

    s1 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat1.category_id,
        amount=Decimal("60.00"),
    )
    s2 = models.TransactionSplit(
        transaction_id=tx.transaction_id,
        category_id=cat2.category_id,
        amount=Decimal("40.00"),
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    # Attempt to delete cat1 via API
    resp = client.delete(f"/categories/{cat1.category_id}")
    assert resp.status_code == 400
    assert "referenced by split allocations" in resp.json()["detail"]


def test_split_transactions_rest_api_lifecycle(client, db_session):
    """Full REST API lifecycle: PUT splits, GET splits, validation error, and POST unsplit."""
    acc, cat1, cat2, cat3 = _setup_environment(db_session)

    tx = models.Transaction(
        account_id=acc.id,
        date=date(2026, 6, 10),
        amount=Decimal("150.00"),
        description="Costco",
        category_id=cat1.category_id,
        category_source="manual",
    )
    db_session.add(tx)
    db_session.commit()

    # 1. Invalid split: sum mismatch returns HTTP 400
    bad_resp = client.put(
        f"/transactions/{tx.transaction_id}/splits",
        json={
            "splits": [
                {"category_id": str(cat1.category_id), "amount": "100.00"},
                {"category_id": str(cat2.category_id), "amount": "49.00"},
            ]
        },
    )
    assert bad_resp.status_code == 400
    assert "must equal parent transaction amount" in bad_resp.json()["detail"]

    # 2. Valid split creation
    put_resp = client.put(
        f"/transactions/{tx.transaction_id}/splits",
        json={
            "splits": [
                {"category_id": str(cat1.category_id), "amount": "100.00"},
                {"category_id": str(cat2.category_id), "amount": "50.00"},
            ]
        },
    )
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["is_split"] is True
    assert data["split_count"] == 2
    assert data["category_id"] is None
    assert len(data["splits"]) == 2

    # 3. GET /splits endpoint
    get_resp = client.get(f"/transactions/{tx.transaction_id}/splits")
    assert get_resp.status_code == 200
    splits_data = get_resp.json()
    assert len(splits_data) == 2
    assert float(splits_data[0]["amount"]) == 100.0
    assert float(splits_data[1]["amount"]) == 50.0

    # 4. POST /unsplit endpoint with target category
    unsplit_resp = client.post(
        f"/transactions/{tx.transaction_id}/unsplit",
        json={"category_id": str(cat3.category_id)},
    )
    assert unsplit_resp.status_code == 200
    unsplit_data = unsplit_resp.json()
    assert unsplit_data["is_split"] is False
    assert unsplit_data["split_count"] == 0
    assert unsplit_data["category_id"] == str(cat3.category_id)

    # 5. Confirm splits are gone
    splits_after = client.get(f"/transactions/{tx.transaction_id}/splits").json()
    assert len(splits_after) == 0
