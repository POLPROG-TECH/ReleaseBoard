"""Tests for dashboard UI — product name consistency, sticky header, JSON editor,
effective tab, inherited display, autocomplete, validation scoping."""

import json
import pathlib
import re

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "src" / "releaseboard" / "presentation" / "templates"

def _html() -> str:
    """Read and concatenate all template partials for string-based checks."""
    parts = []
    for f in sorted(TEMPLATE_DIR.glob("*.j2")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _examples_config() -> dict:
    return json.loads((ROOT / "examples" / "config.json").read_text(encoding="utf-8"))


# ===========================================================================
# Product name consistency
# ===========================================================================

class TestProductNameConsistency:
    """Scenarios for product name consistency."""

    def test_template_no_acmeboard(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for the legacy product name."""
        found = "AcmeBoard" in html

        """THEN AcmeBoard does not appear."""
        assert not found

    def test_examples_config_no_acmeboard(self):
        """GIVEN the examples config file content."""
        raw = (ROOT / "examples" / "config.json").read_text(encoding="utf-8")

        """WHEN scanning for the legacy product name."""
        found = "AcmeBoard" in raw

        """THEN AcmeBoard does not appear."""
        assert not found

    def test_readme_no_acmeboard(self):
        """GIVEN the README file content."""
        raw = (ROOT / "README.md").read_text(encoding="utf-8")

        """WHEN scanning for the legacy product name."""
        found = "AcmeBoard" in raw

        """THEN AcmeBoard does not appear."""
        assert not found

    def test_readme_has_releaseboard(self):
        """GIVEN the README file content."""
        raw = (ROOT / "README.md").read_text(encoding="utf-8")

        """WHEN scanning for the product name."""
        found = "ReleaseBoard" in raw

        """THEN ReleaseBoard appears."""
        assert found

    def test_integration_test_no_acmeboard(self):
        """GIVEN the integration test file content."""
        raw = (ROOT / "tests" / "test_integration.py").read_text(encoding="utf-8")

        """WHEN scanning for the legacy product name."""
        found = "AcmeBoard" in raw

        """THEN AcmeBoard does not appear."""
        assert not found


# ===========================================================================
# Sticky header / toolbar
# ===========================================================================

class TestStickyHeader:
    """Scenarios for sticky header toolbar."""

    def test_toolbar_sticky_css(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the toolbar CSS rules."""
        match = re.search(r"\.toolbar\s*\{[^}]*position:\s*sticky", html, re.S)

        """THEN position is sticky."""
        assert match

    def test_toolbar_top_offset(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the toolbar CSS rules."""
        match = re.search(r"\.toolbar\s*\{[^}]*top:\s*\d+(px)?", html, re.S)

        """THEN a top offset is defined."""
        assert match

    def test_toolbar_z_index(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the toolbar CSS rules."""
        match = re.search(r"\.toolbar\s*\{[^}]*z-index:\s*\d+", html, re.S)

        """THEN z-index is defined."""
        assert match

    def test_print_toolbar_static(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN extracting the @media print block."""
        print_block = re.search(r"@media\s+print\s*\{(.+?)\n\}", html, re.S)
        assert print_block, "@media print block must exist"
        block = print_block.group(1)

        """THEN the toolbar is static or hidden."""
        assert "toolbar" in block.lower()
        assert "position: static" in block or "display: none" in block


# ===========================================================================
# Config add-button visibility / orange accent
# ===========================================================================

class TestCfgAddBtnStyle:
    """Scenarios for cfg-add-btn styling."""

    def test_accent_background_or_border(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN extracting the cfg-add-btn style block."""
        section = re.search(r"\.cfg-add-btn\s*\{([^}]+)\}", html)
        assert section, "cfg-add-btn style block must exist"
        block = section.group(1)

        """THEN the button uses standard border and secondary background."""
        assert "var(--border)" in block or "var(--bg-secondary)" in block

    def test_font_weight(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN extracting the cfg-add-btn style block."""
        section = re.search(r"\.cfg-add-btn\s*\{([^}]+)\}", html)
        assert section

        """THEN font-weight is set."""
        assert "font-weight" in section.group(1)


# ===========================================================================
# JSON field reference placement (below, not right-side)
# ===========================================================================

class TestJsonFieldReferencePlacement:
    """Scenarios for JSON field reference placement."""

    def test_json_tab_flex_column(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the json-editor-wrap layout."""
        match = re.search(r"\.json-editor-wrap\s*\{[^}]*flex-direction:\s*column", html, re.S)

        """THEN flex-direction is column."""
        assert match

    def test_field_legend_exists(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for a field legend element."""
        found = "field-legend" in html.lower() or "Field Reference" in html

        """THEN the field legend exists."""
        assert found


# ===========================================================================
# JSON autocomplete CSS and integration
# ===========================================================================

class TestJsonAutocomplete:
    """Scenarios for JSON autocomplete support."""

    def test_autocomplete_css(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for autocomplete styles."""
        found = ".json-autocomplete" in html

        """THEN the json-autocomplete class exists."""
        assert found

    def test_autocomplete_item_css(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for autocomplete item styles."""
        found = ".json-autocomplete-item" in html

        """THEN the json-autocomplete-item class exists."""
        assert found

    def test_autocomplete_init_called(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for autocomplete initialization."""
        found = "initJsonAutocomplete" in html

        """THEN initJsonAutocomplete is called."""
        assert found

    def test_schema_fields_defined(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for schema field definitions."""
        found = "SCHEMA_FIELDS" in html

        """THEN SCHEMA_FIELDS is defined."""
        assert found

    def test_schema_has_root_fields(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for root schema fields."""
        has_release = "'release'" in html or '"release"' in html
        has_layers = "'layers'" in html or '"layers"' in html
        has_repositories = "'repositories'" in html or '"repositories"' in html

        """THEN release, layers, and repositories are defined."""
        assert has_release
        assert has_layers
        assert has_repositories


# ===========================================================================
# Validation scoping across tabs
# ===========================================================================

class TestValidationScoping:
    """Scenarios for validation scoping across tabs."""

    def test_switch_tab_clears_validation(self):
        """GIVEN the switchTab function body."""
        html = _html()
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        assert match
        body = match.group(1)

        """WHEN checking validation handling."""
        has_validation_panel = "validationPanel" in body

        """THEN validationPanel is referenced."""
        assert has_validation_panel

    def test_json_tab_triggers_json_validation(self):
        """GIVEN the switchTab function body."""
        html = _html()
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        assert match
        body = match.group(1)

        """WHEN switching to the JSON tab."""
        has_validate = "validateJsonEditor" in body

        """THEN validateJsonEditor is called."""
        assert has_validate

    def test_form_tab_triggers_form_validation(self):
        """GIVEN the switchTab function body."""
        html = _html()
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        assert match
        body = match.group(1)

        """WHEN switching to the form tab."""
        has_validate = "validateDraft" in body

        """THEN validateDraft is called."""
        assert has_validate


# ===========================================================================
# Inherited values must appear in inputs
# ===========================================================================

class TestInheritedValueDisplay:
    """Scenarios for inherited value display."""

    def test_branch_input_placeholder_uses_effective(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the branch input placeholder."""
        match = re.search(r"placeholder=\"\$\{esc\(branchPlaceholder\s*\|\|\s*effBranch\)", html)

        """THEN the effective value is shown."""
        assert match

    def test_branch_input_shows_override_only(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the branch input value."""
        match = re.search(r"value=\"\$\{hasRepoOverride\s*\?\s*r\.branch_pattern", html)

        """THEN only the override is shown."""
        assert match


# ===========================================================================
# Real-time auto-name from URL
# ===========================================================================

class TestRealtimeAutoName:
    """Scenarios for real-time auto-name from URL."""

    def test_url_input_has_oninput(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the URL input handler."""
        found = "oninput=\"RB.autoFillRepoName" in html

        """THEN oninput triggers autoFillRepoName."""
        assert found

    def test_url_input_still_has_onchange(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the URL change handler."""
        match = re.search(r"onchange=\"RB\.updateRepo\(\$\{i\},'url'", html)

        """THEN onchange triggers updateRepo."""
        assert match


# ===========================================================================
# Effective/Active tab
# ===========================================================================

class TestEffectiveTab:
    """Scenarios for the effective tab."""

    def test_effective_tab_button_exists(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for the effective tab button."""
        found = 'data-tab="effective"' in html

        """THEN data-tab="effective" exists."""
        assert found

    def test_effective_tab_div_exists(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for the effective tab container."""
        found = 'id="tabEffective"' in html

        """THEN tabEffective div exists."""
        assert found

    def test_render_effective_tab_function(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for the render function."""
        found = "function renderEffectiveTab()" in html

        """THEN renderEffectiveTab is defined."""
        assert found

    def test_effective_tab_css(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for effective tab styles."""
        has_effective_tab = ".effective-tab" in html
        has_eff_section = ".eff-section" in html
        has_eff_table = ".eff-table" in html
        has_eff_source = ".eff-source" in html

        """THEN required CSS classes exist."""
        assert has_effective_tab
        assert has_eff_section
        assert has_eff_table
        assert has_eff_source

    def test_effective_tab_shows_global_settings(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking effective tab content."""
        found = "ui.config.effective.global_settings" in html

        """THEN global settings are rendered."""
        assert found

    def test_effective_tab_shows_layers(self):
        """GIVEN the renderEffectiveTab function body."""
        html = _html()
        match = re.search(r"function renderEffectiveTab\(\)\{(.*?)\n  function effRow", html, re.S)
        assert match
        body = match.group(1)

        """WHEN checking layer rendering."""
        has_layers = "ui.config.effective.layers" in body

        """THEN layers are rendered."""
        assert has_layers

    def test_effective_tab_shows_repositories(self):
        """GIVEN the renderEffectiveTab function body."""
        html = _html()
        match = re.search(r"function renderEffectiveTab\(\)\{(.*?)\n  function effRow", html, re.S)
        assert match
        body = match.group(1)

        """WHEN checking repository rendering."""
        has_repos = "ui.config.effective.repositories" in body

        """THEN repositories are rendered."""
        assert has_repos

    def test_effective_tab_source_badges(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking source badge CSS classes."""
        has_eff_source = "eff-source" in html
        source_checks = {
            src: (f".eff-source.{src}" in html or f"eff-source {src}" in html)
            for src in ["global", "layer", "repo", "default", "derived"]
        }

        """THEN badges exist for all source types."""
        assert has_eff_source
        for src, present in source_checks.items():
            assert present, f"missing badge for {src}"

    def test_effective_tab_in_return_object(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the RB return block."""
        assert "renderEffectiveTab" in html
        return_match = re.search(r"return\s*\{[^}]*toggleDrawer[^}]+\}", html)
        assert return_match

        """THEN renderEffectiveTab is exposed."""
        assert "renderEffectiveTab" in return_match.group(0)

    def test_switch_tab_calls_render_effective(self):
        """GIVEN the switchTab function body."""
        html = _html()
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        assert match

        """WHEN checking tab switch handling."""
        has_render = "renderEffectiveTab" in match.group(1)

        """THEN renderEffectiveTab is called."""
        assert has_render


# ===========================================================================
# Coherence across Form, JSON, and Effective tabs
# ===========================================================================

class TestTabCoherence:
    """Scenarios for tab coherence."""

    def test_three_tabs_toggled(self):
        """GIVEN the switchTab function body."""
        html = _html()
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        assert match
        body = match.group(1)

        """WHEN checking toggled tabs."""
        has_tab_form = "tabForm" in body
        has_tab_json = "tabJson" in body
        has_tab_effective = "tabEffective" in body

        """THEN all three tabs are toggled."""
        assert has_tab_form
        assert has_tab_json
        assert has_tab_effective


# ===========================================================================
# Config example sanity
# ===========================================================================

class TestExamplesConfig:
    """Scenarios for examples config branding."""

    def test_branding_title(self):
        """GIVEN the examples config."""
        cfg = _examples_config()
        title = cfg.get("branding", {}).get("title", "")

        """WHEN checking the branding title."""
        found = "AcmeBoard" in title

        """THEN AcmeBoard does not appear."""
        assert not found


class TestFaviconUsesLogo:
    """Scenarios for favicon using the app logo SVG."""

    def test_favicon_contains_branch_motif(self):
        """GIVEN the dashboard.html.j2 template."""
        html = (TEMPLATE_DIR / "dashboard.html.j2").read_text(encoding="utf-8")

        """WHEN checking the favicon link."""
        assert 'rel="icon"' in html
        match = re.search(r'href="data:image/svg\+xml,([^"]+)"', html)
        assert match, "Favicon must be an inline SVG data URI"
        svg_data = match.group(1)

        """THEN it contains the branch path motif, not 'RB' text."""
        assert "RB" not in svg_data, "Favicon should use logo icon, not 'RB' text"
        assert (
            "stroke-linecap" in svg_data or "M40" in svg_data
        ), "Favicon should contain branch paths"


class TestDefaultTemplateEngineering:
    """Scenarios for default template being 'engineering'."""

    def test_active_template_is_engineering(self):
        """GIVEN the editor script template."""
        html = _html()

        """WHEN checking the initial activeTemplate value."""
        match = re.search(r"let\s+activeTemplate\s*=\s*'([^']+)'", html)
        assert match, "activeTemplate declaration must exist"

        """THEN it defaults to 'engineering'."""
        assert match.group(1) == "engineering"


class TestEnvConnectorArrow:
    """Scenarios for env-connector rendered as arrow."""

    def test_env_connector_has_arrow_pseudo_element(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the env-connector CSS."""
        has_after = re.search(r"\.env-connector::after\s*\{", html)

        """THEN a ::after pseudo-element creates the arrowhead."""
        assert has_after, "env-connector must have ::after for arrow"

    def test_filled_connector_arrow_uses_primary(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking the filled arrow color."""
        has_filled_after = re.search(r"\.env-connector\.filled::after\s*\{[^}]*--primary", html)

        """THEN the filled arrow uses --primary color."""
        assert has_filled_after


class TestCfgAddBtnConsistentStyle:
    """Scenarios for cfg-add-btn matching global button design."""

    def test_hover_uses_primary_bg(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN extracting the cfg-add-btn:hover style block."""
        match = re.search(r"\.cfg-add-btn:hover\s*\{([^}]+)\}", html)
        assert match, "cfg-add-btn:hover style must exist"
        block = match.group(1)

        """THEN hover background is --primary and color is --text-inverse."""
        assert "var(--primary)" in block
        assert "var(--text-inverse)" in block

    def test_default_state_uses_secondary_bg(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN extracting the cfg-add-btn base style block."""
        match = re.search(r"\.cfg-add-btn\s*\{([^}]+)\}", html)
        assert match
        block = match.group(1)

        """THEN default background is --bg-secondary (consistent with tb-btn)."""
        assert "var(--bg-secondary)" in block


class TestCfgTooltipTrigger:
    """Scenarios for cfg-tooltip-trigger hover tooltip."""

    def test_tooltip_css_exists(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN scanning for cfg-tooltip-trigger CSS."""
        has_class = ".cfg-tooltip-trigger" in html

        """THEN the tooltip trigger style exists."""
        assert has_class

    def test_tooltip_shows_on_hover_via_after(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking for hover pseudo-element tooltip."""
        has_hover_after = re.search(r"\.cfg-tooltip-trigger:hover::after\s*\{", html)

        """THEN :hover::after creates the tooltip popup."""
        assert has_hover_after

    def test_tooltip_trigger_in_config_drawer(self):
        """GIVEN the config drawer template."""
        drawer = (TEMPLATE_DIR / "_config_drawer.html.j2").read_text(encoding="utf-8")

        """WHEN scanning for tooltip trigger elements."""
        found = "cfg-tooltip-trigger" in drawer

        """THEN the tooltip trigger element exists."""
        assert found

    def test_tooltip_uses_i18n(self):
        """GIVEN the config drawer template."""
        drawer = (TEMPLATE_DIR / "_config_drawer.html.j2").read_text(encoding="utf-8")

        """WHEN checking the tooltip i18n attribute."""
        found = "data-i18n-tooltip" in drawer

        """THEN data-i18n-tooltip is used for translated tooltip content."""
        assert found


class TestValidationErrorsTranslated:
    """Scenarios for validation error messages using i18n paths."""

    def test_target_year_error_uses_data_path_format(self):
        """GIVEN the editor script template."""
        html = _html()

        """WHEN checking the target_year validation error."""
        has_data_path = "release.target_year:" in html

        """THEN the data-path prefix is used for field matching."""
        assert has_data_path, "target_year error must use data-path format for inline field errors"

    def test_target_year_error_uses_translated_message(self):
        """GIVEN the editor script template."""
        html = _html()

        """WHEN checking for the translated message part."""
        found = "_t('ui.validation.target_year_past')" in html

        """THEN the translated message key is used."""
        assert found

    def test_repo_errors_use_data_path_format(self):
        """GIVEN the editor script template."""
        html = _html()

        """WHEN checking repository validation errors."""
        has_data_path = "repositories.${i}" in html

        """THEN data-path format 'repositories.N' is used for inline field matching."""
        assert has_data_path, "Repo validation must use data-path format for inline field errors"


class TestI18nTooltipHandler:
    """Scenarios for data-i18n-tooltip handler in head scripts."""

    def test_handler_exists(self):
        """GIVEN the head scripts template."""
        head = (TEMPLATE_DIR / "_head_scripts.html.j2").read_text(encoding="utf-8")

        """WHEN checking for data-i18n-tooltip handler."""
        found = "data-i18n-tooltip" in head

        """THEN a handler translates tooltip content."""
        assert found

    def test_handler_sets_data_tooltip(self):
        """GIVEN the head scripts template."""
        head = (TEMPLATE_DIR / "_head_scripts.html.j2").read_text(encoding="utf-8")

        """WHEN checking what the handler sets."""
        found = "setAttribute('data-tooltip'" in head or "data-tooltip" in head

        """THEN it sets data-tooltip attribute."""
        assert found


# ---------------------------------------------------------------------------
# Save-tab awareness
# ---------------------------------------------------------------------------

class TestSaveTabAwareness:
    """Scenarios for save/apply config tab-aware logic."""

    def test_save_checks_current_tab(self):
        """GIVEN the editor template with saveConfig function.
        WHEN the user is on the JSON tab and clicks save.
        THEN saveConfig should check currentTab instead of always calling readForm."""
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        assert "currentTab" in src, "saveConfig must reference currentTab"

    def test_apply_checks_current_tab(self):
        """GIVEN the editor template with applyConfig function.
        WHEN applyConfig is called.
        THEN it should respect the current tab to avoid stale form overwrites."""
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        # Both save and apply paths should reference currentTab
        lines = [line for line in src.splitlines() if "currentTab" in line]
        assert len(lines) >= 2, "Both saveConfig and applyConfig must check currentTab"


# ---------------------------------------------------------------------------
# toggleImportExample fix
# ---------------------------------------------------------------------------

class TestToggleImportExample:
    """Scenarios for toggleImportExample and rcExampleContent wrapper."""

    def test_rc_example_content_div_exists(self):
        """GIVEN the release calendar wizard template.
        WHEN rendering the import section.
        THEN rcExampleContent wrapper div must exist for the toggle function."""
        src = (TEMPLATE_DIR / "_release_calendar_wizard.html.j2").read_text(encoding="utf-8")
        assert "rcExampleContent" in src

    def test_rc_example_display_inside_wrapper(self):
        """GIVEN the release calendar wizard template.
        WHEN looking inside the rcExampleContent wrapper.
        THEN rcExampleDisplay element must be nested inside."""
        src = (TEMPLATE_DIR / "_release_calendar_wizard.html.j2").read_text(encoding="utf-8")
        # rcExampleDisplay should appear after rcExampleContent
        idx_wrapper = src.find("rcExampleContent")
        idx_display = src.find("rcExampleDisplay")
        assert idx_wrapper != -1 and idx_display != -1
        assert idx_wrapper < idx_display

    def test_toggle_function_targets_wrapper(self):
        """GIVEN the calendar ext scripts.
        WHEN toggleImportExample is called.
        THEN it should target rcExampleContent wrapper, not rcExampleDisplay."""
        src = (TEMPLATE_DIR / "_scripts_release_calendar_ext.html.j2").read_text(encoding="utf-8")
        assert "rcExampleContent" in src, "Toggle must target the wrapper div"


# ---------------------------------------------------------------------------
# rc-btn hover consistency
# ---------------------------------------------------------------------------

class TestRcBtnHover:
    """Scenarios for rc-btn hover using primary color."""

    def test_rc_btn_hover_uses_primary(self):
        """GIVEN the calendar styles.
        WHEN a user hovers over an rc-btn.
        THEN the background should use var(--primary)."""
        src = (TEMPLATE_DIR / "_styles_release_calendar.html.j2").read_text(encoding="utf-8")
        hover_line = next(
            (
                line for line in src.splitlines()
                if "rc-btn:hover" in line
                or ("rc-btn" in line and "hover" in line)
            ),
            None,
        )
        assert hover_line is not None, "rc-btn:hover rule must exist"
        # Check primary is used in the hover context
        idx = src.find("rc-btn:hover") or src.find("rc-btn")
        context = src[idx:idx + 200] if idx != -1 else ""
        assert "var(--primary)" in context or "var(--primary)" in hover_line


# ---------------------------------------------------------------------------
# Brand colors: company=primary, subtitle=secondary
# ---------------------------------------------------------------------------

class TestBrandColorSwap:
    """Scenarios for brand-company and brand-subtitle color assignment."""

    def test_brand_company_primary(self):
        """GIVEN the styles template.
        WHEN checking .brand-company color.
        THEN it should use var(--primary)."""
        src = (TEMPLATE_DIR / "_styles.html.j2").read_text(encoding="utf-8")
        line = next(
            (ln for ln in src.splitlines()
             if ".brand-company" in ln and "color:" in ln),
            None,
        )
        assert line is not None
        assert "var(--primary)" in line

    def test_brand_subtitle_secondary(self):
        """GIVEN the styles template.
        WHEN checking .brand-subtitle color.
        THEN it should use var(--text-secondary)."""
        src = (TEMPLATE_DIR / "_styles.html.j2").read_text(encoding="utf-8")
        line = next(
            (ln for ln in src.splitlines()
             if ".brand-subtitle" in ln and "color:" in ln),
            None,
        )
        assert line is not None
        assert "var(--text-secondary)" in line

    def test_brand_subtitle_centered(self):
        """GIVEN the styles template.
        WHEN checking .brand-subtitle.
        THEN it should be centered under brand-company."""
        src = (TEMPLATE_DIR / "_styles.html.j2").read_text(encoding="utf-8")
        line = next((ln for ln in src.splitlines() if ".brand-subtitle" in ln), None)
        assert line is not None
        assert "text-align: center" in line


# ---------------------------------------------------------------------------
# tb-caret font size
# ---------------------------------------------------------------------------

class TestTbCaretSize:
    """Scenarios for toolbar caret icon size."""

    def test_tb_caret_font_size_18px(self):
        """GIVEN the toolbar styles template.
        WHEN checking the .tb-caret rule.
        THEN font-size should be 18px for consistent visibility with other toolbar elements."""
        src = (TEMPLATE_DIR / "_styles_toolbar.html.j2").read_text(encoding="utf-8")
        line = next((ln for ln in src.splitlines() if "tb-caret" in ln), None)
        assert line is not None
        assert "18px" in line


# ---------------------------------------------------------------------------
# Order column fixed width
# ---------------------------------------------------------------------------

class TestOrderColumnWidth:
    """Scenarios for the order column fixed width to prevent label overflow."""

    def test_order_field_fixed_width(self):
        """GIVEN the config UI template.
        WHEN checking the order field flex property.
        THEN it should use a fixed width (72px) via inline or CSS class."""
        src_script = (TEMPLATE_DIR / "_scripts_config_ui.html.j2").read_text(encoding="utf-8")
        src_styles = (TEMPLATE_DIR / "_styles.html.j2").read_text(encoding="utf-8")
        # 72px width must exist either inline in JS or as a CSS class
        has_inline = "72px" in src_script
        has_css_class = "72px" in src_styles and "cfg-flex-72" in src_styles
        assert has_inline or has_css_class, (
            "Order field must have a fixed 72px width"
            " (inline or via CSS class)"
        )


# ---------------------------------------------------------------------------
# README logo visibility
# ---------------------------------------------------------------------------

class TestReadmeLogoVisibility:
    """Scenarios for logo SVG color visibility on dark backgrounds."""

    def test_release_text_not_dark(self):
        """GIVEN the full logo SVG.
        WHEN checking the color of the 'Release' text.
        THEN it should NOT use a dark color that's invisible on dark backgrounds."""
        logo = (ROOT / "docs" / "assets" / "logo-full.svg").read_text(encoding="utf-8")
        assert "#1a1a2e" not in logo, "Dark text color #1a1a2e is invisible on dark backgrounds"


# ---------------------------------------------------------------------------
# Calendar Edit/Delete buttons
# ---------------------------------------------------------------------------

class TestCalendarEditDelete:
    """Scenarios for calendar toolbar edit and delete buttons."""

    def test_edit_button_exists(self):
        """GIVEN the header template.
        WHEN checking the calendar dropdown.
        THEN a dedicated Edit Calendar button should exist."""
        src = (TEMPLATE_DIR / "_header.html.j2").read_text(encoding="utf-8")
        assert "btnEditCalendar" in src

    def test_delete_button_exists(self):
        """GIVEN the header template.
        WHEN checking the calendar dropdown.
        THEN a Delete Calendar button should exist."""
        src = (TEMPLATE_DIR / "_header.html.j2").read_text(encoding="utf-8")
        assert "btnDeleteCalendar" in src

    def test_edit_calendar_function_on_rc(self):
        """GIVEN the calendar scripts.
        WHEN checking the RC public API.
        THEN editCalendar should be exposed."""
        src = (TEMPLATE_DIR / "_scripts_release_calendar.html.j2").read_text(encoding="utf-8")
        assert "editCalendar" in src

    def test_manage_section_hidden_by_default(self):
        """GIVEN the header template with calendar dropdown.
        WHEN the page first loads (no calendar data).
        THEN edit/delete buttons and manage label should be hidden."""
        src = (TEMPLATE_DIR / "_header.html.j2").read_text(encoding="utf-8")
        # All manage items should be hidden initially (class="hidden" or display:none)
        assert 'id="btnEditCalendar"' in src
        edit_line = next(ln for ln in src.splitlines() if "btnEditCalendar" in ln)
        assert "hidden" in edit_line or "display:none" in edit_line

    def test_ext_shows_manage_when_data_exists(self):
        """GIVEN the calendar ext scripts.
        WHEN calendar data is loaded from server.
        THEN the edit/delete buttons should be shown."""
        src = (TEMPLATE_DIR / "_scripts_release_calendar_ext.html.j2").read_text(encoding="utf-8")
        assert "btnEditCalendar" in src, "Ext script must show the edit button"
        assert "rcManageLabel" in src, "Ext script must show the manage label"


# ---------------------------------------------------------------------------
# i18n keys for calendar manage section
# ---------------------------------------------------------------------------

class TestCalendarI18nKeys:
    """Scenarios for calendar manage section i18n keys."""

    def test_en_has_manage_key(self):
        """GIVEN the English locale.
        WHEN checking for ui.tb.manage key.
        THEN the key should exist."""
        _locale = ROOT / "src" / "releaseboard" / "i18n" / "locales"
        data = json.loads(
            (_locale / "en.json").read_text(encoding="utf-8"),
        )
        assert "ui.tb.manage" in data

    def test_pl_has_manage_key(self):
        """GIVEN the Polish locale.
        WHEN checking for ui.tb.manage key.
        THEN the key should exist."""
        _locale = ROOT / "src" / "releaseboard" / "i18n" / "locales"
        data = json.loads(
            (_locale / "pl.json").read_text(encoding="utf-8"),
        )
        assert "ui.tb.manage" in data

    def test_en_has_delete_title(self):
        """GIVEN the English locale.
        WHEN checking for rc.delete.title key.
        THEN the key should exist for the delete button label."""
        _locale = ROOT / "src" / "releaseboard" / "i18n" / "locales"
        data = json.loads(
            (_locale / "en.json").read_text(encoding="utf-8"),
        )
        assert "rc.delete.title" in data

    def test_en_has_edit_no_calendar(self):
        """GIVEN the English locale.
        WHEN checking for rc.edit.no_calendar key.
        THEN the key should exist for the empty state message."""
        _locale = ROOT / "src" / "releaseboard" / "i18n" / "locales"
        data = json.loads(
            (_locale / "en.json").read_text(encoding="utf-8"),
        )
        assert "rc.edit.no_calendar" in data
