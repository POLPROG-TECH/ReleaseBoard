"""Tests for error classification — git errors, placeholder detection, layout schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# --- URL placeholder detection ---
from releaseboard.git.provider import (
    GitAccessError,
    GitErrorKind,
    classify_git_error,
    is_placeholder_url,
)


class TestPlaceholderUrlDetection:
    """Scenarios for placeholder URL detection."""

    def test_example_com(self):
        """GIVEN an example.com URL."""
        url = "https://git.example.com/org/repo"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is detected as a placeholder."""
        assert result is True

    def test_example_org(self):
        """GIVEN an example.org URL."""
        url = "https://example.org/team/app"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is detected as a placeholder."""
        assert result is True

    def test_placeholder_domain(self):
        """GIVEN a placeholder.com domain URL."""
        url = "https://git.placeholder.com/x/y"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is detected as a placeholder."""
        assert result is True

    def test_github_is_not_placeholder(self):
        """GIVEN a github.com URL."""
        url = "https://github.com/acme/app"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is not a placeholder."""
        assert result is False

    def test_gitlab_is_not_placeholder(self):
        """GIVEN a gitlab.com URL."""
        url = "https://gitlab.com/team/repo"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is not a placeholder."""
        assert result is False

    def test_custom_domain(self):
        """GIVEN a custom company domain URL."""
        url = "https://git.mycompany.com/team/repo"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is not a placeholder."""
        assert result is False

    def test_empty_url(self):
        """GIVEN an empty URL string."""
        url = ""

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is detected as a placeholder."""
        assert result is True

    def test_ssh_example(self):
        """GIVEN an SSH example.com URL."""
        url = "git@git.example.com:org/repo.git"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is detected as a placeholder."""
        assert result is True

    def test_ssh_github(self):
        """GIVEN an SSH github.com URL."""
        url = "git@github.com:org/repo.git"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is not a placeholder."""
        assert result is False

    def test_local_path(self):
        """GIVEN a local file path."""
        url = "/home/user/repos/myapp"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is not a placeholder."""
        assert result is False

    def test_subdomain_of_example(self):
        """GIVEN a subdomain of example.com."""
        url = "https://gitops.test.example.com/a/b"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is detected as a placeholder."""
        assert result is True


class TestGitErrorClassification:
    """Scenarios for git error classification."""

    def test_dns_resolution(self):
        """GIVEN a DNS resolution failure message."""
        msg = "Could not resolve host: git.acme.com"

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is DNS_RESOLUTION."""
        assert result == GitErrorKind.DNS_RESOLUTION

    def test_timeout(self):
        """GIVEN a connection timed out message."""
        msg = "connection timed out"

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is TIMEOUT."""
        assert result == GitErrorKind.TIMEOUT

    def test_timeout_after(self):
        """GIVEN a timeout-after message."""
        msg = "Timeout after 30s"

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is TIMEOUT."""
        assert result == GitErrorKind.TIMEOUT

    def test_auth_required(self):
        """GIVEN an authentication prompt disabled message."""
        msg = "could not read Username for 'https://github.com': terminal prompts disabled"

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is AUTH_REQUIRED."""
        assert result == GitErrorKind.AUTH_REQUIRED

    def test_repo_not_found(self):
        """GIVEN a repository not found message."""
        msg = "Repository not found."

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is REPO_NOT_FOUND."""
        assert result == GitErrorKind.REPO_NOT_FOUND

    def test_access_denied(self):
        """GIVEN a permission denied message."""
        msg = "Permission denied (publickey)."

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is ACCESS_DENIED."""
        assert result == GitErrorKind.ACCESS_DENIED

    def test_network_error(self):
        """GIVEN an SSL certificate error message."""
        msg = "unable to access 'https://git.acme.com/repo/': SSL certificate problem"

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is NETWORK_ERROR."""
        assert result == GitErrorKind.NETWORK_ERROR

    def test_git_cli_missing(self):
        """GIVEN a git-not-found message."""
        msg = "git not found in PATH"

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is GIT_CLI_MISSING."""
        assert result == GitErrorKind.GIT_CLI_MISSING

    def test_local_path_missing(self):
        """GIVEN a no-such-file message."""
        msg = "no such file or directory"

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is LOCAL_PATH_MISSING."""
        assert result == GitErrorKind.LOCAL_PATH_MISSING

    def test_placeholder_url_classified(self):
        """GIVEN an error with a placeholder URL."""
        msg = "some error"
        url = "https://git.example.com/x/y"

        """WHEN classifying the error."""
        result = classify_git_error(msg, url)

        """THEN kind is PLACEHOLDER_URL."""
        assert result == GitErrorKind.PLACEHOLDER_URL

    def test_unknown_fallback(self):
        """GIVEN an unrecognized error message."""
        msg = "something completely unexpected happened"

        """WHEN classifying the error."""
        result = classify_git_error(msg)

        """THEN kind is UNKNOWN."""
        assert result == GitErrorKind.UNKNOWN


class TestGitAccessErrorFields:
    """Scenarios for GitAccessError structured fields."""

    def test_auto_classification(self):
        """GIVEN a repo-not-found error message."""
        url = "https://github.com/x/y"
        msg = "Repository not found."

        """WHEN creating a GitAccessError."""
        err = GitAccessError(url, msg)

        """THEN kind, user_message, and detail are auto-classified."""
        assert err.kind == GitErrorKind.REPO_NOT_FOUND
        assert err.user_message == "Repository not found"
        assert err.detail == "Repository not found."

    def test_explicit_kind(self):
        """GIVEN an explicit TIMEOUT error kind."""
        kind = GitErrorKind.TIMEOUT

        """WHEN creating a GitAccessError with an explicit kind."""
        err = GitAccessError("url", "msg", kind=kind)

        """THEN the explicit kind is used."""
        assert err.kind == GitErrorKind.TIMEOUT

    def test_placeholder_url_error(self):
        """GIVEN a placeholder example.com URL."""
        url = "https://git.example.com/org/repo"
        msg = "fatal: unable to access"

        """WHEN creating a GitAccessError."""
        err = GitAccessError(url, msg)

        """THEN kind is PLACEHOLDER_URL with appropriate user_message."""
        assert err.kind == GitErrorKind.PLACEHOLDER_URL
        assert err.user_message == "Placeholder/example URL"

    def test_error_kind_values(self):
        """GIVEN all GitErrorKind variants."""
        all_kinds = list(GitErrorKind)

        """WHEN checking each variant's user_message."""
        messages = {kind: kind.user_message for kind in all_kinds}

        """THEN each has a non-empty value."""
        for kind, msg in messages.items():
            assert msg, f"Missing user_message for {kind.value}"


class TestRepositoryAnalysisErrorFields:
    """Scenarios for RepositoryAnalysis error fields."""

    def test_error_fields_default_none(self):
        """GIVEN error status without explicit error fields."""
        from releaseboard.domain.enums import ReadinessStatus
        from releaseboard.domain.models import RepositoryAnalysis

        """WHEN creating a RepositoryAnalysis."""
        a = RepositoryAnalysis(
            name="test", url="url", layer="fe",
            default_branch="main", expected_pattern="release/{YYYY}.{MM}",
            expected_branch_name="release/2025.03",
            status=ReadinessStatus.ERROR,
            error_message="fail",
        )

        """THEN error_kind and error_detail default to None."""
        assert a.error_kind is None
        assert a.error_detail is None

    def test_error_fields_set(self):
        """GIVEN explicit error_kind and error_detail values."""
        from releaseboard.domain.enums import ReadinessStatus
        from releaseboard.domain.models import RepositoryAnalysis

        """WHEN creating a RepositoryAnalysis with error fields."""
        a = RepositoryAnalysis(
            name="test", url="url", layer="fe",
            default_branch="main", expected_pattern="release/{YYYY}.{MM}",
            expected_branch_name="release/2025.03",
            status=ReadinessStatus.ERROR,
            error_message="Host not found",
            error_kind="dns_resolution",
            error_detail="fatal: Could not resolve host: git.acme.com",
        )

        """THEN error_kind and error_detail are set."""
        assert a.error_kind == "dns_resolution"
        assert a.error_detail == "fatal: Could not resolve host: git.acme.com"

    def test_error_fields_mutable(self):
        """GIVEN a RepositoryAnalysis instance."""
        from releaseboard.domain.enums import ReadinessStatus
        from releaseboard.domain.models import RepositoryAnalysis

        a = RepositoryAnalysis(
            name="test", url="url", layer="fe",
            default_branch="main", expected_pattern="p",
            expected_branch_name="b",
            status=ReadinessStatus.ERROR,
        )

        """WHEN setting error_kind after creation."""
        a.error_kind = "timeout"
        a.error_detail = "detail"

        """THEN the field is updated."""
        assert a.error_kind == "timeout"


class TestRepoViewModelErrorFields:
    """Scenarios for RepoViewModel error fields."""

    def test_view_model_has_error_fields(self):
        """GIVEN a RepoViewModel with error fields."""
        from releaseboard.presentation.view_models import RepoViewModel

        """WHEN creating a RepoViewModel with error_kind and error_detail."""
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

        """THEN error_kind and error_detail are accessible."""
        assert vm.error_kind == "dns_resolution"
        assert vm.error_detail == "could not resolve host"


class TestSchemaLayoutSection:
    """Scenarios for schema layout section."""

    def test_schema_has_layout(self):
        """GIVEN the config schema file."""
        schema_path = (
            Path(__file__).parent.parent
            / "src" / "releaseboard" / "config" / "schema.json"
        )
        schema = json.loads(schema_path.read_text())

        """WHEN inspecting schema properties."""
        props = schema["properties"]

        """THEN layout section with expected fields exists."""
        assert "layout" in props
        layout = props["layout"]
        assert "default_template" in layout["properties"]
        assert "section_order" in layout["properties"]
        assert "enable_drag_drop" in layout["properties"]


class TestSchemaStillValid:
    """Scenarios for schema validation with existing configs."""

    def test_example_config_valid(self):
        """GIVEN the example config file."""
        from releaseboard.config.schema import validate_config

        config_path = Path(__file__).parent.parent / "examples" / "config.json"
        config = json.loads(config_path.read_text())

        """WHEN validating against the schema."""
        errors = validate_config(config)

        """THEN no validation errors are returned."""
        assert errors == [], f"Example config has validation errors: {errors}"

    def test_config_with_layout(self):
        """GIVEN a config with an added layout section."""
        from releaseboard.config.schema import validate_config

        config_path = Path(__file__).parent.parent / "examples" / "config.json"
        config = json.loads(config_path.read_text())
        config["layout"] = {
            "default_template": "executive",
            "section_order": ["score", "metrics", "layer-*", "summary"],
            "enable_drag_drop": True,
        }

        """WHEN validating against the schema."""
        errors = validate_config(config)

        """THEN no validation errors are returned."""
        assert errors == []


class TestPlaceholderSkipping:
    """Scenarios for placeholder URL skipping."""

    def test_placeholder_url_skipped_in_progress(self):
        """GIVEN a deep nested placeholder URL."""
        url = "https://git.example.com/platform/frontend/admin-panel"

        """WHEN checking if it is a placeholder."""
        result = is_placeholder_url(url)

        """THEN it is detected as a placeholder."""
        assert result is True


class TestCheckUrlsEndpoint:
    """Scenarios for URL health-check endpoint."""

    @pytest.mark.asyncio
    async def test_check_urls_endpoint(self):
        """GIVEN a config with various URL types."""
        import tempfile
        from pathlib import Path

        from httpx import ASGITransport, AsyncClient

        from releaseboard.web.server import create_app

        config_path = Path(__file__).parent.parent / "examples" / "config.json"
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write(config_path.read_text())
            temp = Path(f.name)

        try:
            app = create_app(temp)
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:

                """WHEN posting to the check-urls endpoint."""
                resp = await client.post("/api/config/check-urls", json={
                    "repositories": [
                        {"name": "real", "url": "https://github.com/acme/app"},
                        {"name": "placeholder", "url": "https://git.example.com/x/y"},
                        {"name": "empty", "url": ""},
                        {"name": "relative", "url": "my-app"},
                    ]
                })

                """THEN each URL gets the correct status."""
                assert resp.status_code == 200
                data = resp.json()
                assert data["ok"] is True
                results = {r["name"]: r["status"] for r in data["results"]}
                assert results["real"] == "ok"
                assert results["placeholder"] == "placeholder"
                assert results["empty"] == "empty"
                assert results["relative"] == "relative"
        finally:
            temp.unlink()


def _all_template_content() -> str:
    """Read all template partials concatenated for string checks."""
    tmpl_dir = Path(__file__).parent.parent / "src" / "releaseboard" / "presentation" / "templates"
    parts = []
    for f in sorted(tmpl_dir.glob("*.j2")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


class TestSectionIdentity:
    """Scenarios for dashboard section identity."""

    def test_template_has_section_ids(self):
        """GIVEN the template partials."""
        content = _all_template_content()

        """WHEN checking for section ID attributes."""
        expected_ids = ["metrics", "filters", "summary"]

        """THEN expected data-section-id attributes exist."""
        for sid in expected_ids:
            assert f'data-section-id="{sid}"' in content, f"Missing section ID: {sid}"
        assert 'data-section-id="layer-{{ layer.id }}"' in content

    def test_template_has_dashboard_sections(self):
        """GIVEN the template partials."""
        content = _all_template_content()

        """WHEN checking for dashboard section class."""
        has_section_class = 'class="dashboard-section"' in content or 'dashboard-section' in content

        """THEN dashboard-section class exists."""
        assert has_section_class

    def test_template_has_layout_bar(self):
        """GIVEN the template partials."""
        content = _all_template_content()

        """WHEN checking for layout bar elements."""
        has_layout_bar = 'id="layoutBar"' in content
        has_template_list = 'id="layoutTemplateList"' in content

        """THEN layoutBar and layoutTemplateList exist."""
        assert has_layout_bar
        assert has_template_list

    def test_predefined_templates_in_js(self):
        """GIVEN the template partials."""
        content = _all_template_content()

        """WHEN checking for predefined template names."""
        expected_names = ["executive", "release-manager", "engineering", "compact"]
        has_predefined = "PREDEFINED_TEMPLATES" in content

        """THEN all template names are present."""
        assert has_predefined
        for name in expected_names:
            assert f"'{name}'" in content, f"Missing predefined template: {name}"
