from datetime import date
from decimal import Decimal
from unittest.mock import patch, ANY
import pytest

from backend import models
from backend.domain.credit_cards import (
    CreditCardState,
    CreditCardTransaction,
    calculate_credit_card_state,
)
from backend.managers.credit_card_summary_manager import (
    CreditCardAccountSummaryItem,
    CreditCardMonthlyTransactionItem,
    CreditCardSummaryResult,
    get_credit_card_summary,
)


def test_manager_get_credit_card_summary_composition_and_isolation(db_session):
    """
    Verify get_credit_card_summary:
    - Retrieves active credit accounts ordered by name ascending.
    - Excludes inactive credit accounts and non-credit accounts.
    - Coordinates historical transaction loading per card.
    - Reuses CreditCardState directly from Credit Card Engine.
    - Filters current-month transactions for display [start_date, end_date).
    - Preserves transaction date descending ordering.
    - Maps persistence records to immutable application dataclasses without ORM leakage.
    - Preserves field pass-through: category_id (UUID and None), verbatim description.
    """
    month_date = date(2026, 6, 1)

    # Category for category_id pass-through test
    group = models.CategoryGroup(name="CC Group", sort_order=1)
    db_session.add(group)
    db_session.flush()
    cat = models.Category(name="Dining", group_id=group.category_group_id, type="expense", sort_order=1)
    db_session.add(cat)
    db_session.flush()

    # Active cards (inserted in non-alphabetical order)
    card_z = models.Account(
        name="Zeta Card",
        type="credit",
        is_active=True,
        starting_balance=Decimal("200.00"),
        current_balance=Decimal("999.00"),  # Unused by workflow
    )
    card_a = models.Account(
        name="Alpha Visa",
        type="credit",
        is_active=True,
        starting_balance=Decimal("500.00"),
        current_balance=Decimal("888.00"),  # Unused by workflow
    )
    # Excluded accounts
    inactive_card = models.Account(
        name="AAA Inactive",
        type="credit",
        is_active=False,
        starting_balance=Decimal("100.00"),
    )
    checking = models.Account(
        name="AAA Checking",
        type="depository",
        is_active=True,
        starting_balance=Decimal("1000.00"),
    )
    db_session.add_all([card_z, card_a, inactive_card, checking])
    db_session.flush()

    # Transactions for Alpha Visa:
    # May (past): +50.00 (affects balance_owed, excluded from display)
    t_past = models.Transaction(
        account_id=card_a.id,
        amount=Decimal("50.00"),
        date=date(2026, 5, 20),
        description="May Grocery",
        is_transfer=False,
    )
    # June (current month):
    # - June 25: payment -100.00 (transfer payment)
    t_june_late = models.Transaction(
        account_id=card_a.id,
        amount=Decimal("-100.00"),
        date=date(2026, 6, 25),
        description="Payment",
        is_transfer=True,
        category_id=None,
    )
    # - June 15: transfer +40.00
    t_june_mid = models.Transaction(
        account_id=card_a.id,
        amount=Decimal("40.00"),
        date=date(2026, 6, 15),
        description="Transfer In",
        is_transfer=True,
    )
    # - June 5: charge +150.00 (with category)
    t_june_early = models.Transaction(
        account_id=card_a.id,
        amount=Decimal("150.00"),
        date=date(2026, 6, 5),
        description="Dinner",
        is_transfer=False,
        category_id=cat.category_id,
    )
    # July (future): +200.00 (excluded from June point-in-time balance_owed)
    t_future = models.Transaction(
        account_id=card_a.id,
        amount=Decimal("200.00"),
        date=date(2026, 7, 5),
        description="July Flight",
        is_transfer=False,
    )

    # Transactions for Zeta Card (isolation check)
    t_zeta = models.Transaction(
        account_id=card_z.id,
        amount=Decimal("75.00"),
        date=date(2026, 6, 10),
        description="Zeta Book",
        is_transfer=False,
    )

    db_session.add_all([t_past, t_june_late, t_june_mid, t_june_early, t_future, t_zeta])
    db_session.commit()

    result = get_credit_card_summary(db_session, month_date)

    # 1. Structure assertions
    assert isinstance(result, CreditCardSummaryResult)
    assert len(result.cards) == 2

    # 2. Ordering: Alpha Visa then Zeta Card
    c0 = result.cards[0]
    c1 = result.cards[1]
    assert c0.account_name == "Alpha Visa"
    assert c1.account_name == "Zeta Card"

    # 3. Direct reuse of CreditCardState
    assert isinstance(c0.state, CreditCardState)
    assert isinstance(c1.state, CreditCardState)

    # 4. Financial calculations for Alpha Visa:
    # Starting balance: 500.00
    # Net past + June: 50 (May) + (-100 + 40 + 150) (June) = 140.00 (July 200 excluded)
    # balance_owed: 500 + 140 = 640.00
    # charges_this_month: 150.00 (transfer 40.00 excluded)
    # payments_this_month: 100.00
    assert c0.state.starting_balance == Decimal("500.00")
    assert c0.state.balance_owed == Decimal("640.00")
    assert c0.state.charges_this_month == Decimal("150.00")
    assert c0.state.payments_this_month == Decimal("100.00")

    # 5. Monthly display transactions for Alpha Visa:
    # Exactly 3 June transactions, strictly ordered date DESC (June 25, June 15, June 5)
    assert len(c0.transactions) == 3
    assert all(isinstance(t, CreditCardMonthlyTransactionItem) for t in c0.transactions)
    assert not any(isinstance(t, models.Transaction) for t in c0.transactions)

    assert c0.transactions[0].date == date(2026, 6, 25)
    assert c0.transactions[0].amount == Decimal("-100.00")
    assert c0.transactions[0].category_id is None

    assert c0.transactions[1].date == date(2026, 6, 15)
    assert c0.transactions[1].is_transfer is True

    assert c0.transactions[2].date == date(2026, 6, 5)
    assert c0.transactions[2].amount == Decimal("150.00")
    assert c0.transactions[2].category_id == cat.category_id

    # 6. Isolation for Zeta Card:
    # Starting balance: 200.00, Net all-time: 75.00, balance_owed: 275.00
    assert c1.state.starting_balance == Decimal("200.00")
    assert c1.state.balance_owed == Decimal("275.00")
    assert c1.state.charges_this_month == Decimal("75.00")
    assert c1.state.payments_this_month == Decimal("0.00")
    assert len(c1.transactions) == 1
    assert c1.transactions[0].description == "Zeta Book"


def test_manager_delegates_to_credit_card_engine(db_session):
    """
    Verify get_credit_card_summary maps ORM transactions to pure CreditCardTransaction
    and delegates calculation to calculate_credit_card_state.
    """
    card = models.Account(
        name="Engine Test Card",
        type="credit",
        is_active=True,
        starting_balance=Decimal("150.00"),
    )
    db_session.add(card)
    db_session.flush()

    tx = models.Transaction(
        account_id=card.id,
        amount=Decimal("25.00"),
        date=date(2026, 6, 10),
        description="Coffee",
        is_transfer=False,
    )
    db_session.add(tx)
    db_session.commit()

    with patch(
        "backend.managers.credit_card_summary_manager.calculate_credit_card_state",
        wraps=calculate_credit_card_state,
    ) as spy_engine:
        result = get_credit_card_summary(db_session, date(2026, 6, 1))

        spy_engine.assert_called_once()
        call_kwargs = spy_engine.call_args.kwargs
        assert call_kwargs["starting_balance"] == Decimal("150.00")
        assert call_kwargs["period_start"] == date(2026, 6, 1)
        assert call_kwargs["period_end"] == date(2026, 7, 1)
        assert call_kwargs["cutoff_exclusive"] == date(2026, 7, 1)

        domain_txns = call_kwargs["transactions"]
        assert len(domain_txns) == 1
        assert isinstance(domain_txns[0], CreditCardTransaction)
        assert not isinstance(domain_txns[0], models.Transaction)
        assert domain_txns[0].amount == Decimal("25.00")
        assert domain_txns[0].date == date(2026, 6, 10)
        assert domain_txns[0].is_transfer is False


def test_manager_passes_explicit_as_of_date_cutoff(db_session):
    """
    Verify get_credit_card_summary computes cutoff_exclusive using explicit as_of_date:
    When viewing June 2026 on June 15, cutoff_exclusive is June 16.
    """
    card = models.Account(
        name="Cutoff Card",
        type="credit",
        is_active=True,
        starting_balance=Decimal("0.00"),
    )
    db_session.add(card)
    db_session.commit()

    with patch(
        "backend.managers.credit_card_summary_manager.calculate_credit_card_state",
        wraps=calculate_credit_card_state,
    ) as spy_engine:
        result = get_credit_card_summary(
            db_session,
            budget_month=date(2026, 6, 1),
            as_of_date=date(2026, 6, 15),
        )

        spy_engine.assert_called_once()
        call_kwargs = spy_engine.call_args.kwargs
        assert call_kwargs["cutoff_exclusive"] == date(2026, 6, 16)



def test_manager_get_credit_card_summary_zero_transactions(db_session):
    """
    Verify active card with zero transactions:
    - balance_owed == starting_balance
    - charges_this_month == 0.00
    - payments_this_month == 0.00
    - transactions == []
    """
    card = models.Account(
        name="Empty Card",
        type="credit",
        is_active=True,
        starting_balance=Decimal("350.00"),
    )
    db_session.add(card)
    db_session.commit()

    result = get_credit_card_summary(db_session, date(2026, 6, 1))

    assert len(result.cards) == 1
    card_item = result.cards[0]
    assert card_item.account_name == "Empty Card"
    assert card_item.state.starting_balance == Decimal("350.00")
    assert card_item.state.balance_owed == Decimal("350.00")
    assert card_item.state.charges_this_month == Decimal("0.00")
    assert card_item.state.payments_this_month == Decimal("0.00")
    assert card_item.transactions == []


def test_manager_get_credit_card_summary_no_active_cards(db_session):
    """Verify empty result when no active credit accounts exist."""
    checking = models.Account(name="Checking", type="depository", is_active=True)
    inactive_cc = models.Account(name="Old Card", type="credit", is_active=False)
    db_session.add_all([checking, inactive_cc])
    db_session.commit()

    result = get_credit_card_summary(db_session, date(2026, 6, 1))

    assert isinstance(result, CreditCardSummaryResult)
    assert len(result.cards) == 0
