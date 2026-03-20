"""Scenarios for CSP defaults, caching, and audit regression fixes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from releaseboard.web.state import AppState


class TestCSPAllowsChartJS:
    """Scenarios for CSP allowing Chart.js CDN."""

    def _get_csp(self) -> str:
        import inspect

        from releaseboard.web.middleware import SecurityHeadersMiddleware
        source = inspect.getsource(SecurityHeadersMiddleware)
        assert "cdn.jsdelivr.net" in source, "CSP must allow cdn.jsdelivr.net for Chart.js"
        return source


class TestGitLabDefaultBranch:
    """Scenarios for GitLabProvider.get_default_branch_info()."""

    def test_method_exists(self):
        """GIVEN a GitLabProvider instance."""
        from releaseboard.git.gitlab_provider import GitLabProvider
        provider = GitLabProvider(token=None)

        """WHEN checking for get_default_branch_info method."""
        has_method = hasattr(provider, "get_default_branch_info")
        is_callable = callable(provider.get_default_branch_info)

        """THEN the method exists and is callable."""
        assert has_method
        assert is_callable


class TestActiveConfigCaching:
    """Scenarios for get_active_config caching behavior."""

    def _make_state(self, tmp_path: Path) -> AppState:
        from releaseboard.web.state import AppState
        config = {
            "release": {"name": "R1", "target_month": 1, "target_year": 2025},
            "repositories": [],
            "layers": [],
        }
        config_file = tmp_path / "test.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        return AppState(config_file)


class TestAnalyzeSyncEventLoopSafety:
    """Scenarios for analyze_sync event loop safety."""

    def test_detects_running_loop(self):
        """GIVEN the source code of analyze_sync."""
        from releaseboard.application.service import AnalysisService
        mock_provider = MagicMock()
        service = AnalysisService(mock_provider)
        import inspect
        source = inspect.getsource(service.analyze_sync)

        """WHEN checking for running loop detection."""
        has_get_running_loop = "get_running_loop" in source
        has_thread_pool = "ThreadPoolExecutor" in source

        """THEN both get_running_loop and ThreadPoolExecutor are present."""
        assert has_get_running_loop, "Must check for running event loop"
        assert has_thread_pool, "Must use thread pool as fallback"

    def test_has_concurrent_futures_fallback(self):
        """GIVEN the source code of AnalysisService.analyze_sync."""
        import inspect

        from releaseboard.application.service import AnalysisService
        source = inspect.getsource(AnalysisService.analyze_sync)

        """WHEN checking for concurrent.futures fallback."""
        has_concurrent = "concurrent.futures" in source
        has_pool_submit = "pool.submit" in source

        """THEN concurrent.futures and pool.submit are present."""
        assert has_concurrent
        assert has_pool_submit


class TestTemplatePartialsIntegrity:
    """Scenarios for template partials integrity."""

    def test_main_template_uses_includes(self):
        """GIVEN the main dashboard template."""
        main = (
            Path(__file__).parent.parent
            / "src" / "releaseboard" / "presentation"
            / "templates" / "dashboard.html.j2"
        )
        content = main.read_text(encoding="utf-8")

        """WHEN checking template structure."""
        has_includes = "{% include" in content
        lines = content.strip().splitlines()

        """THEN it uses includes and is a small orchestrator."""
        assert has_includes
        assert len(lines) < 50, (
            f"Main template should be a small orchestrator,"
            f" got {len(lines)} lines"
        )
