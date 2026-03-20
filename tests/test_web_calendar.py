"""Tests for the release-calendar web API endpoints.

Covers: GET, PUT, POST import, schema, milestones,
confirmation flow, validation rejection, and edge cases.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from pathlib import Path

from releaseboard.web.server import create_app

MINIMAL_CONFIG: dict[str, Any] = {
    "release": {
        "name": "March 2025",
        "target_month": 3,
        "target_year": 2025,
        "branch_pattern": "release/{MM}.{YYYY}",
    },
    "layers": [
        {"id": "ui", "label": "UI", "order": 0},
    ],
    "repositories": [
        {"name": "web-app", "url": "https://git.local/web.git", "layer": "ui"},
    ],
}

VALID_CALENDAR: dict[str, Any] = {
    "name": "Q2 2025 Release",
    "events": [
        {"date": "2025-07-01", "phase": "sit_start", "label": "SIT begins"},
        {"date": "2025-07-15", "phase": "sit_end"},
        {"date": "2025-08-01", "phase": "prod_install"},
    ],
    "months": [],
}

VALID_CALENDAR_WITH_MONTHS: dict[str, Any] = {
    "name": "Q2 Detailed",
    "events": [],
    "months": [
        {
            "month": 7,
            "year": 2025,
            "phases": {
                "feature_freeze": "2025-07-01",
                "sit_start": "2025-07-05",
                "sit_end": "2025-07-20",
            },
        },
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


# ── GET /api/release-calendar ──


class TestGetCalendar:
    @pytest.mark.asyncio
    async def test_get_empty_calendar(self, client: AsyncClient):
        resp = await client.get("/api/release-calendar")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "release_calendar" in data

    @pytest.mark.asyncio
    async def test_get_after_put(self, client: AsyncClient):
        await client.put(
            "/api/release-calendar",
            json={"release_calendar": VALID_CALENDAR},
        )
        resp = await client.get("/api/release-calendar")
        data = resp.json()
        assert data["ok"] is True
        assert data["release_calendar"]["name"] == "Q2 2025 Release"
        assert len(data["release_calendar"]["events"]) == 3


# ── PUT /api/release-calendar ──


class TestPutCalendar:
    @pytest.mark.asyncio
    async def test_save_valid_calendar(self, client: AsyncClient):
        resp = await client.put(
            "/api/release-calendar",
            json={"release_calendar": VALID_CALENDAR},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_save_with_months(self, client: AsyncClient):
        resp = await client.put(
            "/api/release-calendar",
            json={"release_calendar": VALID_CALENDAR_WITH_MONTHS},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_save_overwrites_previous(self, client: AsyncClient):
        await client.put(
            "/api/release-calendar",
            json={"release_calendar": VALID_CALENDAR},
        )
        new_cal = {**VALID_CALENDAR, "name": "Updated"}
        await client.put(
            "/api/release-calendar",
            json={"release_calendar": new_cal},
        )
        resp = await client.get("/api/release-calendar")
        assert resp.json()["release_calendar"]["name"] == "Updated"


# ── POST /api/release-calendar/import ──


class TestImportCalendar:
    @pytest.mark.asyncio
    async def test_import_valid_json(self, client: AsyncClient):
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": VALID_CALENDAR},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["imported_events"] == 3

    @pytest.mark.asyncio
    async def test_import_rejects_empty_calendar(
        self, client: AsyncClient
    ):
        """Importing with no events and no months is rejected."""
        minimal = {"name": "Minimal"}
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": minimal},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["ok"] is False
        assert any("events" in e or "months" in e for e in data["errors"])

    @pytest.mark.asyncio
    async def test_import_sets_display_defaults(
        self, client: AsyncClient
    ):
        """Import with events but no display section gets defaults."""
        cal = {
            "name": "Minimal with events",
            "events": [{"date": "2025-07-01", "phase": "sit_start"}],
        }
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": cal},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["imported_events"] == 1

    @pytest.mark.asyncio
    async def test_import_rejects_invalid_json_structure(
        self, client: AsyncClient
    ):
        bad = {"name": 12345, "events": "not-a-list"}
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": bad},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["ok"] is False
        assert data.get("validation_failed") is True
        assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_import_rejects_invalid_phase(self, client: AsyncClient):
        bad = {
            "name": "Bad",
            "events": [{"date": "2025-07-01", "phase": "nonexistent"}],
        }
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": bad},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["ok"] is False
        assert any("phase" in e.lower() for e in data["errors"])

    @pytest.mark.asyncio
    async def test_import_rejects_invalid_date(self, client: AsyncClient):
        bad = {
            "name": "Bad dates",
            "events": [{"date": "not-a-date", "phase": "sit_start"}],
        }
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": bad},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["ok"] is False

    @pytest.mark.asyncio
    async def test_import_rejects_empty_name(self, client: AsyncClient):
        bad = {"name": "", "events": []}
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": bad},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["ok"] is False

    @pytest.mark.asyncio
    async def test_import_requires_confirmation_when_existing(
        self, client: AsyncClient
    ):
        # First import succeeds
        await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": VALID_CALENDAR},
        )
        # Second import without confirm is blocked
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": {**VALID_CALENDAR, "name": "New"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["needs_confirmation"] is True

    @pytest.mark.asyncio
    async def test_import_replaces_with_confirmation(
        self, client: AsyncClient
    ):
        # First import
        await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": VALID_CALENDAR},
        )
        # Second import with confirm_replace
        new_cal = {**VALID_CALENDAR, "name": "Replaced"}
        resp = await client.post(
            "/api/release-calendar/import",
            json={
                "release_calendar": new_cal,
                "confirm_replace": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify replaced
        get_resp = await client.get("/api/release-calendar")
        assert get_resp.json()["release_calendar"]["name"] == "Replaced"

    @pytest.mark.asyncio
    async def test_import_too_many_events(self, client: AsyncClient):
        cal = {
            "name": "Too many",
            "events": [
                {"date": "2025-07-01", "phase": "sit_start"}
                for _ in range(501)
            ],
        }
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": cal},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["ok"] is False
        assert any("500" in e or "events" in e.lower() for e in data["errors"])

    @pytest.mark.asyncio
    async def test_import_too_many_months(self, client: AsyncClient):
        cal = {
            "name": "Too many months",
            "events": [],
            "months": [
                {"month": (i % 12) + 1, "year": 2025, "phases": {}}
                for i in range(121)
            ],
        }
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": cal},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["ok"] is False

    @pytest.mark.asyncio
    async def test_import_name_too_long(self, client: AsyncClient):
        cal = {"name": "x" * 201, "events": []}
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": cal},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["ok"] is False

    @pytest.mark.asyncio
    async def test_import_event_label_too_long(self, client: AsyncClient):
        cal = {
            "name": "Test",
            "events": [
                {
                    "date": "2025-07-01",
                    "phase": "sit_start",
                    "label": "x" * 201,
                }
            ],
        }
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": cal},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_import_missing_event_date(self, client: AsyncClient):
        cal = {
            "name": "Bad",
            "events": [{"phase": "sit_start"}],
        }
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": cal},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_import_missing_event_phase(self, client: AsyncClient):
        cal = {
            "name": "Bad",
            "events": [{"date": "2025-07-01"}],
        }
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": cal},
        )
        assert resp.status_code == 422


# ── GET /api/release-calendar/schema ──


class TestCalendarSchema:
    @pytest.mark.asyncio
    async def test_schema_endpoint_returns_ok(self, client: AsyncClient):
        resp = await client.get("/api/release-calendar/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "schema" in data
        assert "example" in data

    @pytest.mark.asyncio
    async def test_schema_has_expected_structure(self, client: AsyncClient):
        resp = await client.get("/api/release-calendar/schema")
        data = resp.json()
        assert "properties" in data["schema"] or "type" in data["schema"]

    @pytest.mark.asyncio
    async def test_example_is_dict_with_name(self, client: AsyncClient):
        resp = await client.get("/api/release-calendar/schema")
        example = resp.json()["example"]
        assert isinstance(example, dict)
        assert "name" in example


# ── GET /api/release-calendar/milestones ──


class TestCalendarMilestones:
    @pytest.mark.asyncio
    async def test_milestones_empty_when_no_calendar(
        self, client: AsyncClient
    ):
        resp = await client.get("/api/release-calendar/milestones")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["milestones"] == []

    @pytest.mark.asyncio
    async def test_milestones_after_import(self, client: AsyncClient):
        await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": VALID_CALENDAR},
        )
        resp = await client.get("/api/release-calendar/milestones")
        data = resp.json()
        assert data["ok"] is True
        milestones = data["milestones"]
        assert len(milestones) > 0
        # Each milestone must have date and days_remaining
        for m in milestones:
            assert "date" in m
            assert "days_remaining" in m
            assert "phase" in m

    @pytest.mark.asyncio
    async def test_milestones_from_months(self, client: AsyncClient):
        await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": VALID_CALENDAR_WITH_MONTHS},
        )
        resp = await client.get("/api/release-calendar/milestones")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["milestones"]) > 0

    @pytest.mark.asyncio
    async def test_milestones_include_labels(self, client: AsyncClient):
        await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": VALID_CALENDAR},
        )
        resp = await client.get("/api/release-calendar/milestones")
        milestones = resp.json()["milestones"]
        labeled = [m for m in milestones if m.get("label")]
        assert len(labeled) > 0
        assert labeled[0]["label"] == "SIT begins"


# ── Edge cases ──


class TestCalendarEdgeCases:
    @pytest.mark.asyncio
    async def test_put_then_import_needs_confirm(self, client: AsyncClient):
        """PUT creates calendar, then import should require confirmation."""
        await client.put(
            "/api/release-calendar",
            json={"release_calendar": VALID_CALENDAR},
        )
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": {**VALID_CALENDAR, "name": "New"}},
        )
        data = resp.json()
        assert data["ok"] is False
        assert data["needs_confirmation"] is True

    @pytest.mark.asyncio
    async def test_import_with_both_events_and_months(
        self, client: AsyncClient
    ):
        cal = {
            "name": "Combined",
            "events": [
                {"date": "2025-07-01", "phase": "sit_start"},
            ],
            "months": [
                {
                    "month": 8,
                    "year": 2025,
                    "phases": {"prod_install": "2025-08-15"},
                },
            ],
        }
        resp = await client.post(
            "/api/release-calendar/import",
            json={"release_calendar": cal},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["imported_events"] == 1
        assert data["imported_months"] == 1

    @pytest.mark.asyncio
    async def test_put_empty_calendar_clears(self, client: AsyncClient):
        """PUT with minimal calendar clears previous data."""
        await client.put(
            "/api/release-calendar",
            json={"release_calendar": VALID_CALENDAR},
        )
        await client.put(
            "/api/release-calendar",
            json={"release_calendar": {"name": "Empty", "events": [], "months": []}},
        )
        resp = await client.get("/api/release-calendar")
        cal = resp.json()["release_calendar"]
        assert cal["name"] == "Empty"
        assert cal["events"] == []
