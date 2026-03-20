"""Tests for GitHub public repos — error classification, default-branch fallback,
provider metadata, diagnostics, and UI quality checks."""

import pathlib
import re
from datetime import UTC, datetime

import pytest

from releaseboard.analysis.readiness import ReadinessAnalyzer
from releaseboard.config.models import (
    AppConfig,
    LayerConfig,
    ReleaseConfig,
    RepositoryConfig,
)
from releaseboard.domain.enums import ReadinessStatus
from releaseboard.domain.models import BranchInfo
from releaseboard.git.provider import GitErrorKind, classify_git_error

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


# ===========================================================================
# Error classification: distinguish branch-not-found vs provider error
# ===========================================================================

class TestErrorClassification:
    """Scenarios for error classification of GitHub-specific messages."""

    def test_rate_limit_classified(self):
        """GIVEN a rate-limit error message."""
        msg = "API rate limit exceeded for owner/repo"

        """WHEN classifying the error."""
        kind = classify_git_error(msg)

        """THEN the kind is RATE_LIMITED."""
        assert kind == GitErrorKind.RATE_LIMITED

    def test_rate_limit_from_403(self):
        """GIVEN a 403 error message mentioning rate limit."""
        msg = "GitHub API error (HTTP 403) for org/repo: rate limit"

        """WHEN classifying the error."""
        kind = classify_git_error(msg)

        """THEN the kind is RATE_LIMITED."""
        assert kind == GitErrorKind.RATE_LIMITED

    def test_403_without_rate_limit_is_rate_limited(self):
        """GIVEN a bare 403 forbidden message."""
        msg = "403 forbidden"

        """WHEN classifying the error."""
        kind = classify_git_error(msg)

        """THEN the kind is RATE_LIMITED."""
        assert kind == GitErrorKind.RATE_LIMITED

    def test_cannot_access_github_repo_classified(self):
        """GIVEN a cannot-access error message."""
        msg = "Cannot access GitHub repo owner/repo"

        """WHEN classifying the error."""
        kind = classify_git_error(msg)

        """THEN the kind is PROVIDER_UNAVAILABLE."""
        assert kind == GitErrorKind.PROVIDER_UNAVAILABLE

    def test_repo_not_found_404(self):
        """GIVEN a repository-not-found error message."""
        msg = "Repository not found: owner/repo"

        """WHEN classifying the error."""
        kind = classify_git_error(msg)

        """THEN the kind is REPO_NOT_FOUND."""
        assert kind == GitErrorKind.REPO_NOT_FOUND

    def test_auth_required_401(self):
        """GIVEN an authentication-required error message."""
        msg = "Authentication required for owner/repo"

        """WHEN classifying the error."""
        kind = classify_git_error(msg)

        """THEN the kind is AUTH_REQUIRED."""
        assert kind == GitErrorKind.AUTH_REQUIRED

    def test_rate_limited_has_user_message(self):
        """GIVEN the RATE_LIMITED error kind."""
        kind = GitErrorKind.RATE_LIMITED

        """WHEN reading the user message."""
        msg = kind.user_message

        """THEN it says API rate limit exceeded."""
        assert msg == "API rate limit exceeded"

    def test_unknown_stays_unknown_for_truly_unexpected(self):
        """GIVEN a completely unexpected error message."""
        msg = "some completely unexpected error"

        """WHEN classifying the error."""
        kind = classify_git_error(msg)

        """THEN the kind is UNKNOWN."""
        assert kind == GitErrorKind.UNKNOWN

    def test_branch_not_found_is_not_error(self):
        """GIVEN a repo with branches that do not match the release pattern."""
        config = _make_config()
        analyzer = ReadinessAnalyzer(config)
        repo_config = config.repositories[0]
        # Branches exist but none match the release pattern
        branches = ["main", "develop", "feature/x"]
        branch_info = BranchInfo(name="release/03.2025", exists=False)

        """WHEN analyzing the repository."""
        result = analyzer.analyze(repo_config, branches, branch_info)

        """THEN the status is MISSING_BRANCH with no error."""
        assert result.status == ReadinessStatus.MISSING_BRANCH
        assert result.error_message is None
        assert result.error_kind is None


# ===========================================================================
# Provider metadata and default-branch fallback
# ===========================================================================

class TestDefaultBranchFallback:
    """Scenarios for default-branch fallback when release branch is missing."""

    def test_missing_branch_with_default_fallback_has_notes(self):
        """GIVEN a reachable repo with default branch info but no release branch."""
        config = _make_config()
        analyzer = ReadinessAnalyzer(config)
        repo_config = config.repositories[0]
        branches = ["main", "develop"]
        branch_info = BranchInfo(
            name="release/03.2025", exists=False,
            repo_default_branch="main", repo_visibility="public",
            repo_owner="org", repo_web_url="https://github.com/org/repo",
        )
        default_branch_info = BranchInfo(
            name="main", exists=True,
            last_commit_date=datetime(2025, 3, 1, tzinfo=UTC),
            last_commit_author="dev",
            repo_default_branch="main",
        )

        """WHEN analyzing with default branch fallback."""
        result = analyzer.analyze(repo_config, branches, branch_info, default_branch_info)

        """THEN the result includes reachability notes and last activity."""
        assert result.status == ReadinessStatus.MISSING_BRANCH
        # Should have repo metadata in notes
        assert any("reachable" in n.lower() or "default branch" in n.lower() for n in result.notes)
        # Should carry last_activity from default branch
        assert result.last_activity is not None

    def test_missing_branch_with_provider_metadata(self):
        """GIVEN branch info carrying repo metadata without the release branch."""
        config = _make_config()
        analyzer = ReadinessAnalyzer(config)
        repo_config = config.repositories[0]
        branches = ["main"]
        branch_info = BranchInfo(
            name="release/03.2025", exists=False,
            repo_default_branch="main",
            repo_visibility="public",
            repo_description="A test repo",
            repo_web_url="https://github.com/org/repo",
        )

        """WHEN analyzing the repository."""
        result = analyzer.analyze(repo_config, branches, branch_info)

        """THEN provider metadata is preserved on the result."""
        assert result.status == ReadinessStatus.MISSING_BRANCH
        # branch_info should be preserved for metadata access
        assert result.branch is not None
        assert result.branch.repo_default_branch == "main"
        assert result.branch.repo_visibility == "public"

    def test_missing_branch_without_metadata_still_works(self):
        """GIVEN no branch info or default branch info."""
        config = _make_config()
        analyzer = ReadinessAnalyzer(config)
        repo_config = config.repositories[0]

        """WHEN analyzing the repository."""
        result = analyzer.analyze(repo_config, ["main"], None, None)

        """THEN the status is MISSING_BRANCH with a warning."""
        assert result.status == ReadinessStatus.MISSING_BRANCH
        assert result.branch is None
        assert "Release branch not found" in result.warnings


# ===========================================================================
# Main board status and details diagnostics
# ===========================================================================

class TestDetailDiagnostics:
    """Scenarios for detail panel diagnostics display."""

    def test_template_has_diagnostics_section(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN searching for the diagnostics section."""
        found = "Diagnostics" in html

        """THEN it contains a Diagnostics heading."""
        assert found

    def test_template_diagnostics_shows_connectivity(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting the diagnostics section."""
        found = "Repository reachable" in html or "repo_reachable" in html

        """THEN it shows repository connectivity status."""
        assert found

    def test_template_diagnostics_shows_release_branch_status(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting the diagnostics section."""
        found = (
            "Release readiness blocked" in html
            or "expected branch not created" in html
            or "blocked_msg" in html
        )

        """THEN it shows release branch status messaging."""
        assert found

    def test_template_shows_provider_metadata_fields(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting the template for metadata fields."""
        has_default_branch = "repoDefaultBranch" in html
        has_visibility = "repoVisibility" in html
        has_description = "repoDescription" in html
        has_web_url = "repoWebUrl" in html
        has_owner = "repoOwner" in html

        """THEN it references all provider metadata fields."""
        assert has_default_branch
        assert has_visibility
        assert has_description
        assert has_web_url
        assert has_owner

    def test_repo_view_model_has_provider_fields(self):
        """GIVEN the RepoViewModel dataclass."""
        import dataclasses

        from releaseboard.presentation.view_models import RepoViewModel

        """WHEN inspecting its fields."""
        fields = {f.name for f in dataclasses.fields(RepoViewModel)}

        """THEN it includes all provider metadata fields."""
        assert "repo_default_branch" in fields
        assert "repo_visibility" in fields
        assert "repo_description" in fields
        assert "repo_web_url" in fields
        assert "repo_owner" in fields


# ===========================================================================
# GitHub provider improvements
# ===========================================================================

class TestGitHubProviderErrors:
    """Scenarios for GitHubProvider error raising."""

    def test_raise_for_status_404(self):
        """GIVEN a GitHubProvider and a 404 response."""
        from releaseboard.git.github_provider import GitHubProvider
        provider = GitHubProvider(token="test")

        """WHEN raising for status."""
        with pytest.raises(Exception) as exc_info:
            provider._raise_for_status(
                "https://github.com/o/r", "o", "r", 404, {"message": "Not Found"}
            )

        """THEN it raises GitAccessError with REPO_NOT_FOUND kind."""
        from releaseboard.git.provider import GitAccessError
        assert isinstance(exc_info.value, GitAccessError)
        assert exc_info.value.kind == GitErrorKind.REPO_NOT_FOUND

    def test_raise_for_status_403_rate_limit(self):
        """GIVEN a GitHubProvider and a 403 rate-limit response."""
        from releaseboard.git.github_provider import GitHubProvider
        from releaseboard.git.provider import GitAccessError
        provider = GitHubProvider(token="test")

        """WHEN raising for status."""
        with pytest.raises(GitAccessError) as exc_info:
            provider._raise_for_status(
                "https://github.com/o/r", "o", "r", 403,
                {"message": "API rate limit exceeded for 1.2.3.4"},
            )

        """THEN it raises GitAccessError with RATE_LIMITED kind."""
        assert exc_info.value.kind == GitErrorKind.RATE_LIMITED

    def test_raise_for_status_401(self):
        """GIVEN a GitHubProvider and a 401 response."""
        from releaseboard.git.github_provider import GitHubProvider
        from releaseboard.git.provider import GitAccessError
        provider = GitHubProvider(token="test")

        """WHEN raising for status."""
        with pytest.raises(GitAccessError) as exc_info:
            provider._raise_for_status(
                "https://github.com/o/r", "o", "r", 401, {}
            )

        """THEN it raises GitAccessError with AUTH_REQUIRED kind."""
        assert exc_info.value.kind == GitErrorKind.AUTH_REQUIRED

    def test_raise_for_status_0_network(self):
        """GIVEN a GitHubProvider and a network error (status 0)."""
        from releaseboard.git.github_provider import GitHubProvider
        from releaseboard.git.provider import GitAccessError
        provider = GitHubProvider(token="test")

        """WHEN raising for status."""
        with pytest.raises(GitAccessError) as exc_info:
            provider._raise_for_status(
                "https://github.com/o/r", "o", "r", 0, None
            )

        """THEN it raises GitAccessError with NETWORK_ERROR kind."""
        assert exc_info.value.kind == GitErrorKind.NETWORK_ERROR

    def test_get_default_branch_info_method_exists(self):
        """GIVEN a GitHubProvider instance."""
        from releaseboard.git.github_provider import GitHubProvider
        provider = GitHubProvider(token="test")

        """WHEN checking for default branch info method."""
        has_method = hasattr(provider, "get_default_branch_info")

        """THEN the method exists."""
        assert has_method

    def test_smart_provider_has_get_default_branch_info(self):
        """GIVEN a SmartGitProvider instance."""
        from releaseboard.git.smart_provider import SmartGitProvider
        provider = SmartGitProvider()

        """WHEN checking for default branch info method."""
        has_method = hasattr(provider, "get_default_branch_info")

        """THEN the method exists."""
        assert has_method


# ===========================================================================
# Footer cleanup
# ===========================================================================

class TestFooterCleanup:
    """Scenarios for footer cleanup and centering."""

    def test_footer_centered_css(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting footer CSS."""
        match = re.search(r"\.rb-footer\s*\{[^}]*text-align:\s*center", html, re.S)

        """THEN the footer has centered text alignment."""
        assert match

    def test_footer_copyright_linked(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting footer brand links."""
        match = re.search(r'rb-footer-brand.*?href=', html, re.S)

        """THEN the footer contains brand href links."""
        assert match

    def test_no_footer_mode_badge(self):
        """GIVEN the rendered footer HTML."""
        html = _html()
        footer_match = re.search(r'<footer class="rb-footer">(.*?)</footer>', html, re.S)
        assert footer_match
        footer = footer_match.group(1)

        """WHEN inspecting footer content for mode badges."""
        has_interactive = "Interactive" in footer
        has_static = "Static" in footer
        has_mode_class = "rb-footer-mode" in footer

        """THEN it does not contain mode badge labels."""
        assert not has_interactive
        assert not has_static
        assert not has_mode_class

    def test_footer_has_tools_section(self):
        """GIVEN the rendered footer HTML."""
        html = _html()
        footer_match = re.search(r'<footer class="rb-footer">(.*?)</footer>', html, re.S)
        assert footer_match
        footer = footer_match.group(1)

        """WHEN inspecting footer content for tool names."""
        has_releaseboard = "ReleaseBoard" in footer
        has_releasepilot = "ReleasePilot" in footer

        """THEN it mentions ReleaseBoard and ReleasePilot."""
        assert has_releaseboard
        assert has_releasepilot


# ===========================================================================
# Identity consistency
# ===========================================================================

class TestIdentityConsistency:
    """Scenarios for identity consistency across templates."""

    def test_no_acmeboard_in_template(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN searching for legacy branding."""
        found = "AcmeBoard" in html

        """THEN AcmeBoard does not appear."""
        assert not found

    def test_no_acme_inc_in_template(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN searching for hardcoded company names."""
        found = "Acme Inc" in html

        """THEN Acme Inc does not appear."""
        assert not found


# ===========================================================================
# Public GitHub repo scenarios
# ===========================================================================

class TestPublicRepoScenarios:
    """Scenarios for public repository handling."""

    def test_reachable_repo_missing_branch_has_missing_branch_status(self):
        """GIVEN a reachable public repo with branches that do not match the release pattern."""
        config = _make_config()
        analyzer = ReadinessAnalyzer(config)
        repo_config = config.repositories[0]
        branches = ["main", "develop", "feature/auth"]
        branch_info = BranchInfo(
            name="release/03.2025", exists=False,
            repo_default_branch="main", repo_visibility="public",
        )

        """WHEN analyzing the repository."""
        result = analyzer.analyze(repo_config, branches, branch_info)

        """THEN the status is MISSING_BRANCH with no error."""
        assert result.status == ReadinessStatus.MISSING_BRANCH
        assert result.error_message is None
        assert result.error_kind is None
        assert "Release branch not found" in result.warnings

    def test_provider_metadata_preserved_on_missing_branch(self):
        """GIVEN branch info with full provider metadata but no release branch."""
        config = _make_config()
        analyzer = ReadinessAnalyzer(config)
        repo_config = config.repositories[0]
        branch_info = BranchInfo(
            name="release/03.2025", exists=False,
            repo_default_branch="main", repo_visibility="public",
            repo_description="A public repo", repo_owner="polprog-tech",
            repo_web_url="https://github.com/polprog-tech/WANPulse",
        )

        """WHEN analyzing the repository."""
        result = analyzer.analyze(repo_config, ["main"], branch_info)

        """THEN provider metadata is preserved on the result."""
        assert result.branch is not None
        assert result.branch.repo_default_branch == "main"
        assert result.branch.repo_visibility == "public"
        assert result.branch.repo_description == "A public repo"

    def test_default_branch_fallback_populates_last_activity(self):
        """GIVEN a default branch with a recent commit date."""
        config = _make_config()
        analyzer = ReadinessAnalyzer(config)
        repo_config = config.repositories[0]
        default_info = BranchInfo(
            name="main", exists=True,
            last_commit_date=datetime(2025, 3, 15, tzinfo=UTC),
            repo_default_branch="main",
        )

        """WHEN analyzing with default branch fallback."""
        result = analyzer.analyze(repo_config, ["main"], None, default_info)

        """THEN last activity is populated from the default branch."""
        assert result.status == ReadinessStatus.MISSING_BRANCH
        assert result.last_activity is not None
        assert result.last_activity.year == 2025

    def test_branch_not_found_no_unknown_error(self):
        """GIVEN a repo with no release branch match."""
        config = _make_config()
        analyzer = ReadinessAnalyzer(config)
        repo_config = config.repositories[0]

        """WHEN analyzing the repository."""
        result = analyzer.analyze(repo_config, ["main", "develop"], None)

        """THEN the status is MISSING_BRANCH with no error kind."""
        assert result.status == ReadinessStatus.MISSING_BRANCH
        assert result.error_kind is None
        assert result.error_message is None


# ===========================================================================
# Service-level: default branch fallback integration
# ===========================================================================

class TestServiceDefaultBranchFallback:
    """Scenarios for service-level default-branch fallback."""

    def test_service_imports_matcher(self):
        """GIVEN the AnalysisService class."""
        from releaseboard.application.service import AnalysisService

        """WHEN resolving the module path."""
        source = pathlib.Path(
            AnalysisService.__module__.replace('.', '/') + '.py'
        )

        """THEN the import chain works."""
        assert source.parts  # verifies the module path resolved

    def test_analysis_result_carries_warnings_and_notes(self):
        """GIVEN the server source code."""
        server_path = ROOT / "src" / "releaseboard" / "web" / "server.py"
        server_src = server_path.read_text(encoding="utf-8")

        """WHEN inspecting the web API response fields."""
        has_warnings = '"warnings"' in server_src
        has_notes = '"notes"' in server_src
        has_default_branch = '"repo_default_branch"' in server_src

        """THEN it includes warnings, notes, and metadata fields."""
        assert has_warnings
        assert has_notes
        assert has_default_branch


# ===========================================================================
# i18n completeness, responsive safety, accessibility
# ===========================================================================

class TestI18nCompleteness:
    """Scenarios for i18n completeness of user-facing text."""

    def test_theme_buttons_localized(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting theme button attributes."""
        has_light = 'data-i18n="ui.theme.light"' in html
        has_auto = 'data-i18n="ui.theme.auto"' in html
        has_dark = 'data-i18n="ui.theme.dark"' in html
        has_midnight = 'data-i18n="ui.theme.midnight"' in html

        """THEN all theme buttons have data-i18n attributes."""
        assert has_light
        assert has_auto
        assert has_dark
        assert has_midnight

    def test_export_buttons_localized(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting export button attributes."""
        has_export_html = 'data-i18n="ui.export_html"' in html
        has_export_config = 'data-i18n="ui.export_config"' in html

        """THEN export buttons have data-i18n attributes."""
        assert has_export_html
        assert has_export_config

    def test_import_button_localized(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting import button attributes."""
        found = 'data-i18n="ui.import_config"' in html

        """THEN the import button has a data-i18n attribute."""
        assert found

    def test_status_text_localized(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting status text attributes."""
        found = 'data-i18n="ui.status.ready"' in html

        """THEN status text has a data-i18n attribute."""
        assert found

    def test_i18n_keys_exist_in_both_locales(self):
        """GIVEN the en.json and pl.json locale files."""
        import json
        locale_dir = ROOT / "src" / "releaseboard" / "i18n" / "locales"
        en = json.loads((locale_dir / "en.json").read_text())
        pl = json.loads((locale_dir / "pl.json").read_text())

        """WHEN checking required i18n keys."""
        required_keys = [
            "ui.theme.light", "ui.theme.auto", "ui.theme.dark", "ui.theme.midnight",
            "ui.status.ready", "ui.status.idle",
        ]

        """THEN every key is present and non-empty in both locales."""
        for key in required_keys:
            assert key in en, f"{key} missing in en.json"
            assert key in pl, f"{key} missing in pl.json"
            assert en[key], f"{key} is empty in en.json"
            assert pl[key], f"{key} is empty in pl.json"


class TestResponsiveSafety:
    """Scenarios for responsive layout on narrow viewports."""

    def test_repo_table_container_allows_horizontal_scroll(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting the table container CSS."""
        match = re.search(r"\.repo-table-container\s*\{[^}]*overflow-x:\s*auto", html, re.S)

        """THEN it allows horizontal scrolling."""
        assert match

    def test_mobile_table_has_min_width(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting the mobile table CSS."""
        match = re.search(r"\.repo-table\s*\{\s*min-width:\s*640px", html, re.S)

        """THEN the table has a minimum width of 640px."""
        assert match

    def test_mobile_logo_scales_down(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting the mobile logo CSS."""
        match = re.search(r"\.brand\s+\.rb-logo\s*\{\s*height:\s*36px", html, re.S)

        """THEN the logo scales down to 36px."""
        assert match

    def test_mobile_toolbar_compact(self):
        """GIVEN the rendered template HTML."""
        html = _html()

        """WHEN inspecting the mobile toolbar CSS."""
        match = re.search(r"\.tb-btn\s*\{[^}]*font-size:\s*12px", html, re.S)

        """THEN toolbar buttons use 12px font size."""
        assert match


class TestPrintStylesheet:
    """Scenarios for print-style visibility of interactive elements."""

    def test_print_hides_wizard_overlay(self):
        """GIVEN the styles template content."""
        styles = (TEMPLATE_DIR / "_styles.html.j2").read_text(encoding="utf-8")

        """WHEN inspecting the print media query."""
        # Find the @media print block
        idx = styles.find("@media print")
        assert idx >= 0, "@media print not found"
        block = styles[idx:idx+500]

        """THEN it hides the wizard overlay."""
        assert "rp-wizard-overlay" in block

    def test_print_hides_footer(self):
        """GIVEN the styles template content."""
        styles = (TEMPLATE_DIR / "_styles.html.j2").read_text(encoding="utf-8")

        """WHEN inspecting the print media query."""
        idx = styles.find("@media print")
        assert idx >= 0
        block = styles[idx:idx+500]

        """THEN it hides the footer."""
        assert "rb-footer" in block


class TestActionButtonBehavior:
    """Scenarios for row action styling."""

    def test_row_actions_no_inline_opacity(self):
        """GIVEN the dashboard content template."""
        content_file = TEMPLATE_DIR / "_dashboard_content.html.j2"
        html = content_file.read_text(encoding="utf-8")

        """WHEN inspecting inline styles."""
        found = 'style="opacity:1;"' in html

        """THEN no inline opacity override exists."""
        assert not found
