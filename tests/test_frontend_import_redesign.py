"""
Contract tests for the Import + Reconciliation redesign slice.

Import (pages/upload.vue):
1. Endpoints, methods, multipart field names, JSON payloads and stale-response
   guards are unchanged; accepted file type stays .csv.
2. The existing four-step sequence and its enable/disable rules are preserved.
3. The real file input has a label, a description and keyboard access; drag and
   drop is an addition, not the only way to choose a file (no clickable div).
4. Failures (inspect, save format, create account, preview) are rendered as
   errors, never as an empty preview; the empty-preview message only exists in
   the preview step, which is reached only after a successful preview.
5. The preview is a real table with explicit ARIA roles, container tiers in range
   syntax, and the Transactions sign convention (no red/green by sign).
6. Semantic tokens only: no hardcoded colors, legacy --color-* aliases, emoji or
   all-caps labels. One primary action per step.

Reconciliation (Accounts reconcile dialog):
7. Requests unchanged; a failed load is never shown as "nothing to reconcile" and
   figures that depend on loaded data are not shown as stand-in zeros.
8. The dialog styles use semantic tokens and restack narrow rows with ARIA roles.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UPLOAD = (REPO_ROOT / "frontend/app/pages/upload.vue").read_text()
TEMPLATE = UPLOAD[: UPLOAD.index('<script setup lang="ts">')]
SCRIPT = UPLOAD[UPLOAD.index('<script setup lang="ts">'): UPLOAD.index("</script>")]
STYLE = UPLOAD[UPLOAD.index("<style scoped>"):]

ACCOUNTS = (REPO_ROOT / "frontend/app/pages/accounts.vue").read_text()
ACC_TEMPLATE = ACCOUNTS[: ACCOUNTS.index("<script setup")]
ACC_SCRIPT = ACCOUNTS[ACCOUNTS.index("<script setup"): ACCOUNTS.index("</script>")]
ACC_STYLE = ACCOUNTS[ACCOUNTS.index("<style scoped>"):]
RECONCILE_TEMPLATE = ACC_TEMPLATE[ACC_TEMPLATE.index("<!-- Reconcile Account Dialog -->"):]
RECONCILE_STYLE = ACC_STYLE[ACC_STYLE.index(".reconcile-dialog-content {"):]

EMOJI = re.compile("[←-⇿☀-➿⬀-⯿\U0001F300-\U0001FAFF＋]")


def _section(step_heading_id):
    start = TEMPLATE.index(f'aria-labelledby="{step_heading_id}"')
    end = TEMPLATE.find('<section v-if="currentStep ===', start)
    return TEMPLATE[start: end if end != -1 else len(TEMPLATE)]


# --- Import: request contracts ---------------------------------------------------

def test_import_endpoints_methods_and_fields_unchanged():
    for fragment in [
        "fetch(`${API_BASE}/accounts/`)",
        "fetch(`${API_BASE}/accounts/`, {\n      method: 'POST',",
        "fetch(`${API_BASE}/upload/inspect`, {\n      method: 'POST',\n      body: form,",
        "fetch(`${API_BASE}/upload/formats`, {\n      method: 'POST',",
        "fetch(`${API_BASE}/upload/preview`, {\n      method: 'POST',\n      body: form,",
        "fetch(`${API_BASE}/upload/confirm`, {\n      method: 'POST',\n      body: form,",
    ]:
        assert fragment in SCRIPT, fragment
    # Multipart field names: inspect sends only the file; preview and confirm send three fields
    assert SCRIPT.count("form.append('file', file)") == 1
    assert SCRIPT.count("form.append('file', selectedFile.value)") == 2
    assert SCRIPT.count("form.append('account_id', selectedAccountId.value)") == 2
    assert SCRIPT.count("form.append('format', resolvedFormatId.value)") == 2
    assert SCRIPT.count("fetch(") == 6
    # Stale-response guards and the inspect-on-select sequence remain
    for guard in ["++inspectRequestGeneration", "++saveRequestGeneration", "++previewRequestGeneration"]:
        assert guard in SCRIPT
    assert "await runInspect(file)" in SCRIPT
    # Accepted type and the drop-time .csv check are unchanged
    assert 'accept=".csv"' in TEMPLATE
    assert "if (!file.name.endsWith('.csv'))" in SCRIPT
    # Import failure feedback is unchanged (native alert, pre-existing)
    assert SCRIPT.count("alert(`Import failed:") == 2


def test_import_payloads_unchanged():
    assert "name: mappingForm.value.name.trim()," in SCRIPT
    assert "status_column: mappingForm.value.status_column || null," in SCRIPT
    assert "date_format: mappingForm.value.date_format.trim()," in SCRIPT
    assert "starting_balance: Number(newAccount.value.starting_balance) || 0," in SCRIPT
    assert "current_balance: Number(newAccount.value.current_balance) || 0," in SCRIPT
    assert "currency: 'USD',\n        is_active: true," in SCRIPT


# --- Import: workflow ------------------------------------------------------------

def test_import_four_step_sequence_and_enable_rules_preserved():
    assert "const stepLabels = ['File', 'Account', 'Preview', 'Done']" in SCRIPT
    for heading in ["step-file-heading", "step-account-heading", "step-preview-heading", "step-done-heading"]:
        assert f'id="{heading}"' in TEMPLATE
    assert ':aria-current="currentStep === index + 1 ? \'step\' : undefined"' in TEMPLATE
    # Transitions
    assert '@click="currentStep = 2"' in TEMPLATE
    assert '@click="currentStep = 1"' in TEMPLATE
    assert "currentStep.value = 3" in SCRIPT and "currentStep.value = 4" in SCRIPT
    # Enable/disable rules
    assert ':disabled="!selectedFile || !resolvedFormatId || inspectLoading || saveLoading"' in TEMPLATE
    assert ":disabled=\"!selectedAccountId || selectedAccountId === '__new__' || previewing\"" in TEMPLATE
    assert ':disabled="preview.valid_rows === 0 || importing"' in TEMPLATE
    assert ':disabled="Boolean(mappingValidationError) || saveLoading"' in TEMPLATE
    assert ':disabled="!newAccount.name || creatingAccount"' in TEMPLATE
    assert ':disabled="formatSavedSuccess || saveLoading"' in TEMPLATE
    # Ambiguous formats still require an explicit choice
    assert '@click="selectAmbiguousFormat(fmt)"' in TEMPLATE
    assert 'name="ambiguousFormat"' in TEMPLATE


def test_import_one_primary_action_per_step():
    for heading in ["step-file-heading", "step-account-heading", "step-preview-heading", "step-done-heading"]:
        section = _section(heading)
        assert section.count("btn-primary") == 1, heading
    # Every step says whether it can continue / what continuing does
    for status in ["fileStepStatus", "accountStepStatus", "previewStepStatus"]:
        assert f"{{{{ {status} }}}}" in TEMPLATE


# --- Import: file selection --------------------------------------------------------

def test_file_input_is_labelled_and_keyboard_reachable():
    assert 'id="import-file-input"' in TEMPLATE
    assert TEMPLATE.count('for="import-file-input"') == 2  # empty drop label + "Change file"
    assert 'aria-describedby="import-file-help"' in TEMPLATE
    assert 'id="import-file-help"' in TEMPLATE
    # The input is visually hidden but focusable (never display:none) and its focus shows
    assert 'class="sr-only file-input"' in TEMPLATE
    assert ".file-input:focus-visible + .file-drop" in STYLE
    # No clickable div standing in for the input
    assert "fileInputRef?.click()" not in TEMPLATE
    assert '@drop.prevent="onDrop"' in TEMPLATE
    # Selected file is named and can be removed
    assert ':title="selectedFile.name"' in TEMPLATE
    assert '@click="clearFile"' in TEMPLATE


# --- Import: errors vs empty ---------------------------------------------------------

def test_import_failures_are_errors_not_empty_states():
    for err in ["inspectError", "saveError", "createAccountError", "parseError"]:
        assert re.search(rf'<ErrorBanner\s+v-if="{err}"', TEMPLATE), err
    # The empty-preview message lives only in the preview step
    preview = _section("step-preview-heading")
    assert "This file has no transaction rows." in preview
    assert TEMPLATE.count("This file has no transaction rows.") == 1
    # Error rows are labelled in text, not color alone
    assert "Can't read" in preview
    assert 'v-if="row.parse_error"' in preview


# --- Import: preview table --------------------------------------------------------

def test_preview_table_structure_and_sign_convention():
    preview = _section("step-preview-heading")
    assert '<table class="preview-table" role="table"' in preview
    for role in ['role="rowgroup"', 'role="row"', 'role="columnheader"', 'role="cell"']:
        assert role in preview
    assert ">Amount</th>" in preview
    # Transactions convention: inflows (negative) shown with +, tones by meaning
    assert ":class=\"Number(row.amount) < 0 ? 'money--inflow' : 'money--outflow'\"" in preview
    assert "return Number(amount) < 0 ? `+${text}` : text" in SCRIPT
    assert "formatMoney(amount, 'never')" in SCRIPT
    assert "amount--out" not in UPLOAD and "amount--in" not in UPLOAD
    # Container tiers in range syntax, one shared amount track
    assert "container: preview / inline-size" in STYLE
    assert "@container preview (width < 720px)" in STYLE
    assert "@container preview (width < 560px)" in STYLE
    assert re.search(r"@container preview \((?:max|min)-width", STYLE) is None
    assert ".col-amount { width: 136px; text-align: right; }" in STYLE


# --- Import: tokens and copy -------------------------------------------------------

def test_import_uses_semantic_tokens_only():
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", STYLE)
    assert "rgb(" not in STYLE and "rgba(" not in STYLE
    assert "--color-" not in UPLOAD
    assert "text-transform: uppercase" not in STYLE
    assert not EMOJI.search(TEMPLATE)
    assert 'class="import-page page-container"' in TEMPLATE
    assert "<PageHeader" in TEMPLATE and "<h1" not in TEMPLATE
    assert 'title="Import"' in TEMPLATE


def test_no_plaid_or_theme_ui_added():
    for text in [UPLOAD, RECONCILE_TEMPLATE]:
        assert "plaid" not in text.lower()
        assert "data-theme" not in text


# --- Reconciliation dialog ---------------------------------------------------------

def test_reconciliation_requests_unchanged():
    assert "`${API_BASE}/accounts/${reconcilingAccount.value.account_id}/reconciliation`" in ACC_SCRIPT
    assert "ending_date: reconcileForm.value.endingDate,\n          ending_balance: reconcileForm.value.endingBalance," in ACC_SCRIPT
    assert ACC_SCRIPT.count("`${API_BASE}/transactions/${tx.transaction_id}/cleared`") == 2
    assert "/reconciliation/complete`" in ACC_SCRIPT
    assert 'v-model="reconcileForm.endingDate"' in RECONCILE_TEMPLATE
    assert '@change="loadReconciliation"' in RECONCILE_TEMPLATE
    assert '@change="toggleTxCleared(tx)"' in RECONCILE_TEMPLATE
    assert '@click="toggleClearAll"' in RECONCILE_TEMPLATE
    assert ':disabled="!isBalanced || completingReconcile || reconcileLoading"' in RECONCILE_TEMPLATE


def test_reconciliation_load_error_is_not_empty_or_zero():
    loading = RECONCILE_TEMPLATE.index('<LoadingState v-if="reconcileLoading"')
    loaded = RECONCILE_TEMPLATE.index('v-else-if="reconcileSummary"')
    empty = RECONCILE_TEMPLATE.index("No unreconciled transactions dated on or before")
    assert loading < loaded < empty
    # Cleared balance and difference show a dash until the summary exists
    assert RECONCILE_TEMPLATE.count('<span v-else class="value-unavailable">—</span>') == 2
    assert '<Money v-if="reconcileSummary" :amount="calculatedClearedBalance" />' in RECONCILE_TEMPLATE
    assert '<Money v-if="reconcileSummary" :amount="differenceAmount" />' in RECONCILE_TEMPLATE


def test_reconciliation_status_text_and_rows():
    # Balanced / mismatch state is named in text
    assert "Balanced ($0.00)" in RECONCILE_TEMPLATE and "to balance" in RECONCILE_TEMPLATE
    assert not EMOJI.search(RECONCILE_TEMPLATE.replace("✕", ""))
    # Amounts follow the Transactions convention
    assert ":class=\"Number(tx.amount) < 0 ? 'money--inflow' : 'money--outflow'\"" in RECONCILE_TEMPLATE
    # Narrow rows restack with explicit roles
    assert '<table class="reconcile-table" role="table"' in RECONCILE_TEMPLATE
    assert 'class="reconcile-row"' in RECONCILE_TEMPLATE and 'role="cell"' in RECONCILE_TEMPLATE
    assert "@container reconcile (width < 480px)" in RECONCILE_STYLE


def test_reconciliation_styles_use_semantic_tokens():
    assert "--color-" not in RECONCILE_STYLE
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", RECONCILE_STYLE)
    assert "text-transform: uppercase" not in RECONCILE_STYLE
    # Cleared rows are not dimmed to look disabled
    assert ".row-cleared" not in RECONCILE_STYLE
    assert "opacity" not in RECONCILE_STYLE
