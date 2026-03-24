"""Tests for web application state management.

Covers the three-tier config model (persisted → active → draft),
save/reset/import/export operations, and SSE subscriber management.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from releaseboard.web.state import (
    AppState,
    fill_config_defaults,
    normalize_config_types,
)

if TYPE_CHECKING:
    from pathlib import Path

# ── Fixtures ──


MINIMAL_CONFIG: dict[str, Any] = {
    "release": {
        "name": "March 2025",
        "target_month": 3,
        "target_year": 2025,
        "branch_pattern": "release/{MM}.{YYYY}",
    },
    "layers": [
        {"id": "api", "label": "API", "order": 0},
    ],
    "repositories": [
        {
            "name": "svc-one",
            "url": "https://git.local/svc-one.git",
            "layer": "api",
        },
    ],
}


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(MINIMAL_CONFIG, indent=2), encoding="utf-8")
    return p


@pytest.fixture
def state(config_file: Path) -> AppState:
    return AppState(config_file)


# ── ConfigState property tests ──


class TestConfigState:
    def test_no_unsaved_changes_initially(self, state: AppState):
        """GIVEN a freshly loaded state
        THEN there are no unsaved changes."""
        assert state.config_state.has_unsaved_changes is False

    def test_draft_update_creates_unsaved_changes(self, state: AppState):
        """GIVEN an initial state
        WHEN draft is modified
        THEN has_unsaved_changes becomes True."""
        draft = state.get_draft()
        draft["release"]["name"] = "April 2025"
        state.update_draft(draft)
        assert state.config_state.has_unsaved_changes is True

    def test_to_api_dict_structure(self, state: AppState):
        """GIVEN a config state
        WHEN serialized to API dict
        THEN required keys are present."""
        d = state.config_state.to_api_dict()
        assert "persisted" in d
        assert "draft" in d
        assert "has_unsaved_changes" in d
        # config_path deliberately removed from API response (security: info disclosure)


# ── Draft operations ──


class TestDraftOperations:
    def test_update_draft_with_valid_config(self, state: AppState):
        """GIVEN valid config data
        WHEN draft is updated
        THEN no validation errors."""
        draft = state.get_draft()
        draft["release"]["name"] = "New Release"
        errors = state.update_draft(draft)
        assert errors == []

    def test_update_draft_stores_invalid_config(self, state: AppState):
        """GIVEN invalid config data (missing required fields)
        WHEN draft is updated
        THEN validation errors returned but draft still updated (with defaults filled)."""
        errors = state.update_draft({"release": {}})
        assert len(errors) > 0
        # Draft was updated — release section preserved, defaults filled in
        assert state.config_state.draft_raw["release"] == {}
        # Defaults are auto-populated for optional sections
        assert "branding" in state.config_state.draft_raw
        assert "settings" in state.config_state.draft_raw

    def test_validate_draft_checks_layer_references(self, state: AppState):
        """GIVEN a repo referencing a nonexistent layer
        WHEN draft is validated
        THEN layer reference error is returned."""
        draft = state.get_draft()
        draft["repositories"][0]["layer"] = "nonexistent"
        state.update_draft(draft)
        errors = state.validate_draft()
        assert any("nonexistent" in e for e in errors)


# ── Save / Reset / Import / Export ──


class TestSaveAndReset:
    def test_save_persists_draft_to_disk(self, state: AppState, config_file: Path):
        """GIVEN a modified draft
        WHEN save is called
        THEN changes are written to disk and unsaved flag cleared."""
        draft = state.get_draft()
        draft["release"]["name"] = "Saved Release"
        state.update_draft(draft)
        assert state.config_state.has_unsaved_changes is True

        errors = state.save_config()
        assert errors == []
        assert state.config_state.has_unsaved_changes is False

        # Verify it's actually on disk
        on_disk = json.loads(config_file.read_text())
        assert on_disk["release"]["name"] == "Saved Release"

    def test_save_rejects_invalid_draft(self, state: AppState):
        """GIVEN an invalid draft
        WHEN save is called
        THEN errors are returned and config is not persisted."""
        state.update_draft({"release": {}})
        errors = state.save_config()
        assert len(errors) > 0

    def test_reset_restores_persisted(self, state: AppState):
        """GIVEN a modified draft
        WHEN reset is called
        THEN draft matches persisted and unsaved flag cleared."""
        draft = state.get_draft()
        draft["release"]["name"] = "Modified"
        state.update_draft(draft)
        assert state.config_state.has_unsaved_changes is True

        state.reset_draft()
        assert state.config_state.has_unsaved_changes is False
        assert state.get_draft()["release"]["name"] == MINIMAL_CONFIG["release"]["name"]

    def test_import_config_updates_draft(self, state: AppState):
        """GIVEN new config data
        WHEN imported
        THEN draft is updated."""
        new_config = json.loads(json.dumps(MINIMAL_CONFIG))
        new_config["release"]["name"] = "Imported Release"
        errors = state.import_config(new_config)
        assert errors == []
        assert state.get_draft()["release"]["name"] == "Imported Release"

    def test_export_returns_current_draft(self, state: AppState):
        """GIVEN a state with draft changes
        WHEN export is called
        THEN draft is returned."""
        draft = state.get_draft()
        draft["release"]["name"] = "Exported"
        state.update_draft(draft)

        exported = state.export_config()
        assert exported["release"]["name"] == "Exported"


# ── get_active_config ──


class TestActiveConfig:
    def test_active_config_from_valid_draft(self, state: AppState):
        """GIVEN a valid draft
        WHEN get_active_config is called
        THEN it builds config from draft."""
        config = state.get_active_config()
        assert config.release.name == MINIMAL_CONFIG["release"]["name"]

    def test_active_config_falls_back_to_persisted(self, state: AppState):
        """GIVEN an invalid draft
        WHEN get_active_config is called
        THEN it falls back to persisted config."""
        state.update_draft({"release": {}})
        config = state.get_active_config()
        # Should still return a valid config (persisted)
        assert config.release.name == MINIMAL_CONFIG["release"]["name"]


# ── SSE Subscriber tests ──


class TestSSESubscribers:
    def test_subscribe_creates_queue(self, state: AppState):
        q = state.subscribe()
        assert isinstance(q, asyncio.Queue)
        assert q in state._sse_subscribers

    def test_unsubscribe_removes_queue(self, state: AppState):
        q = state.subscribe()
        state.unsubscribe(q)
        assert q not in state._sse_subscribers

    @pytest.mark.asyncio
    async def test_broadcast_delivers_to_subscribers(self, state: AppState):
        """GIVEN two subscribers
        WHEN an event is broadcast
        THEN both receive it."""
        q1 = state.subscribe()
        q2 = state.subscribe()

        await state.broadcast("test_event", {"key": "value"})

        msg1 = q1.get_nowait()
        msg2 = q2.get_nowait()
        assert msg1["event"] == "test_event"
        assert msg1["data"]["key"] == "value"
        assert msg2["event"] == "test_event"

    @pytest.mark.asyncio
    async def test_broadcast_drops_full_queues(self, state: AppState):
        """GIVEN a subscriber with a full queue
        WHEN broadcast is called
        THEN the full queue is cleaned up."""
        q = state.subscribe()
        # Fill the queue
        for i in range(100):
            q.put_nowait({"event": f"fill_{i}", "data": {}})

        # This should not raise, and should remove the full queue
        await state.broadcast("overflow", {"x": 1})
        assert q not in state._sse_subscribers


# ── Type normalization tests ──


class TestNormalizeConfigTypes:
    """Tests for the type coercion utility."""

    def test_string_month_coerced_to_int(self):
        """GIVEN target_month as a string
        WHEN normalized
        THEN it becomes an integer."""
        data = {"release": {"target_month": "4", "target_year": "2025"}}
        result = normalize_config_types(data)
        assert result["release"]["target_month"] == 4
        assert isinstance(result["release"]["target_month"], int)
        assert result["release"]["target_year"] == 2025

    def test_integer_values_unchanged(self):
        """GIVEN already-integer values
        WHEN normalized
        THEN they remain integers."""
        data = {"release": {"target_month": 3, "target_year": 2025}}
        result = normalize_config_types(data)
        assert result["release"]["target_month"] == 3

    def test_settings_integers_coerced(self):
        data = {
            "settings": {
                "stale_threshold_days": "14",
                "timeout_seconds": "30",
                "max_concurrent": "5",
            },
        }
        result = normalize_config_types(data)
        assert result["settings"]["stale_threshold_days"] == 14
        assert result["settings"]["timeout_seconds"] == 30
        assert result["settings"]["max_concurrent"] == 5

    def test_layer_order_coerced(self):
        data = {"layers": [{"id": "ui", "label": "UI", "order": "0"}]}
        result = normalize_config_types(data)
        assert result["layers"][0]["order"] == 0

    def test_invalid_string_not_coerced(self):
        """GIVEN a non-numeric string in a numeric field
        WHEN normalized
        THEN the value is left as-is (schema will catch it)."""
        data = {"release": {"target_month": "abc"}}
        result = normalize_config_types(data)
        assert result["release"]["target_month"] == "abc"

    def test_missing_sections_handled(self):
        """GIVEN missing sections
        WHEN normalized
        THEN no error occurs."""
        result = normalize_config_types({})
        assert result == {}

    def test_update_draft_coerces_types(self, state: AppState):
        """GIVEN a draft with string numbers
        WHEN update_draft is called
        THEN the stored draft has integers."""
        draft = state.get_draft()
        draft["release"]["target_month"] = "6"
        draft["release"]["target_year"] = "2026"
        state.update_draft(draft)
        stored = state.config_state.draft_raw
        assert stored["release"]["target_month"] == 6
        assert stored["release"]["target_year"] == 2026


# ── fill_config_defaults tests ──


class TestFillConfigDefaults:
    def test_fills_missing_sections(self):
        """Missing optional sections are created with defaults."""
        data: dict[str, Any] = {"release": {"name": "test"}, "repositories": []}
        fill_config_defaults(data)
        assert "branding" in data
        assert data["branding"]["primary_color"] == "#fb6400"
        assert "settings" in data
        assert data["settings"]["theme"] == "system"
        assert data["settings"]["max_concurrent"] == 10
        assert "layout" in data
        assert data["layers"] == []

    def test_backfills_empty_constrained_fields(self):
        """Empty/None values for constrained fields get proper defaults.

        Note: 0 is a valid numeric value and should NOT be overwritten.
        Only empty strings and None trigger backfill.
        """
        data: dict[str, Any] = {
            "release": {},
            "repositories": [],
            "branding": {"secondary_color": "", "primary_color": ""},
            "settings": {"theme": "", "max_concurrent": None, "timeout_seconds": None},
        }
        fill_config_defaults(data)
        assert data["branding"]["secondary_color"] == "#002754e6"
        assert data["branding"]["primary_color"] == "#fb6400"
        assert data["settings"]["theme"] == "system"
        assert data["settings"]["max_concurrent"] == 10
        assert data["settings"]["timeout_seconds"] == 15

    def test_zero_values_preserved(self):
        """Zero is a valid value for numeric fields and must not be backfilled."""
        data: dict[str, Any] = {
            "release": {},
            "repositories": [],
            "settings": {"max_concurrent": 0, "timeout_seconds": 0, "stale_threshold_days": 0},
        }
        fill_config_defaults(data)
        assert data["settings"]["max_concurrent"] == 0
        assert data["settings"]["timeout_seconds"] == 0
        assert data["settings"]["stale_threshold_days"] == 0

    def test_auto_generates_layers_from_repos(self):
        """When layers is empty but repos reference layers, auto-create them."""
        data: dict[str, Any] = {
            "release": {},
            "repositories": [
                {"name": "a", "url": "x", "layer": "ui"},
                {"name": "b", "url": "y", "layer": "api"},
                {"name": "c", "url": "z", "layer": "ui"},
            ],
        }
        fill_config_defaults(data)
        layer_ids = [layer["id"] for layer in data["layers"]]
        assert "ui" in layer_ids
        assert "api" in layer_ids
        assert len(data["layers"]) == 2

    def test_preserves_existing_layers(self):
        """If layers already defined, don't auto-generate."""
        data: dict[str, Any] = {
            "release": {},
            "repositories": [{"name": "a", "url": "x", "layer": "ui"}],
            "layers": [{"id": "ui", "label": "Frontend", "color": "#111111"}],
        }
        fill_config_defaults(data)
        assert len(data["layers"]) == 1
        assert data["layers"][0]["label"] == "Frontend"
