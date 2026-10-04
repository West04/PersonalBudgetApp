"""
Focused characterization and unit tests for Dashboard presentation calculations (dashboardMath.ts).

Verifies:
1. Cash / Depository aggregation (only active depository accounts, excludes credit/loans/investments).
2. Credit card debt presentation:
   - Positive balance_owed formatted as "$X.XX owed".
   - Negative balance_owed formatted as "$X.XX credit", NEVER "-$X.XX owed".
   - Zero balance_owed formatted as "$0.00".
3. Aggregate Financial Position:
   - Cash / Depository.
   - Credit Card Debt (handles net debt or net credit).
   - Net Position = Cash / Depository - Net Credit Balance.
4. Spending by group calculations:
   - Under budget / on track: calculates remaining and progress percentage.
   - Over budget: calculates overAmount, caps progress bar at 100%, sets isOverBudget=true.
   - Unbudgeted: handles planned = 0 with actual > 0.
5. Derivable budget attention:
   - Detects over-budget groups.
   - Detects positive and negative to_be_assigned.
   - Returns empty list when everything is on track and balanced.
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
        pytest.skip("Node.js not available to execute frontend dashboard math tests")


def test_format_card_balance_semantics(require_node):
    """
    Verifies that credit card balances are never presented as negative debt.
    - Positive balance => "$X.XX owed"
    - Negative balance => "$X.XX credit"
    - Zero => "$0.00"
    """
    script = """
    import { formatCardBalance } from './frontend/app/utils/dashboardMath.ts';

    const cases = [
        { input: 842.16, expectedLabel: '$842.16 owed', isOwed: true, isCredit: false },
        { input: '842.16', expectedLabel: '$842.16 owed', isOwed: true, isCredit: false },
        { input: -178.16, expectedLabel: '$178.16 credit', isOwed: false, isCredit: true },
        { input: '-178.16', expectedLabel: '$178.16 credit', isOwed: false, isCredit: true },
        { input: 0, expectedLabel: '$0.00', isOwed: false, isCredit: false },
        { input: '0.00', expectedLabel: '$0.00', isOwed: false, isCredit: false },
        { input: null, expectedLabel: '$0.00', isOwed: false, isCredit: false },
    ];

    const failures = [];
    for (const c of cases) {
        const res = formatCardBalance(c.input);
        if (res.displayLabel !== c.expectedLabel || res.isOwed !== c.isOwed || res.isCredit !== c.isCredit) {
            failures.push({ input: c.input, expected: c, actual: res });
        }
        if (res.displayLabel.includes('-$') || res.displayLabel.includes('- $')) {
            failures.push({ input: c.input, error: 'Contains negative sign in label', label: res.displayLabel });
        }
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Card balance formatting failures: {res['failures']}"


def test_summarize_financial_position(require_node):
    """
    Verifies Financial Position aggregation:
    - Cash/Depository sums only active depository accounts.
    - Credit Card Debt derives from credit card summary items.
    - Net Position = Depository - Net Credit Balance.
    """
    script = """
    import { summarizeFinancialPosition } from './frontend/app/utils/dashboardMath.ts';

    const accounts = [
        { account_id: 'a1', name: 'USAA Checking', type: 'depository', subtype: 'checking', current_balance: 4281.00, is_active: true },
        { account_id: 'a2', name: 'USAA Savings', type: 'depository', subtype: 'savings', current_balance: 8199.00, is_active: true },
        { account_id: 'a3', name: 'Closed Savings', type: 'depository', subtype: 'savings', current_balance: 5000.00, is_active: false },
        { account_id: 'a4', name: 'Brokerage', type: 'investment', subtype: 'brokerage', current_balance: 50000.00, is_active: true },
        { account_id: 'a5', name: 'Auto Loan', type: 'loan', subtype: 'auto', current_balance: -15000.00, is_active: true },
    ];

    const creditCards = [
        { account_id: 'c1', account_name: 'Discover', balance_owed: 842.16 },
    ];

    // Standard case: Cash = 4281 + 8199 = 12480.00. Credit Debt = 842.16. Net = 11637.84.
    const res1 = summarizeFinancialPosition(accounts, creditCards);
    const failures = [];

    if (Math.abs(res1.depositoryBalance - 12480.00) > 0.001) {
        failures.push({ test: 'depositoryBalance', expected: 12480.00, actual: res1.depositoryBalance });
    }
    if (res1.depositoryCount !== 2) {
        failures.push({ test: 'depositoryCount', expected: 2, actual: res1.depositoryCount });
    }
    if (Math.abs(res1.creditCardDebt - 842.16) > 0.001) {
        failures.push({ test: 'creditCardDebt', expected: 842.16, actual: res1.creditCardDebt });
    }
    if (res1.creditDisplayLabel !== '$842.16') {
        failures.push({ test: 'creditDisplayLabel', expected: '$842.16', actual: res1.creditDisplayLabel });
    }
    if (Math.abs(res1.netPosition - 11637.84) > 0.001) {
        failures.push({ test: 'netPosition', expected: 11637.84, actual: res1.netPosition });
    }

    // Overpayment edge case: Credit card has negative balance_owed (-200.00)
    const overpaidCards = [
        { account_id: 'c1', account_name: 'Discover', balance_owed: -200.00 },
    ];
    const res2 = summarizeFinancialPosition(accounts, overpaidCards);

    if (res2.hasCreditBalance !== true) {
        failures.push({ test: 'overpaid hasCreditBalance', expected: true, actual: res2.hasCreditBalance });
    }
    if (res2.creditDisplayLabel !== '$200.00 credit') {
        failures.push({ test: 'overpaid creditDisplayLabel', expected: '$200.00 credit', actual: res2.creditDisplayLabel });
    }
    if (res2.creditDisplayLabel.includes('-$')) {
        failures.push({ test: 'overpaid no negative string', actual: res2.creditDisplayLabel });
    }
    // Net Position with credit: Cash 12480 - (-200) = 12680
    if (Math.abs(res2.netPosition - 12680.00) > 0.001) {
        failures.push({ test: 'overpaid netPosition', expected: 12680.00, actual: res2.netPosition });
    }

    // Empty accounts and cards
    const res3 = summarizeFinancialPosition([], []);
    if (res3.depositoryBalance !== 0 || res3.creditCardDebt !== 0 || res3.netPosition !== 0) {
        failures.push({ test: 'empty summary', actual: res3 });
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Financial position calculation failures: {res['failures']}"


def test_calculate_group_spending(require_node):
    """
    Verifies Spending by Group presentation math:
    - On track: actual 620, planned 700 => remaining 80, isOverBudget false, percentage 88.57%
    - Over budget: actual 410, planned 350 => remaining -60, isOverBudget true, overAmount 60, percentage 100%
    - Unbudgeted: actual 50, planned 0 => isOverBudget true, overAmount 50, percentage 100%
    """
    script = """
    import { calculateGroupSpending } from './frontend/app/utils/dashboardMath.ts';

    const failures = [];

    // Case 1: Under budget
    const g1 = calculateGroupSpending(620, 700);
    if (g1.remaining !== 80 || g1.isOverBudget !== false || Math.abs(g1.percentage - 88.5714) > 0.01) {
        failures.push({ case: 'under budget', actual: g1 });
    }
    if (g1.statusLabel !== '$80.00 remaining') {
        failures.push({ case: 'under budget label', expected: '$80.00 remaining', actual: g1.statusLabel });
    }

    // Case 2: Over budget
    const g2 = calculateGroupSpending(410, 350);
    if (g2.remaining !== -60 || g2.isOverBudget !== true || g2.overAmount !== 60 || g2.percentage !== 100) {
        failures.push({ case: 'over budget', actual: g2 });
    }
    if (g2.statusLabel !== 'Over by $60.00') {
        failures.push({ case: 'over budget label', expected: 'Over by $60.00', actual: g2.statusLabel });
    }

    // Case 3: Unbudgeted with spending
    const g3 = calculateGroupSpending(50, 0);
    if (g3.isOverBudget !== true || g3.percentage !== 100 || g3.statusLabel !== '$50.00 spent (unbudgeted)') {
        failures.push({ case: 'unbudgeted', actual: g3 });
    }

    // Case 4: Zero spending and zero budget
    const g4 = calculateGroupSpending(0, 0);
    if (g4.isOverBudget !== false || g4.percentage !== 0 || g4.statusLabel !== 'No budget') {
        failures.push({ case: 'zero budget', actual: g4 });
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Group spending math failures: {res['failures']}"


def test_derivable_budget_attention(require_node):
    """
    Verifies that attention items only reflect derivable facts:
    - Over-budget groups surfaced.
    - to_be_assigned surfaced when non-zero.
    - Nothing surfaced when on track and zero remaining to assign.
    """
    script = """
    import { getDerivableBudgetAttention } from './frontend/app/utils/dashboardMath.ts';

    const groups = [
        { group_id: 'g1', name: 'Housing', planned: 1900, actual: 1800 },
        { group_id: 'g2', name: 'Food', planned: 700, actual: 620 },
        { group_id: 'g3', name: 'Transport', planned: 350, actual: 410 }, // Over by 60
    ];

    const failures = [];

    // Case 1: 1 over budget group + 250 unassigned
    const items1 = getDerivableBudgetAttention(groups, 250);
    if (items1.length !== 2) {
        failures.push({ case: 'items count', expected: 2, actual: items1.length });
    }
    const overItem = items1.find(i => i.type === 'over_budget');
    if (!overItem || overItem.message !== 'Transport is over budget by $60.00') {
        failures.push({ case: 'overItem', actual: overItem });
    }
    const tbaItem = items1.find(i => i.type === 'to_be_assigned');
    if (!tbaItem || tbaItem.message !== '$250.00 left to assign in budget') {
        failures.push({ case: 'tbaItem', actual: tbaItem });
    }

    // Case 2: No over budget groups and to_be_assigned is 0
    const onTrackGroups = [
        { group_id: 'g1', name: 'Housing', planned: 1900, actual: 1800 },
        { group_id: 'g2', name: 'Food', planned: 700, actual: 620 },
    ];
    const items2 = getDerivableBudgetAttention(onTrackGroups, 0);
    if (items2.length !== 0) {
        failures.push({ case: 'clean state should have 0 items', actual: items2 });
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Budget attention derivation failures: {res['failures']}"
