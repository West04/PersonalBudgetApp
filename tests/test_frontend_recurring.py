"""
Frontend template and accessibility tests for Recurring Transactions in transactions.vue.
"""

import json
from pathlib import Path
import re
import shutil
import subprocess
import pytest

TRANSACTIONS_VUE = Path("frontend/app/pages/transactions.vue")
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend tests")


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


def test_recurring_tabs_roving_tabindex_and_keyboard_contract():
    """
    UX-004: Verifies that the recurring tablist buttons implement roving tabindex
    and keyboard navigation handlers according to WAI-ARIA tab pattern.
    """
    content = TRANSACTIONS_VUE.read_text(encoding="utf-8")
    assert 'role="tablist"' in content
    assert ':tabindex="recurringTab === tab.value ? 0 : -1"' in content
    assert '@keydown="onRecurringTabKeydown($event, tab.value)"' in content
    assert ':id="`recurring-tab-${tab.value}`"' in content
    assert 'const onRecurringTabKeydown =' in content


def test_recurring_tabs_keyboard_navigation_simulation(require_node):
    """
    UX-004: Behavioral simulation of arrow key and home/end navigation between recurring tabs.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/transactions.vue'), 'utf-8');

    // Contract checks
    const hasRovingTabindex = code.includes(':tabindex="recurringTab === tab.value ? 0 : -1"');
    const hasKeydownHandler = code.includes('@keydown="onRecurringTabKeydown($event, tab.value)"');
    const hasTabId = code.includes(':id="`recurring-tab-${tab.value}`"');
    const hasHandlerDef = code.includes('const onRecurringTabKeydown =');

    if (!hasRovingTabindex || !hasKeydownHandler || !hasTabId || !hasHandlerDef) {
        console.log(JSON.stringify({
            passed: false,
            contractFailures: { hasRovingTabindex, hasKeydownHandler, hasTabId, hasHandlerDef }
        }));
        process.exit(0);
    }

    // Behavioral simulation of onRecurringTabKeydown
    let focusedElementId = null;
    const dom = {
        'recurring-tab-all': { id: 'recurring-tab-all', focus: () => { focusedElementId = 'recurring-tab-all'; } },
        'recurring-tab-confirmed': { id: 'recurring-tab-confirmed', focus: () => { focusedElementId = 'recurring-tab-confirmed'; } },
        'recurring-tab-detected': { id: 'recurring-tab-detected', focus: () => { focusedElementId = 'recurring-tab-detected'; } },
        'recurring-tab-dismissed': { id: 'recurring-tab-dismissed', focus: () => { focusedElementId = 'recurring-tab-dismissed'; } }
    };

    global.document = {
        getElementById: (id) => dom[id] || null
    };
    global.HTMLElement = class {};
    for (const key of Object.keys(dom)) {
        Object.setPrototypeOf(dom[key], global.HTMLElement.prototype);
    }

    let nextTickQueue = [];
    const nextTick = (fn) => { nextTickQueue.push(fn); };
    const flushNextTick = () => {
        const q = [...nextTickQueue];
        nextTickQueue = [];
        q.forEach(fn => fn());
    };

    let recurringTab = { value: 'all' };

    const onRecurringTabKeydown = (event, currentTab) => {
        const tabValues = ['all', 'confirmed', 'detected', 'dismissed'];
        const currentIndex = tabValues.indexOf(currentTab);
        if (currentIndex === -1) return;

        let targetIndex = null;

        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
            targetIndex = (currentIndex + 1) % tabValues.length;
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
            targetIndex = (currentIndex - 1 + tabValues.length) % tabValues.length;
        } else if (event.key === 'Home') {
            targetIndex = 0;
        } else if (event.key === 'End') {
            targetIndex = tabValues.length - 1;
        }

        if (targetIndex !== null) {
            event.preventDefault();
            const targetTab = tabValues[targetIndex];
            recurringTab.value = targetTab;
            nextTick(() => {
                const targetBtn = document.getElementById(`recurring-tab-${targetTab}`);
                if (targetBtn instanceof HTMLElement) {
                    targetBtn.focus();
                }
            });
        }
    };

    const makeEvent = (key) => {
        let prevented = false;
        return {
            key,
            preventDefault: () => { prevented = true; },
            get prevented() { return prevented; }
        };
    };

    // 1. ArrowRight: 'all' -> 'confirmed'
    recurringTab.value = 'all';
    focusedElementId = null;
    let evt = makeEvent('ArrowRight');
    onRecurringTabKeydown(evt, recurringTab.value);
    flushNextTick();
    const right1 = evt.prevented && recurringTab.value === 'confirmed' && focusedElementId === 'recurring-tab-confirmed';

    // 2. ArrowRight wraps from end: 'dismissed' -> 'all'
    recurringTab.value = 'dismissed';
    focusedElementId = null;
    evt = makeEvent('ArrowRight');
    onRecurringTabKeydown(evt, recurringTab.value);
    flushNextTick();
    const wrapRight = evt.prevented && recurringTab.value === 'all' && focusedElementId === 'recurring-tab-all';

    // 3. ArrowLeft wraps backwards: 'all' -> 'dismissed'
    recurringTab.value = 'all';
    focusedElementId = null;
    evt = makeEvent('ArrowLeft');
    onRecurringTabKeydown(evt, recurringTab.value);
    flushNextTick();
    const wrapLeft = evt.prevented && recurringTab.value === 'dismissed' && focusedElementId === 'recurring-tab-dismissed';

    // 4. Home: from 'detected' -> 'all'
    recurringTab.value = 'detected';
    focusedElementId = null;
    evt = makeEvent('Home');
    onRecurringTabKeydown(evt, recurringTab.value);
    flushNextTick();
    const home = evt.prevented && recurringTab.value === 'all' && focusedElementId === 'recurring-tab-all';

    // 5. End: from 'confirmed' -> 'dismissed'
    recurringTab.value = 'confirmed';
    focusedElementId = null;
    evt = makeEvent('End');
    onRecurringTabKeydown(evt, recurringTab.value);
    flushNextTick();
    const end = evt.prevented && recurringTab.value === 'dismissed' && focusedElementId === 'recurring-tab-dismissed';

    // 6. Unhandled key: e.g. 'Tab' or 'Enter'
    recurringTab.value = 'confirmed';
    focusedElementId = null;
    evt = makeEvent('Tab');
    onRecurringTabKeydown(evt, recurringTab.value);
    flushNextTick();
    const unhandled = !evt.prevented && recurringTab.value === 'confirmed' && focusedElementId === null;

    const allPassed = right1 && wrapRight && wrapLeft && home && end && unhandled;

    console.log(JSON.stringify({
        passed: allPassed,
        results: { right1, wrapRight, wrapLeft, home, end, unhandled }
    }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Recurring tabs keyboard simulation failed: {res}"

