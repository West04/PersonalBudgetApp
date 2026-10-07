from decimal import Decimal
from datetime import date
from uuid import uuid4
import pytest

from backend import models
from backend.access import categorization_rule_access, transaction_access
from backend.managers import csv_import_manager, plaid_transaction_sync_manager, categorization_rule_manager
from backend.bank_statement_loader import USAALoader


def _create_account_and_categories(db_session):
    acc = models.Account(name="Checking", type="depository")
    group = models.CategoryGroup(name="General")
    db_session.add_all([acc, group])
    db_session.flush()

    cat_dining = models.Category(name="Dining", group_id=group.category_group_id, type="expense")
    cat_shopping = models.Category(name="Shopping", group_id=group.category_group_id, type="expense")
    cat_coffee = models.Category(name="Coffee", group_id=group.category_group_id, type="expense")
    db_session.add_all([cat_dining, cat_shopping, cat_coffee])
    db_session.commit()
    return acc, cat_dining, cat_shopping, cat_coffee


def test_rule_application_manual_creation_and_protection(db_session):
    """
    Test Section 53, 54, 55, 59:
    - Manual transaction without category + matching rule -> auto-categorized.
    - Manual transaction with explicit category + matching rule -> explicit category preserved.
    - is_reviewed remains False.
    """
    acc, cat_dining, cat_shopping, _ = _create_account_and_categories(db_session)

    # Create rule: Starbucks -> Dining
    categorization_rule_access.create_rule(db_session, "Starbucks", cat_dining.category_id)

    # 1. Manual creation without category
    t1 = transaction_access.create_manual_transaction(
        db=db_session,
        account_id=acc.id,
        category_id=None,
        description="STARBUCKS #1042",
        amount=Decimal("6.50"),
        transaction_date=date(2026, 7, 1),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    assert t1.merchant == "Starbucks"
    assert t1.category_id == cat_dining.category_id
    assert t1.is_reviewed is False  # Review independence!
    assert t1.is_merchant_overridden is False

    # 2. Manual creation with explicit category
    t2 = transaction_access.create_manual_transaction(
        db=db_session,
        account_id=acc.id,
        category_id=cat_shopping.category_id,
        description="STARBUCKS #1042",
        amount=Decimal("12.00"),
        transaction_date=date(2026, 7, 2),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    assert t2.merchant == "Starbucks"
    assert t2.category_id == cat_shopping.category_id  # Explicit category preserved!
    assert t2.is_reviewed is False


def test_rule_application_manual_merchant_override(db_session):
    """
    Test Section 56:
    Merchant manually overridden -> matching rule uses resulting merchant -> is_merchant_overridden remains True.
    """
    acc, cat_dining, _, _ = _create_account_and_categories(db_session)

    categorization_rule_access.create_rule(db_session, "Starbucks", cat_dining.category_id)

    # Create transaction with weird description but manual merchant override to "Starbucks"
    t = transaction_access.create_manual_transaction(
        db=db_session,
        account_id=acc.id,
        category_id=None,
        description="SQ *COFFEE VENDOR NYC",
        merchant="Starbucks",
        amount=Decimal("5.00"),
        transaction_date=date(2026, 7, 3),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    assert t.merchant == "Starbucks"
    assert t.is_merchant_overridden is True
    assert t.category_id == cat_dining.category_id  # Matched from overridden merchant!


def test_rule_application_csv_import(db_session):
    """
    Test Section 53, 58:
    CSV import preserves description, normalizes merchant, applies matching rule,
    preserves deduplication semantics.
    """
    acc, cat_dining, _, _ = _create_account_and_categories(db_session)

    categorization_rule_access.create_rule(db_session, "Starbucks", cat_dining.category_id)

    # USAA CSV format: Date,Description,Original Description,Category,Amount,Status
    # Outflow is negative in USAA CSV; loader inverts to positive outflow
    csv_content = (
        b"Date,Description,Original Description,Category,Amount,Status\n"
        b"2026-07-10,STARBUCKS #1105,STARBUCKS #1105 RAW,, -4.75,Posted\n"
        b"2026-07-11,UNKNOWN BOOKSTORE,UNKNOWN BOOKSTORE RAW,, -25.00,Posted\n"
    )

    loader = USAALoader(account_id=acc.id)
    summary = csv_import_manager.confirm_csv_import(db_session, csv_content, loader)

    assert summary.imported == 2
    assert summary.skipped == 0
    assert len(summary.errors) == 0

    txs = db_session.query(models.Transaction).filter_by(account_id=acc.id).order_by(models.Transaction.date).all()
    assert len(txs) == 2

    # First transaction matched Starbucks rule
    assert txs[0].description == "STARBUCKS #1105"
    assert txs[0].merchant == "Starbucks"
    assert txs[0].category_id == cat_dining.category_id
    assert txs[0].is_reviewed is False

    # Second transaction has no matching rule
    assert txs[1].description == "UNKNOWN BOOKSTORE"
    assert txs[1].merchant == "Unknown Bookstore"
    assert txs[1].category_id is None
    assert txs[1].is_reviewed is False

    # Re-importing same CSV deduplicates properly
    summary2 = csv_import_manager.confirm_csv_import(db_session, csv_content, loader)
    assert summary2.imported == 0
    assert summary2.skipped == 2


def test_csv_import_categorization_equivalence(db_session):
    """
    Characterization test verifying CSV import categorization rules behavior:
    1. Uncategorized row matching rule gets assigned category with category_source='rule'.
    2. Casing/whitespace differences in merchant match rule deterministically.
    3. Row with existing category preserves it with category_source='legacy'.
    4. Row without matching rule remains uncategorized with category_id=None, category_source=None.
    5. Directly verifies equivalence between inline logic and domain.categorization_rules.match_merchant_rule.
    """
    from backend.domain.categorization_rules import match_merchant_rule
    from backend.domain.merchant_normalization import normalize_merchant

    acc, cat_dining, cat_shopping, cat_coffee = _create_account_and_categories(db_session)

    categorization_rule_access.create_rule(db_session, "Starbucks", cat_coffee.category_id)
    categorization_rule_access.create_rule(db_session, "Trader Joe's", cat_dining.category_id)

    rules_lookup = categorization_rule_access.get_rules_lookup_dict(db_session)

    # 1. Verify match_merchant_rule returns expected values for test payees
    assert match_merchant_rule("Starbucks", rules_lookup) == cat_coffee.category_id
    assert match_merchant_rule("  starbucks  ", rules_lookup) == cat_coffee.category_id
    assert match_merchant_rule("Trader Joe's", rules_lookup) == cat_dining.category_id
    assert match_merchant_rule("Unknown Store", rules_lookup) is None
    assert match_merchant_rule(None, rules_lookup) is None
    assert match_merchant_rule("", rules_lookup) is None

    # 2. Run through CSV import confirmation
    csv_content = (
        b"Date,Description,Original Description,Category,Amount,Status\n"
        b"2026-07-10,STARBUCKS #1105,RAW,, -4.75,Posted\n"
        b"2026-07-11,TRADER JOE'S #42,RAW,, -45.00,Posted\n"
        b"2026-07-12,RANDOM BOOKSHOP,RAW,, -15.00,Posted\n"
    )

    loader = USAALoader(account_id=acc.id)
    summary = csv_import_manager.confirm_csv_import(db_session, csv_content, loader)
    assert summary.imported == 3
    assert summary.skipped == 0
    assert len(summary.errors) == 0

    txs = db_session.query(models.Transaction).filter_by(account_id=acc.id).order_by(models.Transaction.date).all()
    assert len(txs) == 3

    # Row 1: Starbucks -> Coffee
    assert txs[0].merchant == "Starbucks"
    assert txs[0].category_id == cat_coffee.category_id
    assert txs[0].category_source == "rule"

    # Row 2: Trader Joe's -> Dining
    assert txs[0].merchant == "Starbucks"
    assert txs[1].merchant == "Trader Joe's"
    assert txs[1].category_id == cat_dining.category_id
    assert txs[1].category_source == "rule"

    # Row 3: Random Bookshop -> None
    assert txs[2].merchant == "Random Bookshop"
    assert txs[2].category_id is None
    assert txs[2].category_source is None

    # 3. Test loader with pre-assigned category_id: preserves it with category_source='legacy'
    from unittest.mock import MagicMock
    from backend.bank_statement_loader import BankStatementLoader, ParsedStatement
    from backend.schemas import TransactionCreate

    mock_loader = MagicMock(spec=BankStatementLoader)
    mock_loader.account_id = acc.id
    mock_loader.load_records_tolerant.return_value = ParsedStatement(
        valid_transactions=(
            TransactionCreate(
                account_id=acc.id,
                date=date(2026, 7, 13),
                amount=Decimal("50.00"),
                description="STARBUCKS GIFT SHOP",
                category_id=cat_shopping.category_id,
            ),
        ),
        row_errors=(),
    )
    summary_legacy = csv_import_manager.confirm_csv_import(db_session, b"dummy", mock_loader)
    assert summary_legacy.imported == 1
    tx_legacy = db_session.query(models.Transaction).filter_by(description="STARBUCKS GIFT SHOP").one()
    assert tx_legacy.category_id == cat_shopping.category_id
    assert tx_legacy.category_source == "legacy"


def test_rule_application_plaid_sync_and_protection(db_session):
    """
    Test Section 54, 57:
    - New Plaid transaction matching rule -> auto-categorized.
    - Subsequent Plaid update with existing non-null category -> category preserved.
    - Existing uncategorized Plaid transaction whose merchant updates to match a rule -> auto-categorized.
    """
    acc, cat_dining, cat_shopping, _ = _create_account_and_categories(db_session)
    acc.plaid_account_id = "plaid_acc_123"
    db_session.add(acc)
    db_session.commit()

    categorization_rule_access.create_rule(db_session, "Starbucks", cat_dining.category_id)

    # 1. New Plaid transaction matching rule
    plaid_data_1 = {
        "account_id": "plaid_acc_123",
        "transaction_id": "plaid_tx_001",
        "date": "2026-07-15",
        "datetime": None,
        "amount": 5.25,  # Plaid positive = debit/outflow
        "name": "STARBUCKS #9999",
        "merchant_name": "Starbucks",
        "pending": False,
    }
    rules_lookup = categorization_rule_access.get_rules_lookup_dict(db_session)
    plaid_transaction_sync_manager._process_upsert_event(db_session, plaid_data_1, rules_lookup=rules_lookup)

    tx1 = db_session.query(models.Transaction).filter_by(plaid_transaction_id="plaid_tx_001").one()
    assert tx1.category_id == cat_dining.category_id

    # 2. User manually changes category to Shopping
    tx1.category_id = cat_shopping.category_id
    db_session.commit()

    # 3. Plaid update event comes in (e.g. pending cleared or name updated)
    plaid_data_1_updated = dict(plaid_data_1)
    plaid_data_1_updated["amount"] = 5.50
    plaid_transaction_sync_manager._process_upsert_event(db_session, plaid_data_1_updated, rules_lookup=rules_lookup)

    db_session.refresh(tx1)
    assert tx1.amount == Decimal("-5.50")
    assert tx1.category_id == cat_shopping.category_id  # Preserved! Never overwritten!

    # 4. Existing uncategorized Plaid transaction with merchant update
    plaid_data_2 = {
        "account_id": "plaid_acc_123",
        "transaction_id": "plaid_tx_002",
        "date": "2026-07-16",
        "datetime": None,
        "amount": 7.00,
        "name": "PENDING PURCHASE",
        "merchant_name": None,
        "pending": True,
    }
    plaid_transaction_sync_manager._process_upsert_event(db_session, plaid_data_2, rules_lookup=rules_lookup)
    tx2 = db_session.query(models.Transaction).filter_by(plaid_transaction_id="plaid_tx_002").one()
    assert tx2.category_id is None

    # Later posted event arrives with merchant "Starbucks"
    plaid_data_2_posted = {
        "account_id": "plaid_acc_123",
        "transaction_id": "plaid_tx_002",
        "date": "2026-07-17",
        "datetime": None,
        "amount": 7.00,
        "name": "STARBUCKS #1000",
        "merchant_name": "Starbucks",
        "pending": False,
    }
    plaid_transaction_sync_manager._process_upsert_event(db_session, plaid_data_2_posted, rules_lookup=rules_lookup)
    db_session.refresh(tx2)
    assert tx2.category_id == cat_dining.category_id  # Now categorized since it was previously None


def test_rule_edit_and_delete_effects(db_session):
    """
    Test Section 60:
    - Edit rule -> future matching behavior changes, historical categorized transactions unchanged.
    - Delete rule -> future transactions not categorized, historical categorized transactions unchanged.
    """
    acc, cat_dining, _, cat_coffee = _create_account_and_categories(db_session)

    rule = categorization_rule_access.create_rule(db_session, "Starbucks", cat_dining.category_id)

    # Transaction 1 categorized with Dining
    t1 = transaction_access.create_manual_transaction(
        db=db_session,
        account_id=acc.id,
        category_id=None,
        description="STARBUCKS #1042",
        amount=Decimal("4.00"),
        transaction_date=date(2026, 7, 20),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    assert t1.category_id == cat_dining.category_id

    # Edit rule: Starbucks -> Coffee
    categorization_rule_access.update_rule(db_session, rule.id, category_id=cat_coffee.category_id)

    # Historical t1 is UNCHANGED
    db_session.refresh(t1)
    assert t1.category_id == cat_dining.category_id

    # New transaction receives Coffee
    t2 = transaction_access.create_manual_transaction(
        db=db_session,
        account_id=acc.id,
        category_id=None,
        description="STARBUCKS #1042",
        amount=Decimal("4.50"),
        transaction_date=date(2026, 7, 21),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    assert t2.category_id == cat_coffee.category_id

    # Delete rule
    categorization_rule_access.delete_rule(db_session, rule.id)

    # Historical t1 and t2 remain unchanged
    db_session.refresh(t1)
    db_session.refresh(t2)
    assert t1.category_id == cat_dining.category_id
    assert t2.category_id == cat_coffee.category_id

    # Future transaction receives None
    t3 = transaction_access.create_manual_transaction(
        db=db_session,
        account_id=acc.id,
        category_id=None,
        description="STARBUCKS #1042",
        amount=Decimal("5.00"),
        transaction_date=date(2026, 7, 22),
        transaction_datetime=None,
        pending=False,
        plaid_transaction_id=None,
    )
    assert t3.category_id is None


def test_duplicate_merchant_rule_refusal(db_session):
    """
    Test Section 61:
    Attempt two logically identical merchant rules differing only by casing/whitespace.
    Verify system refuses ambiguous duplicates.
    """
    acc, cat_dining, _, _ = _create_account_and_categories(db_session)

    categorization_rule_access.create_rule(db_session, "Whole Foods", cat_dining.category_id)

    with pytest.raises(ValueError, match="already exists"):
        categorization_rule_access.create_rule(db_session, "  WHOLE   FOODS  ", cat_dining.category_id)


def test_historical_batch_apply(db_session):
    """
    Test Section 62:
    Matching uncategorized transactions updated.
    Matching already-categorized transactions untouched.
    Returns affected count.
    """
    acc, cat_dining, cat_shopping, _ = _create_account_and_categories(db_session)

    # Create transactions before rule exists
    t_uncat_1 = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #1",
        merchant="Starbucks",
        amount=Decimal("5.00"),
        date=date(2026, 7, 1),
        category_id=None,
    )
    t_uncat_2 = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #2",
        merchant="Starbucks",
        amount=Decimal("6.00"),
        date=date(2026, 7, 2),
        category_id=None,
    )
    t_already_cat = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #3",
        merchant="Starbucks",
        amount=Decimal("15.00"),
        date=date(2026, 7, 3),
        category_id=cat_shopping.category_id,
    )
    t_diff_merchant = models.Transaction(
        account_id=acc.id,
        description="TARGET #1",
        merchant="Target",
        amount=Decimal("45.00"),
        date=date(2026, 7, 4),
        category_id=None,
    )
    db_session.add_all([t_uncat_1, t_uncat_2, t_already_cat, t_diff_merchant])
    db_session.commit()

    rule = categorization_rule_access.create_rule(db_session, "Starbucks", cat_dining.category_id)

    # Preview
    preview_count = categorization_rule_manager.preview_rule_matches(db_session, rule.id)
    assert preview_count == 2

    # Batch apply
    applied_count = categorization_rule_manager.apply_rule_to_uncategorized(db_session, rule.id)
    assert applied_count == 2

    db_session.refresh(t_uncat_1)
    db_session.refresh(t_uncat_2)
    db_session.refresh(t_already_cat)
    db_session.refresh(t_diff_merchant)

    assert t_uncat_1.category_id == cat_dining.category_id
    assert t_uncat_2.category_id == cat_dining.category_id
    assert t_already_cat.category_id == cat_shopping.category_id  # Untouched!
    assert t_diff_merchant.category_id is None  # Untouched!


def test_batch_apply_rollback_regression(db_session, monkeypatch):
    """
    Audit 2: Retroactive batch transaction ownership and rollback.
    Multiple eligible transactions -> updates flushed by accessor
    -> simulated failure before workflow completion -> rollback
    -> every transaction remains uncategorized.
    """
    acc, cat_dining, cat_shopping, _ = _create_account_and_categories(db_session)

    t1 = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #1",
        merchant="Starbucks",
        amount=Decimal("4.50"),
        date=date(2026, 7, 10),
        category_id=None,
    )
    t2 = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #2",
        merchant="Starbucks",
        amount=Decimal("5.50"),
        date=date(2026, 7, 11),
        category_id=None,
    )
    t_already = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #3",
        merchant="Starbucks",
        amount=Decimal("12.00"),
        date=date(2026, 7, 12),
        category_id=cat_shopping.category_id,
    )
    db_session.add_all([t1, t2, t_already])
    db_session.commit()

    rule = categorization_rule_access.create_rule(db_session, "Starbucks", cat_dining.category_id)

    # Monkeypatch db_session.commit to simulate failure before workflow completion
    def mock_commit():
        raise RuntimeError("Simulated DB failure during batch commit")

    monkeypatch.setattr(db_session, "commit", mock_commit)

    with pytest.raises(RuntimeError, match="Simulated DB failure during batch commit"):
        categorization_rule_manager.apply_rule_to_uncategorized(db_session, rule.id)

    # Restore commit and inspect transactions in DB
    monkeypatch.undo()
    db_session.expire_all()

    fresh_t1 = db_session.query(models.Transaction).filter_by(transaction_id=t1.transaction_id).one()
    fresh_t2 = db_session.query(models.Transaction).filter_by(transaction_id=t2.transaction_id).one()
    fresh_already = db_session.query(models.Transaction).filter_by(transaction_id=t_already.transaction_id).one()

    # Every transaction remains in its original state!
    assert fresh_t1.category_id is None
    assert fresh_t2.category_id is None
    assert fresh_already.category_id == cat_shopping.category_id


def test_batch_apply_atomic_success_and_invariants(db_session):
    """
    Audit 2 & 3: Atomic success test proving:
    - All eligible rows persist together.
    - Already-categorized rows remain untouched.
    - Invariants preserved:
      is_reviewed unchanged (False)
      merchant unchanged
      is_merchant_overridden unchanged
      transfer state unchanged
      cleared/reconciled state unchanged
      financial values unchanged
    """
    acc, cat_dining, cat_shopping, _ = _create_account_and_categories(db_session)

    t1 = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #101",
        merchant="Starbucks",
        amount=Decimal("7.25"),
        date=date(2026, 7, 15),
        category_id=None,
        is_reviewed=False,
        is_transfer=False,
        is_cleared=False,
        is_reconciled=False,
        is_merchant_overridden=False,
    )
    t2 = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #102",
        merchant="Starbucks",
        amount=Decimal("8.50"),
        date=date(2026, 7, 16),
        category_id=None,
        is_reviewed=False,
        is_transfer=False,
        is_cleared=False,
        is_reconciled=False,
        is_merchant_overridden=True,
    )
    t_already = models.Transaction(
        account_id=acc.id,
        description="STARBUCKS #103",
        merchant="Starbucks",
        amount=Decimal("15.00"),
        date=date(2026, 7, 17),
        category_id=cat_shopping.category_id,
        is_reviewed=True,
        is_transfer=False,
        is_cleared=True,
        is_reconciled=True,
        is_merchant_overridden=False,
    )
    db_session.add_all([t1, t2, t_already])
    db_session.commit()

    rule = categorization_rule_access.create_rule(db_session, "Starbucks", cat_dining.category_id)

    applied_count = categorization_rule_manager.apply_rule_to_uncategorized(db_session, rule.id)
    assert applied_count == 2

    db_session.expire_all()
    fresh_t1 = db_session.query(models.Transaction).filter_by(transaction_id=t1.transaction_id).one()
    fresh_t2 = db_session.query(models.Transaction).filter_by(transaction_id=t2.transaction_id).one()
    fresh_already = db_session.query(models.Transaction).filter_by(transaction_id=t_already.transaction_id).one()

    # Eligible transactions updated
    assert fresh_t1.category_id == cat_dining.category_id
    assert fresh_t2.category_id == cat_dining.category_id
    assert fresh_already.category_id == cat_shopping.category_id  # Pre-existing category strictly preserved!

    # Invariants strictly preserved
    assert fresh_t1.is_reviewed is False
    assert fresh_t1.merchant == "Starbucks"
    assert fresh_t1.is_merchant_overridden is False
    assert fresh_t1.is_transfer is False
    assert fresh_t1.is_cleared is False
    assert fresh_t1.is_reconciled is False
    assert fresh_t1.amount == Decimal("7.25")
    assert fresh_t1.date == date(2026, 7, 15)

    assert fresh_t2.is_reviewed is False
    assert fresh_t2.merchant == "Starbucks"
    assert fresh_t2.is_merchant_overridden is True
    assert fresh_t2.is_transfer is False
    assert fresh_t2.is_cleared is False
    assert fresh_t2.is_reconciled is False
    assert fresh_t2.amount == Decimal("8.50")
    assert fresh_t2.date == date(2026, 7, 16)

    assert fresh_already.is_reviewed is True
    assert fresh_already.is_cleared is True
    assert fresh_already.is_reconciled is True
    assert fresh_already.amount == Decimal("15.00")
