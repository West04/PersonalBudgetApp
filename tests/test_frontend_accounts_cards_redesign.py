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
