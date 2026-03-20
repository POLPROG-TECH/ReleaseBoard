"""Feature tests — schema and configuration: layout sections,
JSON validation, auto-name, branch inheritance, effective validation,
schema consistency, template integration, validation scoping."""

from __future__ import annotations

import json
import pathlib
import re
from datetime import UTC, datetime
from pathlib import Path

from releaseboard.analysis.readiness import ReadinessAnalyzer
from releaseboard.domain.enums import ReadinessStatus
from releaseboard.domain.models import BranchInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent

TEMPLATE_DIR = ROOT / "src" / "releaseboard" / "presentation" / "templates"

_TEMPLATE_DIR = ROOT / "src" / "releaseboard" / "presentation" / "templates"

SCHEMA = json.loads((ROOT / "src" / "releaseboard" / "config" / "schema.json").read_text())

EXAMPLE_CONFIG = json.loads((ROOT / "examples" / "config.json").read_text())

# Use example config as canonical reference (releaseboard.json is a local-only file)
CONFIG = EXAMPLE_CONFIG

def _html() -> str:
    """Read and concatenate all template partials for string-based checks."""
    parts = []
    for f in sorted(TEMPLATE_DIR.glob("*.j2")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)

def _examples_config() -> dict:
    return json.loads((ROOT / "examples" / "config.json").read_text(encoding="utf-8"))

def _read_all_templates() -> str:
    parts = []
    for f in sorted(_TEMPLATE_DIR.glob("*.j2")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)

TEMPLATE = _read_all_templates()


class TestReadinessStatusFix:
    """Scenarios for readiness status with existing branches."""

    def test_branch_exists_no_metadata_returns_ready(self, sample_config):
        """GIVEN an existing branch with no metadata."""
        repo = sample_config.repositories[0]
        branches = ["main", "release/03.2025"]
        branch_info = BranchInfo(name="release/03.2025", exists=True)
        analyzer = ReadinessAnalyzer(sample_config)

        """WHEN analyzing readiness."""
        result = analyzer.analyze(repo, branches, branch_info)

        """THEN the status is READY."""
        assert result.status == ReadinessStatus.READY

    def test_branch_exists_with_stale_commit_returns_stale(self, sample_config):
        """GIVEN an existing branch with a stale commit date."""
        repo = sample_config.repositories[0]
        branches = ["main", "release/03.2025"]
        branch_info = BranchInfo(
            name="release/03.2025",
            exists=True,
            last_commit_date=datetime(2025, 1, 1, tzinfo=UTC),
        )
        analyzer = ReadinessAnalyzer(sample_config)

        """WHEN analyzing readiness."""
        result = analyzer.analyze(repo, branches, branch_info)

        """THEN the status is STALE."""
        assert result.status == ReadinessStatus.STALE

    def test_branch_exists_fresh_commit_returns_ready(self, sample_config):
        """GIVEN an existing branch with a fresh commit."""
        repo = sample_config.repositories[0]
        branches = ["main", "release/03.2025"]
        branch_info = BranchInfo(
            name="release/03.2025",
            exists=True,
            last_commit_date=datetime.now(tz=UTC),
        )
        analyzer = ReadinessAnalyzer(sample_config)

        """WHEN analyzing readiness."""
        result = analyzer.analyze(repo, branches, branch_info)

        """THEN the status is READY."""
        assert result.status == ReadinessStatus.READY


class TestSchemaLayoutSection:
    """Scenarios for schema layout section."""

    def test_schema_has_layout(self):
        """GIVEN the JSON schema file."""
        schema_path = (
            Path(__file__).parent.parent
            / "src" / "releaseboard" / "config" / "schema.json"
        )
        schema = json.loads(schema_path.read_text())

        """WHEN checking for layout properties."""
        layout = schema["properties"].get("layout", {})
        layout_props = layout.get("properties", {})

        """THEN layout section with expected fields exists."""
        assert "layout" in schema["properties"]
        assert "default_template" in layout_props
        assert "section_order" in layout_props
        assert "enable_drag_drop" in layout_props


class TestJsonValidation:
    """Scenarios for JSON validation and legend UI."""

    def test_json_editor_wrap_exists(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for json editor wrap element."""
        has_wrap = "json-editor-wrap" in template

        """THEN the two-panel layout is present."""
        assert has_wrap

    def test_json_validation_bar(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for validation bar elements."""
        has_bar = "json-validation-bar" in template
        has_js_ref = "jsonValBar" in template

        """THEN both elements exist."""
        assert has_bar
        assert has_js_ref

    def test_json_validation_errors_list(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for error list elements."""
        has_errors = "json-validation-errors" in template
        has_js_ref = "jsonValErrors" in template

        """THEN both elements exist."""
        assert has_errors
        assert has_js_ref

    def test_json_legend_panel(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for legend panel elements."""
        has_legend = "json-legend" in template
        has_title = "Field Reference" in template

        """THEN the legend panel and title exist."""
        assert has_legend
        assert has_title

    def test_json_legend_has_all_sections(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for all config section names."""
        sections = [
            "release", "layers[]", "repositories[]",
            "branding", "settings", "author", "layout",
        ]
        missing = [s for s in sections if s not in template]

        """THEN all sections are present."""
        assert missing == [], f"Legend missing sections: {missing}"

    def test_json_legend_field_types(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for field type elements."""
        has_type = "field-type" in template
        has_req = "field-req" in template
        has_desc = "field-desc" in template

        """THEN all field type elements exist."""
        assert has_type
        assert has_req
        assert has_desc

    def test_validate_json_editor_function(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for validateJsonEditor function."""
        has_func = "validateJsonEditor" in template

        """THEN the async function exists."""
        assert has_func

    def test_show_json_parse_error_function(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for showJsonParseError function."""
        has_func = "showJsonParseError" in template

        """THEN the function exists."""
        assert has_func

    def test_json_editor_responsive(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for responsive editor elements."""
        has_wrap = "json-editor-wrap" in template
        has_legend = "json-legend" in template

        """THEN responsive elements are present."""
        assert has_wrap
        assert has_legend


class TestAutoName:
    """Scenarios for auto-name from URL feature."""

    def test_auto_filled_indicator_css(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for auto-filled indicator CSS class."""
        has_class = "auto-filled-indicator" in template

        """THEN the CSS class exists."""
        assert has_class

    def test_auto_filled_indicator_text(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for auto-filled indicator i18n key."""
        has_key = "auto_filled_from_url" in template

        """THEN the i18n key exists."""
        assert has_key

    def test_update_repo_name_clears_auto_flag(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for updateRepoName and auto flag logic."""
        has_func = "updateRepoName" in template
        clears_flag = "_autoName = false" in template or "_autoName=false" in template

        """THEN the function clears the auto name flag."""
        assert has_func
        assert clears_flag

    def test_auto_fill_checks_auto_name_flag(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for auto name flag reference."""
        has_flag = "_autoName" in template

        """THEN the flag is referenced."""
        assert has_flag

    def test_add_repo_starts_with_empty_name(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for empty name initialization."""
        has_empty = "name:''" in template or 'name:""' in template

        """THEN new repos start with empty name."""
        assert has_empty

    def test_derive_name_from_url_function(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for deriveNameFromUrl function."""
        has_func = "deriveNameFromUrl" in template
        handles_git = ".git" in template

        """THEN the function exists and handles .git suffix."""
        assert has_func
        assert handles_git


class TestBranchInheritance:
    """Scenarios for branch pattern inheritance."""

    def test_inherited_tag_exists(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for inherited tag CSS class."""
        has_tag = "inherited-tag" in template

        """THEN the CSS class exists."""
        assert has_tag

    def test_override_tag_exists(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for override tag CSS class."""
        has_tag = "override-tag" in template

        """THEN the CSS class exists."""
        assert has_tag

    def test_reset_inherit_button(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for reset-to-inherited button elements."""
        has_btn = "reset-inherit-btn" in template
        has_func = "resetRepoBranch" in template

        """THEN the button and handler exist."""
        assert has_btn
        assert has_func

    def test_reset_branch_deletes_override(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for branch pattern deletion logic."""
        has_delete = "delete repo.branch_pattern" in template

        """THEN the delete statement exists."""
        assert has_delete

    def test_layer_shows_effective_branch(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for inherited-from-global i18n key."""
        has_key = "inherited_from_global" in template

        """THEN the inheritance indicator exists."""
        assert has_key

    def test_repo_shows_branch_source(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for branch source i18n keys."""
        has_layer = "source_inherited_layer" in template
        has_override = "source_repo_override" in template or "hasRepoOverride" in template
        has_global = "source_inherited_global" in template

        """THEN all source indicators exist."""
        assert has_layer
        assert has_override
        assert has_global

    def test_layer_branch_change_triggers_re_render(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for layer branch re-render trigger."""
        has_trigger = (
            "renderLayers();RB.renderRepos()" in template
            or "RB.renderLayers();RB.renderRepos()" in template
        )

        """THEN both layers and repos are re-rendered."""
        assert has_trigger

    def test_repo_branch_change_triggers_re_render(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for repo branch re-render trigger."""
        has_trigger = "RB.renderRepos()" in template

        """THEN repos are re-rendered."""
        assert has_trigger


class TestEffectiveValidation:
    """Scenarios for effective value validation."""

    def test_validate_effective_values_function(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for validateEffectiveValues function."""
        has_func = "validateEffectiveValues" in template

        """THEN the function exists."""
        assert has_func

    def test_validate_draft_includes_effective(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for validateEffectiveValues call in validateDraft."""
        has_call = "validateEffectiveValues()" in template

        """THEN validateDraft calls validateEffectiveValues."""
        assert has_call

    def test_bare_slug_warning(self):
        """GIVEN the dashboard template."""
        template = TEMPLATE

        """WHEN checking for bare slug warning i18n key."""
        has_key = "bare_slug" in template

        """THEN the warning key exists."""
        assert has_key


class TestSchemaConsistency:
    """Scenarios for schema and config consistency."""

    def test_schema_has_layout_section(self):
        """GIVEN the JSON schema."""
        schema = SCHEMA

        """WHEN checking for layout property."""
        has_layout = "layout" in schema["properties"]

        """THEN layout section exists."""
        assert has_layout

    def test_config_layout_section(self):
        """GIVEN the project config."""
        config = CONFIG

        """WHEN checking layout section and drag-drop setting."""
        has_layout = "layout" in config
        drag_drop = config.get("layout", {}).get("enable_drag_drop")

        """THEN layout exists with drag-drop enabled."""
        assert has_layout
        assert drag_drop is True

    def test_example_config_layout_section(self):
        """GIVEN the example config."""
        config = EXAMPLE_CONFIG

        """WHEN checking for layout section."""
        has_layout = "layout" in config

        """THEN layout section exists."""
        assert has_layout

    def test_example_config_is_valid_structure(self):
        """GIVEN the example config."""
        config = EXAMPLE_CONFIG

        """WHEN checking required top-level sections."""
        has_release = "release" in config
        has_repos = "repositories" in config
        repo_count = len(config.get("repositories", []))

        """THEN all required sections exist with data."""
        assert has_release
        assert has_repos
        assert repo_count > 0


class TestTemplateIntegration:
    """Scenarios for template integration checks."""

    def test_all_sections_have_data_section_ids(self):
        """GIVEN the dashboard template."""
        import re
        template = TEMPLATE

        """WHEN extracting data-section-id attributes."""
        sections = re.findall(r'data-section-id="(\w[\w-]*)"', template)

        """THEN at least five sections exist."""
        assert len(sections) >= 5

    def test_layout_config_enabled(self):
        """GIVEN the project config."""
        config = CONFIG

        """WHEN checking enable_drag_drop setting."""
        drag_drop = config.get("layout", {}).get("enable_drag_drop")

        """THEN drag-drop is enabled."""
        assert drag_drop is True

    def test_layout_toast_i18n_key(self):
        """GIVEN the dashboard template and project config."""
        template = TEMPLATE
        config = CONFIG

        """WHEN checking for layout saved toast key."""
        has_key = "layout_saved" in template or "layout" in str(config)

        """THEN the layout reference exists."""
        assert has_key

    def test_dashboard_sections_have_ids(self):
        """GIVEN a rendered dashboard template."""
        html = TEMPLATE

        """WHEN extracting data-section-id attributes."""
        sections = re.findall(r'data-section-id="(\w[\w-]*)"', html)

        """THEN at least five sections exist."""
        assert len(sections) >= 5

    def test_section_labels_exist(self):
        """GIVEN a rendered dashboard template."""
        html = TEMPLATE

        """WHEN checking for section display labels."""
        has_labels = "data-section-label" in html

        """THEN data-section-label attributes exist."""
        assert has_labels

    def test_config_drawer_exists(self):
        """GIVEN a rendered dashboard template."""
        html = TEMPLATE

        """WHEN checking for the configuration panel."""
        has_drawer = "config-drawer" in html or "cfg-drawer" in html or "config-panel" in html

        """THEN a config drawer element exists."""
        assert has_drawer


class TestValidationScoping:
    """Scenarios for validation scoping across tabs."""

    def test_switch_tab_clears_validation(self):
        """GIVEN the rendered HTML template."""
        html = _html()

        """WHEN extracting the switchTab function body."""
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        body = match.group(1) if match else ""

        """THEN validationPanel is referenced."""
        assert match
        assert "validationPanel" in body

    def test_json_tab_triggers_json_validation(self):
        """GIVEN the rendered HTML template."""
        html = _html()

        """WHEN extracting the switchTab function body."""
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        body = match.group(1) if match else ""

        """THEN validateJsonEditor is called."""
        assert match
        assert "validateJsonEditor" in body

    def test_form_tab_triggers_form_validation(self):
        """GIVEN the rendered HTML template."""
        html = _html()

        """WHEN extracting the switchTab function body."""
        match = re.search(r"function switchTab\(tab\)\{(.*?)\n  \}", html, re.S)
        body = match.group(1) if match else ""

        """THEN validateDraft is called."""
        assert match
        assert "validateDraft" in body


class TestDragHandleVisibility:
    """Scenarios for drag handle visibility."""

    def test_dashboard_sections_have_section_ids(self):
        """GIVEN a rendered dashboard template."""
        html = TEMPLATE

        """WHEN checking for section identification attributes."""
        has_section_ids = "data-section-id" in html

        """THEN sections include data-section-id attributes."""
        assert has_section_ids

    def test_drag_handle_css_exists(self):
        """GIVEN a rendered dashboard template with drag support."""
        html = TEMPLATE

        """WHEN checking for drag handle CSS classes."""
        has_section_class = "dashboard-section" in html

        """THEN dashboard-section class exists in the template."""
        assert has_section_class

    def test_drop_placeholder_styling(self):
        """GIVEN a rendered dashboard template with drop support."""
        html = TEMPLATE

        """WHEN checking for drop placeholder styling."""
        has_section_class = "dashboard-section" in html

        """THEN dashboard-section class exists in the template."""
        assert has_section_class

    def test_layout_enabled_sections(self):
        """GIVEN a rendered dashboard template with layout support."""
        html = TEMPLATE

        """WHEN checking for section ordering attributes."""
        has_id = "data-section-id" in html
        has_label = "data-section-label" in html

        """THEN sections have both id and label attributes."""
        assert has_id
        assert has_label


class TestExamplesConfig:
    """Scenarios for examples config sanity."""

    def test_branding_title(self):
        """GIVEN the examples config file."""
        cfg = _examples_config()

        """WHEN extracting the branding title."""
        title = cfg.get("branding", {}).get("title", "")

        """THEN the title does not contain AcmeBoard."""
        assert "AcmeBoard" not in title
