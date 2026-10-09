"""
Frontend contract and accessibility tests for Phase 7 Account Reconciliation:
- Reconcile trigger button on depository accounts with accessible aria-label.
- Last reconciled date metadata presentation on account row.
- Reconciliation dialog structure with ending date, ending balance, summary cards, and transactions table.
- Accessible difference status presentation (textual, not color-only).
- Finish Reconciliation action disabled unless balanced.
- Immediate cleared-state toggle and cancellation semantics.
- Responsive design adaptation for narrow screens.
"""

import json
import shutil
import subprocess
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend accounts contract tests")


def test_accounts_reconciliation_ui_contract(require_node):
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/accounts.vue'), 'utf-8');

    const checks = {
        // 1. Entry point on depository accounts
        hasReconcileButton: code.includes('class="btn-reconcile"') && code.includes('openReconcileModal'),
        hasReconcileAriaLabel: code.includes(':aria-label="`Reconcile ${account.name}`"'),
        hasReconciledMeta: /class="[^"]*\\breconciled-meta\\b[^"]*"/.test(code) && code.includes('Last reconciled') && code.includes('Never reconciled'),

        // 2. Reconcile Dialog
        hasReconcileDialog: code.includes(':open="reconcileModalOpen"') && code.includes('Reconcile'),
        hasStatementEndingDateInput: code.includes('label="Statement Ending Date"') && code.includes('v-model="reconcileForm.endingDate"'),
        hasStatementEndingBalanceInput: code.includes('label="Statement Ending Balance ($)"') && code.includes('v-model.number="reconcileForm.endingBalance"'),

        // 3. Difference presentation (textual, not color-only)
        hasDifferenceCard: code.includes('class="card-label">Difference</div>'),
        hasTextualBalancedStatus: code.includes('✓ Balanced ($0.00)') && code.includes('to balance'),

        // 4. Eligible transactions & cleared controls
        hasClearedCheckbox: code.includes('class="reconcile-checkbox"') && code.includes('toggleTxCleared'),
        hasQuickClearAllButton: code.includes('toggleClearAll') && code.includes('Clear All'),

        // 5. Completion control
        hasFinishButton: code.includes('Finish Reconciliation') && code.includes(':disabled="!isBalanced'),
        hasCancelButton: code.includes('closeReconcileModal'),

        // 6. Responsive narrow screen rules
        hasResponsiveInputsGrid: code.includes('.reconcile-inputs-grid') && code.includes('grid-template-columns: 1fr;'),
        hasResponsiveSummaryStrip: code.includes('.reconcile-summary-strip') && code.includes('grid-template-columns: 1fr;'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Reconciliation UI contract failures: {res['failures']}"
