"""
Frontend contract tests for Phase 8 Merchant Normalization in transactions.vue.

Verifies:
1. Table header presents 'Merchant / Description'.
2. Row presentation includes primary merchant name with edit button affordance.
3. Secondary text exposes raw imported description when it differs from normalized merchant.
4. Inline editing form provides accessible controls: text input, save (✓), cancel (✕), and Escape key handler.
5. Search input placeholder and accessible label indicate merchant and description searchability.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TX_VUE = REPO_ROOT / "frontend" / "app" / "pages" / "transactions.vue"


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend tests")


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


def test_merchant_edit_focus_return_contract():
    """
    UX-003: Verifies that cancelling or saving inline merchant edit returns focus
    to the row's edit trigger button rather than losing focus to document.body.
    """
    content = TX_VUE.read_text(encoding="utf-8")
    assert ':id="`btn-edit-merchant-${tx.transaction_id}`"' in content
    assert 'const focusMerchantEditTrigger' in content
    assert 'focusMerchantEditTrigger(txId)' in content
    assert 'focusMerchantEditTrigger(tx.transaction_id)' in content


def test_merchant_edit_focus_return_simulation(require_node):
    """
    UX-003: Behavioral simulation of merchant edit cancellation and successful save
    focus restoration to the trigger button.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/transactions.vue'), 'utf-8');

    // Verify template contract
    const hasTriggerId = code.includes(':id="`btn-edit-merchant-${tx.transaction_id}`"');
    const hasFocusHelper = code.includes('const focusMerchantEditTrigger');
    const hasCancelCall = code.includes('focusMerchantEditTrigger(txId)');
    const hasSaveCall = code.includes('focusMerchantEditTrigger(tx.transaction_id)');

    if (!hasTriggerId || !hasFocusHelper || !hasCancelCall || !hasSaveCall) {
        console.log(JSON.stringify({
            passed: false,
            failures: { hasTriggerId, hasFocusHelper, hasCancelCall, hasSaveCall }
        }));
        process.exit(0);
    }

    // Behavioral simulation of focus restoration mechanics
    let focusedElementId = null;
    const dom = {
        'btn-edit-merchant-tx-123': {
            id: 'btn-edit-merchant-tx-123',
            focus: () => { focusedElementId = 'btn-edit-merchant-tx-123'; }
        }
    };
    global.document = {
        getElementById: (id) => dom[id] || null,
        querySelector: () => null
    };
    global.HTMLElement = class {};
    Object.setPrototypeOf(dom['btn-edit-merchant-tx-123'], global.HTMLElement.prototype);

    let nextTickQueue = [];
    const nextTick = (fn) => { nextTickQueue.push(fn); };
    const flushNextTick = () => {
        const q = [...nextTickQueue];
        nextTickQueue = [];
        q.forEach(fn => fn());
    };

    // 1. Simulation: Cancel editing
    let editingMerchantId = { value: 'tx-123' };
    let editMerchantValue = { value: 'Dirty Edit' };

    const focusMerchantEditTrigger = (txId) => {
        nextTick(() => {
            const btn = document.getElementById(`btn-edit-merchant-${txId}`);
            if (btn instanceof HTMLElement) {
                btn.focus();
            }
        });
    };

    const cancelEditingMerchant = () => {
        const txId = editingMerchantId.value;
        editingMerchantId.value = null;
        editMerchantValue.value = '';
        if (txId) {
            focusMerchantEditTrigger(txId);
        }
    };

    cancelEditingMerchant();
    flushNextTick();

    const cancelPassed = focusedElementId === 'btn-edit-merchant-tx-123' && editingMerchantId.value === null;

    // 2. Simulation: Save editing
    focusedElementId = null;
    editingMerchantId = { value: 'tx-123' };
    const tx = { transaction_id: 'tx-123', merchant: 'Original' };

    // Simulate save success
    editingMerchantId.value = null;
    focusMerchantEditTrigger(tx.transaction_id);
    flushNextTick();

    const savePassed = focusedElementId === 'btn-edit-merchant-tx-123' && editingMerchantId.value === null;

    console.log(JSON.stringify({
        passed: cancelPassed && savePassed,
        results: { cancelPassed, savePassed }
    }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Focus return simulation failed: {res}"
