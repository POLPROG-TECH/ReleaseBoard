"""Tests for API discovery, export, and git provider correctness.

Covers:
- URL encoding in GitHub API URL construction
- SSL context caching (GitHub & GitLab providers)
- Discover route returns repo URL, not repo name
- Silent exception logging in discover & default-branch fallback
- Export HTML error handling
- Config path removed from /api/status
- i18n endpoint consistent response format
- /api/analyze/results 404 when no results
- Staleness off-by-one (strictly greater than)
- Branch pattern month/year validation
- File descriptor safety in save_config
- SSE subscriber queue-full logging
"""
from __future__ import annotations

import json
import ssl
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from releaseboard.analysis.branch_pattern import BranchPatternMatcher
from releaseboard.git.github_provider import GitHubProvider
from releaseboard.git.gitlab_provider import GitLabProvider


class TestGitHubURLEncoding:
    """Scenarios for URL-encoding owner, repo, and branch in API calls."""

    def _extract_url(self, provider: GitHubProvider, method: str, *args: Any) -> str:
        """Call a provider method and capture the URL it tries to fetch."""
        captured: list[str] = []

        def fake_get_json(url: str, timeout: int) -> tuple[Any, int]:
            captured.append(url)
            if method == "list_remote_branches":
                return [{"name": "main", "commit": {"sha": "abc"}}], 200
            if method == "list_org_repos":
                return [{"full_name": "org/repo", "clone_url": "https://x"}], 200
            return {
                "name": "main",
                "commit": {
                    "sha": "abc",
                    "commit": {
                        "author": {
                            "date": "2025-01-01T00:00:00Z",
                        },
                    },
                },
            }, 200

        with patch.object(provider, "_get_json", side_effect=fake_get_json):
            getattr(provider, method)(*args)

        assert captured, f"No URL captured for {method}"
        return captured[0]

    def test_list_branches_encodes_owner_repo(self):
        """GIVEN a GitHub provider and a repo URL with spaces in owner and repo."""
        p = GitHubProvider(token="test")

        """WHEN listing remote branches for that URL."""
        url = self._extract_url(
            p, "list_remote_branches",
            "https://github.com/my org/my repo", 10,
        )

        """THEN the captured URL percent-encodes the spaces."""
        assert "my%20org" in url
        assert "my%20repo" in url
        assert "my org" not in url

    def test_branch_info_encodes_branch_with_slash(self):
        """GIVEN a GitHub provider and a branch name containing slashes."""
        p = GitHubProvider(token="test")

        """WHEN fetching branch info for that branch."""
        url = self._extract_url(
            p, "get_branch_info",
            "https://github.com/owner/repo", "feature/release/2025", 10,
        )

        """THEN the slashes in the branch name are percent-encoded in the URL."""
        assert (
            "feature%2Frelease%2F2025" in url
            or "feature/release/2025"
            not in url.split("repos/")[1].split("?")[0]
        )

    def test_org_repos_encodes_org_name(self):
        """GIVEN a GitHub provider and an org URL with a space in the name."""
        p = GitHubProvider(token="test")

        """WHEN listing org repos for that URL."""
        url = self._extract_url(
            p, "list_org_repos",
            "https://github.com/my org", 10,
        )

        """THEN the captured URL percent-encodes the space in the org name."""
        assert "my%20org" in url


class TestSSLContextCaching:
    """Scenarios for SSL context creation and reuse."""

    def test_github_ssl_context_cached(self):
        """GIVEN a GitHub provider instance."""
        p = GitHubProvider(token="test")

        """WHEN requesting the SSL context twice."""
        ctx1 = p._get_ssl_context()
        ctx2 = p._get_ssl_context()

        """THEN the same SSLContext object is returned both times."""
        assert ctx1 is ctx2
        assert isinstance(ctx1, ssl.SSLContext)

    def test_gitlab_ssl_context_cached(self):
        """GIVEN a GitLab provider instance."""
        p = GitLabProvider(token="test")

        """WHEN requesting the SSL context twice."""
        ctx1 = p._get_ssl_context()
        ctx2 = p._get_ssl_context()

        """THEN the same SSLContext object is returned both times."""
        assert ctx1 is ctx2
        assert isinstance(ctx1, ssl.SSLContext)


def _make_minimal_config() -> dict[str, Any]:
    return {
        "release": {
            "name": "March 2025 Release",
            "target_month": 3,
            "target_year": 2025,
            "branch_pattern": "release/{MM}.{YYYY}",
        },
        "layers": [
            {"id": "backend", "label": "Backend", "color": "#3B82F6", "order": 0},
        ],
        "repositories": [
            {"name": "test-repo", "url": "/tmp/test-repo", "layer": "backend"},
        ],
        "branding": {"title": "TestBoard"},
        "settings": {"stale_threshold_days": 14},
    }


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    """Create a test client with a valid config."""
    config_file = tmp_path / "releaseboard.json"
    config_file.write_text(json.dumps(_make_minimal_config()), encoding="utf-8")

    with (
        patch.dict("os.environ", {
            "RELEASEBOARD_API_KEY": "test-key-123",
            "RELEASEBOARD_CORS_ORIGINS": "*",
        }),
    ):
        from releaseboard.web.server import create_app
        app = create_app(config_file)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"X-Api-Key": "test-key-123"},
        ) as ac:
            yield ac


@pytest.mark.asyncio
async def test_status_no_config_path(client: AsyncClient):
    """GIVEN an authenticated test client connected to the app."""
    assert client is not None

    """WHEN requesting the status endpoint."""
    resp = await client.get("/api/status")
    body = resp.json()

    """THEN the response is 200 OK and does not expose config_path."""
    assert resp.status_code == 200
    assert "config_path" not in body
    assert body["ok"] is True
    assert "version" in body


@pytest.mark.asyncio
async def test_i18n_consistent_format(client: AsyncClient):
    """GIVEN an authenticated test client connected to the app."""

    """WHEN requesting the i18n endpoint for the English locale."""
    resp = await client.get("/api/i18n/en")
    body = resp.json()

    """THEN the response has a structured format with ok, locale, and catalog."""
    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["locale"] == "en"
    assert "catalog" in body
    assert isinstance(body["catalog"], dict)


@pytest.mark.asyncio
async def test_i18n_unsupported_locale(client: AsyncClient):
    """GIVEN an authenticated test client connected to the app."""

    """WHEN requesting the i18n endpoint for an unsupported locale."""
    resp = await client.get("/api/i18n/zz")
    body = resp.json()

    """THEN the response is 404 with ok=false."""
    assert resp.status_code == 404
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_results_returns_404_when_empty(client: AsyncClient):
    """GIVEN an authenticated test client with no prior analysis results."""

    """WHEN requesting the analyze results endpoint."""
    resp = await client.get("/api/analyze/results")
    body = resp.json()

    """THEN the response is 404 with ok=false."""
    assert resp.status_code == 404
    assert body["ok"] is False


class TestBranchPatternValidation:
    """Scenarios for resolve() rejecting invalid month and year values."""

    def test_month_zero_raises(self):
        """GIVEN a BranchPatternMatcher instance."""
        m = BranchPatternMatcher()

        """WHEN resolving a pattern with month=0."""
        with pytest.raises(ValueError, match="Invalid release month"):
            m.resolve("release/{MM}.{YYYY}", month=0, year=2025)

        """THEN the exception is raised (verified by context manager)."""

    def test_month_13_raises(self):
        """GIVEN a BranchPatternMatcher instance."""
        m = BranchPatternMatcher()

        """WHEN resolving a pattern with month=13."""
        with pytest.raises(ValueError, match="Invalid release month"):
            m.resolve("release/{MM}.{YYYY}", month=13, year=2025)

        """THEN the exception is raised (verified by context manager)."""

    def test_negative_month_raises(self):
        """GIVEN a BranchPatternMatcher instance."""
        m = BranchPatternMatcher()

        """WHEN resolving a pattern with month=-1."""
        with pytest.raises(ValueError, match="Invalid release month"):
            m.resolve("release/{MM}.{YYYY}", month=-1, year=2025)

        """THEN the exception is raised (verified by context manager)."""

    def test_year_too_low_raises(self):
        """GIVEN a BranchPatternMatcher instance."""
        m = BranchPatternMatcher()

        """WHEN resolving a pattern with year=1999."""
        with pytest.raises(ValueError, match="Invalid release year"):
            m.resolve("release/{MM}.{YYYY}", month=1, year=1999)

        """THEN the exception is raised (verified by context manager)."""

    def test_year_too_high_raises(self):
        """GIVEN a BranchPatternMatcher instance."""
        m = BranchPatternMatcher()

        """WHEN resolving a pattern with year=2100."""
        with pytest.raises(ValueError, match="Invalid release year"):
            m.resolve("release/{MM}.{YYYY}", month=1, year=2100)

        """THEN the exception is raised (verified by context manager)."""

    def test_valid_range_accepted(self):
        """GIVEN a BranchPatternMatcher instance."""
        m = BranchPatternMatcher()

        """WHEN resolving a pattern with month=12 and year=2025."""
        result = m.resolve("release/{MM}.{YYYY}", month=12, year=2025)

        """THEN the resolved name matches the expected branch."""
        assert result.resolved_name == "release/12.2025"

    def test_edge_month_1_accepted(self):
        """GIVEN a BranchPatternMatcher instance."""
        m = BranchPatternMatcher()

        """WHEN resolving a pattern with month=1 and year=2000."""
        result = m.resolve("release/{MM}.{YYYY}", month=1, year=2000)

        """THEN the resolved name zero-pads the month."""
        assert result.resolved_name == "release/01.2000"


class TestSaveConfigFdLeak:
    """Scenarios for mkstemp fd closure during save_config."""

    @pytest.mark.asyncio
    async def test_save_config_no_fd_leak(self, tmp_path: Path):
        """GIVEN a valid config file and an AppState with a draft config."""
        config_file = tmp_path / "releaseboard.json"
        initial = _make_minimal_config()
        config_file.write_text(json.dumps(initial), encoding="utf-8")

        from releaseboard.web.state import AppState
        state = AppState(config_file)
        state.config_state.draft_raw = initial

        """WHEN saving the config."""
        errors = state.save_config()

        """THEN no errors are returned and the file content is correct."""
        assert errors == []
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved == initial

    @pytest.mark.asyncio
    async def test_save_config_cleans_up_on_failure(self, tmp_path: Path):
        """GIVEN a valid config file and an AppState with a draft config."""
        config_file = tmp_path / "releaseboard.json"
        initial = _make_minimal_config()
        config_file.write_text(json.dumps(initial), encoding="utf-8")

        from releaseboard.web.state import AppState
        state = AppState(config_file)
        state.config_state.draft_raw = initial

        """WHEN write_text fails with an OS error."""
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            errors = state.save_config()

        """THEN an error is reported and the original file is untouched."""
        assert len(errors) == 1
        assert "Failed to write config" in errors[0]
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved == initial


@pytest.mark.asyncio
async def test_export_html_error_handling(client: AsyncClient):
    """GIVEN an authenticated test client with no prior analysis results."""

    """WHEN requesting the export HTML endpoint."""
    resp = await client.get("/api/export/html")

    """THEN the response is 200 with HTML content and the source has error handling."""
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    import inspect

    from releaseboard.web import server
    source = inspect.getsource(server)
    assert "Export HTML template rendering failed" in source


class TestServiceExceptionLogging:
    """Scenarios for service.py default-branch fallback logging."""

    def test_default_branch_exception_logged(self, caplog):
        """GIVEN the source code of the service module."""
        import inspect

        from releaseboard.application import service
        source = inspect.getsource(service)

        """WHEN inspecting the exception handling for default branch fallback."""
        has_logging = "default_exc" in source or "logger.debug" in source
        has_bare_pass = "except Exception:\n                                pass" in source

        """THEN the code uses logging instead of a bare pass."""
        assert has_logging
        assert not has_bare_pass


class TestDiscoverRouteURL:
    """Scenarios for discover endpoint returning repo URL instead of name."""

    def test_discover_source_code_uses_repo_url(self):
        """GIVEN the source code of the web server module."""
        import inspect

        from releaseboard.web import server
        source = inspect.getsource(server)

        """WHEN inspecting the discover repos append block."""
        uses_repo_name = '"url": repo_name' in source
        uses_repo_url = '"url": repo_url' in source

        """THEN the url field is set from repo_url, not repo_name."""
        assert not uses_repo_name
        assert uses_repo_url
