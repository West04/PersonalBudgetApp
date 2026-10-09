"""
Contract tests for the theme system (final redesign slice).

1. Preference contract (utils/theme.ts): exactly system, light, dark, pink, tech;
   default system; anything else falls back to system.
2. Persistence: one `theme` cookie read through useTheme(), shared via useState so
   SSR and hydration agree; writes are normalized.
3. Shell: the preference is rendered as <html data-theme> by the server, and
   themes.css loads between tokens.css and base.css.
4. Token architecture: Dark/Pink/Tech override semantic tokens only; System is
   resolved by prefers-color-scheme to Light or the identical Dark block.
5. Accent vs meaning: financial/status tokens never reference the accent, Pink
   inherits Light's financial/status tokens, and in every theme the accent hue is
   clearly separated from the financial and status hues.
6. Contrast floor for representative token pairs in every theme.
7. Settings exposes an accessible radio group; pages/components never branch on
   the theme and contain no hardcoded presentation colors.
"""

import colorsys
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "frontend" / "app"
CSS_DIR = APP_DIR / "assets" / "css"
TOKENS = (CSS_DIR / "tokens.css").read_text()
THEMES = (CSS_DIR / "themes.css").read_text()

PREFERENCES = ["system", "light", "dark", "pink", "tech"]


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend theme tests")


# --------------------------------------------------------------------------- #
# CSS helpers
# --------------------------------------------------------------------------- #

def _decls(block):
    return dict((k, v.strip()) for k, v in re.findall(r"(--[a-z0-9-]+|color-scheme)\s*:\s*([^;]+);", block))


def _block(source, selector, start=0):
    i = source.index(selector, start)
    j = source.index("{", i)
    k = source.index("}", j)
    return source[j + 1:k]


ROOT = _decls(_block(TOKENS, ":root"))
DARK = _decls(_block(THEMES, ':root[data-theme="dark"]'))
PINK = _decls(_block(THEMES, ':root[data-theme="pink"]'))
TECH = _decls(_block(THEMES, ':root[data-theme="tech"]'))
_media = THEMES.index("@media (prefers-color-scheme: dark)")
SYSTEM_DARK = _decls(_block(THEMES, ':root[data-theme="system"]', _media))

THEME_TOKENS = {
    "light": ROOT,
    "dark": {**ROOT, **DARK},
    "pink": {**ROOT, **PINK},
    "tech": {**ROOT, **TECH},
}


def _resolve(theme, name):
    value = THEME_TOKENS[theme][name]
    while value.startswith("var("):
        value = THEME_TOKENS[theme][value[4:-1].strip()]
    return value


def _rgb(hex_value):
    h = hex_value.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _luminance(hex_value):
    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    hi, lo = sorted([_luminance(a), _luminance(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _hue(hex_value):
    return colorsys.rgb_to_hls(*_rgb(hex_value))[0] * 360


def _hue_distance(a, b):
    d = abs(_hue(a) - _hue(b)) % 360
    return min(d, 360 - d)


# --------------------------------------------------------------------------- #
# 1. Preference contract
# --------------------------------------------------------------------------- #

def test_theme_preference_contract(require_node):
    script = """
    import { THEME_PREFERENCES, DEFAULT_THEME_PREFERENCE, THEME_COOKIE, THEME_OPTIONS, normalizeThemePreference }
      from './frontend/app/utils/theme.ts';
    const inputs = ['system', 'light', 'dark', 'pink', 'tech',
                    null, undefined, '', 'auto', 'default', 'system-dark', 'Dark', ' dark', 42, {}, ['dark']];
    console.log(JSON.stringify({
      prefs: THEME_PREFERENCES,
      def: DEFAULT_THEME_PREFERENCE,
      cookie: THEME_COOKIE,
      options: THEME_OPTIONS.map(o => [o.value, o.label, Boolean(o.description)]),
      normalized: inputs.map(v => normalizeThemePreference(v)),
    }));
    """
    proc = subprocess.run(["node", "--input-type=module", "-e", script], cwd=REPO_ROOT,
                          capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["prefs"] == PREFERENCES
    assert res["def"] == "system"
    assert res["cookie"] == "theme"
    assert res["options"] == [
        ["system", "System", True], ["light", "Light", True], ["dark", "Dark", True],
        ["pink", "Pink", True], ["tech", "Tech", True],
    ]
    assert res["normalized"] == PREFERENCES + ["system"] * 11


# --------------------------------------------------------------------------- #
# 2-3. Persistence and shell
# --------------------------------------------------------------------------- #

def test_theme_preference_persists_in_cookie_and_shared_state():
    code = (APP_DIR / "composables" / "useTheme.ts").read_text()
    assert "useCookie<string | null>(THEME_COOKIE" in code
    assert "maxAge: 60 * 60 * 24 * 365" in code
    # Shared, SSR-serialized state seeded from the sanitized cookie
    assert re.search(r"useState<ThemePreference>\('theme_preference',\s*\(\)\s*=>\s*\n?\s*normalizeThemePreference\(cookie\.value\)", code)
    # Writes are normalized before reaching state or cookie
    setter = re.search(r"const setPreference = .*?\n  \}", code, re.S).group(0)
    assert "normalizeThemePreference(value)" in setter
    assert "preference.value = next" in setter and "cookie.value = next" in setter
    # No browser-only storage: the server must be able to read the preference
    assert "localStorage" not in code and "matchMedia" not in code


def test_shell_renders_theme_on_html_element():
    app = (APP_DIR / "app.vue").read_text()
    assert "const { preference: themePreference } = useTheme()" in app
    assert re.search(r"useHead\(\{\s*htmlAttrs:\s*\{\s*'data-theme':\s*themePreference\s*\}", app)

    config = (REPO_ROOT / "frontend" / "nuxt.config.ts").read_text()
    assert "css: ['~/assets/css/tokens.css', '~/assets/css/themes.css', '~/assets/css/base.css']" in config


# --------------------------------------------------------------------------- #
# 4. Token architecture
# --------------------------------------------------------------------------- #

SURFACE_TOKENS = {
    "--bg-page", "--bg-surface", "--bg-elevated", "--bg-subtle", "--bg-sunken",
    "--text-primary", "--text-secondary", "--text-muted", "--text-disabled", "--text-on-accent",
    "--border-subtle", "--border-default", "--border-strong",
    "--accent-primary", "--accent-hover", "--accent-subtle", "--accent-text",
    "--focus-ring", "--focus-halo",
    "--table-header", "--table-hover", "--nav-bg", "--overlay-scrim", "--input-border-hover",
}
MEANING_TOKENS = {
    "--status-success", "--status-success-bg", "--status-success-border",
    "--status-warning", "--status-warning-bg", "--status-warning-border",
    "--status-error", "--status-error-bg", "--status-error-border",
    "--status-info", "--status-info-bg", "--status-info-border",
    "--financial-inflow", "--financial-debt", "--financial-credit",
    "--financial-available", "--financial-overspent", "--financial-overspent-bg",
}


def test_theme_blocks_define_required_semantic_tokens():
    for name, block in [("dark", DARK), ("tech", TECH)]:
        missing = (SURFACE_TOKENS | MEANING_TOKENS | {"--input-bg", "--button-danger", "--button-danger-text", "--shadow-modal"}) - set(block)
        assert not missing, f"{name} missing {sorted(missing)}"
        assert block["color-scheme"] == "dark"
    missing = SURFACE_TOKENS - set(PINK)
    assert not missing, f"pink missing {sorted(missing)}"
    assert PINK["color-scheme"] == "light"
    assert "light" in _block(THEMES, ':root[data-theme="light"]')


def test_themes_override_only_semantic_color_tokens():
    # Geometry, type and spacing are shared: a theme never changes layout
    forbidden = re.compile(r"^--(space|radius|type|font|line-height|rail|page|mobile|sidebar)")
    for name, block in [("dark", DARK), ("pink", PINK), ("tech", TECH), ("system", SYSTEM_DARK)]:
        for token in block:
            assert token == "color-scheme" or token in ROOT, f"{name} invents token {token}"
            assert not forbidden.match(token), f"{name} overrides layout token {token}"


def test_system_resolves_to_light_or_identical_dark():
    # Only one system rule, and it lives inside the prefers-color-scheme: dark query
    assert THEMES.count('[data-theme="system"]') == 1
    assert THEMES.index('[data-theme="system"]') > _media
    assert SYSTEM_DARK == DARK, "system-dark block drifted from the dark block"


# --------------------------------------------------------------------------- #
# 5. Accent vs financial/status meaning
# --------------------------------------------------------------------------- #

def test_meaning_tokens_never_derive_from_accent():
    for theme, tokens in THEME_TOKENS.items():
        for name, value in tokens.items():
            if name.startswith(("--financial-", "--status-", "--button-danger")):
                assert "--accent" not in value and "--focus" not in value, f"{theme} {name} uses accent"
    # Pink changes the accent only; overspending, errors and inflows keep Light's values
    assert not (MEANING_TOKENS & set(PINK)), "pink must inherit financial/status tokens"
    # Ordinary outflow stays neutral ink in every theme
    for theme in THEME_TOKENS:
        assert _resolve(theme, "--financial-outflow") == _resolve(theme, "--text-primary")


@pytest.mark.parametrize("theme", ["light", "dark", "pink", "tech"])
def test_accent_hue_distinct_from_financial_and_status(theme):
    accent = _resolve(theme, "--accent-primary")
    for name in ["--financial-inflow", "--financial-credit", "--financial-available",
                 "--financial-overspent", "--financial-debt",
                 "--status-error", "--status-warning", "--status-success", "--button-danger"]:
        assert _hue_distance(accent, _resolve(theme, name)) >= 30, f"{theme}: accent too close to {name}"
    # Favorable and unfavorable stay apart, and warning is not error
    assert _hue_distance(_resolve(theme, "--financial-available"), _resolve(theme, "--financial-overspent")) >= 90
    assert _hue_distance(_resolve(theme, "--status-warning"), _resolve(theme, "--status-error")) >= 20


# --------------------------------------------------------------------------- #
# 6. Contrast
# --------------------------------------------------------------------------- #

TEXT_PAIRS = [
    ("--text-primary", "--bg-page"), ("--text-primary", "--bg-surface"),
    ("--text-secondary", "--bg-surface"),
    ("--text-muted", "--bg-page"), ("--text-muted", "--bg-surface"),
    ("--text-muted", "--bg-elevated"), ("--text-muted", "--table-header"),
    ("--input-placeholder", "--input-bg"),
    ("--button-primary-text", "--button-primary"), ("--button-primary-text", "--button-primary-hover"),
    ("--button-danger-text", "--button-danger"), ("--button-danger-text", "--button-danger-hover"),
    ("--accent-text", "--bg-surface"), ("--nav-text-active", "--nav-item-active"),
    ("--status-error", "--status-error-bg"), ("--status-warning", "--status-warning-bg"),
    ("--status-error", "--bg-surface"), ("--status-warning", "--bg-surface"),
    ("--financial-available", "--bg-surface"), ("--financial-inflow", "--bg-surface"),
    ("--financial-credit", "--bg-page"), ("--financial-overspent", "--bg-surface"),
]
UI_PAIRS = [
    ("--focus-ring", "--bg-page"), ("--focus-ring", "--bg-surface"),
    ("--focus-ring", "--bg-elevated"), ("--focus-ring", "--nav-bg"),
    ("--input-border", "--input-bg"), ("--input-border", "--bg-surface"),
]


@pytest.mark.parametrize("theme", ["light", "dark", "pink", "tech"])
def test_theme_contrast_floor(theme):
    failures = []
    for fg, bg in TEXT_PAIRS:
        c = _contrast(_resolve(theme, fg), _resolve(theme, bg))
        if c < 4.5:
            failures.append(f"{fg} on {bg} = {c:.2f}")
    for fg, bg in UI_PAIRS:
        c = _contrast(_resolve(theme, fg), _resolve(theme, bg))
        if c < 3:
            failures.append(f"{fg} on {bg} = {c:.2f}")
    assert not failures, f"{theme}: {failures}"


# --------------------------------------------------------------------------- #
# 7. Settings control, no page branching, no hardcoded colors
# --------------------------------------------------------------------------- #

def test_settings_theme_control_is_accessible_radio_group():
    settings = (APP_DIR / "pages" / "settings.vue").read_text()
    template = settings[: settings.index("<script setup")]
    script = settings[settings.index("<script setup"): settings.index("</script>")]
    section = template[template.index('aria-labelledby="heading-appearance"'):]
    section = section[: section.index("</section>")]

    assert '<h2 id="heading-appearance"' in section
    assert '<fieldset class="theme-fieldset">' in section
    assert '<legend class="theme-legend">Theme</legend>' in section
    assert 'v-for="option in themeOptions"' in section
    assert "<label" in section and 'type="radio"' in section and 'name="theme"' in section
    assert ':checked="themePreference === option.value"' in section
    assert ":aria-describedby=\"`theme-desc-${option.value}`\"" in section
    assert '@change="setThemePreference(option.value)"' in section
    assert "{{ option.label }}" in section and "{{ option.description }}" in section
    assert "useTheme()" in script
    # Local display preference only: no API request
    assert "$fetch" not in section and "useFetch" not in section


def test_no_page_specific_theme_branching():
    pattern = re.compile(r"data-theme|prefers-color-scheme|theme\s*===?|\b(pink|tech)\b", re.I)
    offenders = []
    for path in list((APP_DIR / "pages").rglob("*.vue")) + list((APP_DIR / "components").rglob("*.vue")):
        for line in path.read_text().splitlines():
            if pattern.search(line):
                offenders.append(f"{path.name}: {line.strip()}")
    assert not offenders, offenders
    base = (CSS_DIR / "base.css").read_text()
    assert "data-theme" not in base and "prefers-color-scheme" not in base


def test_no_hardcoded_presentation_colors_outside_token_files():
    color = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    offenders = []
    files = list(APP_DIR.rglob("*.vue")) + [CSS_DIR / "base.css"]
    for path in files:
        source = path.read_text()
        for line in source.splitlines():
            if color.search(line):
                offenders.append(f"{path.relative_to(APP_DIR)}: {line.strip()}")
    assert not offenders, offenders
    icon = (APP_DIR / "components" / "AppIcon.vue").read_text()
    assert 'stroke="currentColor"' in icon and not color.search(icon)
