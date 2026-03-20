"""Tests for server safety — SSE serialization, calendar import validation,
filter null guards, milestone filter guard, config save error handling."""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "src" / "releaseboard" / "presentation" / "templates"
LOCALE_DIR = ROOT / "src" / "releaseboard" / "i18n" / "locales"


# ---------------------------------------------------------------------------
# SSE format — safe serialization
# ---------------------------------------------------------------------------

class TestSseFormatSafeSerialization:
    """Scenarios for _sse_format safe serialization with non-JSON-safe data."""

    def test_sse_format_default_str_fallback(self):
        """GIVEN the server module with _sse_format.
        WHEN formatting SSE data that contains non-serializable objects.
        THEN json.dumps should use default=str to avoid TypeError."""
        src = (ROOT / "src" / "releaseboard" / "web" / "server.py").read_text(encoding="utf-8")
        assert "default=str" in src, "_sse_format must use default=str for safe serialization"

    def test_sse_format_has_try_except(self):
        """GIVEN the server module.
        WHEN looking at _sse_format.
        THEN it should have try/except around json.dumps."""
        src = (ROOT / "src" / "releaseboard" / "web" / "server.py").read_text(encoding="utf-8")
        idx = src.find("def _sse_format")
        assert idx != -1
        func_body = src[idx:idx + 500]
        assert "try:" in func_body, "_sse_format must catch serialization errors"
        assert "serialization_failed" in func_body


# ---------------------------------------------------------------------------
# Calendar import — no fallback to entire body
# ---------------------------------------------------------------------------

class TestCalendarImportSafety:
    """Scenarios for calendar import not using entire body as fallback."""

    def test_put_calendar_no_full_body_fallback(self):
        """GIVEN the PUT /api/release-calendar endpoint.
        WHEN checking the calendar data extraction pattern.
        THEN it must not fall back to the entire request body."""
        src = (ROOT / "src" / "releaseboard" / "web" / "server.py").read_text(encoding="utf-8")
        # The dangerous pattern: body.get("release_calendar", body)
        assert 'body.get("release_calendar", body)' not in src, \
            "Calendar import must not fall back to entire body dict"

    def test_import_calendar_no_full_body_fallback(self):
        """GIVEN the POST /api/release-calendar/import endpoint.
        WHEN checking the calendar data extraction pattern.
        THEN it must not fall back to the entire request body."""
        src = (ROOT / "src" / "releaseboard" / "web" / "server.py").read_text(encoding="utf-8")
        # Should use body.get("release_calendar") or body instead
        assert 'body.get("release_calendar", body)' not in src


# ---------------------------------------------------------------------------
# Filter null guards
# ---------------------------------------------------------------------------

class TestFilterNullGuards:
    """Scenarios for DOM filter elements having null guards."""

    def test_filter_event_listeners_guarded(self):
        """GIVEN the _scripts_core template.
        WHEN attaching event listeners to filter elements.
        THEN each element should be null-checked before addEventListener."""
        src = (TEMPLATE_DIR / "_scripts_core.html.j2").read_text(encoding="utf-8")
        assert "if(e){e.addEventListener" in src or "if(e)" in src, \
            "Filter elements must be null-checked before addEventListener"

    def test_filter_reset_guarded(self):
        """GIVEN the _scripts_core template.
        WHEN attaching click handler to filterReset.
        THEN filterReset should be null-checked."""
        src = (TEMPLATE_DIR / "_scripts_core.html.j2").read_text(encoding="utf-8")
        assert "if(filterReset)" in src, "filterReset must be null-checked"

    def test_filter_count_guarded(self):
        """GIVEN the _scripts_core template applyFilters function.
        WHEN updating filterCount text.
        THEN filterCount should be null-checked."""
        src = (TEMPLATE_DIR / "_scripts_core.html.j2").read_text(encoding="utf-8")
        assert "if(filterCount)" in src, "filterCount must be null-checked"

    def test_search_input_null_safe_in_apply_filters(self):
        """GIVEN the _scripts_core template applyFilters function.
        WHEN reading search input value.
        THEN it should use conditional access (searchInput? or if(searchInput))."""
        src = (TEMPLATE_DIR / "_scripts_core.html.j2").read_text(encoding="utf-8")
        assert "searchInput?" in src or "searchInput &&" in src, \
            "searchInput must use null-safe access in applyFilters"


# ---------------------------------------------------------------------------
# Milestone filter guard
# ---------------------------------------------------------------------------

class TestMilestoneFilterGuard:
    """Scenarios for envViewSelect milestone filter safety."""

    def test_milestones_filter_guarded(self):
        """GIVEN the dashboard content template.
        WHEN the envViewSelect fires onchange.
        THEN _rbMilestonesFilter must be guarded against undefined."""
        src = (TEMPLATE_DIR / "_dashboard_content.html.j2").read_text(encoding="utf-8")
        assert "if(window._rbMilestonesFilter)" in src, \
            "Milestone filter must be guarded against undefined"


# ---------------------------------------------------------------------------
# Config save/apply error handling
# ---------------------------------------------------------------------------

class TestConfigSaveErrorHandling:
    """Scenarios for save/apply config having proper error handling."""

    def test_apply_config_has_try_catch(self):
        """GIVEN the editor template with applyConfig.
        WHEN a network error occurs during apply.
        THEN applyConfig must catch the error and show a message."""
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        idx = src.find("async function applyConfig")
        assert idx != -1
        func_body = src[idx:idx + 800]
        assert "catch" in func_body, "applyConfig must have error handling"

    def test_save_config_has_try_catch(self):
        """GIVEN the editor template with saveConfig.
        WHEN a network error occurs during save.
        THEN saveConfig must catch the error and show a message."""
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        idx = src.find("async function saveConfig")
        assert idx != -1
        func_body = src[idx:idx + 800]
        assert "catch" in func_body, "saveConfig must have error handling"

    def test_apply_validates_json_before_save(self):
        """GIVEN the editor template with applyConfig.
        WHEN the user is on JSON tab with invalid JSON.
        THEN applyConfig must validate JSON and return early with error."""
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        idx = src.find("async function applyConfig")
        func_body = src[idx:idx + 600]
        assert "invalid_json" in func_body or "Invalid JSON" in func_body, \
            "applyConfig must validate JSON syntax"


# ---------------------------------------------------------------------------
# SSE unsubscribe safety
# ---------------------------------------------------------------------------

class TestSseUnsubscribeSafety:
    """Scenarios for SSE unsubscribe tolerating double-removal."""

    def test_unsubscribe_catches_value_error(self):
        """GIVEN the state module with unsubscribe method.
        WHEN removing a queue that was already removed by broadcast.
        THEN it must not raise ValueError."""
        src = (ROOT / "src" / "releaseboard" / "web" / "state.py").read_text(encoding="utf-8")
        idx = src.find("def unsubscribe")
        assert idx != -1
        func_body = src[idx:idx + 300]
        assert "ValueError" in func_body or "except" in func_body, \
            "unsubscribe must handle double-removal safely"


# ---------------------------------------------------------------------------
# i18n validation error keys
# ---------------------------------------------------------------------------

class TestValidationI18nKeys:
    """Scenarios for validation error i18n keys."""

    def test_en_has_invalid_json_key(self):
        """GIVEN the English locale.
        WHEN checking for validation.invalid_json key.
        THEN the key should exist."""
        data = json.loads((LOCALE_DIR / "en.json").read_text(encoding="utf-8"))
        assert "validation.invalid_json" in data

    def test_en_has_save_failed_key(self):
        """GIVEN the English locale.
        WHEN checking for validation.save_failed key.
        THEN the key should exist."""
        data = json.loads((LOCALE_DIR / "en.json").read_text(encoding="utf-8"))
        assert "validation.save_failed" in data

    def test_en_has_network_error_key(self):
        """GIVEN the English locale.
        WHEN checking for validation.network_error key.
        THEN the key should exist."""
        data = json.loads((LOCALE_DIR / "en.json").read_text(encoding="utf-8"))
        assert "validation.network_error" in data

    def test_pl_has_all_validation_keys(self):
        """GIVEN both English and Polish locales.
        WHEN comparing validation.* keys.
        THEN Polish must have all validation keys from English."""
        en = json.loads((LOCALE_DIR / "en.json").read_text(encoding="utf-8"))
        pl = json.loads((LOCALE_DIR / "pl.json").read_text(encoding="utf-8"))
        en_val = {k for k in en if k.startswith("validation.")}
        pl_val = {k for k in pl if k.startswith("validation.")}
        missing = en_val - pl_val
        assert not missing, f"Polish locale missing validation keys: {missing}"
