from uuid import uuid4
from backend.domain.categorization_rules import (
    clean_merchant_key,
    is_eligible_for_rule,
    match_merchant_rule,
)


def test_clean_merchant_key_casing_and_whitespace():
    assert clean_merchant_key("Starbucks") == "starbucks"
    assert clean_merchant_key("  STARBUCKS  ") == "starbucks"
    assert clean_merchant_key("Trader   Joe's") == "trader joe's"
    assert clean_merchant_key("starbucks") == "starbucks"


def test_clean_merchant_key_empty_or_none():
    assert clean_merchant_key(None) is None
    assert clean_merchant_key("") is None
    assert clean_merchant_key("   ") is None


def test_is_eligible_for_rule():
    # Only transactions with current_category_id = None are eligible
    assert is_eligible_for_rule(None) is True
    assert is_eligible_for_rule(uuid4()) is False


def test_match_merchant_rule():
    cat_dining = uuid4()
    cat_groceries = uuid4()
    rules_lookup = {
        "starbucks": cat_dining,
        "trader joe's": cat_groceries,
    }

    assert match_merchant_rule("Starbucks", rules_lookup) == cat_dining
    assert match_merchant_rule("  STARBUCKS ", rules_lookup) == cat_dining
    assert match_merchant_rule("Trader Joe's", rules_lookup) == cat_groceries
    assert match_merchant_rule("Target", rules_lookup) is None
    assert match_merchant_rule(None, rules_lookup) is None
    assert match_merchant_rule("", rules_lookup) is None
