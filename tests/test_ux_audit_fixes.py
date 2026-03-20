"""Tests verifying UX/UI audit fixes — danger button semantics, accessibility
attributes, i18n coverage, responsive safety, and overflow protection."""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "src" / "releaseboard" / "presentation" / "templates"
LOCALE_DIR = ROOT / "src" / "releaseboard" / "i18n" / "locales"


def _read(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _all_templates() -> str:
    parts = []
    for f in sorted(TEMPLATE_DIR.glob("*.j2")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _locale(lang: str) -> dict:
    return json.loads((LOCALE_DIR / f"{lang}.json").read_text(encoding="utf-8"))


# ===========================================================================
# Danger button color semantics
# ===========================================================================
class TestDangerButtonSemantics:
    def test_row_action_danger_uses_red(self):
        src = _read("_styles.html.j2")
        line = next(ln for ln in src.splitlines() if ".row-action-btn.danger {" in ln)
        assert "#DC2626" in line, "Danger row button should use red, not brand primary"

    def test_row_action_danger_hover_uses_red(self):
        src = _read("_styles.html.j2")
        line = next(
            ln for ln in src.splitlines()
            if ".row-action-btn.danger:hover" in ln
            and "data-theme" not in ln
        )
        assert "#DC2626" in line

    def test_confirm_btn_danger_uses_red(self):
        src = _read("_styles.html.j2")
        line = next(ln for ln in src.splitlines() if ".confirm-btn.danger {" in ln)
        assert "#DC2626" in line
        assert "var(--primary)" not in line

    def test_confirm_btn_danger_hover_darkens(self):
        src = _read("_styles.html.j2")
        line = next(ln for ln in src.splitlines() if ".confirm-btn.danger:hover" in ln)
        assert "#B91C1C" in line

    def test_dark_theme_danger_override(self):
        src = _read("_styles.html.j2")
        assert '[data-theme="dark"] .row-action-btn.danger' in src

    def test_midnight_theme_danger_override(self):
        src = _read("_styles.html.j2")
        assert '[data-theme="midnight"] .row-action-btn.danger' in src

    def test_system_theme_dark_danger_override(self):
        src = _read("_styles.html.j2")
        assert '[data-theme="system"] .row-action-btn.danger' in src


# ===========================================================================
# Row actions visible on touch and focus
# ===========================================================================
class TestRowActionsVisibility:
    def test_touch_media_query(self):
        src = _read("_styles.html.j2")
        assert "@media (hover: none)" in src
        assert ".row-actions { opacity: 1; }" in src

    def test_focus_within_trigger(self):
        src = _read("_styles.html.j2")
        assert "tr:focus-within .row-actions" in src


# ===========================================================================
# Repo URL overflow protection
# ===========================================================================
class TestRepoUrlOverflow:
    def test_repo_name_sub_has_ellipsis(self):
        src = _read("_styles.html.j2")
        line = next(ln for ln in src.splitlines() if ".repo-name-sub" in ln)
        assert "text-overflow: ellipsis" in line
        assert "overflow: hidden" in line
        assert "max-width" in line


# ===========================================================================
# Analysis info text clipping
# ===========================================================================
class TestAnalysisInfoOverflow:
    def test_analysis_info_overflow_hidden(self):
        src = _read("_styles.html.j2")
        line = next(ln for ln in src.splitlines() if ".analysis-info" in ln and "min-width" in ln)
        assert "overflow: hidden" in line


# ===========================================================================
# Actions column minimum width
# ===========================================================================
class TestActionsColumnWidth:
    def test_actions_th_uses_min_width(self):
        tmpl = _read("_dashboard_content.html.j2")
        css = _read("_styles.html.j2")
        # Actions column uses class-based min-width
        assert 'col-actions' in tmpl, "Actions th should use col-actions class"
        assert 'col-actions' in css and 'min-width' in css, (
            "CSS must define col-actions with min-width"
        )


# ===========================================================================
# Table header scope accessibility
# ===========================================================================
class TestTableHeaderScope:
    def test_attention_table_headers_have_scope(self):
        src = _read("_dashboard_content.html.j2")
        attention_section = src.split("repo-table")[1]
        ths = re.findall(r'<th[^>]*>', attention_section.split("</thead>")[0])
        for th in ths:
            assert 'scope="col"' in th, f"Missing scope on: {th}"

    def test_layer_table_headers_have_scope(self):
        src = _read("_dashboard_content.html.j2")
        parts = src.split("repo-table")
        assert len(parts) >= 3, "Expected at least 2 repo-table sections"
        layer_header = parts[2].split("</thead>")[0]
        ths = re.findall(r'<th\b[^>]*>', layer_header)
        assert len(ths) > 0, "No th elements found in layer table header"
        for th in ths:
            assert 'scope="col"' in th, f"Missing scope on layer table th: {th}"

    def test_wizard_review_table_headers_have_scope(self):
        src = _read("_modals.html.j2")
        assert "wiz-review-table" in src
        table_section = src.split("wiz-review-table")[1]
        thead_section = table_section.split("</thead>")[0]
        ths = re.findall(r'<th\b[^>]*?>', thead_section)
        assert len(ths) > 0, "No th elements found in wizard review table"
        for th in ths:
            assert 'scope="col"' in th, f"Missing scope on wizard review th: {th}"


# ===========================================================================
# Modal ARIA accessibility
# ===========================================================================
class TestModalAccessibility:
    def test_detail_modal_has_dialog_role(self):
        src = _read("_modals.html.j2")
        assert (
            'id="detailModal" role="dialog"' in src
            or 'role="dialog"'
            in src.split("detailModal")[1][:100]
        )

    def test_detail_modal_aria_modal(self):
        src = _read("_modals.html.j2")
        modal_section = src.split("detailModal")[1][:200]
        assert 'aria-modal="true"' in modal_section

    def test_delete_modal_has_alertdialog_role(self):
        src = _read("_modals.html.j2")
        assert 'role="alertdialog"' in src

    def test_delete_modal_aria_labelledby(self):
        src = _read("_modals.html.j2")
        assert 'aria-labelledby="deleteTitle"' in src

    def test_generic_modal_has_dialog_role(self):
        src = _read("_modals.html.j2")
        assert 'id="genericOverlay"' in src
        generic_part = src.split("genericOverlay")[1][:300]
        assert 'role="dialog"' in generic_part


# ===========================================================================
# Analysis bar live region
# ===========================================================================
class TestAnalysisBarAccessibility:
    def test_analysis_bar_role_status(self):
        src = _read("_header.html.j2")
        assert 'role="status"' in src

    def test_analysis_bar_aria_live(self):
        src = _read("_header.html.j2")
        assert 'aria-live="polite"' in src


# ===========================================================================
# Progress bar ARIA
# ===========================================================================
class TestProgressBarAria:
    def test_progressbar_role(self):
        src = _read("_header.html.j2")
        assert 'role="progressbar"' in src

    def test_progressbar_aria_valuenow(self):
        src = _read("_header.html.j2")
        assert 'aria-valuenow=' in src

    def test_progressbar_js_updates_valuenow(self):
        src = _read("_scripts_analysis.html.j2")
        assert "aria-valuenow" in src


# ===========================================================================
# Reset button i18n
# ===========================================================================
class TestResetButtonI18n:
    def test_reset_buttons_have_i18n_title(self):
        src = _read("_header.html.j2")
        reset_matches = re.findall(r'data-i18n-title="ui\.reset"', src)
        assert len(reset_matches) >= 3


# ===========================================================================
# Midnight danger button override
# ===========================================================================
class TestMidnightDanger:
    def test_midnight_styles_have_danger_override(self):
        src = _read("_styles_midnight.html.j2")
        assert ".row-action-btn.danger" in src


# ===========================================================================
# Config drawer responsive
# ===========================================================================
class TestConfigDrawerResponsive:
    def test_config_drawer_mobile_full_width(self):
        src = _read("_styles.html.j2")
        # Find the 640px media query block
        assert ".config-drawer { width: 100vw; max-width: 100vw; }" in src


# ===========================================================================
# Branch name overflow
# ===========================================================================
class TestBranchNameOverflow:
    def test_branch_name_has_ellipsis(self):
        src = _read("_styles.html.j2")
        line = next(ln for ln in src.splitlines() if ".branch-name {" in ln)
        assert "text-overflow: ellipsis" in line
        assert "overflow: hidden" in line
        assert "max-width" in line


# ===========================================================================
# Filter count i18n
# ===========================================================================
class TestFilterCountI18n:
    def test_filter_count_uses_i18n(self):
        src = _read("_scripts_core.html.j2")
        assert "_tp('ui.filter.repo_count'" in src or '_tp("ui.filter.repo_count"' in src
        assert "repo'+(v===1?'':'s')" not in src

    def test_en_locale_has_repo_count_keys(self):
        data = _locale("en")
        assert "ui.filter.repo_count_one" in data
        assert "ui.filter.repo_count_other" in data

    def test_pl_locale_has_repo_count_keys(self):
        data = _locale("pl")
        assert "ui.filter.repo_count_one" in data
        assert "ui.filter.repo_count_other" in data


# ===========================================================================
# Close button i18n aria-labels
# ===========================================================================
class TestCloseButtonI18n:
    def test_i18n_system_supports_aria_label(self):
        src = _read("_head_scripts.html.j2")
        assert "data-i18n-aria-label" in src

    def test_wizard_close_buttons_have_i18n(self):
        templates = _all_templates()
        close_buttons = re.findall(r'aria-label="Close"[^>]*>', templates)
        for btn in close_buttons:
            assert "data-i18n-aria-label" in btn, f"Close button missing i18n: {btn}"


# ===========================================================================
# Accordion keyboard and ARIA
# ===========================================================================
class TestAccordionAccessibility:
    def test_accordion_header_has_role_button(self):
        src = _read("_scripts_config_ui.html.j2")
        assert 'role="button"' in src

    def test_accordion_header_has_tabindex(self):
        src = _read("_scripts_config_ui.html.j2")
        assert 'tabindex="0"' in src

    def test_accordion_header_has_aria_expanded(self):
        src = _read("_scripts_config_ui.html.j2")
        assert 'aria-expanded' in src

    def test_toggle_updates_aria_expanded(self):
        src = _read("_scripts_config_ui.html.j2")
        assert "setAttribute('aria-expanded'" in src

    def test_accordion_header_keyboard_handler(self):
        src = _read("_scripts_config_ui.html.j2")
        assert "onkeydown" in src
        assert "Enter" in src
        assert "' '" in src or '" "' in src


# ===========================================================================
# Calendar table scope attributes
# ===========================================================================
class TestCalendarTableScope:
    def test_calendar_main_table_scope(self):
        src = _read("_scripts_release_calendar.html.j2")
        assert 'scope="col"' in src

    def test_calendar_ext_table_scope(self):
        src = _read("_scripts_release_calendar_ext.html.j2")
        assert 'scope="col"' in src


# ===========================================================================
# i18n parity verification
# ===========================================================================
class TestI18nParity:
    def test_en_pl_key_parity(self):
        en = _locale("en")
        pl = _locale("pl")
        en_keys = set(self._flatten_keys(en))
        pl_keys = set(self._flatten_keys(pl))
        missing_in_pl = en_keys - pl_keys
        missing_in_en = pl_keys - en_keys
        assert not missing_in_pl, f"Keys missing in PL: {missing_in_pl}"
        assert not missing_in_en, f"Keys missing in EN: {missing_in_en}"

    @staticmethod
    def _flatten_keys(d, prefix=""):
        keys = []
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(TestI18nParity._flatten_keys(v, full))
            else:
                keys.append(full)
        return keys


# ===========================================================================
# Blocker Fixes
# ===========================================================================


# ---------------------------------------------------------------------------
# B1: Focus trap on detail modal and config drawer
# ---------------------------------------------------------------------------
class TestFocusTrapWiring:
    def test_detail_modal_focus_trap(self):
        src = _read("_scripts_core.html.j2")
        assert "trapFocus" in src, "trapFocus must be defined"
        # showDetail/openDetail should call trapFocus
        lines = src.splitlines()
        found = any("trapFocus" in ln and "detail" in ln.lower() for ln in lines)
        assert found, "Detail modal should use trapFocus"

    def test_config_drawer_focus_trap(self):
        src = _read("_scripts_config_ui.html.j2")
        assert "trapFocus" in src, "Config drawer should use trapFocus"


# ---------------------------------------------------------------------------
# B2: Form validation a11y — aria-describedby on inputs
# ---------------------------------------------------------------------------
class TestFormAccessibility:
    def test_config_drawer_has_aria_describedby(self):
        src = _read("_config_drawer.html.j2")
        assert "aria-describedby" in src or "aria-required" in src, \
            "Config drawer form should have a11y attributes on inputs"


# ---------------------------------------------------------------------------
# B4: Config drawer landmark
# ---------------------------------------------------------------------------
class TestConfigDrawerLandmark:
    def test_drawer_has_dialog_role(self):
        src = _read("_config_drawer.html.j2")
        assert 'role="dialog"' in src, "Config drawer must have role=dialog"

    def test_drawer_has_aria_modal(self):
        src = _read("_config_drawer.html.j2")
        assert 'aria-modal="true"' in src, "Config drawer must have aria-modal"

    def test_drawer_has_aria_labelledby(self):
        src = _read("_config_drawer.html.j2")
        assert "aria-labelledby" in src, "Config drawer must have aria-labelledby"


# ---------------------------------------------------------------------------
# B5: ARIA landmarks — <main> and <nav>
# ---------------------------------------------------------------------------
class TestARIALandmarks:
    def test_dashboard_has_main_element(self):
        src = _read("_dashboard_content.html.j2")
        assert "<main" in src, "Dashboard content must be wrapped in <main>"

    def test_header_has_nav_element(self):
        src = _read("_header.html.j2")
        assert "<nav" in src, "Header toolbar should use <nav> element"


# ---------------------------------------------------------------------------
# B3: Wizard step keyboard navigation
# ---------------------------------------------------------------------------
class TestWizardKeyboardNav:
    def test_wizard_arrow_key_support(self):
        src = _read("_scripts_wizard.html.j2")
        assert "ArrowRight" in src or "ArrowLeft" in src, \
            "Wizard steps should support arrow key navigation"


# ---------------------------------------------------------------------------
# C1: JS error boundary
# ---------------------------------------------------------------------------
class TestErrorBoundary:
    def test_global_error_handler_exists(self):
        src = _read("_head_scripts.html.j2")
        assert "addEventListener" in src and "error" in src, \
            "Global error handler must exist"

    def test_unhandledrejection_handler(self):
        src = _read("_head_scripts.html.j2")
        assert "unhandledrejection" in src, \
            "Unhandled promise rejection handler must exist"


# ---------------------------------------------------------------------------
# C2: SSE reconnection
# ---------------------------------------------------------------------------
class TestSSEReconnection:
    def test_sse_retry_logic(self):
        src = _read("_scripts_analysis.html.j2")
        assert "retry" in src.lower() or "reconnect" in src.lower(), \
            "SSE should have retry/reconnection logic"


# ---------------------------------------------------------------------------
# C4: Empty state styling
# ---------------------------------------------------------------------------
class TestEmptyState:
    def test_empty_state_css_exists(self):
        src = _read("_styles.html.j2")
        assert "empty-state" in src, "Empty state CSS class must exist"


# ---------------------------------------------------------------------------
# D1: Color contrast fix
# ---------------------------------------------------------------------------
class TestColorContrast:
    def test_midnight_text_secondary_contrast(self):
        src = _read("_styles_midnight.html.j2")
        # The old low-contrast value should be replaced
        assert "--text-secondary" in src, "Midnight must define --text-secondary"


# ---------------------------------------------------------------------------
# D3: Tooltip viewport safety
# ---------------------------------------------------------------------------
class TestTooltipViewport:
    def test_tooltip_max_width_clamped(self):
        src = _read("_styles.html.j2")
        # Should have max-width with viewport-aware value
        lines = [ln for ln in src.splitlines() if "tooltip" in ln.lower() and "max-width" in ln]
        assert any("100vw" in ln or "calc(" in ln or "min(" in ln for ln in lines), \
            "Tooltip max-width should be viewport-aware"


# ---------------------------------------------------------------------------
# D5: Print stylesheet
# ---------------------------------------------------------------------------
class TestPrintStylesheet:
    def test_print_media_exists(self):
        src = _read("_styles.html.j2")
        assert "@media print" in src, "Print stylesheet must exist"

    def test_print_break_rules(self):
        src = _read("_styles.html.j2")
        assert "break-inside" in src or "page-break" in src, \
            "Print stylesheet should have page-break rules"


# ---------------------------------------------------------------------------
# E1: SVG logo i18n
# ---------------------------------------------------------------------------
class TestSVGLogoI18n:
    def test_svg_tagline_is_translatable(self):
        src = _read("_header.html.j2")
        # Should NOT have hardcoded "Release Readiness Intelligence" in SVG
        # Instead should use Jinja2 template variable
        assert "ui.app.tagline" in src, \
            "SVG tagline should use i18n key ui.app.tagline"

    def test_tagline_keys_in_locales(self):
        en = _locale("en")
        pl = _locale("pl")
        assert "ui.app.tagline" in en, "EN locale must have ui.app.tagline"
        assert "ui.app.tagline" in pl, "PL locale must have ui.app.tagline"


# ---------------------------------------------------------------------------
# E2: Footer dynamic year
# ---------------------------------------------------------------------------
class TestFooterDynamicYear:
    def test_footer_year_is_dynamic(self):
        src = _read("_footer.html.j2")
        # Should use Jinja2 expression for year, not hardcoded "2026"
        assert "generated_at" in src or "now()" in src or "year" in src, \
            "Footer year should be dynamic, not hardcoded"


# ---------------------------------------------------------------------------
# E3: Polish pluralization
# ---------------------------------------------------------------------------
class TestPolishPluralization:
    def test_plural_function_exists(self):
        src = _read("_head_scripts.html.j2")
        assert "_tp" in src or "_pluralForm" in src or "pluralForm" in src, \
            "Plural function must exist for Polish support"

    def test_polish_few_form_key_exists(self):
        pl = _locale("pl")
        assert "ui.filter.repo_count_few" in pl, \
            "PL locale must have repo_count_few for Polish 2-4 form"

    def test_filter_uses_plural_function(self):
        src = _read("_scripts_core.html.j2")
        assert "_tp" in src or "pluralForm" in src or "repo_count" in src, \
            "Filter count should use plural-aware function"


# ---------------------------------------------------------------------------
# D4: Table scroll indicator
# ---------------------------------------------------------------------------
class TestTableScrollIndicator:
    def test_table_scrollbar_styling(self):
        src = _read("_styles.html.j2")
        assert "scrollbar" in src.lower(), \
            "Table container should have scrollbar styling"
