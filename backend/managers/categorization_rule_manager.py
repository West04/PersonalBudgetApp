"""
Manager for Categorization Rule batch application workflows.

Coordinates:
1. Verifying rule existence via CategorizationRule ResourceAccess.
2. Querying matching uncategorized transactions (where category_id IS NULL).
3. Updating transaction category_id while strictly preserving manual/existing categories,
   merchant identity, review status, and financial fields.
4. Owning the batch commit transaction boundary.
5. Reporting affected transaction counts.
"""

from uuid import UUID
from sqlalchemy.orm import Session

from ..access import categorization_rule_access, transaction_access
from ..domain.categorization_rules import clean_merchant_key


class CategorizationRuleNotFoundError(Exception):
    """Raised when a requested CategorizationRule does not exist in persistence."""
    pass


def preview_rule_matches(db: Session, rule_id: UUID) -> int:
    """
    Counts existing uncategorized transactions whose normalized merchant matches the rule.
    Safe read-only inspection query. Does not mutate or commit.
    """
    rule = categorization_rule_access.get_rule_by_id(db, rule_id)
    if not rule:
        raise CategorizationRuleNotFoundError(f"Categorization rule {rule_id} not found.")

    clean_key = clean_merchant_key(rule.merchant)
    if not clean_key:
        return 0

    return transaction_access.count_uncategorized_transactions_by_merchant_key(
        db=db,
        clean_merchant_key=clean_key,
    )


def apply_rule_to_uncategorized(db: Session, rule_id: UUID) -> int:
    """
    Coordinates retroactive rule execution:
    1. Loads the rule.
    2. Identifies matching transactions that are currently uncategorized (category_id IS NULL)
       via transaction_access. Transactions that already have a category are strictly excluded and untouched.
    3. Accessor updates matching rows and flushes without committing.
    4. Manager commits the batch atomically, or rolls back on any error.
    5. Returns the count of categorized transactions.
    """
    rule = categorization_rule_access.get_rule_by_id(db, rule_id)
    if not rule:
        raise CategorizationRuleNotFoundError(f"Categorization rule {rule_id} not found.")

    clean_key = clean_merchant_key(rule.merchant)
    if not clean_key:
        return 0

    try:
        updated_count = transaction_access.apply_category_to_uncategorized_by_merchant_key(
            db=db,
            clean_merchant_key=clean_key,
            category_id=rule.category_id,
        )
        db.commit()
        return updated_count
    except Exception:
        db.rollback()
        raise
