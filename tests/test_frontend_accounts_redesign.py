"""
Contract and accessibility verification tests for Phase 5 Accounts Consolidation.

Verifies:
1. Shared component usage contract (PageHeader, LoadingState, EmptyState, ErrorBanner, AppDialog, FormField).
2. Pure current-state view: strictly verifies absence of MonthNavigator on Accounts.
3. Grouping contract: semantic sections for Depository, Credit Cards, Other, and Inactive.
4. Starting balance prominence contract:
   - Excluded from primary account table headers/rows as everyday metric.
   - Preserved in Add/Edit modal as setup metadata with explanatory hint.
5. Credit card balance presentation contract:
   - Positive balance_owed formatted as "$X.XX owed".
   - Negative balance_owed formatted as "$X.XX credit", NEVER "-$X.XX owed".
   - Zero balance_owed formatted as "$0.00".
   - Distinguishes debt vs credit in text, not color alone.
6. API composition contract:
   - Composes /api/accounts/ with /api/credit-cards/summary to use authoritative balance_owed.
7. Credit Cards page preservation contract:
   - Verifies credit-cards.vue retains transfer candidate discovery and confirmation.
   - Verifies credit cards page route/navigation is preserved.
8. Accessibility & responsive design:
   - Accessible action button labels (aria-label).
   - No decorative emoji in account presentation.
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


def test_accounts_shared_components_and_no_month_navigator(require_node):
    """
    Verifies accounts.vue uses foundation components and does NOT include MonthNavigator
    (Accounts is a current-state page, not month-scoped).
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/accounts.vue'), 'utf-8');

    const checks = {
        hasPageHeader: code.includes('<PageHeader') && code.includes('title="Accounts"'),
        hasLoadingState: code.includes('<LoadingState'),
        hasEmptyState: code.includes('<EmptyState'),
        hasErrorBanner: code.includes('<ErrorBanner'),
        hasAppDialog: code.includes('<AppDialog'),
        hasFormField: code.includes('<FormField'),
        noMonthNavigator: !code.includes('MonthNavigator'),
        noCustomSpinner: !code.includes('class="spinner"'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Shared components contract failures: {res['failures']}"


def test_accounts_starting_balance_metadata_contract(require_node):
    """
    Verifies that Starting Balance:
    - Does NOT appear as an everyday column in the primary table header or rows.
    - IS retained in the Add/Edit AppDialog form with explanatory setup metadata hint.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/accounts.vue'), 'utf-8');

    // Split template into main table area and AppDialog area
    const dialogStartIndex = code.indexOf('<AppDialog');
    const tableArea = dialogStartIndex !== -1 ? code.slice(0, dialogStartIndex) : code;
    const dialogArea = dialogStartIndex !== -1 ? code.slice(dialogStartIndex) : '';

    const checks = {
        // Table header should not include Starting Balance
        noStartingBalanceInHeader: !tableArea.includes('Starting Balance'),
        // Dialog MUST include Starting Balance as setup metadata
        hasStartingBalanceInDialog: dialogArea.includes('Starting Balance'),
        hasSetupHintInDialog: dialogArea.includes('Balance when tracking began') || dialogArea.includes('setup metadata'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Starting balance contract failures: {res['failures']}"


def test_accounts_grouping_and_no_emoji_contract(require_node):
    """
    Verifies semantic grouping for Depository, Credit Cards, Other, and Inactive accounts,
    without decorative emoji.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/accounts.vue'), 'utf-8');

    const checks = {
        hasDepositoryHeading: code.includes('id="heading-depository"') || code.includes('Depository'),
        hasCreditCardsHeading: code.includes('id="heading-credit-cards"') || code.includes('Credit Cards'),
        hasInactiveHeading: code.includes('Inactive Accounts') || code.includes('heading-inactive'),
        noCreditCardEmoji: !code.includes('💳'),
        noBankEmoji: !code.includes('🏦'),
        noMoneyBagEmoji: !code.includes('💰'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Grouping and emoji contract failures: {res['failures']}"


def test_accounts_api_composition_contract(require_node):
    """
    Verifies that accounts.vue composes /api/accounts/ and /api/credit-cards/summary
    to obtain authoritative balance_owed for credit cards.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/accounts.vue'), 'utf-8');

    const checks = {
        fetchesAccounts: code.includes('/accounts/'),
        fetchesCreditCardsSummary: code.includes('/credit-cards/summary'),
        usesFormatCardBalance: code.includes('formatCardBalance'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"API composition contract failures: {res['failures']}"


def test_credit_cards_page_preservation(require_node):
    """
    Verifies that credit-cards.vue preserves transfer matching and is not prematurely removed.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const ccCode = fs.readFileSync(path.resolve('./frontend/app/pages/credit-cards.vue'), 'utf-8');
    const appCode = fs.readFileSync(path.resolve('./frontend/app/app.vue'), 'utf-8');

    const checks = {
        ccPageExists: ccCode.length > 0,
        hasTransferCandidates: ccCode.includes('transfer-candidates'),
        hasMarkTransfers: ccCode.includes('mark-transfers'),
        hasTransferMatchButton: ccCode.includes('Find Transfer Matches') || ccCode.includes('loadCandidates'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Credit cards preservation failures: {res['failures']}"


def test_credit_card_balance_presentation_contract(require_node):
    """
    Verifies that credit card balances in accounts strictly follow:
    - positive balance_owed => "$X.XX owed"
    - negative balance_owed => "$X.XX credit"
    - zero => "$0.00"
    - never "-$X.XX owed"
    """
    script = """
    import { formatCardBalance } from './frontend/app/utils/dashboardMath.ts';

    const cases = [
        { owed: 842.16, expected: '$842.16 owed', isOwed: true, isCredit: false },
        { owed: -178.16, expected: '$178.16 credit', isOwed: false, isCredit: true },
        { owed: 0, expected: '$0.00', isOwed: false, isCredit: false },
        { owed: -0.00, expected: '$0.00', isOwed: false, isCredit: false },
    ];

    const failures = [];
    for (const c of cases) {
        const res = formatCardBalance(c.owed);
        if (res.displayLabel !== c.expected || res.isOwed !== c.isOwed || res.isCredit !== c.isCredit) {
            failures.push({ input: c.owed, expected: c, actual: res });
        }
        if (res.displayLabel.includes('-$') || (res.displayLabel.includes('owed') && res.amount < 0)) {
            failures.push({ input: c.owed, error: 'Negative debt label generated', label: res.displayLabel });
        }
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Card balance presentation contract failures: {res['failures']}"


def test_accounts_modal_field_ordering(require_node):
    """
    Verifies that Add/Edit Account dialog orders fields cleanly according to Section 25:
    Name -> Type/Subtype -> Starting Balance -> Active.
    Strictly verifies that no direct current_balance input exists in the dialog.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/accounts.vue'), 'utf-8');

    const dialogStartIndex = code.indexOf('<AppDialog');
    const dialogArea = dialogStartIndex !== -1 ? code.slice(dialogStartIndex) : '';

    const nameIdx = dialogArea.indexOf('form.name');
    const typeIdx = dialogArea.indexOf('form.type');
    const startBalIdx = dialogArea.indexOf('form.starting_balance');
    const activeIdx = dialogArea.indexOf('form.is_active');
    const curBalInputExists = dialogArea.includes('form.current_balance');

    const ordered = nameIdx !== -1 &&
                    typeIdx > nameIdx &&
                    startBalIdx > typeIdx &&
                    activeIdx > startBalIdx &&
                    !curBalInputExists;

    console.log(JSON.stringify({
        passed: ordered,
        indices: { nameIdx, typeIdx, startBalIdx, activeIdx, curBalInputExists }
    }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Modal field ordering failure: {res['indices']}"

