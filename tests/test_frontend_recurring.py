"""
Frontend template and accessibility tests for Recurring Transactions in transactions.vue.
"""

import re
from pathlib import Path
import pytest

TRANSACTIONS_VUE = Path("frontend/app/pages/transactions.vue")


def has_class(content: str, name: str) -> bool:
    """True when a static class attribute contains `name` as a whole token."""
    return re.search(r'\bclass="[^"]*(?<![\w-])' + re.escape(name) + r'(?![\w-])[^"]*"', content) is not None


def button_markup(content: str, name: str) -> str:
    """Markup from the button carrying class `name` up to its closing tag."""
    match = re.search(r'class="[^"]*(?<![\w-])' + re.escape(name) + r'(?![\w-])[^"]*"', content)
    assert match, f"no element with class {name}"
    return content[match.end():].split("</button>")[0]


def test_transactions_vue_has_recurring_header_button():
    content = TRANSACTIONS_VUE.read_text(encoding="utf-8")
    assert has_class(content, "btn-recurring-matches")
    assert 'toggleRecurringPanel' in content
    assert 'aria-label="View and manage recurring activity"' in content
    assert "Recurring" in content


def test_transactions_vue_has_recurring_panel():
    content = TRANSACTIONS_VUE.read_text(encoding="utf-8")
    assert has_class(content, "recurring-panel")
    assert 'aria-label="Recurring activity review"' in content
    assert 'role="tablist"' in content
    assert 'Confirm genuine items' in content
    assert 'class="recurring-table"' in content


def test_transactions_vue_has_recurring_actions_and_labels():
    content = TRANSACTIONS_VUE.read_text(encoding="utf-8")
    assert 'confirmRecurring(item)' in content
    assert 'dismissRecurring(item)' in content
    assert 'aria-label="`Confirm recurring pattern for ${item.merchant}`"' in content
    assert 'aria-label="`Dismiss recurring pattern for ${item.merchant}`"' in content
    assert has_class(content, "confirm-btn")
    assert has_class(content, "dismiss-btn")
    # Plain text action labels without emojis
    rec_btn_section = button_markup(content, "btn-recurring-matches")
    assert "Recurring" in rec_btn_section
    assert "🔄" not in rec_btn_section


def test_transactions_vue_has_recurring_tag_in_ledger():
    content = TRANSACTIONS_VUE.read_text(encoding="utf-8")
    assert has_class(content, "recurring-tag")
    assert "Recurring · {{ getRecurringCadenceForTx(tx) }}" in content
    assert "getRecurringCadenceForTx" in content


def test_transactions_vue_has_clean_accessibility_and_no_emoji_only():
    content = TRANSACTIONS_VUE.read_text(encoding="utf-8")
    # Must have descriptive plain text, no emoji action labels
    assert "Recurring Activity" in content
    assert "Recurring ·" in content
    rec_table = content.split('class="recurring-table"')[1].split('</table>')[0]
    assert "Confirm" in rec_table
    assert "Dismiss" in rec_table
    assert "✓ Confirm" not in rec_table
    assert "✕ Dismiss" not in rec_table
