"""
Unit tests for Pure Split Domain Engine (backend/domain/transaction_splits.py).

Verifies:
1. Minimum split count invariant (>= 2).
2. Non-zero amount invariant.
3. Sign consistency invariant (matches parent outflow or inflow).
4. Exact Decimal sum invariant (sum(splits) == parent.amount, no float drift).
5. Category uniqueness invariant (no duplicate categories in allocations).
6. Order independence of allocations.
7. Remaining amount calculation accuracy.
"""

from decimal import Decimal
from uuid import uuid4
import pytest

from backend.domain.transaction_splits import (
    SplitAllocationInput,
    SplitValidationResult,
    calculate_remaining_amount,
    validate_split_allocations,
)


def test_valid_two_way_outflow_split():
    cat1, cat2 = uuid4(), uuid4()
    parent_amount = Decimal("150.00")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("100.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("50.00")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is True
    assert res.error is None
    assert res.remaining_amount == Decimal("0.00")
    assert res.total_allocated == Decimal("150.00")


def test_valid_multi_way_outflow_split():
    cat1, cat2, cat3, cat4 = uuid4(), uuid4(), uuid4(), uuid4()
    parent_amount = Decimal("245.89")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("100.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("45.89")),
        SplitAllocationInput(category_id=cat3, amount=Decimal("50.00")),
        SplitAllocationInput(category_id=cat4, amount=Decimal("50.00")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is True
    assert res.total_allocated == Decimal("245.89")
    assert res.remaining_amount == Decimal("0.00")


def test_minimum_count_invariant():
    cat1 = uuid4()
    parent_amount = Decimal("100.00")

    # Empty allocations
    res_empty = validate_split_allocations(parent_amount, [])
    assert res_empty.is_valid is False
    assert "at least 2 allocations" in res_empty.error

    # Single allocation
    res_single = validate_split_allocations(
        parent_amount,
        [SplitAllocationInput(category_id=cat1, amount=Decimal("100.00"))],
    )
    assert res_single.is_valid is False
    assert "at least 2 allocations" in res_single.error


def test_under_allocated_outflow_rejected():
    cat1, cat2 = uuid4(), uuid4()
    parent_amount = Decimal("150.00")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("100.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("49.99")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is False
    assert "must equal parent transaction amount" in res.error
    assert res.remaining_amount == Decimal("0.01")


def test_over_allocated_outflow_rejected():
    cat1, cat2 = uuid4(), uuid4()
    parent_amount = Decimal("150.00")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("100.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("50.01")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is False
    assert "must equal parent transaction amount" in res.error
    assert res.remaining_amount == Decimal("-0.01")


def test_zero_amount_allocation_rejected():
    cat1, cat2 = uuid4(), uuid4()
    parent_amount = Decimal("150.00")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("150.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("0.00")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is False
    assert "non-zero" in res.error


def test_mixed_sign_outflow_rejected():
    cat1, cat2 = uuid4(), uuid4()
    parent_amount = Decimal("150.00")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("200.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("-50.00")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is False
    assert "same sign" in res.error


def test_valid_inflow_split():
    cat1, cat2 = uuid4(), uuid4()
    parent_amount = Decimal("-150.00")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("-100.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("-50.00")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is True
    assert res.remaining_amount == Decimal("0.00")
    assert res.total_allocated == Decimal("-150.00")


def test_inflow_split_with_positive_amount_rejected():
    cat1, cat2 = uuid4(), uuid4()
    parent_amount = Decimal("-150.00")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("100.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("-250.00")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is False
    assert "same sign" in res.error


def test_duplicate_categories_rejected():
    cat1 = uuid4()
    parent_amount = Decimal("100.00")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("50.00")),
        SplitAllocationInput(category_id=cat1, amount=Decimal("50.00")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is False
    assert "Duplicate category" in res.error


def test_parent_amount_zero_rejected():
    cat1, cat2 = uuid4(), uuid4()
    parent_amount = Decimal("0.00")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("0.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("0.00")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is False
    assert "cannot have a zero amount" in res.error


def test_exact_decimal_precision_no_float_drift():
    # In float arithmetic: 0.10 + 0.20 = 0.30000000000000004 != 0.30
    cat1, cat2 = uuid4(), uuid4()
    parent_amount = Decimal("0.30")
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("0.10")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("0.20")),
    ]

    res = validate_split_allocations(parent_amount, allocations)
    assert res.is_valid is True
    assert res.remaining_amount == Decimal("0.00")


def test_order_independence():
    cat1, cat2, cat3 = uuid4(), uuid4(), uuid4()
    parent_amount = Decimal("100.00")
    alloc_a = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("20.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("30.00")),
        SplitAllocationInput(category_id=cat3, amount=Decimal("50.00")),
    ]
    alloc_b = [
        SplitAllocationInput(category_id=cat3, amount=Decimal("50.00")),
        SplitAllocationInput(category_id=cat1, amount=Decimal("20.00")),
        SplitAllocationInput(category_id=cat2, amount=Decimal("30.00")),
    ]

    res_a = validate_split_allocations(parent_amount, alloc_a)
    res_b = validate_split_allocations(parent_amount, alloc_b)
    assert res_a.is_valid is True
    assert res_b.is_valid is True
    assert res_a.total_allocated == res_b.total_allocated


def test_calculate_remaining_amount():
    cat1 = uuid4()
    allocations = [
        SplitAllocationInput(category_id=cat1, amount=Decimal("45.25")),
    ]
    rem = calculate_remaining_amount(Decimal("100.00"), allocations)
    assert rem == Decimal("54.75")
