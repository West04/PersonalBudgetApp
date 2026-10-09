"""
Contract tests for the Budget page (/categories) visual redesign.

Verifies:
1. Summary figures come straight from the existing /summary/budget values, shown as
   the zero-based equation, with an explicit To Be Assigned state (not sign-inferred tone).
2. The ledger uses one shared column grid for group headers and category rows, with
   deliberate responsive tiers (stacked, compact, full) instead of squeezed flex rows.
3. Inline planned editing keeps the native input, Enter/Escape handlers and save path.
4. Status wording/tone uses the API's is_over_budget and category type; income remaining
   and inactive categories are never styled as errors.
5. The page calls exactly the same API endpoints as before the redesign.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / "frontend" / "app" / "pages" / "categories.vue"


def _source():
    code = PAGE.read_text()
    template = code[: code.index("<script")]
    script = code[code.index("<script") : code.index("<style")]
    style = code[code.index("<style") :]
    return code, template, script, style


def test_summary_is_zero_based_equation_from_api_values():
    _, template, script, _ = _source()

    # Values are the API's, unchanged
    for field in ("total_income_planned", "total_income_actual", "total_expense_planned",
                  "total_expense_actual", "to_be_assigned"):
        assert f"budgetSummary.value?.{field} ?? 0" in script, field

    assert '<dl class="budget-equation">' in template
    for binding in ("totalIncomePlanned", "totalExpensePlanned", "totalIncomeActual", "totalExpenseActual"):
        assert f'<Money :amount="{binding}" />' in template, binding

    # Planned income/expenses are planning totals: no success/warning colouring
    assert "summary-card income" not in template and "summary-card expense" not in template

    # To Be Assigned: explicit three-state contract with a caller-chosen tone and words
    assert "const tbaState = computed<'unassigned' | 'over' | 'assigned'>" in script
    assert ":tone=\"tbaState === 'over' ? 'overspent' : tbaState === 'unassigned' ? 'available' : 'neutral'\"" in template
    assert "Over-assigned" in template and "Left to assign" in template and "Every dollar has a job" in template


def test_ledger_shares_one_column_grid_with_responsive_tiers():
    _, template, _, style = _source()

    assert 'class="group-header ledger-grid"' in template
    assert 'class="category-row ledger-grid"' in template
    assert 'class="ledger-head ledger-grid"' in template
    for label in ("Planned", "Activity", "Remaining"):
        assert re.search(rf'<span class="col-\w+">{label}</span>', template), label

    # Container-query tiers, not a squeezed flex row
    assert "container: ledger / inline-size;" in style
    assert "@container ledger (max-width: 659px)" in style
    assert "@container ledger (min-width: 660px)" in style
    assert "@container ledger (min-width: 780px)" in style
    assert not re.search(r"\.category-row\s*\{[^}]*display:\s*flex", style)

    # Group totals sit in the same named columns as category figures
    for area in ("planned", "activity", "remaining"):
        assert f".cell-{area} {{ grid-area: {area}; }}" in style

    # Stacked tier labels each figure in place
    assert template.count('<span class="cell-label">Activity</span>') == 2
    assert template.count('<span class="cell-label">Remaining</span>') == 2

    # Groups are sections of one ledger, not separate shadowed cards
    assert 'class="group-section surface-card"' not in template
    assert "box-shadow: var(--shadow" not in style


def test_planned_inline_edit_contract_preserved():
    _, template, script, _ = _source()

    assert 'type="number"' in template and 'step="0.01"' in template and 'min="0"' in template
    assert '@change="onPlannedAmountChange(category, ($event.target as HTMLInputElement).value)"' in template
    assert '@keydown.enter="($event.target as HTMLInputElement).blur()"' in template
    assert '@keydown.escape="revertPlannedAmount(category, $event.target as HTMLInputElement)"' in template
    assert ':for="`planned-${category.category_id}`"' in template

    # Save path unchanged: parse, skip when equal, PUT existing budget or POST a new one
    assert "const amount = parseFloat(rawValue) || 0" in script
    assert "if (amount === current) return" in script
    assert "`${API_BASE}/budget/${budgetCat.budget_id}`" in script
    assert "budget_month: `${selectedMonth.value}-01`" in script

    # Escape restores the same formatted value the input displays
    assert "inputEl.value = formatPlannedInput(getCategoryPlanned(category))" in script
    assert ':value="formatPlannedInput(getCategoryPlanned(category))"' in template


def test_collapse_and_actions_accessibility():
    _, template, _, style = _source()

    assert '<h2 class="group-heading">' in template
    assert ':aria-expanded="!isGroupCollapsed(group.category_group_id)"' in template
    assert 'v-show="!isGroupCollapsed(group.category_group_id)"' in template
    for label in ("`Add category to ${group.name}`", "`Edit ${group.name} group`", "`Delete ${group.name} group`",
                  "`Edit ${category.name}`", "`Delete ${category.name}`"):
        assert f':aria-label="{label}"' in template, label

    # Actions stay visible (not hover-only)
    assert not re.search(r"\.(category|group)-actions\s*\{[^}]*(opacity:\s*0|visibility:\s*hidden)", style)

    # Progress meaning is carried by text; the bar is decorative
    assert 'class="progress-track"\n                          aria-hidden="true"' in template
    assert '<span class="status-text">{{ categoryStatus(category).label }}</span>' in template


def test_inactive_and_income_are_not_error_states():
    _, template, script, style = _source()

    assert "inactive-badge" not in template
    inactive_rules = re.findall(r"\.is-inactive[^{]*\{([^}]*)\}", style)
    assert inactive_rules, "inactive styling missing"
    for body in inactive_rules:
        assert "danger" not in body and "error" not in body and "overspent" not in body

    # Over-plan state comes from the API flag (false for income), not from the sign
    assert "!!getBudgetCategory(category.category_id)?.is_over_budget" in script
    assert "if (category.type === 'income') return 'neutral'" in script


def test_api_endpoints_unchanged():
    _, _, script, _ = _source()
    urls = sorted(set(re.findall(r"\$fetch(?:<[^>]+>)?\(`([^`]+)`", script)))
    assert urls == sorted([
        "${API_BASE}/budget/",
        "${API_BASE}/budget/${budgetCat.budget_id}",
        "${API_BASE}/categories",
        "${API_BASE}/categories/${categoryEditForm.value.id}",
        "${API_BASE}/categories/${category.category_id}",
        "${API_BASE}/categories/reorder",
        "${API_BASE}/category-groups",
        "${API_BASE}/category-groups/${group.category_group_id}",
        "${API_BASE}/category-groups/${groupEditForm.value.id}",
        "${API_BASE}/category-groups/reorder",
        "${API_BASE}/summary/budget",
    ]), urls


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend contract tests")


def test_category_status_states(require_node):
    """Executes the page's own status/tone helpers against representative budget rows."""
    _, _, script, _ = _source()
    start = script.index("const isCategoryOverBudget")
    end = script.index("</script>")
    helpers = re.sub(r"\): (\{[^=]*\}|MoneyTone|boolean) =>", ") =>", script[start:end])
    helpers = re.sub(r"type CategoryStatusKind = [^\n]*\n", "", helpers)
    helpers = helpers.replace("(category: Category)", "(category)")
    calc = script[script.index("const calculateProgress"):script.index("// --- Computed Summary Totals")]
    calc = calc.replace("(category: Category): number", "(category)")

    js = """
    const rows = {};
    const add = (id, type, planned, actual) => { rows[id] = { type, planned, actual, remaining: planned - actual,
      is_over_budget: type === 'income' ? false : planned - actual < 0 }; return { category_id: id, type }; };
    const getBudgetCategory = (id) => rows[id] || null;
    const getCategoryPlanned = (c) => rows[c.category_id].planned;
    const getCategoryActual = (c) => rows[c.category_id].actual;
    const getCategoryRemaining = (c) => rows[c.category_id].remaining;
    """ + calc + helpers + """
    const cases = {
      within: add('a', 'expense', 250, 212),
      full: add('b', 'expense', 100, 100),
      over: add('c', 'expense', 150, 180),
      refund: add('d', 'expense', 200, -35),
      unplanned: add('e', 'expense', 0, 64.5),
      none: add('f', 'expense', 0, 0),
      incomePartial: add('g', 'income', 4000, 3000),
      incomeAbove: add('h', 'income', 100, 300),
      transferIn: add('i', 'transfer', 300, -120),
    };
    const out = {};
    for (const [k, c] of Object.entries(cases)) {
      const s = categoryStatus(c);
      out[k] = { kind: s.kind, label: s.label, bar: s.showBar, rem: categoryRemainingTone(c), act: categoryActivityTone(c) };
    }
    console.log(JSON.stringify(out));
    """
    proc = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    assert out["within"] == {"kind": "within", "label": "85% spent", "bar": True, "rem": "available", "act": "neutral"}
    assert out["full"]["label"] == "Fully spent" and out["full"]["rem"] == "neutral"
    assert out["over"] == {"kind": "over", "label": "Over plan", "bar": True, "rem": "overspent", "act": "neutral"}
    # Refunds read as money coming back, never as an error or a broken bar
    assert out["refund"] == {"kind": "refund", "label": "Net refund", "bar": False, "rem": "available", "act": "inflow"}
    assert out["unplanned"]["label"] == "Unplanned" and out["unplanned"]["bar"] is False
    assert out["unplanned"]["rem"] == "overspent"
    assert out["none"]["label"] == "No plan" and out["none"]["bar"] is False
    # Income: remaining is money still expected; above plan is not overspending
    assert out["incomePartial"]["label"] == "75% received" and out["incomePartial"]["rem"] == "neutral"
    assert out["incomeAbove"]["label"] == "Above plan" and out["incomeAbove"]["rem"] == "neutral"
    assert out["incomeAbove"]["act"] == "inflow"
    assert out["transferIn"]["label"] == "Net inflow"
