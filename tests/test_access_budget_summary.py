from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest

from backend import models
from backend.access.category_access import get_category_groups
from backend.access.budget_access import get_budgets_for_month
from backend.access.transaction_access import get_actuals_by_category


def test_category_access_get_category_groups_ordering_and_eager_loading(db_session):
    """Verify get_category_groups eagerly loads categories and orders groups by sort_order."""
    g2 = models.CategoryGroup(name="Personal", sort_order=2)
    g1 = models.CategoryGroup(name="Essentials", sort_order=1)
    db_session.add_all([g2, g1])
    db_session.flush()

    c1 = models.Category(group_id=g1.category_group_id, name="Rent", type="expense", sort_order=1)
    c2 = models.Category(group_id=g1.category_group_id, name="Groceries", type="expense", sort_order=2)
    c3 = models.Category(group_id=g2.category_group_id, name="Hobbies", type="expense", sort_order=1)
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    groups = get_category_groups(db_session)
    assert len(groups) == 2
    assert groups[0].name == "Essentials"
    assert groups[1].name == "Personal"
    # Verify categories are eagerly loaded
    assert len(groups[0].categories) == 2
    assert {c.name for c in groups[0].categories} == {"Rent", "Groceries"}
    assert len(groups[1].categories) == 1
    assert groups[1].categories[0].name == "Hobbies"


def test_budget_access_get_budgets_for_month(db_session):
    """Verify get_budgets_for_month retrieves budgets only for the specified month."""
    group = models.CategoryGroup(name="Bills", sort_order=1)
    db_session.add(group)
    db_session.flush()

    cat1 = models.Category(group_id=group.category_group_id, name="Electric", type="expense", sort_order=1)
    cat2 = models.Category(group_id=group.category_group_id, name="Water", type="expense", sort_order=2)
    db_session.add_all([cat1, cat2])
    db_session.flush()

    # June budgets
    b_june1 = models.Budget(category_id=cat1.category_id, budget_month=date(2026, 6, 1), planned_amount=Decimal("150.00"))
    b_june2 = models.Budget(category_id=cat2.category_id, budget_month=date(2026, 6, 1), planned_amount=Decimal("50.00"))
    # July budget (different month)
    b_july = models.Budget(category_id=cat1.category_id, budget_month=date(2026, 7, 1), planned_amount=Decimal("175.00"))
    db_session.add_all([b_june1, b_june2, b_july])
    db_session.commit()

    june_budgets = get_budgets_for_month(db_session, date(2026, 6, 1))
    assert len(june_budgets) == 2
    planned_map = {b.category_id: b.planned_amount for b in june_budgets}
    assert planned_map[cat1.category_id] == Decimal("150.00")
    assert planned_map[cat2.category_id] == Decimal("50.00")

    july_budgets = get_budgets_for_month(db_session, date(2026, 7, 1))
    assert len(july_budgets) == 1
    assert july_budgets[0].planned_amount == Decimal("175.00")


def test_transaction_access_get_actuals_by_category(db_session):
    """Verify get_actuals_by_category aggregates transaction amounts by category within date range."""
    # Account
    account = models.Account(
        name="Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000.00"),
        starting_balance=Decimal("0.00"),
        currency="USD",
    )
    # Category Group & Categories
    group = models.CategoryGroup(name="Living", sort_order=1)
    db_session.add_all([account, group])
    db_session.flush()

    cat1 = models.Category(group_id=group.category_group_id, name="Dining", type="expense", sort_order=1)
    cat2 = models.Category(group_id=group.category_group_id, name="Transport", type="expense", sort_order=2)
    db_session.add_all([cat1, cat2])
    db_session.flush()

    # June transactions for cat1: 40.00 + 60.00 = 100.00
    tx1 = models.Transaction(account_id=account.id, category_id=cat1.category_id, amount=Decimal("40.00"), date=date(2026, 6, 5), description="Dining 1")
    tx2 = models.Transaction(account_id=account.id, category_id=cat1.category_id, amount=Decimal("60.00"), date=date(2026, 6, 15), description="Dining 2")
    # June transaction for cat2: 25.00
    tx3 = models.Transaction(account_id=account.id, category_id=cat2.category_id, amount=Decimal("25.00"), date=date(2026, 6, 20), description="Transport 1")
    # May transaction (out of date range): 80.00
    tx_past = models.Transaction(account_id=account.id, category_id=cat1.category_id, amount=Decimal("80.00"), date=date(2026, 5, 28), description="Past Dining")
    # Uncategorized transaction in June (category_id is None): 15.00 (must be ignored)
    tx_uncat = models.Transaction(account_id=account.id, category_id=None, amount=Decimal("15.00"), date=date(2026, 6, 10), description="Uncat")

    db_session.add_all([tx1, tx2, tx3, tx_past, tx_uncat])
    db_session.commit()

    actuals = get_actuals_by_category(db_session, date(2026, 6, 1), date(2026, 7, 1))
    assert actuals.get(cat1.category_id) == Decimal("100.00")
    assert actuals.get(cat2.category_id) == Decimal("25.00")
    assert None not in actuals
