"""Feature tests — UI and UX: drag handles, footer, sticky header, product
name consistency, JSON editor, autocomplete, inherited values, tabs,
responsive layout, print styles, action buttons."""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

TEMPLATE_DIR = ROOT / "src" / "releaseboard" / "presentation" / "templates"

_TEMPLATE_DIR = ROOT / "src" / "releaseboard" / "presentation" / "templates"

CONFIG = json.loads((ROOT / "examples" / "config.json").read_text())

def _html() -> str:
    """Read and concatenate all template partials for string-based checks."""
    parts = []
    for f in sorted(TEMPLATE_DIR.glob("*.j2")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)

def _read_all_templates() -> str:
    parts = []
    for f in sorted(_TEMPLATE_DIR.glob("*.j2")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)

TEMPLATE = _read_all_templates()

# ── Drag Handle Visibility (req 95-97) ──────────────────────────────────

class TestDragHandleVisibility:
    """Scenarios for drag handle visibility."""

    def test_dashboard_sections_exist(self):
        """GIVEN the concatenated template source."""
        html = TEMPLATE

        """WHEN checking for dashboard section attributes."""
        has_sections = "data-section-id" in html

        """THEN section ID attributes are present."""
        assert has_sections

    def test_section_ids_defined(self):
        """GIVEN the concatenated template source."""
        import re
        html = TEMPLATE

        """WHEN extracting section IDs via regex."""
        sections = re.findall(r'data-section-id="(\w[\w-]*)"', html)

        """THEN at least five sections are defined."""
        assert len(sections) >= 5

    def test_layout_config_in_releaseboard_json(self):
        """GIVEN the releaseboard.json config."""
        config = CONFIG

        """WHEN accessing layout settings."""
        has_layout = "layout" in config
        drag_drop = config.get("layout", {}).get("enable_drag_drop")

        """THEN layout is present with drag-drop enabled."""
        assert has_layout
        assert drag_drop is True

    def test_dashboard_section_class_exists(self):
        """GIVEN the concatenated template source."""
        html = TEMPLATE

        """WHEN checking for dashboard-section CSS class."""
        found = "dashboard-section" in html

        """THEN the class is present."""
        assert found

    def test_section_styles_exist(self):
        """GIVEN the concatenated template source."""
        html = TEMPLATE

        """WHEN checking for dashboard-section CSS selector."""
        found = ".dashboard-section" in html

        """THEN dashboard-section styles are defined."""
        assert found

    def test_primary_color_variable_used(self):
        """GIVEN the concatenated template source."""
        html = TEMPLATE

        """WHEN checking for CSS custom property usage."""
        found = "var(--primary)" in html

        """THEN primary color variable is used."""
        assert found

    def test_sections_have_margin_or_padding(self):
        """GIVEN the concatenated template source."""
        html = TEMPLATE

        """WHEN checking for spacing styles."""
        found = "margin" in html

        """THEN margin rules are present."""
        assert found

# ===========================================================================
# Product name consistency
# ===========================================================================


# ===========================================================================
# Sticky header / toolbar
# ===========================================================================


# ===========================================================================
# Config add-button visibility / orange accent
# ===========================================================================


# ===========================================================================
# JSON field reference placement (below, not right-side)
# ===========================================================================


# ===========================================================================
# JSON autocomplete CSS and integration
# ===========================================================================

class TestJsonAutocomplete:
    """Scenarios for JSON autocomplete support."""

    def test_schema_has_root_fields(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN checking for root schema field names."""
        has_release = "'release'" in html or '"release"' in html
        has_layers = "'layers'" in html or '"layers"' in html
        has_repos = "'repositories'" in html or '"repositories"' in html

        """THEN release, layers, and repositories fields are present."""
        assert has_release
        assert has_layers
        assert has_repos


# ===========================================================================
# Inherited values must appear in inputs
# ===========================================================================


# ===========================================================================
# Real-time auto-name from URL
# ===========================================================================


# ===========================================================================
# Effective/Active tab
# ===========================================================================

class TestEffectiveTab:
    """Scenarios for effective tab rendering."""

    def test_effective_tab_css(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN checking for effective tab CSS classes."""
        has_tab = ".effective-tab" in html
        has_section = ".eff-section" in html
        has_table = ".eff-table" in html
        has_source = ".eff-source" in html

        """THEN all required CSS classes are defined."""
        assert has_tab
        assert has_section
        assert has_table
        assert has_source

    def test_effective_tab_shows_layers(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN extracting the renderEffectiveTab function body."""
        match = re.search(r"function renderEffectiveTab\(\)\{(.*?)\n  function effRow", html, re.S)
        assert match
        body = match.group(1)

        """THEN the function body references layers."""
        assert "ui.config.effective.layers" in body

    def test_effective_tab_shows_repositories(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN extracting the renderEffectiveTab function body."""
        match = re.search(r"function renderEffectiveTab\(\)\{(.*?)\n  function effRow", html, re.S)
        assert match
        body = match.group(1)

        """THEN the function body references repositories."""
        assert "ui.config.effective.repositories" in body

    def test_effective_tab_source_badges(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN checking for source badge CSS classes."""
        has_base = "eff-source" in html
        sources = ["global", "layer", "repo", "default", "derived"]
        badge_matches = [
            f".eff-source.{src}" in html or f"eff-source {src}" in html
            for src in sources
        ]

        """THEN all source badge variants are defined."""
        assert has_base
        for src, matched in zip(sources, badge_matches, strict=True):
            assert matched, f"eff-source badge for '{src}' not found"

    def test_switch_tab_calls_render_effective(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN extracting the switchTab function body."""
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        assert match

        """THEN switchTab invokes renderEffectiveTab."""
        assert "renderEffectiveTab" in match.group(1)


# ===========================================================================
# Coherence across Form, JSON, and Effective tabs
# ===========================================================================

class TestTabCoherence:
    """Scenarios for tab coherence across Form, JSON, and Effective."""

    def test_three_tabs_toggled(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN extracting the switchTab function body."""
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        assert match
        body = match.group(1)

        """THEN all three tab IDs are toggled."""
        assert "tabForm" in body
        assert "tabJson" in body
        assert "tabEffective" in body


# ===========================================================================
# Footer cleanup
# ===========================================================================

class TestFooterCleanup:
    """Scenarios for footer cleanup."""

    def test_no_footer_mode_badge(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN extracting the footer element."""
        footer_match = re.search(r'<footer class="rb-footer">(.*?)</footer>', html, re.S)
        assert footer_match
        footer = footer_match.group(1)

        """THEN no Interactive or Static mode badges are present."""
        assert "Interactive" not in footer
        assert "Static" not in footer
        assert "rb-footer-mode" not in footer

    def test_footer_has_tools_section(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN extracting the footer element."""
        footer_match = re.search(r'<footer class="rb-footer">(.*?)</footer>', html, re.S)
        assert footer_match
        footer = footer_match.group(1)

        """THEN ReleaseBoard and ReleasePilot are mentioned."""
        assert "ReleaseBoard" in footer
        assert "ReleasePilot" in footer


# ===========================================================================
# i18n completeness, responsive safety, accessibility
# ===========================================================================

class TestI18nCompleteness:
    """Scenarios for i18n completeness."""

    def test_export_buttons_localized(self):
        """GIVEN the template HTML source."""
        html = _html()

        """WHEN checking for export button i18n attributes."""
        has_html = 'data-i18n="ui.export_html"' in html
        has_config = 'data-i18n="ui.export_config"' in html

        """THEN both export buttons are localised."""
        assert has_html
        assert has_config

    def test_i18n_keys_exist_in_both_locales(self):
        """GIVEN English and Polish locale files."""
        import json
        locale_dir = ROOT / "src" / "releaseboard" / "i18n" / "locales"
        en = json.loads((locale_dir / "en.json").read_text())
        pl = json.loads((locale_dir / "pl.json").read_text())

        """WHEN checking required i18n keys in both locales."""
        keys = ["ui.theme.light", "ui.theme.auto", "ui.theme.dark", "ui.theme.midnight",
                 "ui.status.ready", "ui.status.idle"]

        """THEN all keys are present and non-empty in both locales."""
        for key in keys:
            assert key in en, f"{key} missing in en.json"
            assert key in pl, f"{key} missing in pl.json"
            assert en[key], f"{key} is empty in en.json"
            assert pl[key], f"{key} is empty in pl.json"


class TestActionButtonBehavior:
    """Scenarios for row action styling."""

    def test_row_actions_no_inline_opacity(self):
        """GIVEN the dashboard content template."""
        content_file = TEMPLATE_DIR / "_dashboard_content.html.j2"
        html = content_file.read_text(encoding="utf-8")

        """WHEN checking for inline opacity override."""
        has_inline_opacity = 'style="opacity:1;"' in html

        """THEN no inline opacity override is present."""
        assert not has_inline_opacity
