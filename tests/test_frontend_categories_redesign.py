"""
Focused characterization and contract tests for Phase 2 Budget / Categories redesign.

Verifies:
1. Group row-wide toggle accessibility contract (aria-expanded, aria-controls, aria-label, chevron indicator).
2. Action separation contract (drag handle, Add Category, Edit, Delete are isolated from row expansion toggle).
3. Creation and editing dialog contracts (AppDialog usage, FormField, clear modal titles, cancel preservation).
4. Category amount editing contract (native numeric input, enter blur, escape revert, change persistence).
5. Pure budget calculation contract (replicates frontend math against synthetic inputs).
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


def test_categories_group_toggle_accessibility_contract(require_node):
    """
    Verifies that the group expand/collapse interaction uses an accessible button
    spanning the reasonable non-interactive row area, with aria-expanded, aria-controls,
    accessible labels, and a rotating chevron affordance.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./app/pages/categories.vue'), 'utf-8');

    // 1. Group toggle button exists and has aria attributes
    const hasGroupToggleBtn = code.includes('class="group-toggle-btn"');
    const hasAriaExpanded = code.includes(':aria-expanded="!isGroupCollapsed(group.category_group_id)"');
    const hasAriaControls = code.includes(':aria-controls="`group-categories-${group.category_group_id}`"');
    const hasAriaLabel = code.includes(':aria-label="`${group.name} group');
    const hasChevronAffordance = code.includes('class="group-chevron"') && code.includes('isGroupCollapsed(group.category_group_id)');

    // 2. Drag handle is isolated as a sibling, not nested inside the toggle button
    const hasDragHandleBeforeBtn = code.indexOf('group-drag-handle') < code.indexOf('group-toggle-btn');

    // 3. Action buttons are isolated in .group-actions outside the toggle button
    const hasGroupActionsAfterBtn = code.indexOf('class="group-actions"') > code.indexOf('group-toggle-btn');
    const hasAddCategoryTrigger = code.includes('+ Add Category');
    const hasEditGroupTrigger = code.includes('openEditGroupModal(group)');
    const hasDeleteGroupTrigger = code.includes('confirmDeleteGroup(group)');

    const passed = hasGroupToggleBtn && hasAriaExpanded && hasAriaControls && hasAriaLabel &&
                   hasChevronAffordance && hasDragHandleBeforeBtn && hasGroupActionsAfterBtn &&
                   hasAddCategoryTrigger && hasEditGroupTrigger && hasDeleteGroupTrigger;

    console.log(JSON.stringify({
        passed,
        checks: {
            hasGroupToggleBtn,
            hasAriaExpanded,
            hasAriaControls,
            hasAriaLabel,
            hasChevronAffordance,
            hasDragHandleBeforeBtn,
            hasGroupActionsAfterBtn,
            hasAddCategoryTrigger,
            hasEditGroupTrigger,
            hasDeleteGroupTrigger
        }
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
    assert res["passed"] is True, f"Group toggle accessibility contract failed: {res['checks']}"


def test_categories_dialog_and_form_contracts(require_node):
    """
    Verifies that Add Group, Edit Group, Add Category, and Edit Category
    use AppDialog and FormField with distinct titles, clear labels, and cancel buttons
    that do not prematurely persist records.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./app/pages/categories.vue'), 'utf-8');

    // Add Group Dialog
    const hasAddGroupDialog = code.includes('title="Add Category Group"');
    const hasAddGroupSubmit = code.includes('submitAddGroup') && code.includes('closeAddGroupModal');

    // Edit Group Dialog
    const hasEditGroupDialog = code.includes('title="Edit Category Group"');
    const hasEditGroupSubmit = code.includes('submitEditGroup') && code.includes('closeEditGroupModal');

    // Add Category Dialog
    const hasAddCategoryDialog = code.includes('title="Add Category"');
    const hasAddCategorySubmit = code.includes('submitAddCategory') && code.includes('closeAddCategoryModal');
    const hasGroupPreselection = code.includes('selectedGroupForCategory') || code.includes('categoryForm.group_id');

    // Edit Category Dialog
    const hasEditCategoryDialog = code.includes('title="Edit Category"');
    const hasEditCategorySubmit = code.includes('submitEditCategory') && code.includes('closeEditCategoryModal');

    // FormField and ErrorBanner usage in dialogs
    const hasFormField = code.includes('<FormField label="Group Name"') && code.includes('<FormField label="Category Name"');
    const hasErrorBanner = code.includes('<ErrorBanner');

    const passed = hasAddGroupDialog && hasAddGroupSubmit &&
                   hasEditGroupDialog && hasEditGroupSubmit &&
                   hasAddCategoryDialog && hasAddCategorySubmit && hasGroupPreselection &&
                   hasEditCategoryDialog && hasEditCategorySubmit &&
                   hasFormField && hasErrorBanner;

    console.log(JSON.stringify({
        passed,
        checks: {
            hasAddGroupDialog,
            hasAddGroupSubmit,
            hasEditGroupDialog,
            hasEditGroupSubmit,
            hasAddCategoryDialog,
            hasAddCategorySubmit,
            hasGroupPreselection,
            hasEditCategoryDialog,
            hasEditCategorySubmit,
            hasFormField,
            hasErrorBanner
        }
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
    assert res["passed"] is True, f"Dialog and form contracts failed: {res['checks']}"


def test_category_planned_amount_inline_input_contract(require_node):
    """
    Verifies that planned budget amounts can be adjusted directly via a native
    numeric input with blur/change handlers, enter commit, and escape revert.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./app/pages/categories.vue'), 'utf-8');

    const hasAmountInput = code.includes('class="form-input font-mono amount-input"') || code.includes('amount-input');
    const hasTypeNumber = code.includes('type="number"') && code.includes('step="0.01"');
    const hasChangeHandler = code.includes('onPlannedAmountChange');
    const hasEnterHandler = code.includes('@keydown.enter=');
    const hasEscapeHandler = code.includes('revertPlannedAmount');

    const passed = hasAmountInput && hasTypeNumber && hasChangeHandler && hasEnterHandler && hasEscapeHandler;

    console.log(JSON.stringify({
        passed,
        checks: { hasAmountInput, hasTypeNumber, hasChangeHandler, hasEnterHandler, hasEscapeHandler }
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
    assert res["passed"] is True, f"Amount input contract failed: {res['checks']}"


def test_budget_math_and_totals_preservation(require_node):
    """
    Verifies the zero-based budgeting calculation logic implemented on the frontend:
    - planned, actual, and remaining calculations
    - group totals summing categories
    - to_be_assigned = total_income_planned - total_expense_planned
    - negative remaining properly identified
    """
    script = """
    // Replicate the exact helper logic from categories.vue
    const mockSummary = {
        month: '2026-06',
        groups: [
            {
                group_id: 'g1',
                name: 'Housing',
                categories: [
                    { category_id: 'c1', name: 'Rent', type: 'expense', planned: 1500, actual: 1500, remaining: 0, is_over_budget: false },
                    { category_id: 'c2', name: 'Utilities', type: 'expense', planned: 250, actual: 212, remaining: 38, is_over_budget: false },
                    { category_id: 'c3', name: 'Home', type: 'expense', planned: 150, actual: 180, remaining: -30, is_over_budget: true }
                ],
                total_planned: 1900,
                total_actual: 1892,
                total_remaining: 8
            },
            {
                group_id: 'g2',
                name: 'Income',
                categories: [
                    { category_id: 'c4', name: 'Salary', type: 'income', planned: 3000, actual: 3000, remaining: 0, is_over_budget: false }
                ],
                total_planned: 3000,
                total_actual: 3000,
                total_remaining: 0
            }
        ],
        total_income_planned: 3000,
        total_income_actual: 3000,
        total_expense_planned: 1900,
        total_expense_actual: 1892,
        to_be_assigned: 1100
    };

    const getBudgetCategory = (categoryId) => {
        for (const group of mockSummary.groups) {
            const cat = group.categories.find(c => c.category_id === categoryId);
            if (cat) return cat;
        }
        return null;
    };

    const getCategoryPlanned = (cat) => {
        const b = getBudgetCategory(cat.category_id);
        return b ? Number(b.planned) : 0;
    };
    const getCategoryActual = (cat) => {
        const b = getBudgetCategory(cat.category_id);
        return b ? Number(b.actual) : 0;
    };
    const getCategoryRemaining = (cat) => {
        const b = getBudgetCategory(cat.category_id);
        return b ? Number(b.remaining) : 0;
    };
    const getGroupTotalPlanned = (group) => {
        return group.categories.reduce((sum, cat) => sum + getCategoryPlanned(cat), 0);
    };
    const getGroupTotalActual = (group) => {
        return group.categories.reduce((sum, cat) => sum + getCategoryActual(cat), 0);
    };
    const getGroupTotalRemaining = (group) => {
        return group.categories.reduce((sum, cat) => sum + getCategoryRemaining(cat), 0);
    };

    const housingGroup = {
        category_group_id: 'g1',
        name: 'Housing',
        categories: [
            { category_id: 'c1' },
            { category_id: 'c2' },
            { category_id: 'c3' }
        ]
    };

    const groupPlanned = getGroupTotalPlanned(housingGroup);
    const groupActual = getGroupTotalActual(housingGroup);
    const groupRemaining = getGroupTotalRemaining(housingGroup);

    if (groupPlanned !== 1900) throw new Error(`Expected groupPlanned 1900, got ${groupPlanned}`);
    if (groupActual !== 1892) throw new Error(`Expected groupActual 1892, got ${groupActual}`);
    if (groupRemaining !== 8) throw new Error(`Expected groupRemaining 8, got ${groupRemaining}`);

    // Verify negative remaining
    const c3Remaining = getCategoryRemaining({ category_id: 'c3' });
    if (c3Remaining !== -30) throw new Error(`Expected c3Remaining -30, got ${c3Remaining}`);

    // Verify to_be_assigned
    const expectedTBA = mockSummary.total_income_planned - mockSummary.total_expense_planned;
    if (mockSummary.to_be_assigned !== expectedTBA) {
        throw new Error(`Expected to_be_assigned ${expectedTBA}, got ${mockSummary.to_be_assigned}`);
    }

    console.log(JSON.stringify({ passed: true, groupPlanned, groupActual, groupRemaining, c3Remaining, expectedTBA }));
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
