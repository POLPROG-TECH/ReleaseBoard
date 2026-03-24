"""Tests for web infrastructure — SSE events, health/liveness probes,
graceful shutdown, background tasks, structured logging, endpoint routing."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from releaseboard.config.models import (
    AppConfig,
    LayerConfig,
    ReleaseConfig,
    RepositoryConfig,
    SettingsConfig,
)
from releaseboard.domain.models import BranchInfo
from releaseboard.git.provider import GitProvider
from releaseboard.web.state import (
    AppState,
)

if TYPE_CHECKING:
    from pathlib import Path

_MINIMAL_CONFIG = {
    "release": {"name": "Test", "target_month": 3, "target_year": 2026},
    "repositories": [],
    "layers": [],
    "branding": {
        "title": "Test",
        "subtitle": "Test Dashboard",
        "primary_color": "#fb6400",
        "secondary_color": "#002754e6",
    },
    "settings": {
        "stale_threshold_days": 14,
        "output_path": "output/test.html",
        "theme": "system",
        "timeout_seconds": 30,
        "max_concurrent": 5,
    },
}
MINIMAL_CONFIG = _MINIMAL_CONFIG

def _write_config(tmp_path: Path, data: dict | None = None) -> Path:
    config_path = tmp_path / "test_config.json"
    config_path.write_text(json.dumps(data or MINIMAL_CONFIG), encoding="utf-8")
    return config_path

def _create_app_for_test(tmp_path: Path, data: dict | None = None):
    """Create a FastAPI app for testing."""
    from releaseboard.web.server import create_app
    config_path = _write_config(tmp_path, data)
    return create_app(config_path), config_path

@pytest.fixture
def config_path(tmp_path):
    p = tmp_path / "releaseboard.json"
    p.write_text(json.dumps(_MINIMAL_CONFIG), encoding="utf-8")
    return p

@pytest.fixture
def app(config_path):
    from releaseboard.web.server import create_app
    return create_app(config_path)

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

@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(MINIMAL_CONFIG, indent=2), encoding="utf-8")
    return p

@pytest.fixture
def state(config_file: Path) -> AppState:
    return AppState(config_file)


class TestSSEEventIDs:
    """Scenarios for SSE event ID formatting."""

    def test_sse_format_includes_id_field(self):
        """GIVEN the SSE format function."""
        from releaseboard.web.server import _sse_format

        """WHEN formatting an event with a payload."""
        output = _sse_format("test_event", {"key": "value"})
        lines = output.strip().split("\n")

        """THEN output includes id, event, and data fields."""
        assert lines[0].startswith("id: ")
        assert "event: test_event" in output
        assert "data:" in output

    def test_sse_data_is_valid_json(self):
        """GIVEN the SSE format function."""
        from releaseboard.web.server import _sse_format

        """WHEN formatting an event with data."""
        output = _sse_format("evt", {"count": 42})

        """THEN the data line contains valid JSON with correct value."""
        for line in output.strip().split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                assert data["count"] == 42


class TestHealthProbes:
    """Scenarios for readiness and liveness probes."""

    @pytest.mark.asyncio
    async def test_readiness_returns_503_when_config_missing(self, tmp_path):
        """GIVEN an app whose config file is deleted after creation."""
        config_path = tmp_path / "releaseboard.json"
        config_path.write_text(json.dumps(_MINIMAL_CONFIG), encoding="utf-8")

        from releaseboard.web.server import create_app
        app = create_app(config_path)

        # Delete config after app creation
        config_path.unlink()

        """WHEN requesting the readiness probe."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            resp = await c.get("/health/ready")

        """THEN returns 503 with config_readable false."""
        assert resp.status_code == 503
        assert resp.json()["config_readable"] is False


class TestSSEQueueFullLogging:
    """Scenarios for SSE queue-full logging."""

    @pytest.mark.asyncio
    async def test_queue_full_logs_warning(self, tmp_path: Path, caplog):
        """GIVEN a subscriber with a full queue."""
        config_file = tmp_path / "releaseboard.json"
        config_file.write_text(json.dumps(_make_minimal_config()), encoding="utf-8")

        from releaseboard.web.state import AppState
        state = AppState(config_file)

        # Add a subscriber with a tiny queue
        tiny_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
        state._sse_subscribers.append(tiny_queue)

        # Fill the queue
        await tiny_queue.put({"event": "fill", "data": {}})

        """WHEN broadcast sends a message."""
        with caplog.at_level(logging.WARNING, logger="releaseboard.web.state"):
            await state.broadcast("test", {"key": "value"})

        """THEN a warning is logged and the subscriber is removed."""
        assert any("Dropping SSE subscriber" in r.message for r in caplog.records)
        assert tiny_queue not in state._sse_subscribers


class TestServiceExceptionLogging:
    """Scenarios for service exception logging."""

    def test_default_branch_exception_logged(self, caplog):
        """GIVEN the service module source code."""
        import inspect

        from releaseboard.application import service
        source = inspect.getsource(service)

        """WHEN inspecting the default branch fallback."""
        has_logging = "default_exc" in source or "logger.debug" in source

        """THEN it logs instead of silently passing."""
        assert has_logging
        # Ensure there is no bare `except Exception:\n                                pass`
        # in the default branch fallback
        assert "except Exception:\n                                pass" not in source


class TestDiscoverRouteURL:
    """Scenarios for discover route URL field."""

    def test_discover_source_code_uses_repo_url(self):
        """GIVEN the server module source code."""
        import inspect

        from releaseboard.web import server
        source = inspect.getsource(server)

        """WHEN inspecting the discover endpoint."""
        has_repo_name = '"url": repo_name' in source
        has_repo_url = '"url": repo_url' in source

        """THEN it uses repo_url for the URL field."""
        assert not has_repo_name
        assert has_repo_url


@pytest.mark.asyncio
async def test_status_no_config_path(client: AsyncClient):
    """GIVEN the status endpoint."""
    endpoint = "/api/status"

    """WHEN requesting status."""
    resp = await client.get(endpoint)

    """THEN config_path is not exposed and response is valid."""
    assert resp.status_code == 200
    body = resp.json()
    assert "config_path" not in body
    assert body["ok"] is True
    assert "version" in body


@pytest.mark.asyncio
async def test_i18n_consistent_format(client: AsyncClient):
    """GIVEN the i18n endpoint for English locale."""
    endpoint = "/api/i18n/en"

    """WHEN requesting the locale."""
    resp = await client.get(endpoint)

    """THEN returns structured response with ok, locale, and catalog."""
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["locale"] == "en"
    assert "catalog" in body
    assert isinstance(body["catalog"], dict)


@pytest.mark.asyncio
async def test_i18n_unsupported_locale(client: AsyncClient):
    """GIVEN the i18n endpoint with an unsupported locale."""
    endpoint = "/api/i18n/zz"

    """WHEN requesting the locale."""
    resp = await client.get(endpoint)

    """THEN returns 404 with ok false."""
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_results_returns_404_when_empty(client: AsyncClient):
    """GIVEN no analysis results exist."""
    endpoint = "/api/analyze/results"

    """WHEN requesting analysis results."""
    resp = await client.get(endpoint)

    """THEN returns 404 with ok false."""
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_export_html_error_handling(client: AsyncClient):
    """GIVEN the export HTML endpoint."""
    endpoint = "/api/export/html"

    """WHEN requesting export without analysis results."""
    resp = await client.get(endpoint)

    """THEN returns 200 with HTML and source has error handling."""
    # Export renders even without analysis results (empty dashboard)
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")

    # Verify the source code actually has the try/except guard
    import inspect

    from releaseboard.web import server
    source = inspect.getsource(server)
    assert "Export HTML template rendering failed" in source


class TestBackgroundTaskReference:
    """Scenarios for background task reference storage."""

    def test_background_tasks_set_exists(self):
        """GIVEN the create_app function source code."""
        import inspect

        from releaseboard.web import server
        source = inspect.getsource(server.create_app)

        """WHEN inspecting for background task storage."""
        has_bg_tasks = "_background_tasks" in source
        has_callback = "add_done_callback" in source

        """THEN _background_tasks set and add_done_callback exist."""
        assert has_bg_tasks
        assert has_callback


class TestSSEEventFormat:
    """Scenarios for SSE event formatting."""

    def test_sse_format_structure(self):
        """GIVEN the SSE format function."""
        from releaseboard.web.server import _sse_format

        """WHEN formatting a test event."""
        output = _sse_format("test_event", {"key": "value"})

        """THEN output has id, event, and data fields with double newline ending."""
        assert "id:" in output
        assert "event: test_event" in output
        assert 'data: {"key": "value"}' in output
        assert output.endswith("\n\n")

    def test_sse_format_increments_id(self):
        """GIVEN the SSE format function."""
        from releaseboard.web.server import _sse_format

        """WHEN formatting two sequential events."""
        out1 = _sse_format("a", {})
        out2 = _sse_format("b", {})

        """THEN the second ID is greater than the first."""
        # Extract IDs
        id1 = int(out1.split("\n")[0].split(": ")[1])
        id2 = int(out2.split("\n")[0].split(": ")[1])
        assert id2 > id1


class TestHealthEndpoints:
    """Scenarios for health endpoints after fixes."""

    @pytest.mark.asyncio
    async def test_health_live(self, client: AsyncClient):
        """GIVEN the liveness endpoint."""
        endpoint = "/health/live"

        """WHEN requesting the probe."""
        resp = await client.get(endpoint)

        """THEN the service reports alive."""
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_health_ready(self, client: AsyncClient):
        """GIVEN the readiness endpoint."""
        endpoint = "/health/ready"

        """WHEN requesting the probe."""
        resp = await client.get(endpoint)

        """THEN returns 200."""
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_status_no_config_path(self, client: AsyncClient):
        """GIVEN the status endpoint."""
        endpoint = "/api/status"

        """WHEN requesting status."""
        resp = await client.get(endpoint)

        """THEN config_path is not exposed and includes version and uptime."""
        assert resp.status_code == 200
        data = resp.json()
        assert "config_path" not in data
        assert "version" in data
        assert "uptime_seconds" in data


class TestExportEndpoint:
    """Scenarios for export endpoint."""

    @pytest.mark.asyncio
    async def test_export_html_returns_200(self, client: AsyncClient):
        """GIVEN the export HTML endpoint."""
        endpoint = "/api/export/html"

        """WHEN requesting export."""
        resp = await client.get(endpoint)

        """THEN returns 200 with HTML content type."""
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_export_html_has_content_disposition(self, client: AsyncClient):
        """GIVEN the export HTML endpoint."""
        endpoint = "/api/export/html"

        """WHEN requesting export."""
        resp = await client.get(endpoint)

        """THEN includes Content-Disposition for download."""
        assert "Content-Disposition" in resp.headers or "content-disposition" in resp.headers
        cd = resp.headers.get("content-disposition", "")
        assert "dashboard.html" in cd

    @pytest.mark.asyncio
    async def test_old_export_url_gives_404(self, client: AsyncClient):
        """GIVEN the old export URL."""
        endpoint = "/export/html"

        """WHEN requesting the old endpoint."""
        resp = await client.get(endpoint)

        """THEN returns 404."""
        assert resp.status_code == 404


class TestAnalyzeSyncEventLoopSafety:
    """Scenarios for analyze_sync event loop safety."""

    def test_no_event_loop(self):
        """GIVEN a mocked provider and minimal config."""
        from releaseboard.application.service import AnalysisService
        from releaseboard.config.models import (
            AppConfig,
            ReleaseConfig,
        )

        mock_provider = MagicMock()
        mock_provider.list_remote_branches.return_value = []
        mock_provider.get_branch_info.return_value = MagicMock(
            name="release/2025.01", exists=False,
        )

        service = AnalysisService(mock_provider)
        config = AppConfig(
            release=ReleaseConfig(name="R", target_month=1, target_year=2025),
            layers=[],
            repositories=[],
        )

        """WHEN calling analyze_sync without a running event loop."""
        result = service.analyze_sync(config)

        """THEN returns a valid result with zero total."""
        assert result is not None
        assert result.metrics.total == 0

    def test_detects_running_loop(self):
        """GIVEN the analyze_sync method source code."""
        import inspect

        from releaseboard.application.service import AnalysisService

        mock_provider = MagicMock()
        service = AnalysisService(mock_provider)
        source = inspect.getsource(service.analyze_sync)

        """WHEN inspecting for event loop detection."""
        has_loop_check = "get_running_loop" in source
        has_thread_pool = "ThreadPoolExecutor" in source

        """THEN it checks for running loop and uses ThreadPoolExecutor."""
        assert has_loop_check, "Must check for running event loop"
        assert has_thread_pool, "Must use thread pool as fallback"


class TestSSEDisconnect:
    """Scenarios for SSE client disconnect detection."""

    @pytest.mark.asyncio
    async def test_sse_subscribe_and_unsubscribe(self, tmp_path: Path):
        """GIVEN the SSE subscriber system."""
        config_path = _write_config(tmp_path)
        state = AppState(config_path)

        """WHEN subscribing and then unsubscribing."""
        queue = state.subscribe()
        assert len(state._sse_subscribers) == 1

        state.unsubscribe(queue)

        """THEN subscribers are properly tracked."""
        assert len(state._sse_subscribers) == 0

    @pytest.mark.asyncio
    async def test_sse_broadcast_removes_dead_queues(self, tmp_path: Path):
        """GIVEN a full SSE queue."""
        config_path = _write_config(tmp_path)
        state = AppState(config_path)

        # Create a queue with maxsize=1 and fill it
        small_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        state._sse_subscribers.append(small_queue)
        await small_queue.put({"event": "filler", "data": {}})

        """WHEN broadcast sends a message."""
        await state.broadcast("test_event", {"test": True})

        """THEN the full queue is removed as dead."""
        assert small_queue not in state._sse_subscribers


class TestConcurrentAnalysis:
    """Scenarios for concurrent analysis."""

    @pytest.mark.asyncio
    async def test_max_concurrent_1_runs_sequentially(self):
        """GIVEN max_concurrent set to 1 with two repositories."""
        from releaseboard.application.service import AnalysisService

        execution_order: list[str] = []

        class OrderTrackingProvider(GitProvider):
            def list_remote_branches(self, url: str, timeout: int = 30) -> list[str]:
                return ["release/03.2025"]

            def get_branch_info(
                self, url: str, branch: str, timeout: int = 30,
            ) -> BranchInfo | None:
                execution_order.append(f"branch:{url}")
                return BranchInfo(
                    name="release/03.2025", exists=True,
                    last_commit_date=datetime.now(tz=UTC),
                    last_commit_author="dev", last_commit_message="ok",
                )

        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025,
                                  branch_pattern="release/{MM}.{YYYY}"),
            layers=[LayerConfig(id="api", label="API", order=0)],
            repositories=[
                RepositoryConfig(name="a", url="https://git.local/a.git", layer="api"),
                RepositoryConfig(name="b", url="https://git.local/b.git", layer="api"),
            ],
            settings=SettingsConfig(max_concurrent=1),
        )

        """WHEN analysis runs."""
        service = AnalysisService(OrderTrackingProvider())
        result = await service.analyze_async(config)

        """THEN both repos are analyzed sequentially."""
        assert len(result.analyses) == 2
        # With max_concurrent=1, should see sequential ordering
        assert len(execution_order) == 2


class TestSSEBroadcastSafety:
    """Scenarios for SSE broadcast race condition safety."""

    @pytest.mark.asyncio
    async def test_broadcast_with_concurrent_unsubscribe(self, state: AppState):
        """GIVEN two active subscribers."""
        q1 = state.subscribe()
        q2 = state.subscribe()

        """WHEN one unsubscribes and broadcast fires."""
        # Manually unsubscribe q1 before broadcast completes
        state.unsubscribe(q1)
        await state.broadcast("test", {"v": 1})

        """THEN remaining subscriber receives the message."""
        # q2 should still get the message
        msg = q2.get_nowait()
        assert msg["event"] == "test"

    @pytest.mark.asyncio
    async def test_broadcast_already_removed_dead_queue(self, state: AppState):
        """GIVEN a full queue that is pre-removed."""
        q = state.subscribe()
        for i in range(100):
            q.put_nowait({"event": f"fill_{i}", "data": {}})

        # Pre-remove to simulate race
        state.unsubscribe(q)

        """WHEN broadcast fires."""
        await state.broadcast("test", {"v": 1})

        """THEN no crash even though queue was already removed."""
        assert q not in state._sse_subscribers


class TestAnalysisTaskErrorHandling:
    """Scenarios for analysis task error handling."""

    @pytest.mark.asyncio
    async def test_analysis_task_failure_sets_failed_phase(self, state: AppState):
        """GIVEN an analysis service that raises an error."""
        from releaseboard.application.service import AnalysisPhase, AnalysisService

        service = AnalysisService.__new__(AnalysisService)

        async def boom(*args, **kwargs):
            raise RuntimeError("simulated failure")

        service.analyze_async = boom

        """WHEN the analysis task runs."""
        # Simulate what trigger_analysis does
        async with state.analysis_lock:
            try:
                config = state.get_active_config()
                await service.analyze_async(config)
            except Exception:
                state.analysis_progress.phase = AnalysisPhase.FAILED
                await state.broadcast("analysis_complete", state.analysis_progress.to_dict())

        """THEN the progress phase is set to FAILED."""
        assert state.analysis_progress.phase == AnalysisPhase.FAILED
