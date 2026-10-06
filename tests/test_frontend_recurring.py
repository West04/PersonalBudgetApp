"""
Frontend template and accessibility tests for Recurring Transactions in transactions.vue.
"""

from pathlib import Path
import pytest

TRANSACTIONS_VUE = Path("frontend/app/pages/transactions.vue")


def test_transactions_vue_has_recurring_header_button():
    content = TRANSACTIONS_VUE.read_text(encoding="utf-8")
    assert 'class="btn-recurring-matches"' in content
    assert 'toggleRecurringPanel' in content
    assert 'aria-label="View and manage recurring activity"' in content
    assert "Recurring" in content


def test_transactions_vue_has_recurring_panel():
    content = TRANSACTIONS_VUE.read_text(encoding="utf-8")
    assert 'class="recurring-panel card"' in content
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
    assert 'class="confirm-btn"' in content
    assert 'class="dismiss-btn"' in content
    # Plain text action labels without emojis
    rec_btn_section = content.split('class="btn-recurring-matches"')[1].split('</button>')[0]
    assert "Recurring" in rec_btn_section
    assert "🔄" not in rec_btn_section


def test_transactions_vue_has_recurring_tag_in_ledger():
    content = TRANSACTIONS_VUE.read_text(encoding="utf-8")
    assert 'class="recurring-tag font-mono"' in content
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
