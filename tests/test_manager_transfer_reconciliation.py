from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock
from uuid import uuid4
import pytest

from backend import models
from backend.domain.reconciliation import (
    ReconciliationTransaction,
    detect_transfer_candidates,
)
from backend.managers.transfer_reconciliation_manager import (
    TransferCandidateItem,
    TransferInflowSideItem,
    TransferOutflowAccountItem,
    TransferOutflowSideItem,
    get_account_for_transaction,
    get_transfer_candidates,
)


def test_manager_transfer_reconciliation_composition(db_session):
    """
    Verify get_transfer_candidates:
    - Coordinates candidate retrieval via Transaction ResourceAccess.
    - Maps records to ReconciliationTransaction domain models.
    - Delegates pair matching to pure Reconciliation Engine.
    - Resolves account metadata via get_account_for_transaction.
    - Maps persistence records to immutable application dataclasses without ORM leakage.
    - Produces a flat Sequence[TransferCandidateItem] with no top-level wrapper.
    - TransferOutflowAccountItem contains no 'status' field (Presentation-only default).
    """
    acct_chk = models.Account(
        name="Mgr Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("3000.00"),
        starting_balance=Decimal("100.00"),
        currency="USD",
        mask="4321",
        is_active=True,
    )
    acct_card = models.Account(
        name="Mgr Card",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("-400.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
        mask="8765",
        is_active=True,
    )
    db_session.add_all([acct_chk, acct_card])
    db_session.flush()

    grp = models.CategoryGroup(name="Mgr Group", sort_order=1)
    db_session.add(grp)
    db_session.flush()
    cat = models.Category(name="Transfer Cat", group_id=grp.category_group_id, type="transfer", sort_order=1)
    db_session.add(cat)
    db_session.flush()

    # Valid matched pair
    tx_out = models.Transaction(
        account_id=acct_chk.id,
        category_id=cat.category_id,
        description="Payment Out",
        amount=Decimal("175.50"),
        date=date(2026, 6, 10),
        pending=False,
        is_transfer=False,
    )
    tx_in = models.Transaction(
        account_id=acct_card.id,
        category_id=None,
        description="Payment Received",
        amount=Decimal("-175.50"),
        date=date(2026, 6, 11),
        pending=False,
        is_transfer=False,
    )
    db_session.add_all([tx_out, tx_in])
    db_session.commit()

    candidates = get_transfer_candidates(db_session)

    # 1. Flat sequence without wrapper
    assert isinstance(candidates, list)
    assert len(candidates) == 1

    item = candidates[0]
    assert isinstance(item, TransferCandidateItem)

    # 2. Inflow side
    assert isinstance(item.inflow_side, TransferInflowSideItem)
    assert item.inflow_side.transaction_id == tx_in.transaction_id
    assert item.inflow_side.description == "Payment Received"
    assert item.inflow_side.amount == Decimal("-175.50")
    assert item.inflow_side.date == date(2026, 6, 11)
    assert item.inflow_side.is_transfer is False
    assert item.inflow_side.category_id is None
    assert item.inflow_account_name == "Mgr Card"

    # 3. Outflow side
    assert isinstance(item.outflow_side, TransferOutflowSideItem)
    assert item.outflow_side.transaction_id == tx_out.transaction_id
    assert item.outflow_side.account_id == acct_chk.id
    assert item.outflow_side.description == "Payment Out"
    assert item.outflow_side.amount == Decimal("175.50")
    assert item.outflow_side.date == date(2026, 6, 10)
    assert item.outflow_side.is_transfer is False
    assert item.outflow_side.category_id == cat.category_id
    assert item.outflow_account_name == "Mgr Checking"

    # 4. Outflow account item (no status field!)
    outflow_acc = item.outflow_side.account
    assert isinstance(outflow_acc, TransferOutflowAccountItem)
    assert outflow_acc.id == acct_chk.id
    assert outflow_acc.name == "Mgr Checking"
    assert outflow_acc.type == "depository"
    assert outflow_acc.current_balance == Decimal("3000.00")
    assert outflow_acc.starting_balance == Decimal("100.00")
    assert outflow_acc.mask == "4321"
    assert not hasattr(outflow_acc, "status")


def test_manager_transfer_reconciliation_controlled_ordering():
    """
    Verify get_transfer_candidates preserves Accessor return order exactly
    when constructing inputs for the pure Reconciliation Engine:
    - Inflow and outflow sequences are passed to detect_transfer_candidates in original sequence.
    - No sorting (by date, amount, ID, etc.) is applied.
    """
    mock_db = MagicMock()

    id_in_1, id_in_2 = uuid4(), uuid4()
    id_out_1, id_out_2 = uuid4(), uuid4()
    acct_1, acct_2 = uuid4(), uuid4()

    # Inflows in a specific controlled order (e.g. later date first)
    inflow_1 = MagicMock()
    inflow_1.transaction_id = id_in_1
    inflow_1.account_id = acct_1
    inflow_1.amount = Decimal("-100.00")
    inflow_1.date = date(2026, 6, 20)
    inflow_1.is_transfer = False

    inflow_2 = MagicMock()
    inflow_2.transaction_id = id_in_2
    inflow_2.account_id = acct_1
    inflow_2.amount = Decimal("-50.00")
    inflow_2.date = date(2026, 6, 10)
    inflow_2.is_transfer = False

    # Outflows in a specific controlled order
    outflow_1 = MagicMock()
    outflow_1.transaction_id = id_out_1
    outflow_1.account_id = acct_2
    outflow_1.amount = Decimal("100.00")
    outflow_1.date = date(2026, 6, 20)
    outflow_1.is_transfer = False

    outflow_2 = MagicMock()
    outflow_2.transaction_id = id_out_2
    outflow_2.account_id = acct_2
    outflow_2.amount = Decimal("50.00")
    outflow_2.date = date(2026, 6, 10)
    outflow_2.is_transfer = False

    with patch(
        "backend.managers.transfer_reconciliation_manager.get_unmatched_inflow_transactions",
        return_value=[inflow_1, inflow_2],
    ), patch(
        "backend.managers.transfer_reconciliation_manager.get_unmatched_outflow_transactions",
        return_value=[outflow_1, outflow_2],
    ), patch(
        "backend.managers.transfer_reconciliation_manager.detect_transfer_candidates",
        wraps=detect_transfer_candidates,
    ) as spy_engine, patch(
        "backend.managers.transfer_reconciliation_manager.get_account_for_transaction",
    ) as mock_get_acc:
        mock_acc_1 = MagicMock(id=acct_1, name="Account 1", type="credit", subtype=None,
                               current_balance=Decimal("0"), available_balance=None, starting_balance=Decimal("0"),
                               currency="USD", balance_last_updated=None, is_active=True, mask=None,
                               plaid_account_id=None, item_id=None)
        mock_acc_2 = MagicMock(id=acct_2, name="Account 2", type="depository", subtype=None,
                               current_balance=Decimal("0"), available_balance=None, starting_balance=Decimal("0"),
                               currency="USD", balance_last_updated=None, is_active=True, mask=None,
                               plaid_account_id=None, item_id=None)
        mock_get_acc.side_effect = lambda t: mock_acc_1 if t.account_id == acct_1 else mock_acc_2

        results = get_transfer_candidates(mock_db)

        # Verify Engine was invoked with inputs in EXACT Accessor sequence
        spy_engine.assert_called_once()
        call_kwargs = spy_engine.call_args.kwargs

        passed_inflows = call_kwargs["inflows"]
        assert [t.transaction_id for t in passed_inflows] == [id_in_1, id_in_2]

        passed_outflows = call_kwargs["outflows"]
        assert [t.transaction_id for t in passed_outflows] == [id_out_1, id_out_2]


def test_manager_transfer_reconciliation_resolves_accounts_only_for_matches(db_session):
    """
    Verify get_transfer_candidates calls get_account_for_transaction ONLY for
    transactions that are part of an actual matched pair, and never for unmatched candidates.
    """
    acct_chk = models.Account(name="Chk Only", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    acct_cc = models.Account(name="CC Only", type="credit", current_balance=Decimal("-200.00"), currency="USD")
    db_session.add_all([acct_chk, acct_cc])
    db_session.flush()

    # Matched pair (amount 100.00)
    tx_match_out = models.Transaction(account_id=acct_chk.id, amount=Decimal("100.00"), date=date(2026, 6, 1), description="Transfer Out", is_transfer=False)
    tx_match_in = models.Transaction(account_id=acct_cc.id, amount=Decimal("-100.00"), date=date(2026, 6, 1), description="Transfer In", is_transfer=False)

    # Unmatched candidate inflow (no matching outflow)
    tx_unmatched_in = models.Transaction(account_id=acct_cc.id, amount=Decimal("-999.00"), date=date(2026, 6, 1), description="Unmatched In", is_transfer=False)
    # Unmatched candidate outflow (no matching inflow)
    tx_unmatched_out = models.Transaction(account_id=acct_chk.id, amount=Decimal("777.00"), date=date(2026, 6, 1), description="Unmatched Out", is_transfer=False)

    db_session.add_all([tx_match_out, tx_match_in, tx_unmatched_in, tx_unmatched_out])
    db_session.commit()

    with patch(
        "backend.managers.transfer_reconciliation_manager.get_account_for_transaction",
        wraps=get_account_for_transaction,
    ) as spy_get_acc:
        candidates = get_transfer_candidates(db_session)

        assert len(candidates) == 1

        # get_account_for_transaction should be called exactly twice:
        # once for tx_match_in, once for tx_match_out.
        # It must NEVER be called for tx_unmatched_in or tx_unmatched_out.
        assert spy_get_acc.call_count == 2
        called_tx_ids = {call.args[0].transaction_id for call in spy_get_acc.call_args_list}
        assert called_tx_ids == {tx_match_in.transaction_id, tx_match_out.transaction_id}
        assert tx_unmatched_in.transaction_id not in called_tx_ids
        assert tx_unmatched_out.transaction_id not in called_tx_ids


def test_manager_transfer_reconciliation_empty_result(db_session):
    """Verify get_transfer_candidates returns empty list when no candidates exist."""
    candidates = get_transfer_candidates(db_session)
    assert isinstance(candidates, list)
    assert len(candidates) == 0


def test_manager_transfer_reconciliation_missing_account_relationship_raises(db_session):
    """
    Verify get_transfer_candidates preserves the old failure invariant when an Account
    relationship is missing: raises AttributeError rather than silently skipping the candidate
    or manufacturing empty strings/None.
    """
    acct_chk = models.Account(name="Chk", type="depository", current_balance=Decimal("1000.00"), currency="USD")
    acct_cc = models.Account(name="CC", type="credit", current_balance=Decimal("-200.00"), currency="USD")
    db_session.add_all([acct_chk, acct_cc])
    db_session.flush()

    tx_match_out = models.Transaction(account_id=acct_chk.id, amount=Decimal("100.00"), date=date(2026, 6, 1), description="Transfer Out", is_transfer=False)
    tx_match_in = models.Transaction(account_id=acct_cc.id, amount=Decimal("-100.00"), date=date(2026, 6, 1), description="Transfer In", is_transfer=False)
    db_session.add_all([tx_match_out, tx_match_in])
    db_session.commit()

    with patch(
        "backend.managers.transfer_reconciliation_manager.get_account_for_transaction",
        return_value=None,
    ):
        with pytest.raises(AttributeError, match="Account relationship missing"):
            get_transfer_candidates(db_session)

