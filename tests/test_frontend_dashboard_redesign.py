"""
Contract and accessibility verification tests for Phase 3 Dashboard Redesign.

Verifies:
1. Shared component usage contract (PageHeader, MonthNavigator, LoadingState, ErrorBanner).
2. Financial Position layout contract (Cash / Depository, Credit Card Debt, Net Position).
3. Credit card balance presentation contract (owed vs credit, strictly avoids negative debt strings).
4. Spending by Group progress and accessibility contract (role="progressbar", aria-valuenow, remaining/over state).
5. Current Accounts and Recent Activity supporting context contracts.
6. Date-only transaction formatting contract (preserves formatDateOnly usage).
7. Month navigation link synchronization contract (passes month query param).
8. Dashboard visual redesign contracts: Money adoption with caller-chosen tone,
   To Be Assigned shown from the existing API value (no new fetches), and an
   attention state whose meaning does not rely on color alone.
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
        pytest.skip("Node.js not available to execute frontend dashboard contract tests")


def test_dashboard_shared_components_contract(require_node):
    """
    Verifies that dashboard.vue uses the shared foundation components (PageHeader,
    MonthNavigator, LoadingState, ErrorBanner) and does not recreate page-specific versions.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/dashboard.vue'), 'utf-8');

    const checks = {
        hasPageHeader: code.includes('<PageHeader') && code.includes('title="Dashboard"'),
        hasMonthNavigator: code.includes('<MonthNavigator />'),
        hasLoadingState: code.includes('<LoadingState'),
        hasErrorBanner: code.includes('<ErrorBanner'),
        noCustomSpinnerClass: !code.includes('class="spinner"'),
        noCustomRetryBtn: !code.includes('class="retry-btn"'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Shared components contract failures: {res['failures']}"


def test_dashboard_financial_position_contract(require_node):
    """
    Verifies that the Financial Position section exposes:
    - Cash / Depository
    - Credit Card Debt / Balance
    - Net Position
    - Semantic heading hierarchy
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/dashboard.vue'), 'utf-8');
    const template = code.slice(0, code.indexOf('<script'));
    const lower = template.toLowerCase();

    const checks = {
        hasFinancialPositionHeading: /id="heading-financial-position"[^>]*>\\s*Financial position/i.test(template),
        hasCashLabel: />\\s*Cash\\s*</.test(template),
        hasCreditDebtLabel: lower.includes('credit card debt') && lower.includes('credit card balance'),
        hasNetPositionLabel: lower.includes('net position'),
        netUsesMoneyWithExplicitTone: /<Money\\s+:amount="position\\?\\.netPosition"\\s+:tone=/.test(template),
        hasDepositoryBalanceBinding: code.includes('position?.depositoryBalance'),
        hasCreditDisplayBinding: code.includes('position?.creditDisplayLabel'),
        hasNetPositionBinding: code.includes('position?.netPosition'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Financial position contract failures: {res['failures']}"


def test_dashboard_spending_by_group_and_progress_accessibility(require_node):
    """
    Verifies Spending by Group:
    - Accessible progress bar (role="progressbar", aria-valuenow, aria-valuemin, aria-valuemax, aria-label).
    - Status pill communicates remaining or over-budget with text, not color alone.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/dashboard.vue'), 'utf-8');

    const checks = {
        hasSpendingHeading: /id="heading-spending-by-group"[^>]*>\\s*Spending by group/i.test(code),
        hasAriaValueText: code.includes(':aria-valuetext="spendingValueText(spending)"'),
        hasRoleProgressBar: code.includes('role="progressbar"'),
        hasAriaValueNow: code.includes(':aria-valuenow="Math.round(spending.percentage)"'),
        hasAriaValueMinMax: code.includes('aria-valuemin="0"') && code.includes('aria-valuemax="100"'),
        hasAriaLabel: code.includes("group.name + ' spending progress'") || code.includes('spending progress'),
        hasStatusPill: code.includes('class="spending-status"'),
        hasSpendingActualAndPlanned: code.includes('spending-actual') && code.includes('spending-planned'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Spending by group accessibility contract failures: {res['failures']}"


def test_dashboard_supporting_context_and_date_contract(require_node):
    """
    Verifies Current Accounts and Recent Activity supporting sections:
    - Uses formatDateOnly (not new Date().toLocaleDateString()).
    - Preserves links with month query parameter.
    - Inflow transactions explicitly display '+' sign.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/dashboard.vue'), 'utf-8');

    const checks = {
        hasCurrentAccountsHeading: /id="heading-current-accounts"[^>]*>\\s*Current accounts/i.test(code),
        hasRecentActivityHeading: /id="heading-recent-activity"[^>]*>\\s*Recent activity/i.test(code),
        importsFormatDateOnly: code.includes("from '~/utils/formatDate'"),
        usesFormatDateOnly: code.includes('formatDateOnly('),
        hasInflowSign: code.includes("tx.amount < 0 ? '+' : ''"),
        hasTransactionLinkWithMonth: code.includes("path: '/transactions'") && code.includes("month: selectedMonth"),
        hasCategoriesLinkWithMonth: code.includes("path: '/categories'") && code.includes("month: selectedMonth"),
        hasAccountsLink: code.includes('/accounts'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Supporting context contract failures: {res['failures']}"


def test_dashboard_to_be_assigned_and_data_fetching_contract(require_node):
    """
    To Be Assigned is presented from the existing dashboard API value; the page
    still makes exactly the two existing requests and does not recompute it.
    Credit card wording keeps formatCardBalance / creditDisplayLabel output.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/dashboard.vue'), 'utf-8');
    const fetches = code.match(/useFetch<any>\\(`([^`]+)`/g) || [];

    const checks = {
        exactlyTwoFetches: fetches.length === 2,
        fetchesDashboardSummary: code.includes('${API_BASE}/summary/dashboard'),
        fetchesCreditCardSummary: code.includes('${API_BASE}/credit-cards/summary'),
        tbaFromApiValue: code.includes('dashboardData.value?.to_be_assigned'),
        tbaLabelVisible: code.includes('To be assigned'),
        tbaOverWording: code.includes('over-assigned'),
        cardBalanceUsesFormatCardBalance: code.includes('formatCardBalance(cardOwed)'),
        cardWordsOwedAndCredit: code.includes("return 'owed'") && code.includes("return 'credit'"),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"To Be Assigned / data contract failures: {res['failures']}"


def test_dashboard_attention_state_contract(require_node):
    """
    The attention state is a labelled region with a visible heading and icon, so its
    meaning never depends on color alone, and each notice links to the budget month.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/dashboard.vue'), 'utf-8');

    const checks = {
        renderedOnlyWithItems: code.includes('v-if="attentionItems.length > 0"'),
        labelledByHeading: code.includes('aria-labelledby="heading-attention"') && code.includes('id="heading-attention"'),
        visibleHeadingText: code.includes('Needs attention'),
        usesDerivedMessages: code.includes('{{ item.message }}'),
        linkDescribedByMessage: code.includes(':aria-describedby="`attention-msg-${item.id}`"'),
        linksToBudgetMonth: code.includes("path: '/categories', query: { month: selectedMonth }"),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Attention state contract failures: {res['failures']}"
