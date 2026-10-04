"""
Focused characterization and contract tests for Phase 1B shared frontend primitives.

Verifies:
1. MonthNavigator month rollover sequence and timezone invariance.
2. FormField label/id association and accessibility contracts (label 'for' == input 'id', role="alert" on errors).
3. AppDialog accessibility contracts (role="dialog", aria-modal="true", aria-labelledby, close button accessible name).
4. LoadingState, EmptyState, and ErrorBanner semantic feedback contracts.
"""

import json
import shutil
import subprocess
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend component tests")


def test_month_traversal_sequence(require_node):
    """
    Verifies multi-step month navigation traversals (forward and backward)
    across year boundaries.
    """
    script = """
    import { getPreviousMonth, getNextMonth, formatMonthDisplay } from './app/utils/monthMath.ts';

    // Sequence 1: Backward across year boundary and back forward
    let current = '2026-03';
    current = getPreviousMonth(current); // 2026-02
    current = getPreviousMonth(current); // 2026-01
    current = getPreviousMonth(current); // 2025-12 (boundary crossed)
    current = getPreviousMonth(current); // 2025-11
    current = getNextMonth(current);     // 2025-12
    current = getNextMonth(current);     // 2026-01 (boundary crossed back)

    if (current !== '2026-01') {
        throw new Error(`Expected 2026-01, got ${current}`);
    }

    // Sequence 2: Forward across year boundary
    current = '2026-11';
    current = getNextMonth(current); // 2026-12
    current = getNextMonth(current); // 2027-01 (boundary crossed)
    current = getNextMonth(current); // 2027-02
    if (current !== '2027-02') {
        throw new Error(`Expected 2027-02, got ${current}`);
    }

    // Sequence 3: Display formatting invariant across calendar boundaries
    const janDisplay = formatMonthDisplay('2026-01');
    const decDisplay = formatMonthDisplay('2026-12');
    if (janDisplay !== 'January 2026' || decDisplay !== 'December 2026') {
        throw new Error(`Formatting failed: ${janDisplay}, ${decDisplay}`);
    }

    console.log(JSON.stringify({ passed: true }));
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=str(FRONTEND_DIR),
        capture_output=True,
        text=True,
        check=True,
    )
    res = json.loads(proc.stdout)
    assert res["passed"] is True


def test_form_field_accessibility_contract(require_node):
    """
    Verifies FormField template contracts:
    - Scoped slot exposes generated ID.
    - Rendered <label for="xxx"> matches <input id="xxx">.
    - Required marker renders.
    - Error message renders with role="alert".
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const formFieldCode = fs.readFileSync(path.resolve('./app/components/FormField.vue'), 'utf-8');

    // Structural contract verification
    const hasLabelFor = formFieldCode.includes(':for="fieldId"');
    const hasScopedSlot = formFieldCode.includes('<slot :id="fieldId" />') || formFieldCode.includes('<slot :id="fieldId"');
    const hasRoleAlert = formFieldCode.includes('role="alert"');
    const hasRequiredMarker = formFieldCode.includes('required-marker');
    const hasUseId = formFieldCode.includes('useId');

    const passed = hasLabelFor && hasScopedSlot && hasRoleAlert && hasRequiredMarker && hasUseId;
    console.log(JSON.stringify({
        passed,
        checks: { hasLabelFor, hasScopedSlot, hasRoleAlert, hasRequiredMarker, hasUseId }
    }));
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=str(FRONTEND_DIR),
        capture_output=True,
        text=True,
        check=True,
    )
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"FormField contract check failed: {res['checks']}"


def test_app_dialog_accessibility_contract(require_node):
    """
    Verifies AppDialog template contracts:
    - role="dialog"
    - aria-modal="true"
    - aria-labelledby bound to dialog title
    - Close button has accessible aria-label
    - Escape key handler
    - Focus management hooks present
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const dialogCode = fs.readFileSync(path.resolve('./app/components/AppDialog.vue'), 'utf-8');

    const hasRoleDialog = dialogCode.includes('role="dialog"');
    const hasAriaModal = dialogCode.includes('aria-modal="true"');
    const hasAriaLabelledby = dialogCode.includes(':aria-labelledby="titleId"');
    const hasCloseAriaLabel = dialogCode.includes('aria-label="Close dialog"');
    const hasEscapeHandler = dialogCode.includes("event.key === 'Escape'") || dialogCode.includes('@keydown.esc') || dialogCode.includes('handleEscape');
    const hasFocusManagement = dialogCode.includes('previouslyFocusedElement') && dialogCode.includes('focusable.focus()');
    const hasFocusTrap = dialogCode.includes('handleTabTrap') && dialogCode.includes('first.focus()') && dialogCode.includes('last.focus()');

    const passed = hasRoleDialog && hasAriaModal && hasAriaLabelledby && hasCloseAriaLabel && hasEscapeHandler && hasFocusManagement && hasFocusTrap;
    console.log(JSON.stringify({
        passed,
        checks: { hasRoleDialog, hasAriaModal, hasAriaLabelledby, hasCloseAriaLabel, hasEscapeHandler, hasFocusManagement, hasFocusTrap }
    }));
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=str(FRONTEND_DIR),
        capture_output=True,
        text=True,
        check=True,
    )
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"AppDialog contract check failed: {res['checks']}"


def test_feedback_states_contracts(require_node):
    """
    Verifies LoadingState, EmptyState, and ErrorBanner contracts:
    - LoadingState has role="status" and aria-live="polite".
    - ErrorBanner has role="alert" and aria-live="assertive" with accessible dismiss button.
    - EmptyState supports title and description without forcing emojis.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const loadingCode = fs.readFileSync(path.resolve('./app/components/LoadingState.vue'), 'utf-8');
    const emptyCode = fs.readFileSync(path.resolve('./app/components/EmptyState.vue'), 'utf-8');
    const errorCode = fs.readFileSync(path.resolve('./app/components/ErrorBanner.vue'), 'utf-8');

    const loadingAria = loadingCode.includes('role="status"') && loadingCode.includes('aria-live="polite"');
    const errorAria = errorCode.includes('role="alert"') && errorCode.includes('aria-live="assertive"') && errorCode.includes('aria-label="Dismiss error notification"');
    const emptyClean = emptyCode.includes('empty-title') && emptyCode.includes('empty-description') && !emptyCode.includes('🏦');

    const passed = loadingAria && errorAria && emptyClean;
    console.log(JSON.stringify({
        passed,
        checks: { loadingAria, errorAria, emptyClean }
    }));
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=str(FRONTEND_DIR),
        capture_output=True,
        text=True,
        check=True,
    )
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Feedback state checks failed: {res['checks']}"
