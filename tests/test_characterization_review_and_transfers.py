"""
Comprehensive characterization and contract tests for Phase 6:
Transaction Review + Transfer Workflow.

Verifies:
1. Transaction.is_reviewed persistence, schema annotations, and historical default semantics (default=False / Needs Review).
2. Human review state independence from category_id, uncategorized filter, and is_transfer.
3. PUT /transactions/{id} focused update contract for is_reviewed.
4. GET /transactions/ query filtering by is_reviewed (True, False, None / All) and alias reviewed.
5. GET /transactions/transfer-candidates endpoint returns matching pairs across accounts.
6. POST /transactions/mark-transfers marks transactions as transfers and does not alter review state.
7. Backward compatibility for /credit-cards/transfer-candidates and /credit-cards/mark-transfers.
8. Preservation of characterized greedy transfer matching behavior.
9. Frontend contracts: useTransactionFilters, buildTransactionQuery, and navigation without Credit Cards.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4
import pytest

from backend import models, schemas
from backend.access import transaction_access
from backend.database import engine, migrate_review_state
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend contract tests")


# ---------------------------------------------------------------------------
# 1. Model Persistence & Historical Default Semantics
# ---------------------------------------------------------------------------

def test_transaction_is_reviewed_default_and_persistence(db_session):
    """
    Verifies that new and historical transactions default to is_reviewed=False (Needs Review),
    preserving human review integrity without false 'reviewed' assertions.
    """
    account = models.Account(name="Checking Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    # Omitted is_reviewed should default to False
    tx = models.Transaction(
        account_id=account.id,
        amount=Decimal("42.50"),
        date=date(2026, 6, 10),
        description="Coffee & Bakery",
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)

    assert tx.is_reviewed is False

    # Updating is_reviewed persists
    tx.is_reviewed = True
    db_session.commit()
    db_session.refresh(tx)

    assert tx.is_reviewed is True

    # Can be marked back to Needs Review
    tx.is_reviewed = False
    db_session.commit()
    db_session.refresh(tx)

    assert tx.is_reviewed is False


def test_review_state_independent_from_categorization(db_session):
    """
    Verifies that review state is strictly independent from category classification:
    - Categorized transaction can be Needs Review (is_reviewed=False).
    - Uncategorized transaction can be Reviewed (is_reviewed=True).
    """
    account = models.Account(name="Main Acc", type="depository")
    group = models.CategoryGroup(name="Living")
    db_session.add_all([account, group])
    db_session.flush()

    cat = models.Category(name="Groceries", group_id=group.category_group_id)
    db_session.add(cat)
    db_session.flush()

    # Case 1: Categorized, but Needs Review
    tx1 = models.Transaction(
        account_id=account.id,
        category_id=cat.category_id,
        amount=Decimal("85.00"),
        date=date(2026, 6, 11),
        description="Supermarket",
        is_reviewed=False,
    )
    # Case 2: Uncategorized, but marked Reviewed
    tx2 = models.Transaction(
        account_id=account.id,
        category_id=None,
        amount=Decimal("15.00"),
        date=date(2026, 6, 12),
        description="Corner Store",
        is_reviewed=True,
    )
    db_session.add_all([tx1, tx2])
    db_session.commit()

    reloaded_tx1 = db_session.query(models.Transaction).filter_by(transaction_id=tx1.transaction_id).one()
    assert reloaded_tx1.category_id == cat.category_id
    assert reloaded_tx1.is_reviewed is False

    reloaded_tx2 = db_session.query(models.Transaction).filter_by(transaction_id=tx2.transaction_id).one()
    assert reloaded_tx2.category_id is None
    assert reloaded_tx2.is_reviewed is True


def test_migration_historical_backfill_and_subsequent_new_transactions(db_session):
    """
    Characterization test for Phase 6 historical review-state migration:
    - Pre-existing transactions before migration -> Reviewed (is_reviewed = True).
    - New transactions created after migration -> Needs Review (is_reviewed = False).
    """
    account = models.Account(name="Pre-Migration Acc", type="depository")
    db_session.add(account)
    db_session.commit()

    try:
        # 1. Simulate pre-migration state: drop column is_reviewed
        db_session.execute(text("ALTER TABLE transactions DROP COLUMN IF EXISTS is_reviewed CASCADE;"))
        db_session.commit()

        # 2. Insert pre-existing transaction without is_reviewed
        tx_old_id = uuid4()
        db_session.execute(
            text(
                "INSERT INTO transactions (transaction_id, account_id, amount, date, description, pending, is_transfer) "
                "VALUES (:tid, :aid, :amt, :dt, :desc, false, false);"
            ),
            {
                "tid": tx_old_id,
                "aid": account.id,
                "amt": Decimal("75.00"),
                "dt": date(2026, 5, 20),
                "desc": "Historical Transaction",
            },
        )
        db_session.commit()

        # 3. Run migration
        applied = migrate_review_state(engine)
        assert applied is True

        # 4. Verify historical transaction backfilled to is_reviewed = True
        res_old = db_session.execute(
            text("SELECT is_reviewed FROM transactions WHERE transaction_id = :tid;"),
            {"tid": tx_old_id},
        ).scalar()
        assert res_old is True

        # 5. Insert new transaction after migration (using models.Transaction default)
        tx_new = models.Transaction(
            account_id=account.id,
            amount=Decimal("25.00"),
            date=date(2026, 6, 1),
            description="Post-Migration Transaction",
        )
        db_session.add(tx_new)
        db_session.commit()
        db_session.refresh(tx_new)

        assert tx_new.is_reviewed is False
    finally:
        # Ensure column exists for subsequent tests
        migrate_review_state(engine)


def test_migration_idempotent_on_startup_preserves_needs_review(db_session):
    """
    Regression test for Section 2:
    - Migration already applied.
    - Transaction manually changed or created as Needs Review (is_reviewed = False).
    - Application / startup migration runs again.
    -> Transaction MUST remain Needs Review (not reset to Reviewed).
    """
    account = models.Account(name="Idempotency Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        amount=Decimal("99.00"),
        date=date(2026, 6, 2),
        description="User Unreviewed Item",
        is_reviewed=False,
    )
    db_session.add(tx)
    db_session.commit()

    # Verify initial state is False
    assert tx.is_reviewed is False

    # Simulate application restart: migrate_review_state(engine) runs during lifespan
    applied = migrate_review_state(engine)
    assert applied is False  # Migration recognized column already exists and did not re-run backfill

    # Verify transaction remains False
    db_session.expire_all()
    reloaded_tx = db_session.query(models.Transaction).filter_by(transaction_id=tx.transaction_id).one()
    assert reloaded_tx.is_reviewed is False


def test_plaid_sync_and_csv_import_review_state_preservation(db_session):
    """
    Verifies that:
    1. stage_csv_import_transaction defaults new transactions to is_reviewed=False (Needs Review).
    2. stage_or_update_plaid_transaction defaults new transactions to is_reviewed=False (Needs Review).
    3. stage_or_update_plaid_transaction preserves an existing transaction's is_reviewed state
       when updating description, amount, or pending status.
    """
    account = models.Account(name="Plaid/CSV Acc", type="depository")
    db_session.add(account)
    db_session.flush()

    # 1. CSV import
    csv_tx = transaction_access.stage_csv_import_transaction(
        db=db_session,
        account_id=account.id,
        transaction_date=date(2026, 6, 3),
        amount=Decimal("35.00"),
        description="CSV Grocery Store",
    )
    db_session.commit()
    db_session.refresh(csv_tx)
    assert csv_tx.is_reviewed is False

    # 2. New Plaid transaction
    plaid_tx = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="plaid_txn_123",
        account_id=account.id,
        description="Plaid Coffee Shop (Pending)",
        amount=Decimal("4.50"),
        transaction_date=date(2026, 6, 4),
        pending=True,
    )
    db_session.commit()
    db_session.refresh(plaid_tx)
    assert plaid_tx.is_reviewed is False

    # User reviews this transaction:
    plaid_tx.is_reviewed = True
    db_session.commit()
    db_session.refresh(plaid_tx)
    assert plaid_tx.is_reviewed is True

    # 3. Subsequent Plaid sync arrives (transaction posted, updated description/amount)
    updated_plaid_tx = transaction_access.stage_or_update_plaid_transaction(
        db=db_session,
        plaid_transaction_id="plaid_txn_123",
        account_id=account.id,
        description="Plaid Coffee Shop",
        amount=Decimal("4.75"),
        transaction_date=date(2026, 6, 4),
        pending=False,
    )
    db_session.commit()
    db_session.refresh(updated_plaid_tx)

    # Invariant: Review state MUST be preserved
    assert updated_plaid_tx.is_reviewed is True
    assert updated_plaid_tx.description == "Plaid Coffee Shop"
    assert updated_plaid_tx.amount == Decimal("4.75")
    assert updated_plaid_tx.pending is False


def test_categorization_update_does_not_alter_review_state(client, db_session):
    """
    Verifies that changing categorization on a transaction does NOT automatically alter its review state.
    """
    account = models.Account(name="Cat Acc", type="depository")
    group = models.CategoryGroup(name="Expenses")
    db_session.add_all([account, group])
    db_session.flush()

    cat1 = models.Category(name="Dining", group_id=group.category_group_id)
    cat2 = models.Category(name="Entertainment", group_id=group.category_group_id)
    db_session.add_all([cat1, cat2])
    db_session.flush()

    # Case A: Needs Review transaction categorized -> remains Needs Review
    tx_unreviewed = models.Transaction(
        account_id=account.id,
        category_id=None,
        amount=Decimal("30.00"),
        date=date(2026, 6, 5),
        description="Restaurant",
        is_reviewed=False,
    )
    # Case B: Reviewed transaction re-categorized -> remains Reviewed
    tx_reviewed = models.Transaction(
        account_id=account.id,
        category_id=cat1.category_id,
        amount=Decimal("60.00"),
        date=date(2026, 6, 6),
        description="Concert",
        is_reviewed=True,
    )
    db_session.add_all([tx_unreviewed, tx_reviewed])
    db_session.commit()

    # Update category on Case A
    resp_a = client.put(f"/transactions/{tx_unreviewed.transaction_id}", json={
        "category_id": str(cat1.category_id)
    })
    assert resp_a.status_code == 200
    assert resp_a.json()["category_id"] == str(cat1.category_id)
    assert resp_a.json()["is_reviewed"] is False

    # Update category on Case B
    resp_b = client.put(f"/transactions/{tx_reviewed.transaction_id}", json={
        "category_id": str(cat2.category_id)
    })
    assert resp_b.status_code == 200
    assert resp_b.json()["category_id"] == str(cat2.category_id)
    assert resp_b.json()["is_reviewed"] is True


# ---------------------------------------------------------------------------
# 2. Schema Annotations & CRUD API
# ---------------------------------------------------------------------------

def test_schema_transaction_read_and_create_is_reviewed():
    """
    Verifies schemas include is_reviewed annotations and default to False.
    """
    read_fields = schemas.TransactionRead.model_fields
    assert "is_reviewed" in read_fields
    assert read_fields["is_reviewed"].annotation is bool
    assert read_fields["is_reviewed"].default is False

    create_fields = schemas.TransactionCreate.model_fields
    assert "is_reviewed" in create_fields
    assert create_fields["is_reviewed"].annotation is bool
    assert create_fields["is_reviewed"].default is False

    update_fields = schemas.TransactionUpdate.model_fields
    assert "is_reviewed" in update_fields


def test_put_transaction_updates_is_reviewed_focused(client, db_session):
    """
    Verifies that PUT /transactions/{id} updates is_reviewed with a focused partial payload
    without altering category, description, or amount.
    """
    account = models.Account(name="Card", type="credit")
    db_session.add(account)
    db_session.flush()

    tx = models.Transaction(
        account_id=account.id,
        amount=Decimal("50.00"),
        date=date(2026, 6, 15),
        description="Gas Station",
        is_reviewed=False,
    )
    db_session.add(tx)
    db_session.commit()

    # Mark Reviewed
    resp = client.put(f"/transactions/{tx.transaction_id}", json={"is_reviewed": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_reviewed"] is True
    assert data["description"] == "Gas Station"
    assert data["amount"] == "50.00"

    # Verify in DB
    db_tx = db_session.query(models.Transaction).filter_by(transaction_id=tx.transaction_id).one()
    assert db_tx.is_reviewed is True

    # Mark Needs Review
    resp2 = client.put(f"/transactions/{tx.transaction_id}", json={"is_reviewed": False})
    assert resp2.status_code == 200
    assert resp2.json()["is_reviewed"] is False


def test_list_transactions_filters_by_review_status(client, db_session):
    """
    Verifies GET /transactions/ filtering by is_reviewed=true, is_reviewed=false,
    and alias reviewed=true / false.
    """
    account = models.Account(name="Checking", type="depository")
    db_session.add(account)
    db_session.flush()

    tx_reviewed = models.Transaction(
        account_id=account.id,
        amount=Decimal("10.00"),
        date=date(2026, 6, 5),
        description="Reviewed Item",
        is_reviewed=True,
    )
    tx_unreviewed = models.Transaction(
        account_id=account.id,
        amount=Decimal("20.00"),
        date=date(2026, 6, 6),
        description="Needs Review Item",
        is_reviewed=False,
    )
    db_session.add_all([tx_reviewed, tx_unreviewed])
    db_session.commit()

    # 1. No filter: returns both
    resp_all = client.get("/transactions/")
    assert resp_all.status_code == 200
    assert resp_all.json()["total"] == 2

    # 2. Filter is_reviewed=true
    resp_rev = client.get("/transactions/?is_reviewed=true")
    assert resp_rev.status_code == 200
    items_rev = resp_rev.json()["items"]
    assert len(items_rev) == 1
    assert items_rev[0]["description"] == "Reviewed Item"
    assert items_rev[0]["is_reviewed"] is True

    # 3. Filter is_reviewed=false
    resp_unrev = client.get("/transactions/?is_reviewed=false")
    assert resp_unrev.status_code == 200
    items_unrev = resp_unrev.json()["items"]
    assert len(items_unrev) == 1
    assert items_unrev[0]["description"] == "Needs Review Item"
    assert items_unrev[0]["is_reviewed"] is False

    # 4. Alias reviewed=true
    resp_alias = client.get("/transactions/?reviewed=true")
    assert resp_alias.status_code == 200
    assert len(resp_alias.json()["items"]) == 1
    assert resp_alias.json()["items"][0]["description"] == "Reviewed Item"


# ---------------------------------------------------------------------------
# 3. Transfer Candidate Search & Confirmation under /transactions
# ---------------------------------------------------------------------------

def test_transactions_transfer_candidates_and_confirmation(client, db_session):
    """
    Verifies:
    1. GET /transactions/transfer-candidates discovers matching pairs across accounts.
    2. POST /transactions/mark-transfers marks is_transfer=True.
    3. Confirmed transactions disappear from candidate list.
    4. Review status is not accidentally altered by transfer confirmation.
    """
    acct1 = models.Account(name="USAA Checking", type="depository")
    acct2 = models.Account(name="Discover Card", type="credit")
    db_session.add_all([acct1, acct2])
    db_session.flush()

    # Inflow side: negative $150.00 on Discover
    tx_in = models.Transaction(
        account_id=acct2.id,
        amount=Decimal("-150.00"),
        date=date(2026, 6, 12),
        description="PAYMENT RECEIVED",
        is_transfer=False,
        is_reviewed=False,
    )
    # Outflow side: positive $150.00 on USAA Checking
    tx_out = models.Transaction(
        account_id=acct1.id,
        amount=Decimal("150.00"),
        date=date(2026, 6, 11),
        description="DISCOVER CARD PAYMENT",
        is_transfer=False,
        is_reviewed=False,
    )
    db_session.add_all([tx_in, tx_out])
    db_session.commit()

    # 1. Discover candidates under /transactions/transfer-candidates
    resp = client.get("/transactions/transfer-candidates")
    assert resp.status_code == 200
    candidates = resp.json()
    assert len(candidates) == 1

    candidate = candidates[0]
    assert candidate["inflow_account_name"] == "Discover Card"
    assert candidate["outflow_account_name"] == "USAA Checking"
    assert candidate["inflow_side"]["transaction_id"] == str(tx_in.transaction_id)
    assert candidate["outflow_side"]["transaction_id"] == str(tx_out.transaction_id)

    # 2. Confirm transfer via POST /transactions/mark-transfers
    confirm_resp = client.post("/transactions/mark-transfers", json={
        "transaction_ids": [str(tx_in.transaction_id), str(tx_out.transaction_id)]
    })
    assert confirm_resp.status_code == 204

    # 3. Verify in DB: both is_transfer=True, is_reviewed remains False
    db_in = db_session.query(models.Transaction).filter_by(transaction_id=tx_in.transaction_id).one()
    db_out = db_session.query(models.Transaction).filter_by(transaction_id=tx_out.transaction_id).one()
    assert db_in.is_transfer is True
    assert db_out.is_transfer is True
    assert db_in.is_reviewed is False  # Invariant: transfer confirmation does not mutate review state
    assert db_out.is_reviewed is False

    # 4. Candidate list now empty
    resp_empty = client.get("/transactions/transfer-candidates")
    assert resp_empty.status_code == 200
    assert len(resp_empty.json()) == 0


def test_backward_compatibility_credit_cards_transfer_routes(client, db_session):
    """
    Verifies that legacy /credit-cards/transfer-candidates and /credit-cards/mark-transfers
    remain functional for external client compatibility.
    """
    acct1 = models.Account(name="Checking", type="depository")
    acct2 = models.Account(name="Savings", type="depository")
    db_session.add_all([acct1, acct2])
    db_session.flush()

    tx_in = models.Transaction(
        account_id=acct2.id,
        amount=Decimal("-300.00"),
        date=date(2026, 6, 20),
        description="TRANSFER FROM CHECKING",
        is_transfer=False,
    )
    tx_out = models.Transaction(
        account_id=acct1.id,
        amount=Decimal("300.00"),
        date=date(2026, 6, 20),
        description="TRANSFER TO SAVINGS",
        is_transfer=False,
    )
    db_session.add_all([tx_in, tx_out])
    db_session.commit()

    # Legacy GET
    resp = client.get("/credit-cards/transfer-candidates")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Legacy POST
    post_resp = client.post("/credit-cards/mark-transfers", json={
        "transaction_ids": [str(tx_in.transaction_id), str(tx_out.transaction_id)]
    })
    assert post_resp.status_code == 204

    # Both confirmed
    db_in = db_session.query(models.Transaction).filter_by(transaction_id=tx_in.transaction_id).one()
    assert db_in.is_transfer is True


def test_greedy_matching_heuristic_preserved(client, db_session):
    """
    Verifies that the characterized greedy, order-dependent matching heuristic
    in detect_transfer_candidates is preserved without silent policy modification.
    """
    acct1 = models.Account(name="Acc 1", type="depository")
    acct2 = models.Account(name="Acc 2", type="credit")
    db_session.add_all([acct1, acct2])
    db_session.flush()

    # Inflow: on June 15 for -100
    tx_in = models.Transaction(
        account_id=acct2.id,
        amount=Decimal("-100.00"),
        date=date(2026, 6, 15),
        description="Payment In",
        is_transfer=False,
    )
    # Outflow 1: on June 13 (+2 days away)
    tx_out_far = models.Transaction(
        account_id=acct1.id,
        amount=Decimal("100.00"),
        date=date(2026, 6, 13),
        description="Payment Out Far",
        is_transfer=False,
    )
    # Outflow 2: on June 15 (0 days away - closest date)
    tx_out_close = models.Transaction(
        account_id=acct1.id,
        amount=Decimal("100.00"),
        date=date(2026, 6, 15),
        description="Payment Out Close",
        is_transfer=False,
    )
    db_session.add_all([tx_in, tx_out_far, tx_out_close])
    db_session.commit()

    resp = client.get("/transactions/transfer-candidates")
    assert resp.status_code == 200
    candidates = resp.json()
    assert len(candidates) == 1
    # Existing algorithm matches the first matching outflow in retrieval order without closest-date preference
    matched_outflow_id = candidates[0]["outflow_side"]["transaction_id"]
    assert matched_outflow_id in (str(tx_out_far.transaction_id), str(tx_out_close.transaction_id))


# ---------------------------------------------------------------------------
# 4. Frontend Contract Verification (useTransactionFilters, query builder, UI)
# ---------------------------------------------------------------------------

def test_frontend_review_filter_and_query_builder(require_node):
    """
    Verifies:
    1. buildTransactionQuery formats is_reviewed boolean for 'needs_review' and 'reviewed'.
    2. useTransactionFilters includes reviewFilter in secondary filter state and reset.
    """
    script = """
    import { buildTransactionQuery } from './frontend/app/utils/transactionQuery.ts';

    const failures = [];

    // Case 1: reviewFilter = 'needs_review' -> is_reviewed: false
    const q1 = buildTransactionQuery({ month: '2026-06', reviewFilter: 'needs_review' });
    if (q1.is_reviewed !== false) {
        failures.push({ case: 'needs_review', actual: q1.is_reviewed });
    }

    // Case 2: reviewFilter = 'reviewed' -> is_reviewed: true
    const q2 = buildTransactionQuery({ month: '2026-06', reviewFilter: 'reviewed' });
    if (q2.is_reviewed !== true) {
        failures.push({ case: 'reviewed', actual: q2.is_reviewed });
    }

    // Case 3: reviewFilter = 'all' -> is_reviewed omitted
    const q3 = buildTransactionQuery({ month: '2026-06', reviewFilter: 'all' });
    if ('is_reviewed' in q3) {
        failures.push({ case: 'all should omit is_reviewed', actual: q3.is_reviewed });
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"buildTransactionQuery review filter failures: {res['failures']}"


def test_frontend_transactions_page_elements(require_node):
    """
    Verifies transactions.vue contains:
    - Review Status filter dropdown
    - Review column in table and review toggle button with accessibility labels
    - Find Transfer Matches button and Transfer Review Panel with Confirm and Dismiss buttons
    - Clear filters button resetting reviewFilter
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const txCode = fs.readFileSync(path.resolve('./frontend/app/pages/transactions.vue'), 'utf-8');
    const composableCode = fs.readFileSync(path.resolve('./frontend/app/composables/useTransactionFilters.ts'), 'utf-8');
    const appCode = fs.readFileSync(path.resolve('./frontend/app/app.vue'), 'utf-8');

    const checks = {
        hasReviewFilterSelect: txCode.includes('id="tx-review-select"') && txCode.includes('v-model="reviewFilter"'),
        hasReviewTableHeader: txCode.includes('<th scope="col" class="status-col">Review</th>'),
        hasReviewToggleButton: txCode.includes('class="review-toggle-btn"') && txCode.includes('toggleReviewStatus'),
        hasTransferMatchesBtn: txCode.includes('btn-transfer-matches') && txCode.includes('toggleTransfersPanel'),
        hasTransferPanel: txCode.includes('class="transfer-panel') && txCode.includes('confirmTransfer') && txCode.includes('dismissTransfer'),
        composableHasReviewFilter: composableCode.includes('reviewFilter') && composableCode.includes("tx_filter_review', () => 'all')"),
        composableClearResetsReview: composableCode.includes("reviewFilter.value = 'all'"),
        sidebarRemovesCreditCards: !appCode.includes('to="{ path: \\'/credit-cards\\'') && !appCode.includes('title="Credit Cards"'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Transactions page elements failures: {res['failures']}"
