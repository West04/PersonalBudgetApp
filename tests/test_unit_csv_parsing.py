from decimal import Decimal
from uuid import uuid4
from datetime import date
import pytest

from backend.bank_statement_loader import (
    USAALoader,
    DiscoverLoader,
    get_loader,
    LOADER_REGISTRY
)


def test_usaa_loader_parsing_and_sign_inversion():
    """
    USAA exports charges/purchases as negative amounts, deposits as positive amounts.
    The application convention requires outflows (purchases) to be POSITIVE.
    Verify USAALoader inverts signs accordingly.
    """
    account_id = uuid4()
    loader = USAALoader(account_id=account_id)

    csv_content = (
        "Date,Description,Category,Amount,Status\n"
        "2026-05-15,HEB GROCERY,Food,-85.42,posted\n"
        "2026-05-16,PAYCHECK,Income,2450.00,posted\n"
        "2026-05-17,PENDING COFFEE,Food,-4.75,pending\n"
        "2026-05-18,ZERO DOLLAR ADJUSTMENT,Misc,0.00,posted\n"
    )

    transactions = loader.load_from_text(csv_content)
    assert len(transactions) == 4

    # 1. Purchase: raw -85.42 -> converted to +85.42 (outflow > 0)
    t1 = transactions[0]
    assert t1.account_id == account_id
    assert t1.date == date(2026, 5, 15)
    assert t1.description == "HEB GROCERY"
    assert t1.amount == Decimal("85.42")
    assert t1.pending is False

    # 2. Deposit: raw +2450.00 -> converted to -2450.00 (inflow < 0)
    t2 = transactions[1]
    assert t2.date == date(2026, 5, 16)
    assert t2.description == "PAYCHECK"
    assert t2.amount == Decimal("-2450.00")
    assert t2.pending is False

    # 3. Pending: status is 'pending' -> pending is True
    t3 = transactions[2]
    assert t3.amount == Decimal("4.75")
    assert t3.pending is True

    # 4. Zero amount: -0.00 -> Decimal('0.00')
    t4 = transactions[3]
    assert t4.amount == Decimal("0.00")


def test_discover_loader_parsing_and_sign_preservation():
    """
    Discover exports credit card charges as positive amounts.
    The application convention requires outflows to be POSITIVE.
    Verify DiscoverLoader preserves positive amounts.
    """
    account_id = uuid4()
    loader = DiscoverLoader(account_id=account_id)

    csv_content = (
        "Trans. Date,Description,Amount,Category\n"
        "05/20/2026,TARGET STORE,64.21,Merchandise\n"
        "05/21/2026,ONLINE PAYMENT - THANK YOU,-200.00,Payments\n"
        "05/22/2026,REBATE REWARD,-15.50,Rewards\n"
    )

    transactions = loader.load_from_text(csv_content)
    assert len(transactions) == 3

    # 1. Charge: raw 64.21 -> preserved as +64.21 (outflow > 0)
    t1 = transactions[0]
    assert t1.account_id == account_id
    assert t1.date == date(2026, 5, 20)
    assert t1.description == "TARGET STORE"
    assert t1.amount == Decimal("64.21")
    assert t1.pending is False

    # 2. Payment received: raw -200.00 -> preserved as -200.00 (inflow/payment < 0)
    t2 = transactions[1]
    assert t2.date == date(2026, 5, 21)
    assert t2.description == "ONLINE PAYMENT - THANK YOU"
    assert t2.amount == Decimal("-200.00")

    # 3. Credit / Rebate: raw -15.50 -> preserved as -15.50
    t3 = transactions[2]
    assert t3.amount == Decimal("-15.50")


def test_missing_column_raises_value_error():
    account_id = uuid4()
    loader = USAALoader(account_id=account_id)

    # Missing "Status" column
    csv_missing_col = (
        "Date,Description,Category,Amount\n"
        "2026-05-15,HEB GROCERY,Food,-85.42\n"
    )

    with pytest.raises(ValueError, match="Missing columns"):
        loader.load_from_text(csv_missing_col)


def test_get_loader_factory():
    account_id = uuid4()

    usaa = get_loader("usaa", account_id)
    assert isinstance(usaa, USAALoader)

    discover = get_loader("discover", account_id)
    assert isinstance(discover, DiscoverLoader)

    with pytest.raises(ValueError, match="Unknown format 'chase'"):
        get_loader("chase", account_id)
