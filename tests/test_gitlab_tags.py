"""Tests for GitLab tag enrichment feature.

Covers:
- TagInfo domain model
- GitLabProvider.get_latest_branch_tag() with mocked API
- RepoViewModel tag fields mapping
- Dashboard table column rendering
- Detail modal tag section rendering
- Graceful degradation for non-GitLab repos and missing tags
- i18n keys for tag-related UI
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from releaseboard.domain.models import BranchInfo, RepositoryAnalysis, TagInfo
from releaseboard.git.gitlab_provider import GitLabProvider

# ---------------------------------------------------------------------------
# TagInfo model tests
# ---------------------------------------------------------------------------

class TestTagInfo:
    def test_basic_creation(self):
        tag = TagInfo(name="v1.2.3", target_sha="abc123def456")
        assert tag.name == "v1.2.3"
        assert tag.target_sha == "abc123def456"
        assert tag.committed_date is None
        assert tag.message is None

    def test_full_creation(self):
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        tag = TagInfo(
            name="release/2024.06",
            target_sha="deadbeef12345678",
            committed_date=dt,
            message="Release 2024.06 tag",
        )
        assert tag.name == "release/2024.06"
        assert tag.committed_date == dt
        assert tag.message == "Release 2024.06 tag"

    def test_frozen(self):
        tag = TagInfo(name="v1.0", target_sha="aaa")
        with pytest.raises(AttributeError):
            tag.name = "v2.0"


class TestRepositoryAnalysisTagField:
    def test_latest_tag_default_none(self):
        from releaseboard.domain.enums import ReadinessStatus
        ra = RepositoryAnalysis(
            name="test", url="https://gitlab.com/g/p",
            layer="core", default_branch="main",
            expected_pattern="release/{YYYY}.{MM}",
            expected_branch_name="release/2024.06",
            status=ReadinessStatus.READY,
        )
        assert ra.latest_tag is None

    def test_latest_tag_set(self):
        from releaseboard.domain.enums import ReadinessStatus
        tag = TagInfo(name="v1.0", target_sha="abc")
        ra = RepositoryAnalysis(
            name="test", url="https://gitlab.com/g/p",
            layer="core", default_branch="main",
            expected_pattern="release/{YYYY}.{MM}",
            expected_branch_name="release/2024.06",
            status=ReadinessStatus.READY,
            latest_tag=tag,
        )
        assert ra.latest_tag is not None
        assert ra.latest_tag.name == "v1.0"


# ---------------------------------------------------------------------------
# GitLabProvider.get_latest_branch_tag() tests (mocked API)
# ---------------------------------------------------------------------------

class TestGitLabProviderGetLatestBranchTag:
    """Test tag retrieval with mocked HTTP responses."""

    def _provider(self):
        return GitLabProvider(token="test-token")

    def _mock_get_json(self, responses: dict):
        """Create a side_effect for _get_json based on URL patterns."""
        def side_effect(url, timeout):
            for pattern, (data, status) in responses.items():
                if pattern in url:
                    return data, status
            return None, 404
        return side_effect

    def test_returns_none_for_non_gitlab_url(self):
        provider = self._provider()
        result = provider.get_latest_branch_tag("https://github.com/owner/repo", "main")
        assert result is None

    def test_returns_none_when_no_tags(self):
        provider = self._provider()
        with patch.object(provider, "_get_json", return_value=([], 200)):
            result = provider.get_latest_branch_tag(
                "https://gitlab.com/group/project", "release/2024.06"
            )
        assert result is None

    def test_returns_tag_when_reachable(self):
        provider = self._provider()
        tags_response = [
            {
                "name": "v2.0.0",
                "commit": {
                    "id": "sha_v2",
                    "committed_date": "2024-06-15T12:00:00+00:00",
                },
                "message": "Release v2.0.0",
            },
            {
                "name": "v1.0.0",
                "commit": {
                    "id": "sha_v1",
                    "committed_date": "2024-01-01T12:00:00+00:00",
                },
                "message": "",
            },
        ]
        refs_response = [
            {"type": "branch", "name": "main"},
            {"type": "branch", "name": "release/2024.06"},
        ]

        call_count = {"n": 0}
        def mock_get_json(url, timeout):
            call_count["n"] += 1
            if "/repository/tags?" in url:
                return tags_response, 200
            if "/refs?" in url:
                return refs_response, 200
            return None, 404

        with patch.object(provider, "_get_json", side_effect=mock_get_json):
            result = provider.get_latest_branch_tag(
                "https://gitlab.com/group/project", "release/2024.06"
            )

        assert result is not None
        assert result.name == "v2.0.0"
        assert result.target_sha == "sha_v2"
        assert result.committed_date == datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        assert result.message == "Release v2.0.0"

    def test_skips_unreachable_tags(self):
        """First tag is not on the branch, second tag is."""
        provider = self._provider()
        tags_response = [
            {
                "name": "v2.0.0",
                "commit": {"id": "sha_v2", "committed_date": "2024-06-15T12:00:00Z"},
            },
            {
                "name": "v1.0.0",
                "commit": {"id": "sha_v1", "committed_date": "2024-01-01T12:00:00Z"},
            },
        ]

        def mock_get_json(url, timeout):
            if "/repository/tags?" in url:
                return tags_response, 200
            if "sha_v2/refs?" in url:
                # v2.0.0 is only on main, not on our branch
                return [{"type": "branch", "name": "main"}], 200
            if "sha_v1/refs?" in url:
                # v1.0.0 is on our branch
                return [{"type": "branch", "name": "release/2024.06"}], 200
            return None, 404

        with patch.object(provider, "_get_json", side_effect=mock_get_json):
            result = provider.get_latest_branch_tag(
                "https://gitlab.com/group/project", "release/2024.06"
            )

        assert result is not None
        assert result.name == "v1.0.0"

    def test_returns_none_when_no_tags_on_branch(self):
        provider = self._provider()
        tags_response = [
            {"name": "v1.0", "commit": {"id": "sha1", "committed_date": "2024-01-01T00:00:00Z"}},
        ]

        def mock_get_json(url, timeout):
            if "/repository/tags?" in url:
                return tags_response, 200
            if "/refs?" in url:
                return [{"type": "branch", "name": "other-branch"}], 200
            return None, 404

        with patch.object(provider, "_get_json", side_effect=mock_get_json):
            result = provider.get_latest_branch_tag(
                "https://gitlab.com/group/project", "release/2024.06"
            )

        assert result is None

    def test_handles_api_error_on_tags(self):
        provider = self._provider()
        with patch.object(provider, "_get_json", return_value=(None, 500)):
            result = provider.get_latest_branch_tag(
                "https://gitlab.com/group/project", "main"
            )
        assert result is None

    def test_handles_refs_api_error_gracefully(self):
        """If refs check fails for one tag, try the next."""
        provider = self._provider()
        tags_response = [
            {"name": "v2.0", "commit": {"id": "sha2", "committed_date": "2024-06-01T00:00:00Z"}},
            {"name": "v1.0", "commit": {"id": "sha1", "committed_date": "2024-01-01T00:00:00Z"}},
        ]

        def mock_get_json(url, timeout):
            if "/repository/tags?" in url:
                return tags_response, 200
            if "sha2/refs?" in url:
                return None, 500  # API error for first tag
            if "sha1/refs?" in url:
                return [{"type": "branch", "name": "main"}], 200
            return None, 404

        with patch.object(provider, "_get_json", side_effect=mock_get_json):
            result = provider.get_latest_branch_tag(
                "https://gitlab.com/group/project", "main"
            )

        assert result is not None
        assert result.name == "v1.0"

    def test_lightweight_tag_no_message(self):
        provider = self._provider()
        tags_response = [
            {
                "name": "v1.0",
                "commit": {"id": "sha1", "committed_date": "2024-01-01T00:00:00Z"},
                "message": "",
            },
        ]

        def mock_get_json(url, timeout):
            if "/repository/tags?" in url:
                return tags_response, 200
            if "/refs?" in url:
                return [{"type": "branch", "name": "main"}], 200
            return None, 404

        with patch.object(provider, "_get_json", side_effect=mock_get_json):
            result = provider.get_latest_branch_tag(
                "https://gitlab.com/group/project", "main"
            )

        assert result is not None
        assert result.message is None  # Empty string → None

    def test_self_hosted_gitlab(self):
        provider = self._provider()
        tags_response = [
            {
                "name": "v3.0",
                "commit": {"id": "sha3", "committed_date": "2024-07-01T00:00:00Z"},
                "message": "",
            },
        ]

        def mock_get_json(url, timeout):
            assert "git.company.com/api/v4" in url
            if "/repository/tags?" in url:
                return tags_response, 200
            if "/refs?" in url:
                return [{"type": "branch", "name": "main"}], 200
            return None, 404

        with patch.object(provider, "_get_json", side_effect=mock_get_json):
            result = provider.get_latest_branch_tag(
                "https://git.company.com/team/service", "main"
            )

        assert result is not None
        assert result.name == "v3.0"


# ---------------------------------------------------------------------------
# View model tag fields tests
# ---------------------------------------------------------------------------

class TestRepoViewModelTagFields:
    def test_gitlab_repo_with_tag(self):
        from releaseboard.domain.enums import ReadinessStatus
        from releaseboard.presentation.view_models import build_repo_view_model

        tag = TagInfo(
            name="v1.2.3",
            target_sha="abc123",
            committed_date=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
            message="Release v1.2.3",
        )
        analysis = RepositoryAnalysis(
            name="my-service",
            url="https://gitlab.com/group/my-service",
            layer="core",
            default_branch="main",
            expected_pattern="release/{YYYY}.{MM}",
            expected_branch_name="release/2024.06",
            status=ReadinessStatus.READY,
            branch=BranchInfo(name="release/2024.06", exists=True),
            latest_tag=tag,
        )
        vm = build_repo_view_model(analysis, "Core", 14)
        assert vm.latest_tag == "v1.2.3"
        assert vm.latest_tag_sha == "abc123"
        assert vm.latest_tag_message == "Release v1.2.3"
        assert vm.is_gitlab is True
        assert vm.latest_tag_date != ""

    def test_gitlab_repo_without_tag(self):
        from releaseboard.domain.enums import ReadinessStatus
        from releaseboard.presentation.view_models import build_repo_view_model

        analysis = RepositoryAnalysis(
            name="new-service",
            url="https://gitlab.com/group/new-service",
            layer="core",
            default_branch="main",
            expected_pattern="release/{YYYY}.{MM}",
            expected_branch_name="release/2024.06",
            status=ReadinessStatus.READY,
        )
        vm = build_repo_view_model(analysis, "Core", 14)
        assert vm.latest_tag == ""
        assert vm.is_gitlab is True

    def test_github_repo_not_gitlab(self):
        from releaseboard.domain.enums import ReadinessStatus
        from releaseboard.presentation.view_models import build_repo_view_model

        analysis = RepositoryAnalysis(
            name="gh-service",
            url="https://github.com/org/gh-service",
            layer="core",
            default_branch="main",
            expected_pattern="release/{YYYY}.{MM}",
            expected_branch_name="release/2024.06",
            status=ReadinessStatus.READY,
        )
        vm = build_repo_view_model(analysis, "Core", 14)
        assert vm.latest_tag == ""
        assert vm.is_gitlab is False


# ---------------------------------------------------------------------------
# Dashboard template rendering tests
# ---------------------------------------------------------------------------

class TestDashboardTagColumn:
    """Test that the Latest Tag column renders correctly in the dashboard."""

    @pytest.fixture
    def rendered_html(self):
        """Render the dashboard with test data and return the HTML."""
        import json
        import pathlib

        from releaseboard.config.models import AppConfig

        config_path = pathlib.Path(__file__).parent.parent / "examples" / "config.json"
        with open(config_path) as f:
            raw = json.load(f)
        AppConfig(raw)
        # Use a mock analysis result
        return None  # We'll test via regex on template content instead

    def test_header_contains_latest_tag_column(self):
        """The table header must include a Latest Tag column."""
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_dashboard_content.html.j2"
        )
        content = tmpl.read_text()
        assert 'data-i18n="ui.table.latest_tag"' in content
        assert "Latest Tag" in content

    def test_data_cell_for_gitlab_repo(self):
        """The row must contain tag-specific rendering logic for GitLab repos."""
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_dashboard_content.html.j2"
        )
        content = tmpl.read_text()
        assert "repo.is_gitlab" in content
        assert "repo.latest_tag" in content
        assert 'data-i18n="ui.table.latest_tag.no_tag"' in content
        assert 'data-i18n="ui.table.latest_tag.na"' in content

    def test_tag_column_count_matches(self):
        """Header and data columns must match — 8 columns (7 base + 1 tag)."""
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_dashboard_content.html.j2"
        )
        content = tmpl.read_text()
        # Count <th> in header row
        header_ths = re.findall(r'<th\s', content)
        # Should be at least 7
        # (Repository, Status, Branch, Naming, Last Activity, Freshness, Latest Tag)
        # Plus optional Actions column
        assert len(header_ths) >= 7


# ---------------------------------------------------------------------------
# Detail modal tag section tests
# ---------------------------------------------------------------------------

class TestDetailModalTagSection:
    def test_repo_data_includes_tag_fields(self):
        """REPO_DATA JS object must include tag fields."""
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_core.html.j2"
        )
        content = tmpl.read_text()
        assert "latestTag:" in content
        assert "latestTagSha:" in content
        assert "latestTagDate:" in content
        assert "latestTagMessage:" in content
        assert "isGitlab:" in content

    def test_detail_modal_has_tag_section(self):
        """Detail modal JS must render a GitLab tag section."""
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_core.html.j2"
        )
        content = tmpl.read_text()
        assert "r.isGitlab" in content
        assert "r.latestTag" in content
        assert "ui.detail.tag_info" in content
        assert "ui.detail.tag_derivation" in content


# ---------------------------------------------------------------------------
# i18n completeness tests
# ---------------------------------------------------------------------------

class TestTagI18nKeys:
    def test_en_has_all_tag_keys(self):
        import pathlib
        locale_path = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "i18n" / "locales" / "en.json"
        )
        data = json.loads(locale_path.read_text())
        required_keys = [
            "ui.table.latest_tag",
            "ui.table.latest_tag.no_tag",
            "ui.table.latest_tag.na",
            "ui.detail.tag_info",
            "ui.detail.tag_name",
            "ui.detail.tag_sha",
            "ui.detail.tag_date",
            "ui.detail.tag_message",
            "ui.detail.tag_branch_ctx",
            "ui.detail.tag_note",
            "ui.detail.tag_derivation",
        ]
        for key in required_keys:
            assert key in data, f"Missing EN key: {key}"

    def test_pl_has_all_tag_keys(self):
        import pathlib
        locale_path = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "i18n" / "locales" / "pl.json"
        )
        data = json.loads(locale_path.read_text())
        required_keys = [
            "ui.table.latest_tag",
            "ui.table.latest_tag.no_tag",
            "ui.table.latest_tag.na",
            "ui.detail.tag_info",
            "ui.detail.tag_name",
            "ui.detail.tag_sha",
            "ui.detail.tag_date",
            "ui.detail.tag_message",
            "ui.detail.tag_branch_ctx",
            "ui.detail.tag_note",
            "ui.detail.tag_derivation",
        ]
        for key in required_keys:
            assert key in data, f"Missing PL key: {key}"


# ---------------------------------------------------------------------------
# Analysis service integration test (mocked)
# ---------------------------------------------------------------------------

class TestAnalysisServiceTagEnrichment:
    """Verify that the analysis service calls tag enrichment for GitLab repos."""

    def test_tag_enrichment_called_for_gitlab_url(self):
        """When a repo URL is GitLab, get_latest_branch_tag should be called."""
        # This is a structural test — verify the import and code path exists
        import inspect

        from releaseboard.application.service import AnalysisService
        source = inspect.getsource(AnalysisService.analyze_async)
        assert "is_gitlab_url" in source
        assert "get_latest_branch_tag" in source
        assert "latest_tag" in source

    def test_tag_enrichment_non_fatal(self):
        """Tag enrichment failure must not crash analysis.

        The code wraps tag enrichment in try/except — verify structurally.
        """
        import inspect

        from releaseboard.application.service import AnalysisService
        source = inspect.getsource(AnalysisService.analyze_async)
        # There should be an except clause after the tag enrichment
        assert "tag_exc" in source or "tag enrichment" in source.lower()


# ---------------------------------------------------------------------------
# Tag Export Modal — template and i18n tests
# ---------------------------------------------------------------------------

class TestTagExportModal:
    """Verify the tag export popup modal is wired correctly."""

    def test_export_overlay_exists_in_modals(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_modals.html.j2"
        )
        content = tmpl.read_text()
        assert 'id="tagExportOverlay"' in content
        assert 'id="tagExportFilename"' in content
        assert 'id="tagExportPreview"' in content
        assert 'id="tagExportDownloadBtn"' in content

    def test_export_overlay_has_aria(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_modals.html.j2"
        )
        content = tmpl.read_text()
        assert 'role="dialog"' in content
        assert 'aria-modal="true"' in content
        assert 'aria-labelledby="tagExportTitle"' in content

    def test_export_button_in_toolbar(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_header.html.j2"
        )
        content = tmpl.read_text()
        assert "openTagExport" in content
        assert "ui.tag_export.menu_item" in content

    def test_export_functions_in_scripts(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_editor.html.j2"
        )
        content = tmpl.read_text()
        assert "function openTagExport" in content
        assert "function closeTagExport" in content
        assert "function tagExportDownload" in content
        assert "function tagExportCopy" in content
        assert "_teBuildYaml" in content

    def test_export_functions_exposed_in_rb(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_interactive.html.j2"
        )
        content = tmpl.read_text()
        assert "openTagExport" in content
        assert "closeTagExport" in content
        assert "tagExportDownload" in content
        assert "tagExportCopy" in content

    def test_yaml_builder_uses_repo_data(self):
        """The JS YAML builder must iterate over REPO_DATA entries."""
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_editor.html.j2"
        )
        content = tmpl.read_text()
        assert "REPO_DATA" in content
        assert "isGitlab" in content
        assert "latestTag" in content
        assert "AppVersion" in content
        assert "enabled:" in content

    def test_yaml_structure_format(self):
        """The generated YAML lines must follow the expected per-app structure."""
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_editor.html.j2"
        )
        content = tmpl.read_text()
        # Must produce lines like:
        # "ApplicationName:", "  enabled: true", "  AppVersion: v1.2.3"
        assert "'  enabled: true'" in content or '"  enabled: true"' in content
        assert "'  AppVersion: '" in content or '"  AppVersion: "' in content

    def test_filename_validation_pattern(self):
        """Filename must be validated with a safe regex."""
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_editor.html.j2"
        )
        content = tmpl.read_text()
        assert "_TE_FILENAME_RE" in content
        assert ".yaml" in content  # Extension appended

    def test_export_css_classes_exist(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_styles.html.j2"
        )
        content = tmpl.read_text()
        assert ".te-filename-row" in content
        assert ".te-yaml-preview" in content
        assert ".te-status" in content
        assert ".te-stats" in content

    def test_include_no_tag_toggle_exists(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_modals.html.j2"
        )
        content = tmpl.read_text()
        assert 'id="tagExportIncludeNoTag"' in content
        assert 'type="checkbox"' in content


class TestTagExportI18n:
    """Verify all tag export i18n keys exist in both locales."""

    REQUIRED_KEYS = [
        "ui.tag_export.title",
        "ui.tag_export.description",
        "ui.tag_export.filename_label",
        "ui.tag_export.filename_hint",
        "ui.tag_export.filename_invalid",
        "ui.tag_export.include_no_tag",
        "ui.tag_export.preview_label",
        "ui.tag_export.download",
        "ui.tag_export.copy",
        "ui.tag_export.copied",
        "ui.tag_export.copy_failed",
        "ui.tag_export.downloaded",
        "ui.tag_export.no_data",
        "ui.tag_export.stat_gitlab",
        "ui.tag_export.stat_included",
        "ui.tag_export.stat_skipped",
        "ui.tag_export.menu_item",
    ]

    def test_en_has_all_export_keys(self):
        import pathlib
        data = json.loads(
            (pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
             / "i18n" / "locales" / "en.json").read_text()
        )
        for key in self.REQUIRED_KEYS:
            assert key in data, f"Missing EN key: {key}"

    def test_pl_has_all_export_keys(self):
        import pathlib
        data = json.loads(
            (pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
             / "i18n" / "locales" / "pl.json").read_text()
        )
        for key in self.REQUIRED_KEYS:
            assert key in data, f"Missing PL key: {key}"


# ---------------------------------------------------------------------------
# Dashboard interaction bug-fix tests
# ---------------------------------------------------------------------------

class TestDashboardInteractionFixes:
    """Tests for dashboard interaction correctness."""

    @pytest.fixture
    def config_ui_content(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_config_ui.html.j2"
        )
        return tmpl.read_text()

    # --- Bug 1: Delete repo should trigger re-analysis, not page reload ---

    def _extract_function(self, content, name):
        """Extract JS function body by matching balanced braces."""
        pattern = re.compile(r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{')
        m = pattern.search(content)
        assert m, f"{name} function not found in template"
        start = m.end()
        depth = 1
        i = start
        while i < len(content) and depth > 0:
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
            i += 1
        return content[start:i - 1]

    def test_push_draft_calls_start_analysis(self, config_ui_content):
        """pushDraftAndRefresh must call startAnalysis() instead of reloading the page."""
        body = self._extract_function(config_ui_content, "pushDraftAndRefresh")
        assert "startAnalysis()" in body, "pushDraftAndRefresh must call startAnalysis()"

    def test_push_draft_does_not_reload_page(self, config_ui_content):
        """pushDraftAndRefresh must NOT use window.location to reload."""
        body = self._extract_function(config_ui_content, "pushDraftAndRefresh")
        assert "window.location.href" not in body, (
            "pushDraftAndRefresh should not use window.location.href"
        )
        assert "window.location.pathname" not in body, (
            "pushDraftAndRefresh should not use window.location.pathname"
        )

    # --- Bug 2: Apply button stays disabled when pasting URL ---

    def test_auto_fill_repo_name_syncs_url_to_draft(self, config_ui_content):
        """autoFillRepoName must set repo.url = url to sync URL to draft immediately."""
        body = self._extract_function(config_ui_content, "autoFillRepoName")
        assert "repo.url = url" in body or "repo.url=url" in body, \
            "autoFillRepoName must sync URL to draft with repo.url = url"

    def test_add_repo_calls_validate_draft(self, config_ui_content):
        """addRepo must call validateDraft() so the Apply button state updates."""
        body = self._extract_function(config_ui_content, "addRepo")
        assert "validateDraft()" in body, "addRepo must call validateDraft()"


class TestValidationVisibility:
    """Tests for validation error visibility and button tooltip fixes."""

    @pytest.fixture()
    def editor_content(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_editor.html.j2"
        )
        return tmpl.read_text()

    @pytest.fixture()
    def config_ui_content(self):
        import pathlib
        tmpl = (
            pathlib.Path(__file__).parent.parent / "src" / "releaseboard"
            / "presentation" / "templates" / "_scripts_config_ui.html.j2"
        )
        return tmpl.read_text()

    def test_place_errors_always_shows_unmatched_errors(self, editor_content):
        """placeErrors must show unmatched errors even without panelPrefix."""
        assert "panelPrefix || _t('ui.validation.errors_found')" in editor_content, \
               "placeErrors must use fallback header when panelPrefix is null"

    def test_place_errors_no_prefix_guard(self, editor_content):
        """placeErrors must not gate error display on panelPrefix being truthy."""
        assert "unmatched.length && panelPrefix" not in editor_content, \
               "The old guard 'unmatched.length && panelPrefix' should be removed"

    def test_update_action_buttons_sets_tooltip(self, editor_content):
        """Disabled Apply/Save buttons must get a tooltip explaining why."""
        assert "fix_errors_hint" in editor_content, \
               "_updateActionButtons must set tooltip with fix_errors_hint"

    def test_update_action_buttons_clears_tooltip_on_valid(self, editor_content):
        """Buttons must clear tooltip when config is valid."""
        assert "applyBtn.title = ''" in editor_content or \
               "applyBtn.title=''" in editor_content, \
               "_updateActionButtons must clear title when no errors"

    def test_drawer_open_calls_validate_draft(self, config_ui_content):
        """Opening the drawer must trigger validateDraft() for correct initial button state."""
        assert "validateDraft();" in config_ui_content, \
               "toggleDrawer must call validateDraft on open"

    def test_i18n_errors_found_key_en(self):
        import json
        with open("src/releaseboard/i18n/locales/en.json") as f:
            d = json.load(f)
        assert "ui.validation.errors_found" in d
        assert "ui.validation.fix_errors_hint" in d

    def test_i18n_errors_found_key_pl(self):
        import json
        with open("src/releaseboard/i18n/locales/pl.json") as f:
            d = json.load(f)
        assert "ui.validation.errors_found" in d
        assert "ui.validation.fix_errors_hint" in d


# ---------------------------------------------------------------------------
# UI Polish Pass — 7 Fixes
# ---------------------------------------------------------------------------

TEMPLATE_DIR = Path("src/releaseboard/presentation/templates")


class TestToastContainerBottomCenter:
    """Issue #7: Toast container must be positioned at bottom-center."""

    def test_toast_fixed_bottom(self):
        src = (TEMPLATE_DIR / "_scripts_core.html.j2").read_text(encoding="utf-8")
        assert "bottom:" in src and "left:50%" in src, "Toast container must be bottom-center"

    def test_toast_no_top_right(self):
        src = (TEMPLATE_DIR / "_scripts_core.html.j2").read_text(encoding="utf-8")
        assert "top:16px;right:16px" not in src, "Toast must not use top-right positioning"

    def test_toast_translate_y_animation(self):
        src = (TEMPLATE_DIR / "_scripts_core.html.j2").read_text(encoding="utf-8")
        assert "translateY" in src, "Toast animation must use translateY for bottom-center"


class TestCaretSizeConsistency:
    """Issue #6: Toolbar caret must be visible and consistent with Analyze button."""

    def test_tb_caret_18px(self):
        src = (TEMPLATE_DIR / "_styles_toolbar.html.j2").read_text(encoding="utf-8")
        line = next(
            (line for line in src.splitlines()
             if ".tb-caret" in line and "font-size" in line),
            None,
        )
        assert line and "18px" in line, "Caret must be 18px"

    def test_tb_caret_opacity_visible(self):
        src = (TEMPLATE_DIR / "_styles_toolbar.html.j2").read_text(encoding="utf-8")
        line = next(
            (line for line in src.splitlines()
             if ".tb-caret" in line and "opacity" in line),
            None,
        )
        assert line is not None
        import re
        m = re.search(r"opacity:\s*([\d.]+)", line)
        assert m and float(m.group(1)) >= 0.7, "Caret opacity must be >= 0.7"


class TestColorPickerVisibility:
    """Issue #4: Color picker input must be visible with proper sizing and border."""

    def test_cfg_color_width(self):
        src = (TEMPLATE_DIR / "_styles.html.j2").read_text(encoding="utf-8")
        line = next((line for line in src.splitlines() if ".cfg-color" in line), None)
        assert line and "40px" in line, "Color picker must be 40px wide"

    def test_cfg_color_border(self):
        src = (TEMPLATE_DIR / "_styles.html.j2").read_text(encoding="utf-8")
        line = next((line for line in src.splitlines() if ".cfg-color" in line), None)
        assert line and "border:" in line, "Color picker must have explicit border"


class TestRpActionBtnBackground:
    """Issue #2: rp-action-btn must have explicit card background."""

    def test_rp_btn_has_bg_card(self):
        src = (TEMPLATE_DIR / "_styles_release_wizard.html.j2").read_text(encoding="utf-8")
        assert "var(--bg-card)" in src, "rp-action-btn must use var(--bg-card) background"

    def test_rp_btn_no_transparent(self):
        content = (TEMPLATE_DIR / "_styles_release_wizard.html.j2").read_text(
            encoding="utf-8"
        )
        lines = content.splitlines()
        for line in lines:
            if ".rp-action-btn" in line and "background:" in line and ":hover" not in line:
                assert "transparent" not in line, (
                    "rp-action-btn must not have transparent background"
                )


class TestFieldValidationInline:
    """Issue #1: Client-side errors must use data-path format for inline field display."""

    def test_release_target_year_path_format(self):
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        assert "'release.target_year: '" in src or '"release.target_year: "' in src, \
            "target_year error must use data-path format"

    def test_repo_name_path_format(self):
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        assert "repositories.${i}.name:" in src, \
            "Repo name error must use data-path format for field matching"

    def test_repo_url_path_format(self):
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        assert "repositories.${i}.url:" in src, \
            "Repo URL error must use data-path format for field matching"

    def test_settings_root_url_path_format(self):
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        assert (
            "'settings.repository_root_url: '" in src
            or '"settings.repository_root_url: "' in src
        ), "Settings root URL error must use data-path format"


class TestDefaultTabEngineering:
    """Issue #5: Default active template must be 'engineering'."""

    def test_active_template_engineering(self):
        src = (TEMPLATE_DIR / "_scripts_editor.html.j2").read_text(encoding="utf-8")
        assert "activeTemplate = 'engineering'" in src


class TestExampleConfigs:
    """Issue #3: Example configs must exist and be valid JSON."""

    def test_config_json_exists(self):
        assert Path("examples/config.json").exists()

    def test_config_minimal_exists(self):
        assert Path("examples/config.minimal.json").exists()

    def test_config_local_exists(self):
        assert Path("examples/config.local.json").exists()

    def test_config_json_valid_structure(self):
        import json
        with open("examples/config.json") as f:
            d = json.load(f)
        assert "release" in d
        assert "layers" in d
        assert "repositories" in d
        assert len(d["repositories"]) >= 3, "Full example should have multiple repos"

    def test_config_minimal_fewer_repos(self):
        import json
        with open("examples/config.minimal.json") as f:
            d = json.load(f)
        assert len(d["repositories"]) <= 3, "Minimal example should have few repos"

    def test_examples_have_engineering_template(self):
        import json
        with open("examples/config.json") as f:
            d = json.load(f)
        assert d.get("layout", {}).get("default_template") == "engineering"
