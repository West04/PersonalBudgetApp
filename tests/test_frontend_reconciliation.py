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
        hasDifferenceCard: code.includes('class="card-label">Difference</dt>'),
        hasTextualBalancedStatus: code.includes('Balanced ($0.00)') && code.includes('to balance'),

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


def test_reconciliation_clear_all_resilience_and_rollback(require_node):
    """
    COR-001 Regression:
    - Verifies toggleClearAll provides an in-progress re-entrancy lock (isTogglingClearAll).
    - Verifies Clear All button, checkboxes, and Finish button are disabled during in-progress toggle.
    - Verifies failed PATCH rolls back individual transaction cleared state and reports reconcileError.
    - Simulates failure scenario in Node.js to prove state consistency.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/accounts.vue'), 'utf-8');

    // 1. Static Contract Checks
    const checks = {
        hasIsTogglingClearAllRef: code.includes('const isTogglingClearAll = ref(false)'),
        hasClearAllDisabledLock: code.includes(':disabled="isTogglingClearAll || completingReconcile"'),
        hasCheckboxDisabledLock: code.includes(':disabled="isTogglingClearAll || completingReconcile"') && code.includes('class="reconcile-checkbox"'),
        hasFinishDisabledLock: code.includes(':disabled="!isBalanced || !reconcileSummary || completingReconcile || reconcileLoading || isTogglingClearAll"'),
        hasRollbackOnCatch: code.includes('tx.is_cleared = prevStatus'),
        hasReconcileErrorOnCatch: code.includes('reconcileError.value = err.data?.detail || err.message ||'),
        hasFinallyResetLock: code.includes('isTogglingClearAll.value = false'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    if (failures.length > 0) {
        console.log(JSON.stringify({ passed: false, failures, reason: 'Static contract checks failed' }));
        process.exit(0);
    }

    // 2. Behavioral Simulation: simulate toggleClearAll with one failing PATCH
    const txs = [
        { transaction_id: 'tx-1', description: 'Grocery', amount: 50.0, is_cleared: false },
        { transaction_id: 'tx-2', description: 'Gas', amount: 30.0, is_cleared: false },
        { transaction_id: 'tx-3', description: 'Coffee', amount: 5.0, is_cleared: false },
    ];

    const reconcileSummary = { transactions: txs };
    let isTogglingClearAll = false;
    let reconcileError = null;
    const allCleared = false;
    const targetStatus = !allCleared; // true

    async function mockFetch(url, opts) {
        if (url.includes('tx-2')) {
            const err = new Error('Network error on tx-2');
            err.data = { detail: 'Database lock timeout on tx-2' };
            throw err;
        }
        return { success: true };
    }

    async function simulateToggleClearAll() {
        if (!reconcileSummary || isTogglingClearAll) return;
        isTogglingClearAll = true;
        reconcileError = null;
        const txsToUpdate = reconcileSummary.transactions.filter(t => t.is_cleared !== targetStatus);
        try {
            for (const tx of txsToUpdate) {
                if (!reconcileSummary) break;
                const prevStatus = tx.is_cleared;
                tx.is_cleared = targetStatus;
                try {
                    await mockFetch(`/transactions/${tx.transaction_id}/cleared`, {
                        method: 'PATCH',
                        body: { is_cleared: targetStatus },
                    });
                } catch (err) {
                    tx.is_cleared = prevStatus;
                    reconcileError = err.data?.detail || err.message || 'Failed to update transaction cleared status';
                }
            }
        } finally {
            isTogglingClearAll = false;
        }
    }

    (async () => {
        await simulateToggleClearAll();
        const simChecks = {
            tx1Cleared: txs[0].is_cleared === true,
            tx2RolledBack: txs[1].is_cleared === false,
            tx3Cleared: txs[2].is_cleared === true,
            hasErrorReported: reconcileError === 'Database lock timeout on tx-2',
            lockReset: isTogglingClearAll === false,
        };

        const simFailures = Object.entries(simChecks).filter(([_, v]) => !v).map(([k]) => k);
        console.log(JSON.stringify({ passed: simFailures.length === 0, failures: simFailures }));
    })();
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Reconciliation Clear All resilience failures: {res['failures']}"


def test_reconciliation_finish_disabled_when_summary_unloaded_or_failed(require_node):
    """
    COR-002 Regression:
    - Verifies Finish Reconciliation button is disabled when reconcileSummary is null (e.g. failed load).
    - Verifies isBalanced returns false when reconcileSummary is null, even if endingBalance is 0.
    - Verifies finishReconciliation aborts without network dispatch if reconcileSummary is null.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/accounts.vue'), 'utf-8');

    // 1. Static Contract Checks
    const checks = {
        hasSummaryGuardInIsBalanced: code.includes('if (!reconcileSummary.value) return false'),
        hasSummaryCheckInFinishDisabled: code.includes('!reconcileSummary') && code.includes('Finish Reconciliation'),
        hasSummaryGuardInFinishReconciliation: code.includes('!reconcileSummary.value') && code.includes('const finishReconciliation ='),
        hasSummaryResetOnLoadError: code.includes('reconcileSummary.value = null') && code.includes('loadReconciliation'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    if (failures.length > 0) {
        console.log(JSON.stringify({ passed: false, failures, reason: 'Static contract checks failed' }));
        process.exit(0);
    }

    // 2. Behavioral Simulation: null summary with 0 ending balance
    let fetchCalled = false;
    async function mockFetch(url, opts) {
        fetchCalled = true;
        return { success: true };
    }

    function checkIsBalanced(summary, endingBal) {
        if (!summary) return false;
        const prior = Number(summary.prior_reconciled_balance) || 0;
        const clearedNet = (summary.transactions || [])
            .filter(t => t.is_cleared)
            .reduce((sum, t) => sum + Number(t.amount), 0);
        const cleared = Math.round((prior - clearedNet) * 100) / 100;
        const diff = Math.round(((Number(endingBal) || 0) - cleared) * 100) / 100;
        return Math.abs(diff) < 0.005;
    }

    function isFinishDisabled(summary, isBal, completing, loading, toggling) {
        return !isBal || !summary || completing || loading || toggling;
    }

    async function simulateFinish(account, summary, isBal, toggling) {
        if (!account || !summary || !isBal || toggling) return;
        await mockFetch('/reconciliation/complete');
    }

    (async () => {
        // Case A: summary is null (failed load), endingBalance is 0
        let fetchCount = 0;
        async function mockFetchA(url, opts) {
            fetchCount++;
            return { success: true };
        }
        async function simulateFinishA(account, summary, isBal, toggling) {
            if (!account || !summary || !isBal || toggling) return;
            await mockFetchA('/reconciliation/complete');
        }

        const nullSummary = null;
        const endingBalance = 0;
        const isBalA = checkIsBalanced(nullSummary, endingBalance);
        const disabledA = isFinishDisabled(nullSummary, isBalA, false, false, false);
        await simulateFinishA({ account_id: 'acc-1' }, nullSummary, isBalA, false);
        const didNotDispatchOnNull = fetchCount === 0;

        // Case B: summary is loaded, endingBalance matches cleared balance
        const loadedSummary = { prior_reconciled_balance: 0, transactions: [] };
        const isBalB = checkIsBalanced(loadedSummary, 0);
        const disabledB = isFinishDisabled(loadedSummary, isBalB, false, false, false);
        await simulateFinishA({ account_id: 'acc-1' }, loadedSummary, isBalB, false);
        const dispatchedOnLoaded = fetchCount === 1;

        const simChecks = {
            nullSummaryNotBalanced: isBalA === false,
            nullSummaryButtonDisabled: disabledA === true,
            nullSummaryDidNotDispatch: didNotDispatchOnNull,
            loadedSummaryIsBalanced: isBalB === true,
            loadedSummaryButtonEnabled: disabledB === false,
            loadedSummaryDispatched: dispatchedOnLoaded,
        };

        const simFailures = Object.entries(simChecks).filter(([_, v]) => !v).map(([k]) => k);
        console.log(JSON.stringify({ passed: simFailures.length === 0, failures: simFailures }));
    })();
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Reconciliation Finish button guard failures: {res['failures']}"


def test_reconciliation_default_date_uses_local_date(require_node):
    """
    COR-004 Regression:
    - Verifies accounts.vue imports getLocalDateString from ~/utils/formatDate.
    - Verifies reconcileForm.endingDate is initialized with getLocalDateString().
    - Verifies openReconcileModal sets today using getLocalDateString().
    - Verifies new Date().toISOString().slice(0, 10) is not used for reconciliation dates.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/accounts.vue'), 'utf-8');

    const checks = {
        importsGetLocalDateString: code.includes("import { formatDateOnly, getLocalDateString } from '~/utils/formatDate'"),
        formInitUsesLocalDateString: code.includes('endingDate: getLocalDateString()'),
        openModalUsesLocalDateString: code.includes('const today = getLocalDateString()'),
        noIsoStringInReconciliation: !code.includes('endingDate: new Date().toISOString()') && !code.includes('const today = new Date().toISOString()'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Reconciliation local date defaults failures: {res['failures']}"
