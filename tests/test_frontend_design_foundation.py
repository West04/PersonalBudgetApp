"""
Tests for the frontend design foundation slice (tokens, shell navigation, Money primitive).

Verifies:
1. formatMoney (utils/money.ts) formatting contract:
   - 'auto' matches the existing formatCurrency output for ordinary values.
   - 'never' drops the sign; 'always' shows +/- except for zero.
   - Values that round to zero cents never render as "-$0.00".
   - Invalid input renders "$0.00" like formatCurrency.
2. Money.vue only formats: it delegates to formatMoney and takes tone from the caller.
3. Every Money tone has a matching global CSS class bound to a financial token.
4. tokens.css defines the semantic token set and keeps every legacy --color-* alias
   that page styles still reference.
5. Shell navigation contract (app.vue):
   - All existing route destinations are reachable, including /credit-cards.
   - Labels: Budget for /categories, Import for /upload.
   - Month-scoped destinations carry the selected month query.
   - Labels are never removed from the DOM when the rail collapses.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "frontend" / "app"


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend foundation tests")


def test_format_money_contract(require_node):
    script = """
    import { formatMoney } from './frontend/app/utils/money.ts';
    import { formatCurrency } from './frontend/app/utils/dashboardMath.ts';

    const cases = [
        { args: [1234.5], expected: '$1,234.50' },
        { args: ['-42.36'], expected: '-$42.36' },
        { args: [-42.36, 'never'], expected: '$42.36' },
        { args: [42.36, 'always'], expected: '+$42.36' },
        { args: [-42.36, 'always'], expected: '-$42.36' },
        { args: [0, 'always'], expected: '$0.00' },
        { args: [-0.001], expected: '$0.00' },
        { args: [-0], expected: '$0.00' },
        { args: [null], expected: '$0.00' },
        { args: [undefined], expected: '$0.00' },
        { args: ['not-a-number'], expected: '$0.00' },
    ];

    const failures = [];
    for (const c of cases) {
        const actual = formatMoney(...c.args);
        if (actual !== c.expected) failures.push({ args: c.args, expected: c.expected, actual });
    }

    // 'auto' must not change how ordinary values look today
    for (const v of [0, 5, -5, 1234.567, '99.99', '-0.50', 1e6]) {
        if (formatMoney(v) !== formatCurrency(v)) {
            failures.push({ parity: v, money: formatMoney(v), currency: formatCurrency(v) });
        }
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"formatMoney failures: {res['failures']}"


def test_money_component_only_formats():
    code = (APP_DIR / "components" / "Money.vue").read_text()
    assert "formatMoney(props.amount, props.sign)" in code
    assert "tone: 'neutral'" in code
    # No financial inference inside the primitive
    assert "dashboardMath" not in code
    assert not re.search(r"amount\s*[<>]=?\s*0", code), "Money.vue must not pick tone from the sign"


def test_money_tones_have_css_classes(require_node):
    script = """
    import { MONEY_TONES } from './frontend/app/utils/money.ts';
    console.log(JSON.stringify(MONEY_TONES));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    tones = json.loads(proc.stdout)
    base = (APP_DIR / "assets" / "css" / "base.css").read_text()
    for tone in tones:
        assert re.search(rf"\.money--{tone}\s*\{{\s*color:\s*var\(--financial-", base), f"missing .money--{tone}"


def test_semantic_tokens_and_legacy_aliases():
    tokens = (APP_DIR / "assets" / "css" / "tokens.css").read_text()
    defined = set(re.findall(r"^\s*(--[a-z0-9-]+)\s*:", tokens, re.M))

    required = {
        "--bg-page", "--bg-surface", "--bg-elevated",
        "--text-primary", "--text-secondary", "--text-muted", "--text-on-accent",
        "--border-subtle", "--border-strong",
        "--accent-primary", "--accent-hover", "--focus-ring",
        "--status-success", "--status-warning", "--status-error",
        "--financial-debt", "--financial-credit", "--financial-inflow", "--financial-outflow",
        "--financial-overspent", "--financial-available", "--financial-neutral",
        "--table-header", "--table-hover", "--table-row-selected",
        "--input-bg", "--button-primary", "--overlay-scrim",
        "--font-display", "--font-body", "--font-numeric",
        "--page-width-standard", "--page-width-wide",
    }
    assert not (required - defined), f"missing semantic tokens: {sorted(required - defined)}"

    # Every custom property referenced by existing frontend code must still be defined
    referenced = set()
    for path in list(APP_DIR.rglob("*.vue")) + list((APP_DIR / "assets" / "css").glob("*.css")):
        for name in re.findall(r"var\((--[a-z0-9-]+)\s*[,)]", path.read_text()):
            referenced.add(name)
    # Pre-existing references that were never defined (pages rely on fallbacks or
    # inheritance). Left untouched here so rendering does not change; page slices fix them.
    known_undefined = {
        "--color-text-emphasis",
        "--color-primary-bg",
        "--color-surface-subtle",
        "--font-mono",
        "--font-weight-normal",
    }
    missing = referenced - defined - known_undefined
    assert not missing, f"custom properties referenced but not defined: {sorted(missing)}"


def test_shell_navigation_contract():
    app = (APP_DIR / "app.vue").read_text()

    expected = {
        "Dashboard": "{ path: '/dashboard', query: { month: selectedMonth.value } }",
        "Budget": "{ path: '/categories', query: { month: selectedMonth.value } }",
        "Transactions": "{ path: '/transactions', query: { month: selectedMonth.value } }",
        "Accounts": "'/accounts'",
        "Credit Cards": "{ path: '/credit-cards', query: { month: selectedMonth.value } }",
        "Import": "'/upload'",
    }
    for label, to in expected.items():
        assert f"label: '{label}'" in app, f"missing nav label {label}"
        assert f"to: {to}" in app, f"nav destination changed for {label}"
    assert 'to="/settings"' in app

    # Collapsed rail keeps labels in the DOM (visually hidden), never v-if
    assert re.search(r'<span class="nav-label">\{\{ item\.label \}\}</span>', app)
    assert "v-if=\"!isCollapsed\"" not in app

    # Emoji-only navigation is gone
    assert not re.search(r"[\U0001F300-\U0001FAFF⚙]", app)


def _tag(source, tag, marker):
    """Return the opening tag of `tag` that contains `marker` (attributes may span lines)."""
    for m in re.finditer(rf"<{tag}\b[^>]*>", source, re.S):
        if marker in m.group(0):
            return m.group(0)
    return None


def test_mobile_navigation_accessibility_contract():
    """
    Protects the accessible mobile drawer:
    - menu control is tied to the drawer (aria-controls) and reports its state (aria-expanded);
    - background content is inert while the drawer is open;
    - Escape closes the drawer from a document-level listener that exists only while open;
    - reduced motion removes the drawer transition and never creates new transitions globally
      (a transitioned `visibility` blocks focus entry).
    """
    app = (APP_DIR / "app.vue").read_text()
    template = app.split("<script", 1)[0]
    script = app.split("<script", 1)[1].split("</script>", 1)[0]
    style = app.split("<style", 1)[1]

    assert _tag(template, "aside", 'id="app-nav"'), "drawer must keep id app-nav"

    menu = _tag(template, "button", 'aria-label="Open navigation"')
    assert menu, "mobile menu button missing"
    assert 'aria-controls="app-nav"' in menu
    assert re.search(r':aria-expanded="[^"]*\bdrawerOpen\b', menu), "aria-expanded must be bound to drawerOpen"

    main = _tag(template, "main", 'id="main-content"')
    assert main and re.search(r':inert="[^"]*\bdrawerOpen\b', main), "<main> must be inert while the drawer is open"

    # Escape handler: checks the key and closes the drawer
    handler = re.search(r"const onDocumentKeydown\s*=.*?\n\}", script, re.S)
    assert handler, "document-level Escape handler missing"
    assert "'Escape'" in handler.group(0) and "closeDrawer(" in handler.group(0)

    # Listener is attached/removed with drawer state and removed on unmount
    drawer_watch = re.search(r"watch\(\s*drawerOpen\s*,.*?\n\}\)", script, re.S)
    assert drawer_watch, "drawerOpen watcher missing"
    assert re.search(r"document\.addEventListener\(\s*'keydown'\s*,\s*onDocumentKeydown\s*\)", drawer_watch.group(0))
    assert re.search(r"document\.removeEventListener\(\s*'keydown'\s*,\s*onDocumentKeydown\s*\)", drawer_watch.group(0))
    unmount = re.search(r"onBeforeUnmount\(.*?\n\}\)", script, re.S)
    assert unmount and "removeEventListener('keydown', onDocumentKeydown)" in re.sub(r"\s+", " ", unmount.group(0)).replace("( ", "(")

    # Reduced motion: sidebar/drawer transition disabled
    rm = re.search(r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{(.*?)\n\}", style, re.S)
    assert rm, "reduced-motion block missing from shell styles"
    assert re.search(r"\.sidebar\b[^{]*\{[^}]*transition\s*:\s*none", rm.group(1)), "reduced motion must disable the drawer transition"

    # Global reduced-motion rule must cut transitions to 0s. A tiny non-zero duration turns every
    # element's default `transition-property: all` into a real transition, so inherited
    # `visibility` lags and focus cannot enter the drawer.
    base = (APP_DIR / "assets" / "css" / "base.css").read_text()
    global_rm = re.search(r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{(.*?)\n\}", base, re.S)
    assert global_rm, "global reduced-motion block missing"
    durations = re.findall(r"transition-duration\s*:\s*([^;!]+)", global_rm.group(1))
    assert durations and all(d.strip() in ("0s", "0") for d in durations), f"reduced-motion transition-duration must be 0s, got {durations}"
