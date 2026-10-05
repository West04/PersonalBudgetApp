"""
Pure domain functions and invariants for transaction categorization rules.

Invariants:
1. Exact Match: Operates on normalized merchant identity, not noisy raw description.
2. Case/Whitespace Insensitive: 'Starbucks', 'STARBUCKS', and '  Starbucks  ' map to the same key.
3. Category Preservation: Automatic rules ONLY apply when transaction.category_id is None. Existing non-null categories are strictly preserved.
4. Empty Merchant Ineligible: None, blank, or empty merchants never match a rule.
5. Pure: No ORM, no Session, no HTTP, no external network or environment calls.
"""

from collections.abc import Mapping
from typing import Optional
from uuid import UUID


def clean_merchant_key(merchant: Optional[str]) -> Optional[str]:
    """
    Normalizes a merchant string for deterministic rule identity and matching:
    - Strips leading and trailing whitespace.
    - Collapses internal whitespace sequences to a single space.
    - Converts to lowercase.
    Returns None if merchant is None or empty.
    """
    if merchant is None:
        return None
    cleaned = " ".join(merchant.split()).strip().lower()
    return cleaned if cleaned else None


def is_eligible_for_rule(current_category_id: Optional[UUID]) -> bool:
    """
    Evaluates whether a transaction is eligible for automatic rule categorization.
    Strict domain rule: Only transactions with category_id IS NULL are eligible.
    Transactions with existing categories (manual or prior) are never overwritten.
    """
    return current_category_id is None


def match_merchant_rule(
    merchant: Optional[str],
    rules_lookup: Mapping[str, UUID],
) -> Optional[UUID]:
    """
    Matches a normalized merchant against a pre-indexed rules lookup mapping
    (clean_merchant_key -> category_id).
    Returns matched category_id UUID if found, otherwise None.
    """
    key = clean_merchant_key(merchant)
    if not key:
        return None
    return rules_lookup.get(key)
