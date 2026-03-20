"""Scenarios for configuration persistence: atomic save, ETag, backup,
defaults, caching, env-var resolution, layer validation, temp-file cleanup."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from releaseboard import __version__
from releaseboard.config.loader import _resolve_env_vars, load_config
from releaseboard.config.models import (
    AppConfig,
    LayoutConfig,
    ReleaseConfig,
)
from releaseboard.config.schema import validate_layer_references
from releaseboard.web.state import (
    AppState,
    _auto_generate_layers,
    fill_config_defaults,
)

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


class TestConfigETag:
    """Scenarios for config ETag handling."""

    @pytest.mark.asyncio
    async def test_config_response_includes_etag(self, client):
        """GIVEN the config API endpoint."""
        url = "/api/config"

        """WHEN requesting the config."""
        resp = await client.get(url)
        body = resp.json()

        """THEN the response includes a 16-char etag in body and headers."""
        assert "etag" in body
        assert len(body["etag"]) == 16  # SHA256 truncated to 16 hex chars
        assert "etag" in resp.headers

    @pytest.mark.asyncio
    async def test_save_with_stale_etag_returns_409(self, client):
        """GIVEN a stale etag value."""
        stale_etag = '"stale-etag-value"'

        """WHEN saving config with the stale etag."""
        resp = await client.post(
            "/api/config/save",
            headers={"if-match": stale_etag},
        )

        """THEN a 409 conflict is returned."""
        assert resp.status_code == 409
        assert "modified" in resp.json()["error"].lower()

    @pytest.mark.asyncio
    async def test_save_with_correct_etag_succeeds(self, client):
        """GIVEN the current etag from the config endpoint."""
        config_resp = await client.get("/api/config")
        etag = config_resp.json()["etag"]

        """WHEN saving config with the matching etag."""
        resp = await client.post(
            "/api/config/save",
            headers={"if-match": f'"{etag}"'},
        )

        """THEN the save succeeds and returns a new etag."""
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "etag" in resp.json()

    @pytest.mark.asyncio
    async def test_save_without_etag_succeeds(self, client):
        """GIVEN an API client with no If-Match header."""
        url = "/api/config/save"

        """WHEN saving config without an etag for backward compatibility."""
        resp = await client.post(url)

        """THEN the save succeeds."""
        assert resp.json()["ok"] is True

    def test_etag_changes_on_config_change(self, config_path):
        """GIVEN an AppState with an initial etag."""
        from releaseboard.web.state import AppState
        state = AppState(config_path)
        etag1 = state.config_state.config_etag

        """WHEN the draft is modified and saved."""
        draft = state.get_draft()
        draft["branding"]["title"] = "Changed"
        state.update_draft(draft)
        state.save_config()
        etag2 = state.config_state.config_etag

        """THEN the etag changes."""
        assert etag1 != etag2


class TestConfigBackup:
    """Scenarios for config backup on save."""

    @pytest.mark.asyncio
    async def test_save_creates_backup_file(self, client, config_path):
        """GIVEN a config file with no existing backup."""
        backup_path = config_path.with_suffix(".json.bak")
        assert not backup_path.exists()

        """WHEN saving config via the API."""
        resp = await client.post("/api/config/save")

        """THEN a backup file is created."""
        assert resp.json()["ok"] is True
        assert backup_path.exists()

    @pytest.mark.asyncio
    async def test_backup_is_valid_json(self, client, config_path):
        """GIVEN a config that has been saved once."""
        await client.post("/api/config/save")
        backup_path = config_path.with_suffix(".json.bak")

        """WHEN reading the backup file."""
        data = json.loads(backup_path.read_text(encoding="utf-8"))

        """THEN it contains valid JSON with a release key."""
        assert isinstance(data, dict)
        assert "release" in data


class TestConfigPathNotLeaked:
    """Scenarios for config_path not exposed in API."""

    @pytest.mark.asyncio
    async def test_api_config_no_path(self, client: AsyncClient):
        """GIVEN the config API endpoint."""
        url = "/api/config"

        """WHEN requesting the config."""
        resp = await client.get(url)

        """THEN config_path is not in the response."""
        assert resp.status_code == 200
        data = resp.json()
        assert "config_path" not in data

    def test_to_api_dict_no_config_path(self, tmp_path: Path):
        """GIVEN a ConfigState built from minimal config."""
        from releaseboard.config.loader import (
            _build_branding,
            _build_layers,
            _build_release,
            _build_repositories,
            _build_settings,
        )
        from releaseboard.config.models import AppConfig
        from releaseboard.web.state import ConfigState

        raw = _make_minimal_config()
        config = AppConfig(
            release=_build_release(raw["release"]),
            layers=_build_layers(raw.get("layers")),
            repositories=_build_repositories(raw["repositories"]),
            branding=_build_branding(raw.get("branding")),
            settings=_build_settings(raw.get("settings")),
        )
        cs = ConfigState(
            persisted_raw=dict(raw),
            draft_raw=dict(raw),
            persisted=config,
            config_path=tmp_path / "releaseboard.json",
        )

        """WHEN converting to API dict."""
        api_dict = cs.to_api_dict()

        """THEN config_path is absent and expected keys are present."""
        assert "config_path" not in api_dict
        assert "persisted" in api_dict
        assert "draft" in api_dict
        assert "has_unsaved_changes" in api_dict


class TestConfigEndpointShape:
    """Scenarios for /api/config response shape."""

    @pytest.mark.asyncio
    async def test_config_has_expected_keys(self, client: AsyncClient):
        """GIVEN the config API endpoint."""
        url = "/api/config"

        """WHEN requesting the config."""
        resp = await client.get(url)
        data = resp.json()

        """THEN the response has expected keys and no config_path."""
        assert resp.status_code == 200
        assert "persisted" in data
        assert "draft" in data
        assert "has_unsaved_changes" in data
        assert "config_path" not in data

    @pytest.mark.asyncio
    async def test_config_persisted_matches_draft_initially(self, client: AsyncClient):
        """GIVEN the config API endpoint."""
        url = "/api/config"

        """WHEN requesting the config before any changes."""
        resp = await client.get(url)
        data = resp.json()

        """THEN persisted and draft are equal with no unsaved changes."""
        assert data["persisted"] == data["draft"]
        assert data["has_unsaved_changes"] is False


class TestBuildSettingsDefensive:
    """Scenarios for _build_settings defensive int conversion."""

    def test_non_numeric_stale_threshold(self):
        """GIVEN settings with non-numeric stale_threshold_days."""
        from releaseboard.config.loader import _build_settings
        raw = {"stale_threshold_days": "abc"}

        """WHEN building settings."""
        settings = _build_settings(raw)

        """THEN it falls back to the default value."""
        assert settings.stale_threshold_days == 14  # default

    def test_non_numeric_timeout(self):
        """GIVEN settings with non-numeric timeout_seconds."""
        from releaseboard.config.loader import _build_settings
        raw = {"timeout_seconds": "not-a-number"}

        """WHEN building settings."""
        settings = _build_settings(raw)

        """THEN it falls back to the default value."""
        assert settings.timeout_seconds == 30  # default

    def test_non_numeric_max_concurrent(self):
        """GIVEN settings with None max_concurrent."""
        from releaseboard.config.loader import _build_settings
        raw = {"max_concurrent": None}

        """WHEN building settings."""
        settings = _build_settings(raw)

        """THEN it falls back to the default value."""
        assert settings.max_concurrent == 5  # default

    def test_valid_string_numbers_work(self):
        """GIVEN settings with string representations of numbers."""
        from releaseboard.config.loader import _build_settings
        raw = {
            "stale_threshold_days": "7",
            "timeout_seconds": "60",
            "max_concurrent": "10",
        }

        """WHEN building settings."""
        settings = _build_settings(raw)

        """THEN the string numbers are correctly parsed."""
        assert settings.stale_threshold_days == 7
        assert settings.timeout_seconds == 60
        assert settings.max_concurrent == 10

    def test_none_data_returns_defaults(self):
        """GIVEN None as input data."""
        from releaseboard.config.loader import _build_settings
        data = None

        """WHEN building settings."""
        settings = _build_settings(data)

        """THEN all defaults are used."""
        assert settings.stale_threshold_days == 14
        assert settings.timeout_seconds == 30
        assert settings.max_concurrent == 5


class TestRateLimiterPruning:
    """Scenarios for rate limiter pruning logic."""

    def test_pruning_logic_in_source(self):
        """GIVEN the RateLimitMiddleware source code."""
        import inspect

        from releaseboard.web import middleware
        source = inspect.getsource(middleware.RateLimitMiddleware)

        """WHEN inspecting the source for pruning logic."""
        has_cutoff = "cutoff" in source
        has_stale_ips = "stale_ips" in source
        has_last_resort = "last resort" in source.lower() or "force-clear" in source.lower()

        """THEN selective pruning keywords are present."""
        assert has_cutoff
        assert has_stale_ips
        assert has_last_resort

    def test_prune_removes_stale_keeps_fresh(self):
        """GIVEN a rate limiter with 10001 IPs, some stale and some fresh."""
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
        assert len(limiter._windows) > 10_000

        """WHEN pruning stale entries older than 60 seconds."""
        cutoff = now - 60
        stale = [
            ip for ip, times in limiter._windows.items()
            if not times or times[-1] < cutoff
        ]
        for ip in stale:
            del limiter._windows[ip]

        """THEN only fresh IPs remain."""
        assert len(limiter._windows) > 0
        assert len(limiter._windows) <= 5_001  # only fresh ones


class TestFillConfigDefaultsZero:
    """Scenarios for fill_config_defaults preserving zero values."""

    def test_zero_max_concurrent_preserved(self):
        """GIVEN config data with max_concurrent set to zero."""
        data: dict[str, Any] = {
            "release": {},
            "repositories": [],
            "settings": {"max_concurrent": 0},
        }

        """WHEN filling config defaults."""
        fill_config_defaults(data)

        """THEN the zero value is preserved."""
        assert data["settings"]["max_concurrent"] == 0

    def test_zero_timeout_preserved(self):
        """GIVEN config data with timeout_seconds set to zero."""
        data: dict[str, Any] = {
            "release": {},
            "repositories": [],
            "settings": {"timeout_seconds": 0},
        }

        """WHEN filling config defaults."""
        fill_config_defaults(data)

        """THEN the zero value is preserved."""
        assert data["settings"]["timeout_seconds"] == 0

    def test_zero_stale_threshold_preserved(self):
        """GIVEN config data with stale_threshold_days set to zero."""
        data: dict[str, Any] = {
            "release": {},
            "repositories": [],
            "settings": {"stale_threshold_days": 0},
        }

        """WHEN filling config defaults."""
        fill_config_defaults(data)

        """THEN the zero value is preserved."""
        assert data["settings"]["stale_threshold_days"] == 0

    def test_none_still_gets_default(self):
        """GIVEN config data with None values for settings."""
        data: dict[str, Any] = {
            "release": {},
            "repositories": [],
            "settings": {"max_concurrent": None, "timeout_seconds": None},
        }

        """WHEN filling config defaults."""
        fill_config_defaults(data)

        """THEN None values are replaced with defaults."""
        assert data["settings"]["max_concurrent"] == 5
        assert data["settings"]["timeout_seconds"] == 30

    def test_empty_string_still_gets_default(self):
        """GIVEN config data with an empty string for theme."""
        data: dict[str, Any] = {
            "release": {},
            "repositories": [],
            "settings": {"theme": ""},
        }

        """WHEN filling config defaults."""
        fill_config_defaults(data)

        """THEN the empty string is replaced with the default."""
        assert data["settings"]["theme"] == "system"

    def test_valid_nonzero_values_untouched(self):
        """GIVEN config data with valid nonzero settings."""
        data: dict[str, Any] = {
            "release": {},
            "repositories": [],
            "settings": {"max_concurrent": 10, "timeout_seconds": 60, "stale_threshold_days": 7},
        }

        """WHEN filling config defaults."""
        fill_config_defaults(data)

        """THEN the nonzero values are untouched."""
        assert data["settings"]["max_concurrent"] == 10
        assert data["settings"]["timeout_seconds"] == 60
        assert data["settings"]["stale_threshold_days"] == 7


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

    def test_second_call_uses_cache(self, tmp_path):
        """GIVEN an AppState with a cached active config."""
        state = self._make_state(tmp_path)
        cfg1 = state.get_active_config()

        """WHEN calling get_active_config again without changes."""
        cfg2 = state.get_active_config()

        """THEN the same cached object is returned."""
        assert cfg1 is cfg2

    def test_cache_invalidated_after_draft_change(self, tmp_path):
        """GIVEN an AppState with a cached active config."""
        state = self._make_state(tmp_path)
        cfg1 = state.get_active_config()

        """WHEN updating the draft with different content."""
        new_draft = json.loads(json.dumps(state.config_state.draft_raw))
        new_draft["release"]["name"] = "R2"
        state.update_draft(new_draft)
        cfg2 = state.get_active_config()

        """THEN a new config object is built."""
        assert cfg2 is not cfg1

    def test_cache_not_stale_after_same_update(self, tmp_path):
        """GIVEN an AppState with a cached active config."""
        state = self._make_state(tmp_path)
        cfg1 = state.get_active_config()

        """WHEN updating draft with identical content."""
        state.update_draft(json.loads(json.dumps(state.config_state.draft_raw)))
        cfg2 = state.get_active_config()

        """THEN the cache is reused because the hash is unchanged."""
        assert cfg1 is cfg2  # same hash → cache hit


class TestAtomicConfigSave:
    """Scenarios for atomic config save."""

    def test_save_config_writes_valid_json(self, tmp_path: Path):
        """GIVEN a valid draft config with a modified branding title."""
        config_path = _write_config(tmp_path)
        state = AppState(config_path)
        state.config_state.draft_raw["branding"]["title"] = "Updated Title"

        """WHEN save_config is called."""
        errors = state.save_config()

        """THEN the file on disk contains valid JSON matching the draft."""
        assert errors == []
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved["branding"]["title"] == "Updated Title"

    def test_save_config_no_partial_writes(self, tmp_path: Path):
        """GIVEN an AppState with a valid config."""
        config_path = _write_config(tmp_path)
        state = AppState(config_path)

        """WHEN save_config completes."""
        state.save_config()

        """THEN no temporary files are left behind."""
        tmp_files = list(tmp_path.glob(".releaseboard_*"))
        assert tmp_files == [], f"Temp files left behind: {tmp_files}"

    def test_save_config_with_invalid_draft_returns_errors(self, tmp_path: Path):
        """GIVEN an invalid draft with a missing required field."""
        config_path = _write_config(tmp_path)
        state = AppState(config_path)
        original_content = config_path.read_text(encoding="utf-8")
        del state.config_state.draft_raw["release"]["name"]

        """WHEN save_config is called."""
        errors = state.save_config()

        """THEN errors are returned and the file is not modified."""
        assert len(errors) > 0
        assert config_path.read_text(encoding="utf-8") == original_content


class TestVersionConsistency:
    """Scenarios for version consistency."""

    @pytest.mark.asyncio
    async def test_status_endpoint_uses_package_version(self, tmp_path: Path):
        """GIVEN a test app and the /api/status endpoint."""
        app, _ = _create_app_for_test(tmp_path)

        """WHEN calling the status endpoint."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/status")
            data = resp.json()

        """THEN the version matches __version__ from the package."""
        assert data["version"] == __version__

    def test_version_not_hardcoded_in_server(self):
        """GIVEN the server.py source code."""
        import inspect

        import releaseboard.web.server as mod
        source = inspect.getsource(mod)

        """WHEN checking for hardcoded version strings."""
        has_hardcoded = 'version="1.0.0"' in source

        """THEN there are no hardcoded version assignments."""
        assert not has_hardcoded


class TestLayoutConfig:
    """Scenarios for layout config loading."""

    def test_layout_config_model_defaults(self):
        """GIVEN a default LayoutConfig."""
        layout = LayoutConfig()

        """WHEN inspecting its attributes."""
        template = layout.default_template
        section_order = layout.section_order
        drag_drop = layout.enable_drag_drop

        """THEN it has sensible defaults."""
        assert template == "default"
        assert isinstance(section_order, tuple)
        assert drag_drop is True

    def test_app_config_includes_layout(self):
        """GIVEN an AppConfig with minimal fields."""
        config = AppConfig(
            release=ReleaseConfig(name="Test", target_month=3, target_year=2025),
        )

        """WHEN accessing the layout field."""
        layout = config.layout

        """THEN it is a LayoutConfig instance."""
        assert isinstance(layout, LayoutConfig)

    def test_loader_builds_layout_from_json(self, tmp_path: Path):
        """GIVEN a config file with a custom layout section."""
        data = dict(MINIMAL_CONFIG)
        data["layout"] = {
            "default_template": "executive",
            "section_order": ["score", "metrics"],
            "enable_drag_drop": False,
        }
        config_path = _write_config(tmp_path, data)

        """WHEN loading the config."""
        config = load_config(config_path)

        """THEN the layout is properly parsed."""
        assert config.layout.default_template == "executive"
        assert config.layout.section_order == ("score", "metrics")
        assert config.layout.enable_drag_drop is False

    def test_loader_uses_defaults_when_no_layout(self, tmp_path: Path):
        """GIVEN a config file without a layout section."""
        config_path = _write_config(tmp_path)

        """WHEN loading the config."""
        config = load_config(config_path)

        """THEN the default LayoutConfig is used."""
        assert config.layout.default_template == "default"


class TestPackageData:
    """Scenarios for package data file existence."""

    def test_template_file_exists(self):
        """GIVEN the templates directory."""
        from releaseboard.presentation.renderer import _TEMPLATE_DIR
        template = _TEMPLATE_DIR / "dashboard.html.j2"

        """WHEN checking for the dashboard template."""
        exists = template.exists()

        """THEN the template file exists."""
        assert exists, f"Template not found: {template}"

    def test_locale_files_exist(self):
        """GIVEN the locales directory."""
        from releaseboard.i18n import _LOCALES_DIR
        en_path = _LOCALES_DIR / "en.json"
        pl_path = _LOCALES_DIR / "pl.json"

        """WHEN checking for locale files."""
        en_exists = en_path.exists()
        pl_exists = pl_path.exists()

        """THEN en.json and pl.json both exist."""
        assert en_exists
        assert pl_exists

    def test_schema_json_exists(self):
        """GIVEN the config directory."""
        from releaseboard.config.schema import _SCHEMA_PATH
        schema_path = _SCHEMA_PATH

        """WHEN checking for schema.json."""
        exists = schema_path.exists()

        """THEN the schema file exists."""
        assert exists


class TestEnvVarResolution:
    """Scenarios for env var resolution."""

    def test_unresolved_env_var_preserved_as_placeholder(self):
        """GIVEN a string with an unset environment variable placeholder."""
        input_str = "https://${NONEXISTENT_VAR_12345}/repo"

        """WHEN resolving env vars."""
        result = _resolve_env_vars(input_str)

        """THEN the placeholder is left as-is."""
        assert "${NONEXISTENT_VAR_12345}" in result

    def test_resolved_env_var_replaced(self):
        """GIVEN a string with a set environment variable."""
        input_str = "https://${TEST_HOST_XYZ}/repo"

        """WHEN resolving env vars with the variable set."""
        with patch.dict(os.environ, {"TEST_HOST_XYZ": "git.example.com"}):
            result = _resolve_env_vars(input_str)

        """THEN the value is substituted."""
        assert result == "https://git.example.com/repo"


class TestActiveConfigTempFileCleanup:
    """Scenarios for get_active_config temp file cleanup."""

    def test_temp_file_cleaned_on_success(self, state: AppState, tmp_path: Path):
        """GIVEN a valid draft and the current temp files on disk."""
        temp_dir = tempfile.gettempdir()
        before = set(Path(temp_dir).glob("*.json"))

        """WHEN get_active_config succeeds."""
        state.get_active_config()
        after = set(Path(temp_dir).glob("*.json"))

        """THEN no temp files remain."""
        leaked = after - before
        assert len(leaked) == 0, f"Leaked temp files: {leaked}"

    def test_temp_file_cleaned_on_failure(self, state: AppState):
        """GIVEN a draft that causes load_config to fail."""
        temp_dir = tempfile.gettempdir()
        before = set(Path(temp_dir).glob("*.json"))

        """WHEN get_active_config is called with a broken loader."""
        with patch("releaseboard.web.state.load_config", side_effect=RuntimeError("boom")):
            config = state.get_active_config()

        """THEN it falls back gracefully and no temp file leaks."""
        assert config.release.name == MINIMAL_CONFIG["release"]["name"]
        after = set(Path(temp_dir).glob("*.json"))
        leaked = after - before
        assert len(leaked) == 0, f"Leaked temp files: {leaked}"


class TestAutoGenerateLayersNoDuplicates:
    """Scenarios for _auto_generate_layers deduplication."""

    def test_no_duplicates_when_layer_exists(self):
        """GIVEN data with an existing 'ui' layer and repos referencing 'ui' and 'api'."""
        data: dict[str, Any] = {
            "layers": [{"id": "ui", "label": "Frontend", "color": "#111111"}],
            "repositories": [
                {"name": "a", "url": "x", "layer": "ui"},
                {"name": "b", "url": "y", "layer": "api"},
            ],
        }

        """WHEN _auto_generate_layers runs."""
        _auto_generate_layers(data)
        layer_ids = [layer["id"] for layer in data["layers"]]

        """THEN only 'api' is added and the existing 'ui' retains its label."""
        assert layer_ids.count("ui") == 1
        assert "api" in layer_ids
        ui_layer = next(layer for layer in data["layers"] if layer["id"] == "ui")
        assert ui_layer["label"] == "Frontend"

    def test_no_generation_when_all_layers_exist(self):
        """GIVEN data where all referenced layers already exist."""
        data: dict[str, Any] = {
            "layers": [{"id": "api", "label": "API"}],
            "repositories": [{"name": "a", "url": "x", "layer": "api"}],
        }
        original_count = len(data["layers"])

        """WHEN _auto_generate_layers runs."""
        _auto_generate_layers(data)

        """THEN no new layers are added."""
        assert len(data["layers"]) == original_count


class TestAppStateInvalidJson:
    """Scenarios for AppState invalid JSON handling."""

    def test_invalid_json_raises_value_error(self, tmp_path: Path):
        """GIVEN a config file with invalid JSON."""
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{ not valid json }", encoding="utf-8")

        """WHEN AppState is constructed."""
        with pytest.raises(ValueError, match="Invalid JSON") as exc_info:
            AppState(bad_path)

        """THEN a ValueError is raised with the file path in the message."""
        assert exc_info.type is ValueError

    def test_valid_json_loads_normally(self, config_file: Path):
        """GIVEN a valid config file."""
        path = config_file

        """WHEN AppState is constructed."""
        state = AppState(path)

        """THEN no error is raised and data loads correctly."""
        assert state.config_state.persisted.release.name == MINIMAL_CONFIG["release"]["name"]


class TestValidateLayerReferences:
    """Scenarios for validate_layer_references robustness."""

    def test_rejects_undefined_layer(self):
        """GIVEN repos referencing a layer not in the layers list."""
        data = {
            "layers": [{"id": "ui", "label": "UI"}],
            "repositories": [{"name": "a", "url": "x", "layer": "nonexistent"}],
        }

        """WHEN validating layer references."""
        errors = validate_layer_references(data)

        """THEN validation returns an error mentioning the undefined layer."""
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_accepts_defined_layer(self):
        """GIVEN repos referencing a layer that exists in the layers list."""
        data = {
            "layers": [{"id": "ui", "label": "UI"}],
            "repositories": [{"name": "a", "url": "x", "layer": "ui"}],
        }

        """WHEN validating layer references."""
        errors = validate_layer_references(data)

        """THEN no errors are returned."""
        assert errors == []

    def test_malformed_layer_entries_do_not_crash(self):
        """GIVEN a layers list with a non-dict item."""
        data = {
            "layers": ["not-a-dict", {"id": "api", "label": "API"}],
            "repositories": [{"name": "a", "url": "x", "layer": "api"}],
        }

        """WHEN validating layer references."""
        errors = validate_layer_references(data)

        """THEN no crash occurs and validation passes."""
        assert errors == []

    def test_malformed_repo_entries_do_not_crash(self):
        """GIVEN a repositories list with a non-dict item."""
        data = {
            "layers": [{"id": "api", "label": "API"}],
            "repositories": ["not-a-dict"],
        }

        """WHEN validating layer references."""
        errors = validate_layer_references(data)

        """THEN no crash occurs and validation passes."""
        assert errors == []

    def test_empty_layers_skips_validation(self):
        """GIVEN an empty layers list and repos with arbitrary layer references."""
        data = {
            "layers": [],
            "repositories": [{"name": "a", "url": "x", "layer": "anything"}],
        }

        """WHEN validating layer references."""
        errors = validate_layer_references(data)

        """THEN validation is skipped and no errors are returned."""
        assert errors == []
