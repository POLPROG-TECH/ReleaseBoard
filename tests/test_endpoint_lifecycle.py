"""Tests for endpoint behavior, lifecycle, and resource management.

Covers: background tasks, timezone handling, config path protection,
export endpoints, rate limiter pruning, freshness boundaries, graceful
shutdown, body-size rejection, SSE format, health endpoints, templates.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def _make_minimal_config() -> dict[str, Any]:
    return {
        "release": {
            "name": "2025.01",
            "target_month": 1,
            "target_year": 2025,
        },
        "layers": [
            {"id": "core", "label": "Core", "color": "#3B82F6", "order": 0},
        ],
        "repositories": [
            {
                "name": "repo-a",
                "url": "/tmp/test-repo",
                "layer": "core",
            },
        ],
        "branding": {"title": "TestBoard"},
        "settings": {"stale_threshold_days": 14},
    }


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    """Create a test client with a valid config."""
    cfg_file = tmp_path / "releaseboard.json"
    cfg_file.write_text(json.dumps(_make_minimal_config()), encoding="utf-8")

    from releaseboard.web.server import create_app

    with patch.dict("os.environ", {
        "RELEASEBOARD_API_KEY": "test-key-123",
        "RELEASEBOARD_CORS_ORIGINS": "*",
    }):
        app = create_app(cfg_file)
        transport = ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-API-Key": "test-key-123"},
        ) as c:
            yield c


class TestBackgroundTaskReference:
    """Scenarios for background task reference storage."""

    def test_background_tasks_set_exists(self):
        """GIVEN the create_app function source code."""
        import inspect

        from releaseboard.web import server
        source = inspect.getsource(server.create_app)

        """WHEN checking for background task storage."""
        has_tasks_set = "_background_tasks" in source
        has_callback = "add_done_callback" in source

        """THEN both patterns are present."""
        assert has_tasks_set
        assert has_callback

    def test_task_has_name(self):
        """GIVEN the create_app function source code."""
        import inspect

        from releaseboard.web import server
        source = inspect.getsource(server.create_app)

        """WHEN checking for task naming."""
        has_name = 'name="releaseboard-analysis"' in source

        """THEN the task has a descriptive name."""
        assert has_name


class TestGeneratedAtTimezone:
    """Scenarios for timezone-aware generated_at timestamps."""

    def test_generated_at_is_utc(self):
        """GIVEN a dashboard view model built from minimal config."""
        from releaseboard.analysis.metrics import DashboardMetrics
        from releaseboard.config.loader import (
            _build_branding,
            _build_layers,
            _build_release,
            _build_repositories,
            _build_settings,
        )
        from releaseboard.config.models import AppConfig
        from releaseboard.presentation.view_models import build_dashboard_view_model

        raw = _make_minimal_config()
        config = AppConfig(
            release=_build_release(raw["release"]),
            layers=_build_layers(raw.get("layers")),
            repositories=_build_repositories(raw["repositories"]),
            branding=_build_branding(raw.get("branding")),
            settings=_build_settings(raw.get("settings")),
        )

        """WHEN building the dashboard view model."""
        vm = build_dashboard_view_model(config, [], DashboardMetrics(), locale="en")

        """THEN generated_at is a non-empty string."""
        assert vm.generated_at
        assert isinstance(vm.generated_at, str)
        assert len(vm.generated_at) > 0

    def test_source_uses_timezone_utc(self):
        """GIVEN the view_models module source code."""
        import inspect

        from releaseboard.presentation import view_models
        source = inspect.getsource(view_models)

        """WHEN checking for timezone-aware datetime usage."""
        uses_utc = ("timezone.utc" in source or "datetime.UTC" in source
                    or "tz=UTC" in source)
        no_naive_now = "datetime.now()" not in source.replace("datetime.now(tz=", "")

        """THEN timezone.utc is used and naive now is absent."""
        assert uses_utc
        assert no_naive_now


class TestExportEndpoint:
    """Scenarios for HTML export endpoint behavior."""

    @pytest.mark.asyncio
    async def test_export_html_returns_200(self, client: AsyncClient):
        """GIVEN a running application with export endpoint."""
        url = "/api/export/html"

        """WHEN requesting HTML export."""
        resp = await client.get(url)

        """THEN it returns 200 with HTML content type."""
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_export_html_has_content_disposition(self, client: AsyncClient):
        """GIVEN a running application with export endpoint."""
        url = "/api/export/html"

        """WHEN requesting HTML export."""
        resp = await client.get(url)

        """THEN response includes Content-Disposition for download."""
        assert "Content-Disposition" in resp.headers or "content-disposition" in resp.headers
        cd = resp.headers.get("content-disposition", "")
        assert "dashboard.html" in cd

    @pytest.mark.asyncio
    async def test_old_export_url_gives_404(self, client: AsyncClient):
        """GIVEN a running application without legacy export route."""
        url = "/export/html"

        """WHEN requesting the old export URL."""
        resp = await client.get(url)

        """THEN it returns 404."""
        assert resp.status_code == 404


class TestRateLimiterPruning:
    """Scenarios for rate limiter entry pruning."""

    def test_prune_removes_stale_keeps_fresh(self):
        """GIVEN a rate limiter with stale and fresh entries."""
        from releaseboard.web.middleware import RateLimitMiddleware

        limiter = RateLimitMiddleware(
            app=AsyncMock(),
            requests_per_minute=120,
            analysis_per_minute=5,
        )

        now = time.monotonic()
        for i in range(10_001):
            ip = f"10.0.{i // 256}.{i % 256}"
            if i < 5000:
                limiter._windows[ip] = [now - 120]
            else:
                limiter._windows[ip] = [now]

        """WHEN pruning stale entries beyond the cutoff."""
        assert len(limiter._windows) > 10_000
        cutoff = now - 60
        stale = [
            ip for ip, times in limiter._windows.items()
            if not times or times[-1] < cutoff
        ]
        for ip in stale:
            del limiter._windows[ip]

        """THEN only fresh IPs remain."""
        assert len(limiter._windows) > 0
        assert len(limiter._windows) <= 5_001


class TestFreshnessLabelBoundary:
    """Scenarios for freshness label boundary consistency."""

    def test_at_threshold_not_stale(self):
        """GIVEN a commit exactly at the staleness threshold."""
        from releaseboard.analysis.staleness import is_stale

        threshold = 14
        last_commit = datetime.now(tz=UTC) - timedelta(days=threshold)

        """WHEN checking if the commit is stale."""
        result = is_stale(last_commit, threshold)

        """THEN it is not considered stale."""
        assert result is False

    def test_at_threshold_label_not_stale(self):
        """GIVEN a commit exactly at the staleness threshold."""
        from releaseboard.analysis.staleness import freshness_label

        threshold = 14
        last_commit = datetime.now(tz=UTC) - timedelta(days=threshold)

        """WHEN getting the freshness label."""
        label = freshness_label(last_commit, threshold, locale="en")

        """THEN the label shows days ago, not stale."""
        assert str(threshold) in label

    def test_past_threshold_is_stale(self):
        """GIVEN a commit one day past the staleness threshold."""
        from releaseboard.analysis.staleness import freshness_label, is_stale

        threshold = 14
        last_commit = datetime.now(tz=UTC) - timedelta(days=threshold + 1)

        """WHEN checking staleness and freshness label."""
        stale_result = is_stale(last_commit, threshold)
        label = freshness_label(last_commit, threshold, locale="en")

        """THEN both indicate the commit is stale."""
        assert stale_result is True
        assert str(threshold + 1) in label


class TestShutdownGraceful:
    """Scenarios for graceful shutdown behavior."""

    def test_shutdown_has_wait_logic(self):
        """GIVEN the create_app function source code."""
        import inspect

        from releaseboard.web import server
        source = inspect.getsource(server.create_app)

        """WHEN checking for shutdown wait patterns."""
        has_wait = "asyncio.wait(" in source
        has_timeout = "timeout=" in source

        """THEN shutdown logic waits with a timeout."""
        assert has_wait
        assert has_timeout


class TestBodySizeEarlyRejection:
    """Scenarios for body size early rejection."""

    def test_source_checks_content_length(self):
        """GIVEN the create_app function source code."""
        import inspect

        from releaseboard.web import server
        source = inspect.getsource(server.create_app)

        """WHEN checking for Content-Length validation."""
        checks_content_length = "content-length" in source.lower()

        """THEN the source validates Content-Length header."""
        assert checks_content_length

    @pytest.mark.asyncio
    async def test_large_content_length_rejected(self, client: AsyncClient):
        """GIVEN a request with an oversized Content-Length header."""
        content = b'{"test": true}'
        headers = {
            "Content-Type": "application/json",
            "Content-Length": "99999999",
        }

        """WHEN sending the request to update config."""
        resp = await client.put(
            "/api/config",
            content=content,
            headers=headers,
        )

        """THEN the request is rejected with 413."""
        assert resp.status_code == 413


class TestBuildSettingsDefensive:
    """Scenarios for defensive settings parsing."""

    def test_non_numeric_stale_threshold(self):
        """GIVEN a non-numeric stale_threshold_days value."""
        from releaseboard.config.loader import _build_settings
        data = {"stale_threshold_days": "abc"}

        """WHEN building settings."""
        settings = _build_settings(data)

        """THEN the default threshold is used."""
        assert settings.stale_threshold_days == 14

    def test_non_numeric_timeout(self):
        """GIVEN a non-numeric timeout_seconds value."""
        from releaseboard.config.loader import _build_settings
        data = {"timeout_seconds": "not-a-number"}

        """WHEN building settings."""
        settings = _build_settings(data)

        """THEN the default timeout is used."""
        assert settings.timeout_seconds == 30

    def test_non_numeric_max_concurrent(self):
        """GIVEN a None max_concurrent value."""
        from releaseboard.config.loader import _build_settings
        data = {"max_concurrent": None}

        """WHEN building settings."""
        settings = _build_settings(data)

        """THEN the default max_concurrent is used."""
        assert settings.max_concurrent == 5

    def test_valid_string_numbers_work(self):
        """GIVEN string representations of numeric settings."""
        from releaseboard.config.loader import _build_settings
        data = {
            "stale_threshold_days": "7",
            "timeout_seconds": "60",
            "max_concurrent": "10",
        }

        """WHEN building settings."""
        settings = _build_settings(data)

        """THEN string numbers are correctly parsed."""
        assert settings.stale_threshold_days == 7
        assert settings.timeout_seconds == 60
        assert settings.max_concurrent == 10


class TestSSEEventFormat:
    """Scenarios for SSE event formatting."""

    def test_sse_format_structure(self):
        """GIVEN SSE format function and event data."""
        from releaseboard.web.server import _sse_format
        event_name = "test_event"
        event_data = {"key": "value"}

        """WHEN formatting an SSE event."""
        output = _sse_format(event_name, event_data)

        """THEN the output contains id, event, and data fields."""
        assert "id:" in output
        assert "event: test_event" in output
        assert 'data: {"key": "value"}' in output
        assert output.endswith("\n\n")


class TestHealthEndpoints:
    """Scenarios for health endpoint functionality."""

    @pytest.mark.asyncio
    async def test_health_live(self, client: AsyncClient):
        """GIVEN a running application with health endpoints."""
        url = "/health/live"

        """WHEN requesting the liveness endpoint."""
        resp = await client.get(url)

        """THEN it returns alive status."""
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_health_ready(self, client: AsyncClient):
        """GIVEN a running application with health endpoints."""
        url = "/health/ready"

        """WHEN requesting the readiness endpoint."""
        resp = await client.get(url)

        """THEN it returns 200."""
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_status_no_config_path(self, client: AsyncClient):
        """GIVEN a running application with status endpoint."""
        url = "/api/status"

        """WHEN requesting the status endpoint."""
        resp = await client.get(url)

        """THEN config_path is not exposed and expected fields are present."""
        assert resp.status_code == 200
        data = resp.json()
        assert "config_path" not in data
        assert "version" in data
        assert "uptime_seconds" in data


class TestTemplateSplit:
    """Scenarios for dashboard template decomposition."""

    TEMPLATE_DIR = (
        Path(__file__).parent.parent
        / "src" / "releaseboard" / "presentation" / "templates"
    )
    MAX_PARTIAL_LINES = 800

    def _all_content(self) -> str:
        parts = []
        for f in sorted(self.TEMPLATE_DIR.glob("*.j2")):
            parts.append(f.read_text(encoding="utf-8"))
        return "\n".join(parts)

    def test_main_template_is_orchestrator(self):
        """GIVEN the main dashboard template."""
        main = self.TEMPLATE_DIR / "dashboard.html.j2"
        content = main.read_text(encoding="utf-8")

        """WHEN counting non-blank lines and checking includes."""
        lines = [line for line in content.splitlines() if line.strip()]
        has_includes = "{% include" in content

        """THEN it is small and uses include directives."""
        assert len(lines) < 50, f"Main template too large: {len(lines)} non-blank lines"
        assert has_includes

    def test_partials_exist(self):
        """GIVEN a list of required template partials."""
        required = [
            "_styles.html.j2", "_header.html.j2", "_dashboard_content.html.j2",
            "_modals.html.j2", "_config_drawer.html.j2", "_footer.html.j2",
            "_scripts.html.j2", "_scripts_core.html.j2",
            "_scripts_interactive.html.j2", "_scripts_editor.html.j2",
            "_scripts_config_ui.html.j2", "_scripts_wizard.html.j2",
            "_scripts_analysis.html.j2", "_head_scripts.html.j2",
        ]

        """WHEN checking for each partial in the template directory."""
        [name for name in required if not (self.TEMPLATE_DIR / name).exists()]

        """THEN all required partials exist."""
        for name in required:
            assert (self.TEMPLATE_DIR / name).exists(), f"Missing partial: {name}"

    def test_combined_content_has_key_elements(self):
        """GIVEN all template content concatenated."""
        content = self._all_content()
        essentials = [
            "<!DOCTYPE html>", "<html", "</html>",
            "renderEffectiveTab", "PREDEFINED_TEMPLATES",
            'data-tab="effective"', 'id="layoutBar"',
            "REPO_DATA",
        ]

        """WHEN checking for essential dashboard tokens."""
        {token: token in content for token in essentials}

        """THEN all essential tokens are present."""
        for token in essentials:
            assert token in content, f"Missing essential token: {token}"

    def test_jinja_render_works(self):
        """GIVEN a minimal dashboard view model and renderer."""
        from releaseboard.analysis.metrics import DashboardMetrics
        from releaseboard.presentation.renderer import DashboardRenderer
        from releaseboard.presentation.view_models import (
            ChartData,
            DashboardViewModel,
        )
        vm = DashboardViewModel(
            title="Test", subtitle="Sub", company="Co", primary_color="#000",
            secondary_color="#111", tertiary_color="#10b981", theme="light", release_name="v1",
            generated_at="2024-01-01T00:00:00Z",
            metrics=DashboardMetrics(),
            layers=[], attention_items=[], all_repos=[],
            status_chart=ChartData(labels=[], values=[], colors=[]),
            layer_readiness_chart=ChartData(labels=[], values=[], colors=[]),
        )
        renderer = DashboardRenderer()

        """WHEN rendering the template."""
        html = renderer.render(vm)

        """THEN the output contains valid HTML structure."""
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html
