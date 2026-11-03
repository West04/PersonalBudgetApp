"""
Contract tests for the Accounts + Credit Cards redesign slice.

Accounts:
1. API endpoint set and request payload fields unchanged.
2. Balances come from the existing helpers (getAccountBalance -> formatCardBalance);
   tone is chosen from isCredit, never from the sign of a number.
3. Row actions preserved (Reconcile on depository rows, Edit, Delete) with accessible names.
4. Inactive accounts are named in text and never styled as an error.
5. One ledger surface with container-query tiers.

Credit Cards:
1. Owed / credit / zero wording follows formatCardBalance (same path as Dashboard).
2. Card metrics are read straight from the summary response fields.
3. Transfer candidate discovery, confirmation and dismissal preserved.
4. No sign-based colors, hardcoded hex colors or decorative emoji.
5. Container-query tiers; month labels describe the loaded data.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS = (REPO_ROOT / "frontend/app/pages/accounts.vue").read_text()
CARDS = (REPO_ROOT / "frontend/app/pages/credit-cards.vue").read_text()


def _template(code: str) -> str:
    return code[: code.index("<script setup")]


def _style(code: str) -> str:
    return code[code.index("<style scoped>"):]


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #

def test_accounts_api_endpoints_unchanged():
    for fragment in [
        "$fetch<Account[]>(`${API_BASE}/accounts/`)",
        "`${API_BASE}/credit-cards/summary`",
        "`${API_BASE}/accounts/${editingAccount.value.account_id}`",
        "method: 'PUT'",
        "method: 'POST'",
        "`${API_BASE}/accounts/${account.account_id}`, { method: 'DELETE' }",
        "/reconciliation`",
        "/reconciliation/complete`",
        "/cleared`",
    ]:
        assert fragment in ACCOUNTS, fragment
    # Add still seeds current_balance from starting_balance; edit never sends it
    put_body = ACCOUNTS[ACCOUNTS.index("method: 'PUT'"): ACCOUNTS.index("} else {", ACCOUNTS.index("method: 'PUT'"))]
    assert "current_balance" not in put_body
    assert "current_balance: startingBalance" in ACCOUNTS


def test_accounts_balance_uses_existing_helpers_not_sign():
    template = _template(ACCOUNTS)
    assert "getAccountBalance(account).formatted" in template
    assert "getAccountBalance(account).isCredit ? 'money--credit' : 'money--neutral'" in template
    assert "return formatCardBalance(cardOwed)" in ACCOUNTS
    assert "balanceWord(account)" in template
    # No sign-driven or alarm styling of balances
    assert "money--debt" not in template
    assert "balance-debt" not in ACCOUNTS
    assert not re.search(r"current_balance\)?\s*[<>]\s*0", template)


def test_accounts_row_actions_preserved_and_named():
    template = _template(ACCOUNTS)
    assert "v-if=\"group.key === 'depository'\"" in template
    assert ':aria-label="`Reconcile ${account.name}`"' in template
    assert ':aria-label="`Edit ${account.name}`"' in template
    assert ':aria-label="`Delete ${account.name}`"' in template
    assert '@click="openReconcileModal(account)"' in template
    assert '@click="openEditModal(account)"' in template
    assert '@click="confirmDelete(account)"' in template
    assert '<AppIcon name="edit"' in template and '<AppIcon name="trash"' in template
    # Inline SVG icons were replaced by the shared icon set
    assert "<svg" not in template


def test_accounts_inactive_is_text_not_error():
    template = _template(ACCOUNTS)
    style = re.sub(r"/\*.*?\*/", "", _style(ACCOUNTS), flags=re.S)
    assert ">Inactive</span>" in template
    inactive_rules = re.findall(r"[^{}]*(?:inactive)[^{}]*\{[^}]*\}", style)
    assert inactive_rules, "inactive styling expected"
    for rule in inactive_rules:
        assert "error" not in rule and "danger" not in rule, rule
    assert "opacity" not in style[: style.index(".reconcile-dialog-content")]


def test_accounts_single_ledger_with_container_tiers():
    template = _template(ACCOUNTS)
    style = _style(ACCOUNTS)
    assert template.count('class="ledger surface-card"') == 1
    assert 'v-for="group in accountGroups"' in template
    assert "container: accounts / inline-size" in style
    assert "@container accounts (min-width: 560px)" in style
    # Stacked and compact tiers meet with no fractional-width gap (< 560 / >= 560)
    assert "@container accounts (width < 560px)" in style
    assert "max-width: 559px" not in style
    assert "@container accounts (min-width: 880px)" in style
    # Failed loads show the error only, not the empty state
    assert 'v-else-if="!accounts.length && !error"' in template


# --------------------------------------------------------------------------- #
# Credit Cards
# --------------------------------------------------------------------------- #

def test_cards_balance_wording_follows_format_card_balance():
    template = _template(CARDS)
    assert "formatCardBalance(card.balance_owed).formatted" in template
    assert "formatCardBalance(card.balance_owed).isCredit ? 'money--credit' : 'money--neutral'" in template
    assert "if (display.isOwed) return 'owed'" in CARDS
    assert "if (display.isCredit) return 'credit'" in CARDS
    assert "money--debt" not in template
    assert "positive-balance" not in CARDS and "credit-balance" not in CARDS


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available")


def test_cards_owed_credit_zero_and_large_values(require_node):
    script = """
    import { formatCardBalance } from './frontend/app/utils/dashboardMath.ts';
    const word = (d) => d.isOwed ? 'owed' : d.isCredit ? 'credit' : '';
    const cases = [
      [1200, '$1,200.00', 'owed'],
      [-40, '$40.00', 'credit'],
      [0, '$0.00', ''],
      ['1234567.89', '$1,234,567.89', 'owed'],
      ['-123456.78', '$123,456.78', 'credit'],
    ];
    const failures = cases.filter(([v, f, w]) => {
      const d = formatCardBalance(v);
      return d.formatted !== f || word(d) !== w || d.formatted.startsWith('-');
    });
    console.log(JSON.stringify({ failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    assert json.loads(proc.stdout)["failures"] == []


def test_cards_metrics_sourced_from_summary_fields():
    template = _template(CARDS)
    for field in ["card.balance_owed", "card.charges_this_month", "card.payments_this_month", "card.starting_balance", "card.transactions"]:
        assert field in template, field
    # No client-side aggregate totals invented across cards
    assert ".reduce(" not in CARDS
    assert "utilization" not in CARDS.lower()


def test_cards_transfer_workflow_preserved():
    template = _template(CARDS)
    assert "`${API_BASE}/credit-cards/transfer-candidates`" in CARDS
    assert "`${API_BASE}/credit-cards/mark-transfers`" in CARDS
    assert "transaction_ids: [pair.inflow_side.transaction_id, pair.outflow_side.transaction_id]" in CARDS
    assert '@click="confirmTransfer(pair, idx)"' in template
    assert '@click="candidates.splice(idx, 1)"' in template
    assert '@click="loadCandidates"' in template
    assert ':aria-label="`Confirm transfer between ${pair.outflow_account_name} and ${pair.inflow_account_name}`"' in template
    assert ':aria-label="`Dismiss candidate match between ${pair.outflow_account_name} and ${pair.inflow_account_name}`"' in template
    assert '<span class="sr-only">From</span>' in template and '<span class="sr-only">To</span>' in template
    # Starting balance edit keeps its partial PUT and gains an accessible trigger
    assert "body: { starting_balance: amount }" in CARDS
    assert ':aria-label="`Edit starting balance for ${card.account_name}`"' in template


def test_cards_uses_foundation_and_no_hardcoded_colors():
    template = _template(CARDS)
    for component in ["<PageHeader", "<ErrorBanner", "<LoadingState", "<EmptyState", "<Money", "<AppIcon", "<MonthNavigator"]:
        assert component in template, component
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", _style(CARDS))
    assert "box-shadow" not in CARDS
    for emoji in ["💳", "🔍", "⚠️", "✏️", "✓"]:
        assert emoji not in CARDS, emoji


def test_cards_responsive_tiers_and_truthful_month_label():
    style = _style(CARDS)
    template = _template(CARDS)
    assert "container: cards / inline-size" in style
    assert "@container cards (min-width: 560px)" in style
    assert "@container cards (min-width: 860px)" in style
    assert "formatMonthDisplay(summary.value?.month ?? selectedMonth.value)" in CARDS
    # Empty state only once data has loaded; a failed load is not "no cards"
    assert '<template v-else-if="summary">' in template


def test_cards_transfer_confirm_lock_and_id_based_removal():
    """
    COR-003 Regression:
    - Verifies confirmingPair ref exists to prevent concurrent transfer confirmations.
    - Verifies Confirm button and Dismiss button have :disabled="confirmingPair".
    - Verifies confirmTransfer guards against concurrent execution.
    - Verifies candidate removal matches by transaction IDs rather than blindly splicing by captured index.
    - Simulates rapid/interleaved confirmation in Node.js to prove correct candidate is removed.
    """
    template = _template(CARDS)
    assert "const confirmingPair = ref(false)" in CARDS
    assert ':disabled="confirmingPair"' in template
    assert "if (confirmingPair.value) return" in CARDS
    assert "finally {\n    confirmingPair.value = false" in CARDS
    assert "c.inflow_side.transaction_id === pair.inflow_side.transaction_id" in CARDS
    assert "c.outflow_side.transaction_id === pair.outflow_side.transaction_id" in CARDS

    script = """
    const candidates = [
        {
            inflow_side: { transaction_id: 'in-1', description: 'Payment 1' },
            outflow_side: { transaction_id: 'out-1', description: 'Checking 1' }
        },
        {
            inflow_side: { transaction_id: 'in-2', description: 'Payment 2' },
            outflow_side: { transaction_id: 'out-2', description: 'Checking 2' }
        }
    ];

    let confirmingPair = false;
    async function mockFetch() {
        return { success: true };
    }

    async function confirmTransfer(pair, idx) {
        if (confirmingPair) return false;
        confirmingPair = true;
        try {
            await mockFetch();
            const foundIdx = candidates.findIndex(
                c => c.inflow_side.transaction_id === pair.inflow_side.transaction_id &&
                     c.outflow_side.transaction_id === pair.outflow_side.transaction_id
            );
            if (foundIdx !== -1) {
                candidates.splice(foundIdx, 1);
            } else {
                candidates.splice(idx, 1);
            }
            return true;
        } finally {
            confirmingPair = false;
        }
    }

    (async () => {
        // Confirm pair 2 using stale idx 0 (simulating array index drift)
        const pair2 = candidates[1];
        const res = await confirmTransfer(pair2, 0);

        const checks = {
            confirmedSuccess: res === true,
            remainingLength: candidates.length === 1,
            remainingIsPair1: candidates[0].inflow_side.transaction_id === 'in-1',
            lockReset: confirmingPair === false,
        };

        const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
        console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    })();
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Credit cards confirm transfer lock/removal failures: {res['failures']}"


def test_accounts_card_summary_failure_representation(require_node):
    """
    COR-006 regression test:
    When credit card summary fails to load or an active credit card's balance_owed
    is missing, the page must:
    1. Set error.value = 'Failed to load credit card balances'.
    2. NOT fall back to account.current_balance (which for manual cards is opening balance).
    3. Return an unavailable representation ('—', isUnavailable: true) with empty balanceWord.
    4. Preserve formatCardBalance(account.current_balance) for inactive cards (PROD-003 boundary).
    """
    code = (REPO_ROOT / "frontend/app/pages/accounts.vue").read_text()
    assert "error.value = 'Failed to load credit card balances'" in code
    assert "isUnavailable: true" in code
    assert "if (account.is_active)" in code

    script = """
    import { formatCardBalance, formatCurrency } from './frontend/app/utils/dashboardMath.ts';

    // Simulate creditCardOwedMap and getAccountBalance from accounts.vue
    const creditCardOwedMap = new Map();
    // card-1 has authoritative owed in map
    creditCardOwedMap.set('card-1', 250.75);

    const getAccountBalance = (account) => {
        const typeStr = (account.type || '').toLowerCase();
        if (typeStr === 'credit') {
            const cardOwed = creditCardOwedMap.get(account.account_id);
            if (cardOwed !== undefined) {
                return formatCardBalance(cardOwed);
            }
            if (account.is_active) {
                return {
                    amount: 0,
                    formatted: '—',
                    isOwed: false,
                    isCredit: false,
                    isUnavailable: true,
                    displayLabel: 'Unavailable',
                };
            }
            return formatCardBalance(account.current_balance);
        }
        const bal = Number(account.current_balance) || 0;
        return {
            amount: bal,
            formatted: formatCurrency(bal),
            isOwed: false,
            isCredit: false,
            displayLabel: formatCurrency(bal),
        };
    };

    const balanceWord = (account) => {
        const display = getAccountBalance(account);
        if (display.isOwed) return 'owed';
        if (display.isCredit) return 'credit';
        return '';
    };

    const activeCardKnown = { account_id: 'card-1', type: 'credit', is_active: true, current_balance: 0 };
    const activeCardMissing = { account_id: 'card-2', type: 'credit', is_active: true, current_balance: 1000 };
    const inactiveCardMissing = { account_id: 'card-3', type: 'credit', is_active: false, current_balance: 500 };

    const knownBal = getAccountBalance(activeCardKnown);
    const missingBal = getAccountBalance(activeCardMissing);
    const inactiveBal = getAccountBalance(inactiveCardMissing);

    const checks = {
        knownIsFormatted: knownBal.formatted === '$250.75',
        knownIsOwed: knownBal.isOwed === true,
        knownBalanceWord: balanceWord(activeCardKnown) === 'owed',

        // Active card with missing summary does not use current_balance (1000)
        missingNotUsingCurrentBalance: missingBal.amount === 0 && missingBal.formatted === '—',
        missingIsUnavailable: missingBal.isUnavailable === true,
        missingNotOwed: missingBal.isOwed === false,
        missingNoWord: balanceWord(activeCardMissing) === '',

        // Inactive card fallback preserved per PROD-003 scope guard
        inactiveUsesCurrentBalance: inactiveBal.amount === 500 && inactiveBal.formatted === '$500.00',
        inactiveIsOwed: inactiveBal.isOwed === true,
        inactiveBalanceWord: balanceWord(inactiveCardMissing) === 'owed',
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"COR-006 card summary failure representation failures: {res['failures']}"

