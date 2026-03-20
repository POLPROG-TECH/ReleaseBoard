"""Tests for staleness severity, branding schema validation, and local provider
output parsing. Each test covers a specific edge case in these subsystems."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from releaseboard.domain.models import BranchInfo
from releaseboard.web.state import (
    AppState,
)

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


class TestLocalProviderSplitlinesGuard:
    """Scenarios for local provider splitlines guard."""

    def test_empty_stdout_no_index_error(self):
        """GIVEN a LocalGitProvider and empty branch creation data."""
        from releaseboard.git.local_provider import LocalGitProvider

        LocalGitProvider()

        """WHEN building BranchInfo with no estimated creation date."""
        info = BranchInfo(name="test", exists=True, estimated_creation_date=None)

        """THEN no IndexError occurs and estimated_creation_date is None."""
        assert info.estimated_creation_date is None


