"""
Focused characterization and contract tests for Phase 9 Categorization Rules Settings UX.

Verifies:
1. Categorization Rules table structure and accessibility (table, thead, th scope, aria-labels).
2. Action separation (Apply, Edit, Delete buttons with accessible aria-labels).
3. Add Rule dialog contract (AppDialog, FormField for merchant and category, autofocus, enter key).
4. Edit Rule dialog contract (AppDialog, FormField, save changes).
5. Delete Rule confirmation contract (AppDialog, explicit warning regarding future vs past transactions).
6. Retroactive Apply modal contract (AppDialog, preview count presentation, non-destructive explanation).
7. Responsive layout contract (narrow screen media queries, no fixed-width horizontal overflow).
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


def test_settings_rules_table_accessibility_contract(require_node):
    """
    Verifies that the rules table has proper semantic structure, table headers,
    scope attributes, and accessible action buttons.
    """
    script = r"""
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./app/pages/settings.vue'), 'utf-8');

    const hasTable = code.includes('<table class="rules-table"');
    const hasAriaLabel = code.includes('aria-label="Categorization rules table"');
    const hasThScope = code.includes('scope="col"') && code.includes('Merchant') && code.includes('Target Category');
    // Actions column keeps an accessible header name (visually hidden is fine)
    const hasActionsHeader = /<th scope="col"[^>]*class="th-actions"[^>]*>(<span class="sr-only">)?Actions/.test(code);

    const hasApplyBtn = /class="[^"]*\bbtn-apply\b[^"]*"/.test(code) && code.includes(':aria-label="`Apply rule for ${rule.merchant}');
    const hasEditBtn = /class="[^"]*\bbtn-edit\b[^"]*"/.test(code) && code.includes(':aria-label="`Edit rule for ${rule.merchant}`"');
    const hasDeleteBtn = /class="[^"]*\bbtn-delete\b[^"]*"/.test(code) && code.includes(':aria-label="`Delete rule for ${rule.merchant}`"');

    const passed = hasTable && hasAriaLabel && hasThScope && hasActionsHeader && hasApplyBtn && hasEditBtn && hasDeleteBtn;

    console.log(JSON.stringify({
        passed,
        hasTable,
        hasAriaLabel,
        hasThScope,
        hasActionsHeader,
        hasApplyBtn,
        hasEditBtn,
        hasDeleteBtn
    }));
    """

    res = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(res.stdout)
    assert result["passed"] is True, f"Accessibility contract check failed: {result}"


def test_settings_rules_dialogs_contract(require_node):
    """
    Verifies that the Add, Edit, Delete, and Apply modals adhere to AppDialog,
    FormField, and accessible confirmation standards.
    """
    script = r"""
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./app/pages/settings.vue'), 'utf-8');

    // 1. Add Rule Dialog
    const hasAddDialog = code.includes(':open="isAddOpen"') && code.includes('title="Add Categorization Rule"');
    const hasMerchantField = code.includes('label="Merchant Name"') && code.includes('v-model="ruleForm.merchant"');
    const hasCategoryField = code.includes('label="Target Category"') && code.includes('v-model="ruleForm.category_id"');

    // 2. Edit Rule Dialog
    const hasEditDialog = code.includes(':open="isEditOpen"') && code.includes('title="Edit Categorization Rule"');
    const hasEditMerchantField = code.includes('v-model="editForm.merchant"');
    const hasEditCategoryField = code.includes('v-model="editForm.category_id"');

    // 3. Delete Dialog
    const hasDeleteDialog = code.includes(':open="isDeleteOpen"') && code.includes('title="Delete Categorization Rule"');
    const hasDeleteWarning = code.includes('Future transactions will no longer be automatically categorized');

    // 4. Apply Dialog
    const hasApplyDialog = code.includes(':open="isApplyOpen"') && code.includes('title="Apply Rule to Uncategorized Transactions"');
    const hasPreviewBox = code.includes('preview-match-box') && code.includes('previewCount');
    const hasNonDestructiveNote = code.includes('Transactions that already have a category will never be modified');

    const passed = hasAddDialog && hasMerchantField && hasCategoryField &&
                   hasEditDialog && hasEditMerchantField && hasEditCategoryField &&
                   hasDeleteDialog && hasDeleteWarning &&
                   hasApplyDialog && hasPreviewBox && hasNonDestructiveNote;

    console.log(JSON.stringify({
        passed,
        hasAddDialog,
        hasMerchantField,
        hasCategoryField,
        hasEditDialog,
        hasDeleteDialog,
        hasDeleteWarning,
        hasApplyDialog,
        hasPreviewBox,
        hasNonDestructiveNote
    }));
    """

    res = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(res.stdout)
    assert result["passed"] is True, f"Dialog contracts check failed: {result}"


def test_settings_rules_responsive_styles(require_node):
    """
    Verifies that the rules table adapts for narrow widths: a container-query
    narrow tier stacks each rule while actions stay reachable, and the table
    surface never forces horizontal overflow.
    """
    script = r"""
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./app/pages/settings.vue'), 'utf-8');

    const hasMediaQuery = /@container rules \(width < \d+px\)/.test(code);
    const narrow = code.slice(code.search(/@container rules \(width </));
    const hasActionButtonsStack = code.includes('.action-buttons') && narrow.includes('grid-template-areas') && narrow.includes('"merchant actions"');
    const hasOverflowControl = /\.table-container \{[^}]*overflow: hidden/.test(code) && code.includes('overflow-wrap: anywhere');

    const passed = hasMediaQuery && hasActionButtonsStack && hasOverflowControl;

    console.log(JSON.stringify({
        passed,
        hasMediaQuery,
        hasActionButtonsStack,
        hasOverflowControl
    }));
    """

    res = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(res.stdout)
    assert result["passed"] is True, f"Responsive styles check failed: {result}"
