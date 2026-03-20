"""Feature tests — git providers: URL parsing, name derivation, error
classification, placeholder detection, public-repo handling, default-branch
fallback, smart provider, diagnostics."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from pathlib import Path

from releaseboard.config.models import (
    AppConfig,
    LayerConfig,
    ReleaseConfig,
    RepositoryConfig,
    derive_name_from_url,
)
from releaseboard.domain.enums import ReadinessStatus
from releaseboard.domain.models import BranchInfo
from releaseboard.git.github_provider import parse_github_url
from releaseboard.git.provider import (
    GitAccessError,
    GitErrorKind,
)
from releaseboard.git.smart_provider import SmartGitProvider


def _all_template_content() -> str:
    """Read all template partials concatenated for string checks."""
    tmpl_dir = Path(__file__).parent.parent / "src" / "releaseboard" / "presentation" / "templates"
    parts = []
    for f in sorted(tmpl_dir.glob("*.j2")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "src" / "releaseboard" / "presentation" / "templates"


def _html() -> str:
    """Read and concatenate all template partials for string-based checks."""
    parts = []
    for f in sorted(TEMPLATE_DIR.glob("*.j2")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _make_config(**overrides) -> AppConfig:
    return AppConfig(
        release=ReleaseConfig(
            name="Test Release",
            target_month=3,
            target_year=2025,
            branch_pattern="release/{MM}.{YYYY}",
        ),
        layers=[LayerConfig(id="api", label="API")],
        repositories=[
            RepositoryConfig(name="TestRepo", url="https://github.com/org/repo", layer="api"),
        ],
        **overrides,
    )


# ──────────────────────────────────────────────────────────────────────────────
# URL → name derivation
# ──────────────────────────────────────────────────────────────────────────────


class TestDeriveNameFromUrl:
    """Scenarios for derive_name_from_url() utility."""

    def test_bare_slug(self):
        """GIVEN a bare slug without URL scheme."""
        url = "my-service"

        """WHEN deriving the name from the URL."""
        result = derive_name_from_url(url)

        """THEN the slug itself is the name."""
        assert result == "my-service"

    def test_local_path(self):
        """GIVEN a local filesystem path."""
        url = "/home/user/repos/my-tool"

        """WHEN deriving the name from the URL."""
        result = derive_name_from_url(url)

        """THEN the directory name is extracted."""
        assert result == "my-tool"

    def test_local_path_with_git_suffix(self):
        """GIVEN a local path with .git suffix."""
        url = "/home/user/repos/my-tool.git"

        """WHEN deriving the name from the URL."""
        result = derive_name_from_url(url)

        """THEN the .git suffix is stripped."""
        assert result == "my-tool"


# ──────────────────────────────────────────────────────────────────────────────
# GitHub URL parsing
# ──────────────────────────────────────────────────────────────────────────────


class TestParseGitHubUrl:
    """Scenarios for parse_github_url() helper."""

    def test_local_path_returns_none(self):
        """GIVEN a local filesystem path."""
        url = "/home/user/repo"

        """WHEN parsing the GitHub URL."""
        result = parse_github_url(url)

        """THEN None is returned."""
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# SmartGitProvider routing
# ──────────────────────────────────────────────────────────────────────────────


class TestSmartGitProvider:
    """Scenarios for SmartGitProvider routing to the correct provider."""

    def test_github_url_uses_github_provider(self):
        """GIVEN a SmartGitProvider and a GitHub URL."""
        provider = SmartGitProvider()
        url = "https://github.com/acme/repo"

        """WHEN checking if the URL is a GitHub URL."""
        result = provider._is_github(url)

        """THEN it is identified as GitHub."""
        assert result is True

    def test_local_path_uses_local_provider(self):
        """GIVEN a SmartGitProvider and a local path."""
        provider = SmartGitProvider()
        url = "/home/user/repos/my-app"

        """WHEN checking if the path is a GitHub URL."""
        result = provider._is_github(url)

        """THEN it is not identified as GitHub."""
        assert result is False

    def test_non_github_remote_uses_local_provider(self):
        """GIVEN a SmartGitProvider and a non-GitHub remote URL."""
        provider = SmartGitProvider()
        url = "https://gitlab.com/acme/repo.git"

        """WHEN checking if the URL is a GitHub URL."""
        result = provider._is_github(url)

        """THEN it is not identified as GitHub."""
        assert result is False


# ──────────────────────────────────────────────────────────────────────────────
# BranchInfo enriched fields
# ──────────────────────────────────────────────────────────────────────────────


class TestBranchInfoEnrichedFields:
    """Scenarios for BranchInfo enriched metadata fields."""

    def test_new_fields_default_to_none(self):
        """GIVEN a BranchInfo with only required fields."""
        info = BranchInfo(name="main", exists=True)

        """WHEN accessing enriched metadata fields."""
        sha = info.last_commit_sha
        desc = info.repo_description
        default_branch = info.repo_default_branch
        visibility = info.repo_visibility
        owner = info.repo_owner
        archived = info.repo_archived
        web_url = info.repo_web_url
        updated_at = info.provider_updated_at

        """THEN all enriched fields default to None."""
        assert sha is None
        assert desc is None
        assert default_branch is None
        assert visibility is None
        assert owner is None
        assert archived is None
        assert web_url is None
        assert updated_at is None

    def test_new_fields_can_be_set(self):
        """GIVEN a BranchInfo with all enriched fields set."""
        info = BranchInfo(
            name="release/2025.03",
            exists=True,
            last_commit_sha="abc123",
            repo_description="My service",
            repo_default_branch="main",
            repo_visibility="private",
            repo_owner="acme",
            repo_archived=False,
            repo_web_url="https://github.com/acme/my-service",
            provider_updated_at=datetime(2025, 3, 1, tzinfo=UTC),
        )

        """WHEN accessing the enriched fields."""
        sha = info.last_commit_sha
        owner = info.repo_owner
        archived = info.repo_archived

        """THEN the values match what was set."""
        assert sha == "abc123"
        assert owner == "acme"
        assert archived is False


class TestGitAccessErrorFields:
    """Scenarios for GitAccessError structured kind and user_message."""

    def test_auto_classification(self):
        """GIVEN a GitAccessError with a 'Repository not found' detail."""
        err = GitAccessError("https://github.com/x/y", "Repository not found.")

        """WHEN inspecting the error fields."""
        kind = err.kind
        user_message = err.user_message
        detail = err.detail

        """THEN the error is auto-classified as REPO_NOT_FOUND."""
        assert kind == GitErrorKind.REPO_NOT_FOUND
        assert user_message == "Repository not found"
        assert detail == "Repository not found."

    def test_explicit_kind(self):
        """GIVEN a GitAccessError with an explicit kind override."""
        err = GitAccessError("url", "msg", kind=GitErrorKind.TIMEOUT)

        """WHEN inspecting the error kind."""
        kind = err.kind

        """THEN the explicit kind is used."""
        assert kind == GitErrorKind.TIMEOUT

    def test_placeholder_url_error(self):
        """GIVEN a GitAccessError for a placeholder URL."""
        err = GitAccessError("https://git.example.com/org/repo", "fatal: unable to access")

        """WHEN inspecting the error fields."""
        kind = err.kind
        user_message = err.user_message

        """THEN it is classified as PLACEHOLDER_URL."""
        assert kind == GitErrorKind.PLACEHOLDER_URL
        assert user_message == "Placeholder/example URL"

    def test_error_kind_values(self):
        """GIVEN all GitErrorKind enum members."""
        kinds = list(GitErrorKind)

        """WHEN checking user_message for each kind."""
        messages = [(kind, kind.user_message) for kind in kinds]

        """THEN every kind has a non-empty user_message."""
        for kind, msg in messages:
            assert msg, f"Missing user_message for {kind.value}"


class TestRepositoryAnalysisErrorFields:
    """Scenarios for RepositoryAnalysis error_kind and error_detail fields."""

    def test_error_fields_default_none(self):
        """GIVEN a RepositoryAnalysis without error_kind or error_detail."""
        from releaseboard.domain.models import RepositoryAnalysis

        a = RepositoryAnalysis(
            name="test", url="url", layer="fe",
            default_branch="main", expected_pattern="release/{YYYY}.{MM}",
            expected_branch_name="release/2025.03",
            status=ReadinessStatus.ERROR,
            error_message="fail",
        )

        """WHEN accessing error fields."""
        error_kind = a.error_kind
        error_detail = a.error_detail

        """THEN both default to None."""
        assert error_kind is None
        assert error_detail is None

    def test_error_fields_set(self):
        """GIVEN a RepositoryAnalysis with error_kind and error_detail set."""
        from releaseboard.domain.models import RepositoryAnalysis

        a = RepositoryAnalysis(
            name="test", url="url", layer="fe",
            default_branch="main", expected_pattern="release/{YYYY}.{MM}",
            expected_branch_name="release/2025.03",
            status=ReadinessStatus.ERROR,
            error_message="Host not found",
            error_kind="dns_resolution",
            error_detail="fatal: Could not resolve host: git.acme.com",
        )

        """WHEN accessing the error fields."""
        error_kind = a.error_kind
        error_detail = a.error_detail

        """THEN the values match what was set."""
        assert error_kind == "dns_resolution"
        assert error_detail == "fatal: Could not resolve host: git.acme.com"


class TestRepoViewModelErrorFields:
    """Scenarios for RepoViewModel error_kind and error_detail fields."""

    def test_view_model_has_error_fields(self):
        """GIVEN a RepoViewModel with error_kind and error_detail."""
        from releaseboard.presentation.view_models import RepoViewModel

        vm = RepoViewModel(
            name="x", url="u", layer="l", layer_label="L",
            status="error", status_label="Error",
            status_color_bg="#c52a2a", status_color_fg="#fff",
            status_badge_bg="#fce8e8", status_badge_fg="#8b1a1a",
            expected_branch="b", actual_branch="",
            naming_valid=False, is_stale=False,
            last_activity="", last_activity_raw="", first_activity="",
            last_author="", last_message="", commit_count="0",
            freshness="", warnings=[], notes=[],
            error_message="Host not found",
            error_kind="dns_resolution",
            error_detail="could not resolve host",
            branch_exists=False,
        )

        """WHEN accessing the error fields."""
        error_kind = vm.error_kind
        error_detail = vm.error_detail

        """THEN the values match what was set."""
        assert error_kind == "dns_resolution"
        assert error_detail == "could not resolve host"


class TestSectionIdentity:
    """Scenarios for dashboard section stable IDs."""

    def test_template_has_section_ids(self):
        """GIVEN the concatenated template content."""
        content = _all_template_content()
        expected_ids = ["metrics", "filters", "summary"]

        """WHEN checking for data-section-id attributes."""
        found = {sid: f'data-section-id="{sid}"' in content for sid in expected_ids}
        has_dynamic = 'data-section-id="layer-{{ layer.id }}"' in content

        """THEN all expected section IDs are present."""
        for sid in expected_ids:
            assert found[sid], f"Missing section ID: {sid}"
        assert has_dynamic

    def test_template_has_dashboard_sections(self):
        """GIVEN the concatenated template content."""
        content = _all_template_content()

        """WHEN checking for dashboard section markers."""
        has_section = 'class="dashboard-section"' in content or 'dashboard-section' in content

        """THEN dashboard sections exist."""
        assert has_section

    def test_predefined_templates_in_js(self):
        """GIVEN the concatenated template content."""
        content = _all_template_content()
        template_names = ["executive", "release-manager", "engineering", "compact"]

        """WHEN checking for predefined layout templates."""
        has_constant = "PREDEFINED_TEMPLATES" in content
        found = {name: f"'{name}'" in content for name in template_names}

        """THEN all predefined templates are present."""
        assert has_constant
        for name in template_names:
            assert found[name], f"Missing predefined template: {name}"


# ===========================================================================
# Error classification: distinguish branch-not-found vs provider error
# ===========================================================================


# ===========================================================================
# Provider metadata and default-branch fallback
# ===========================================================================


# ===========================================================================
# GitHub provider improvements
# ===========================================================================


# ===========================================================================
# Public GitHub repo scenarios
# ===========================================================================


# ===========================================================================
# Service-level: default branch fallback integration
# ===========================================================================

class TestServiceDefaultBranchFallback:
    """Scenarios for service-level default-branch fallback."""

    def test_service_imports_matcher(self):
        """GIVEN the AnalysisService class."""
        from releaseboard.application.service import AnalysisService
        pathlib.Path(AnalysisService.__module__.replace('.', '/') + '.py')

        """WHEN verifying the import chain."""
        result = AnalysisService

        """THEN the AnalysisService is importable."""
        assert result is not None


# ===========================================================================
# Main board status and details diagnostics
# ===========================================================================

class TestDetailDiagnostics:
    """Scenarios for details panel diagnostics for reachable repos."""

    def test_template_has_diagnostics_section(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking for the diagnostics section."""
        has_diagnostics = "Diagnostics" in html

        """THEN the diagnostics section exists."""
        assert has_diagnostics

    def test_template_diagnostics_shows_connectivity(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking for connectivity diagnostics."""
        has_connectivity = "Repository reachable" in html or "repo_reachable" in html

        """THEN connectivity information is shown."""
        assert has_connectivity

    def test_template_diagnostics_shows_release_branch_status(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking for release branch status diagnostics."""
        has_status = (
            "Release readiness blocked" in html
            or "expected branch not created" in html
            or "blocked_msg" in html
        )

        """THEN release branch status is shown."""
        assert has_status

    def test_repo_view_model_has_provider_fields(self):
        """GIVEN the RepoViewModel dataclass."""
        import dataclasses

        from releaseboard.presentation.view_models import RepoViewModel
        fields = {f.name for f in dataclasses.fields(RepoViewModel)}

        """WHEN checking for provider metadata fields."""
        expected = {
            "repo_default_branch", "repo_visibility",
            "repo_description", "repo_web_url", "repo_owner",
        }
        expected & fields

        """THEN all provider fields are present."""
        assert "repo_default_branch" in fields
        assert "repo_visibility" in fields
        assert "repo_description" in fields
        assert "repo_web_url" in fields
        assert "repo_owner" in fields


# ===========================================================================
# Identity consistency
# ===========================================================================

class TestIdentityConsistency:
    """Scenarios for identity consistency in templates."""

    def test_no_acmeboard_in_template(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking for AcmeBoard references."""
        has_acmeboard = "AcmeBoard" in html

        """THEN no AcmeBoard remnants exist."""
        assert not has_acmeboard

    def test_no_acme_inc_in_template(self):
        """GIVEN the concatenated template HTML."""
        html = _html()

        """WHEN checking for Acme Inc references."""
        has_acme_inc = "Acme Inc" in html

        """THEN no Acme Inc hardcoding exists."""
        assert not has_acme_inc
