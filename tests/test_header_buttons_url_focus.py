"""Tests for header UI components — company name rendering, milestone filter
translations, URL field focus preservation, action button styling,
and consistent hover behavior with primary color."""

import json
from pathlib import Path

import pytest

from releaseboard.i18n import t

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "releaseboard" / "presentation" / "templates"
LOCALES_DIR = Path(__file__).parent.parent / "src" / "releaseboard" / "i18n" / "locales"


def _read(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _load_catalog(locale: str) -> dict:
    return json.loads((LOCALES_DIR / f"{locale}.json").read_text("utf-8"))


class TestCompanyNameInHeader:
    """Scenarios for company name rendering in the dashboard header."""

    def test_header_renders_company(self):
        """GIVEN the _header template."""
        src = _read("_header.html.j2")

        """WHEN checking for company display elements."""
        has_vm_company = "vm.company" in src
        has_brand_class = 'class="brand-company"' in src
        has_brand_id = 'id="brandCompany"' in src

        """THEN it should render vm.company in a brand-company div."""
        assert has_vm_company
        assert has_brand_class
        assert has_brand_id

    def test_company_appears_before_subtitle(self):
        """GIVEN the _header template."""
        src = _read("_header.html.j2")

        """WHEN locating brand-company and brand-subtitle positions."""
        company_pos = src.index("brand-company")
        subtitle_pos = src.index("brand-subtitle")

        """THEN brand-company should appear before brand-subtitle."""
        assert company_pos < subtitle_pos

    def test_company_css_bigger_bolder(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the .brand-company CSS rule."""
        rule_line = next(
            (ln for ln in src.splitlines()
             if ".brand-company" in ln and "{" in ln),
            None,
        )

        """THEN it should have larger font-size and bold weight."""
        assert rule_line is not None, ".brand-company CSS rule not found"
        assert "font-size: 18px" in rule_line
        assert "font-weight: 700" in rule_line

    def test_company_hidden_on_small_screens(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN checking responsive rules for brand-info."""
        found = ".brand-info { display: none; }" in src

        """THEN brand-info should be hidden on small screens."""
        assert found

    def test_brand_info_is_flex_column(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the .brand-info CSS rule."""
        rule_line = next(
            (ln for ln in src.splitlines()
             if ".brand-info" in ln and "flex-direction" in ln),
            None,
        )

        """THEN it should use flex-direction: column for vertical stacking."""
        assert rule_line is not None, ".brand-info flex-direction rule not found"
        assert "flex-direction: column" in rule_line

    def test_brand_company_uses_primary_color(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the .brand-company CSS rule."""
        rule_line = next(
            (ln for ln in src.splitlines()
             if ".brand-company" in ln and "color:" in ln),
            None,
        )

        """THEN company should use the primary color variable."""
        assert rule_line is not None
        assert "var(--primary)" in rule_line

    def test_brand_subtitle_uses_secondary_color(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the .brand-subtitle CSS rule."""
        rule_line = next(
            (ln for ln in src.splitlines()
             if ".brand-subtitle" in ln and "color:" in ln),
            None,
        )

        """THEN subtitle should use the text-secondary color variable."""
        assert rule_line is not None
        assert "var(--text-secondary)" in rule_line

    def test_brand_info_wraps_company_and_subtitle(self):
        """GIVEN the _header template."""
        src = _read("_header.html.j2")

        """WHEN checking for brand-info container around company and subtitle."""
        has_brand_info = 'class="brand-info"' in src

        """THEN brand-info wrapper should exist."""
        assert has_brand_info

    def test_quicksettings_syncs_company_live(self):
        """GIVEN the _quick_settings template."""
        src = _read("_quick_settings.html.j2")

        """WHEN checking the save handler for company sync."""
        has_brand_company = "brandCompany" in src
        has_body_company = "body.company" in src

        """THEN it should update brandCompany element live."""
        assert has_brand_company
        assert has_body_company


class TestEnvViewSelectTranslation:
    """Scenarios for milestone filter select i18n."""

    VIEW_KEYS = [
        "ui.milestones.view_all",
        "ui.milestones.view_key",
        "ui.milestones.view_enterprise",
        "ui.milestones.view_legacy",
    ]

    def test_select_options_have_data_i18n(self):
        """GIVEN the env-view-select in _dashboard_content."""
        src = _read("_dashboard_content.html.j2")

        """WHEN checking option elements for data-i18n attributes."""
        missing_keys = [key for key in self.VIEW_KEYS if f'data-i18n="{key}"' not in src]

        """THEN each should have data-i18n attribute."""
        assert not missing_keys, (
            f"Missing data-i18n for {missing_keys} in env-view-select"
        )

    def test_keys_exist_en(self):
        """GIVEN the English catalog."""
        cat = _load_catalog("en")

        """WHEN checking milestone view keys."""
        missing = [key for key in self.VIEW_KEYS if key not in cat]

        """THEN all should exist."""
        assert not missing, f"Missing EN keys: {missing}"

    def test_keys_exist_pl(self):
        """GIVEN the Polish catalog."""
        cat = _load_catalog("pl")

        """WHEN checking milestone view keys."""
        missing = [key for key in self.VIEW_KEYS if key not in cat]

        """THEN all should exist."""
        assert not missing, f"Missing PL keys: {missing}"

    def test_pl_translations_are_polish(self):
        """GIVEN the Polish locale."""
        locale = "pl"

        """WHEN translating view_all."""
        result = t("ui.milestones.view_all", locale=locale)

        """THEN it should be in Polish."""
        assert "milowe" in result.lower()


class TestUrlFieldFocusPreservation:
    """Scenarios for URL/Slug input focus during auto-name derivation."""

    def test_autofill_does_not_call_renderrepos(self):
        """GIVEN the autoFillRepoName function in _scripts_config_ui."""
        src = _read("_scripts_config_ui.html.j2")

        """WHEN extracting the autoFillRepoName function body."""
        start = src.index("function autoFillRepoName")
        end = src.index("\n  }", start) + 4
        func_body = src[start:end]

        """THEN it should NOT call renderRepos() which destroys DOM."""
        assert "renderRepos()" not in func_body, (
            "autoFillRepoName still calls renderRepos(), which destroys the URL input"
        )

    def test_autofill_updates_name_in_place(self):
        """GIVEN the autoFillRepoName function."""
        src = _read("_scripts_config_ui.html.j2")

        """WHEN searching for direct DOM update pattern."""
        found = "querySelector('[data-path=\"repositories.'+i+'.name\"]')" in src

        """THEN it should update the name input element directly."""
        assert found

    def test_url_input_has_oninput_handler(self):
        """GIVEN the repo accordion template."""
        src = _read("_scripts_config_ui.html.j2")

        """WHEN checking the URL/Slug input for oninput handler."""
        found = "oninput=\"RB.autoFillRepoName(" in src

        """THEN it should have oninput for live auto-fill."""
        assert found


class TestRpActionBtnStyle:
    """Scenarios for Release Notes (rp-action-btn) button styling."""

    def test_rp_action_btn_css_exists(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN checking for .rp-action-btn rule."""
        found = ".rp-action-btn {" in src or ".rp-action-btn{" in src

        """THEN the rule should exist with display, padding, border."""
        assert found

    def test_rp_action_btn_has_background(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the .rp-action-btn base rule."""
        rule_line = next(
            (ln for ln in src.splitlines()
             if ".rp-action-btn {" in ln
             or ".rp-action-btn{" in ln),
            None,
        )

        """THEN it should have a background property."""
        assert rule_line is not None, ".rp-action-btn base rule not found"
        assert "background:" in rule_line

    def test_rp_action_btn_hover_uses_primary(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the .rp-action-btn:hover rule."""
        hover_line = next((ln for ln in src.splitlines() if ".rp-action-btn:hover" in ln), None)

        """THEN it should use primary color."""
        assert hover_line is not None, ".rp-action-btn:hover rule not found"
        assert "var(--primary)" in hover_line


class TestButtonHoverConsistency:
    """Scenarios for unified primary-color hover across all button types."""

    BUTTON_SELECTORS = [
        ".tb-btn:hover",
        ".row-action-btn:hover",
        ".rp-action-btn:hover",
        ".filter-reset:hover",
        ".layout-template-btn:hover",
        ".cfg-add-btn:hover",
    ]

    def test_all_standard_buttons_hover_primary(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN extracting hover rule lines."""
        lines = src.splitlines()

        """THEN each standard button hover should reference var(--primary)."""
        for selector in self.BUTTON_SELECTORS:
            for line in lines:
                if selector in line:
                    assert "var(--primary)" in line, (
                        f"{selector} hover does not use primary color"
                    )
                    break
            else:
                pytest.fail(f"{selector} hover rule not found")

    def test_danger_buttons_hover_red(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the danger button hover rule."""
        danger_line = next(
            (ln for ln in src.splitlines()
             if ".row-action-btn.danger:hover" in ln),
            None,
        )

        """THEN it should use explicit red for destructive actions, not brand primary."""
        assert danger_line is not None, ".row-action-btn.danger:hover rule not found"
        assert "#DC2626" in danger_line

    def test_primary_btn_hover_brightens(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the .tb-btn.primary:hover rule."""
        rule_line = next((ln for ln in src.splitlines() if ".tb-btn.primary:hover" in ln), None)

        """THEN it should use brightness filter, not opacity."""
        assert rule_line is not None, ".tb-btn.primary:hover rule not found"
        assert "brightness" in rule_line

    def test_confirm_btn_danger_uses_red(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the .confirm-btn.danger CSS rule."""
        rule_line = next((ln for ln in src.splitlines() if ".confirm-btn.danger {" in ln), None)

        """THEN it should use explicit red for destructive modal actions."""
        assert rule_line is not None, ".confirm-btn.danger rule not found"
        assert "#DC2626" in rule_line

    def test_confirm_btn_cancel_hover_primary(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN finding the .confirm-btn.cancel:hover CSS rule."""
        rule_line = next((ln for ln in src.splitlines() if ".confirm-btn.cancel:hover" in ln), None)

        """THEN cancel hover should use primary color."""
        assert rule_line is not None, ".confirm-btn.cancel:hover rule not found"
        assert "var(--primary)" in rule_line


class TestI18nParityV3:
    """Scenarios for i18n catalog key parity after adding milestone view keys."""

    def test_catalogs_same_key_count(self):
        """GIVEN both locale catalogs."""
        en = _load_catalog("en")
        pl = _load_catalog("pl")

        """WHEN comparing key counts."""
        en_count = len(en)
        pl_count = len(pl)

        """THEN they should be equal."""
        assert en_count == pl_count, (
            f"Key count mismatch: EN={en_count}, PL={pl_count}"
        )

    def test_no_missing_keys_in_pl(self):
        """GIVEN both catalogs."""
        en = _load_catalog("en")
        pl = _load_catalog("pl")

        """WHEN checking for keys in EN missing from PL."""
        missing = set(en.keys()) - set(pl.keys())

        """THEN none should be missing."""
        assert not missing, f"Keys in EN missing from PL: {missing}"
