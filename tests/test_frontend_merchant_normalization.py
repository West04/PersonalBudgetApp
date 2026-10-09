"""
Frontend contract tests for Phase 8 Merchant Normalization in transactions.vue.

Verifies:
1. Table header presents 'Merchant / Description'.
2. Row presentation includes primary merchant name with edit button affordance.
3. Secondary text exposes raw imported description when it differs from normalized merchant.
4. Inline editing form provides accessible controls: text input, save (✓), cancel (✕), and Escape key handler.
5. Search input placeholder and accessible label indicate merchant and description searchability.
"""

import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TX_VUE = REPO_ROOT / "frontend" / "app" / "pages" / "transactions.vue"


def has_class(content: str, name: str) -> bool:
    """True when a static class attribute contains `name` as a whole token."""
    return re.search(r'\bclass="[^"]*(?<![\w-])' + re.escape(name) + r'(?![\w-])[^"]*"', content) is not None


def test_transactions_table_header_has_merchant_and_description():
    content = TX_VUE.read_text(encoding="utf-8")
    assert re.search(r'<th scope="col" class="desc-col"[^>]*>Merchant / Description</th>', content)


def test_transactions_row_renders_merchant_and_edit_button():
    content = TX_VUE.read_text(encoding="utf-8")
    assert 'class="merchant-row"' in content
    assert 'class="merchant-name"' in content
    assert has_class(content, "btn-edit-merchant")
    assert ':aria-label="`Edit merchant for ${tx.merchant || tx.description}`"' in content


def test_transactions_row_renders_secondary_raw_description():
    content = TX_VUE.read_text(encoding="utf-8")
    assert 'class="raw-desc-text"' in content
    assert ':title="`Original description: ${tx.description}`"' in content
    assert "{{ tx.description }}" in content


def test_transactions_inline_merchant_editing_form():
    content = TX_VUE.read_text(encoding="utf-8")
    assert 'class="merchant-edit-form"' in content
    assert 'class="merchant-edit-input"' in content
    assert '@keydown.esc="cancelEditingMerchant"' in content
    assert has_class(content, "btn-save-merchant")
    assert has_class(content, "btn-cancel-merchant")
    assert 'const startEditingMerchant' in content
    assert 'const cancelEditingMerchant' in content
    assert 'const saveMerchant' in content


def test_search_input_indicates_merchant_searchability():
    content = TX_VUE.read_text(encoding="utf-8")
    assert 'placeholder="Search description or merchant..."' in content
    assert 'aria-label="Search transaction description or merchant"' in content
