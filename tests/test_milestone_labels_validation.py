"""Tests for milestone labels, field validation, and UI controls — i18n label
translation, README logo presence, dashboard loading overlay, target year
validation, release name validation, order field bounds, and disabled button
hover styling."""

import json
from pathlib import Path

from releaseboard.i18n import t

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "releaseboard" / "presentation" / "templates"
LOCALES_DIR = Path(__file__).parent.parent / "src" / "releaseboard" / "i18n" / "locales"


def _read(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _load_catalog(locale: str) -> dict:
    return json.loads((LOCALES_DIR / f"{locale}.json").read_text("utf-8"))


class TestMilestoneLabelTranslation:
    """Scenarios for milestone label i18n in JS templates."""

    MILESTONE_KEYS = [
        "feature_freeze", "promote_sit", "sit_start", "sit_end",
        "fov_readiness", "promote_uat", "uat_end", "hard_code_freeze",
        "uat2_install", "uat2_end", "prod_install",
        "dev", "sit", "uat", "preprod", "prod",
    ]

    def test_core_labels_use_i18n(self):
        """GIVEN the _scripts_core template with milestone LABELS dict."""
        src = _read("_scripts_core.html.j2")

        """WHEN checking the LABELS object for i18n calls."""
        [ln for ln in src.splitlines() if "_t('rc.milestone." in ln]

        """THEN every milestone key should use _t() calls."""
        for key in self.MILESTONE_KEYS:
            assert f"_t('rc.milestone.{key}')" in src, (
                f"LABELS['{key}'] is not using _t() translation"
            )

    def test_core_labels_no_hardcoded_english(self):
        """GIVEN the _scripts_core LABELS dict."""
        src = _read("_scripts_core.html.j2")

        """WHEN searching for hardcoded English label values."""
        hardcoded = [
            ":'Feature Freeze'", ":'Promote SIT'", ":'SIT Start'",
            ":'SIT End'", ":'FOV Readiness'", ":'PROD Install'",
        ]

        """THEN none should remain."""
        for h in hardcoded:
            assert h not in src, f"Hardcoded label {h} still present in _scripts_core"

    def test_calendar_labels_use_i18n(self):
        """GIVEN the _scripts_release_calendar template with PHASE_LABELS dict."""
        src = _read("_scripts_release_calendar.html.j2")

        """WHEN checking the PHASE_LABELS object for i18n calls."""
        [ln for ln in src.splitlines() if "T('rc.milestone." in ln]

        """THEN every milestone key should use T() calls."""
        for key in self.MILESTONE_KEYS:
            assert f"T('rc.milestone.{key}'" in src, (
                f"PHASE_LABELS['{key}'] is not using T() translation"
            )

    def test_milestone_keys_exist_en(self):
        """GIVEN the English locale catalog."""
        cat = _load_catalog("en")

        """WHEN looking up all rc.milestone.* keys."""
        [f"rc.milestone.{k}" for k in self.MILESTONE_KEYS if f"rc.milestone.{k}" not in cat]

        """THEN each milestone has a translation."""
        for key in self.MILESTONE_KEYS:
            full = f"rc.milestone.{key}"
            assert full in cat, f"Missing EN translation: {full}"

    def test_milestone_keys_exist_pl(self):
        """GIVEN the Polish locale catalog."""
        cat = _load_catalog("pl")

        """WHEN looking up all rc.milestone.* keys."""
        [f"rc.milestone.{k}" for k in self.MILESTONE_KEYS if f"rc.milestone.{k}" not in cat]

        """THEN each milestone has a translation."""
        for key in self.MILESTONE_KEYS:
            full = f"rc.milestone.{key}"
            assert full in cat, f"Missing PL translation: {full}"


class TestReadmeLogo:
    """Scenarios for README logo rendering."""

    def test_logo_svg_exists(self):
        """GIVEN the docs/assets directory."""
        logo = Path(__file__).parent.parent / "docs" / "assets" / "logo.svg"

        """WHEN checking the logo file."""
        exists = logo.exists()

        """THEN it should exist and be valid SVG."""
        assert exists, "logo.svg is missing"
        content = logo.read_text("utf-8")
        assert "<svg" in content

    def test_readme_references_logo(self):
        """GIVEN the README.md file."""
        readme = (Path(__file__).parent.parent / "README.md").read_text("utf-8")

        """WHEN checking for logo reference."""
        has_src = 'src="docs/assets/logo-full.svg"' in readme

        """THEN it should use a simple img tag with the correct path."""
        assert has_src
        assert 'alt="ReleaseBoard"' in readme

    def test_readme_no_broken_picture_element(self):
        """GIVEN the README.md file."""
        readme = (Path(__file__).parent.parent / "README.md").read_text("utf-8")

        """WHEN checking for complex picture element."""
        has_picture = "<picture>" in readme

        """THEN it should NOT use picture or source elements."""
        assert not has_picture


class TestDashboardLoadingOverlay:
    """Scenarios for loading skeleton overlay behavior."""

    def test_skeletons_use_overlay_class(self):
        """GIVEN the _dashboard_content template."""
        src = _read("_dashboard_content.html.j2")

        """WHEN checking the loading skeletons container."""
        has_overlay = 'class="loading-overlay hidden"' in src

        """THEN it should have the loading-overlay class."""
        assert has_overlay

    def test_overlay_css_is_absolute(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN searching for the loading-overlay rule."""
        found = ".loading-overlay" in src

        """THEN it should use absolute positioning."""
        assert found
        assert "position: absolute" in src

    def test_container_has_relative_position(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN checking the container CSS rule."""
        has_relative = "position: relative" in src

        """THEN it should include position relative for overlay stacking."""
        assert has_relative


class TestTargetYearValidation:
    """Scenarios for target year minimum validation."""

    def test_dynamic_min_in_populateform(self):
        """GIVEN the _scripts_config_ui template."""
        src = _read("_scripts_config_ui.html.j2")

        """WHEN checking the populateForm function."""
        has_min_set = 'tyEl.min = new Date().getFullYear()' in src

        """THEN it should set the min attribute to current year dynamically."""
        assert has_min_set

    def test_effective_validation_checks_year(self):
        """GIVEN the _scripts_editor template."""
        src = _read("_scripts_editor.html.j2")

        """WHEN checking validateEffectiveValues."""
        has_year_check = "target_year" in src and "new Date().getFullYear()" in src

        """THEN it should validate target_year against current year."""
        assert has_year_check
        assert "_t('ui.validation.target_year_past')" in src

    def test_i18n_key_target_year_past_en(self):
        """GIVEN the English locale."""
        locale = "en"

        """WHEN translating target_year_past."""
        result = t("ui.validation.target_year_past", locale=locale)

        """THEN a meaningful message is returned."""
        assert "current year" in result.lower()

    def test_i18n_key_target_year_past_pl(self):
        """GIVEN the Polish locale."""
        locale = "pl"

        """WHEN translating target_year_past."""
        result = t("ui.validation.target_year_past", locale=locale)

        """THEN a meaningful message is returned."""
        assert "bieżący rok" in result.lower()


class TestReleaseNameValidation:
    """Scenarios for release name validation i18n."""

    def test_friendly_error_handles_release_name(self):
        """GIVEN the friendlyError function in _scripts_editor."""
        src = _read("_scripts_editor.html.j2")

        """WHEN checking the regex map for release name pattern."""
        has_pattern = r"release\.name:.*should be non-empty" in src

        """THEN it should have a pattern for release name non-empty."""
        assert has_pattern

    def test_i18n_key_release_name_empty_en(self):
        """GIVEN the English locale."""
        locale = "en"

        """WHEN translating release_name_empty."""
        result = t("ui.validation.release_name_empty", locale=locale)

        """THEN it returns a user-friendly message."""
        assert "release name" in result.lower()
        assert "empty" in result.lower()

    def test_i18n_key_release_name_empty_pl(self):
        """GIVEN the Polish locale."""
        locale = "pl"

        """WHEN translating release_name_empty."""
        result = t("ui.validation.release_name_empty", locale=locale)

        """THEN it returns a user-friendly message in Polish."""
        assert "wydania" in result.lower()


class TestOrderFieldValidation:
    """Scenarios for layer order field bounds."""

    def test_order_input_has_min_zero(self):
        """GIVEN the layer order input in _scripts_config_ui."""
        src = _read("_scripts_config_ui.html.j2")

        """WHEN checking the HTML for the order input."""
        has_min = 'type="number" min="0"' in src

        """THEN it should have min zero attribute."""
        assert has_min

    def test_order_clamps_negative(self):
        """GIVEN the order onchange handler."""
        src = _read("_scripts_config_ui.html.j2")

        """WHEN checking the handler."""
        has_clamp = "Math.max(0," in src

        """THEN it should clamp to zero with Math.max."""
        assert has_clamp

    def test_effective_validation_checks_order(self):
        """GIVEN the _scripts_editor validateEffectiveValues."""
        src = _read("_scripts_editor.html.j2")

        """WHEN checking the validation logic."""
        has_order_check = "order_negative" in src

        """THEN it should reject negative order values."""
        assert has_order_check

    def test_i18n_key_order_negative_en(self):
        """GIVEN the English locale."""
        locale = "en"

        """WHEN translating order_negative."""
        result = t("ui.validation.order_negative", locale=locale)

        """THEN a meaningful message is returned."""
        assert "0" in result

    def test_i18n_key_order_negative_pl(self):
        """GIVEN the Polish locale."""
        locale = "pl"

        """WHEN translating order_negative."""
        result = t("ui.validation.order_negative", locale=locale)

        """THEN a meaningful message is returned."""
        assert "0" in result


class TestDisabledButtonHover:
    """Scenarios for disabled button hover stability."""

    def test_disabled_has_pointer_events_none(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN checking tb-btn disabled CSS."""
        has_pointer_none = "pointer-events: none" in src

        """THEN it should include pointer-events none."""
        assert has_pointer_none

    def test_disabled_hover_override_exists(self):
        """GIVEN the _styles template."""
        src = _read("_styles.html.j2")

        """WHEN checking for disabled hover override rule."""
        has_override = ".tb-btn:disabled:hover" in src

        """THEN it should explicitly prevent hover color changes."""
        assert has_override

    def test_disabled_hover_no_shadow(self):
        """GIVEN the tb-btn disabled hover CSS rule."""
        src = _read("_styles.html.j2")

        """WHEN checking the hover override."""
        hover_line = next(
            (ln for ln in src.splitlines() if ".tb-btn:disabled:hover" in ln),
            None,
        )

        """THEN box-shadow should be none."""
        assert hover_line is not None, ".tb-btn:disabled:hover rule not found"
        assert "box-shadow: none" in hover_line


class TestI18nCatalogParity:
    """Scenarios for i18n catalog consistency of newly added keys."""

    NEW_KEYS = [
        "ui.validation.release_name_empty",
        "ui.validation.target_year_past",
        "ui.validation.order_negative",
    ]

    def test_all_new_keys_in_en(self):
        """GIVEN the English catalog."""
        cat = _load_catalog("en")

        """WHEN checking all new validation keys."""
        [k for k in self.NEW_KEYS if k not in cat]

        """THEN each must be present."""
        for key in self.NEW_KEYS:
            assert key in cat, f"Missing EN key: {key}"

    def test_all_new_keys_in_pl(self):
        """GIVEN the Polish catalog."""
        cat = _load_catalog("pl")

        """WHEN checking all new validation keys."""
        [k for k in self.NEW_KEYS if k not in cat]

        """THEN each must be present."""
        for key in self.NEW_KEYS:
            assert key in cat, f"Missing PL key: {key}"
