"""Tests for the FastAPI web endpoints.

Covers config CRUD, analysis trigger, static export, and status endpoints.
Uses httpx AsyncClient with the TestClient pattern.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from releaseboard.web.server import create_app

if TYPE_CHECKING:
    from pathlib import Path

MINIMAL_CONFIG: dict[str, Any] = {
    "release": {
        "name": "March 2025",
        "target_month": 3,
        "target_year": 2025,
        "branch_pattern": "release/{MM}.{YYYY}",
    },
    "layers": [
        {"id": "ui", "label": "UI", "order": 0},
        {"id": "api", "label": "API", "order": 1},
    ],
    "repositories": [
        {"name": "web-app", "url": "https://git.local/web.git", "layer": "ui"},
        {"name": "svc-api", "url": "https://git.local/api.git", "layer": "api"},
    ],
}


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(MINIMAL_CONFIG, indent=2), encoding="utf-8")
    return p


@pytest.fixture
def app(config_file: Path):
    return create_app(config_file)


@pytest_asyncio.fixture
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Dashboard ──


class TestDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_returns_html(self, client: AsyncClient):
        """GIVEN the app is running
        WHEN GET / is requested
        THEN HTML dashboard is returned."""
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "ReleaseBoard" in resp.text


# ── Config API ──


class TestConfigAPI:
    @pytest.mark.asyncio
    async def test_get_config(self, client: AsyncClient):
        """GIVEN the app has loaded config
        WHEN GET /api/config is called
        THEN config state is returned."""
        resp = await client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "draft" in data
        assert "persisted" in data
        assert data["has_unsaved_changes"] is False

    @pytest.mark.asyncio
    async def test_update_draft(self, client: AsyncClient):
        """GIVEN valid config
        WHEN PUT /api/config is called
        THEN draft is updated."""
        new_config = json.loads(json.dumps(MINIMAL_CONFIG))
        new_config["release"]["name"] = "Updated via API"
        resp = await client.put("/api/config", json=new_config)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify draft changed
        resp2 = await client.get("/api/config")
        assert resp2.json()["draft"]["release"]["name"] == "Updated via API"
        assert resp2.json()["has_unsaved_changes"] is True

    @pytest.mark.asyncio
    async def test_save_config(self, client: AsyncClient, config_file: Path):
        """GIVEN modified draft
        WHEN POST /api/config/save is called
        THEN changes are persisted to disk."""
        new_config = json.loads(json.dumps(MINIMAL_CONFIG))
        new_config["release"]["name"] = "Saved via API"
        await client.put("/api/config", json=new_config)

        resp = await client.post("/api/config/save")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify on disk
        on_disk = json.loads(config_file.read_text())
        assert on_disk["release"]["name"] == "Saved via API"

    @pytest.mark.asyncio
    async def test_reset_config(self, client: AsyncClient):
        """GIVEN a modified draft
        WHEN POST /api/config/reset is called
        THEN draft is restored to persisted."""
        new_config = json.loads(json.dumps(MINIMAL_CONFIG))
        new_config["release"]["name"] = "To be reset"
        await client.put("/api/config", json=new_config)

        resp = await client.post("/api/config/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["draft"]["release"]["name"] == MINIMAL_CONFIG["release"]["name"]

    @pytest.mark.asyncio
    async def test_validate_valid_config(self, client: AsyncClient):
        """GIVEN valid config
        WHEN POST /api/config/validate is called
        THEN no errors returned."""
        resp = await client.post("/api/config/validate", json=MINIMAL_CONFIG)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["errors"] == []

    @pytest.mark.asyncio
    async def test_validate_invalid_config(self, client: AsyncClient):
        """GIVEN invalid config
        WHEN POST /api/config/validate is called
        THEN errors returned."""
        resp = await client.post("/api/config/validate", json={"release": {}})
        data = resp.json()
        assert data["ok"] is False
        assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_get_schema(self, client: AsyncClient):
        """GIVEN the app
        WHEN GET /api/config/schema is called
        THEN JSON Schema is returned with example."""
        resp = await client.get("/api/config/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True
        schema = data.get("schema", {})
        assert schema.get("type") == "object" or "$schema" in schema
        assert "example" in data


# ── Export ──


class TestExport:
    @pytest.mark.asyncio
    async def test_export_html_returns_static_dashboard(self, client: AsyncClient):
        """GIVEN the app
        WHEN GET /api/export/html is called
        THEN a self-contained HTML is returned without interactive features."""
        resp = await client.get("/api/export/html")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        html = resp.text
        assert "ReleaseBoard" in html
        # Interactive toolbar should NOT appear in static export
        assert "btnAnalyze" not in html

    @pytest.mark.asyncio
    async def test_export_config_returns_json(self, client: AsyncClient):
        """GIVEN the app
        WHEN GET /api/config/export is called
        THEN current config is returned as JSON."""
        resp = await client.get("/api/config/export")
        assert resp.status_code == 200
        data = resp.json()
        assert "release" in data
        assert "repositories" in data


# ── Status ──


class TestStatus:
    @pytest.mark.asyncio
    async def test_app_status(self, client: AsyncClient):
        """GIVEN the app
        WHEN GET /api/status is called
        THEN health check passes."""
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "version" in data


# ── Cancel Analysis ──


class TestCancelAnalysis:
    @pytest.mark.asyncio
    async def test_cancel_when_not_running_returns_409(self, client: AsyncClient):
        """GIVEN no analysis running
        WHEN POST /api/analyze/cancel is called
        THEN 409 is returned."""
        resp = await client.post("/api/analyze/cancel")
        assert resp.status_code == 409
        assert resp.json()["ok"] is False


# ── Type coercion via config API ──


class TestTypeCoercionViaAPI:
    @pytest.mark.asyncio
    async def test_string_month_coerced_to_int(self, client: AsyncClient):
        """GIVEN config with target_month as string
        WHEN PUT /api/config is called
        THEN stored value is an integer."""
        config = json.loads(json.dumps(MINIMAL_CONFIG))
        config["release"]["target_month"] = "4"
        config["release"]["target_year"] = "2026"
        resp = await client.put("/api/config", json=config)
        assert resp.json()["ok"] is True

        # Verify types in stored draft
        resp2 = await client.get("/api/config")
        draft = resp2.json()["draft"]
        assert isinstance(draft["release"]["target_month"], int)
        assert draft["release"]["target_month"] == 4
        assert isinstance(draft["release"]["target_year"], int)
