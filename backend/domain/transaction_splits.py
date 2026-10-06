"""
Pure domain functions and invariants for transaction split allocations.

Invariants:
1. Pure: No ORM, no Session, no HTTP, no filesystem, no external environment.
2. Exact Decimal Accounting: sum(split.amount) == parent.amount using exact Decimal.
3. Minimum Split Count: At least 2 allocations are required for a split.
4. Non-zero Allocations: Split allocation amounts cannot be zero.
5. Sign Consistency: Every split allocation must have the same sign/direction as the parent transaction.
6. Unique Category Allocations: Duplicate categories within a single split are rejected.
7. Order-Independent: Validation behavior is identical regardless of input order.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class SplitAllocationInput:
    category_id: UUID
    amount: Decimal


@dataclass(frozen=True)
class SplitValidationResult:
    is_valid: bool
    error: Optional[str] = None
    total_allocated: Optional[Decimal] = None
    remaining_amount: Optional[Decimal] = None


def calculate_remaining_amount(
    parent_amount: Decimal,
    allocated_amounts: Sequence[Decimal | SplitAllocationInput],
) -> Decimal:
    """
    Computes remaining unallocated amount: parent_amount - sum(allocated_amounts).
    Uses exact Decimal arithmetic.
    """
    parent_dec = Decimal(str(parent_amount))
    amounts = [
        Decimal(str(a.amount)) if isinstance(a, SplitAllocationInput) else Decimal(str(a))
        for a in allocated_amounts
    ]
    alloc_sum = sum(amounts, ZERO)
    return parent_dec - alloc_sum


def validate_split_allocations(
    parent_amount: Decimal,
    allocations: Sequence[SplitAllocationInput],
) -> SplitValidationResult:
    """
    Validates split allocations against core accounting invariants:
    - Parent amount must be non-zero.
    - At least 2 allocations required.
    - All category IDs must be present.
    - No duplicate categories allowed.
    - All allocation amounts must be non-zero.
    - All allocation amounts must match parent sign.
    - Exact sum of allocation amounts must equal parent amount.
    """
    parent_dec = Decimal(str(parent_amount))
    alloc_sum = sum((Decimal(str(a.amount)) for a in allocations if a.amount is not None), ZERO)
    remaining = parent_dec - alloc_sum

    if parent_dec == ZERO:
        return SplitValidationResult(
            is_valid=False,
            error="Parent transaction cannot have a zero amount.",
            total_allocated=alloc_sum,
            remaining_amount=remaining,
        )

    if len(allocations) < 2:
        return SplitValidationResult(
            is_valid=False,
            error="A split transaction must have at least 2 allocations.",
            total_allocated=alloc_sum,
            remaining_amount=remaining,
        )

    seen_categories: set[UUID] = set()
    total_allocated = ZERO

    for alloc in allocations:
        if alloc.category_id is None:
            return SplitValidationResult(
                is_valid=False,
                error="All split allocations must specify a valid category.",
                total_allocated=alloc_sum,
                remaining_amount=remaining,
            )

        if alloc.category_id in seen_categories:
            return SplitValidationResult(
                is_valid=False,
                error="Duplicate category in split allocations.",
                total_allocated=alloc_sum,
                remaining_amount=remaining,
            )
        seen_categories.add(alloc.category_id)

        amt_dec = Decimal(str(alloc.amount))
        if amt_dec == ZERO:
            return SplitValidationResult(
                is_valid=False,
                error="Split allocation amounts must be non-zero.",
                total_allocated=alloc_sum,
                remaining_amount=remaining,
            )

        if parent_dec > ZERO and amt_dec < ZERO:
            return SplitValidationResult(
                is_valid=False,
                error="All split allocations must have the same sign as the parent transaction.",
                total_allocated=alloc_sum,
                remaining_amount=remaining,
            )
        if parent_dec < ZERO and amt_dec > ZERO:
            return SplitValidationResult(
                is_valid=False,
                error="All split allocations must have the same sign as the parent transaction.",
                total_allocated=alloc_sum,
                remaining_amount=remaining,
            )

        total_allocated += amt_dec

    if total_allocated != parent_dec:
        return SplitValidationResult(
            is_valid=False,
            error=f"Split allocations sum ({total_allocated}) must equal parent transaction amount ({parent_dec}).",
            total_allocated=total_allocated,
            remaining_amount=remaining,
        )

    return SplitValidationResult(
        is_valid=True,
        error=None,
        total_allocated=total_allocated,
        remaining_amount=ZERO,
    )
