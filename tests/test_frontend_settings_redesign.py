"""
Contract tests for the Settings redesign slice.

1. Endpoint set, methods and request payloads unchanged; every mutation is an
   explicit dialog/button action (no autosave).
2. Validation (trimmed merchant + category required) and refresh-after-save preserved.
3. Failed loads are distinct from empty/default state: a failed rules fetch never
   shows "No categorization rules yet", a failed model-status fetch never shows
   placeholder counts as if they were real.
4. Page hierarchy: narrow page container, one h1 (PageHeader), labelled sections
   (rules, ML, appearance),
   rule actions inside the rules section, not the page header.
5. Shared primitives (.btn, .btn-icon, AppIcon, AppDialog, FormField, ErrorBanner);
   no page-local input styling, hardcoded colors, emoji or all-caps labels.
6. Status is named in text; success feedback uses an icon and text, not color alone.
7. One container-query tier in range syntax (no adjacent max/min gap).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS = (REPO_ROOT / "frontend/app/pages/settings.vue").read_text()
TEMPLATE = SETTINGS[: SETTINGS.index("<script setup")]
SCRIPT = SETTINGS[SETTINGS.index("<script setup"): SETTINGS.index("</script>")]
STYLE = SETTINGS[SETTINGS.index("<style scoped>"):]


def test_settings_endpoints_and_payloads_unchanged():
    for fragment in [
        "useFetch<any[]>(`${API_BASE}/category-groups`)",
        "useFetch<any[]>(`${API_BASE}/rules/`)",
        "useFetch<any>(`${API_BASE}/ml/status`)",
        "$fetch<any>(`${API_BASE}/ml/retrain?force=true`, {\n      method: 'POST',",
        "fetch(`${API_BASE}/rules/${rule.id}/preview`)",
        "fetch(`${API_BASE}/rules/`, {\n      method: 'POST',",
        "fetch(`${API_BASE}/rules/${selectedRule.value.id}`, {\n      method: 'PUT',",
        "fetch(`${API_BASE}/rules/${selectedRule.value.id}`, {\n      method: 'DELETE',",
        "fetch(`${API_BASE}/rules/${ruleId}/apply`, {\n      method: 'POST',",
        "merchant: ruleForm.merchant.trim(),\n        category_id: ruleForm.category_id,",
        "merchant: editForm.merchant.trim(),\n        category_id: editForm.category_id,",
    ]:
        assert fragment in SCRIPT, fragment
    # No autosave: no watchers or change handlers that issue requests
    assert "watch(" not in SCRIPT
    # The only change handler is the local theme preference, which issues no request
    start = TEMPLATE.index('aria-labelledby="heading-appearance"')
    appearance = TEMPLATE[start: TEMPLATE.index("</section>", start)]
    assert re.findall(r'@change="[^"]*"', appearance) == ['@change="setThemePreference(option.value)"']
    rest = TEMPLATE.replace(appearance, "")
    assert "@change" not in rest and "@input" not in rest


def test_settings_validation_and_refresh_preserved():
    assert "ruleForm.merchant.trim().length > 0 && !!ruleForm.category_id" in SCRIPT
    assert "editForm.merchant.trim().length > 0 && !!editForm.category_id" in SCRIPT
    assert ':disabled="!isFormValid || isSubmitting"' in TEMPLATE
    assert ':disabled="!isEditFormValid || isSubmitting"' in TEMPLATE
    assert ':disabled="retraining"' in TEMPLATE
    # Create / update / delete refresh the rules list; retrain refreshes status
    assert SCRIPT.count("await refreshRules()") == 3
    assert "await refreshMLStatus()" in SCRIPT
    # Field errors stay inside FormField so they remain tied to their control
    assert TEMPLATE.count(':error="formErrors.merchant"') == 2
    assert TEMPLATE.count(':error="formErrors.category_id"') == 2


def test_settings_failed_load_is_not_shown_as_empty_or_default():
    assert "error: fetchError" in SCRIPT
    assert "error: mlStatusError" in SCRIPT
    loading = TEMPLATE.index('<LoadingState v-if="pending"')
    failed = TEMPLATE.index('v-else-if="fetchError && !rules"')
    empty = TEMPLATE.index('v-else-if="!rules || rules.length === 0"')
    assert loading < failed < empty, "rules load error must be checked before the empty state"
    status_error = TEMPLATE.index('v-if="mlStatusError && !mlStatus"')
    facts = TEMPLATE.index('<dl class="model-facts">')
    assert status_error < facts
    assert "Couldn't load categorization rules." in TEMPLATE
    assert "Couldn't load model status." in TEMPLATE


def test_settings_hierarchy_and_sections():
    assert 'class="settings-page page-container page-container--narrow"' in TEMPLATE
    assert "<PageHeader" in TEMPLATE and "<h1" not in TEMPLATE
    assert re.findall(r'<section class="settings-section" aria-labelledby="([^"]+)"', TEMPLATE) == [
        "heading-rules",
        "heading-ml",
        "heading-appearance",
    ]
    assert '<h2 id="heading-rules"' in TEMPLATE
    assert '<h2 id="heading-ml"' in TEMPLATE
    # Add rule lives with the rules it creates, not in the page header
    header = TEMPLATE[TEMPLATE.index("<PageHeader"): TEMPLATE.index("/>", TEMPLATE.index("<PageHeader"))]
    assert "openAddModal" not in header
    rules_section = TEMPLATE[TEMPLATE.index('aria-labelledby="heading-rules"'): TEMPLATE.index('aria-labelledby="heading-ml"')]
    assert 'aria-label="Create new categorization rule"' in rules_section
    # Model facts are a description list, not a grid of cards
    assert "<dt" in TEMPLATE and "<dd" in TEMPLATE


def test_settings_uses_shared_primitives():
    for fragment in ["btn btn-primary", "btn btn-secondary", "btn btn-ghost btn-sm", "btn-icon btn-icon-danger", "<AppIcon", "<AppDialog", "<FormField", "<ErrorBanner"]:
        assert fragment in TEMPLATE, fragment
    assert "btn-action" not in SETTINGS
    # Shared base.css owns input/select styling (and focus); no page-local override
    assert ".form-input" not in STYLE and ".form-select" not in STYLE
    assert "outline: none" not in STYLE
    # Delete stays a destructive confirmation dialog, never native confirm()
    assert 'class="btn btn-danger"' in TEMPLATE
    assert "confirm(" not in SCRIPT


def test_settings_no_hardcoded_colors_emoji_or_caps():
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", STYLE)
    assert "rgba(" not in STYLE
    assert "text-transform: uppercase" not in STYLE
    assert not re.search(r"[\U0001F300-\U0001FAFFℹ✅✎✕✓•]", TEMPLATE)
    # Only semantic tokens (no legacy --color-* aliases)
    assert "var(--color-" not in STYLE


def test_settings_status_and_success_not_color_alone():
    # Status badge shows the status text; tone class mapping unchanged
    assert "{{ mlStatus?.status || 'Unknown' }}" in TEMPLATE
    assert "if (s === 'Ready') return 'status-ready'" in SCRIPT
    assert "if (s === 'Stale') return 'status-stale'" in SCRIPT
    assert "return 'status-needs-data'" in SCRIPT
    success = TEMPLATE[TEMPLATE.index('class="success-banner"') - 80: TEMPLATE.index("</div>", TEMPLATE.index('class="success-banner"'))]
    assert 'role="status"' in success and 'aria-live="polite"' in success
    assert '<AppIcon name="check-circle"' in success
    assert "{{ successMessage }}" in success
    assert 'aria-label="Dismiss success message"' in success


def test_settings_single_continuous_container_tier():
    assert "container: rules / inline-size" in STYLE
    queries = re.findall(r"@(?:container|media)[^{]+", STYLE)
    assert [q.strip() for q in queries] == ["@container rules (width < 520px)"]
    assert "max-width: 639px" not in STYLE and "min-width: 640px" not in STYLE
    # Narrow tier changes table display, so table semantics are explicit in markup
    for role in ['role="table"', 'role="row"', 'role="columnheader"', 'role="cell"']:
        assert role in TEMPLATE, role
